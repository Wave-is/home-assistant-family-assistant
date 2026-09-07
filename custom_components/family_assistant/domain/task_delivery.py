"""Current-authority checks for persisted ordinary-task notifications."""

from __future__ import annotations

from ..const import PRIVILEGED
from .task_access import current_assignee, personal_task

TASK_EVENTS = frozenset(
    {
        "task_assigned",
        "task_reminder",
        "task_personal_due",
        "task_review",
        "task_overdue",
        "task_incident_closed",
    }
)
OPEN = frozenset({"assigned", "accepted", "in_progress", "needs_changes"})
ANNOUNCED = frozenset({"sent", "sending", "uncertain"})


def _mapping(value) -> bool:
    return isinstance(value, dict)


def _revision(value) -> bool:
    return type(value) is int and 1 <= value <= 2**53 - 1


def _active_member(state: dict, member_id: str, data: dict) -> bool:
    members = state.get("members")
    if not _mapping(members):
        return False
    member = members.get(member_id)
    if (
        not _mapping(member)
        or member.get("active") is not True
        or member.get("role") == "guest"
        or not _revision(member.get("revision"))
    ):
        return False
    # Persisted pre-epoch events are accepted only through the narrower current
    # task/recipient relationship checks performed by the caller. Once stamped,
    # a malformed or changed epoch always fails closed.
    if "member_revision" not in data:
        return True
    expected = data.get("member_revision")
    current = member.get("revision")
    return _revision(expected) and _revision(current) and expected == current


def _has_parent(state: dict) -> bool:
    members = state.get("members")
    return _mapping(members) and any(
        _mapping(member)
        and member.get("active") is True
        and member.get("role") in PRIVILEGED
        and _revision(member.get("revision"))
        for member in members.values()
    )


def _announced(deliveries) -> bool:
    return _mapping(deliveries) and any(
        _mapping(delivery) and delivery.get("state") in ANNOUNCED
        for delivery in deliveries.values()
    )


def _closure_current(state: dict, event: dict, task: dict, data: dict) -> bool:
    """Keep a truthful closure after an actually announced overdue incident."""
    task_id = data.get("id")
    member_id = data.get("member")
    if not isinstance(task_id, str) or not isinstance(member_id, str):
        return False
    # A stamped closure keeps its historical epoch across the deliberate
    # revocation exception, but malformed persisted stamps are never trusted.
    if "member_revision" in data and not _revision(data["member_revision"]):
        return False
    outbox = state.get("outbox")
    if not _mapping(outbox):
        return False
    has_original = "original_event_id" in data
    has_generation = "incident_generation" in data
    if has_original != has_generation:
        return False
    if has_original:
        original_id = data.get("original_event_id")
        generation = data.get("incident_generation")
        if not isinstance(original_id, str) or not _revision(generation):
            return False
        overdue_prefix = f"incident:task:{task_id}:{generation}:"
        closure_prefix = f"incident:task:{task_id}:{generation}:close:"
        if not original_id.startswith(overdue_prefix) or not event["id"].startswith(closure_prefix):
            return False
    else:
        # Persisted events created before closure pairs were stamped can only be
        # authorized while the current incident still points to that closure.
        incidents = state.get("incidents")
        incident = incidents.get(f"task:{task_id}") if _mapping(incidents) else None
        if (
            not _mapping(incident)
            or incident.get("state") != "closed"
            or incident.get("closure_event_id") != event.get("id")
            or incident.get("recipient") != event.get("recipient")
        ):
            return False
        original_id = incident.get("event_id")
    original = outbox.get(original_id)
    if not _mapping(original) or original.get("key") != "task_overdue":
        return False
    original_data = original.get("data")
    if (
        not _mapping(original_data)
        or original_data.get("id") != task_id
        or original_data.get("member") != member_id
        or ("member_revision" in original_data and not _revision(original_data["member_revision"]))
        or original.get("recipient") != event.get("recipient")
        or not _announced(original.get("deliveries"))
    ):
        return False
    # Completion, reassignment, member revocation, or disabling Tasks is often
    # exactly why the incident closed. Do not suppress the corrective message.
    return isinstance(task.get("assignee"), str)


def current_task_event(state: dict, event: dict) -> bool:
    """Return whether a task event still has current content and authority.

    This validates content scope only. Channel enrollment and the current target
    are still checked independently by the delivery adapter.
    """
    try:
        if not _mapping(state) or not _mapping(event) or event.get("key") not in TASK_EVENTS:
            return False
        if not isinstance(event.get("id"), str) or not event["id"]:
            return False
        recipient = event.get("recipient")
        data = event.get("data")
        if not isinstance(recipient, str) or not _mapping(data):
            return False
        task_id = data.get("id")
        tasks = state.get("tasks")
        if not isinstance(task_id, str) or not _mapping(tasks):
            return False
        task = tasks.get(task_id)
        if not _mapping(task):
            return False
        if personal_task(task) and (
            task.get("creator") != task.get("assignee")
            or recipient != task.get("assignee")
            or not current_assignee(state, task)
            or not _active_member(state, recipient, data)
            or "member_revision" not in data
            or event["key"] not in {"task_assigned", "task_reminder", "task_personal_due"}
        ):
            return False
        if event["key"] == "task_incident_closed":
            return _closure_current(state, event, task, data)

        settings = state.get("settings")
        modules = settings.get("modules") if _mapping(settings) else None
        if not isinstance(modules, list) or "tasks" not in modules:
            return False
        assignee = task.get("assignee")
        if not isinstance(assignee, str):
            return False
        stamped_member = data.get("member", assignee)
        if not isinstance(stamped_member, str) or stamped_member != assignee:
            return False
        if not _active_member(state, assignee, data):
            return False
        if not current_assignee(state, task):
            return False

        key = event["key"]
        if key == "task_assigned":
            return recipient == assignee and task.get("status") in OPEN
        if key in {"task_reminder", "task_personal_due"}:
            return (
                recipient == assignee
                and (key != "task_personal_due" or personal_task(task))
                and isinstance(data.get("due_at"), str)
                and data["due_at"] == task.get("due_at")
                and task.get("status") in OPEN
            )
        if key == "task_review":
            return (
                recipient == "parents" and task.get("status") == "submitted" and _has_parent(state)
            )
        if key != "task_overdue" or not _has_parent(state):
            return False
        if "due_at" in data and (
            not isinstance(data["due_at"], str) or data["due_at"] != task.get("due_at")
        ):
            return False
        incidents = state.get("incidents")
        incident = incidents.get(f"task:{task_id}") if _mapping(incidents) else None
        return (
            task.get("status") in OPEN
            and isinstance(task.get("due_at"), str)
            and _mapping(incident)
            and incident.get("state") == "open"
            and incident.get("event_id") == event["id"]
            and incident.get("recipient") == recipient
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
