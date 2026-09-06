"""Shopping records, quantities and approval; separate from tasks."""

from __future__ import annotations

from .context import Context
from .validation import DomainError, fields, number, text


def handle(ctx: Context, action: str, payload: dict) -> dict:
    if action.startswith("series_"):
        from .shopping_series import handle as series_command

        return series_command(ctx, action, payload)
    if ctx.actor["role"] == "guest":
        raise DomainError("forbidden")
    if action == "add":
        fields(
            payload, {"name", "quantity", "unit", "category", "store", "note", "buyer"}, {"name"}
        )
        buyer = payload.get("buyer")
        if buyer:
            ctx.member(buyer)
        item = {
            "id": ctx.identifier("S"),
            "name": text(payload["name"], "name", 200),
            "quantity": number(payload.get("quantity", 1), "quantity", 0.001),
            "purchased": 0.0,
            "unit": str(payload.get("unit", ""))[:32],
            "category": str(payload.get("category", ""))[:80],
            "store": str(payload.get("store", ""))[:80],
            "note": str(payload.get("note", ""))[:500],
            "buyer": buyer,
            "creator": ctx.actor_id,
            "created_at": ctx.now.isoformat(),
            "status": "pending" if ctx.actor["role"] == "child" else "approved",
        }
        ctx.state["shopping"][item["id"]] = ctx.touch(item)
        if item["status"] == "pending":
            ctx.notify("parents", "shopping_approval", {"id": item["id"]})
        return item
    fields(payload, {"id", "revision", "quantity", "unit"}, {"id"})
    item = ctx.record("shopping", payload["id"], payload.get("revision"))
    if action in {"approve", "reject", "archive"}:
        ctx.require_parent()
        if action != "archive" and item["status"] != "pending":
            raise DomainError("invalid_transition")
        item["status"] = {"approve": "approved", "reject": "rejected", "archive": "archived"}[
            action
        ]
    elif action == "purchase":
        if item["status"] != "approved":
            raise DomainError("invalid_transition")
        if payload.get("unit", item["unit"]) != item["unit"]:
            raise DomainError("unit_mismatch")
        remaining = round(item["quantity"] - item["purchased"], 6)
        amount = number(payload.get("quantity", remaining), "quantity", 0.000001, remaining)
        item["purchased"] = round(item["purchased"] + amount, 6)
        if item["purchased"] >= item["quantity"]:
            item["status"] = "purchased"
            item["purchased_at"] = ctx.now.isoformat()
    else:
        raise DomainError("unknown_action")
    return ctx.touch(item)
