"""Private, manually recorded dietary preferences.

Profiles are display-only household notes.  They are never interpreted as medical
advice, matched against meals, or used to claim that food is safe.
"""

from __future__ import annotations

from copy import deepcopy

from ..const import PRIVILEGED
from .context import Context
from .validation import DomainError, fields, text
from .validation import revision as strict_revision

ADULT_ROLES = frozenset({"owner", "parent", "adult"})
MANAGEMENT = frozenset({"self", "parent_child"})
STATUSES = frozenset({"active", "cleared"})
CONTENT_FIELDS = frozenset({"likes", "dislikes", "avoid", "allergy_note"})
SAVE_FIELDS = CONTENT_FIELDS | {"member_id", "revision"}
MAX_LABELS = 30
MAX_LABEL_LENGTH = 80
MAX_NOTE_LENGTH = 1000


def _bucket(state: dict) -> dict:
    bucket = state.get("dietary_profiles", {})
    if not isinstance(bucket, dict):
        raise DomainError("invalid_field", "dietary_profiles")
    return bucket


def _mutable_bucket(ctx: Context) -> dict:
    bucket = ctx.state.get("dietary_profiles")
    if bucket is None:
        bucket = {}
        ctx.state["dietary_profiles"] = bucket
    if not isinstance(bucket, dict):
        raise DomainError("invalid_field", "dietary_profiles")
    return bucket


def _current_member(state: dict, member_id, *, field="member_id") -> dict:
    member_id = text(member_id, field, 80)
    member = state.get("members", {}).get(member_id)
    if not isinstance(member, dict) or not member.get("active", False):
        raise DomainError("forbidden")
    return member


def _actor(ctx: Context) -> dict:
    actor = _current_member(ctx.state, ctx.actor_id)
    if actor.get("role") == "guest":
        raise DomainError("forbidden")
    return actor


def _basic_record(record, member_id: str) -> dict:
    if not isinstance(record, dict):
        raise DomainError("invalid_field", "dietary_profiles")
    if (
        record.get("member_id") != member_id
        or record.get("management") not in MANAGEMENT
        or record.get("status") not in STATUSES
    ):
        raise DomainError("invalid_field", "dietary_profiles")
    strict_revision(record.get("revision"))
    return record


def _record(state: dict, member_id: str, record_revision) -> dict:
    record = _bucket(state).get(member_id)
    if record is None:
        raise DomainError("not_found")
    record = _basic_record(record, member_id)
    if strict_revision(record_revision) != record["revision"]:
        raise DomainError("conflict")
    if record["revision"] == 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    return record


def _touch(ctx: Context, record: dict) -> dict:
    if strict_revision(record.get("revision")) == 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    return ctx.touch(record)


def _labels(value, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_LABELS:
        raise DomainError("invalid_field", field)
    result = []
    seen = set()
    for item in value:
        label = text(item, field, MAX_LABEL_LENGTH)
        identity = label.casefold()
        if identity in seen:
            raise DomainError("invalid_field", field)
        seen.add(identity)
        result.append(label)
    return result


def _note(value) -> str:
    if not isinstance(value, str) or len(value) > MAX_NOTE_LENGTH:
        raise DomainError("invalid_field", "allergy_note")
    return value.strip()


def _content(payload: dict) -> dict:
    result = {
        "likes": _labels(payload["likes"], "likes"),
        "dislikes": _labels(payload["dislikes"], "dislikes"),
        "avoid": _labels(payload["avoid"], "avoid"),
        "allergy_note": _note(payload["allergy_note"]),
    }
    seen = set()
    for field in ("likes", "dislikes", "avoid"):
        for label in result[field]:
            identity = label.casefold()
            if identity in seen:
                raise DomainError("invalid_field", field)
            seen.add(identity)
    return result


def _can_parent_manage(actor: dict, target: dict, record: dict | None) -> bool:
    return (
        actor.get("role") in PRIVILEGED
        and target.get("role") == "child"
        and (record is None or record.get("management") == "parent_child")
    )


def _effective_share(record: dict, target: dict) -> bool:
    """Consent is invalidated conservatively by any membership-record change."""
    member_revision = target.get("revision")
    consent_revision = record.get("consent_member_revision")
    return (
        target.get("role") in ADULT_ROLES
        and record.get("status") == "active"
        and record.get("management") == "self"
        and record.get("share_with_parents") is True
        and type(member_revision) is int
        and type(consent_revision) is int
        and 1 <= member_revision <= 2**53 - 1
        and consent_revision == member_revision
    )


def _controller(ctx: Context, member_id: str, record: dict | None) -> tuple[dict, str]:
    actor = _actor(ctx)
    target = _current_member(ctx.state, member_id)
    if actor["id"] == target["id"] and actor.get("role") in ADULT_ROLES:
        return target, "self"
    if _can_parent_manage(actor, target, record):
        return target, "parent_child"
    raise DomainError("forbidden")


def _receipt(record: dict) -> dict:
    """Return no preference text because Engine journals command receipts."""
    return {
        "member_id": record["member_id"],
        "revision": record["revision"],
        "status": record["status"],
    }


def _save(ctx: Context, payload: dict) -> dict:
    fields(payload, SAVE_FIELDS, CONTENT_FIELDS | {"member_id"})
    member_id = text(payload["member_id"], "member_id", 80)
    existing = _bucket(ctx.state).get(member_id)
    if existing is None:
        _, authority = _controller(ctx, member_id, None)
        if "revision" in payload:
            raise DomainError("invalid_field", "revision")
        record = {
            "member_id": member_id,
            "management": authority,
            "share_with_parents": False,
            "status": "active",
            **_content(payload),
            "revision": 1,
            "updated_at": ctx.now.isoformat(),
        }
        _mutable_bucket(ctx)[member_id] = record
        return _receipt(record)

    raw_record = _basic_record(existing, member_id)
    target, authority = _controller(ctx, member_id, raw_record)
    record = _record(ctx.state, member_id, payload.get("revision"))
    content = _content(payload)
    share = authority == "self" and _effective_share(record, target)
    unchanged = (
        record["status"] == "active"
        and all(record.get(key) == value for key, value in content.items())
        and record["management"] == authority
        and record.get("share_with_parents") is share
        and (share or "consent_member_revision" not in record)
    )
    if unchanged:
        raise DomainError("invalid_transition")
    record.update(
        **content,
        management=authority,
        share_with_parents=share if authority == "self" else False,
        status="active",
    )
    if not share:
        record.pop("consent_member_revision", None)
    _touch(ctx, record)
    return _receipt(record)


def _access_set(ctx: Context, payload: dict) -> dict:
    fields(
        payload,
        {"member_id", "revision", "member_revision", "share_with_parents"},
        {"member_id", "revision", "share_with_parents"},
    )
    member_id = text(payload["member_id"], "member_id", 80)
    actor = _actor(ctx)
    target = _current_member(ctx.state, member_id)
    allowed = payload["share_with_parents"]
    if not isinstance(allowed, bool):
        raise DomainError("invalid_field", "share_with_parents")
    if actor["id"] != target["id"] or actor.get("role") not in ADULT_ROLES:
        raise DomainError("forbidden")
    member_revision = strict_revision(payload.get("member_revision"))
    if strict_revision(target.get("revision")) != member_revision:
        raise DomainError("conflict")
    record = _record(ctx.state, member_id, payload["revision"])
    if record["status"] != "active":
        raise DomainError("invalid_transition")
    effective = _effective_share(record, target)
    if (
        record["management"] == "self"
        and effective is allowed
        and record.get("share_with_parents") is allowed
    ):
        raise DomainError("invalid_transition")
    record["management"] = "self"
    record["share_with_parents"] = allowed
    if allowed:
        record["consent_member_revision"] = member_revision
    else:
        record.pop("consent_member_revision", None)
    _touch(ctx, record)
    return _receipt(record)


def _clear(ctx: Context, payload: dict) -> dict:
    fields(payload, {"member_id", "revision"}, {"member_id"})
    member_id = text(payload["member_id"], "member_id", 80)
    raw_record = _bucket(ctx.state).get(member_id)
    if raw_record is None:
        _controller(ctx, member_id, None)
        raise DomainError("not_found")
    raw_record = _basic_record(raw_record, member_id)
    _controller(ctx, member_id, raw_record)
    record = _record(ctx.state, member_id, payload.get("revision"))
    if record["status"] != "active":
        raise DomainError("invalid_transition")
    for key in CONTENT_FIELDS | {"share_with_parents", "consent_member_revision"}:
        record.pop(key, None)
    record["status"] = "cleared"
    _touch(ctx, record)
    return _receipt(record)


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Apply one private profile mutation and return an opaque receipt."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    if action == "dietary_save":
        return _save(ctx, payload)
    if action == "dietary_access_set":
        return _access_set(ctx, payload)
    if action == "dietary_clear":
        return _clear(ctx, payload)
    raise DomainError("unknown_action")


def _base(member_id: str, status: str, *, revision=None, can_edit=False) -> dict:
    result = {
        "member_id": member_id,
        "status": status,
        "can_edit": can_edit,
        "can_share": False,
    }
    if revision is not None:
        result["revision"] = revision
    return result


def _row(record: dict, target: dict, *, can_edit: bool, can_share: bool) -> dict:
    result = _base(
        record["member_id"], record["status"], revision=record["revision"], can_edit=can_edit
    )
    result["can_share"] = can_share
    if record["status"] == "active":
        result.update(
            {
                key: deepcopy(record[key])
                for key in (
                    "likes",
                    "dislikes",
                    "avoid",
                    "allergy_note",
                    "management",
                )
            }
        )
        result["share_with_parents"] = _effective_share(record, target)
    return result


def view(state: dict, actor: dict) -> dict:
    """Return only profiles authorized for the actor's current role and consent."""
    empty = {"self": None, "managed_children": [], "shared_adults": []}
    if not isinstance(actor, dict):
        return empty
    current = state.get("members", {}).get(actor.get("id"), {})
    modules = state.get("settings", {}).get("modules", [])
    if (
        not isinstance(modules, list)
        or "pantry" not in modules
        or not isinstance(current, dict)
        or not current.get("active")
        or current.get("role") == "guest"
    ):
        return empty
    profiles = _bucket(state)
    actor_id = current["id"]
    adult = current.get("role") in ADULT_ROLES
    own = profiles.get(actor_id)
    result = {**empty}
    if own is None:
        result["self"] = _base(actor_id, "missing", can_edit=adult)
    elif isinstance(own, dict):
        result["self"] = _row(
            own,
            current,
            can_edit=adult,
            can_share=adult and own.get("status") == "active",
        )
    else:
        raise DomainError("invalid_field", "dietary_profiles")

    if current.get("role") not in PRIVILEGED:
        return result
    for member in state.get("members", {}).values():
        if not isinstance(member, dict) or member.get("id") == actor_id or not member.get("active"):
            continue
        member_id = member.get("id")
        record = profiles.get(member_id)
        if member.get("role") == "child":
            if record is None:
                result["managed_children"].append(_base(member_id, "missing", can_edit=True))
            elif isinstance(record, dict) and record.get("management") == "parent_child":
                result["managed_children"].append(
                    _row(record, member, can_edit=True, can_share=False)
                )
            continue
        if (
            member.get("role") in ADULT_ROLES
            and isinstance(record, dict)
            and record.get("status") == "active"
            and record.get("management") == "self"
            and _effective_share(record, member)
        ):
            result["shared_adults"].append(_row(record, member, can_edit=False, can_share=False))
    return result


def authorize_replay(ctx: Context, action: str, payload: dict) -> None:
    """Recheck current identity and target authority before returning a cached receipt."""
    if not isinstance(payload, dict):
        raise DomainError("forbidden")
    if action not in {"dietary_save", "dietary_access_set", "dietary_clear"}:
        raise DomainError("unknown_action")
    member_id = payload.get("member_id")
    if not isinstance(member_id, str):
        raise DomainError("forbidden")
    record = _bucket(ctx.state).get(member_id)
    if action == "dietary_access_set":
        actor = _actor(ctx)
        target = _current_member(ctx.state, member_id)
        if actor["id"] != target["id"] or actor.get("role") not in ADULT_ROLES:
            raise DomainError("forbidden")
        member_revision = strict_revision(payload.get("member_revision"))
        if strict_revision(target.get("revision")) != member_revision:
            raise DomainError("conflict")
        if (
            not isinstance(record, dict)
            or record.get("status") != "active"
            or record.get("management") != "self"
            or _effective_share(record, target) is not payload.get("share_with_parents")
        ):
            raise DomainError("forbidden")
        return
    _controller(ctx, member_id, record if isinstance(record, dict) else None)
