"""Current identity and channel scope for explicitly private ordinary tasks."""

from copy import deepcopy

from ..const import PRIVILEGED
from .validation import DomainError


def private_task(task):
    if not isinstance(task, dict):
        return False
    source = task.get("source")
    return task.get("delivery_scope") == "private" or (
        isinstance(source, dict)
        and source.get("kind") in {"maintenance_fault", "maintenance_service", "school_homework"}
    )


def current_assignee(state, task):
    """Private materialized work survives asset changes, not an identity rebind."""
    member = state.get("members", {}).get(task.get("assignee"), {})
    if not member.get("active") or member.get("role") == "guest":
        return False
    if not private_task(task):
        return True
    expected = task.get("assignee_revision")
    return (
        type(expected) is int
        and 1 <= expected <= 2**53 - 1
        and type(member.get("revision")) is int
        and expected == member["revision"]
    )


def may_view(state, actor, task):
    current = state.get("members", {}).get(actor.get("id"), {})
    if not current.get("active") or current.get("role") == "guest":
        return False
    return current.get("role") in PRIVILEGED or (
        task.get("assignee") == current.get("id") and current_assignee(state, task)
    )


def public_task(task, *, parent):
    result = deepcopy(task)
    if private_task(task):
        result["delivery_scope"] = "private"
        if isinstance(task.get("source"), dict) and task["source"].get("kind") == "school_homework":
            result["managed_by"] = "school"
        if not parent:
            result.pop("source", None)
            result.pop("previous_reports", None)
    return result


def authorize_replay(state, actor, result):
    if not private_task(result):
        return
    task = state.get("tasks", {}).get(result.get("id"))
    if not isinstance(task, dict) or not may_view(state, actor, task):
        raise DomainError("forbidden")
    if actor.get("role") not in PRIVILEGED and (
        result.get("assignee") != actor.get("id")
        or result.get("assignee_revision") != actor.get("revision")
    ):
        raise DomainError("forbidden")
