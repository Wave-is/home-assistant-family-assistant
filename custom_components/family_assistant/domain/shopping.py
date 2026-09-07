"""Shopping records, quantities and approval; separate from tasks."""

from __future__ import annotations

import math
import unicodedata

from .context import Context
from .shopping_history import record_event
from .validation import DomainError, fields, number, revision, text

TERMINAL_STATUSES = frozenset({"pending", "archived", "purchased", "merged"})
METADATA_LIMITS = {"category": 80, "store": 80, "note": 500}


def normalized_name(name: str) -> str:
    """Normalize item name: NFC, whitespace collapse, casefold."""
    normalized = unicodedata.normalize("NFC", name)
    collapsed = " ".join(normalized.split())
    return collapsed.casefold()


def _optional_text(value, field: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise DomainError("invalid_field", field)
    return value.strip()


def _buyer(ctx: Context, value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError("invalid_field", "buyer")
    member = ctx.member(value)
    if member["role"] == "guest":
        raise DomainError("invalid_field", "buyer")
    if ctx.actor["role"] == "child" and member["id"] != ctx.actor_id:
        raise DomainError("forbidden")
    return member["id"]


def _metadata(ctx: Context, payload: dict, *, existing=None) -> dict:
    result = {}
    for field, maximum in METADATA_LIMITS.items():
        value = payload[field] if field in payload else (existing or {}).get(field, "")
        result[field] = _optional_text(value, field, maximum)
    value = payload["buyer"] if "buyer" in payload else (existing or {}).get("buyer")
    result["buyer"] = _buyer(ctx, value)
    return result


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
        metadata = _metadata(ctx, payload)
        unit = _optional_text(payload.get("unit", ""), "unit", 32)
        item = {
            "id": ctx.identifier("S"),
            "name": text(payload["name"], "name", 200),
            "quantity": round(number(payload.get("quantity", 1), "quantity", 0.001), 6),
            "purchased": 0.0,
            "unit": unit,
            **metadata,
            "creator": ctx.actor_id,
            "created_at": ctx.now.isoformat(),
            "status": "pending" if ctx.actor["role"] == "child" else "approved",
            "history": [],
        }
        ctx.state["shopping"][item["id"]] = ctx.touch(item)
        record_event(
            ctx,
            item["id"],
            "add",
            {
                "quantity": item["quantity"],
                "unit": item["unit"],
                "status": item["status"],
            },
        )
        if item["status"] == "pending":
            ctx.notify("parents", "shopping_approval", {"id": item["id"]})
        return item

    if action == "edit":
        fields(
            payload,
            {"id", "revision", "name", "category", "store", "note", "buyer"},
            {"id", "revision", "name", "category", "store", "note", "buyer"},
        )
        item = ctx.record("shopping", payload["id"], revision(payload["revision"]))
        if item.get("status") not in {"pending", "approved"}:
            raise DomainError("invalid_transition")
        role = ctx.actor["role"]
        allowed = role in {"owner", "parent"} or (
            role == "adult" and item.get("status") == "approved"
        )
        if role == "child":
            allowed = item.get("status") == "pending" and item.get("creator") == ctx.actor_id
        if not allowed:
            raise DomainError("forbidden")
        replacement = {
            "name": text(payload["name"], "name", 200),
            **_metadata(ctx, payload, existing=item),
        }
        changed = [field for field, value in replacement.items() if item.get(field) != value]
        if not changed:
            raise DomainError("invalid_transition")
        item.update(replacement)
        ctx.touch(item)
        record_event(ctx, item["id"], "edit", {"fields": changed})
        return item

    if action == "merge":
        ctx.require_parent()
        fields(payload, {"id", "revision", "sources"}, {"id", "revision", "sources"})

        target_id = text(payload.get("id"), "id", 80)
        target_rev = revision(payload["revision"])

        sources_raw = payload.get("sources")
        if not isinstance(sources_raw, list):
            raise DomainError("invalid_field", "sources")
        if not (1 <= len(sources_raw) <= 19):
            raise DomainError("invalid_field", "sources")

        target_item = ctx.record("shopping", target_id, target_rev)

        # Validate target status and remaining quantity
        if target_item.get("status") != "approved":
            raise DomainError("invalid_transition", "status")

        target_qty = number(target_item.get("quantity", 0.0), "quantity", 0.001, 1000000.0)
        target_purchased = number(target_item.get("purchased", 0.0), "purchased", 0.0, 1000000.0)
        target_remaining = round(target_qty - target_purchased, 6)
        if target_remaining <= 0:
            raise DomainError("invalid_transition", "quantity")

        target_norm_name = normalized_name(target_item.get("name", ""))
        target_unit = target_item.get("unit", "")
        target_category = target_item.get("category", "")
        target_store = target_item.get("store", "")
        target_note = target_item.get("note", "")
        target_buyer = target_item.get("buyer")

        source_items = []
        seen_source_ids = {target_id}

        quantities = [target_qty]
        purchased_amounts = [target_purchased]

        for idx, src in enumerate(sources_raw):
            if not isinstance(src, dict):
                raise DomainError("invalid_field", f"sources[{idx}]")
            fields(src, {"id", "revision"}, {"id", "revision"})
            src_id = text(src.get("id"), "id", 80)
            src_rev = revision(src["revision"])

            if src_id in seen_source_ids:
                # Sources must be distinct and not include target
                raise DomainError("invalid_field", "sources")
            seen_source_ids.add(src_id)

            src_item = ctx.record("shopping", src_id, src_rev)

            # Check status
            src_status = src_item.get("status")
            if src_status in TERMINAL_STATUSES or src_status != "approved":
                raise DomainError("invalid_transition", "status")

            # Check remaining quantity
            src_qty = number(src_item.get("quantity", 0.0), "quantity", 0.001, 1000000.0)
            src_purchased = number(src_item.get("purchased", 0.0), "purchased", 0.0, 1000000.0)
            src_remaining = round(src_qty - src_purchased, 6)
            if src_remaining <= 0:
                raise DomainError("invalid_transition", "quantity")

            # Check name match (normalized: NFC, whitespace collapse, casefold)
            if normalized_name(src_item.get("name", "")) != target_norm_name:
                raise DomainError("conflict", "name")

            # EXACT unit match
            if src_item.get("unit", "") != target_unit:
                raise DomainError("unit_mismatch", "unit")

            # EXACT category/store/note/buyer match
            if src_item.get("category", "") != target_category:
                raise DomainError("conflict", "category")
            if src_item.get("store", "") != target_store:
                raise DomainError("conflict", "store")
            if src_item.get("note", "") != target_note:
                raise DomainError("conflict", "note")
            if src_item.get("buyer") != target_buyer:
                raise DomainError("conflict", "buyer")

            quantities.append(src_qty)
            purchased_amounts.append(src_purchased)
            source_items.append(src_item)

        total_quantity = round(math.fsum(quantities), 6)
        total_purchased = round(math.fsum(purchased_amounts), 6)

        # Check finite bounded 1e6 and open remaining
        number(total_quantity, "quantity", 0.001, 1000000.0)
        number(total_purchased, "purchased", 0.0, 1000000.0)
        if round(total_quantity - total_purchased, 6) <= 0:
            raise DomainError("invalid_transition", "quantity")

        merged_from = list(target_item.get("merged_from", []))
        for src_item in source_items:
            merged_from.append(src_item["id"])
            src_item["status"] = "merged"
            src_item["merged_into"] = target_id
            ctx.touch(src_item)
            record_event(
                ctx,
                src_item["id"],
                "merge",
                {
                    "merged_into": target_id,
                },
            )

        target_item["quantity"] = total_quantity
        target_item["purchased"] = total_purchased
        target_item["merged_from"] = merged_from
        ctx.touch(target_item)
        record_event(
            ctx,
            target_id,
            "merge",
            {
                "sources": [src["id"] for src in source_items],
                "quantity": total_quantity,
                "purchased": total_purchased,
            },
        )
        return target_item

    if action not in {"approve", "reject", "archive", "purchase"}:
        raise DomainError("unknown_action")
    fields(payload, {"id", "revision", "quantity", "unit"}, {"id", "revision"})
    item = ctx.record("shopping", payload["id"], revision(payload["revision"]))
    if action in {"approve", "reject", "archive"}:
        ctx.require_parent()
        if action == "archive":
            if item["status"] in {"archived", "merged"}:
                raise DomainError("invalid_transition")
        elif item["status"] != "pending":
            raise DomainError("invalid_transition")
        item["status"] = {"approve": "approved", "reject": "rejected", "archive": "archived"}[
            action
        ]
        ctx.touch(item)
        record_event(
            ctx,
            item["id"],
            action,
            {
                "status": item["status"],
            },
        )
    elif action == "purchase":
        if item["status"] != "approved":
            raise DomainError("invalid_transition")
        if payload.get("unit", item["unit"]) != item["unit"]:
            raise DomainError("unit_mismatch")
        remaining = round(item["quantity"] - item["purchased"], 6)
        amount = round(
            number(payload.get("quantity", remaining), "quantity", 0.000001, remaining), 6
        )
        item["purchased"] = round(item["purchased"] + amount, 6)
        detail = {
            "amount": amount,
            "purchased": item["purchased"],
            "remaining": round(item["quantity"] - item["purchased"], 6),
        }
        if item["purchased"] >= round(item["quantity"], 6):
            item["status"] = "purchased"
            item["purchased_at"] = ctx.now.isoformat()
            detail["status"] = "purchased"
        ctx.touch(item)
        record_event(ctx, item["id"], "purchase", detail)
    return item
