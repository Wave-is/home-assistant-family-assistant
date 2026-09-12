"""Parent-reviewed school timetables with child-private projections.

Manual weekly lessons and pinned backpack references remain passive records.
Explicit homework and preparation commands delegate to existing private tasks
and routines; there is no independent school scheduler or device action.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import PRIVILEGED
from . import recurrence
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

MAX_REVISION = 2**53 - 1
MAX_LESSONS = 70
MAX_MATERIALS_PER_LESSON = 12
MAX_MATERIALS_TOTAL = 200
SAVE_FIELDS = frozenset(
    {
        "id",
        "revision",
        "member",
        "member_revision",
        "title",
        "valid_from",
        "valid_until",
        "lessons",
        "backpack_routine",
        "exceptions",
    }
)
SAVE_REQUIRED = frozenset(
    {
        "member",
        "member_revision",
        "title",
        "valid_from",
        "valid_until",
        "lessons",
        "backpack_routine",
    }
)
LESSON_FIELDS = frozenset({"weekday", "start", "end", "subject", "room", "materials"})


def _module_enabled(state: dict) -> bool:
    modules = state.get("settings", {}).get("modules", [])
    return isinstance(modules, list) and "school" in modules


def _require_parent(ctx: Context) -> dict:
    if not _module_enabled(ctx.state):
        raise DomainError("module_disabled")
    actor = ctx.state.get("members", {}).get(ctx.actor_id, {})
    if (
        not isinstance(actor, dict)
        or not actor.get("active", False)
        or actor.get("role") not in PRIVILEGED
    ):
        raise DomainError("forbidden")
    return actor


def _bucket(state: dict) -> dict:
    school = state.get("school", {})
    if not isinstance(school, dict):
        raise DomainError("invalid_field", "school")
    timetables = school.get("timetables", {})
    if not isinstance(timetables, dict):
        raise DomainError("invalid_field", "timetables")
    return timetables


def _mutable_bucket(ctx: Context) -> dict:
    school = ctx.state.get("school")
    if school is None:
        school = {}
        ctx.state["school"] = school
    if not isinstance(school, dict):
        raise DomainError("invalid_field", "school")
    timetables = school.get("timetables")
    if timetables is None:
        timetables = {}
        school["timetables"] = timetables
    if not isinstance(timetables, dict):
        raise DomainError("invalid_field", "timetables")
    return timetables


def _version(value, field: str = "revision") -> int:
    try:
        result = strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None
    return result


def _record(timetables: dict, record_id, record_revision) -> dict:
    record_id = text(record_id, "id", 80)
    record = timetables.get(record_id)
    if record is None:
        raise DomainError("not_found")
    if not isinstance(record, dict) or record.get("id") != record_id:
        raise DomainError("invalid_field", "timetables")
    current_revision = _version(record.get("revision"))
    if _version(record_revision) != current_revision:
        raise DomainError("conflict")
    if current_revision == MAX_REVISION:
        raise DomainError("invalid_field", "revision")
    return record


def _local_date(value, field: str) -> date:
    try:
        return recurrence.local_date(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _clock(value, field: str) -> str:
    try:
        return recurrence.clock(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _optional_text(value, field: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise DomainError("invalid_field", field)
    return value.strip()


def _lessons(value) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_LESSONS:
        raise DomainError("invalid_field", "lessons")
    result = []
    material_count = 0
    for index, lesson in enumerate(value):
        prefix = f"lessons[{index}]"
        if not isinstance(lesson, dict):
            raise DomainError("invalid_field", prefix)
        fields(lesson, LESSON_FIELDS, LESSON_FIELDS)
        weekday = lesson["weekday"]
        if type(weekday) is not int or not 0 <= weekday <= 6:
            raise DomainError("invalid_field", f"{prefix}.weekday")
        start = _clock(lesson["start"], f"{prefix}.start")
        end = _clock(lesson["end"], f"{prefix}.end")
        if start >= end:
            raise DomainError("invalid_field", f"{prefix}.end")
        materials = lesson["materials"]
        if not isinstance(materials, list) or len(materials) > MAX_MATERIALS_PER_LESSON:
            raise DomainError("invalid_field", f"{prefix}.materials")
        normalized_materials = []
        seen_materials = set()
        for material in materials:
            normalized = text(material, f"{prefix}.materials", 120)
            identity = normalized.casefold()
            if identity in seen_materials:
                raise DomainError("invalid_field", f"{prefix}.materials")
            seen_materials.add(identity)
            normalized_materials.append(normalized)
        material_count += len(normalized_materials)
        if material_count > MAX_MATERIALS_TOTAL:
            raise DomainError("invalid_field", "materials")
        result.append(
            {
                "weekday": weekday,
                "start": start,
                "end": end,
                "subject": text(lesson["subject"], f"{prefix}.subject", 120),
                "room": _optional_text(lesson["room"], f"{prefix}.room", 80),
                "materials": normalized_materials,
            }
        )
    result.sort(key=lambda row: (row["weekday"], row["start"], row["end"], row["subject"]))
    previous_by_day: dict[int, dict] = {}
    for lesson in result:
        previous = previous_by_day.get(lesson["weekday"])
        if previous is not None and lesson["start"] < previous["end"]:
            raise DomainError("invalid_field", "lessons")
        previous_by_day[lesson["weekday"]] = lesson
    return result


def _exceptions(value, valid_from: date, valid_until: date | None) -> list[str]:
    if not isinstance(value, list) or len(value) > 366:
        raise DomainError("invalid_field", "exceptions")
    result = []
    seen = set()
    for item in value:
        exception = _local_date(item, "exceptions")
        canonical = exception.isoformat()
        if (
            canonical in seen
            or exception < valid_from
            or (valid_until is not None and exception > valid_until)
        ):
            raise DomainError("invalid_field", "exceptions")
        seen.add(canonical)
        result.append(canonical)
    return sorted(result)


def _current_child(state: dict, member_id, member_revision) -> dict:
    member_id = text(member_id, "member", 80)
    member = state.get("members", {}).get(member_id)
    if (
        not isinstance(member, dict)
        or not member.get("active", False)
        or member.get("role") != "child"
    ):
        raise DomainError("unknown_member")
    expected = _version(member_revision, "member_revision")
    current = _version(member.get("revision"), "member_revision")
    if expected != current:
        raise DomainError("conflict")
    return member


def _routine_usable(
    state: dict, template: dict, member_id: str, revision: int, record_id: str
) -> bool:
    modules = state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "routines" not in modules or not isinstance(template, dict):
        return False
    try:
        if _version(template.get("revision")) != revision:
            return False
    except DomainError:
        return False
    creator = state.get("members", {}).get(template.get("creator"), {})
    assignees = template.get("assignees")
    steps = template.get("steps")
    if template.get("id") != record_id:
        return False
    if (
        template.get("enabled") is not True
        or not isinstance(creator, dict)
        or not creator.get("active", False)
        or creator.get("role") not in PRIVILEGED
        or not isinstance(assignees, list)
        or member_id not in assignees
        or not isinstance(steps, list)
        or not steps
    ):
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        assignee = step.get("assignee")
        if assignee is None:
            continue
        if not isinstance(assignee, str):
            return False
        current = state.get("members", {}).get(assignee, {})
        if (
            not isinstance(current, dict)
            or not current.get("active", False)
            or current.get("role") == "guest"
        ):
            return False
    return True


def _routine_link(ctx: Context, value, member_id: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "backpack_routine")
    fields(value, {"id", "revision"}, {"id", "revision"})
    record_id = text(value["id"], "backpack_routine", 80)
    record_revision = _version(value["revision"])
    template = ctx.state.get("routines", {}).get(record_id)
    if template is None:
        raise DomainError("not_found")
    if not _routine_usable(ctx.state, template, member_id, record_revision, record_id):
        current_revision = template.get("revision") if isinstance(template, dict) else None
        if type(current_revision) is int and current_revision != record_revision:
            raise DomainError("conflict")
        raise DomainError("invalid_field", "backpack_routine")
    return {"id": record_id, "revision": record_revision}


def _current_routine(state: dict, link, member_id: str) -> dict | None:
    if not isinstance(link, dict) or set(link) != {"id", "revision"}:
        return None
    record_id = link.get("id")
    revision = link.get("revision")
    if not isinstance(record_id, str) or type(revision) is not int:
        return None
    template = state.get("routines", {}).get(record_id)
    if not _routine_usable(state, template, member_id, revision, record_id):
        return None
    title_value = template.get("title")
    if not isinstance(title_value, str) or not title_value.strip() or len(title_value) > 255:
        return None
    return {"id": record_id, "revision": revision, "title": title_value.strip()}


def _history(ctx: Context, record: dict, action: str, *, reason="") -> dict:
    history = record.setdefault("history", [])
    if not isinstance(history, list):
        raise DomainError("invalid_field", "history")
    event = {"actor": ctx.actor_id, "at": ctx.now.isoformat(), "action": action}
    if reason:
        event["reason"] = reason
    history.append(event)
    ctx.touch(record)
    return record


def _receipt(record: dict) -> dict:
    return {"id": record["id"], "revision": record["revision"], "status": record["status"]}


def _save(ctx: Context, payload: dict) -> dict:
    is_edit = "id" in payload
    fields(
        payload,
        SAVE_FIELDS,
        SAVE_REQUIRED | ({"id", "revision"} if is_edit else set()),
    )
    if not is_edit and "revision" in payload:
        raise DomainError("invalid_field", "revision")
    timetables = _bucket(ctx.state)
    existing = _record(timetables, payload["id"], payload["revision"]) if is_edit else None
    if existing is not None and existing.get("status") == "archived":
        raise DomainError("invalid_transition")
    child = _current_child(ctx.state, payload["member"], payload["member_revision"])
    if existing is not None and existing.get("member") != child["id"]:
        raise DomainError("invalid_field", "member")

    valid_from = _local_date(payload["valid_from"], "valid_from")
    valid_until_value = payload["valid_until"]
    valid_until = (
        None if valid_until_value is None else _local_date(valid_until_value, "valid_until")
    )
    if valid_until is not None and valid_until < valid_from:
        raise DomainError("invalid_field", "valid_until")
    values = {
        "member": child["id"],
        "member_revision": _version(payload["member_revision"], "member_revision"),
        "title": text(payload["title"], "title", 120),
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat() if valid_until is not None else None,
        "lessons": _lessons(payload["lessons"]),
        "backpack_routine": _routine_link(ctx, payload["backpack_routine"], child["id"]),
        # Full replacement is uniform: omission means no exception dates.
        "exceptions": _exceptions(payload.get("exceptions", []), valid_from, valid_until),
    }
    if any(
        isinstance(other, dict)
        and other.get("id") != (existing or {}).get("id")
        and other.get("member") == child["id"]
        and other.get("status") == "active"
        for other in timetables.values()
    ):
        raise DomainError("conflict", "member")

    if existing is None:
        record = {
            "id": ctx.identifier("ST"),
            **values,
            "status": "active",
            "created_by": ctx.actor_id,
            "created_at": ctx.now.isoformat(),
            "history": [],
        }
        _mutable_bucket(ctx)[record["id"]] = record
        _history(ctx, record, "created")
        return _receipt(record)

    record = deepcopy(existing)
    if all(record.get(key) == value for key, value in values.items()):
        raise DomainError("invalid_transition")
    record.update(values)
    _history(ctx, record, "updated")
    timetables[record["id"]] = record
    return _receipt(record)


def _archive(ctx: Context, payload: dict) -> dict:
    fields(payload, {"id", "revision", "reason"}, {"id", "revision", "reason"})
    timetables = _bucket(ctx.state)
    record = deepcopy(_record(timetables, payload["id"], payload["revision"]))
    if record.get("status") != "active":
        raise DomainError("invalid_transition")
    reason = text(payload["reason"], "reason", 500)
    record["status"] = "archived"
    record["archived_at"] = ctx.now.isoformat()
    _history(ctx, record, "archived", reason=reason)
    timetables[record["id"]] = record
    return _receipt(record)


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Route explicit school work or a parent-reviewed timetable mutation."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    if action.startswith("online_"):
        from .online_school import handle as online_command

        return online_command(ctx, action.removeprefix("online_"), payload)
    if action in {"homework_create", "homework_revise"}:
        from .school_work import handle as homework_command

        return homework_command(ctx, action, payload)
    if action == "backpack_start":
        from .school_preparation import handle as preparation_command

        return preparation_command(ctx, action, payload)
    if action == "preparation_reminder_access_set":
        from .school_reminders import handle as reminder_command

        return reminder_command(ctx, action, payload)
    _require_parent(ctx)
    if action == "timetable_save":
        return _save(ctx, payload)
    if action == "timetable_archive":
        return _archive(ctx, payload)
    raise DomainError("unknown_action")


def _current_timetable(state: dict, record: dict) -> bool:
    member = state.get("members", {}).get(record.get("member"), {})
    if (
        not isinstance(member, dict)
        or not member.get("active", False)
        or member.get("role") != "child"
    ):
        return False
    try:
        return _version(record.get("member_revision"), "member_revision") == _version(
            member.get("revision"), "member_revision"
        )
    except DomainError:
        return False


def _authorized_records(state: dict, current: dict) -> tuple[list[dict], bool]:
    parent = current.get("role") in PRIVILEGED
    if not parent and current.get("role") != "child":
        return [], False
    result = []
    for stored in _bucket(state).values():
        if not isinstance(stored, dict):
            raise DomainError("invalid_field", "timetables")
        if parent or (
            stored.get("member") == current.get("id")
            and stored.get("status") == "active"
            and _current_timetable(state, stored)
        ):
            result.append(stored)
    return result, parent


def _occurrences(state: dict, records: list[dict], today: date) -> list[dict]:
    result = []
    for offset in range(14):
        try:
            day = today + timedelta(days=offset)
        except OverflowError:
            break
        day_value = day.isoformat()
        for record in records:
            if record.get("status") != "active" or not _current_timetable(state, record):
                continue
            try:
                valid_from = _local_date(record.get("valid_from"), "valid_from")
                valid_until = (
                    None
                    if record.get("valid_until") is None
                    else _local_date(record.get("valid_until"), "valid_until")
                )
            except DomainError:
                continue
            exceptions = record.get("exceptions")
            lessons = record.get("lessons")
            if (
                day < valid_from
                or valid_until is not None
                and day > valid_until
                or not isinstance(exceptions, list)
                or day_value in exceptions
                or not isinstance(lessons, list)
            ):
                continue
            routine = _current_routine(state, record.get("backpack_routine"), record["member"])
            for lesson_index, lesson in enumerate(lessons):
                if not isinstance(lesson, dict) or lesson.get("weekday") != day.weekday():
                    continue
                result.append(
                    {
                        "id": f"{record.get('id')}:{day_value}:{lesson_index}",
                        "timetable_id": record.get("id"),
                        "member": record.get("member"),
                        "date": day_value,
                        "subject": deepcopy(lesson.get("subject")),
                        "start": deepcopy(lesson.get("start")),
                        "end": deepcopy(lesson.get("end")),
                        "room": deepcopy(lesson.get("room")),
                        "materials": deepcopy(lesson.get("materials")),
                        "backpack_routine": routine,
                    }
                )
    return sorted(
        result,
        key=lambda row: (
            row["date"],
            row["start"],
            row["end"],
            row["member"],
            row["timetable_id"],
            row["id"],
        ),
    )


def view(state: dict, actor: dict, now=None) -> dict:
    """Return a pure projection; children see only their current active timetable."""
    empty = {"timetables": [], "upcoming": []}
    if not _module_enabled(state) or not isinstance(actor, dict):
        return empty
    current = state.get("members", {}).get(actor.get("id"), {})
    if not isinstance(current, dict) or not current.get("active", False):
        return empty
    records, parent = _authorized_records(state, current)
    projected = []
    for stored in records:
        item = deepcopy(stored)
        current_routine = _current_routine(
            state, stored.get("backpack_routine"), stored.get("member")
        )
        if parent:
            item["backpack_routine_current"] = current_routine
        else:
            item.pop("history", None)
            item.pop("created_by", None)
            item["backpack_routine"] = current_routine
        projected.append(item)
    upcoming = []
    if now is not None:
        moment = timestamp(now, "now")
        timezone = state.get("settings", {}).get("timezone", "UTC")
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise DomainError("invalid_field", "timezone") from None
        try:
            today = moment.astimezone(zone).date()
        except (OverflowError, OSError):
            raise DomainError("invalid_field", "now") from None
        upcoming = _occurrences(state, records, today)
    return {"timetables": projected, "upcoming": upcoming}
