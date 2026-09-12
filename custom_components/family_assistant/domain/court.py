"""Reversible score events. No fixed family or consequence is encoded."""

from __future__ import annotations

from . import court_weekly, rewards
from .context import Context
from .validation import DomainError, fields, number, text
from .validation import revision as strict_revision


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if action.startswith("reward_"):
        return rewards.handle(ctx, action, payload)
    if action == "configure":
        return court_weekly.configure(ctx, payload)
    if ctx.actor["role"] == "guest":
        raise DomainError("forbidden")
    if action == "reverse_source":
        return _reverse_source(ctx, payload)
    if action == "award":
        ctx.require_parent()
        fields(payload, {"member", "points", "reason"}, {"member", "points", "reason"})
        member = ctx.member(payload["member"])
        if member["role"] == "guest":
            raise DomainError("invalid_field", "member")
        points = number(payload["points"], "points", -100, 100)
        if not points or not points.is_integer():
            raise DomainError("invalid_field", "points")
        record = {
            "id": ctx.identifier("C"),
            "member": member["id"],
            "points": int(points),
            "reason": text(payload["reason"], "reason"),
            "actor": ctx.actor_id,
            "created_at": ctx.now.isoformat(),
            "status": "active",
            "source": "manual",
        }
        ctx.state["court"][record["id"]] = ctx.touch(record)
        return record
    if action not in {"appeal", "reverse", "resolve_appeal"}:
        raise DomainError("unknown_action")
    allowed = {"id", "revision", "reason"} | ({"decision"} if action == "resolve_appeal" else set())
    fields(
        payload,
        allowed,
        {"id", "revision", "reason"} | ({"decision"} if action == "resolve_appeal" else set()),
    )
    record = ctx.record("court", payload["id"], strict_revision(payload["revision"]))
    if action == "appeal":
        if record["member"] != ctx.actor_id and not ctx.privileged:
            raise DomainError("forbidden")
        if record["status"] != "active":
            raise DomainError("invalid_transition")
        previous = record.get("appeal")
        if previous and previous.get("status", "pending") == "pending":
            raise DomainError("invalid_transition")
        if previous:
            record.setdefault("previous_appeals", []).append(previous)
        record["appeal"] = {
            "reason": text(payload["reason"], "reason"),
            "actor": ctx.actor_id,
            "at": ctx.now.isoformat(),
            "status": "pending",
        }
        ctx.notify("parents", "court_appeal", {"id": record["id"]})
    elif action in {"reverse", "resolve_appeal"}:
        ctx.require_parent()
        if record["status"] != "active":
            raise DomainError("invalid_transition")
        appeal = record.get("appeal")
        pending = appeal and appeal.get("status", "pending") == "pending"
        decision = payload.get("decision", "reverse")
        if action == "resolve_appeal":
            if not pending:
                raise DomainError("invalid_transition")
            if decision not in {"uphold", "reverse"}:
                raise DomainError("invalid_field", "decision")
        if pending:
            court_weekly.require_independent_reviewer(ctx, record)
        resolution = {
            "reason": text(payload["reason"], "reason"),
            "actor": ctx.actor_id,
            "at": ctx.now.isoformat(),
        }
        if decision == "reverse":
            record["status"] = "reversed"
            record["reversal"] = resolution
        if pending:
            appeal.update(status="resolved", decision=decision, resolution=resolution)
            for event in ctx.state["outbox"].values():
                if (
                    event["key"] == "court_appeal"
                    and event["data"].get("id") == record["id"]
                    and event["state"] in {"pending", "awaiting_channel"}
                ):
                    event["state"] = "superseded"
            ctx.notify(
                record["member"],
                "court_appeal_resolved",
                {"id": record["id"], "decision": decision},
            )
    else:
        raise DomainError("unknown_action")
    return ctx.touch(record)


def _reverse_source(ctx: Context, payload: dict) -> dict:
    """Correct one exact automatic event using the ordinary reversal review rules.

    This does not certify task completion, alter an alarm or infer another source
    from a member name. The original automatic event remains in the ledger.
    """
    ctx.require_parent()
    required = {"source", "source_id", "member", "revision", "reason"}
    fields(payload, required, required)
    source = payload["source"]
    if not isinstance(source, str) or source not in {"task", "alarm"}:
        raise DomainError("invalid_field", "source")
    source_id = text(payload["source_id"], "source_id", 70)
    member = text(payload["member"], "member", 80)
    record = ctx.record("court", f"{source}:{source_id}", strict_revision(payload["revision"]))
    reference = "task_id" if source == "task" else "run_id"
    if (
        record.get("source") != source
        or record.get("actor") != "system"
        or record.get("member") != member
        or type(record.get("points")) is not int
        or record["points"] >= 0
        or not isinstance(record.get("reason_data"), dict)
        or record.get("reason_data", {}).get(reference) != source_id
    ):
        raise DomainError("invalid_field", "source_id")
    result = handle(
        ctx,
        "reverse",
        {
            "id": record["id"],
            "revision": record["revision"],
            "reason": payload["reason"],
        },
    )
    result["reversal"]["source_reference"] = {"source": source, "source_id": source_id}
    return result
