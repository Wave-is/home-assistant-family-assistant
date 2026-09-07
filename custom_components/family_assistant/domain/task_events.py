"""Deadline reminders and opt-in penalties are persisted with the task transition."""

from datetime import timedelta

from . import penalties, task_access
from .context import Context
from .incidents import close_incident, open_incident
from .validation import DomainError, timestamp


def policy(ctx, payload, previous=None):
    result = dict(previous or {"reminder_minutes": 60, "grace_minutes": 30, "penalty": 0})
    for key, minimum, maximum in (
        ("reminder_minutes", 0, 10080),
        ("grace_minutes", 0, 1440),
        ("penalty", -10, 0),
    ):
        if key not in payload:
            continue
        value = payload[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise DomainError("invalid_field", key)
        if key == "penalty" and value:
            ctx.require_parent()
        result[key] = value
    return result


def member_stamp(ctx, item):
    member = ctx.state["members"].get(item["assignee"], {})
    return {
        "id": item["id"],
        "member": item["assignee"],
        "member_revision": (
            item.get("assignee_revision")
            if task_access.private_task(item)
            else member.get("revision")
        ),
    }


def close(ctx, item, *, assignment=False):
    stale_keys = {"task_reminder"}
    if assignment or item["status"] in {"submitted", "completed", "cancelled", "archived"}:
        stale_keys.add("task_assigned")
    if item["status"] in {"completed", "cancelled", "archived"} or assignment:
        stale_keys.add("task_review")
    for event in ctx.state["outbox"].values():
        if (
            event["key"] in stale_keys
            and event["data"].get("id") == item["id"]
            and event["state"] in {"pending", "awaiting_channel"}
        ):
            event["state"] = "superseded"
    closure_data = member_stamp(ctx, item)
    incident = ctx.state["incidents"].get(f"task:{item['id']}")
    if incident and incident.get("state") == "open":
        original = ctx.state["outbox"].get(incident.get("event_id"), {})
        original_data = original.get("data", {})
        # Preserve the original incident's subject even if closure follows an
        # identity change or a later incident reuses the task's incident slot.
        for key in ("member", "member_revision"):
            if key in original_data:
                closure_data[key] = original_data[key]
        closure_data.update(
            original_event_id=incident["event_id"],
            incident_generation=incident["generation"],
        )
    close_incident(
        ctx,
        f"task:{item['id']}",
        "task_incident_closed",
        closure_data,
    )


def tick(ctx: Context):
    if "tasks" not in ctx.state["settings"]["modules"]:
        for item in ctx.state["tasks"].values():
            close(ctx, item)
        return
    for item in ctx.state["tasks"].values():
        if not task_access.current_assignee(ctx.state, item):
            close(ctx, item)
            continue
        if item["status"] in {"submitted", "completed", "cancelled", "archived"} or not item.get(
            "due_at"
        ):
            close(ctx, item)
            continue
        deadline = timestamp(item["due_at"], "due_at")
        if deadline <= timestamp(item["created_at"], "created_at"):
            continue  # Never issue a retroactive automatic penalty on an imported/past task.
        config = item.get(
            "deadline_policy", {"reminder_minutes": 60, "grace_minutes": 30, "penalty": 0}
        )
        events = item.get("deadline_events", {}).get(item["due_at"], {})
        reminder = deadline - timedelta(minutes=config["reminder_minutes"])
        if (
            config["reminder_minutes"]
            and reminder <= ctx.now < deadline
            and not events.get("reminded")
        ):
            events["reminded"] = ctx.now.isoformat()
            notification_ctx = Context(
                ctx.state, ctx.actor, ctx.now, f"task-reminder:{item['id']}:{item['due_at']}"
            )
            notification_ctx.notify(
                item["assignee"],
                "task_reminder",
                {**member_stamp(ctx, item), "due_at": item["due_at"]},
            )
        if ctx.now >= deadline + timedelta(minutes=config["grace_minutes"]) and not events.get(
            "escalated"
        ):
            events["escalated"] = ctx.now.isoformat()
            open_incident(
                ctx,
                f"task:{item['id']}",
                "task_overdue",
                {**member_stamp(ctx, item), "due_at": item["due_at"]},
                recipient="parents" if task_access.private_task(item) else "family",
            )
            events["penalty_applied"] = penalties.award(
                ctx,
                source="task",
                source_id=item["id"],
                member=item["assignee"],
                points=config["penalty"],
                reason_key="task_missed",
                reason_data={"task_id": item["id"], "due_at": item["due_at"]},
                timezone=ctx.state["settings"].get("timezone", "UTC"),
            )
        if events:
            item.setdefault("deadline_events", {})[item["due_at"]] = events
