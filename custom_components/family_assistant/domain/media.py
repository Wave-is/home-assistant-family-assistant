"""Private metadata and authority primitives for verified scoped image media.

Binary I/O, decoding, and HTTP handling deliberately live outside this domain.
Consumers support one JPEG/PNG/WebP attachment and have no generic
attach command, notification, provider, or device effect.
"""

from __future__ import annotations

import re
import secrets
from copy import deepcopy
from datetime import timedelta

from ..const import PRIVILEGED
from . import task_access
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

PURPOSE = "task_report"
FAULT_PURPOSE = "maintenance_fault"
DOCUMENT_PURPOSE = "equipment_document"
PURPOSES = frozenset({PURPOSE, FAULT_PURPOSE, DOCUMENT_PURPOSE})
IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MIME_TYPES = IMAGE_MIME_TYPES | {"application/pdf"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_VERIFIED_BYTES = 250 * 1024 * 1024
MAX_PENDING_MEMBER = 5
MAX_PENDING_HOUSEHOLD = 20
MAX_RECORDS = 10_000
MAX_TOMBSTONES = 1_000
MAX_REAP = 100
RESERVED_TTL = timedelta(hours=1)
AVAILABLE_TTL = timedelta(hours=24)
TOMBSTONE_TTL = timedelta(hours=24)
PENDING = frozenset({"reserved", "available"})
STATUSES = frozenset({"reserved", "available", "attached", "deleting", "deleted"})
OPEN_TASK_STATUSES = frozenset({"assigned", "accepted", "in_progress", "needs_changes"})
FINAL_TASK_STATUSES = frozenset({"completed", "cancelled", "archived"})
PUBLIC_FIELDS = ("id", "revision", "purpose", "mime_type", "size_bytes", "status")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_OPAQUE_ID = re.compile(r"M[0-9a-f]{32}")
_BLOB_KEY = re.compile(r"[0-9a-f]{64}")
_TOMBSTONE_FIELDS = {
    "id",
    "revision",
    "status",
    "created_at",
    "updated_at",
    "deleted_at",
}


def _version(value, field="revision") -> int:
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def mimes_for(purpose) -> frozenset:
    if purpose == DOCUMENT_PURPOSE:
        return MIME_TYPES
    return (
        IMAGE_MIME_TYPES
        if isinstance(purpose, str) and purpose in {PURPOSE, FAULT_PURPOSE}
        else frozenset()
    )


def _modules(state: dict, purpose=PURPOSE) -> None:
    modules = state.get("settings", {}).get("modules", [])
    required = "maintenance" if purpose == DOCUMENT_PURPOSE else "tasks"
    if not isinstance(modules, list) or required not in modules:
        raise DomainError("module_disabled")


def _current_member(state: dict, member_id, *, field="uploader") -> dict:
    member_id = text(member_id, field, 80)
    member = state.get("members", {}).get(member_id)
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") not in {*PRIVILEGED, "adult", "child"}
    ):
        raise DomainError("forbidden")
    _version(member.get("revision"), f"{field}_revision")
    return member


def _current_actor(ctx: Context) -> dict:
    current = _current_member(ctx.state, ctx.actor_id)
    try:
        actor_revision = _version(ctx.actor.get("revision"), "uploader_revision")
    except (AttributeError, DomainError):
        raise DomainError("forbidden") from None
    if current.get("role") != ctx.actor.get("role") or current["revision"] != actor_revision:
        raise DomainError("forbidden")
    return current


def _task_scope(state: dict, actor: dict, task_id, task_revision) -> tuple[dict, dict]:
    _modules(state)
    task_id = text(task_id, "task_id", 80)
    expected_revision = _version(task_revision, "task_revision")
    task = state.get("tasks", {}).get(task_id)
    if task is None:
        raise DomainError("not_found")
    if not isinstance(task, dict) or task.get("id") != task_id:
        raise DomainError("invalid_field", "task")
    if task_access.personal_task(task):
        raise DomainError("forbidden")  # Personal reminders never accept report uploads.
    if actor.get("role") not in PRIVILEGED and task.get("assignee") != actor.get("id"):
        raise DomainError("forbidden")
    if _version(task.get("revision"), "task_revision") != expected_revision:
        raise DomainError("conflict")
    if task.get("status") in FINAL_TASK_STATUSES or task.get("status") == "submitted":
        raise DomainError("invalid_transition")
    if task.get("status") not in OPEN_TASK_STATUSES:
        raise DomainError("invalid_field", "status")
    if task.get("report_type") != "photo":
        raise DomainError("invalid_field", "purpose")
    assignee = _current_member(state, task.get("assignee"), field="assignee")
    if task.get("assignee_revision") != assignee["revision"]:
        raise DomainError("conflict")
    if actor.get("role") not in PRIVILEGED and not task_access.may_view(state, actor, task):
        raise DomainError("forbidden")
    target = {
        "task_id": task_id,
        "task_revision": expected_revision,
        "assignee": assignee["id"],
        "assignee_revision": assignee["revision"],
    }
    return task, target


def _bucket(state: dict) -> dict:
    value = state.get("media", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "media")
    return value


def _mutable_bucket(ctx: Context) -> dict:
    value = ctx.state.get("media")
    if value is None:
        value = {}
        ctx.state["media"] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "media")
    return value


def _record(state: dict, media_id) -> dict:
    media_id = text(media_id, "id", 80)
    if not _OPAQUE_ID.fullmatch(media_id):
        raise DomainError("invalid_field", "id")
    record = _bucket(state).get(media_id)
    if record is None:
        raise DomainError("forbidden")
    if not isinstance(record, dict) or record.get("id") != media_id:
        raise DomainError("invalid_field", "media")
    _version(record.get("revision"))
    if record.get("status") not in STATUSES:
        raise DomainError("invalid_field", "status")
    return record


def _pending_and_budget(media: dict, uploader: str) -> tuple[int, int, int]:
    member_pending = household_pending = verified_budget = live_records = tombstones = 0
    for record in media.values():
        if not isinstance(record, dict) or record.get("status") not in STATUSES:
            raise DomainError("invalid_field", "media")
        status = record["status"]
        if status != "deleted":
            live_records += 1
        else:
            tombstones += 1
        if status in PENDING:
            household_pending += 1
            if record.get("uploader") == uploader:
                member_pending += 1
        if status == "reserved":
            verified_budget += MAX_FILE_BYTES
        elif status in {"available", "attached"}:
            size = record.get("size_bytes")
            if type(size) is not int or not 1 <= size <= MAX_FILE_BYTES:
                raise DomainError("invalid_field", "size_bytes")
            verified_budget += size
        elif status == "deleting":
            size = record.get("size_bytes")
            if size is None:
                verified_budget += MAX_FILE_BYTES
            elif type(size) is int and 1 <= size <= MAX_FILE_BYTES:
                verified_budget += size
            else:
                raise DomainError("invalid_field", "size_bytes")
    if live_records >= MAX_RECORDS or tombstones >= MAX_TOMBSTONES:
        raise DomainError("quota_exceeded")
    return member_pending, household_pending, verified_budget


def _receipt(record: dict) -> dict:
    return {key: record[key] for key in ("id", "revision", "status")}


def _advance(ctx: Context, record: dict) -> None:
    _ensure_advance(record)
    ctx.touch(record)


def _ensure_advance(record: dict) -> None:
    if _version(record.get("revision")) == 2**53 - 1:
        raise DomainError("invalid_field", "revision")


def _new_identifiers(media: dict) -> tuple[str, str]:
    used_keys = {
        record.get("blob_key")
        for record in media.values()
        if isinstance(record, dict) and isinstance(record.get("blob_key"), str)
    }
    for _ in range(10):
        media_id = f"M{secrets.token_hex(16)}"
        if media_id not in media:
            blob_key = secrets.token_hex(32)
            if blob_key not in used_keys:
                return media_id, blob_key
    raise DomainError("quota_exceeded")


def _deadline(now, delta: timedelta) -> str:
    moment = timestamp(now, "now")
    try:
        return (moment + delta).isoformat()
    except OverflowError:
        raise DomainError("invalid_field", "now") from None


def _blob_key(record: dict) -> str:
    value = record.get("blob_key")
    if not isinstance(value, str) or not _BLOB_KEY.fullmatch(value):
        raise DomainError("invalid_field", "blob_key")
    return value


def _tombstone_time(media_id: str, record: dict):
    """Validate the exact content-free deletion record before forgetting it."""
    if (
        not isinstance(record, dict)
        or set(record) != _TOMBSTONE_FIELDS
        or record.get("id") != media_id
        or record.get("status") != "deleted"
    ):
        raise DomainError("invalid_field", "media")
    _version(record.get("revision"))
    created_at = timestamp(record.get("created_at"), "created_at")
    updated_at = timestamp(record.get("updated_at"), "updated_at")
    deleted_at = timestamp(record.get("deleted_at"), "deleted_at")
    if created_at > deleted_at or updated_at != deleted_at:
        raise DomainError("invalid_field", "media")
    return deleted_at


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Reserve private metadata; upload finalization is internal-only."""
    if action != "reserve":
        raise DomainError("unknown_action")
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    reservation_fields = _reservation_fields(payload)
    fields(payload, reservation_fields, reservation_fields)
    actor = _current_actor(ctx)
    if _version(payload["uploader_revision"], "uploader_revision") != actor["revision"]:
        raise DomainError("conflict")
    _, intended_target = _payload_target(ctx.state, actor, payload)
    media = _bucket(ctx.state)
    member_pending, household_pending, budget = _pending_and_budget(media, actor["id"])
    if (
        member_pending >= MAX_PENDING_MEMBER
        or household_pending >= MAX_PENDING_HOUSEHOLD
        or budget + MAX_FILE_BYTES > MAX_VERIFIED_BYTES
    ):
        raise DomainError("quota_exceeded")
    media_id, blob_key = _new_identifiers(media)
    now = timestamp(ctx.now, "now")
    record = {
        "id": media_id,
        "revision": 1,
        "uploader": actor["id"],
        "uploader_revision": actor["revision"],
        "purpose": payload["purpose"],
        "mime_type": None,
        "size_bytes": None,
        "sha256": None,
        "status": "reserved",
        "scope": {
            "kind": "uploader_private",
            "member": actor["id"],
            "member_revision": actor["revision"],
            "intended_target": intended_target,
        },
        "blob_key": blob_key,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": _deadline(now, RESERVED_TTL),
    }
    _mutable_bucket(ctx)[media_id] = record
    return _receipt(record)


def _reservation_fields(payload: dict) -> set[str]:
    purpose = payload.get("purpose")
    if not isinstance(purpose, str) or purpose not in PURPOSES:
        raise DomainError("invalid_field", "purpose")
    target = {
        PURPOSE: {"task_id", "task_revision"},
        FAULT_PURPOSE: {"fault_id", "fault_revision"},
        DOCUMENT_PURPOSE: {"asset_id", "asset_revision"},
    }[purpose]
    return {"purpose", "uploader_revision", *target}


def _payload_target(state: dict, actor: dict, payload: dict) -> tuple[dict, dict]:
    if payload["purpose"] == PURPOSE:
        return _task_scope(state, actor, payload["task_id"], payload["task_revision"])
    if payload["purpose"] == DOCUMENT_PURPOSE:
        from .asset_documents import upload_target

        return upload_target(state, actor, payload["asset_id"], payload["asset_revision"])
    from .fault_photos import upload_target

    return upload_target(state, actor, payload["fault_id"], payload["fault_revision"])


def _reserved_authority(state: dict, actor: dict, record: dict) -> tuple[dict, dict]:
    if (
        not isinstance(record.get("purpose"), str)
        or record.get("purpose") not in PURPOSES
        or record.get("uploader") != actor["id"]
        or record.get("uploader_revision") != actor["revision"]
    ):
        raise DomainError("forbidden")
    scope = record.get("scope")
    if (
        not isinstance(scope, dict)
        or scope.get("kind") != "uploader_private"
        or scope.get("member") != actor["id"]
        or scope.get("member_revision") != actor["revision"]
        or not isinstance(scope.get("intended_target"), dict)
    ):
        raise DomainError("forbidden")
    target = scope["intended_target"]
    if record.get("status") == "available" and record.get("mime_type") not in mimes_for(
        record["purpose"]
    ):
        raise DomainError("invalid_field", "mime_type")
    if record["purpose"] == PURPOSE:
        task, current_target = _task_scope(
            state, actor, target.get("task_id"), target.get("task_revision")
        )
    elif record["purpose"] == DOCUMENT_PURPOSE:
        from .asset_documents import upload_target

        task, current_target = upload_target(
            state, actor, target.get("asset_id"), target.get("asset_revision")
        )
    else:
        from .fault_photos import upload_target

        task, current_target = upload_target(
            state, actor, target.get("fault_id"), target.get("fault_revision")
        )
    if target != current_target:
        raise DomainError("conflict")
    return task, target


def finalize(
    ctx: Context,
    actor_id,
    media_id,
    revision,
    verifiedmime,
    size,
    sha256,
) -> dict:
    """Persist metadata for bytes already verified by the private blob adapter."""
    actor = _current_member(ctx.state, actor_id)
    record = _record(ctx.state, media_id)
    _blob_key(record)
    requested_revision = _version(revision)
    if verifiedmime not in mimes_for(record.get("purpose")):
        raise DomainError("invalid_field", "mime_type")
    if type(size) is not int or not 1 <= size <= MAX_FILE_BYTES:
        raise DomainError("invalid_field", "size_bytes")
    if not isinstance(sha256, str) or not _DIGEST.fullmatch(sha256):
        raise DomainError("invalid_field", "sha256")
    _reserved_authority(ctx.state, actor, record)
    if timestamp(ctx.now, "now") >= timestamp(record.get("expires_at"), "expires_at"):
        raise DomainError("invalid_transition")
    if record["status"] == "available":
        if (
            requested_revision == 2**53 - 1
            or record["revision"] != requested_revision + 1
            or record.get("mime_type") != verifiedmime
            or record.get("size_bytes") != size
            or record.get("sha256") != sha256
        ):
            raise DomainError("conflict")
        return _receipt(record)
    if record["status"] != "reserved":
        raise DomainError("invalid_transition")
    if record["revision"] != requested_revision:
        raise DomainError("conflict")
    _ensure_advance(record)
    record.update(
        mime_type=verifiedmime,
        size_bytes=size,
        sha256=sha256,
        status="available",
        expires_at=_deadline(ctx.now, AVAILABLE_TTL),
    )
    _advance(ctx, record)
    return _receipt(record)


def attach_task_report(ctx: Context, task: dict, reference: dict) -> dict:
    """Attach one available own upload inside a task submission transaction."""
    if not isinstance(reference, dict):
        raise DomainError("invalid_field", "media")
    fields(reference, {"id", "revision"}, {"id", "revision"})
    actor = _current_actor(ctx)
    if not isinstance(task, dict) or ctx.state.get("tasks", {}).get(task.get("id")) is not task:
        raise DomainError("not_found")
    current_task, target = _task_scope(ctx.state, actor, task["id"], task.get("revision"))
    if current_task is not task:
        raise DomainError("conflict")
    record = _record(ctx.state, reference["id"])
    if record.get("purpose") != PURPOSE:
        raise DomainError("invalid_field", "purpose")
    _blob_key(record)
    if record["revision"] != _version(reference["revision"]):
        raise DomainError("conflict")
    _reserved_authority(ctx.state, actor, record)
    if record["scope"]["intended_target"] != target:
        raise DomainError("conflict")
    if record["status"] != "available":
        raise DomainError("invalid_transition")
    if timestamp(ctx.now, "now") >= timestamp(record.get("expires_at"), "expires_at"):
        raise DomainError("invalid_transition")
    if task.get("report_media") not in (None, []):
        raise DomainError("invalid_transition")
    generation = task.get("report_generation", 0)
    if type(generation) is not int or not 0 <= generation < 2**53 - 1:
        raise DomainError("invalid_field", "report_generation")
    _ensure_advance(record)
    generation += 1
    task["report_generation"] = generation
    task["report_media"] = [record["id"]]
    record.update(
        status="attached",
        scope={
            "kind": "task_report",
            "task_id": task["id"],
            "report_generation": generation,
            "assignee": target["assignee"],
            "assignee_revision": target["assignee_revision"],
        },
        expires_at=None,
    )
    _advance(ctx, record)
    return _receipt(record)


def purge_task_report(
    ctx: Context,
    task: dict,
    report_generation,
    media_id,
    media_revision,
) -> dict:
    """Detach one reviewed retained photo and begin its crash-safe deletion."""
    _modules(ctx.state)
    if ctx.actor.get("role") != "owner":
        raise DomainError("forbidden")
    if not isinstance(task, dict) or ctx.state.get("tasks", {}).get(task.get("id")) is not task:
        raise DomainError("not_found")
    generation = _version(report_generation, "report_generation")
    requested_revision = _version(media_revision, "media_revision")
    record = _record(ctx.state, media_id)
    if record["revision"] != requested_revision:
        raise DomainError("conflict")
    if record["status"] != "attached":
        raise DomainError("invalid_transition")
    scope = record.get("scope")
    if (
        not isinstance(scope, dict)
        or scope.get("kind") != "task_report"
        or scope.get("task_id") != task.get("id")
        or scope.get("report_generation") != generation
    ):
        raise DomainError("conflict")

    reports = []
    if task.get("report_generation") == generation and task.get("report_media") == [record["id"]]:
        reports.append(task)
    history = task.get("previous_reports", [])
    if not isinstance(history, list):
        raise DomainError("invalid_field", "previous_reports")
    reports.extend(
        report
        for report in history
        if isinstance(report, dict)
        and report.get("report_generation") == generation
        and report.get("report_media") == [record["id"]]
    )
    if len(reports) != 1:
        raise DomainError("conflict")
    if _version(task.get("revision")) == 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    _ensure_advance(record)

    report = reports[0]
    report.pop("report_media", None)
    report.pop("report_attachments", None)
    report["report_media_purged_at"] = timestamp(ctx.now, "now").isoformat()
    record["status"] = "deleting"
    _advance(ctx, record)
    ctx.touch(task)
    return _receipt(record)


def _attached_reference(state: dict, actor: dict, record: dict) -> bool:
    if record.get("purpose") == DOCUMENT_PURPOSE:
        from .asset_documents import attached_reference

        return attached_reference(state, actor, record)
    if record.get("purpose") == FAULT_PURPOSE:
        from .fault_photos import attached_reference

        return attached_reference(state, actor, record)
    if record.get("purpose") != PURPOSE:
        return False
    scope = record.get("scope")
    if not isinstance(scope, dict) or scope.get("kind") != "task_report":
        return False
    task = state.get("tasks", {}).get(scope.get("task_id"))
    if not isinstance(task, dict):
        return False
    assignee = state.get("members", {}).get(scope.get("assignee"))
    assignee_current = (
        isinstance(assignee, dict)
        and assignee.get("active") is True
        and assignee.get("role") != "guest"
        and assignee.get("revision") == scope.get("assignee_revision")
    )
    current_reference = (
        task.get("id") == scope.get("task_id")
        and task.get("report_generation") == scope.get("report_generation")
        and task.get("report_media") == [record["id"]]
        and task.get("assignee") == scope.get("assignee")
        and task.get("assignee_revision") == scope.get("assignee_revision")
    )
    if actor.get("role") in PRIVILEGED:
        if current_reference:
            return True
        history = task.get("previous_reports", [])
        return isinstance(history, list) and any(
            isinstance(item, dict)
            and item.get("report_generation") == scope.get("report_generation")
            and item.get("report_media") == [record["id"]]
            and item.get("assignee") == scope.get("assignee")
            and item.get("assignee_revision") == scope.get("assignee_revision")
            for item in history
        )
    if not current_reference or not assignee_current or task.get("assignee") != actor.get("id"):
        return False
    return assignee.get("revision") == task.get("assignee_revision") == actor.get(
        "revision"
    ) and task_access.may_view(state, actor, task)


def authorize_blob(state: dict, actor: dict, media_id, now) -> dict:
    """Return private metadata only after current consumer-scope authorization."""
    current = _current_member(state, actor.get("id") if isinstance(actor, dict) else None)
    if current.get("role") != actor.get("role") or current["revision"] != actor.get("revision"):
        raise DomainError("forbidden")
    record = _record(state, media_id)
    _blob_key(record)
    status = record["status"]
    if status in {"available", "attached"} and record.get("mime_type") not in mimes_for(
        record.get("purpose")
    ):
        raise DomainError("forbidden")
    if status in PENDING:
        _modules(state, record.get("purpose"))
        _reserved_authority(state, current, record)
        if timestamp(now, "now") >= timestamp(record.get("expires_at"), "expires_at"):
            raise DomainError("forbidden")
    elif status == "attached":
        _modules(state, record.get("purpose"))
        if not _attached_reference(state, current, record):
            raise DomainError("forbidden")
    else:
        raise DomainError("forbidden")
    return deepcopy(record)


def read_metadata(state: dict, actor: dict, media_id, now) -> dict:
    """Project bounded attachment metadata; never reveal blob keys or hashes."""
    record = authorize_blob(state, actor, media_id, now)
    return {key: record[key] for key in PUBLIC_FIELDS}


def expire_pending(ctx: Context, media_id, revision) -> dict:
    """Begin two-phase cleanup only for an expired unattached upload."""
    record = _record(ctx.state, media_id)
    requested_revision = _version(revision)
    if record["status"] == "deleting":
        if requested_revision == 2**53 - 1 or record["revision"] != requested_revision + 1:
            raise DomainError("conflict")
        return _receipt(record)
    if record["status"] not in PENDING:
        raise DomainError("invalid_transition")
    if record["revision"] != requested_revision:
        raise DomainError("conflict")
    _blob_key(record)
    if timestamp(ctx.now, "now") < timestamp(record.get("expires_at"), "expires_at"):
        raise DomainError("invalid_transition")
    _ensure_advance(record)
    record["status"] = "deleting"
    _advance(ctx, record)
    return _receipt(record)


def finish_delete(ctx: Context, media_id, revision) -> dict:
    """Persist a content-free tombstone after the private blob unlink succeeds."""
    record = _record(ctx.state, media_id)
    requested_revision = _version(revision)
    if record["status"] == "deleted":
        if requested_revision == 2**53 - 1 or record["revision"] != requested_revision + 1:
            raise DomainError("conflict")
        return _receipt(record)
    if record["status"] != "deleting":
        raise DomainError("invalid_transition")
    if record["revision"] != requested_revision:
        raise DomainError("conflict")
    tombstones = sum(
        isinstance(item, dict) and item.get("status") == "deleted"
        for item in _bucket(ctx.state).values()
    )
    if tombstones >= MAX_TOMBSTONES:
        raise DomainError("quota_exceeded")
    _ensure_advance(record)
    created_at = timestamp(record.get("created_at"), "created_at").isoformat()
    next_revision = record["revision"] + 1
    now = timestamp(ctx.now, "now").isoformat()
    record.clear()
    record.update(
        id=text(media_id, "id", 80),
        revision=next_revision,
        status="deleted",
        created_at=created_at,
        updated_at=now,
        deleted_at=now,
    )
    return _receipt(record)


def reap_deleted(ctx: Context) -> dict:
    """Forget at most one bounded batch of old content-free tombstones."""
    now = timestamp(ctx.now, "now")
    cutoff = now - TOMBSTONE_TTL
    media = _mutable_bucket(ctx)
    candidates = []
    for media_id, record in media.items():
        if not isinstance(record, dict) or record.get("status") != "deleted":
            continue
        deleted_at = _tombstone_time(media_id, record)
        if deleted_at <= cutoff:
            candidates.append((deleted_at, media_id))
    selected = [media_id for _deleted_at, media_id in sorted(candidates)[:MAX_REAP]]
    for media_id in selected:
        del media[media_id]
    return {"reaped": len(selected)}


def health_stats(state: dict, now) -> dict:
    """Return aggregate capacity facts without exposing media identity or content."""
    cutoff = timestamp(now, "now") - TOMBSTONE_TTL
    counts = {
        "nondeleted": 0,
        "tombstones": 0,
        "reapable_tombstones": 0,
        "pending": 0,
        "deleting": 0,
        "verified_bytes": 0,
    }
    for media_id, record in _bucket(state).items():
        if not isinstance(record, dict) or record.get("status") not in STATUSES:
            raise DomainError("invalid_field", "media")
        status = record["status"]
        if status == "deleted":
            counts["tombstones"] += 1
            if _tombstone_time(media_id, record) <= cutoff:
                counts["reapable_tombstones"] += 1
            continue
        counts["nondeleted"] += 1
        if status in PENDING:
            counts["pending"] += 1
        if status == "deleting":
            counts["deleting"] += 1
        if status == "reserved" or (status == "deleting" and record.get("size_bytes") is None):
            counts["verified_bytes"] += MAX_FILE_BYTES
        elif status in {"available", "attached", "deleting"}:
            size = record.get("size_bytes")
            if type(size) is not int or not 1 <= size <= MAX_FILE_BYTES:
                raise DomainError("invalid_field", "size_bytes")
            counts["verified_bytes"] += size
    if (
        counts["nondeleted"] >= MAX_RECORDS
        or counts["tombstones"] >= MAX_TOMBSTONES
        or counts["pending"] >= MAX_PENDING_HOUSEHOLD
        or counts["verified_bytes"] + MAX_FILE_BYTES > MAX_VERIFIED_BYTES
    ):
        capacity = "blocked"
    elif (
        counts["nondeleted"] >= MAX_RECORDS * 9 // 10
        or counts["tombstones"] >= MAX_TOMBSTONES * 9 // 10
        or counts["pending"] >= MAX_PENDING_HOUSEHOLD * 9 // 10
        or counts["verified_bytes"] >= MAX_VERIFIED_BYTES * 9 // 10
    ):
        capacity = "near_limit"
    else:
        capacity = "ok"
    return {**counts, "capacity": capacity}


def deleting_blob(state: dict, media_id, revision) -> str:
    """Return the validated private key only for the exact deleting generation."""
    record = _record(state, media_id)
    if record["revision"] != _version(revision):
        raise DomainError("conflict")
    if record["status"] != "deleting":
        raise DomainError("invalid_transition")
    return _blob_key(record)


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict | None = None) -> None:
    """Recheck a cached reservation against current actor and target authority."""
    if action != "reserve":
        raise DomainError("unknown_action")
    if not isinstance(payload, dict) or not isinstance(result, dict):
        raise DomainError("forbidden")
    reservation_fields = _reservation_fields(payload)
    fields(payload, reservation_fields, reservation_fields)
    fields(result, {"id", "revision", "status"}, {"id", "revision", "status"})
    if result.get("revision") != 1 or result.get("status") != "reserved":
        raise DomainError("forbidden")
    actor = _current_actor(ctx)
    if _version(payload["uploader_revision"], "uploader_revision") != actor["revision"]:
        raise DomainError("conflict")
    _, target = _payload_target(ctx.state, actor, payload)
    record = _record(ctx.state, result["id"])
    scope = record.get("scope")
    if (
        record.get("uploader") != actor["id"]
        or record.get("uploader_revision") != actor["revision"]
        or record.get("purpose") != payload["purpose"]
        or not isinstance(scope, dict)
        or scope.get("kind") != "uploader_private"
        or scope.get("intended_target") != target
        or record.get("status") not in PENDING
    ):
        raise DomainError("forbidden")
