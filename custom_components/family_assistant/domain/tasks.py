"""Task lifecycle and reviews, without channel or device dependencies."""

from __future__ import annotations

from . import task_access, task_events
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

FINAL = {"completed", "cancelled", "archived"}
ACTION_FIELDS = {
    "revise": {"title", "due_at", "assignee", "reminder_minutes", "grace_minutes", "penalty"},
    "submit": {"report", "media"},
    "check": {"checklist_index", "done"},
    "request_changes": {"note"},
    "report_media_purge": {
        "report_generation",
        "media_id",
        "media_revision",
        "reason",
        "confirmed",
    },
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
                "assignee_revision",
                "due_at",
                "report_type",
                "checklist",
                "reminder_minutes",
                "grace_minutes",
                "penalty",
                "personal",
            },
            {"title", "assignee"},
        )
        assignee = assignee_member(ctx, payload["assignee"])
        if "assignee_revision" in payload:
            expected_assignee_revision = strict_revision(payload["assignee_revision"])
            if expected_assignee_revision != assignee["revision"]:
                raise DomainError("conflict")
        personal = payload.get("personal", False)
        if type(personal) is not bool:
            raise DomainError("invalid_field", "personal")
        if personal and assignee["id"] != ctx.actor_id:
            raise DomainError("forbidden")
        if not ctx.privileged and assignee["id"] != ctx.actor_id:
            raise DomainError("forbidden")
        due = payload.get("due_at")
        if due is not None:
            due = timestamp(due, "due_at").isoformat()
        report_type = payload.get("report_type", "none" if personal else "text")
        if report_type not in {"text", "photo", "none"}:
            raise DomainError("invalid_field", "report_type")
        if personal and report_type != "none":
            raise DomainError("invalid_field", "report_type")
        deadline_policy = task_events.policy(
            ctx,
            payload,
            {"reminder_minutes": 0, "grace_minutes": 0, "penalty": 0} if personal else None,
        )
        if personal and (deadline_policy["penalty"] or deadline_policy["grace_minutes"]):
            raise DomainError("invalid_field", "personal_policy")
        checklist = payload.get("checklist", [])
        if not isinstance(checklist, list) or len(checklist) > 50:
            raise DomainError("invalid_field", "checklist")
        item = {
            "id": ctx.identifier("T"),
            "title": text(payload["title"], "title"),
            "assignee": assignee["id"],
            "assignee_revision": assignee["revision"],
            "creator": ctx.actor_id,
            "due_at": due,
            "created_at": ctx.now.isoformat(),
            "status": "assigned",
            "report_type": report_type,
            "report": None,
            "deadline_policy": deadline_policy,
            "checklist": [{"text": text(t, "checklist", 200), "done": False} for t in checklist],
        }
        if personal:
            item["delivery_scope"] = "personal"
        ctx.state["tasks"][item["id"]] = ctx.touch(item)
        ctx.notify(assignee["id"], "task_assigned", task_events.member_stamp(ctx, item))
        return item
    if action not in ACTION_FIELDS:
        raise DomainError("unknown_action")
    fields(payload, {"id", "revision"} | ACTION_FIELDS[action], {"id", "revision"})
    if action == "report_media_purge":
        from . import media

        required = {"id", "revision"} | ACTION_FIELDS[action]
        fields(payload, required, required)
        if ctx.actor.get("role") != "owner":
            raise DomainError("forbidden")
        if payload["confirmed"] is not True:
            raise DomainError("invalid_field", "confirmed")
        text(payload["reason"], "reason", 500)
        item = ctx.record("tasks", payload["id"], strict_revision(payload["revision"]))
        media.purge_task_report(
            ctx,
            item,
            payload["report_generation"],
            payload["media_id"],
            payload["media_revision"],
        )
        return {key: item[key] for key in ("id", "revision", "status")}
    item = ctx.record("tasks", payload["id"], strict_revision(payload["revision"]))
    if task_access.private_task(item) and not task_access.may_view(ctx.state, ctx.actor, item):
        raise DomainError("forbidden")
    personal = task_access.personal_task(item)
    if personal and action in {"submit", "request_changes"}:
        raise DomainError("invalid_transition")
    own = item["assignee"] == ctx.actor_id
    if not ctx.privileged and not own:
        raise DomainError("forbidden")
    if action == "archive":
        if not personal:
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
            if personal:
                raise DomainError("invalid_field", "assignee")
            ctx.require_parent()
            new_assignee = assignee_member(ctx, payload["assignee"])["id"]
            if (
                new_assignee != item["assignee"]
                or item.get("assignee_revision") != ctx.member(new_assignee)["revision"]
            ):
                task_events.close(ctx, item, assignment=True)
                task_access.archive_report(ctx, item, "reassigned_at")
                item["assignee"] = new_assignee
                item["assignee_revision"] = ctx.member(new_assignee)["revision"]
                item["status"] = "assigned"
                item["report"] = None
                item.pop("review_note", None)
                ctx.notify(new_assignee, "task_assigned", task_events.member_stamp(ctx, item))
            else:
                # An explicitly reviewed assignment refreshes a changed identity binding.
                item["assignee_revision"] = ctx.member(new_assignee)["revision"]
        item["deadline_policy"] = task_events.policy(ctx, payload, item.get("deadline_policy"))
        if personal and (
            item["deadline_policy"]["penalty"] or item["deadline_policy"]["grace_minutes"]
        ):
            raise DomainError("invalid_field", "personal_policy")
    elif action in {"accept", "start", "submit", "check"}:
        if not own and not ctx.privileged:
            raise DomainError("forbidden")
        if item["status"] == "submitted":
            raise DomainError("invalid_transition")
        if action == "submit":
            if item["report_type"] == "photo":
                from . import media

                if "report" in payload or "media" not in payload:
                    raise DomainError("photo_required")
                task_access.archive_report(ctx, item, "resubmitted_at")
                media.attach_task_report(ctx, item, payload["media"])
                item["report"] = None
            else:
                if "media" in payload:
                    raise DomainError("invalid_field", "media")
                report = payload.get("report")
                if item["report_type"] != "none":
                    report = text(report, "report", 2000)
                task_access.archive_report(ctx, item, "resubmitted_at")
                item["report"] = report
            item["submitted_at"] = ctx.now.isoformat()
            item["status"] = "submitted"
            ctx.notify("parents", "task_review", task_events.member_stamp(ctx, item))
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
        if not personal:
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
    ctx.touch(item)
    # Command receipts obey the same private projection as reads. The stored
    # record keeps its source for lifecycle guards, but a child response does not.
    if item["report_type"] == "photo":
        return {key: item[key] for key in ("id", "revision", "status")}
    return task_access.public_task(item, parent=ctx.privileged)
