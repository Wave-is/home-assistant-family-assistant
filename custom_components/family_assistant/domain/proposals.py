"""Expiring actor-bound confirmation of an already validated model plan."""

from .validation import DomainError, fields, timestamp
from .validation import revision as strict_revision


def _same_identity(proposal: dict, actor: dict) -> bool:
    """Treat a member revision as part of the actor identity, including in old state."""
    if (
        not isinstance(proposal, dict)
        or proposal.get("actor") != actor.get("id")
        or proposal.get("role") != actor.get("role")
    ):
        return False
    try:
        return strict_revision(proposal.get("actor_revision")) == strict_revision(
            actor.get("revision")
        )
    except DomainError:
        return False


def project(proposal: dict, actor: dict) -> dict | None:
    """Return a pending proposal only to the exact current member identity epoch."""
    if not _same_identity(proposal, actor) or proposal.get("status") != "pending":
        return None
    try:
        return {key: proposal[key] for key in ("id", "status", "preview", "expires_at")}
    except KeyError:
        return None


def _authorize(ctx, proposal_id) -> dict:
    proposal = ctx.record("proposals", proposal_id)
    if proposal.get("actor") != ctx.actor_id or proposal.get("role") != ctx.actor.get("role"):
        raise DomainError("forbidden")
    if not _same_identity(proposal, ctx.actor):
        # Legacy rows remain available for migration/audit, but cannot be rebound
        # silently to a later incarnation of the same member ID.
        raise DomainError("conflict")
    return proposal


def _receipt(proposal: dict) -> dict:
    return {
        "id": proposal["id"],
        "status": proposal["status"],
        "items": proposal.get("result", []),
    }


def handle(ctx, action, payload):
    from .engine import Engine

    if action in {"learn", "forget"}:
        from .learning import handle as learning

        return learning(ctx, action, payload)

    fields(payload, {"id"}, {"id"})
    proposal = _authorize(ctx, payload["id"])
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
    return _receipt(proposal)


def authorize_replay(ctx, action: str, payload: dict, result: dict) -> None:
    """Recheck the exact current identity before returning a cached transition receipt."""
    if action not in {"confirm", "reject"}:
        raise DomainError("unknown_action")
    if not isinstance(payload, dict) or not isinstance(result, dict):
        raise DomainError("forbidden")
    fields(payload, {"id"}, {"id"})
    proposal = _authorize(ctx, payload["id"])
    expected_status = "applied" if action == "confirm" else "rejected"
    if proposal.get("status") != expected_status or result != _receipt(proposal):
        raise DomainError("conflict")
