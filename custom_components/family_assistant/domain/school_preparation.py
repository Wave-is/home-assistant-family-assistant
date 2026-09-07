"""Explicit school-day backpack preparation through the existing routine engine.

This module records only a minimal timetable/date-to-run link.  It has no tick,
reminder, task, device, or Home Assistant effect of its own.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import PRIVILEGED
from . import recurrence, routines, school
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

MAX_PREPARATIONS = 5000
START_FIELDS = frozenset(
    {
        "timetable_id",
        "timetable_revision",
        "member",
        "member_revision",
        "date",
        "routine_id",
        "routine_revision",
    }
)
PUBLIC_FIELDS = (
    "id",
    "revision",
    "status",
    "timetable_id",
    "member",
    "date",
    "run_id",
)


def _modules(state: dict, *, routines_required=True) -> None:
    modules = state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "school" not in modules:
        raise DomainError("module_disabled")
    if routines_required and "routines" not in modules:
        raise DomainError("module_disabled")


def _version(value, field: str) -> int:
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _current_actor(state: dict, actor_id: str) -> dict:
    actor = state.get("members", {}).get(actor_id)
    if (
        not isinstance(actor, dict)
        or actor.get("active") is not True
        or actor.get("role") not in {*PRIVILEGED, "child"}
    ):
        raise DomainError("forbidden")
    return actor


def _current_child(state: dict, actor: dict, member_id, member_revision) -> dict:
    member_id = text(member_id, "member", 80)
    if actor.get("role") not in PRIVILEGED and member_id != actor.get("id"):
        raise DomainError("forbidden")
    member = state.get("members", {}).get(member_id)
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") != "child"
    ):
        raise DomainError("unknown_member")
    expected = _version(member_revision, "member_revision")
    current = _version(member.get("revision"), "member_revision")
    if expected != current:
        raise DomainError("conflict")
    return member


def _timetables(state: dict) -> dict:
    school_state = state.get("school", {})
    if not isinstance(school_state, dict):
        raise DomainError("invalid_field", "school")
    result = school_state.get("timetables", {})
    if not isinstance(result, dict):
        raise DomainError("invalid_field", "timetables")
    return result


def _preparations(state: dict) -> dict:
    school_state = state.get("school", {})
    if not isinstance(school_state, dict):
        raise DomainError("invalid_field", "school")
    result = school_state.get("preparations", {})
    if not isinstance(result, dict):
        raise DomainError("invalid_field", "preparations")
    return result


def _mutable_preparations(ctx: Context) -> dict:
    school_state = ctx.state.get("school")
    if school_state is None:
        school_state = {}
        ctx.state["school"] = school_state
    if not isinstance(school_state, dict):
        raise DomainError("invalid_field", "school")
    result = school_state.get("preparations")
    if result is None:
        result = {}
        school_state["preparations"] = result
    if not isinstance(result, dict):
        raise DomainError("invalid_field", "preparations")
    return result


def _local_today(state: dict, now):
    moment = timestamp(now, "now")
    timezone = state.get("settings", {}).get("timezone", "UTC")
    try:
        return moment.astimezone(ZoneInfo(timezone)).date()
    except (ZoneInfoNotFoundError, ValueError, TypeError, OverflowError, OSError):
        raise DomainError("invalid_field", "now") from None


def _day(value):
    try:
        return recurrence.local_date(value)
    except DomainError:
        raise DomainError("invalid_field", "date") from None


def _source(ctx: Context, payload: dict, *, require_day_window: bool) -> tuple:
    actor = _current_actor(ctx.state, ctx.actor_id)
    member = _current_child(
        ctx.state,
        actor,
        payload["member"],
        payload["member_revision"],
    )
    timetable_id = text(payload["timetable_id"], "timetable_id", 80)
    timetable = _timetables(ctx.state).get(timetable_id)
    # A child never gets an existence/version oracle for another child's row.
    if actor.get("role") == "child" and (
        not isinstance(timetable, dict) or timetable.get("member") != actor["id"]
    ):
        raise DomainError("not_found")
    if timetable is None:
        raise DomainError("not_found")
    if not isinstance(timetable, dict) or timetable.get("id") != timetable_id:
        raise DomainError("invalid_field", "timetables")
    timetable_revision = _version(payload["timetable_revision"], "timetable_revision")
    current_timetable_revision = _version(timetable.get("revision"), "timetable_revision")
    if timetable_revision != current_timetable_revision:
        raise DomainError("conflict")
    if timetable.get("status") != "active":
        raise DomainError("invalid_transition")
    if (
        timetable.get("member") != member["id"]
        or timetable.get("member_revision") != member["revision"]
    ):
        raise DomainError("conflict")

    day = _day(payload["date"])
    today = _local_today(ctx.state, ctx.now)
    if require_day_window:
        allowed = {today}
        try:
            allowed.add(today + timedelta(days=1))
        except OverflowError:
            pass
        if day not in allowed:
            raise DomainError("invalid_field", "date")
        occurrences = school._occurrences(ctx.state, [timetable], today)
        if not any(
            item.get("timetable_id") == timetable_id and item.get("date") == day.isoformat()
            for item in occurrences
        ):
            raise DomainError("invalid_transition")

    routine_id = text(payload["routine_id"], "routine_id", 80)
    routine_revision = _version(payload["routine_revision"], "routine_revision")
    link = timetable.get("backpack_routine")
    if not isinstance(link, dict) or set(link) != {"id", "revision"}:
        raise DomainError("invalid_transition")
    if link.get("id") != routine_id:
        raise DomainError("invalid_field", "routine_id")
    if link.get("revision") != routine_revision:
        raise DomainError("conflict")
    template = ctx.state.get("routines", {}).get(routine_id)
    if template is None:
        raise DomainError("not_found")
    if not school._routine_usable(
        ctx.state,
        template,
        member["id"],
        routine_revision,
        routine_id,
    ):
        if isinstance(template, dict) and template.get("revision") != routine_revision:
            raise DomainError("conflict")
        raise DomainError("invalid_transition")
    return actor, member, timetable, template, day


def _start(ctx: Context, payload: dict) -> dict:
    actor, member, timetable, template, day = _source(ctx, payload, require_day_window=True)
    preparations = _preparations(ctx.state)
    for stored in preparations.values():
        if (
            isinstance(stored, dict)
            and stored.get("timetable_id") == timetable["id"]
            and stored.get("date") == day.isoformat()
        ):
            raise DomainError("invalid_transition")
    if len(preparations) >= MAX_PREPARATIONS:
        raise DomainError("invalid_transition")
    for run in ctx.state.get("routine_runs", {}).values():
        if (
            isinstance(run, dict)
            and run.get("template_id") == template["id"]
            and run.get("member") == member["id"]
            and run.get("status") == "active"
        ):
            raise DomainError("invalid_transition")

    routine_ctx = Context(ctx.state, actor, ctx.now, ctx.operation_id)
    result = routines.handle(
        routine_ctx,
        "start",
        {
            "id": template["id"],
            "revision": template["revision"],
            "member": member["id"],
        },
    )
    run = ctx.state.get("routine_runs", {}).get(result.get("id"))
    if not isinstance(run, dict) or run.get("template_id") != template["id"]:
        raise DomainError("invalid_transition")
    record = {
        "id": ctx.identifier("SP"),
        "revision": 1,
        "status": "started",
        "timetable_id": timetable["id"],
        "timetable_revision": timetable["revision"],
        "member": member["id"],
        "member_revision": member["revision"],
        "date": day.isoformat(),
        "routine_id": template["id"],
        "routine_revision": template["revision"],
        "run_id": run["id"],
        "created_by": actor["id"],
        "created_at": ctx.now.isoformat(),
    }
    _mutable_preparations(ctx)[record["id"]] = record
    return {
        "id": record["id"],
        "revision": record["revision"],
        "status": record["status"],
        "run_id": record["run_id"],
    }


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Start one explicitly reviewed backpack routine for today or tomorrow."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    _modules(ctx.state)
    _current_actor(ctx.state, ctx.actor_id)
    if action != "backpack_start":
        raise DomainError("unknown_action")
    fields(payload, START_FIELDS, START_FIELDS)
    return _start(ctx, payload)


def _public(state: dict, stored: dict) -> dict:
    result = {key: deepcopy(stored.get(key)) for key in PUBLIC_FIELDS}
    run = state.get("routine_runs", {}).get(stored.get("run_id"))
    result["run_status"] = run.get("status") if isinstance(run, dict) else "unavailable"
    return result


def view(state: dict, actor: dict) -> dict:
    """Show minimal history to current parents and the current child subject."""
    empty = {"preparations": []}
    try:
        _modules(state, routines_required=False)
    except DomainError:
        return empty
    if not isinstance(actor, dict):
        return empty
    current = state.get("members", {}).get(actor.get("id"))
    if (
        not isinstance(current, dict)
        or current.get("active") is not True
        or current.get("role") not in {*PRIVILEGED, "child"}
    ):
        return empty
    parent = current.get("role") in PRIVILEGED
    result = []
    for stored in _preparations(state).values():
        if not isinstance(stored, dict):
            continue
        if parent or (
            stored.get("member") == current["id"]
            and stored.get("member_revision") == current.get("revision")
        ):
            result.append(_public(state, stored))
    result.sort(key=lambda item: (item.get("date", ""), item.get("id", "")), reverse=True)
    return {"preparations": result}


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict) -> None:
    """Recheck identity and pinned sources before returning a stored receipt."""
    _modules(ctx.state)
    _current_actor(ctx.state, ctx.actor_id)
    if action != "backpack_start" or not isinstance(payload, dict):
        raise DomainError("forbidden")
    fields(payload, START_FIELDS, START_FIELDS)
    _source(ctx, payload, require_day_window=False)
    if not isinstance(result, dict):
        raise DomainError("forbidden")
    preparation = _preparations(ctx.state).get(result.get("id"))
    if not isinstance(preparation, dict):
        raise DomainError("forbidden")
    expected = {
        "timetable_id": payload["timetable_id"],
        "timetable_revision": payload["timetable_revision"],
        "member": payload["member"],
        "member_revision": payload["member_revision"],
        "date": payload["date"],
        "routine_id": payload["routine_id"],
        "routine_revision": payload["routine_revision"],
    }
    if any(preparation.get(key) != value for key, value in expected.items()) or any(
        result.get(key) != preparation.get(key) for key in ("id", "revision", "status", "run_id")
    ):
        raise DomainError("forbidden")
    routines.check_replay(
        ctx.state,
        ctx.actor_id,
        "start",
        {"id": preparation["run_id"]},
    )
