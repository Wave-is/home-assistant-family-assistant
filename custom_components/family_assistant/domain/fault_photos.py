"""One private, verified image attached to an already reported maintenance fault.

The photograph is evidence of an observation, never proof of completed work.
This consumer reuses the private media store and its crash-safe collector.
"""

from __future__ import annotations

from ..const import PRIVILEGED
from . import maintenance
from .context import Context
from .validation import DomainError, fields, revision, text, timestamp

PURPOSE = "maintenance_fault"
MAX_PHOTO_EVENTS = 100


def _actor(state: dict, actor: dict) -> dict:
    current = state.get("members", {}).get(actor.get("id")) if isinstance(actor, dict) else None
    if (
        not isinstance(current, dict)
        or current.get("active") is not True
        or current.get("role") not in {*PRIVILEGED, "adult", "child"}
        or current.get("role") != actor.get("role")
        or revision(current.get("revision")) != revision(actor.get("revision"))
    ):
        raise DomainError("forbidden")
    return current


def _fault(state: dict, actor: dict, fault_id) -> tuple[dict, dict]:
    maintenance._require_module(state, tasks_required=True)
    actor = _actor(state, actor)
    fault_id = text(fault_id, "fault_id", 80)
    fault = maintenance._bucket(state, "faults").get(fault_id)
    if not isinstance(fault, dict) or fault.get("id") != fault_id:
        raise DomainError("forbidden")
    revision(fault.get("revision"))
    revision(fault.get("asset_revision"))
    revision(fault.get("reporter_member_revision"))
    if fault.get("status") != "reported":
        raise DomainError("invalid_field", "fault")
    task = state.get("tasks", {}).get(fault.get("task_id"))
    if not isinstance(task, dict) or task.get("id") != fault.get("task_id"):
        raise DomainError("conflict")
    revision(task.get("revision"))
    source = task.get("source")
    if (
        not isinstance(source, dict)
        or source.get("kind") != "maintenance_fault"
        or source.get("fault_id") != fault_id
        or source.get("asset_id") != fault.get("asset_id")
        or revision(source.get("asset_revision")) != fault["asset_revision"]
    ):
        raise DomainError("conflict")
    reporter = (
        fault.get("reporter") == actor["id"]
        and fault.get("reporter_member_revision") == actor["revision"]
    )
    if (
        actor["role"] not in PRIVILEGED
        and not reporter
        and not maintenance._task_assigned_to(task, actor)
    ):
        raise DomainError("forbidden")
    return fault, task


def upload_target(state: dict, actor: dict, fault_id, fault_revision) -> tuple[dict, dict]:
    """Pin an open, current fault and its assignment before reserving private bytes."""
    fault, task = _fault(state, actor, fault_id)
    if fault["revision"] != revision(fault_revision):
        raise DomainError("conflict")
    if task.get("status") not in {"assigned", "accepted", "in_progress", "needs_changes"}:
        raise DomainError("invalid_transition")
    if fault.get("attachment_ids") != []:
        raise DomainError("invalid_transition")
    assignee = state.get("members", {}).get(task.get("assignee"))
    if (
        not isinstance(assignee, dict)
        or assignee.get("active") is not True
        or assignee.get("role") not in {*PRIVILEGED, "adult", "child"}
        or revision(assignee.get("revision")) != revision(task.get("assignee_revision"))
    ):
        raise DomainError("conflict")
    return fault, {
        "fault_id": fault["id"],
        "fault_revision": fault["revision"],
        "task_id": task["id"],
        "assignee": task["assignee"],
        "assignee_revision": task["assignee_revision"],
    }


def attached_reference(state: dict, actor: dict, record: dict) -> bool:
    """Current fault visibility and an exact reverse reference authorize image reads."""
    scope = record.get("scope")
    if (
        record.get("purpose") != PURPOSE
        or not isinstance(scope, dict)
        or set(scope) != {"kind", "fault_id"}
        or scope.get("kind") != PURPOSE
    ):
        return False
    try:
        fault, _task = _fault(state, actor, scope["fault_id"])
    except DomainError:
        return False
    return fault.get("attachment_ids") == [record.get("id")]


def public_attachment(state: dict, actor: dict, fault: dict) -> dict | None:
    from . import media

    attachments = fault.get("attachment_ids")
    if not isinstance(attachments, list) or len(attachments) != 1:
        return None
    try:
        record = media._record(state, attachments[0])
        if record.get("status") != "attached" or not attached_reference(state, actor, record):
            return None
        return media.read_metadata(state, actor, attachments[0], None)
    except DomainError:
        return None


def handle(ctx: Context, action: str, payload: dict) -> dict:
    from . import media

    required = {"id", "revision", "actor_member_revision", "media"}
    if action == "fault_photo_purge":
        required.add("reason")
    elif action != "fault_photo_attach":
        raise DomainError("unknown_action")
    fields(payload, required, required)
    actor = _actor(ctx.state, ctx.actor)
    if revision(payload["actor_member_revision"]) != actor["revision"]:
        raise DomainError("conflict")
    fault, _task = _fault(ctx.state, actor, payload["id"])
    if revision(payload["revision"]) != fault["revision"]:
        raise DomainError("conflict")
    if fault["revision"] == 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    reference = payload["media"]
    if not isinstance(reference, dict):
        raise DomainError("invalid_field", "media")
    fields(reference, {"id", "revision"}, {"id", "revision"})
    record = media._record(ctx.state, reference["id"])
    media._blob_key(record)
    if record["revision"] != revision(reference["revision"]):
        raise DomainError("conflict")
    media._ensure_advance(record)
    history = fault.get("photo_history", [])
    if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
        raise DomainError("invalid_field", "photo_history")
    if len(history) >= MAX_PHOTO_EVENTS:
        raise DomainError("quota_exceeded")
    event = {
        "action": action,
        "actor": actor["id"],
        "actor_member_revision": actor["revision"],
        "media_id": record["id"],
        "at": ctx.now.isoformat(),
    }
    if action == "fault_photo_attach":
        _, target = upload_target(ctx.state, actor, fault["id"], fault["revision"])
        if record.get("purpose") != PURPOSE or record.get("status") != "available":
            raise DomainError("invalid_transition")
        _, reserved_target = media._reserved_authority(ctx.state, actor, record)
        if reserved_target != target:
            raise DomainError("conflict")
        if timestamp(ctx.now, "now") >= timestamp(record.get("expires_at"), "expires_at"):
            raise DomainError("invalid_transition")
        record.update(
            status="attached", scope={"kind": PURPOSE, "fault_id": fault["id"]}, expires_at=None
        )
        fault["attachment_ids"] = [record["id"]]
    else:
        if actor["role"] != "owner":
            raise DomainError("forbidden")
        if record.get("status") != "attached" or not attached_reference(ctx.state, actor, record):
            raise DomainError("conflict")
        # The reverse reference must point to THIS reviewed fault, not another one.
        if record["scope"]["fault_id"] != fault["id"]:
            raise DomainError("conflict")
        reason = text(payload["reason"], "reason", 500)
        event["reason"] = reason
        record["status"] = "deleting"
        fault["attachment_ids"] = []
        fault["photo_purge"] = {
            "media_id": record["id"],
            "reason": reason,
            "actor": actor["id"],
            "actor_member_revision": actor["revision"],
            "at": ctx.now.isoformat(),
        }
    fault["photo_history"] = [*history, event]
    media._advance(ctx, record)
    ctx.touch(fault)
    return {"id": fault["id"], "revision": fault["revision"], "status": fault["status"]}


def authorize_replay(ctx: Context, action: str, payload: dict) -> None:
    actor = _actor(ctx.state, ctx.actor)
    if revision(payload.get("actor_member_revision")) != actor["revision"]:
        raise DomainError("conflict")
    fault, _task = _fault(ctx.state, actor, payload.get("id"))
    if fault["revision"] != revision(payload.get("revision")) + 1:
        raise DomainError("conflict")
    reference = payload.get("media")
    if not isinstance(reference, dict):
        raise DomainError("forbidden")
    if action == "fault_photo_attach":
        attachment = public_attachment(ctx.state, actor, fault)
        if attachment is None or attachment["id"] != reference.get("id"):
            raise DomainError("conflict")
    elif action == "fault_photo_purge":
        purge = fault.get("photo_purge")
        if (
            actor["role"] != "owner"
            or fault.get("attachment_ids") != []
            or not isinstance(purge, dict)
            or purge.get("media_id") != reference.get("id")
            or purge.get("actor") != actor["id"]
            or purge.get("actor_member_revision") != actor["revision"]
        ):
            raise DomainError("forbidden")
    else:
        raise DomainError("unknown_action")
