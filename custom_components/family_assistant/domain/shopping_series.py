"""Recurring shopping series generate approved shopping items on due dates."""

from __future__ import annotations

from ..const import PRIVILEGED
from . import recurrence, shopping
from .context import Context
from .gtin import normalize_gtin
from .validation import DomainError, fields, number, text, timestamp


def handle(ctx: Context, action: str, payload: dict) -> dict:
    ctx.require_parent()
    ctx.state.setdefault("shopping_series", {})

    if action == "series_enable":
        fields(payload, {"id", "enabled", "revision"}, {"id", "enabled", "revision"})
        if type(payload["revision"]) is not int or payload["revision"] < 1:
            raise DomainError("invalid_field", "revision")
        if type(payload["enabled"]) is not bool:
            raise DomainError("invalid_field", "enabled")
        item = ctx.record("shopping_series", payload["id"], payload["revision"])
        item["enabled"] = payload["enabled"]
        item["effective_at"] = ctx.now.isoformat()
        return ctx.touch(item)

    if action != "series_save":
        raise DomainError("unknown_action")

    fields(
        payload,
        {
            "id",
            "revision",
            "name",
            "quantity",
            "unit",
            "category",
            "store",
            "note",
            "buyer",
            "barcode",
            "rule",
            "enabled",
        },
        {"name", "rule"},
    )

    series_id = payload.get("id")
    revision = payload.get("revision")
    if "id" in payload:
        if type(revision) is not int or revision < 1:
            raise DomainError("invalid_field", "revision")
        existing = ctx.record("shopping_series", series_id, revision)
    else:
        if "revision" in payload:
            raise DomainError("invalid_field", "revision")
        existing = {}

    name = text(payload["name"], "name", 200)

    quantity_val = payload.get("quantity", existing.get("quantity", 1))
    quantity = number(quantity_val, "quantity", 0.001)

    for field_name, max_len in (
        ("unit", 32),
        ("category", 80),
        ("store", 80),
        ("note", 500),
    ):
        if field_name in payload and not isinstance(payload[field_name], str):
            raise DomainError("invalid_field", field_name)
        if field_name in payload and len(payload[field_name]) > max_len:
            raise DomainError("invalid_field", field_name)

    unit = payload.get("unit", existing.get("unit", ""))
    category = payload.get("category", existing.get("category", ""))
    store = payload.get("store", existing.get("store", ""))
    note = payload.get("note", existing.get("note", ""))
    barcode = normalize_gtin(payload.get("barcode", existing.get("barcode", "")))

    buyer = payload.get("buyer", existing.get("buyer"))
    if buyer is not None:
        if not isinstance(buyer, str):
            raise DomainError("invalid_field", "buyer")
        if ctx.member(buyer)["role"] == "guest":
            raise DomainError("invalid_field", "buyer")

    rule = recurrence.validate(payload["rule"])

    enabled = payload.get("enabled", existing.get("enabled", True))
    if type(enabled) is not bool:
        raise DomainError("invalid_field", "enabled")

    item = {
        **existing,
        "id": existing.get("id") or ctx.identifier("B"),
        "creator": existing.get("creator", ctx.actor_id),
        "name": name,
        "quantity": quantity,
        "unit": unit,
        "category": category,
        "store": store,
        "note": note,
        "buyer": buyer,
        "rule": rule,
        "enabled": enabled,
        "effective_at": ctx.now.isoformat(),
        "occurrences": existing.get("occurrences", {}),
    }

    if barcode or "barcode" in existing:
        item["barcode"] = barcode
    ctx.state["shopping_series"][item["id"]] = ctx.touch(item)
    return item


def _open_descendant(items: dict, item: dict) -> bool:
    """Merged records retain provenance; follow their live target without cycles."""
    seen = set()
    while item.get("status") == "merged":
        target = item.get("merged_into")
        if not isinstance(target, str) or target in seen or target not in items:
            # Corrupt/partial legacy provenance needs review, not more purchases.
            return True
        seen.add(target)
        item = items[target]
    return item.get("status") in {"pending", "approved"}


def tick(ctx: Context) -> None:
    if "shopping" not in ctx.state["settings"]["modules"]:
        return

    ctx.state.setdefault("shopping_series", {})
    ctx.state.setdefault("shopping", {})

    for series in ctx.state["shopping_series"].values():
        creator = ctx.state["members"].get(series["creator"], {})
        if (
            not series.get("enabled")
            or not creator.get("active")
            or creator.get("role") not in PRIVILEGED
        ):
            continue

        buyer = series.get("buyer")
        if buyer:
            buyer_member = ctx.state["members"].get(buyer, {})
            if not buyer_member.get("active") or buyer_member.get("role") == "guest":
                continue

        effective_dt = timestamp(series["effective_at"], "effective_at")

        for moment in recurrence.due(series["rule"], ctx.now, not_before=effective_dt):
            occurrence_id = moment.date().isoformat()
            if occurrence_id in series["occurrences"]:
                continue

            # Check open items for this series to prevent accumulation
            has_open_item = False
            for item in ctx.state["shopping"].values():
                if item.get("series_id") == series["id"] and _open_descendant(
                    ctx.state["shopping"], item
                ):
                    has_open_item = True
                    break

            if has_open_item:
                series["occurrences"][occurrence_id] = {
                    "state": "skipped_open",
                    "item_id": None,
                }
                ctx.touch(series)
                continue

            child_ctx = Context(
                ctx.state,
                creator,
                ctx.now,
                f"shopping_series:{series['id']}:{occurrence_id}",
            )

            shopping_payload = {
                "name": series["name"],
                "quantity": series["quantity"],
                "unit": series["unit"],
                "category": series["category"],
                "store": series["store"],
                "note": series["note"],
            }
            if series.get("buyer"):
                shopping_payload["buyer"] = series["buyer"]
            if series.get("barcode"):
                shopping_payload["barcode"] = series["barcode"]

            created_item = shopping.handle(child_ctx, "add", shopping_payload)
            created_item["series_id"] = series["id"]
            created_item["occurrence_id"] = occurrence_id

            series["occurrences"][occurrence_id] = {
                "state": "created",
                "item_id": created_item["id"],
            }
            ctx.touch(series)
