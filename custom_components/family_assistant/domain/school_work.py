"""Explicit school homework backed by the ordinary private-task lifecycle."""

from __future__ import annotations

from copy import deepcopy

from ..const import PRIVILEGED
from . import recurrence, task_events, tasks
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

MAX_REVISION = 2**53 - 1
CREATE_FIELDS = frozenset(
    {
        "member",
        "member_revision",
        "title",
        "due_at",
        "checklist",
        "reminder_minutes",
        "grace_minutes",
        "lesson",
    }
)
CREATE_REQUIRED = frozenset({"member", "member_revision", "title", "due_at", "checklist"})
REVISE_FIELDS = frozenset(
    {
        "id",
        "revision",
        "member_revision",
        "title",
        "due_at",
        "reminder_minutes",
        "grace_minutes",
    }
)
REVISE_REQUIRED = REVISE_FIELDS
LESSON_FIELDS = frozenset({"timetable_id", "timetable_revision", "date", "lesson_index"})
REVISABLE = frozenset({"assigned", "accepted", "in_progress", "needs_changes"})
SOURCE_FIELDS = frozenset({"kind", "member", "member_revision", "lesson"})


def _version(value, field="revision") -> int:
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _require_modules(state: dict) -> None:
    modules = state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "school" not in modules or "tasks" not in modules:
        raise DomainError("module_disabled")


def _current_actor(ctx: Context) -> dict:
    actor = ctx.state.get("members", {}).get(ctx.actor_id)
    if (
        not isinstance(actor, dict)
        or actor.get("active") is not True
        or actor.get("role") == "guest"
    ):
        raise DomainError("forbidden")
    _version(actor.get("revision"), "member_revision")
    return actor


def _current_child(state: dict, member_id, member_revision) -> dict:
    member_id = text(member_id, "member", 80)
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


def _target(ctx: Context, member_id, member_revision, *, parent_only=False) -> dict:
    actor = _current_actor(ctx)
    if actor.get("role") not in PRIVILEGED:
        if parent_only or actor.get("role") != "child" or member_id != actor.get("id"):
            raise DomainError("forbidden")
    return _current_child(ctx.state, member_id, member_revision)


def _policy(payload: dict) -> dict:
    result = {}
    for key, default, maximum in (
        ("reminder_minutes", 60, 10080),
        ("grace_minutes", 30, 1440),
    ):
        value = payload.get(key, default)
        if type(value) is not int or not 0 <= value <= maximum:
            raise DomainError("invalid_field", key)
        result[key] = value
    return result


def _checklist(value) -> list[str]:
    if not isinstance(value, list) or len(value) > 50:
        raise DomainError("invalid_field", "checklist")
    return [text(item, "checklist", 200) for item in value]


def _due(value):
    return None if value is None else timestamp(value, "due_at").isoformat()


def _lesson_shape(value) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "lesson")
    fields(value, LESSON_FIELDS, LESSON_FIELDS)
    timetable_id = text(value["timetable_id"], "lesson.timetable_id", 80)
    timetable_revision = _version(value["timetable_revision"], "lesson.timetable_revision")
    lesson_date = recurrence.local_date(value["date"]).isoformat()
    lesson_index = value["lesson_index"]
    if type(lesson_index) is not int or lesson_index < 0:
        raise DomainError("invalid_field", "lesson.lesson_index")
    return {
        "timetable_id": timetable_id,
        "timetable_revision": timetable_revision,
        "date": lesson_date,
        "lesson_index": lesson_index,
    }


def _lesson(state: dict, value, child: dict) -> dict | None:
    result = _lesson_shape(value)
    if result is None:
        return None
    school = state.get("school")
    timetables = school.get("timetables") if isinstance(school, dict) else None
    if not isinstance(timetables, dict):
        raise DomainError("not_found")
    timetable = timetables.get(result["timetable_id"])
    if not isinstance(timetable, dict) or timetable.get("member") != child["id"]:
        raise DomainError("not_found")
    current_revision = _version(timetable.get("revision"), "lesson.timetable_revision")
    if result["timetable_revision"] != current_revision:
        raise DomainError("conflict")
    if timetable.get("status") != "active":
        raise DomainError("invalid_transition")
    if _version(timetable.get("member_revision"), "member_revision") != child["revision"]:
        raise DomainError("conflict")
    lesson_date = recurrence.local_date(result["date"])
    valid_from = recurrence.local_date(timetable.get("valid_from"))
    valid_until = (
        None
        if timetable.get("valid_until") is None
        else recurrence.local_date(timetable.get("valid_until"))
    )
    exceptions = timetable.get("exceptions")
    lessons = timetable.get("lessons")
    index = result["lesson_index"]
    if (
        lesson_date < valid_from
        or valid_until is not None
        and lesson_date > valid_until
        or not isinstance(exceptions, list)
        or result["date"] in exceptions
        or not isinstance(lessons, list)
        or index >= len(lessons)
    ):
        raise DomainError("invalid_field", "lesson")
    lesson = lessons[index]
    if not isinstance(lesson, dict) or lesson.get("weekday") != lesson_date.weekday():
        raise DomainError("invalid_field", "lesson")
    return result


def _source(task: dict) -> dict:
    source = task.get("source")
    if (
        not isinstance(source, dict)
        or set(source) != SOURCE_FIELDS
        or source.get("kind") != "school_homework"
        or not isinstance(source.get("member"), str)
    ):
        raise DomainError("not_found")
    _version(source.get("member_revision"), "member_revision")
    _lesson_shape(source.get("lesson"))
    return source


def is_homework_task(task: dict) -> bool:
    """Return whether a task claims the reserved School homework namespace."""
    return (
        isinstance(task, dict)
        and isinstance(task.get("source"), dict)
        and task["source"].get("kind") == "school_homework"
    )


def current_homework(state: dict, task: dict) -> bool:
    """Fail closed unless a private homework task still binds its current child."""
    try:
        source = _source(task)
        child = _current_child(state, task.get("assignee"), task.get("assignee_revision"))
        return (
            task.get("delivery_scope") == "private"
            and source["member"] == child["id"]
            and source["member_revision"] == child["revision"]
        )
    except (DomainError, TypeError, KeyError):
        return False


def _receipt(task: dict) -> dict:
    return {key: task[key] for key in ("id", "revision", "status")}


def _create(ctx: Context, payload: dict) -> dict:
    fields(payload, CREATE_FIELDS, CREATE_REQUIRED)
    child = _target(ctx, payload["member"], payload["member_revision"])
    title_value = text(payload["title"], "title")
    due_at = _due(payload["due_at"])
    checklist = _checklist(payload["checklist"])
    policy = _policy(payload)
    lesson = _lesson(ctx.state, payload.get("lesson"), child)
    task = tasks.handle(
        ctx,
        "create",
        {
            "title": title_value,
            "assignee": child["id"],
            "due_at": due_at,
            "report_type": "text",
            "checklist": checklist,
            "penalty": 0,
            **policy,
        },
    )
    task.update(
        delivery_scope="private",
        source={
            "kind": "school_homework",
            "member": child["id"],
            "member_revision": child["revision"],
            "lesson": deepcopy(lesson),
        },
    )
    return _receipt(task)


def _task(state: dict, task_id, revision_value) -> dict:
    task_id = text(task_id, "id", 80)
    tasks_bucket = state.get("tasks")
    task = tasks_bucket.get(task_id) if isinstance(tasks_bucket, dict) else None
    if not isinstance(task, dict) or not is_homework_task(task):
        raise DomainError("not_found")
    expected = _version(revision_value)
    current = _version(task.get("revision"))
    if expected != current:
        raise DomainError("conflict")
    if current == MAX_REVISION:
        raise DomainError("invalid_field", "revision")
    return task


def _reset_identity_epoch(ctx: Context, task: dict) -> None:
    """Retire child-authored lifecycle state before approving a new identity epoch."""
    task_events.close(ctx, task, assignment=True)
    tasks.task_access.archive_report(ctx, task, "reassigned_at")
    task["status"] = "assigned"
    task["report"] = None
    task.pop("review_note", None)
    task.pop("closed_at", None)
    task.pop("previous_status", None)
    task.pop("deadline_events", None)
    for entry in task["checklist"]:
        entry["done"] = False


def _revise(ctx: Context, payload: dict) -> dict:
    fields(payload, REVISE_FIELDS, REVISE_REQUIRED)
    actor = _current_actor(ctx)
    if actor.get("role") not in PRIVILEGED:
        raise DomainError("forbidden")
    task = _task(ctx.state, payload["id"], payload["revision"])
    source = _source(task)
    if source["member"] != task.get("assignee"):
        raise DomainError("not_found")
    child = _current_child(ctx.state, task["assignee"], payload["member_revision"])
    if task.get("status") not in REVISABLE:
        raise DomainError("invalid_transition")
    title_value = text(payload["title"], "title")
    due_at = _due(payload["due_at"])
    policy = _policy(payload)
    identity_changed = task.get("assignee_revision") != child["revision"]
    if identity_changed:
        _reset_identity_epoch(ctx, task)
    tasks.handle(
        ctx,
        "revise",
        {
            "id": task["id"],
            "revision": task["revision"],
            "title": title_value,
            "due_at": due_at,
            "assignee": child["id"],
            "penalty": 0,
            **policy,
        },
    )
    stored = ctx.state["tasks"][task["id"]]
    stored["source"] = {**source, "member_revision": child["revision"]}
    if identity_changed:
        ctx.notify(child["id"], "task_assigned", task_events.member_stamp(ctx, stored))
    return _receipt(stored)


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Apply an explicit homework mutation and return a content-free receipt."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    _require_modules(ctx.state)
    if action == "homework_create":
        return _create(ctx, payload)
    if action == "homework_revise":
        return _revise(ctx, payload)
    raise DomainError("unknown_action")


def authorize_replay(ctx: Context, action: str, payload: dict) -> None:
    """Recheck current modules, actor and child epoch for opaque receipts."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    _require_modules(ctx.state)
    if action == "homework_create":
        fields(payload, CREATE_FIELDS, CREATE_REQUIRED)
        child = _target(ctx, payload["member"], payload["member_revision"])
        text(payload["title"], "title")
        _due(payload["due_at"])
        _checklist(payload["checklist"])
        _policy(payload)
        _lesson_shape(payload.get("lesson"))
        return
    if action == "homework_revise":
        fields(payload, REVISE_FIELDS, REVISE_REQUIRED)
        actor = _current_actor(ctx)
        if actor.get("role") not in PRIVILEGED:
            raise DomainError("forbidden")
        task_id = text(payload["id"], "id", 80)
        _version(payload["revision"])
        text(payload["title"], "title")
        _due(payload["due_at"])
        _policy(payload)
        task = ctx.state.get("tasks", {}).get(task_id)
        if not isinstance(task, dict) or not is_homework_task(task):
            raise DomainError("not_found")
        source = _source(task)
        if source["member"] != task.get("assignee"):
            raise DomainError("not_found")
        child = _current_child(ctx.state, task["assignee"], payload["member_revision"])
        if not current_homework(ctx.state, task) or source["member_revision"] != child["revision"]:
            raise DomainError("conflict")
        return
    raise DomainError("unknown_action")
