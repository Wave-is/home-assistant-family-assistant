"""Consent-bound, ephemeral Home Assistant presence evidence."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import UTC, datetime

from ..const import PRIVILEGED
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

DEFAULT_MAX_AGE_SECONDS = 300
MIN_MAX_AGE_SECONDS = 30
MAX_MAX_AGE_SECONDS = 3600
MAX_ACTIVE_SOURCES = 20
MAX_SOURCE_RECORDS = 100
ENTITY_PATTERN = re.compile(r"^(?:person|device_tracker)\.[a-z0-9_]+$")
STATUSES = frozenset({"active", "removed"})
SUBSCRIPTION_STATUSES = frozenset({"enabled", "disabled"})
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _module(state: dict) -> None:
    modules = state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "presence" not in modules:
        raise DomainError("module_disabled")


def _bucket(state: dict) -> dict:
    value = state.get("presence", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "presence")
    bindings = value.get("bindings", {})
    subscriptions = value.get("subscriptions", {})
    if not isinstance(bindings, dict) or not isinstance(subscriptions, dict):
        raise DomainError("invalid_field", "presence")
    return {"bindings": bindings, "subscriptions": subscriptions}


def _mutable_bucket(ctx: Context) -> dict:
    value = ctx.state.setdefault("presence", {"bindings": {}, "subscriptions": {}})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "presence")
    value.setdefault("bindings", {})
    value.setdefault("subscriptions", {})
    if not isinstance(value["bindings"], dict) or not isinstance(value["subscriptions"], dict):
        raise DomainError("invalid_field", "presence")
    return value


def _member_id(value, field: str = "member") -> str:
    result = text(value, field, 80)
    if result != value:
        raise DomainError("invalid_field", field)
    return result


def _current_member(state: dict, member_id: str) -> dict:
    member = state.get("members", {}).get(member_id)
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") == "guest"
    ):
        raise DomainError("forbidden")
    strict_revision(member.get("revision"))
    return member


def _current_actor(ctx: Context) -> dict:
    actor = _current_member(ctx.state, _member_id(ctx.actor_id, "actor"))
    if (
        actor.get("role") != ctx.actor.get("role")
        or actor.get("revision") != ctx.actor.get("revision")
        or not isinstance(actor.get("ha_user_id"), str)
        or not actor["ha_user_id"]
    ):
        raise DomainError("forbidden")
    return actor


def _source_hash(entity_id: str) -> str:
    return hashlib.sha256(entity_id.encode()).hexdigest()


def validate_options(options) -> dict:
    """Return strict presence-only options without retaining unrelated settings."""
    if not isinstance(options, dict):
        raise DomainError("invalid_field", "presence_sources")
    maximum_age = options.get("presence_max_age_seconds", DEFAULT_MAX_AGE_SECONDS)
    if (
        type(maximum_age) is not int
        or not MIN_MAX_AGE_SECONDS <= maximum_age <= MAX_MAX_AGE_SECONDS
    ):
        raise DomainError("invalid_field", "presence_max_age_seconds")
    raw = options.get("presence_sources", {})
    if not isinstance(raw, dict) or len(raw) > MAX_SOURCE_RECORDS:
        raise DomainError("invalid_field", "presence_sources")
    sources = {}
    entities = set()
    active = 0
    for raw_member, value in raw.items():
        member_id = _member_id(raw_member)
        if not isinstance(value, dict):
            raise DomainError("invalid_field", "presence_sources")
        status = value.get("status")
        allowed = {"revision", "status", "member_revision"}
        if status == "active":
            allowed.add("entity_id")
        fields(value, allowed, allowed)
        if status not in STATUSES:
            raise DomainError("invalid_field", "status")
        source_revision = strict_revision(value["revision"])
        member_revision = strict_revision(value["member_revision"])
        normalized = {
            "revision": source_revision,
            "status": status,
            "member_revision": member_revision,
        }
        if status == "active":
            entity_id = value["entity_id"]
            if (
                not isinstance(entity_id, str)
                or len(entity_id) > 255
                or not ENTITY_PATTERN.fullmatch(entity_id)
                or entity_id in entities
            ):
                raise DomainError("invalid_field", "entity_id")
            entities.add(entity_id)
            normalized["entity_id"] = entity_id
            active += 1
        sources[member_id] = normalized
    if active > MAX_ACTIVE_SOURCES:
        raise DomainError("invalid_field", "presence_sources")
    return {"sources": sources, "max_age_seconds": maximum_age}


def _binding_metadata(member_id: str, source: dict) -> dict:
    result = {
        "member": member_id,
        "revision": source["revision"],
        "status": source["status"],
        "member_revision": source["member_revision"],
    }
    if source["status"] == "active":
        result["source_hash"] = _source_hash(source["entity_id"])
    return result


def _binding_record(value, member_id: str) -> dict:
    if not isinstance(value, dict) or value.get("member") != member_id:
        raise DomainError("invalid_field", "presence")
    status = value.get("status")
    allowed = {"member", "revision", "status", "member_revision"}
    if status == "active":
        allowed.add("source_hash")
    if set(value) != allowed or status not in STATUSES:
        raise DomainError("invalid_field", "presence")
    strict_revision(value.get("revision"))
    strict_revision(value.get("member_revision"))
    if status == "active" and (
        not isinstance(value.get("source_hash"), str)
        or not HASH_PATTERN.fullmatch(value["source_hash"])
    ):
        raise DomainError("invalid_field", "presence")
    return value


def _subscription_record(value, member_id: str) -> dict:
    allowed = {
        "member",
        "revision",
        "member_revision",
        "binding_revision",
        "status",
        "created_at",
        "updated_at",
    }
    if (
        not isinstance(value, dict)
        or set(value) != allowed
        or value.get("member") != member_id
        or value.get("status") not in SUBSCRIPTION_STATUSES
    ):
        raise DomainError("invalid_field", "presence")
    strict_revision(value.get("revision"))
    strict_revision(value.get("member_revision"))
    strict_revision(value.get("binding_revision"))
    timestamp(value.get("created_at"), "created_at")
    timestamp(value.get("updated_at"), "updated_at")
    return value


def sync_bindings(ctx: Context, options) -> dict:
    """Mirror only source lineage into Engine state; never persist an entity ID."""
    config = validate_options(options)
    bucket = _mutable_bucket(ctx)
    current = bucket["bindings"]
    if set(current) - set(config["sources"]):
        # Options must carry content-free removed records so delete/re-add has no ABA.
        raise DomainError("conflict")
    normalized = {}
    for member_id, source in config["sources"].items():
        value = _binding_metadata(member_id, source)
        old = current.get(member_id)
        if old is None:
            if value["revision"] != 1:
                raise DomainError("conflict")
        else:
            old = _binding_record(old, member_id)
            old_revision = strict_revision(old.get("revision"))
            if value["revision"] == old_revision:
                if old != value:
                    raise DomainError("conflict")
            elif value["revision"] != old_revision + 1:
                raise DomainError("conflict")
        # Unchanged stale pins stay inert: they must not prevent an owner from
        # removing another source, nor silently acquire the member's new epoch.
        if source["status"] == "active" and old != value:
            member = _current_member(ctx.state, member_id)
            if member["revision"] != source["member_revision"]:
                raise DomainError("conflict")
        normalized[member_id] = value
    bucket["bindings"] = normalized
    return {
        "records": len(normalized),
        "active": sum(value["status"] == "active" for value in normalized.values()),
    }


def _valid_binding(state: dict, member_id: str, source: dict) -> dict | None:
    try:
        binding = _binding_record(_bucket(state)["bindings"].get(member_id), member_id)
        expected = _binding_metadata(member_id, source)
        member = _current_member(state, member_id)
        if binding != expected or member["revision"] != source["member_revision"]:
            return None
        return binding
    except DomainError:
        return None


def _valid_subscription(state: dict, member_id: str, binding: dict) -> dict | None:
    try:
        record = _subscription_record(_bucket(state)["subscriptions"].get(member_id), member_id)
        if (
            record.get("status") != "enabled"
            or record.get("member_revision") != binding.get("member_revision")
            or record.get("binding_revision") != binding.get("revision")
        ):
            return None
        return record
    except DomainError:
        return None


def select_sources(state: dict, actor: dict, options) -> dict[str, str]:
    """Select only sources this current actor may project and the adapter may read."""
    try:
        _module(state)
        current = _current_member(state, _member_id(actor.get("id"), "actor"))
        if (
            current.get("role") != actor.get("role")
            or current.get("revision") != actor.get("revision")
            or not isinstance(current.get("ha_user_id"), str)
            or not current["ha_user_id"]
        ):
            return {}
        config = validate_options(options)
    except (AttributeError, DomainError):
        return {}
    result = {}
    for member_id, source in config["sources"].items():
        if current.get("role") not in PRIVILEGED and member_id != current["id"]:
            continue
        if source["status"] != "active":
            continue
        binding = _valid_binding(state, member_id, source)
        if binding is None or _valid_subscription(state, member_id, binding) is None:
            continue
        result[member_id] = source["entity_id"]
    return result


def _payload(payload) -> tuple[str, int, int, int | None, bool]:
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    required = {
        "member",
        "member_revision",
        "binding_revision",
        "subscription_revision",
        "enabled",
    }
    fields(payload, required, required)
    member_id = _member_id(payload["member"])
    member_revision = strict_revision(payload["member_revision"])
    binding_revision = strict_revision(payload["binding_revision"])
    subscription_revision = payload["subscription_revision"]
    if subscription_revision is not None:
        subscription_revision = strict_revision(subscription_revision)
    enabled = payload["enabled"]
    if type(enabled) is not bool:
        raise DomainError("invalid_field", "enabled")
    return member_id, member_revision, binding_revision, subscription_revision, enabled


def _binding(state: dict, member_id: str, member_revision: int, revision: int) -> dict:
    try:
        binding = _binding_record(_bucket(state)["bindings"].get(member_id), member_id)
    except DomainError:
        raise DomainError("conflict") from None
    if (
        binding.get("member") != member_id
        or strict_revision(binding.get("revision")) != revision
        or strict_revision(binding.get("member_revision")) != member_revision
        or binding.get("status") not in STATUSES
    ):
        raise DomainError("conflict")
    return binding


def _receipt(record: dict) -> dict:
    return {
        "member": record["member"],
        "revision": record["revision"],
        "status": record["status"],
    }


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Apply a self-consent change and return a content-free receipt."""
    if action != "access_set":
        raise DomainError("unknown_action")
    _module(ctx.state)
    actor = _current_actor(ctx)
    member_id, member_revision, binding_revision, subscription_revision, enabled = _payload(payload)
    if actor["id"] != member_id or actor["revision"] != member_revision:
        raise DomainError("forbidden" if actor["id"] != member_id else "conflict")
    binding = _binding(ctx.state, member_id, member_revision, binding_revision)
    if enabled and binding["status"] != "active":
        raise DomainError("invalid_transition")
    subscriptions = _mutable_bucket(ctx)["subscriptions"]
    old = subscriptions.get(member_id)
    if old is None:
        if subscription_revision is not None:
            raise DomainError("invalid_field", "subscription_revision")
        if not enabled:
            raise DomainError("invalid_transition")
        revision = 1
        created_at = ctx.now.isoformat()
    else:
        old = _subscription_record(old, member_id)
        old_revision = strict_revision(old.get("revision"))
        if subscription_revision is None:
            raise DomainError("invalid_field", "subscription_revision")
        if subscription_revision != old_revision:
            raise DomainError("conflict")
        if old_revision == 2**53 - 1:
            raise DomainError("invalid_field", "revision")
        if (
            old.get("status") == ("enabled" if enabled else "disabled")
            and old.get("member_revision") == member_revision
            and old.get("binding_revision") == binding_revision
        ):
            raise DomainError("invalid_transition")
        revision = old_revision + 1
        created_at = old.get("created_at", ctx.now.isoformat())
    record = {
        "member": member_id,
        "revision": revision,
        "member_revision": member_revision,
        "binding_revision": binding_revision,
        "status": "enabled" if enabled else "disabled",
        "created_at": created_at,
        "updated_at": ctx.now.isoformat(),
    }
    subscriptions[member_id] = record
    return _receipt(record)


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict) -> None:
    """Recheck the current member, source lineage, and consent receipt."""
    if action != "access_set":
        raise DomainError("unknown_action")
    _module(ctx.state)
    actor = _current_actor(ctx)
    member_id, member_revision, binding_revision, _, enabled = _payload(payload)
    if actor["id"] != member_id or actor["revision"] != member_revision:
        raise DomainError("forbidden" if actor["id"] != member_id else "conflict")
    binding = _binding(ctx.state, member_id, member_revision, binding_revision)
    if enabled and binding["status"] != "active":
        raise DomainError("conflict")
    if not isinstance(result, dict):
        raise DomainError("forbidden")
    fields(result, {"member", "revision", "status"}, {"member", "revision", "status"})
    expected_status = "enabled" if enabled else "disabled"
    try:
        record = _subscription_record(_bucket(ctx.state)["subscriptions"].get(member_id), member_id)
    except DomainError:
        raise DomainError("conflict") from None
    if (
        record.get("member_revision") != member_revision
        or record.get("binding_revision") != binding_revision
        or _receipt(record) != result
        or result.get("member") != member_id
        or result.get("status") != expected_status
    ):
        raise DomainError("conflict")


def _observation(value, now: datetime, maximum_age: int) -> tuple[str, str, str | None]:
    if not isinstance(value, dict) or set(value) != {"state", "observed_at"}:
        return "unknown", "unavailable", None
    state = value["state"]
    if not isinstance(state, str) or not state.strip():
        return "unknown", "unavailable", None
    state = state.strip()
    if state in {
        "unknown",
        "unavailable",
    }:
        return "unknown", "unavailable", None
    try:
        observed = timestamp(value["observed_at"], "observed_at").astimezone(UTC)
        age = (now.astimezone(UTC) - observed).total_seconds()
    except (DomainError, OverflowError, ValueError):
        return "unknown", "unavailable", None
    if age < -5 or age > maximum_age:
        return "unknown", "stale", None
    status = "reported_home" if state == "home" else "reported_away"
    return status, "fresh", observed.isoformat()


def _self_row(
    state: dict,
    actor: dict,
    config: dict,
    observations: dict,
    now: datetime,
) -> dict:
    member_id = actor["id"]
    source = config["sources"].get(member_id)
    binding = _valid_binding(state, member_id, source) if source else None
    subscription = _bucket(state)["subscriptions"].get(member_id)
    effective = (
        source is not None
        and source["status"] == "active"
        and binding is not None
        and _valid_subscription(state, member_id, binding) is not None
    )
    subscription_revision = None
    if isinstance(subscription, dict):
        try:
            subscription_revision = strict_revision(subscription.get("revision"))
        except DomainError:
            subscription_revision = None
    row = {
        "member": member_id,
        "member_revision": actor["revision"],
        "binding_revision": binding.get("revision") if binding else None,
        "subscription_revision": subscription_revision,
        "enabled": effective,
        "can_edit": binding is not None and source["status"] == "active",
        "status": "unknown",
        "reason": (
            "not_shared" if binding is not None and source["status"] == "active" else "unconfigured"
        ),
        "observed_at": None,
    }
    if effective:
        row["status"], row["reason"], row["observed_at"] = _observation(
            observations.get(member_id), now, config["max_age_seconds"]
        )
    return row


def view(state: dict, actor: dict, options, observations, now: datetime) -> dict:
    """Return a normalized presence projection without raw source identifiers."""
    empty = {"self": None, "shared": []}
    if not isinstance(state, dict) or not isinstance(actor, dict):
        return empty
    try:
        _module(state)
        current = _current_member(state, _member_id(actor.get("id"), "actor"))
        if (
            current.get("role") != actor.get("role")
            or current.get("revision") != actor.get("revision")
            or not isinstance(current.get("ha_user_id"), str)
            or not current["ha_user_id"]
        ):
            return empty
        now = timestamp(now, "now")
        if not isinstance(observations, dict):
            observations = {}
        try:
            config = validate_options(options)
        except DomainError:
            config = {"sources": {}, "max_age_seconds": DEFAULT_MAX_AGE_SECONDS}
        own = _self_row(state, current, config, observations, now)
        result = {"self": own, "shared": []}
        if current.get("role") not in PRIVILEGED:
            return result
        selected = select_sources(state, current, options)
        for member_id in selected:
            if member_id == current["id"]:
                continue
            member = state.get("members", {}).get(member_id)
            if not isinstance(member, dict):
                continue
            status, reason, observed_at = _observation(
                observations.get(member_id), now, config["max_age_seconds"]
            )
            result["shared"].append(
                {
                    "member": member_id,
                    "member_revision": member["revision"],
                    "status": status,
                    "reason": reason,
                    "observed_at": observed_at,
                }
            )
        return deepcopy(result)
    except (DomainError, OverflowError, ValueError, TypeError):
        return empty
