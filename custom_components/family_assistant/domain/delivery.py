"""Parent review for failed or uncertain notifications; no automatic blind retry."""

from .context import Context
from .task_access import event_visible
from .validation import DomainError, fields, text


def handle(ctx: Context, action: str, payload: dict) -> dict:
    ctx.require_parent()
    fields(payload, {"id", "reason", "confirmed"}, {"id", "reason"})
    event_id = text(payload["id"], "id", 400)
    reason = text(payload["reason"], "reason")
    event = ctx.state["outbox"].get(event_id)
    if event is None:
        raise DomainError("not_found")
    if not event_visible(ctx.state, ctx.actor, event):
        raise DomainError("forbidden")
    if event["state"] not in {"uncertain", "failed"}:
        raise DomainError("invalid_transition")
    if action == "retry":
        if payload.get("confirmed") is not True:
            raise DomainError("retry_confirmation_required")
        for delivery in event.get("deliveries", {}).values():
            if delivery["state"] in {"uncertain", "failed"}:
                delivery.setdefault("retry_history", []).append(
                    {
                        "state": delivery["state"],
                        "attempts": delivery["attempts"],
                        "actor": ctx.actor_id,
                        "at": ctx.now.isoformat(),
                        "reason": reason,
                    }
                )
                delivery.update(state="pending", attempts=0, next_at=ctx.now.isoformat())
        event["state"] = "pending"
    elif action == "resolve":
        event["state"] = "resolved"
        event["resolution"] = {"actor": ctx.actor_id, "at": ctx.now.isoformat(), "reason": reason}
    else:
        raise DomainError("unknown_action")
    # Do not return delivery destinations or message contents to a card.
    return {"id": event_id, "state": event["state"], "reason": reason}


def authorize_replay(state, actor, payload):
    event = state.get("outbox", {}).get(payload.get("id"))
    if (
        actor.get("role") not in {"owner", "parent"}
        or event is None
        or not event_visible(state, actor, event)
    ):
        raise DomainError("forbidden")
