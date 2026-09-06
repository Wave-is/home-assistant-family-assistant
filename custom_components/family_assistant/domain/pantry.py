"""Local pantry inventory and reviewable shopping suggestions."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..const import PRIVILEGED
from . import dietary_profiles, meal_plans, meal_shopping, pantry_expiry, shopping
from .context import Context
from .validation import DomainError, fields, number, text, timestamp

ITEM_FIELDS = {
    "id",
    "revision",
    "name",
    "unit",
    "quantity",
    "minimum_quantity",
    "category",
    "location",
    "note",
    "expires_on",
    "reason",
}
METADATA_LIMITS = {"category": 80, "location": 80, "note": 500}
OPEN_SHOPPING = frozenset({"pending", "approved"})


def _bucket(state: dict, name: str) -> dict:
    pantry = state.get("pantry", {})
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    value = pantry.get(name, {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _mutable_bucket(ctx: Context, name: str) -> dict:
    pantry = ctx.state.get("pantry")
    if pantry is None:
        pantry = {}
        ctx.state["pantry"] = pantry
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    value = pantry.get(name)
    if value is None:
        value = {}
        pantry[name] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _require_roles(ctx: Context, roles: set[str] | frozenset[str]) -> None:
    current = ctx.state.get("members", {}).get(ctx.actor_id, {})
    if not current.get("active", False) or current.get("role") not in roles:
        raise DomainError("forbidden")


def _revision(value) -> int:
    if type(value) is not int or not 1 <= value <= 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    return value


def _quantity(value, field: str) -> float:
    result = number(value, field, 0, 1000000)
    rounded = round(result, 3)
    if result != rounded:
        raise DomainError("invalid_field", field)
    return rounded


def _metadata(value, field: str) -> str:
    if not isinstance(value, str) or len(value) > METADATA_LIMITS[field]:
        raise DomainError("invalid_field", field)
    return value.strip()


def _expiry(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError("invalid_field", "expires_on")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise DomainError("invalid_field", "expires_on") from None
    if parsed.isoformat() != value:
        raise DomainError("invalid_field", "expires_on")
    return value


def _record(bucket: dict, record_id, revision) -> dict:
    record_id = text(record_id, "id", 80)
    record = bucket.get(record_id)
    if record is None:
        raise DomainError("not_found")
    if record.get("revision") != _revision(revision):
        raise DomainError("conflict")
    return record


def _history(ctx: Context, record: dict, action: str, *, reason="", changes=None) -> dict:
    history = record.setdefault("history", [])
    if not isinstance(history, list):
        raise DomainError("invalid_field", "history")
    entry = {"actor": ctx.actor_id, "at": ctx.now.isoformat(), "action": action}
    if reason:
        entry["reason"] = reason
    if changes:
        entry["changes"] = deepcopy(changes)
    history.append(entry)
    return ctx.touch(record)


def _deficit(item: dict) -> float:
    return round(item["minimum_quantity"] - item["quantity"], 3)


def _matching_shopping(state: dict, item: dict) -> dict | None:
    target_name = shopping.normalized_name(item["name"])
    for candidate in state.get("shopping", {}).values():
        if candidate.get("status") not in OPEN_SHOPPING:
            continue
        quantity = candidate.get("quantity")
        purchased = candidate.get("purchased", 0)
        if (
            isinstance(quantity, bool)
            or isinstance(purchased, bool)
            or not isinstance(quantity, (int, float))
            or not isinstance(purchased, (int, float))
            or quantity <= purchased
        ):
            continue
        if candidate.get("unit", "") != item["unit"]:
            continue
        name = candidate.get("name")
        if isinstance(name, str) and shopping.normalized_name(name) == target_name:
            return candidate
    return None


def _change_suggestion(
    ctx: Context, suggestion: dict, status: str, *, history_reason="", **extra
) -> None:
    suggestion.update(status=status, **extra)
    _history(ctx, suggestion, status, reason=history_reason, changes=extra)


def _supersede_item_suggestions(ctx: Context, item_id: str) -> None:
    for suggestion in _bucket(ctx.state, "suggestions").values():
        if suggestion.get("pantry_id") == item_id and suggestion.get("status") == "open":
            _change_suggestion(ctx, suggestion, "superseded")


def _save_item(ctx: Context, payload: dict) -> dict:
    _require_roles(ctx, PRIVILEGED)
    is_edit = "id" in payload
    required = (
        {"id", "revision"}
        if is_edit
        else {
            "name",
            "unit",
            "quantity",
            "minimum_quantity",
        }
    )
    fields(payload, ITEM_FIELDS, required)
    if not is_edit and "revision" in payload:
        raise DomainError("invalid_field", "revision")
    if is_edit and not (payload.keys() - {"id", "revision", "reason"}):
        raise DomainError("invalid_field", "item")

    items = _bucket(ctx.state, "items")
    existing = _record(items, payload["id"], payload["revision"]) if is_edit else {}
    if existing and existing.get("status") != "active":
        raise DomainError("invalid_transition")

    value = {
        "name": text(payload.get("name", existing.get("name")), "name", 200),
        "unit": text(payload.get("unit", existing.get("unit")), "unit", 32),
        "quantity": _quantity(payload.get("quantity", existing.get("quantity")), "quantity"),
        "minimum_quantity": _quantity(
            payload.get("minimum_quantity", existing.get("minimum_quantity")),
            "minimum_quantity",
        ),
        "expires_on": _expiry(payload.get("expires_on", existing.get("expires_on"))),
    }
    for field in METADATA_LIMITS:
        value[field] = _metadata(payload.get(field, existing.get(field, "")), field)
    value["normalized_name"] = shopping.normalized_name(value["name"])

    changes = {key: val for key, val in value.items() if existing.get(key) != val}
    if is_edit and not changes:
        raise DomainError("invalid_transition")
    reason = ""
    if "reason" in payload:
        reason = text(payload["reason"], "reason", 500)
    if is_edit and {"quantity", "unit"} & changes.keys() and not reason:
        raise DomainError("invalid_field", "reason")

    if not is_edit:
        items = _mutable_bucket(ctx, "items")
        record = {
            "id": ctx.identifier("I"),
            **value,
            "status": "active",
            "created_at": ctx.now.isoformat(),
            "history": [],
        }
        items[record["id"]] = record
        _history(ctx, record, "created", changes=value)
        return record

    existing.update(value)
    _history(ctx, existing, "saved", reason=reason, changes=changes)
    _supersede_item_suggestions(ctx, existing["id"])
    return existing


def _stock_set(ctx: Context, payload: dict) -> dict:
    _require_roles(ctx, frozenset({"owner", "parent", "adult"}))
    fields(
        payload, {"id", "revision", "quantity", "reason"}, {"id", "revision", "quantity", "reason"}
    )
    items = _bucket(ctx.state, "items")
    item = _record(items, payload["id"], payload["revision"])
    if item.get("status") != "active":
        raise DomainError("invalid_transition")
    quantity = _quantity(payload["quantity"], "quantity")
    reason = text(payload["reason"], "reason", 500)
    if quantity == item["quantity"]:
        raise DomainError("invalid_transition")
    previous = item["quantity"]
    item["quantity"] = quantity
    _history(ctx, item, "stock_set", reason=reason, changes={"from": previous, "to": quantity})
    _supersede_item_suggestions(ctx, item["id"])
    result = deepcopy(item)
    if ctx.actor["role"] not in PRIVILEGED:
        result.pop("history", None)
        result.pop("note", None)
    return result


def _archive(ctx: Context, payload: dict) -> dict:
    _require_roles(ctx, PRIVILEGED)
    fields(payload, {"id", "revision", "reason"}, {"id", "revision", "reason"})
    item = _record(_bucket(ctx.state, "items"), payload["id"], payload["revision"])
    if item.get("status") != "active":
        raise DomainError("invalid_transition")
    reason = text(payload["reason"], "reason", 500)
    item["status"] = "archived"
    item["archived_at"] = ctx.now.isoformat()
    _history(ctx, item, "archived", reason=reason)
    _supersede_item_suggestions(ctx, item["id"])
    return item


def _suggestion(ctx: Context, action: str, payload: dict) -> dict:
    _require_roles(ctx, PRIVILEGED)
    fields(payload, {"id", "revision", "reason"}, {"id", "revision"})
    suggestions = _bucket(ctx.state, "suggestions")
    suggestion = _record(suggestions, payload["id"], payload["revision"])
    if suggestion.get("status") != "open":
        raise DomainError("invalid_transition")
    if action == "suggestion_dismiss":
        reason = text(payload.get("reason"), "reason", 500)
        _change_suggestion(ctx, suggestion, "dismissed", history_reason=reason)
        return suggestion
    if action != "suggestion_accept":
        raise DomainError("unknown_action")
    if "reason" in payload:
        raise DomainError("invalid_field", "reason")
    if "shopping" not in ctx.state.get("settings", {}).get("modules", []):
        raise DomainError("module_disabled")

    item = _bucket(ctx.state, "items").get(suggestion["pantry_id"])
    if (
        item is None
        or item.get("status") != "active"
        or item.get("revision") != suggestion.get("source_revision")
        or _deficit(item) <= 0
    ):
        raise DomainError("conflict")
    covered = _matching_shopping(ctx.state, item)
    if covered is not None:
        _change_suggestion(ctx, suggestion, "covered", shopping_id=covered["id"])
        return suggestion

    created = shopping.handle(
        ctx,
        "add",
        {
            "name": item["name"],
            "quantity": _deficit(item),
            "unit": item["unit"],
            "category": item["category"],
        },
    )
    created["pantry_id"] = item["id"]
    created["pantry_suggestion_id"] = suggestion["id"]
    _change_suggestion(ctx, suggestion, "accepted", shopping_id=created["id"])
    return suggestion


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Apply one pantry command without external side effects."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    if action.startswith("dietary_"):
        return dietary_profiles.handle(ctx, action, payload)
    if action.startswith("meal_shop_"):
        return meal_shopping.handle(ctx, action, payload)
    if action.startswith("meal_"):
        return meal_plans.handle(ctx, action, payload)
    if action == "item_save":
        return _save_item(ctx, payload)
    if action == "stock_set":
        return _stock_set(ctx, payload)
    if action == "item_archive":
        return _archive(ctx, payload)
    if action in {"suggestion_accept", "suggestion_dismiss"}:
        return _suggestion(ctx, action, payload)
    raise DomainError("unknown_action")


def tick(ctx: Context) -> None:
    """Create reviewable low-stock suggestions; never create shopping items."""
    pantry_expiry.tick(ctx)
    if "pantry" not in ctx.state.get("settings", {}).get("modules", []):
        return
    items = _bucket(ctx.state, "items")
    suggestions = _bucket(ctx.state, "suggestions")

    for suggestion in list(suggestions.values()):
        if suggestion.get("status") != "open":
            continue
        item = items.get(suggestion.get("pantry_id"))
        if (
            item is None
            or item.get("status") != "active"
            or item.get("revision") != suggestion.get("source_revision")
            or _deficit(item) <= 0
        ):
            _change_suggestion(ctx, suggestion, "superseded")

    for item in list(items.values()):
        if item.get("status") != "active" or _deficit(item) <= 0:
            continue
        covered = _matching_shopping(ctx.state, item)
        current = [
            proposal
            for proposal in suggestions.values()
            if proposal.get("pantry_id") == item["id"]
            and proposal.get("source_revision") == item["revision"]
        ]
        if covered is not None:
            for proposal in current:
                if proposal.get("status") == "open":
                    _change_suggestion(ctx, proposal, "covered", shopping_id=covered["id"])
            continue
        if current:
            continue
        suggestions = _mutable_bucket(ctx, "suggestions")
        proposal = {
            "id": ctx.identifier("G"),
            "pantry_id": item["id"],
            "source_revision": item["revision"],
            "quantity": _deficit(item),
            "unit": item["unit"],
            "reason": "below_minimum",
            "status": "open",
            "created_at": ctx.now.isoformat(),
            "history": [],
        }
        suggestions[proposal["id"]] = proposal
        _history(ctx, proposal, "opened")


def _expiry_status(
    state: dict, expires_on: str | None, now: datetime | None
) -> tuple[str, int | None]:
    if expires_on is None:
        return "none", None
    if now is None:
        return "unknown", None
    current = timestamp(now, "now")
    zone = ZoneInfo(state.get("settings", {}).get("timezone", "UTC"))
    days = (date.fromisoformat(expires_on) - current.astimezone(zone).date()).days
    if days < 0:
        return "expired", days
    if days == 0:
        return "today", days
    if days <= 7:
        return "expiring", days
    return "fresh", days


def _public_item(state: dict, item: dict, *, parent: bool, now: datetime | None) -> dict:
    result = deepcopy(item)
    result["low_stock"] = _deficit(item) > 0
    result["expiry_status"], result["expires_in_days"] = _expiry_status(
        state, item.get("expires_on"), now
    )
    if not parent:
        result.pop("history", None)
        result.pop("note", None)
    return result


def view(state: dict, actor: dict, now: datetime | None = None) -> dict:
    """Return a role-filtered projection without mutating persisted state."""
    current = state.get("members", {}).get(actor.get("id"), {})
    if not current.get("active", False) or current.get("role") == "guest":
        return {"items": [], "archived": [], "suggestions": []}
    parent = current.get("role") in PRIVILEGED
    items = _bucket(state, "items")
    active = [
        _public_item(state, item, parent=parent, now=now)
        for item in items.values()
        if item.get("status") == "active"
    ]
    archived = [
        _public_item(state, item, parent=parent, now=now)
        for item in items.values()
        if item.get("status") == "archived"
    ]
    suggestions = (
        [deepcopy(item) for item in _bucket(state, "suggestions").values()] if parent else []
    )
    return {
        "items": active,
        "archived": archived,
        "suggestions": suggestions,
        "meal_plans": meal_plans.view(state, actor),
        "meal_shopping": meal_shopping.view(state, actor),
        "dietary_profiles": dietary_profiles.view(state, actor),
    }
