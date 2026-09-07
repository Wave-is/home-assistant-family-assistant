"""Bounded, recipient-scoped content for private family digests."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import PRIVILEGED
from . import family_calendar, maintenance, pantry, polls, routines, school, task_access
from .validation import DomainError, timestamp

KINDS = frozenset({"morning", "evening", "weekly"})
DETAIL_KEYS = frozenset({"tasks", "calendar", "routines", "school"})
COUNT_KEYS = frozenset(
    {
        "shopping",
        "pantry_low_stock",
        "pantry_expiring",
        "maintenance_faults",
        "maintenance_services",
        "polls_open",
        "polls_results",
    }
)
ROW_KEYS = {
    "tasks": {"title", "status", "due_at"},
    "calendar": {"title", "start", "all_day"},
    "routines": {"routine_title", "step_title"},
    "school": {"date", "subject", "start", "materials"},
}
DETAIL_LIMIT = 10
MATERIAL_LIMIT = 10
FINAL_TASKS = frozenset({"completed", "cancelled", "archived"})
ACTIVE_TASKS = frozenset({"assigned", "accepted", "in_progress", "submitted", "needs_changes"})


def _empty(kind, start, end):
    return {
        "schema": 1,
        "kind": kind,
        "window_start": start,
        "window_end": end,
        "sections": [],
    }


def _canonical_day(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def has_content(value) -> bool:
    """Return whether a structurally valid snapshot has at least one section."""
    if not (
        isinstance(value, dict)
        and set(value)
        == {
            "schema",
            "kind",
            "window_start",
            "window_end",
            "sections",
        }
        and value.get("schema") == 1
        and value.get("kind") in KINDS
        and isinstance(value.get("window_start"), str)
        and isinstance(value.get("window_end"), str)
        and isinstance(value.get("sections"), list)
        and value["sections"]
    ):
        return False
    if not _canonical_day(value["window_start"]) or not _canonical_day(value["window_end"]):
        return False
    start = date.fromisoformat(value["window_start"])
    end = date.fromisoformat(value["window_end"])
    expected_days = 7 if value["kind"] == "weekly" else 1
    if end - start != timedelta(days=expected_days):
        return False
    seen = set()
    for section in value["sections"]:
        if not isinstance(section, dict) or set(section) != {
            "key",
            "rows",
            "count",
            "overflow",
        }:
            return False
        key = section.get("key")
        rows = section.get("rows")
        count = section.get("count")
        overflow = section.get("overflow")
        if (
            key not in DETAIL_KEYS | COUNT_KEYS
            or key in seen
            or not isinstance(rows, list)
            or len(rows) > DETAIL_LIMIT
            or type(count) is not int
            or type(overflow) is not int
            or count <= 0
            or overflow < 0
            or count < len(rows) + overflow
            or key in COUNT_KEYS
            and (rows or overflow)
        ):
            return False
        if key in DETAIL_KEYS:
            for row in rows:
                if not isinstance(row, dict) or set(row) != ROW_KEYS[key]:
                    return False
                if key == "calendar":
                    if (
                        not isinstance(row["title"], str)
                        or not isinstance(row["start"], str)
                        or type(row["all_day"]) is not bool
                    ):
                        return False
                elif key == "school":
                    if (
                        not _canonical_day(row["date"])
                        or not isinstance(row["subject"], str)
                        or not isinstance(row["start"], str)
                        or not isinstance(row["materials"], list)
                        or len(row["materials"]) > MATERIAL_LIMIT
                        or any(not isinstance(item, str) for item in row["materials"])
                    ):
                        return False
                elif any(not isinstance(item, str) for item in row.values()):
                    return False
        seen.add(key)
    return True


def _day(value, field):
    if not isinstance(value, str):
        raise DomainError("invalid_field", field)
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise DomainError("invalid_field", field) from None
    if value != result.isoformat():
        raise DomainError("invalid_field", field)
    return result


def _context(state, actor, kind, window_start, window_end, now):
    if kind not in KINDS:
        raise DomainError("invalid_field", "kind")
    moment = timestamp(now, "now")
    start = _day(window_start, "window_start")
    end = _day(window_end, "window_end")
    expected_days = 7 if kind == "weekly" else 1
    if end - start != timedelta(days=expected_days):
        raise DomainError("invalid_field", "window_end")
    try:
        zone = ZoneInfo(state.get("settings", {}).get("timezone", "UTC"))
        today = moment.astimezone(zone).date()
    except (AttributeError, TypeError, ValueError, ZoneInfoNotFoundError):
        raise DomainError("invalid_field", "timezone") from None
    try:
        permitted_starts = {today, today + timedelta(days=1)}
        if kind == "weekly":
            permitted_starts.add(today - timedelta(days=1))
    except OverflowError:
        raise DomainError("invalid_field", "now") from None
    if start not in permitted_starts:
        raise DomainError("invalid_field", "window_start")
    if not isinstance(actor, dict):
        return None, zone, start, end
    current = state.get("members", {}).get(actor.get("id"))
    if (
        not isinstance(current, dict)
        or current.get("active") is not True
        or current.get("role") == "guest"
        or actor.get("revision") != current.get("revision")
        or actor.get("role") != current.get("role")
    ):
        return None, zone, start, end
    return current, zone, start, end


def _section(key, rows, count, detail_count=None):
    count = max(0, int(count))
    detail_count = count if detail_count is None else max(0, int(detail_count))
    rows = rows[:DETAIL_LIMIT]
    return {
        "key": key,
        "rows": rows,
        "count": count,
        "overflow": max(0, detail_count - len(rows)),
    }


def _in_window(value, zone, start, end):
    try:
        return start <= timestamp(value, "time").astimezone(zone).date() < end
    except DomainError:
        return False


def _task_section(state, actor, zone, start, end):
    projected = []
    for task in state.get("tasks", {}).values():
        if (
            not isinstance(task, dict)
            or task.get("status") not in ACTIVE_TASKS
            or not isinstance(task.get("due_at"), str)
            or not _in_window(task.get("due_at"), zone, start, end)
            or not task_access.may_view(state, actor, task)
            or actor.get("role") not in PRIVILEGED
            and task.get("assignee") != actor.get("id")
        ):
            continue
        projected.append(task)
    projected.sort(key=lambda row: (row["due_at"], row.get("id", "")))
    own = [row for row in projected if row.get("assignee") == actor["id"]]
    rows = [
        {"title": row["title"], "status": row["status"], "due_at": row["due_at"]}
        for row in own[:DETAIL_LIMIT]
    ]
    return _section("tasks", rows, len(projected), len(own)) if projected else None


def _calendar_section(state, actor, zone, start, end):
    range_start = datetime.combine(start, time.min, zone)
    range_end = datetime.combine(end, time.min, zone)
    occurrences = []
    for record in state.get("calendar", {}).values():
        if (
            not isinstance(record, dict)
            or record.get("status") != "confirmed"
            or not family_calendar.visible(record, actor)
        ):
            continue
        personal = (
            actor["id"] == record.get("creator")
            or actor["id"] in record.get("participants", [])
            or actor["id"] == record.get("escort")
        )
        for occurrence in family_calendar.occurrences(record, range_start, range_end, str(zone)):
            occurrences.append(
                (family_calendar.moment(occurrence, str(zone)), personal, occurrence)
            )
    occurrences.sort(key=lambda item: (item[0], item[2].get("id", "")))
    personal = [item[2] for item in occurrences if item[1]]
    rows = [
        {"title": row["title"], "start": row["start"], "all_day": row["all_day"]}
        for row in personal[:DETAIL_LIMIT]
    ]
    return _section("calendar", rows, len(occurrences), len(personal)) if occurrences else None


def _routine_section(state, actor):
    projection = routines.view(state, actor)
    active = [row for row in projection["runs"] if row.get("status") == "active"]
    active.sort(key=lambda row: (row.get("planned_at", ""), row.get("id", "")))
    details = []
    for run in active:
        for step in run.get("steps", []):
            if step.get("status") == "active" and routines.step_member(run, step) == actor["id"]:
                details.append(
                    {
                        "routine_title": run["title"],
                        "step_title": step["title"],
                    }
                )
                break
    return _section("routines", details, len(active), len(details)) if active else None


def _school_section(state, actor, now, start, end):
    projection = school.view(state, actor, now)
    upcoming = [
        row
        for row in projection["upcoming"]
        if isinstance(row, dict)
        and isinstance(row.get("date"), str)
        and start.isoformat() <= row["date"] < end.isoformat()
    ]
    upcoming.sort(key=lambda row: (row["date"], row["start"], row.get("id", "")))
    detail_rows = upcoming if actor.get("role") == "child" else []
    rows = [
        {
            "date": row["date"],
            "subject": row["subject"],
            "start": row["start"],
            "materials": list(row.get("materials", []))[:MATERIAL_LIMIT],
        }
        for row in detail_rows[:DETAIL_LIMIT]
    ]
    return _section("school", rows, len(upcoming), len(detail_rows)) if upcoming else None


def _shopping_section(state):
    count = 0
    for row in state.get("shopping", {}).values():
        if not isinstance(row, dict) or row.get("status") not in {"pending", "approved"}:
            continue
        quantity, purchased = row.get("quantity"), row.get("purchased")
        if (
            type(quantity) in {int, float}
            and type(purchased) in {int, float}
            and quantity > purchased
        ):
            count += 1
    return _section("shopping", [], count, 0) if count else None


def _pantry_sections(state, now):
    items = state.get("pantry", {}).get("items", {})
    if not isinstance(items, dict):
        raise DomainError("invalid_field", "items")
    active = [
        row for row in items.values() if isinstance(row, dict) and row.get("status") == "active"
    ]
    low = sum(pantry._deficit(row) > 0 for row in active)
    expiring = sum(
        pantry._expiry_status(state, row.get("expires_on"), now)[0]
        in {"expired", "today", "expiring"}
        for row in active
    )
    return [
        section
        for section in (
            _section("pantry_low_stock", [], low, 0) if low else None,
            _section("pantry_expiring", [], expiring, 0) if expiring else None,
        )
        if section is not None
    ]


def _maintenance_sections(state, actor):
    projection = maintenance.view(state, actor)
    open_faults = sum(
        row.get("task_status") in ACTIVE_TASKS
        for row in projection["faults"]
        if isinstance(row, dict)
    )
    open_services = sum(
        row.get("enabled") is True and row.get("current") is True
        for row in projection["services"]
        if isinstance(row, dict)
    )
    return [
        section
        for section in (
            _section("maintenance_faults", [], open_faults, 0) if open_faults else None,
            _section("maintenance_services", [], open_services, 0) if open_services else None,
        )
        if section is not None
    ]


def _poll_sections(state, actor, now):
    projection = polls.view(state, actor, now)
    return [
        section
        for section in (
            _section("polls_open", [], len(projection["open"]), 0) if projection["open"] else None,
            _section("polls_results", [], len(projection["closed"]), 0)
            if projection["closed"]
            else None,
        )
        if section is not None
    ]


def snapshot(
    state: dict,
    actor: dict,
    kind: str,
    window_start: str,
    window_end: str,
    now: datetime,
) -> dict:
    """Build a bounded snapshot from explicit current domain authorization rules."""
    current, zone, start, end = _context(state, actor, kind, window_start, window_end, now)
    result = _empty(kind, window_start, window_end)
    modules = state.get("settings", {}).get("modules", [])
    if current is None or not isinstance(modules, list) or "digests" not in modules:
        return result

    sections = []
    if "tasks" in modules:
        section = _task_section(state, current, zone, start, end)
        if section:
            sections.append(section)
    if "calendar" in modules:
        section = _calendar_section(state, current, zone, start, end)
        if section:
            sections.append(section)
    if "routines" in modules:
        section = _routine_section(state, current)
        if section:
            sections.append(section)
    if "school" in modules and current.get("role") in {*PRIVILEGED, "child"}:
        section = _school_section(state, current, now, start, end)
        if section:
            sections.append(section)
    if "shopping" in modules:
        section = _shopping_section(state)
        if section:
            sections.append(section)
    if "pantry" in modules:
        sections.extend(_pantry_sections(state, now))
    if "maintenance" in modules:
        sections.extend(_maintenance_sections(state, current))
    if "polls" in modules:
        sections.extend(_poll_sections(state, current, now))
    result["sections"] = sections
    return result
