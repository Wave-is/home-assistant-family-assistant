"""Task lifecycle and reviews, without channel or device dependencies."""

from __future__ import annotations

from . import task_events
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

FINAL = {"completed", "cancelled", "archived"}
ACTION_FIELDS = {
    "revise": {"title", "due_at", "assignee", "reminder_minutes", "grace_minutes", "penalty"},
    "submit": {"report"},
    "check": {"checklist_index", "done"},
    "request_changes": {"note"},
    **{key: set() for key in ("accept", "start", "complete", "cancel", "archive")},
}


def assignee_member(ctx, member_id):
    member = ctx.member(member_id)
    if member["role"] == "guest":
        raise DomainError("invalid_field", "assignee")
    return member


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if action.startswith("series_"):
        from .task_series import handle as series_command

        return series_command(ctx, action, payload)
    if ctx.actor["role"] == "guest":
        raise DomainError("forbidden")
    if action == "create":
        fields(
            payload,
            {
                "title",
                "assignee",
                "due_at",
                "report_type",
                "checklist",
                "reminder_minutes",
                "grace_minutes",
                "penalty",
            },
            {"title", "assignee"},
        )
        assignee = assignee_member(ctx, payload["assignee"])
        if not ctx.privileged and assignee["id"] != ctx.actor_id:
            raise DomainError("forbidden")
        due = payload.get("due_at")
        if due is not None:
            due = timestamp(due, "due_at").isoformat()
        report_type = payload.get("report_type", "text")
        if report_type not in {"text", "photo", "none"}:
            raise DomainError("invalid_field", "report_type")
        checklist = payload.get("checklist", [])
        if not isinstance(checklist, list) or len(checklist) > 50:
            raise DomainError("invalid_field", "checklist")
        item = {
            "id": ctx.identifier("T"),
            "title": text(payload["title"], "title"),
            "assignee": assignee["id"],
            "creator": ctx.actor_id,
            "due_at": due,
            "created_at": ctx.now.isoformat(),
            "status": "assigned",
            "report_type": report_type,
            "report": None,
            "deadline_policy": task_events.policy(ctx, payload),
            "checklist": [{"text": text(t, "checklist", 200), "done": False} for t in checklist],
        }
        ctx.state["tasks"][item["id"]] = ctx.touch(item)
        ctx.notify(assignee["id"], "task_assigned", {"id": item["id"]})
        return item
    if action not in ACTION_FIELDS:
        raise DomainError("unknown_action")
    fields(payload, {"id", "revision"} | ACTION_FIELDS[action], {"id", "revision"})
    item = ctx.record("tasks", payload["id"], strict_revision(payload["revision"]))
    own = item["assignee"] == ctx.actor_id
    if not ctx.privileged and not own:
        raise DomainError("forbidden")
    if action == "archive":
        ctx.require_parent()
        if item["status"] == "archived":
            raise DomainError("invalid_transition")
        item["previous_status"] = item["status"]
        item["status"] = "archived"
    elif item["status"] in FINAL:
        raise DomainError("invalid_transition")
    elif action == "revise":
        if not ctx.privileged and item["creator"] != ctx.actor_id:
            raise DomainError("forbidden")
        if item["status"] == "submitted":
            raise DomainError("invalid_transition")
        if "title" in payload:
            item["title"] = text(payload["title"], "title")
        if "due_at" in payload:
            new_due = (
                timestamp(payload["due_at"], "due_at") if payload["due_at"] is not None else None
            )
            old_due = timestamp(item["due_at"], "due_at") if item.get("due_at") else None
            if new_due != old_due:
                task_events.close(ctx, item)
                item["due_at"] = new_due.isoformat() if new_due else None
        if "assignee" in payload:
            ctx.require_parent()
            new_assignee = assignee_member(ctx, payload["assignee"])["id"]
            if new_assignee != item["assignee"]:
                task_events.close(ctx, item, assignment=True)
                if item.get("report") is not None:
                    item.setdefault("previous_reports", []).append(
                        {
                            "assignee": item["assignee"],
                            "report": item["report"],
                            "review_note": item.get("review_note"),
                            "reassigned_at": ctx.now.isoformat(),
                        }
                    )
                item["assignee"] = new_assignee
                item["status"] = "assigned"
                item["report"] = None
                item.pop("review_note", None)
                ctx.notify(new_assignee, "task_assigned", {"id": item["id"]})
        item["deadline_policy"] = task_events.policy(ctx, payload, item.get("deadline_policy"))
    elif action in {"accept", "start", "submit", "check"}:
        if not own and not ctx.privileged:
            raise DomainError("forbidden")
        if item["status"] == "submitted":
            raise DomainError("invalid_transition")
        if action == "submit":
            report = payload.get("report")
            if item["report_type"] != "none":
                report = text(report, "report", 2000)
            # Photo reports must be verified media references by the transport.
            if item["report_type"] == "photo":
                raise DomainError("photo_required")
            item["report"] = report
            item["status"] = "submitted"
            ctx.notify("parents", "task_review", {"id": item["id"]})
        elif action == "check":
            index = payload.get("checklist_index")
            if type(index) is not int or not 0 <= index < len(item["checklist"]):
                raise DomainError("invalid_field", "checklist_index")
            if not isinstance(payload.get("done"), bool):
                raise DomainError("invalid_field", "done")
            item["checklist"][index]["done"] = payload["done"]
        else:
            if action == "accept" and item["status"] not in {"assigned", "needs_changes"}:
                raise DomainError("invalid_transition")
            if action == "start" and item["status"] not in {
                "assigned",
                "accepted",
                "needs_changes",
            }:
                raise DomainError("invalid_transition")
            item["status"] = "accepted" if action == "accept" else "in_progress"
    elif action in {"complete", "request_changes"}:
        ctx.require_parent()
        if action == "request_changes":
            if item["status"] != "submitted":
                raise DomainError("invalid_transition")
            item["review_note"] = text(payload.get("note"), "note")
            item["status"] = "needs_changes"
        else:
            item["status"] = "completed"
            item["closed_at"] = ctx.now.isoformat()
    elif action == "cancel":
        if not ctx.privileged and item["creator"] != ctx.actor_id:
            raise DomainError("forbidden")
        item["status"] = "cancelled"
        item["closed_at"] = ctx.now.isoformat()
    else:
        raise DomainError("unknown_action")
    if item["status"] in {"submitted", "completed", "cancelled", "archived"}:
        task_events.close(ctx, item)
    return ctx.touch(item)
