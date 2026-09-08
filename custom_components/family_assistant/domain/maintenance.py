"""Household maintenance assets backed by the existing task lifecycle.

Faults create ordinary tasks and recurring services are ordinary task-series
records.  This module has no scheduler, media transport, stock mutation, OCR,
or device effects of its own.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import PRIVILEGED
from . import recurrence, task_series, tasks
from .context import Context
from .validation import DomainError, fields, number, text, timestamp
from .validation import revision as strict_revision

MAX_REVISION = 2**53 - 1
MAX_ASSETS = 500
MAX_FAULTS = 5000
MAX_SERVICE_LOGS = 5000
MAX_ACTIVE_FAULTS_PER_REPORTER = 20
FINAL_TASK_STATUSES = frozenset({"completed", "cancelled", "archived"})

ASSET_FIELDS = frozenset(
    {
        "id",
        "revision",
        "name",
        "category",
        "location",
        "responsible_member",
        "responsible_member_revision",
        "warranty",
        "consumables",
        "note",
        "reportable",
    }
)
ASSET_REQUIRED = ASSET_FIELDS - {"id", "revision", "reportable"}
SERVICE_FIELDS = frozenset(
    {
        "id",
        "revision",
        "asset_id",
        "asset_revision",
        "title",
        "report_type",
        "assignees",
        "rotation",
        "rule",
        "due_time",
        "checklist",
        "enabled",
        "reminder_minutes",
        "grace_minutes",
    }
)
SERVICE_REQUIRED = SERVICE_FIELDS - {"id", "revision", "report_type"}
SOURCE_FIELDS = frozenset(
    {
        "kind",
        "asset_id",
        "asset_revision",
        "approved_by",
        "approved_by_revision",
        "member_revisions",
    }
)


def _module_enabled(state: dict, module: str) -> bool:
    modules = state.get("settings", {}).get("modules", [])
    return isinstance(modules, list) and module in modules


def _require_module(state: dict, *, tasks_required=False) -> None:
    if not _module_enabled(state, "maintenance"):
        raise DomainError("module_disabled")
    if tasks_required and not _module_enabled(state, "tasks"):
        raise DomainError("module_disabled")


def _current_actor(ctx: Context, *, parent=False) -> dict:
    actor = ctx.state.get("members", {}).get(ctx.actor_id)
    if not isinstance(actor, dict) or not actor.get("active", False):
        raise DomainError("forbidden")
    role = actor.get("role")
    if role == "guest" or parent and role not in PRIVILEGED:
        raise DomainError("forbidden")
    return actor


def _version(value, field="revision") -> int:
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _optional_text(value, field: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise DomainError("invalid_field", field)
    return value.strip()


def _local_date(value, field: str) -> date:
    try:
        return recurrence.local_date(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _quantity(value, field: str) -> float:
    result = number(value, field, 0, 1000000)
    rounded = round(result, 3)
    if result <= 0 or result != rounded:
        raise DomainError("invalid_field", field)
    return rounded


def _bucket(state: dict, name: str) -> dict:
    maintenance = state.get("maintenance", {})
    if not isinstance(maintenance, dict):
        raise DomainError("invalid_field", "maintenance")
    value = maintenance.get(name, {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _mutable_bucket(ctx: Context, name: str) -> dict:
    maintenance = ctx.state.get("maintenance")
    if maintenance is None:
        maintenance = {}
        ctx.state["maintenance"] = maintenance
    if not isinstance(maintenance, dict):
        raise DomainError("invalid_field", "maintenance")
    value = maintenance.get(name)
    if value is None:
        value = {}
        maintenance[name] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _record(
    bucket: dict,
    record_id,
    record_revision,
    field="id",
    *,
    for_update: bool = False,
) -> dict:
    record_id = text(record_id, field, 80)
    record = bucket.get(record_id)
    if record is None:
        raise DomainError("not_found")
    if not isinstance(record, dict) or record.get("id") != record_id:
        raise DomainError("invalid_field", field)
    current = _version(record.get("revision"))
    if _version(record_revision) != current:
        raise DomainError("conflict")
    if for_update and current == MAX_REVISION:
        raise DomainError("invalid_field", "revision")
    return record


def _member(state: dict, member_id, member_revision, field="responsible_member") -> dict:
    member_id = text(member_id, field, 80)
    member = state.get("members", {}).get(member_id)
    if (
        not isinstance(member, dict)
        or not member.get("active", False)
        or member.get("role") == "guest"
    ):
        raise DomainError("unknown_member")
    expected = _version(member_revision, f"{field}_revision")
    current = _version(member.get("revision"), f"{field}_revision")
    if expected != current:
        raise DomainError("conflict")
    return member


def _warranty(value) -> dict:
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "warranty")
    fields(value, {"expires_on", "vendor", "reference"}, {"expires_on", "vendor", "reference"})
    expires_on = value["expires_on"]
    return {
        "expires_on": None
        if expires_on is None
        else _local_date(expires_on, "warranty.expires_on").isoformat(),
        "vendor": _optional_text(value["vendor"], "warranty.vendor", 120),
        "reference": _optional_text(value["reference"], "warranty.reference", 200),
    }


def _pantry_link(state: dict, value, unit: str, field: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DomainError("invalid_field", field)
    fields(value, {"id", "revision"}, {"id", "revision"})
    if not _module_enabled(state, "pantry"):
        raise DomainError("module_disabled")
    pantry = state.get("pantry", {})
    items = pantry.get("items", {}) if isinstance(pantry, dict) else {}
    if not isinstance(items, dict):
        raise DomainError("invalid_field", field)
    item = _record(items, value["id"], value["revision"], field)
    if item.get("status") != "active" or item.get("unit") != unit:
        raise DomainError("invalid_field", field)
    return {"id": item["id"], "revision": item["revision"]}


def _consumables(state: dict, value, field="consumables") -> list[dict]:
    if not isinstance(value, list) or len(value) > 30:
        raise DomainError("invalid_field", field)
    result = []
    seen = set()
    for index, item in enumerate(value):
        prefix = f"{field}[{index}]"
        if not isinstance(item, dict):
            raise DomainError("invalid_field", prefix)
        fields(
            item, {"label", "unit", "quantity", "pantry"}, {"label", "unit", "quantity", "pantry"}
        )
        label = text(item["label"], f"{prefix}.label", 120)
        unit = text(item["unit"], f"{prefix}.unit", 24)
        identity = (label.casefold(), unit)
        if identity in seen:
            raise DomainError("invalid_field", field)
        seen.add(identity)
        result.append(
            {
                "label": label,
                "unit": unit,
                "quantity": _quantity(item["quantity"], f"{prefix}.quantity"),
                "pantry": _pantry_link(state, item["pantry"], unit, f"{prefix}.pantry"),
            }
        )
    return result


def _empty_attachments(value) -> list:
    if not isinstance(value, list) or value:
        raise DomainError("invalid_field", "attachment_ids")
    return []


def _history(ctx: Context, record: dict, action: str, reason="") -> dict:
    history = record.setdefault("history", [])
    if not isinstance(history, list):
        raise DomainError("invalid_field", "history")
    event = {"actor": ctx.actor_id, "at": ctx.now.isoformat(), "action": action}
    if reason:
        event["reason"] = reason
    history.append(event)
    return ctx.touch(record)


def _receipt(record: dict) -> dict:
    return {"id": record["id"], "revision": record["revision"], "status": record["status"]}


def _asset_values(ctx: Context, payload: dict, actor: dict) -> dict:
    responsible = _member(
        ctx.state,
        payload["responsible_member"],
        payload["responsible_member_revision"],
    )
    return {
        "name": text(payload["name"], "name", 120),
        "category": _optional_text(payload["category"], "category", 80),
        "location": _optional_text(payload["location"], "location", 120),
        "responsible_member": responsible["id"],
        "responsible_member_revision": _version(
            payload["responsible_member_revision"], "responsible_member_revision"
        ),
        "warranty": _warranty(payload["warranty"]),
        "consumables": _consumables(ctx.state, payload["consumables"]),
        "note": _optional_text(payload["note"], "note", 1000),
        "reportable": payload["reportable"],
        "approved_by": actor["id"],
        "approved_by_revision": _version(actor.get("revision"), "approved_by_revision"),
    }


def _asset_save(ctx: Context, payload: dict) -> dict:
    actor = _current_actor(ctx, parent=True)
    is_edit = "id" in payload
    fields(
        payload,
        ASSET_FIELDS,
        ASSET_REQUIRED | ({"id", "revision"} if is_edit else set()),
    )
    if not is_edit and "revision" in payload:
        raise DomainError("invalid_field", "revision")
    assets = _bucket(ctx.state, "assets")
    existing = (
        _record(assets, payload["id"], payload["revision"], for_update=True) if is_edit else None
    )
    if existing is not None and existing.get("status") != "active":
        raise DomainError("invalid_transition")
    reportable = payload.get(
        "reportable", existing.get("reportable", False) if existing is not None else False
    )
    if type(reportable) is not bool:
        raise DomainError("invalid_field", "reportable")
    values = _asset_values(ctx, {**payload, "reportable": reportable}, actor)
    if existing is None:
        if len(assets) >= MAX_ASSETS:
            raise DomainError("invalid_transition")
        record = {
            "id": ctx.identifier("MX"),
            **values,
            "status": "active",
            "created_by": actor["id"],
            "created_at": ctx.now.isoformat(),
            "history": [],
        }
        _mutable_bucket(ctx, "assets")[record["id"]] = record
        _history(ctx, record, "created")
        return _receipt(record)
    record = deepcopy(existing)
    if all(record.get(key) == value for key, value in values.items()):
        raise DomainError("invalid_transition")
    record.update(values)
    _history(ctx, record, "updated")
    assets[record["id"]] = record
    return _receipt(record)


def _asset_retire(ctx: Context, payload: dict) -> dict:
    _current_actor(ctx, parent=True)
    fields(payload, {"id", "revision", "reason"}, {"id", "revision", "reason"})
    assets = _bucket(ctx.state, "assets")
    record = deepcopy(_record(assets, payload["id"], payload["revision"], for_update=True))
    if record.get("status") != "active":
        raise DomainError("invalid_transition")
    reason = text(payload["reason"], "reason", 500)
    record["status"] = "retired"
    record["retired_at"] = ctx.now.isoformat()
    _history(ctx, record, "retired", reason)
    assets[record["id"]] = record
    return _receipt(record)


def _asset_usable(state: dict, asset: dict) -> tuple[dict, dict] | None:
    if not isinstance(asset, dict) or asset.get("status") != "active":
        return None
    approver = state.get("members", {}).get(asset.get("approved_by"))
    responsible = state.get("members", {}).get(asset.get("responsible_member"))
    try:
        valid = (
            isinstance(approver, dict)
            and approver.get("active", False)
            and approver.get("role") in PRIVILEGED
            and _version(approver.get("revision"), "approved_by_revision")
            == _version(asset.get("approved_by_revision"), "approved_by_revision")
            and isinstance(responsible, dict)
            and responsible.get("active", False)
            and responsible.get("role") != "guest"
            and _version(responsible.get("revision"), "responsible_member_revision")
            == _version(asset.get("responsible_member_revision"), "responsible_member_revision")
        )
    except DomainError:
        return None
    return (approver, responsible) if valid else None


def _summary_identity(value: str) -> str:
    return " ".join(value.split()).casefold()


def _fault_active(state: dict, fault: dict) -> bool:
    task = state.get("tasks", {}).get(fault.get("task_id"))
    return isinstance(task, dict) and task.get("status") not in FINAL_TASK_STATUSES


def _fault_report(ctx: Context, payload: dict) -> dict:
    reporter = _current_actor(ctx)
    _require_module(ctx.state, tasks_required=True)
    fields(
        payload,
        {
            "asset_id",
            "asset_revision",
            "reporter_member_revision",
            "summary",
            "details",
            "attachment_ids",
        },
        {
            "asset_id",
            "asset_revision",
            "reporter_member_revision",
            "summary",
            "details",
            "attachment_ids",
        },
    )
    reporter_revision = _version(payload["reporter_member_revision"], "reporter_member_revision")
    if _version(reporter.get("revision"), "reporter_member_revision") != reporter_revision:
        raise DomainError("conflict")
    assets = _bucket(ctx.state, "assets")
    asset = _record(assets, payload["asset_id"], payload["asset_revision"], "asset_id")
    usable = _asset_usable(ctx.state, asset)
    if usable is None:
        raise DomainError("conflict")
    approver, responsible = usable
    if (
        reporter.get("role") not in PRIVILEGED
        and reporter["id"] != responsible["id"]
        and asset.get("reportable") is not True
    ):
        raise DomainError("forbidden")
    summary = text(payload["summary"], "summary", 200)
    details = _optional_text(payload["details"], "details", 2000)
    attachments = _empty_attachments(payload["attachment_ids"])
    identity = _summary_identity(summary)
    faults = _bucket(ctx.state, "faults")
    active_for_reporter = 0
    for fault in faults.values():
        if not isinstance(fault, dict) or not _fault_active(ctx.state, fault):
            continue
        if fault.get("reporter") == reporter["id"]:
            active_for_reporter += 1
            if fault.get("asset_id") == asset["id"] and fault.get("normalized_summary") == identity:
                raise DomainError("invalid_transition")
    if len(faults) >= MAX_FAULTS or active_for_reporter >= MAX_ACTIVE_FAULTS_PER_REPORTER:
        raise DomainError("invalid_transition")

    fault_id = ctx.identifier("MF")
    delegated = Context(
        ctx.state,
        approver,
        ctx.now,
        f"{ctx.operation_id}:maintenance-task",
    )
    task = tasks.handle(
        delegated,
        "create",
        {
            "title": summary,
            "assignee": responsible["id"],
            "report_type": "text",
            "penalty": 0,
        },
    )
    task.update(
        delivery_scope="private",
        source={
            "kind": "maintenance_fault",
            "asset_id": asset["id"],
            "asset_revision": asset["revision"],
            "fault_id": fault_id,
        },
    )
    record = {
        "id": fault_id,
        "revision": 1,
        "status": "reported",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "reporter": reporter["id"],
        "reporter_member_revision": reporter_revision,
        "summary": summary,
        "normalized_summary": identity,
        "details": details,
        "task_id": task["id"],
        "attachment_ids": attachments,
        "created_at": ctx.now.isoformat(),
    }
    _mutable_bucket(ctx, "faults")[fault_id] = record
    return {**_receipt(record), "task_id": task["id"]}


def _assignees(state: dict, value) -> tuple[list[str], dict[str, int]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 20:
        raise DomainError("invalid_field", "assignees")
    ids = []
    revisions = {}
    for item in value:
        if not isinstance(item, dict):
            raise DomainError("invalid_field", "assignees")
        fields(item, {"id", "revision"}, {"id", "revision"})
        member = _member(state, item["id"], item["revision"], "assignee")
        if member["id"] in revisions:
            raise DomainError("invalid_field", "assignees")
        ids.append(member["id"])
        revisions[member["id"]] = _version(item["revision"], "assignee_revision")
    return ids, revisions


def is_managed_series(series: dict) -> bool:
    """Identify a maintenance-owned task series for the generic-route gate."""
    if not isinstance(series, dict):
        return False
    source = series.get("source")
    return isinstance(source, dict) and source.get("kind") == "maintenance"


def _source(asset: dict, actor: dict, member_revisions: dict[str, int]) -> dict:
    return {
        "kind": "maintenance",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "approved_by": actor["id"],
        "approved_by_revision": _version(actor.get("revision"), "approved_by_revision"),
        "member_revisions": dict(member_revisions),
    }


def _managed_record(state: dict, record_id, record_revision) -> dict:
    record = _record(state.get("task_series", {}), record_id, record_revision, for_update=True)
    if not is_managed_series(record):
        raise DomainError("not_found")
    return record


def _service_save(ctx: Context, payload: dict) -> dict:
    actor = _current_actor(ctx, parent=True)
    _require_module(ctx.state, tasks_required=True)
    is_edit = "id" in payload
    fields(
        payload,
        SERVICE_FIELDS,
        SERVICE_REQUIRED | ({"id", "revision"} if is_edit else set()),
    )
    if not is_edit and "revision" in payload:
        raise DomainError("invalid_field", "revision")
    assets = _bucket(ctx.state, "assets")
    asset = _record(assets, payload["asset_id"], payload["asset_revision"], "asset_id")
    if asset.get("status") != "active" or _asset_usable(ctx.state, asset) is None:
        raise DomainError("conflict")
    existing = _managed_record(ctx.state, payload["id"], payload["revision"]) if is_edit else None
    if existing is not None and existing["source"].get("asset_id") != asset["id"]:
        raise DomainError("invalid_field", "asset_id")
    ids, revisions = _assignees(ctx.state, payload["assignees"])
    report_type = payload.get(
        "report_type", existing.get("report_type", "text") if existing is not None else "text"
    )
    if not isinstance(report_type, str) or report_type not in {"text", "photo"}:
        raise DomainError("invalid_field", "report_type")
    series_payload = {
        **({"id": payload["id"], "revision": payload["revision"]} if is_edit else {}),
        "title": payload["title"],
        "assignees": ids,
        "rotation": payload["rotation"],
        "rule": deepcopy(payload["rule"]),
        "due_time": payload["due_time"],
        "report_type": report_type,
        "checklist": deepcopy(payload["checklist"]),
        "enabled": payload["enabled"],
        "reminder_minutes": payload["reminder_minutes"],
        "grace_minutes": payload["grace_minutes"],
        "penalty": 0,
    }
    series = task_series.handle(ctx, "series_save", series_payload, _maintenance=True)
    series["creator"] = actor["id"]
    series["source"] = _source(asset, actor, revisions)
    return {"id": series["id"], "revision": series["revision"], "enabled": series["enabled"]}


def _service_enable(ctx: Context, payload: dict) -> dict:
    _current_actor(ctx, parent=True)
    _require_module(ctx.state, tasks_required=True)
    fields(
        payload,
        {"id", "revision", "enabled", "asset_revision"},
        {"id", "revision", "enabled", "asset_revision"},
    )
    if type(payload["enabled"]) is not bool:
        raise DomainError("invalid_field", "enabled")
    series = _managed_record(ctx.state, payload["id"], payload["revision"])
    asset_revision = _version(payload["asset_revision"], "asset_revision")
    if series.get("enabled") is payload["enabled"]:
        raise DomainError("invalid_transition")
    if payload["enabled"]:
        asset = _record(
            _bucket(ctx.state, "assets"),
            series["source"].get("asset_id"),
            asset_revision,
            "asset_id",
        )
        if asset.get("status") != "active" or not series_current(ctx.state, series):
            raise DomainError("conflict")
    elif asset_revision != _version(series["source"].get("asset_revision"), "asset_revision"):
        raise DomainError("conflict")
    updated = task_series.handle(
        ctx,
        "series_enable",
        {"id": series["id"], "revision": series["revision"], "enabled": payload["enabled"]},
        _maintenance=True,
    )
    return {"id": updated["id"], "revision": updated["revision"], "enabled": updated["enabled"]}


def series_current(state: dict, series: dict) -> bool:
    """Fail-closed source guard for maintenance-linked task-series generation."""
    if not _module_enabled(state, "maintenance") or not _module_enabled(state, "tasks"):
        return False
    if not is_managed_series(series):
        return False
    try:
        source = series.get("source")
        if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
            return False
        asset = _bucket(state, "assets").get(source.get("asset_id"))
        if not isinstance(asset, dict) or asset.get("status") != "active":
            return False
        approver = state.get("members", {}).get(source.get("approved_by"))
        assignees = series.get("assignees")
        revisions = source.get("member_revisions")
        policy = series.get("deadline_policy")
        if (
            _version(asset.get("revision")) != _version(source.get("asset_revision"))
            or _asset_usable(state, asset) is None
            or not isinstance(approver, dict)
            or not approver.get("active", False)
            or approver.get("role") not in PRIVILEGED
            or series.get("creator") != approver.get("id")
            or _version(approver.get("revision"), "approved_by_revision")
            != _version(source.get("approved_by_revision"), "approved_by_revision")
            or not isinstance(assignees, list)
            or not 1 <= len(assignees) <= 20
            or len(set(assignees)) != len(assignees)
            or not isinstance(revisions, dict)
            or set(revisions) != set(assignees)
            or series.get("report_type") not in {"text", "photo"}
            or not isinstance(policy, dict)
            or type(policy.get("penalty")) is not int
            or policy.get("penalty") != 0
        ):
            return False
        for member_id in assignees:
            member = state.get("members", {}).get(member_id)
            if (
                not isinstance(member, dict)
                or not member.get("active", False)
                or member.get("role") == "guest"
                or _version(member.get("revision"), "assignee_revision")
                != _version(revisions.get(member_id), "assignee_revision")
            ):
                return False
    except (DomainError, TypeError):
        return False
    return True


def _related_task(state: dict, asset_id: str, value) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "task")
    fields(value, {"id", "revision"}, {"id", "revision"})
    task = _record(state.get("tasks", {}), value["id"], value["revision"], "task")
    if task.get("status") != "completed":
        raise DomainError("invalid_transition")
    source = task.get("source")
    related = (
        isinstance(source, dict)
        and source.get("kind") in {"maintenance_fault", "maintenance_service"}
        and source.get("asset_id") == asset_id
    )
    if not related:
        raise DomainError("invalid_field", "task")
    return task


def _today(state: dict, now) -> date:
    moment = timestamp(now, "now")
    timezone = state.get("settings", {}).get("timezone", "UTC")
    try:
        return moment.astimezone(ZoneInfo(timezone)).date()
    except (ZoneInfoNotFoundError, ValueError, TypeError, OverflowError, OSError):
        raise DomainError("invalid_field", "now") from None


def _service_log(ctx: Context, payload: dict) -> dict:
    _current_actor(ctx, parent=True)
    fields(
        payload,
        {
            "asset_id",
            "asset_revision",
            "performed_on",
            "summary",
            "task",
            "consumables_used",
            "attachment_ids",
        },
        {
            "asset_id",
            "asset_revision",
            "performed_on",
            "summary",
            "task",
            "consumables_used",
            "attachment_ids",
        },
    )
    asset = _record(
        _bucket(ctx.state, "assets"),
        payload["asset_id"],
        payload["asset_revision"],
        "asset_id",
    )
    performed_on = _local_date(payload["performed_on"], "performed_on")
    if performed_on > _today(ctx.state, ctx.now):
        raise DomainError("invalid_field", "performed_on")
    summary = text(payload["summary"], "summary", 2000)
    related_task = _related_task(ctx.state, asset["id"], payload["task"])
    logs = _bucket(ctx.state, "service_logs")
    if related_task is not None and any(
        isinstance(item, dict) and item.get("task_id") == related_task["id"]
        for item in logs.values()
    ):
        raise DomainError("invalid_transition")
    if len(logs) >= MAX_SERVICE_LOGS:
        raise DomainError("invalid_transition")
    consumables_used = _consumables(ctx.state, payload["consumables_used"], "consumables_used")
    attachment_ids = _empty_attachments(payload["attachment_ids"])
    record = {
        "id": ctx.identifier("MH"),
        "revision": 1,
        "status": "recorded",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "performed_on": performed_on.isoformat(),
        "summary": summary,
        "task_id": related_task["id"] if related_task is not None else None,
        "task_revision": related_task["revision"] if related_task is not None else None,
        "consumables_used": consumables_used,
        "attachment_ids": attachment_ids,
        "actor": ctx.actor_id,
        "created_at": ctx.now.isoformat(),
    }
    _mutable_bucket(ctx, "service_logs")[record["id"]] = record
    return _receipt(record)


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Apply a bounded maintenance mutation without media or device effects."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    _require_module(ctx.state)
    if action in {"fault_photo_attach", "fault_photo_purge"}:
        from . import fault_photos

        return fault_photos.handle(ctx, action, payload)
    if action == "asset_save":
        return _asset_save(ctx, payload)
    if action == "asset_retire":
        return _asset_retire(ctx, payload)
    if action == "fault_report":
        return _fault_report(ctx, payload)
    if action == "service_save":
        return _service_save(ctx, payload)
    if action == "service_enable":
        return _service_enable(ctx, payload)
    if action == "service_log":
        return _service_log(ctx, payload)
    raise DomainError("unknown_action")


def _public_fault(state: dict, fault: dict, *, parent: bool, actor: dict) -> dict:
    from .fault_photos import public_attachment, upload_target

    task = state.get("tasks", {}).get(fault.get("task_id"), {})
    result = deepcopy(fault)
    result["task_status"] = task.get("status") if isinstance(task, dict) else "unavailable"
    result["task_revision"] = task.get("revision") if isinstance(task, dict) else None
    result["assignee"] = task.get("assignee") if isinstance(task, dict) else None
    result.pop("normalized_summary", None)
    try:
        upload_target(state, actor, fault.get("id"), fault.get("revision"))
        result["can_upload_photo"] = True
    except DomainError:
        result["can_upload_photo"] = False
    if fault.get("attachment_ids"):
        result["photo_attachment"] = public_attachment(state, actor, fault)
    if not parent:
        for key in ("asset_revision", "reporter_member_revision", "photo_purge", "photo_history"):
            result.pop(key, None)
    return result


def _public_service(series: dict, current: bool) -> dict:
    source = series["source"]
    return {
        "id": series.get("id"),
        "revision": series.get("revision"),
        "asset_id": source.get("asset_id"),
        "asset_revision": source.get("asset_revision"),
        "title": deepcopy(series.get("title")),
        "report_type": series.get("report_type"),
        "assignees": deepcopy(series.get("assignees")),
        "rotation": series.get("rotation"),
        "rule": deepcopy(series.get("rule")),
        "due_time": series.get("due_time"),
        "checklist": deepcopy(series.get("checklist")),
        "enabled": series.get("enabled"),
        "deadline_policy": deepcopy(series.get("deadline_policy")),
        "effective_at": series.get("effective_at"),
        "current": current,
    }


def _task_assigned_to(task: dict, member: dict) -> bool:
    if not isinstance(task, dict) or task.get("assignee") != member.get("id"):
        return False
    try:
        return _version(task.get("assignee_revision"), "assignee_revision") == _version(
            member.get("revision"), "assignee_revision"
        )
    except DomainError:
        return False


def view(state: dict, actor: dict) -> dict:
    """Return a pure role projection; warranty and service history stay parent-only."""
    empty = {"assets": [], "faults": [], "service_logs": [], "services": []}
    if not _module_enabled(state, "maintenance") or not isinstance(actor, dict):
        return empty
    current = state.get("members", {}).get(actor.get("id"))
    if (
        not isinstance(current, dict)
        or not current.get("active", False)
        or current.get("role") == "guest"
    ):
        return empty
    parent = current.get("role") in PRIVILEGED
    assets = _bucket(state, "assets")
    faults = _bucket(state, "faults")
    logs = _bucket(state, "service_logs")
    if parent:
        services = [
            _public_service(series, series_current(state, series))
            for series in state.get("task_series", {}).values()
            if is_managed_series(series)
        ]
        public_assets = []
        for item in assets.values():
            public = deepcopy(item)
            current_asset = _asset_usable(state, item) is not None
            public["current"] = current_asset
            public["can_report"] = current_asset
            public_assets.append(public)
        return {
            "assets": public_assets,
            "faults": [
                _public_fault(state, item, parent=True, actor=current) for item in faults.values()
            ],
            "service_logs": [deepcopy(item) for item in logs.values()],
            "services": services,
        }
    actor_revision = current.get("revision")
    related_asset_ids = set()
    for fault in faults.values():
        if not isinstance(fault, dict):
            continue
        task = state.get("tasks", {}).get(fault.get("task_id"), {})
        if (
            fault.get("reporter") == current["id"]
            and fault.get("reporter_member_revision") == actor_revision
        ) or _task_assigned_to(task, current):
            related_asset_ids.add(fault.get("asset_id"))
    public_assets = []
    for item in assets.values():
        if not isinstance(item, dict) or item.get("status") != "active":
            continue
        responsible = False
        if item.get("responsible_member") == current["id"]:
            try:
                responsible = _version(
                    item.get("responsible_member_revision"), "responsible_member_revision"
                ) == _version(current.get("revision"), "responsible_member_revision")
            except DomainError:
                responsible = False
        related = (
            item.get("reportable") is True or responsible or item.get("id") in related_asset_ids
        )
        if not related:
            continue
        public_assets.append(
            {
                "id": item.get("id"),
                "revision": item.get("revision"),
                "name": deepcopy(item.get("name")),
                "category": deepcopy(item.get("category")),
                "location": deepcopy(item.get("location")),
                "can_report": _asset_usable(state, item) is not None
                and (item.get("reportable") is True or responsible),
            }
        )
    public_faults = []
    for item in faults.values():
        if not isinstance(item, dict):
            continue
        task = state.get("tasks", {}).get(item.get("task_id"), {})
        own_current = (
            item.get("reporter") == current["id"]
            and item.get("reporter_member_revision") == actor_revision
        )
        if own_current or _task_assigned_to(task, current):
            public_faults.append(_public_fault(state, item, parent=False, actor=current))
    return {**empty, "assets": public_assets, "faults": public_faults}


def authorize_replay(ctx: Context, action: str, payload: dict) -> None:
    """Recheck the current actor and dependent module before returning an opaque receipt."""
    if action in {"fault_photo_attach", "fault_photo_purge"}:
        from . import fault_photos

        fault_photos.authorize_replay(ctx, action, payload)
        return
    _require_module(
        ctx.state, tasks_required=action in {"fault_report", "service_save", "service_enable"}
    )
    actor = _current_actor(ctx, parent=action != "fault_report")
    if action == "fault_report":
        if not isinstance(payload, dict):
            raise DomainError("invalid_field", "payload")
        expected = _version(payload.get("reporter_member_revision"), "reporter_member_revision")
        if _version(actor.get("revision"), "reporter_member_revision") != expected:
            raise DomainError("conflict")
