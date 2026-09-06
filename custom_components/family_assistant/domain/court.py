"""Reversible score events. No fixed family or consequence is encoded."""

from __future__ import annotations

from .context import Context
from .validation import DomainError, fields, number, text


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if action == "award":
        ctx.require_parent()
        fields(payload, {"member", "points", "reason"}, {"member", "points", "reason"})
        member = ctx.member(payload["member"])
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
    fields(payload, {"id", "revision", "reason"}, {"id", "reason"})
    record = ctx.record("court", payload["id"], payload.get("revision"))
    if action == "appeal":
        if record["member"] != ctx.actor_id and not ctx.privileged:
            raise DomainError("forbidden")
        if record["status"] != "active":
            raise DomainError("invalid_transition")
        record["appeal"] = {
            "reason": text(payload["reason"], "reason"),
            "actor": ctx.actor_id,
            "at": ctx.now.isoformat(),
        }
        ctx.notify("parents", "court_appeal", {"id": record["id"]})
    elif action == "reverse":
        ctx.require_parent()
        if record["status"] != "active":
            raise DomainError("invalid_transition")
        record["status"] = "reversed"
        record["reversal"] = {
            "reason": text(payload["reason"], "reason"),
            "actor": ctx.actor_id,
            "at": ctx.now.isoformat(),
        }
    else:
        raise DomainError("unknown_action")
    return ctx.touch(record)
