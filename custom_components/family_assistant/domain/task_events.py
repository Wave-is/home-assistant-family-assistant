"""Deadline reminders and opt-in penalties are persisted with the task transition."""

from copy import deepcopy
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import PRIVILEGED
from . import penalties, task_access, task_delivery, task_settlements
from .context import Context
from .incidents import close_incident, open_incident
from .validation import DomainError, timestamp

# Daily local-time checkpoint after which each member gets one reminder listing
# every task that is still open, including tasks without a due date.
EVENING_CHECK = time(20, 0)
EVENING_RETENTION_DAYS = 7
EVENING_MAX_TASKS = 20


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
        **({"private_context": True} if task_access.personal_task(item) else {}),
        "member_revision": (
            item.get("assignee_revision")
            if task_access.private_task(item)
            else member.get("revision")
        ),
    }


def review_policy(ctx, payload, item, *, personal=False):
    """Reviewer time is explicitly parent-configured and independent of child due time."""
    if "review_minutes" not in payload:
        return
    ctx.require_parent()
    value = payload["review_minutes"]
    if personal or type(value) is not int or not 0 <= value <= 10080:
        raise DomainError("invalid_field", "review_minutes")
    item["review_minutes"] = value


def reviewers(state):
    return {
        member["id"]: member["revision"]
        for member in state["members"].values()
        if member.get("active") is True and member.get("role") in PRIVILEGED
    }


def schedule_review(ctx, item):
    """Persist the exact submitted report generation before any transport runs."""
    revoke_review(ctx, item)
    minutes = item.get("review_minutes", 0)
    if not minutes or task_access.personal_task(item):
        return
    try:
        due_at = (ctx.now + timedelta(minutes=minutes)).isoformat()
    except OverflowError:
        raise DomainError("invalid_field", "review_minutes") from None
    item["review_generation"] = item.get("review_generation", 0) + 1
    item["review_deadline"] = {
        "generation": item["review_generation"],
        "submission_id": ctx.operation_id,
        "submitted_at": item["submitted_at"],
        "due_at": due_at,
        "minutes": minutes,
        "member": item["assignee"],
        "member_revision": ctx.member(item["assignee"])["revision"],
        "reviewers": reviewers(ctx.state),
        "source": deepcopy(item.get("source")),
        "report_generation": item.get("report_generation"),
        "report_media": deepcopy(item.get("report_media")),
        "state": "scheduled",
    }


def review_current(state, item):
    """Identity/source changes revoke this submission's reminder, never retarget it."""
    review = item.get("review_deadline")
    if not isinstance(review, dict) or review.get("state") not in {"scheduled", "queued"}:
        return False
    if (
        type(review.get("generation")) is not int
        or review["generation"] < 1
        or not isinstance(review.get("submission_id"), str)
        or not review["submission_id"]
        or type(review.get("minutes")) is not int
        or not 0 < review["minutes"] <= 10080
    ):
        return False
    try:
        if timestamp(review.get("due_at"), "review_due_at") != timestamp(
            review.get("submitted_at"), "submitted_at"
        ) + timedelta(minutes=review["minutes"]):
            return False
    except (DomainError, OverflowError):
        return False
    member = state["members"].get(item.get("assignee"), {})
    return (
        "tasks" in state["settings"]["modules"]
        and not task_access.personal_task(item)
        and item.get("status") == "submitted"
        and type(item.get("review_minutes")) is int
        and 0 < item["review_minutes"] <= 10080
        and review.get("minutes") == item["review_minutes"]
        and review.get("generation") == item.get("review_generation")
        and review.get("submitted_at") == item.get("submitted_at")
        and review.get("report_generation") == item.get("report_generation")
        and review.get("report_media") == item.get("report_media")
        and review.get("source") == item.get("source")
        and review.get("member") == item.get("assignee")
        and member.get("active") is True
        and member.get("role") != "guest"
        and type(review.get("member_revision")) is int
        and review["member_revision"] == member.get("revision")
        and task_access.current_assignee(state, item)
        and bool(review.get("reviewers"))
        and review["reviewers"] == reviewers(state)
    )


def revoke_review(ctx, item):
    review = item.get("review_deadline")
    if isinstance(review, dict) and review.get("state") in {"scheduled", "queued"}:
        review["state"] = "revoked"
    for event in ctx.state["outbox"].values():
        if (
            event["key"] in {"task_review", "task_review_overdue"}
            and event["data"].get("id") == item["id"]
            and event["state"] in {"pending", "awaiting_channel"}
        ):
            event["state"] = "superseded"


def tick_review(ctx, item):
    if not review_current(ctx.state, item):
        if item.get("review_deadline") is not None:
            revoke_review(ctx, item)
        return
    review = item["review_deadline"]
    if review["state"] != "scheduled" or ctx.now < timestamp(review["due_at"], "review_due_at"):
        return
    notification_ctx = Context(
        ctx.state,
        ctx.actor,
        ctx.now,
        f"task-review:{item['id']}:{review['generation']}:{review['submission_id']}",
    )
    review["event_id"] = notification_ctx.notify(
        "parents",
        "task_review_overdue",
        {
            **member_stamp(ctx, item),
            "member_revision": review["member_revision"],
            "review_generation": review["generation"],
            "submission_id": review["submission_id"],
            "review_due_at": review["due_at"],
        },
    )
    review["state"] = "queued"


def close(ctx, item, *, assignment=False):
    if (
        assignment
        or item["status"] in {"completed", "cancelled", "archived"}
        or "tasks" not in ctx.state["settings"]["modules"]
    ):
        task_settlements.revoke(ctx, item)
    if (
        assignment
        or item["status"] != "submitted"
        or "tasks" not in ctx.state["settings"]["modules"]
    ):
        revoke_review(ctx, item)
    stale_keys = {"task_reminder", "task_personal_due"}
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


def evening_check(ctx: Context) -> None:
    """Once per member per local day, remind about every task still open.

    Unlike the one-shot deadline events, this repeats daily while tasks stay
    open and covers tasks without a due date, which can never reach a
    deadline window.
    """
    if "tasks" not in ctx.state["settings"]["modules"]:
        return
    try:
        zone = ZoneInfo(ctx.state["settings"].get("timezone", "UTC"))
        local_now = timestamp(ctx.now, "now").astimezone(zone)
    except (DomainError, ValueError, ZoneInfoNotFoundError, OverflowError):
        return
    if local_now.time() < EVENING_CHECK:
        return
    day = local_now.date().isoformat()
    reminders = ctx.state.setdefault("task_evening_reminders", {})
    if not isinstance(reminders, dict):
        return
    cutoff = local_now.date() - timedelta(days=EVENING_RETENTION_DAYS)
    for key in list(reminders):
        marker = reminders[key]
        try:
            marker_date = date.fromisoformat(key.rsplit(":", 1)[0])
        except ValueError:
            marker_date = None
        if not isinstance(marker, dict) or marker_date is None or marker_date < cutoff:
            reminders.pop(key, None)
    by_member = {}
    for item in ctx.state["tasks"].values():
        if not isinstance(item, dict) or item.get("status") not in task_delivery.OPEN:
            continue
        if task_access.personal_task(item):
            continue
        member_id = item.get("assignee")
        member = ctx.state["members"].get(member_id, {})
        if not member.get("active") or member.get("role") == "guest":
            continue
        if not task_access.current_assignee(ctx.state, item):
            continue
        by_member.setdefault(member_id, []).append(item)
    for member_id in sorted(by_member):
        marker_key = f"{day}:{member_id}"
        if marker_key in reminders:
            continue
        items = sorted(
            by_member[member_id],
            key=lambda item: (
                item.get("due_at") is None,
                item.get("due_at") or "",
                item.get("id") or "",
            ),
        )
        task_ids = [item["id"] for item in items[:EVENING_MAX_TASKS]]
        notification_ctx = Context(
            ctx.state, ctx.actor, ctx.now, f"task-evening:{member_id}:{day}"
        )
        event_id = notification_ctx.notify(
            member_id,
            "task_evening_reminder",
            {
                "date": day,
                "tasks": task_ids,
                # A delayed transport must not deliver a stale "evening" list
                # after local midnight.
                "expires_at": local_now.replace(
                    hour=23, minute=59, second=59, microsecond=0
                ).isoformat(),
            },
        )
        reminders[marker_key] = {"at": ctx.now.isoformat(), "event_id": event_id}


def tick(ctx: Context):
    if "tasks" not in ctx.state["settings"]["modules"]:
        for item in ctx.state["tasks"].values():
            close(ctx, item)
        return
    evening_check(ctx)
    for item in ctx.state["tasks"].values():
        tick_review(ctx, item)
        if not task_access.current_assignee(ctx.state, item):
            close(ctx, item)
            continue
        if task_settlements.managed(item) and not task_settlements.current(ctx.state, item):
            task_settlements.revoke(ctx, item)
            close(ctx, item)
            continue
        if item["status"] in {"submitted", "completed", "cancelled", "archived"} or not item.get(
            "due_at"
        ):
            close(ctx, item)
            continue
        deadline = timestamp(item["due_at"], "due_at")
        if deadline <= timestamp(item["created_at"], "created_at") and not task_settlements.managed(
            item
        ):
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
        if task_access.personal_task(item):
            if ctx.now >= deadline and not events.get("personal_due"):
                events["personal_due"] = ctx.now.isoformat()
                ctx.notify(
                    item["assignee"],
                    "task_personal_due",
                    {**member_stamp(ctx, item), "due_at": item["due_at"]},
                )
            if events:
                item.setdefault("deadline_events", {})[item["due_at"]] = events
            continue  # Personal reminders never create court rows or family incidents.
        if task_settlements.managed(item):
            if events:
                item.setdefault("deadline_events", {})[item["due_at"]] = events
            task_settlements.tick(ctx, item)
            continue
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
