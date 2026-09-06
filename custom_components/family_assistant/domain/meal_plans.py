"""Weekly meal plans with explicit total ingredient quantities.

Ingredient quantities describe the total required for the entry's stated servings.
This domain does not scale, convert, infer safety, or mutate pantry/shopping state.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

from ..const import PRIVILEGED
from .context import Context
from .validation import DomainError, enum, fields, number, text
from .validation import revision as strict_revision

SLOTS = frozenset({"breakfast", "lunch", "dinner", "snack"})
SAVE_FIELDS = frozenset({"id", "revision", "week_start", "title", "entries", "note"})
PARENT_ONLY_FIELDS = frozenset(
    {
        "revision",
        "note",
        "history",
        "created_by",
        "created_at",
        "updated_at",
        "published_at",
        "archived_at",
    }
)


def _require_parent(ctx: Context) -> None:
    member = ctx.state.get("members", {}).get(ctx.actor_id, {})
    if not member.get("active", False) or member.get("role") not in PRIVILEGED:
        raise DomainError("forbidden")


def _bucket(state: dict) -> dict:
    pantry = state.get("pantry", {})
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    plans = pantry.get("meal_plans", {})
    if not isinstance(plans, dict):
        raise DomainError("invalid_field", "meal_plans")
    return plans


def _mutable_bucket(ctx: Context) -> dict:
    pantry = ctx.state.get("pantry")
    if pantry is None:
        pantry = {}
        ctx.state["pantry"] = pantry
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    plans = pantry.get("meal_plans")
    if plans is None:
        plans = {}
        pantry["meal_plans"] = plans
    if not isinstance(plans, dict):
        raise DomainError("invalid_field", "meal_plans")
    return plans


def _canonical_date(value, field: str) -> date:
    if not isinstance(value, str):
        raise DomainError("invalid_field", field)
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise DomainError("invalid_field", field) from None
    if result.isoformat() != value:
        raise DomainError("invalid_field", field)
    return result


def _week_start(value) -> str:
    result = _canonical_date(value, "week_start")
    if result.weekday() != 0:
        raise DomainError("invalid_field", "week_start")
    try:
        result + timedelta(days=6)
    except OverflowError:
        raise DomainError("invalid_field", "week_start") from None
    return result.isoformat()


def _optional_note(value) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise DomainError("invalid_field", "note")
    return value.strip()


def _strict_int(value, field: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise DomainError("invalid_field", field)
    return value


def _quantity(value, field: str) -> float:
    result = number(value, field, 0, 1000000)
    rounded = round(result, 3)
    if result <= 0 or result != rounded:
        raise DomainError("invalid_field", field)
    return rounded


def _ingredients(value, entry_index: int) -> list[dict]:
    field = f"entries[{entry_index}].ingredients"
    if not isinstance(value, list) or len(value) > 20:
        raise DomainError("invalid_field", field)
    result = []
    for ingredient_index, ingredient in enumerate(value):
        prefix = f"{field}[{ingredient_index}]"
        if not isinstance(ingredient, dict):
            raise DomainError("invalid_field", prefix)
        fields(ingredient, {"name", "unit", "quantity"}, {"name", "unit", "quantity"})
        result.append(
            {
                "name": text(ingredient["name"], f"{prefix}.name", 120),
                "unit": text(ingredient["unit"], f"{prefix}.unit", 24),
                "quantity": _quantity(ingredient["quantity"], f"{prefix}.quantity"),
            }
        )
    return result


def _entries(value, week_start: str) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= 28:
        raise DomainError("invalid_field", "entries")
    first = date.fromisoformat(week_start)
    last = first + timedelta(days=6)
    result = []
    occupied = set()
    ingredient_count = 0
    for index, entry in enumerate(value):
        prefix = f"entries[{index}]"
        if not isinstance(entry, dict):
            raise DomainError("invalid_field", prefix)
        fields(
            entry,
            {"date", "slot", "title", "servings", "ingredients"},
            {"date", "slot", "title", "servings", "ingredients"},
        )
        entry_date = _canonical_date(entry["date"], f"{prefix}.date")
        if not first <= entry_date <= last:
            raise DomainError("invalid_field", f"{prefix}.date")
        slot = enum(entry["slot"], SLOTS, f"{prefix}.slot")
        identity = (entry_date.isoformat(), slot)
        if identity in occupied:
            raise DomainError("invalid_field", f"{prefix}.slot")
        occupied.add(identity)
        ingredients = _ingredients(entry["ingredients"], index)
        ingredient_count += len(ingredients)
        if ingredient_count > 100:
            raise DomainError("invalid_field", "ingredients")
        result.append(
            {
                "date": entry_date.isoformat(),
                "slot": slot,
                "title": text(entry["title"], f"{prefix}.title", 120),
                "servings": _strict_int(entry["servings"], f"{prefix}.servings", 1, 50),
                "ingredients": ingredients,
            }
        )
    return result


def _values(payload: dict, existing: dict | None = None) -> dict:
    existing = existing or {}
    week_start = _week_start(payload.get("week_start", existing.get("week_start")))
    return {
        "week_start": week_start,
        "title": text(payload.get("title", existing.get("title")), "title", 120),
        "entries": _entries(payload.get("entries", existing.get("entries")), week_start),
        "note": _optional_note(payload.get("note", existing.get("note", ""))),
    }


def _record(plans: dict, record_id, record_revision) -> dict:
    record_id = text(record_id, "id", 80)
    record = plans.get(record_id)
    if record is None:
        raise DomainError("not_found")
    if strict_revision(record_revision) != record.get("revision"):
        raise DomainError("conflict")
    return record


def _history(ctx: Context, record: dict, action: str, *, reason="", changes=None) -> dict:
    history = record.setdefault("history", [])
    if not isinstance(history, list):
        raise DomainError("invalid_field", "history")
    event = {"actor": ctx.actor_id, "at": ctx.now.isoformat(), "action": action}
    if reason:
        event["reason"] = reason
    if changes:
        event["changes"] = deepcopy(changes)
    history.append(event)
    return ctx.touch(record)


def _save(ctx: Context, payload: dict) -> dict:
    is_edit = "id" in payload
    fields(
        payload,
        SAVE_FIELDS,
        {"id", "revision"} if is_edit else {"week_start", "title", "entries"},
    )
    if not is_edit and "revision" in payload:
        raise DomainError("invalid_field", "revision")
    plans = _bucket(ctx.state)
    if not is_edit:
        values = _values(payload)
        plans = _mutable_bucket(ctx)
        record = {
            "id": ctx.identifier("MP"),
            **values,
            "status": "draft",
            "created_by": ctx.actor_id,
            "created_at": ctx.now.isoformat(),
            "history": [],
        }
        plans[record["id"]] = record
        return _history(ctx, record, "created", changes=values)

    record = _record(plans, payload["id"], payload["revision"])
    if record.get("status") == "archived":
        raise DomainError("invalid_transition")
    values = _values(payload, record)
    changes = {key: value for key, value in values.items() if record.get(key) != value}
    if not changes:
        raise DomainError("invalid_transition")
    record.update(values)
    if record.get("status") == "published":
        record["status"] = "draft"
        record.pop("published_at", None)
        changes["status"] = "draft"
    return _history(ctx, record, "edited", changes=changes)


def _publish(ctx: Context, payload: dict) -> dict:
    fields(payload, {"id", "revision"}, {"id", "revision"})
    plans = _bucket(ctx.state)
    record = _record(plans, payload["id"], payload["revision"])
    if record.get("status") != "draft":
        raise DomainError("invalid_transition")
    _values(record)
    if any(
        other.get("status") == "published"
        and other.get("week_start") == record["week_start"]
        and other.get("id") != record["id"]
        for other in plans.values()
    ):
        raise DomainError("conflict", "week_start")
    record["status"] = "published"
    record["published_at"] = ctx.now.isoformat()
    return _history(ctx, record, "published")


def _archive(ctx: Context, payload: dict) -> dict:
    fields(payload, {"id", "revision", "reason"}, {"id", "revision", "reason"})
    record = _record(_bucket(ctx.state), payload["id"], payload["revision"])
    if record.get("status") not in {"draft", "published"}:
        raise DomainError("invalid_transition")
    reason = text(payload["reason"], "reason", 500)
    record["status"] = "archived"
    record["archived_at"] = ctx.now.isoformat()
    return _history(ctx, record, "archived", reason=reason)


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Apply one parent-reviewed weekly menu command without external effects."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    _require_parent(ctx)
    if action == "meal_save":
        return _save(ctx, payload)
    if action == "meal_publish":
        return _publish(ctx, payload)
    if action == "meal_archive":
        return _archive(ctx, payload)
    raise DomainError("unknown_action")


def view(state: dict, actor: dict) -> list[dict]:
    """Return a pure role-filtered meal plan projection."""
    current = state.get("members", {}).get(actor.get("id"), {})
    if not current.get("active", False) or current.get("role") == "guest":
        return []
    parent = current.get("role") in PRIVILEGED
    result = []
    for record in _bucket(state).values():
        if not parent and record.get("status") != "published":
            continue
        item = deepcopy(record)
        if not parent:
            for field in PARENT_ONLY_FIELDS:
                item.pop(field, None)
        result.append(item)
    return result
