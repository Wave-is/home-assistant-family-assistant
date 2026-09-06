"""Opt-in reminders for recorded pantry expiry dates.

Dates and quantities are factual household records.  A reminder is not a food-safety
assessment and never changes stock, shopping, penalties, or devices.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .context import Context
from .validation import DomainError, text
from .validation import revision as strict_revision

KEY = "pantry_expiry"
TRIGGER_TIME = time(9, 0)
UNSENT = frozenset({"pending", "awaiting_channel"})


def _pantry(state: dict) -> dict:
    pantry = state.get("pantry", {})
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    return pantry


def _items(state: dict) -> dict:
    items = _pantry(state).get("items", {})
    if not isinstance(items, dict):
        raise DomainError("invalid_field", "items")
    return items


def _markers(state: dict) -> dict:
    markers = _pantry(state).get("expiry_reminders", {})
    if not isinstance(markers, dict):
        raise DomainError("invalid_field", "expiry_reminders")
    return markers


def _mutable_markers(ctx: Context) -> dict:
    pantry = ctx.state.get("pantry")
    if pantry is None:
        pantry = {}
        ctx.state["pantry"] = pantry
    if not isinstance(pantry, dict):
        raise DomainError("invalid_field", "pantry")
    markers = pantry.get("expiry_reminders")
    if markers is None:
        markers = {}
        pantry["expiry_reminders"] = markers
    if not isinstance(markers, dict):
        raise DomainError("invalid_field", "expiry_reminders")
    return markers


def _recorded_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        result = date.fromisoformat(value)
    except ValueError:
        return None
    return result if result.isoformat() == value else None


def _positive_quantity(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
    )


def _zone(state: dict) -> ZoneInfo | None:
    value = state.get("settings", {}).get("timezone", "UTC")
    if not isinstance(value, str):
        return None
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def current_event(state: dict, event: dict, now: datetime | None = None) -> bool:
    """Return whether an adapter may still deliver one expiry reminder.

    With ``now`` omitted this checks authorization and source freshness only.  With
    ``now`` supplied it also requires the recorded date to remain inside the owner's
    current household-local lead window.
    """
    if (
        not isinstance(event, dict)
        or event.get("key") != KEY
        or event.get("recipient") != "parents"
    ):
        return False
    settings = state.get("settings", {})
    modules = settings.get("modules", []) if isinstance(settings, dict) else []
    if (
        not isinstance(settings, dict)
        or not isinstance(modules, list)
        or "pantry" not in modules
        or settings.get("pantry_expiry_reminders") is not True
    ):
        return False
    lead_days = settings.get("pantry_expiry_days", 3)
    if type(lead_days) is not int or not 0 <= lead_days <= 30:
        return False
    data = event.get("data")
    if not isinstance(data, dict) or set(data) != {
        "id",
        "source_revision",
        "name",
        "expires_on",
    }:
        return False
    item_id = data.get("id")
    if not isinstance(item_id, str):
        return False
    try:
        item = _items(state).get(item_id)
    except DomainError:
        return False
    if not isinstance(item, dict) or item.get("status") != "active":
        return False
    source_revision = data.get("source_revision")
    item_revision = item.get("revision")
    if (
        type(source_revision) is not int
        or type(item_revision) is not int
        or not 1 <= item_revision <= 2**53 - 1
        or source_revision != item_revision
        or data.get("expires_on") != item.get("expires_on")
        or data.get("name") != item.get("name")
        or not _positive_quantity(item.get("quantity"))
    ):
        return False
    expires_on = _recorded_date(item.get("expires_on"))
    if expires_on is None:
        return False
    if now is None:
        return True
    zone = _zone(state)
    if zone is None or not isinstance(now, datetime) or now.tzinfo is None:
        return False
    days = (expires_on - now.astimezone(zone).date()).days
    return 0 <= days <= lead_days


def supersede_invalid(ctx: Context) -> None:
    """Supersede only unsent invalid intents; never claim recall of in-flight work."""
    outbox = ctx.state.get("outbox", {})
    if not isinstance(outbox, dict):
        raise DomainError("invalid_field", "outbox")
    for event in outbox.values():
        if (
            not isinstance(event, dict)
            or event.get("key") != KEY
            or event.get("state") not in UNSENT
            or current_event(ctx.state, event, ctx.now)
        ):
            continue
        deliveries = event.get("deliveries")
        if not isinstance(deliveries, dict) or not deliveries:
            event["state"] = "superseded"
            continue
        for delivery in deliveries.values():
            if isinstance(delivery, dict) and delivery.get("state") == "pending":
                delivery["state"] = "superseded"
        statuses = {
            delivery.get("state") for delivery in deliveries.values() if isinstance(delivery, dict)
        }
        if "sending" in statuses:
            continue
        if statuses <= {"superseded"}:
            event["state"] = "superseded"
        elif statuses <= {"sent", "superseded"}:
            event["state"] = "sent"
        elif "uncertain" in statuses:
            event["state"] = "uncertain"
        else:
            event["state"] = "failed"


def tick(ctx: Context) -> None:
    """Create one durable parent reminder per eligible current item revision."""
    supersede_invalid(ctx)
    settings = ctx.state.get("settings", {})
    if (
        "pantry" not in settings.get("modules", [])
        or settings.get("pantry_expiry_reminders") is not True
    ):
        return
    lead_days = settings.get("pantry_expiry_days", 3)
    if type(lead_days) is not int or not 0 <= lead_days <= 30:
        raise DomainError("invalid_field", "pantry_expiry_days")
    zone = _zone(ctx.state)
    if zone is None:
        raise DomainError("invalid_field", "timezone")
    local_now = ctx.now.astimezone(zone)
    if local_now.time().replace(tzinfo=None) < TRIGGER_TIME:
        return
    items = _items(ctx.state)
    markers = _markers(ctx.state)
    for item in items.values():
        if (
            not isinstance(item, dict)
            or item.get("status") != "active"
            or not _positive_quantity(item.get("quantity"))
        ):
            continue
        expires_on = _recorded_date(item.get("expires_on"))
        if expires_on is None:
            continue
        days = (expires_on - local_now.date()).days
        if not 0 <= days <= lead_days:
            continue
        item_id = text(item.get("id"), "id", 80)
        source_revision = strict_revision(item.get("revision"))
        marker = markers.get(item_id)
        if isinstance(marker, dict) and marker.get("source_revision") == source_revision:
            continue
        name = text(item.get("name"), "name", 200)
        event_id = ctx.notify(
            "parents",
            KEY,
            {
                "id": item_id,
                "source_revision": source_revision,
                "name": name,
                "expires_on": expires_on.isoformat(),
            },
        )
        markers = _mutable_markers(ctx)
        markers[item_id] = {"source_revision": source_revision, "event_id": event_id}
