"""Reviewable shopping-list transfers from published weekly meal plans.

Ingredient quantities are manual totals.  Matching is normalized-name plus exact-unit;
this module never converts units, changes pantry stock, or performs external effects.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from ..const import PRIVILEGED
from . import shopping
from .context import Context
from .validation import DomainError, fields, text
from .validation import revision as strict_revision

OPEN_SHOPPING = frozenset({"pending", "approved"})
TERMINAL_PROPOSALS = frozenset({"accepted", "covered"})
COMMAND_FIELDS = frozenset({"id", "revision"})
MAXIMUM = Decimal("1000000")
MILLI = Decimal("0.001")
MICRO = Decimal("0.000001")


def _require_access(ctx: Context) -> None:
    current = ctx.state.get("members", {}).get(ctx.actor_id, {})
    if (
        not current.get("active", False)
        or current.get("role") not in PRIVILEGED
        or ctx.actor.get("role") != current.get("role")
    ):
        raise DomainError("forbidden")
    modules = ctx.state.get("settings", {}).get("modules", [])
    if "pantry" not in modules or "shopping" not in modules:
        raise DomainError("module_disabled")


def _pantry(state: dict) -> dict:
    pantry = state.get("pantry", {})
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    return pantry


def _bucket(state: dict) -> dict:
    value = _pantry(state).get("meal_shopping", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "meal_shopping")
    return value


def _mutable_bucket(ctx: Context) -> dict:
    pantry = ctx.state.get("pantry")
    if pantry is None:
        pantry = {}
        ctx.state["pantry"] = pantry
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    value = pantry.get("meal_shopping")
    if value is None:
        value = {}
        pantry["meal_shopping"] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "meal_shopping")
    return value


def _mapping(state: dict, name: str, *, pantry: bool = False) -> dict:
    owner = _pantry(state) if pantry else state
    value = owner.get(name, {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _decimal(value, field: str, *, places: Decimal, minimum: Decimal = Decimal(0)) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainError("invalid_field", field)
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise DomainError("invalid_field", field) from None
    if not result.is_finite() or not minimum <= result <= MAXIMUM:
        raise DomainError("invalid_field", field)
    if result.quantize(places) != result:
        raise DomainError("invalid_field", field)
    return result


def _bounded_total(value: Decimal, field: str) -> Decimal:
    if not value.is_finite() or not Decimal(0) <= value <= MAXIMUM:
        raise DomainError("invalid_field", field)
    return value


def _finite_total(value: Decimal, field: str) -> Decimal:
    if not value.is_finite() or value < 0:
        raise DomainError("invalid_field", field)
    return value


def _json_quantity(value: Decimal):
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _canonical(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _plan(state: dict, plan_id, plan_revision) -> dict:
    plans = _mapping(state, "meal_plans", pantry=True)
    plan_id = text(plan_id, "id", 80)
    plan = plans.get(plan_id)
    if plan is None:
        raise DomainError("not_found")
    if strict_revision(plan_revision) != plan.get("revision"):
        raise DomainError("conflict")
    if plan.get("status") != "published":
        raise DomainError("invalid_transition")
    return plan


def _ingredient_totals(plan: dict) -> dict[tuple[str, str], dict]:
    totals: dict[tuple[str, str], dict] = {}
    entries = plan.get("entries")
    if not isinstance(entries, list):
        raise DomainError("invalid_field", "entries")
    for entry_index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("ingredients"), list):
            raise DomainError("invalid_field", f"entries[{entry_index}].ingredients")
        for ingredient_index, ingredient in enumerate(entry["ingredients"]):
            field = f"entries[{entry_index}].ingredients[{ingredient_index}]"
            if not isinstance(ingredient, dict):
                raise DomainError("invalid_field", field)
            name = text(ingredient.get("name"), f"{field}.name", 120)
            unit = text(ingredient.get("unit"), f"{field}.unit", 24)
            quantity = _decimal(
                ingredient.get("quantity"),
                f"{field}.quantity",
                places=MILLI,
                minimum=MILLI,
            )
            key = (shopping.normalized_name(name), unit)
            if key not in totals:
                totals[key] = {"name": name, "unit": unit, "required": Decimal(0)}
            totals[key]["required"] = _bounded_total(totals[key]["required"] + quantity, "required")
    return totals


def _normalized_record_name(record: dict) -> str | None:
    name = record.get("name")
    return shopping.normalized_name(name) if isinstance(name, str) else None


def _snapshot(state: dict, plan: dict) -> tuple[list[dict], str]:
    totals = _ingredient_totals(plan)
    pantry_records = _mapping(state, "items", pantry=True)
    shopping_records = _mapping(state, "shopping")
    stock_by_key = {key: Decimal(0) for key in totals}
    open_by_key = {key: Decimal(0) for key in totals}
    stock_snapshot = []
    shopping_snapshot = []

    for record in pantry_records.values():
        if not isinstance(record, dict) or record.get("status") != "active":
            continue
        key = (_normalized_record_name(record), record.get("unit"))
        if key not in totals:
            continue
        record_id = text(record.get("id"), "id", 80)
        record_revision = strict_revision(record.get("revision"))
        quantity = _decimal(record.get("quantity"), "quantity", places=MILLI)
        stock_by_key[key] = _finite_total(stock_by_key[key] + quantity, "stock")
        stock_snapshot.append(
            {
                "key": [key[0], key[1]],
                "id": record_id,
                "revision": record_revision,
                "quantity": _canonical(quantity),
                "status": "active",
            }
        )

    for record in shopping_records.values():
        if not isinstance(record, dict) or record.get("status") not in OPEN_SHOPPING:
            continue
        key = (_normalized_record_name(record), record.get("unit"))
        if key not in totals:
            continue
        record_id = text(record.get("id"), "id", 80)
        record_revision = strict_revision(record.get("revision"))
        quantity = _decimal(record.get("quantity"), "quantity", places=MICRO)
        purchased = _decimal(record.get("purchased", 0), "purchased", places=MICRO)
        if purchased > quantity:
            raise DomainError("invalid_field", "purchased")
        remaining = quantity - purchased
        open_by_key[key] = _finite_total(open_by_key[key] + remaining, "open_shopping")
        shopping_snapshot.append(
            {
                "key": [key[0], key[1]],
                "id": record_id,
                "revision": record_revision,
                "quantity": _canonical(quantity),
                "purchased": _canonical(purchased),
                "status": record["status"],
            }
        )

    lines = []
    plan_snapshot = []
    for key in sorted(totals):
        required = totals[key]["required"]
        stock = stock_by_key[key]
        open_shopping = open_by_key[key]
        deficit = _bounded_total(max(Decimal(0), required - stock - open_shopping), "deficit")
        quantity = deficit.quantize(MILLI, rounding=ROUND_CEILING) if deficit else Decimal(0)
        lines.append(
            {
                "name": totals[key]["name"],
                "unit": key[1],
                "required": _json_quantity(required),
                "stock": _json_quantity(stock),
                "open_shopping": _json_quantity(open_shopping),
                "deficit": _json_quantity(deficit),
                "quantity": _json_quantity(quantity),
            }
        )
        plan_snapshot.append({"name": key[0], "unit": key[1], "required": _canonical(required)})

    fingerprint_value = {
        "plan": {
            "id": plan["id"],
            "revision": plan["revision"],
            "status": plan["status"],
            "ingredients": plan_snapshot,
        },
        "stock": sorted(stock_snapshot, key=lambda item: item["id"]),
        "shopping": sorted(shopping_snapshot, key=lambda item: item["id"]),
    }
    encoded = json.dumps(
        fingerprint_value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return lines, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _history(ctx: Context, record: dict, action: str) -> dict:
    history = record.setdefault("history", [])
    if not isinstance(history, list):
        raise DomainError("invalid_field", "history")
    history.append({"actor": ctx.actor_id, "at": ctx.now.isoformat(), "action": action})
    return ctx.touch(record)


def _terminal(proposals: dict, plan_id: str) -> dict | None:
    return next(
        (
            proposal
            for proposal in proposals.values()
            if isinstance(proposal, dict)
            and proposal.get("source_plan_id") == plan_id
            and proposal.get("status") in TERMINAL_PROPOSALS
        ),
        None,
    )


def _prepare(ctx: Context, payload: dict) -> dict:
    fields(payload, COMMAND_FIELDS, COMMAND_FIELDS)
    plan_id = text(payload["id"], "id", 80)
    strict_revision(payload["revision"])
    proposals = _bucket(ctx.state)
    terminal = _terminal(proposals, plan_id)
    if terminal is not None:
        return terminal

    plan = _plan(ctx.state, plan_id, payload["revision"])
    lines, fingerprint = _snapshot(ctx.state, plan)
    for proposal in proposals.values():
        if not isinstance(proposal, dict):
            raise DomainError("invalid_field", "meal_shopping")
        if (
            proposal.get("source_plan_id") == plan_id
            and proposal.get("status") == "open"
            and proposal.get("input_fingerprint") == fingerprint
        ):
            return proposal

    proposals = _mutable_bucket(ctx)
    for proposal in proposals.values():
        if proposal.get("source_plan_id") == plan_id and proposal.get("status") == "open":
            proposal["status"] = "superseded"
            _history(ctx, proposal, "superseded")
    record = {
        "id": ctx.identifier("MS"),
        "source_plan_id": plan["id"],
        "source_revision": plan["revision"],
        "plan_title": plan["title"],
        "week_start": plan["week_start"],
        "lines": lines,
        "status": "open",
        "created_by": ctx.actor_id,
        "created_at": ctx.now.isoformat(),
        "input_fingerprint": fingerprint,
        "history": [],
    }
    proposals[record["id"]] = record
    return _history(ctx, record, "prepared")


def _proposal(state: dict, proposal_id, proposal_revision) -> dict:
    proposal_id = text(proposal_id, "id", 80)
    proposal = _bucket(state).get(proposal_id)
    if proposal is None:
        raise DomainError("not_found")
    if strict_revision(proposal_revision) != proposal.get("revision"):
        raise DomainError("conflict")
    return proposal


def _accept(ctx: Context, payload: dict) -> dict:
    fields(payload, COMMAND_FIELDS, COMMAND_FIELDS)
    proposal = _proposal(ctx.state, payload["id"], payload["revision"])
    if proposal.get("status") != "open":
        raise DomainError("invalid_transition")
    if _terminal(_bucket(ctx.state), proposal["source_plan_id"]) is not None:
        raise DomainError("invalid_transition")
    plan = _plan(ctx.state, proposal["source_plan_id"], proposal["source_revision"])
    lines, fingerprint = _snapshot(ctx.state, plan)
    if fingerprint != proposal.get("input_fingerprint") or lines != proposal.get("lines"):
        raise DomainError("conflict")

    result_lines = deepcopy(lines)
    transfer_count = 0
    for line in result_lines:
        if line["quantity"] <= 0:
            continue
        created = shopping.handle(
            ctx,
            "add",
            {"name": line["name"], "unit": line["unit"], "quantity": line["quantity"]},
        )
        created["meal_plan_id"] = plan["id"]
        created["meal_shopping_id"] = proposal["id"]
        line["shopping_id"] = created["id"]
        transfer_count += 1

    proposal["lines"] = result_lines
    proposal["transfer_count"] = transfer_count
    proposal["status"] = "accepted" if transfer_count else "covered"
    return _history(ctx, proposal, proposal["status"])


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Prepare or accept one parent-reviewed meal shopping-list proposal."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    _require_access(ctx)
    if action == "meal_shop_prepare":
        return _prepare(ctx, payload)
    if action == "meal_shop_accept":
        return _accept(ctx, payload)
    raise DomainError("unknown_action")


def view(state: dict, actor: dict) -> list[dict]:
    """Return parent-only proposals without internal input fingerprints."""
    current = state.get("members", {}).get(actor.get("id"), {})
    if not current.get("active", False) or current.get("role") not in PRIVILEGED:
        return []
    result = []
    for proposal in _bucket(state).values():
        item = deepcopy(proposal)
        item.pop("input_fingerprint", None)
        result.append(item)
    return result
