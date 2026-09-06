"""Task lifecycle and reviews, without channel or device dependencies."""

from __future__ import annotations

from .context import Context
from .validation import DomainError, fields, text, timestamp

FINAL = {"completed", "cancelled", "archived"}


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if ctx.actor["role"] == "guest":
        raise DomainError("forbidden")
    if action == "create":
        fields(
            payload,
            {"title", "assignee", "due_at", "report_type", "checklist"},
            {"title", "assignee"},
        )
        assignee = ctx.member(payload["assignee"])
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
            "checklist": [{"text": text(t, "checklist", 200), "done": False} for t in checklist],
        }
        ctx.state["tasks"][item["id"]] = ctx.touch(item)
        ctx.notify(assignee["id"], "task_assigned", {"id": item["id"]})
        return item
    fields(
        payload,
        {
            "id",
            "revision",
            "title",
            "due_at",
            "assignee",
            "report",
            "note",
            "checklist_index",
            "done",
        },
        {"id"},
    )
    item = ctx.record("tasks", payload["id"], payload.get("revision"))
    own = item["assignee"] == ctx.actor_id
    if not ctx.privileged and not own:
        raise DomainError("forbidden")
    if action == "archive":
        ctx.require_parent()
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
            item["due_at"] = timestamp(payload["due_at"], "due_at").isoformat()
        if "assignee" in payload:
            ctx.require_parent()
            item["assignee"] = ctx.member(payload["assignee"])["id"]
            item["status"] = "assigned"
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
    return ctx.touch(item)
