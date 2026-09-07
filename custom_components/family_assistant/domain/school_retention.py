"""Bounded retention for content-free school preparation reminder intents.

Only an exact marker/outbox lineage may be removed.  A compact monotonic date
watermark survives pruning so a wall-clock rollback cannot recreate a reminder
for an already-retired school date.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import recurrence
from .context import Context
from .validation import DomainError, timestamp
from .validation import revision as strict_revision

KEY = "school_preparation_reminder"
MAX_RECORDS = 10_000
SUCCESS_RETENTION = timedelta(days=35)
FAILED_RETENTION = timedelta(days=90)

ACTIVE_OR_UNCERTAIN = frozenset({"pending", "awaiting_channel", "sending", "uncertain"})
TERMINAL = frozenset({"sent", "superseded", "resolved"})
EVENT_FIELDS = frozenset(
    {
        "timetable_id",
        "timetable_revision",
        "member",
        "member_revision",
        "recipient_revision",
        "date",
        "routine_id",
        "routine_revision",
        "subscription_revision",
        "policy_fingerprint",
        "expires_at",
    }
)
MARKER_FIELDS = frozenset(
    {
        "event_id",
        "timetable_revision",
        "member_revision",
        "recipient_revision",
        "routine_revision",
        "subscription_revision",
    }
)
RETENTION_FIELDS = frozenset({"through_date", "updated_at"})
REVISION_FIELDS = (
    "timetable_revision",
    "member_revision",
    "recipient_revision",
    "routine_revision",
    "subscription_revision",
)
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")


def _school(state: dict) -> dict:
    value = state.get("school", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "school")
    return value


def _markers(state: dict) -> dict:
    value = _school(state).get("preparation_reminder_markers", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "preparation_reminder_markers")
    return value


def _outbox(state: dict) -> dict:
    value = state.get("outbox", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "outbox")
    return value


def _retention(state: dict) -> tuple[date | None, datetime | None]:
    value = _school(state).get("preparation_reminder_retention")
    if value is None:
        return None, None
    if not isinstance(value, dict) or set(value) != RETENTION_FIELDS:
        raise DomainError("invalid_field", "preparation_reminder_retention")
    through = recurrence.local_date(value["through_date"])
    updated = timestamp(value["updated_at"], "updated_at")
    return through, updated


def _marker_parts(value) -> tuple[str, str, date] | None:
    try:
        parts = json.loads(value)
        if (
            not isinstance(parts, list)
            or len(parts) != 3
            or not all(isinstance(part, str) and part for part in parts)
            or value != json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
        ):
            return None
        day = recurrence.local_date(parts[2])
        if day.isoformat() != parts[2]:
            return None
        return parts[0], parts[1], day
    except (DomainError, TypeError, ValueError):
        return None


def _lineage(marker_key, marker, event):
    parts = _marker_parts(marker_key)
    if (
        parts is None
        or not isinstance(marker, dict)
        or set(marker) != MARKER_FIELDS
        or not isinstance(event, dict)
        or event.get("id") != marker.get("event_id")
        or event.get("key") != KEY
        or event.get("recipient") != parts[0]
    ):
        return None
    data = event.get("data")
    if (
        not isinstance(data, dict)
        or set(data) != EVENT_FIELDS
        or data.get("timetable_id") != parts[1]
        or data.get("date") != parts[2].isoformat()
        or not isinstance(data.get("member"), str)
        or not data["member"]
        or not isinstance(data.get("routine_id"), str)
        or not data["routine_id"]
        or not isinstance(data.get("policy_fingerprint"), str)
        or _FINGERPRINT.fullmatch(data["policy_fingerprint"]) is None
    ):
        return None
    try:
        for field in REVISION_FIELDS:
            if strict_revision(marker.get(field)) != strict_revision(data.get(field)):
                return None
        created = timestamp(event.get("created_at"), "created_at").astimezone(UTC)
        expires = timestamp(data["expires_at"], "expires_at").astimezone(UTC)
    except (DomainError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    # The actual policy permits today or tomorrow only.  Three elapsed days
    # leaves room for an extreme lesson clock and DST while preventing a
    # malformed far-future date from advancing the anti-replay watermark.
    if not created < expires <= created + timedelta(days=3):
        return None
    if abs((parts[2] - expires.date()).days) > 1:
        return None
    return parts[2], expires


def _delivery_states_compatible(event: dict) -> bool:
    state = event.get("state")
    if state in ACTIVE_OR_UNCERTAIN or state not in {*TERMINAL, "failed"}:
        return False
    allowed = {
        "sent": {"sent", "superseded"},
        "superseded": {"sent", "superseded"},
        # An explicit resolution is the only terminal acknowledgement allowed
        # to retire a transport whose outcome remained uncertain.
        "resolved": {"sent", "superseded", "failed", "uncertain"},
        "failed": {"failed", "superseded"},
    }[state]
    deliveries = event.get("deliveries", {})
    if not isinstance(deliveries, dict) or state in {"sent", "failed"} and not deliveries:
        return False
    return all(
        isinstance(delivery, dict) and delivery.get("state") in allowed
        for delivery in deliveries.values()
    )


def _prunable(marker_key, marker, event, now: datetime):
    lineage = _lineage(marker_key, marker, event)
    if lineage is None or not _delivery_states_compatible(event):
        return None
    day, expires = lineage
    horizon = FAILED_RETENTION if event.get("state") == "failed" else SUCCESS_RETENTION
    return day if now >= expires + horizon else None


def creation_allowed(state: dict, target_date: date) -> bool:
    """Allow a new period only below capacity and beyond the durable watermark."""
    if type(target_date) is not date:
        return False
    try:
        markers = _markers(state)
        outbox = _outbox(state)
        through, _updated = _retention(state)
    except DomainError:
        return False
    retained = sum(isinstance(event, dict) and event.get("key") == KEY for event in outbox.values())
    return bool(
        len(markers) < MAX_RECORDS
        and retained < MAX_RECORDS
        and (through is None or target_date > through)
    )


def prune(ctx: Context) -> int:
    """Remove exact old terminal marker/event pairs and advance one watermark."""
    try:
        markers = _markers(ctx.state)
        outbox = _outbox(ctx.state)
        through, _updated = _retention(ctx.state)
        current = timestamp(ctx.now, "now").astimezone(UTC)
    except (DomainError, TypeError, ValueError, OverflowError, OSError):
        return 0
    removed = []
    newest = through
    for marker_key in sorted(markers):
        marker = markers[marker_key]
        event_id = marker.get("event_id") if isinstance(marker, dict) else None
        event = outbox.get(event_id) if isinstance(event_id, str) else None
        day = _prunable(marker_key, marker, event, current)
        if day is not None:
            removed.append((marker_key, event_id))
            newest = day if newest is None or day > newest else newest
    if not removed:
        return 0
    for marker_key, event_id in removed:
        markers.pop(marker_key, None)
        outbox.pop(event_id, None)
    if newest != through:
        _school(ctx.state)["preparation_reminder_retention"] = {
            "through_date": newest.isoformat(),
            "updated_at": current.isoformat(),
        }
    return len(removed)


def health_stats(state: dict, now=None) -> dict:
    """Return counts and booleans only; never IDs, dates, or reminder content."""
    try:
        markers = _markers(state)
        outbox = _outbox(state)
        through, _updated = _retention(state)
    except DomainError:
        return {
            "markers": 0,
            "retained": 0,
            "unresolved": 0,
            "unpaired": 0,
            "retention_errors": 1,
            "capacity": True,
            "clock_rollback": False,
        }
    events = [
        event for event in outbox.values() if isinstance(event, dict) and event.get("key") == KEY
    ]
    matched = set()
    invalid_markers = 0
    retention_errors = 0
    for marker_key, marker in markers.items():
        event_id = marker.get("event_id") if isinstance(marker, dict) else None
        event = outbox.get(event_id) if isinstance(event_id, str) else None
        if _lineage(marker_key, marker, event) is None:
            invalid_markers += 1
        else:
            matched.add(event_id)
            if event.get("state") not in ACTIVE_OR_UNCERTAIN and not _delivery_states_compatible(
                event
            ):
                retention_errors += 1
    unpaired_events = sum(event.get("id") not in matched for event in events)
    rollback = False
    if now is not None and through is not None:
        try:
            settings = state.get("settings", {})
            zone_name = settings.get("timezone") if isinstance(settings, dict) else None
            if not isinstance(zone_name, str):
                raise ValueError
            zone = ZoneInfo(zone_name)
            local_day = timestamp(now, "now").astimezone(zone).date()
            rollback = local_day <= through
        except (DomainError, TypeError, ValueError, ZoneInfoNotFoundError, OverflowError, OSError):
            retention_errors += 1
    return {
        "markers": len(markers),
        "retained": len(events),
        "unresolved": sum(
            event.get("state") in {*ACTIVE_OR_UNCERTAIN, "failed"} for event in events
        ),
        "unpaired": invalid_markers + unpaired_events,
        "retention_errors": retention_errors,
        "capacity": len(markers) >= MAX_RECORDS or len(events) >= MAX_RECORDS,
        "clock_rollback": rollback,
    }
