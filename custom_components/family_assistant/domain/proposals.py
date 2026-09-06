"""Expiring actor-bound confirmation of an already validated model plan."""

from .validation import DomainError, fields, timestamp


def handle(ctx, action, payload):
    from .engine import Engine

    fields(payload, {"id"}, {"id"})
    proposal = ctx.record("proposals", payload["id"])
    if proposal["actor"] != ctx.actor_id or proposal["role"] != ctx.actor["role"]:
        raise DomainError("forbidden")
    if proposal["status"] != "pending" or ctx.now >= timestamp(
        proposal["expires_at"], "expires_at"
    ):
        raise DomainError("proposal_expired")
    if action == "reject":
        proposal["status"] = "rejected"
    elif action == "confirm":
        proposal["result"] = [
            Engine._dispatch(ctx, c["action"], c["payload"]) for c in proposal["commands"]
        ]
        proposal["status"] = "applied"
    else:
        raise DomainError("unknown_action")
    ctx.touch(proposal)
    return {"id": proposal["id"], "status": proposal["status"], "items": proposal.get("result", [])}
