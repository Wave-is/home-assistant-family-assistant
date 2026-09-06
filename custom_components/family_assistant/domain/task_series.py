"""Recurring duties create ordinary, independently reviewable task instances."""

from datetime import timedelta

from ..const import PRIVILEGED
from . import recurrence, task_events
from .context import Context
from .validation import DomainError, fields, text, timestamp


def handle(ctx, action, payload):
    ctx.require_parent()
    if action == "series_enable":
        fields(payload, {"id", "enabled", "revision"}, {"id", "enabled"})
        item = ctx.record("task_series", payload["id"], payload.get("revision"))
        if type(payload["enabled"]) is not bool:
            raise DomainError("invalid_field", "enabled")
        item["enabled"] = payload["enabled"]
        item["effective_at"] = ctx.now.isoformat()
        return ctx.touch(item)
    if action != "series_save":
        raise DomainError("unknown_action")
    fields(
        payload,
        {
            "id",
            "revision",
            "title",
            "assignees",
            "rotation",
            "rule",
            "due_time",
            "report_type",
            "checklist",
            "enabled",
            "reminder_minutes",
            "grace_minutes",
            "penalty",
        },
        {"title", "assignees", "rule", "due_time"},
    )
    members = payload["assignees"]
    if (
        not isinstance(members, list)
        or not 1 <= len(members) <= 20
        or any(not isinstance(member, str) for member in members)
        or len(set(members)) != len(members)
    ):
        raise DomainError("invalid_field", "assignees")
    for member in members:
        ctx.member(member)
    rotation, enabled = payload.get("rotation", False), payload.get("enabled", True)
    if type(rotation) is not bool or type(enabled) is not bool:
        raise DomainError("invalid_field", "enabled")
    existing = (
        ctx.record("task_series", payload["id"], payload.get("revision"))
        if payload.get("id")
        else {}
    )
    report_type = payload.get("report_type", "text")
    if report_type not in {"text", "photo", "none"}:
        raise DomainError("invalid_field", "report_type")
    checklist = payload.get("checklist", [])
    if not isinstance(checklist, list) or len(checklist) > 50:
        raise DomainError("invalid_field", "checklist")
    item = {
        **existing,
        "id": existing.get("id") or ctx.identifier("D"),
        "creator": ctx.actor_id,
        "title": text(payload["title"], "title"),
        "assignees": list(members),
        "rotation": rotation,
        "enabled": enabled,
        "rule": recurrence.validate(payload["rule"]),
        "due_time": recurrence.clock(payload["due_time"]),
        "report_type": report_type,
        "checklist": [text(t, "checklist", 200) for t in checklist],
        "deadline_policy": task_events.policy(ctx, payload, existing.get("deadline_policy")),
        "effective_at": ctx.now.isoformat(),
        "cursor": existing.get("cursor", 0),
        "occurrences": existing.get("occurrences", {}),
    }
    ctx.state["task_series"][item["id"]] = ctx.touch(item)
    return item


def tick(ctx):
    from .tasks import handle as task_command

    if "tasks" not in ctx.state["settings"]["modules"]:
        return
    for series in ctx.state["task_series"].values():
        creator = ctx.state["members"].get(series["creator"], {})
        if (
            not series["enabled"]
            or not creator.get("active")
            or creator.get("role") not in PRIVILEGED
        ):
            continue
        for moment in recurrence.due(
            series["rule"], ctx.now, not_before=timestamp(series["effective_at"], "effective_at")
        ):
            occurrence_id = moment.date().isoformat()
            if occurrence_id in series["occurrences"]:
                continue
            available = [
                m for m in series["assignees"] if ctx.state["members"].get(m, {}).get("active")
            ]
            if not available:
                continue
            selected = (
                [available[series["cursor"] % len(available)]] if series["rotation"] else available
            )
            day = moment.date() + (
                timedelta(days=1) if series["due_time"] < series["rule"]["time"] else timedelta()
            )
            deadline = recurrence.local_clock(day, series["due_time"], series["rule"]["timezone"])
            if deadline is None or deadline <= ctx.now:
                # A late restart never creates a task already overdue and immediately punishes it.
                series["occurrences"][occurrence_id] = {"state": "skipped_deadline", "tasks": []}
                continue
            ids = []
            for member in selected:
                child_ctx = Context(
                    ctx.state, creator, ctx.now, f"series:{series['id']}:{occurrence_id}:{member}"
                )
                task = task_command(
                    child_ctx,
                    "create",
                    {
                        "title": series["title"],
                        "assignee": member,
                        "due_at": deadline.isoformat(),
                        "report_type": series["report_type"],
                        "checklist": series["checklist"],
                        **series.get("deadline_policy", {}),
                    },
                )
                task.update(series_id=series["id"], occurrence_id=occurrence_id)
                ids.append(task["id"])
            series["occurrences"][occurrence_id] = {"state": "created", "tasks": ids}
            series["cursor"] += 1
            ctx.touch(series)
