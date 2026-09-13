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
    result = {
        "id": proposal["id"],
        "status": proposal["status"],
        "items": proposal.get("result", []),
    }
    if proposal.get("feedback_id"):
        result["feedback_id"] = proposal["feedback_id"]
    return result


def handle(ctx, action, payload):
    from .engine import Engine

    if action == "apply_name_repair":
        from .name_learning import handle as repair_name

        return repair_name(ctx, payload)

    if action in {"learn", "forget"}:
        from .learning import handle as learning

        return learning(ctx, action, payload)

    if action == "feedback_purge":
        from .semantic_feedback import purge

        return purge(ctx, payload)

    fields(payload, {"id", "feedback"} if action == "reject" else {"id"}, {"id"})
    proposal = _authorize(ctx, payload["id"])
    if proposal["status"] != "pending" or ctx.now >= timestamp(
        proposal["expires_at"], "expires_at"
    ):
        raise DomainError("proposal_expired")
    if action == "reject":
        if "feedback" in payload:
            from .semantic_feedback import capture

            feedback = capture(ctx, proposal, payload["feedback"])
            proposal["feedback_id"] = feedback["id"]
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
    if not isinstance(payload, dict) or not isinstance(result, dict):
        raise DomainError("forbidden")
    if action == "feedback_purge":
        from .semantic_feedback import project

        fields(payload, {"id", "confirmed"}, {"id", "confirmed"})
        # Purging never recreates data on retry, and a later account incarnation
        # cannot replay another identity's deletion receipt.
        if (
            payload["confirmed"] is not True
            or result.get("id") != payload["id"]
            or result.get("status") != "purged"
            or strict_revision(result.get("actor_revision"))
            != strict_revision(ctx.actor.get("revision"))
            or result.get("role") != ctx.actor.get("role")
        ):
            raise DomainError("forbidden")
        private = project(ctx.state, ctx.actor)
        if not private["available"] or any(
            row["id"] == payload["id"] for row in private["records"]
        ):
            raise DomainError("conflict")
        return
    if action not in {"confirm", "reject"}:
        raise DomainError("unknown_action")
    fields(payload, {"id", "feedback"} if action == "reject" else {"id"}, {"id"})
    proposal = _authorize(ctx, payload["id"])
    expected_status = "applied" if action == "confirm" else "rejected"
    if proposal.get("status") != expected_status or result != _receipt(proposal):
        raise DomainError("conflict")
    if "feedback" in payload:
        from .semantic_feedback import project

        private = project(ctx.state, ctx.actor)
        if not private["available"] or not any(
            record["id"] == proposal.get("feedback_id") for record in private["records"]
        ):
            raise DomainError("conflict")
