"""Current identity and channel scope for explicitly private ordinary tasks."""

from copy import deepcopy
from datetime import UTC, datetime

from ..const import PRIVILEGED
from .validation import DomainError


def personal_task(task):
    return isinstance(task, dict) and task.get("delivery_scope") == "personal"


def private_task(task):
    if not isinstance(task, dict):
        return False
    source = task.get("source")
    return task.get("delivery_scope") in {"private", "personal"} or (
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
    if personal_task(task):
        return task.get("creator") == task.get("assignee") == current.get(
            "id"
        ) and current_assignee(state, task)
    return current.get("role") in PRIVILEGED or (
        task.get("assignee") == current.get("id") and current_assignee(state, task)
    )


def archive_report(ctx, task, reason):
    """Retain report identity stamps before replacing the current attachment slot."""
    purged_at = task.get("report_media_purged_at")
    if task.get("report") is not None or task.get("report_media") or purged_at is not None:
        previous = {
            "assignee": task["assignee"],
            "report": task.get("report"),
            "review_note": task.get("review_note"),
            reason: ctx.now.isoformat(),
        }
        if task.get("submitted_at") is not None:
            previous["submitted_at"] = task["submitted_at"]
        if task.get("assignee_revision") is not None:
            previous["assignee_revision"] = task["assignee_revision"]
        if task.get("report_media"):
            previous.update(
                assignee_revision=task.get("assignee_revision"),
                report_media=list(task["report_media"]),
                report_generation=task.get("report_generation", 0),
            )
        elif purged_at is not None:
            previous.update(
                assignee_revision=task.get("assignee_revision"),
                report_generation=task.get("report_generation", 0),
                report_media_purged_at=purged_at,
            )
        task.setdefault("previous_reports", []).append(previous)
    task.pop("report_media", None)
    task.pop("report_media_purged_at", None)
    task["report"] = None
    task.pop("review_note", None)
    task.pop("submitted_at", None)


def public_task(task, *, parent, state=None, actor=None, now=None):
    result = deepcopy(task)
    if not parent:
        result.pop("previous_reports", None)
    # A global library or raw ID list would disclose stale/private attachments.
    # Only current object authority can produce the bounded metadata for the UI.
    for report in [result, *result.get("previous_reports", [])]:
        references = report.pop("report_media", [])
        report.pop("report_attachments", None)
        if references and state is not None and actor is not None:
            from .media import read_metadata

            attachments = []
            for reference in references:
                try:
                    attachments.append(
                        read_metadata(state, actor, reference, now or datetime.now(UTC))
                    )
                except DomainError:
                    continue
            report["report_attachments"] = attachments
    if private_task(task):
        result["delivery_scope"] = "personal" if personal_task(task) else "private"
        if isinstance(task.get("source"), dict) and task["source"].get("kind") == "school_homework":
            result["managed_by"] = "school"
        if not parent:
            result.pop("source", None)
            result.pop("previous_reports", None)
    return result


def authorize_replay(state, actor, result):
    current = state.get("tasks", {}).get(result.get("id"))
    if personal_task(result) or personal_task(current):
        if (
            not personal_task(current)
            or not may_view(state, actor, current)
            or result.get("creator") != actor.get("id")
            or result.get("assignee") != actor.get("id")
            or result.get("assignee_revision") != actor.get("revision")
        ):
            raise DomainError("forbidden")
        return
    if isinstance(current, dict) and current.get("report_type") == "photo":
        if not may_view(state, actor, current):
            raise DomainError("forbidden")
        if actor.get("role") not in PRIVILEGED and current.get("assignee_revision") != actor.get(
            "revision"
        ):
            raise DomainError("forbidden")
        return
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


def audit_visible(state, actor, result):
    """Hide a whole mixed batch if any personal receipt is outside current scope."""
    if not isinstance(result, dict):
        return False
    if isinstance(result.get("items"), list):
        return all(audit_visible(state, actor, item) for item in result["items"])
    event = state.get("outbox", {}).get(result.get("id"))
    if isinstance(event, dict) and not event_visible(state, actor, event):
        return False
    task = state.get("tasks", {}).get(result.get("id"))
    if not personal_task(result) and not personal_task(task):
        return True
    try:
        authorize_replay(state, actor, result)
    except DomainError:
        return False
    return True


def event_visible(state, actor, event):
    data = event.get("data", {})
    task = state.get("tasks", {}).get(data.get("id"))
    if data.get("private_context") is True and not personal_task(task):
        current = state.get("members", {}).get(actor.get("id"), {})
        return (
            event.get("key") == "telegram_reply"
            and current.get("active") is True
            and data.get("actor") == event.get("recipient") == current.get("id")
            and data.get("actor_revision") == current.get("revision")
        )
    return not personal_task(task) or (
        may_view(state, actor, task)
        and event.get("recipient") == actor.get("id")
        and data.get("member_revision") == actor.get("revision")
    )
