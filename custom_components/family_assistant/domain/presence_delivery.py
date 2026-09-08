"""Independent consent for private nonurgent notification presence gating.

Dashboard subscriptions grant no background observation permission. This module
stores only reviewed preferences/identity lineage, never observations or entity IDs.
"""

from __future__ import annotations

from copy import deepcopy

from ..const import PRIVILEGED
from . import presence
from .context import Context
from .validation import DomainError, fields, revision, text, timestamp

DEFAULT_WAIT_MINUTES = 720
ACTIONS = frozenset({"notification_access_set", "guardian_notification_access_set"})
PAYLOAD_FIELDS = frozenset(
    {
        "member",
        "member_revision",
        "binding_revision",
        "preference_revision",
        "enabled",
        "max_wait_minutes",
        "actor_member_revision",
    }
)
RECORD_FIELDS = frozenset(
    {
        "member",
        "revision",
        "member_revision",
        "binding_revision",
        "status",
        "max_wait_minutes",
        "approved_by",
        "approved_by_revision",
        "created_at",
        "updated_at",
    }
)


def _records(state: dict) -> dict:
    bucket = state.get("presence", {})
    records = bucket.get("delivery_preferences", {}) if isinstance(bucket, dict) else None
    if not isinstance(records, dict):
        raise DomainError("invalid_field", "presence_delivery")
    return records


def _wait(value) -> int:
    if type(value) is not int or not 15 <= value <= 1440:
        raise DomainError("invalid_field", "max_wait_minutes")
    return value


def _record(value, member_id: str) -> dict:
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "presence_delivery")
    fields(value, RECORD_FIELDS, RECORD_FIELDS)
    if value.get("member") != member_id or value.get("status") not in ("enabled", "disabled"):
        raise DomainError("invalid_field", "presence_delivery")
    for key in ("revision", "member_revision", "binding_revision", "approved_by_revision"):
        revision(value[key])
    if text(value["approved_by"], "approved_by", 80) != value["approved_by"]:
        raise DomainError("invalid_field", "approved_by")
    _wait(value["max_wait_minutes"])
    if timestamp(value["created_at"], "created_at") > timestamp(value["updated_at"], "updated_at"):
        raise DomainError("invalid_field", "updated_at")
    return value


def _authorized(ctx: Context, action: str, payload: dict) -> tuple[dict, dict]:
    if action not in ACTIONS:
        raise DomainError("unknown_action")
    presence._module(ctx.state)
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    fields(payload, PAYLOAD_FIELDS, PAYLOAD_FIELDS)
    member_id = presence._member_id(payload["member"])
    subject_revision = revision(payload["member_revision"])
    binding_revision = revision(payload["binding_revision"])
    if payload["preference_revision"] is not None:
        revision(payload["preference_revision"])
    _wait(payload["max_wait_minutes"])
    if type(payload["enabled"]) is not bool:
        raise DomainError("invalid_field", "enabled")
    actor = presence._current_actor(ctx)
    if revision(payload["actor_member_revision"]) != actor["revision"]:
        raise DomainError("conflict")
    presence._authority(
        ctx,
        "access_set" if action == "notification_access_set" else "guardian_access_set",
        member_id,
        subject_revision,
    )
    binding = presence._binding_record(
        presence._bucket(ctx.state)["bindings"].get(member_id), member_id
    )
    if binding["revision"] != binding_revision:
        raise DomainError("conflict")
    if payload["enabled"] and (
        binding["status"] != "active" or binding["member_revision"] != subject_revision
    ):
        raise DomainError("conflict")
    return actor, binding


def _receipt(record: dict) -> dict:
    return {key: record[key] for key in ("member", "revision", "status")}


def handle(ctx: Context, action: str, payload: dict) -> dict:
    actor, binding = _authorized(ctx, action, payload)
    member_id = payload["member"]
    records = _records(ctx.state)
    old = records.get(member_id)
    wanted = {
        "member": member_id,
        "member_revision": payload["member_revision"],
        "binding_revision": binding["revision"],
        "status": "enabled" if payload["enabled"] else "disabled",
        "max_wait_minutes": payload["max_wait_minutes"],
        "approved_by": actor["id"],
        "approved_by_revision": actor["revision"],
    }
    if old is None:
        if payload["preference_revision"] is not None:
            raise DomainError("conflict")
        if not payload["enabled"]:
            raise DomainError("invalid_transition")
        version, created = 1, ctx.now.isoformat()
    else:
        old = _record(old, member_id)
        if payload["preference_revision"] != old["revision"]:
            raise DomainError("conflict")
        if old["revision"] == 2**53 - 1:
            raise DomainError("invalid_field", "revision")
        if all(old[key] == value for key, value in wanted.items()):
            raise DomainError("invalid_transition")
        version, created = old["revision"] + 1, old["created_at"]
    new = {**wanted, "revision": version, "created_at": created, "updated_at": ctx.now.isoformat()}
    _record(new, member_id)
    ctx.state.setdefault("presence", {}).setdefault("delivery_preferences", {})[member_id] = new
    return _receipt(new)


def effective_policy(state: dict, member_id: str) -> dict | None:
    try:
        presence._module(state)
        record = _record(_records(state).get(member_id), member_id)
        member = presence._current_member(state, member_id)
        approver = presence._current_member(state, record["approved_by"])
        binding = presence._binding_record(
            presence._bucket(state)["bindings"].get(member_id), member_id
        )
        if (
            record["status"] != "enabled"
            or member["revision"] != record["member_revision"]
            or approver["revision"] != record["approved_by_revision"]
            or not isinstance(approver.get("ha_user_id"), str)
            or not approver["ha_user_id"]
            or binding["status"] != "active"
            or binding["revision"] != record["binding_revision"]
            or binding["member_revision"] != member["revision"]
            or (
                member_id != approver["id"]
                and (member["role"] != "child" or approver["role"] not in PRIVILEGED)
            )
        ):
            return None
        return deepcopy(record)
    except (DomainError, AttributeError, KeyError, TypeError, ValueError):
        return None


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict) -> None:
    actor, _binding = _authorized(ctx, action, payload)
    record = _record(_records(ctx.state).get(payload["member"]), payload["member"])
    if not isinstance(result, dict):
        raise DomainError("forbidden")
    fields(result, {"member", "revision", "status"}, {"member", "revision", "status"})
    revision(result["revision"])
    previous = payload["preference_revision"]
    if (
        result != _receipt(record)
        or record["revision"] != (1 if previous is None else previous + 1)
        or record["approved_by"] != actor["id"]
        or record["approved_by_revision"] != actor["revision"]
        or record["member_revision"] != payload["member_revision"]
        or record["binding_revision"] != payload["binding_revision"]
        or record["status"] != ("enabled" if payload["enabled"] else "disabled")
        or record["max_wait_minutes"] != payload["max_wait_minutes"]
    ):
        raise DomainError("conflict")


def _row(state: dict, member: dict) -> dict:
    try:
        record = _record(_records(state).get(member["id"]), member["id"])
    except DomainError:
        record = None
    try:
        binding = presence._binding_record(
            presence._bucket(state)["bindings"].get(member["id"]), member["id"]
        )
    except DomainError:
        binding = None
    return {
        "member": member["id"],
        "member_revision": member["revision"],
        "binding_revision": binding["revision"] if binding else None,
        "source_available": bool(
            binding
            and binding["status"] == "active"
            and binding["member_revision"] == member["revision"]
        ),
        "preference_revision": record["revision"] if record else None,
        "enabled": bool(record and record["status"] == "enabled"),
        "effective": effective_policy(state, member["id"]) is not None,
        "max_wait_minutes": record["max_wait_minutes"] if record else DEFAULT_WAIT_MINUTES,
        "approved_by": record["approved_by"] if record else None,
    }


def view(state: dict, actor: dict) -> dict:
    empty = {"self": None}
    try:
        presence._module(state)
        current = presence._current_member(state, actor["id"])
        if current["role"] != actor["role"] or current["revision"] != revision(actor["revision"]):
            return empty
        result = {"self": _row(state, current)}
        if current["role"] in PRIVILEGED:
            result["managed"] = [
                _row(state, member)
                for member in state["members"].values()
                if member.get("active") is True and member.get("role") == "child"
            ]
        return result
    except (DomainError, KeyError, TypeError, AttributeError):
        return empty
