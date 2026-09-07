"""Owner-reviewed Home Assistant source bindings for ephemeral presence evidence."""

from __future__ import annotations

import hashlib
import inspect
from copy import deepcopy

import voluptuous as vol
from homeassistant.helpers import selector

from .domain import presence
from .domain.validation import DomainError
from .domain.validation import revision as strict_revision


def _strict_age(value):
    if type(value) is not int or not 30 <= value <= 3600:
        raise vol.Invalid("presence_max_age_seconds")
    return value


async def _ha_user(flow):
    user_id = flow.context.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise DomainError("forbidden")
    getter = getattr(getattr(flow.hass, "auth", None), "async_get_user", None)
    if not callable(getter):
        raise DomainError("forbidden")
    user = getter(user_id)
    if inspect.isawaitable(user):
        user = await user
    if user is None or getattr(user, "id", None) != user_id:
        raise DomainError("forbidden")
    return user


def _entry_current(flow, runtime) -> bool:
    entries = getattr(flow.hass, "config_entries", None)
    getter = getattr(entries, "async_get_entry", None)
    if callable(getter) and getter(flow.config_entry.entry_id) is not flow.config_entry:
        return False
    attached = getattr(flow.config_entry, "runtime_data", runtime)
    return attached is runtime


async def _scope(flow):
    runtime, actor_id = flow._authorized_runtime()
    user = await _ha_user(flow)
    # The user lookup is an await boundary. Reauthorize before reading private Options.
    current_runtime, current_actor = flow._authorized_runtime()
    if (
        current_runtime is not runtime
        or current_actor != actor_id
        or not _entry_current(flow, runtime)
    ):
        raise DomainError("conflict")
    state = runtime.engine.snapshot()
    member = state.get("members", {}).get(actor_id)
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") != "owner"
        or member.get("ha_user_id") != user.id
    ):
        raise DomainError("forbidden")
    actor_revision = strict_revision(member.get("revision"))
    options = deepcopy(dict(flow.config_entry.options))
    presence.validate_options(options)
    return {
        "runtime": runtime,
        "actor": actor_id,
        "actor_revision": actor_revision,
        "user": user,
        "options": options,
        "state": state,
    }


def _same_scope(left, right) -> bool:
    return bool(
        isinstance(left, dict)
        and isinstance(right, dict)
        and left["runtime"] is right["runtime"]
        and left["actor"] == right["actor"]
        and left["actor_revision"] == right["actor_revision"]
        and left["user"].id == right["user"].id
        and left["options"] == right["options"]
    )


def _member_marker(state, member_id: str):
    member = state.get("members", {}).get(member_id)
    if not isinstance(member, dict):
        return None
    return tuple(member.get(key) for key in ("id", "revision", "active", "role", "ha_user_id"))


def _sync_review(flow, ctx, reviewed_scope, target_marker, summary, options):
    """Recheck synchronous authority at the exact Engine transaction boundary."""
    runtime, actor_id = flow._authorized_runtime()
    if (
        runtime is not reviewed_scope["runtime"]
        or actor_id != reviewed_scope["actor"]
        or not _entry_current(flow, runtime)
        or deepcopy(dict(flow.config_entry.options)) != reviewed_scope["options"]
    ):
        raise DomainError("conflict")
    member = ctx.state.get("members", {}).get(actor_id)
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") != "owner"
        or member.get("ha_user_id") != reviewed_scope["user"].id
    ):
        raise DomainError("forbidden")
    if strict_revision(member.get("revision")) != reviewed_scope["actor_revision"]:
        raise DomainError("conflict")
    if _member_marker(ctx.state, summary["member"]) != target_marker:
        raise DomainError("conflict")
    if summary["enabled"] and not _registered_readable(
        flow, reviewed_scope["user"], summary["entity_id"]
    ):
        raise DomainError("forbidden")
    return presence.sync_bindings(ctx, options)


def _members(scope) -> dict:
    state = scope["state"]
    config = presence.validate_options(scope["options"])
    result = {}
    for member_id, member in state.get("members", {}).items():
        if (
            isinstance(member, dict)
            and member.get("active") is True
            and member.get("role") != "guest"
        ):
            result[member_id] = member.get("name", member_id)
    # A stale binding remains selectable so an owner can explicitly remove it.
    for member_id in config["sources"]:
        result.setdefault(member_id, member_id)
    return result


def _registered_readable(flow, user, entity_id: str) -> bool:
    try:
        from homeassistant.auth.permissions.const import POLICY_READ
        from homeassistant.helpers import entity_registry

        registry = entity_registry.async_get(flow.hass)
        record = registry.async_get(entity_id)
        return bool(
            record is not None
            and getattr(record, "entity_id", None) == entity_id
            and entity_id.split(".", 1)[0] in {"person", "device_tracker"}
            and user.permissions.check_entity(entity_id, POLICY_READ) is True
        )
    except (AttributeError, ImportError, KeyError, TypeError, ValueError):
        return False


def _hash(entity_id: str) -> str:
    return hashlib.sha256(entity_id.encode()).hexdigest()


def _mirror(scope, member_id: str) -> dict | None:
    value = scope["state"].get("presence", {}).get("bindings", {}).get(member_id)
    return value if isinstance(value, dict) else None


def _next_revision(existing: dict | None, mirror: dict | None, desired: dict) -> int:
    desired_mirror = {
        "member": desired["member"],
        "status": desired["status"],
        "member_revision": desired["member_revision"],
    }
    if desired["status"] == "active":
        desired_mirror["source_hash"] = _hash(desired["entity_id"])
    if isinstance(mirror, dict):
        try:
            mirror_revision = strict_revision(mirror.get("revision"))
        except DomainError:
            raise DomainError("conflict") from None
        if mirror == {**desired_mirror, "revision": mirror_revision}:
            return mirror_revision
    else:
        mirror_revision = 0
    existing_revision = 0
    if isinstance(existing, dict):
        existing_revision = strict_revision(existing.get("revision"))
    revision = max(existing_revision, mirror_revision) + 1
    if revision > 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    return revision


def _proposal(scope, user_input) -> tuple[dict, dict]:
    if not isinstance(user_input, dict):
        raise DomainError("invalid_field", "payload")
    required = {"member", "enabled", "entity_id", "presence_max_age_seconds"}
    if set(user_input) != required:
        raise DomainError("invalid_field", "payload")
    member_id = user_input["member"]
    if not isinstance(member_id, str) or member_id not in _members(scope):
        raise DomainError("unknown_member")
    enabled = user_input["enabled"]
    if type(enabled) is not bool:
        raise DomainError("invalid_field", "enabled")
    maximum_age = user_input["presence_max_age_seconds"]
    if type(maximum_age) is not int or not 30 <= maximum_age <= 3600:
        raise DomainError("invalid_field", "presence_max_age_seconds")
    config = presence.validate_options(scope["options"])
    existing = config["sources"].get(member_id)
    current_member = scope["state"].get("members", {}).get(member_id)
    if enabled:
        if (
            not isinstance(current_member, dict)
            or current_member.get("active") is not True
            or current_member.get("role") == "guest"
        ):
            raise DomainError("unknown_member")
        entity_id = user_input["entity_id"]
        if not isinstance(entity_id, str) or not _registered_readable(
            scope["flow"], scope["user"], entity_id
        ):
            raise DomainError("forbidden")
        desired = {
            "member": member_id,
            "status": "active",
            "member_revision": strict_revision(current_member.get("revision")),
            "entity_id": entity_id,
        }
    else:
        if existing is None or existing["status"] == "removed":
            raise DomainError("invalid_transition")
        desired = {
            "member": member_id,
            "status": "removed",
            # Removal must remain possible after the bound member epoch became stale.
            "member_revision": existing["member_revision"],
        }
    revision = _next_revision(existing, _mirror(scope, member_id), desired)
    source = {key: value for key, value in desired.items() if key != "member"}
    source["revision"] = revision
    sources = deepcopy(config["sources"])
    sources[member_id] = source
    options = deepcopy(scope["options"])
    options["presence_sources"] = sources
    options["presence_max_age_seconds"] = maximum_age
    presence.validate_options(options)
    if options == scope["options"]:
        raise DomainError("invalid_transition")
    return options, {
        "member": member_id,
        "member_name": _members(scope)[member_id],
        "enabled": enabled,
        "entity_id": source.get("entity_id", ""),
        "binding_revision": revision,
        "member_revision": source["member_revision"],
        "presence_max_age_seconds": maximum_age,
    }


def _editor_schema(scope):
    config = presence.validate_options(scope["options"])
    members = _members(scope)
    default_member = next(iter(members), "")
    current = config["sources"].get(default_member, {})
    return vol.Schema(
        {
            vol.Required("member", default=default_member): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": key, "label": value} for key, value in members.items()]
                )
            ),
            vol.Required("enabled", default=current.get("status") == "active"): bool,
            vol.Optional("entity_id", default=current.get("entity_id", "")): (
                selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                )
            ),
            vol.Required(
                "presence_max_age_seconds", default=config["max_age_seconds"]
            ): _strict_age,
        }
    )


async def source_step(flow, user_input=None):
    """Select one per-member source mutation, then require a separate review."""
    try:
        scope = await _scope(flow)
    except DomainError as error:
        return flow.async_abort(reason=error.code)
    scope["flow"] = flow
    errors = {}
    if user_input is not None:
        displayed = getattr(flow, "_presence_displayed_scope", None)
        if not _same_scope(scope, displayed):
            errors["base"] = "conflict"
        else:
            try:
                member_id = user_input.get("member") if isinstance(user_input, dict) else None
                if isinstance(member_id, str) and _member_marker(
                    scope["state"], member_id
                ) != _member_marker(displayed["state"], member_id):
                    raise DomainError("conflict")
                options, summary = _proposal(scope, user_input)
                flow._presence_review = {
                    "scope": displayed,
                    "options": options,
                    "summary": summary,
                    "target_marker": _member_marker(displayed["state"], summary["member"]),
                }
                return await review_step(flow)
            except DomainError as error:
                errors["base"] = error.code
    flow._presence_displayed_scope = scope
    return flow.async_show_form(
        step_id="presence_sources",
        data_schema=_editor_schema(scope),
        errors=errors,
    )


async def review_step(flow, user_input=None):
    """Commit one frozen source change only after explicit current review."""
    review = getattr(flow, "_presence_review", None)
    if not isinstance(review, dict):
        return await source_step(flow)
    try:
        current = await _scope(flow)
        if not _same_scope(current, review["scope"]):
            raise DomainError("conflict")
        summary = review["summary"]
        if _member_marker(current["state"], summary["member"]) != review.get("target_marker"):
            raise DomainError("conflict")
        if summary["enabled"] and not _registered_readable(
            flow, current["user"], summary["entity_id"]
        ):
            raise DomainError("forbidden")
    except DomainError as error:
        # The frozen review contains a private entity id. Never render it after
        # authority, identity, entry, Options, or source permission changed.
        flow._presence_review = None
        return flow.async_abort(reason=error.code)
    errors = {}
    if user_input is not None:
        if not isinstance(user_input, dict) or set(user_input) != {"confirmed"}:
            errors["base"] = "invalid_field"
        elif type(user_input["confirmed"]) is not bool:
            errors["base"] = "invalid_field"
        elif not user_input["confirmed"]:
            flow._presence_review = None
            return await source_step(flow)
        else:
            try:
                runtime = current["runtime"]
                options = deepcopy(review["options"])
                from homeassistant.util import dt as dt_util

                await runtime.engine.system_update(
                    "presence-bindings",
                    dt_util.utcnow(),
                    lambda ctx: _sync_review(
                        flow,
                        ctx,
                        review["scope"],
                        review["target_marker"],
                        summary,
                        options,
                    ),
                )
                # Store persistence above was an await boundary. Recheck Options,
                # identity, entity permission, and backup before Config Entry commit.
                after = await _scope(flow)
                if not _same_scope(after, review["scope"]):
                    raise DomainError("conflict")
                if _member_marker(after["state"], summary["member"]) != review["target_marker"]:
                    raise DomainError("conflict")
                if summary["enabled"] and not _registered_readable(
                    flow, after["user"], summary["entity_id"]
                ):
                    raise DomainError("forbidden")
                result = flow.async_create_entry(title="", data=options)
                if result.get("type") != "abort":
                    flow._presence_review = None
                return result
            except DomainError as error:
                flow._presence_review = None
                return flow.async_abort(reason=error.code)
            except OSError:
                errors["base"] = "storage_error"
    summary = review["summary"]
    return flow.async_show_form(
        step_id="presence_source_review",
        data_schema=vol.Schema({vol.Required("confirmed", default=False): bool}),
        errors=errors,
        description_placeholders={
            "member": summary["member_name"],
            "entity": summary["entity_id"] if summary["enabled"] else "—",
            "action": "enable" if summary["enabled"] else "remove",
            "binding_revision": str(summary["binding_revision"]),
            "member_revision": str(summary["member_revision"]),
            "max_age_seconds": str(summary["presence_max_age_seconds"]),
        },
    )
