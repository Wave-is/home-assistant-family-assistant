"""Pure, bounded one-week proposals from expanded calendar occurrences."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .school import _lessons
from .validation import DomainError


def _start(value):
    try:
        if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            raise ValueError
        result = date.fromisoformat(value)
        if result.weekday() != 0:
            raise ValueError
        return result, result + timedelta(days=6)
    except (ValueError, OverflowError):
        raise DomainError("invalid_field", "week_start") from None


def _instant(value, zone):
    try:
        if (
            not isinstance(value, str)
            or len(value) > 40
            or re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T", value) is None
        ):
            raise ValueError
        instant = datetime.fromisoformat(value)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError
        result = instant.astimezone(zone)
        if (
            result.second
            or result.microsecond
            or result.replace(fold=0).utcoffset() != result.replace(fold=1).utcoffset()
        ):
            # The timetable model stores local clocks, not a DST fold selector.
            raise ValueError
        return result
    except (ValueError, OverflowError):
        raise DomainError("invalid_field", "events") from None


def calendar_week(events, *, week_start, timezone):
    """Never infer a recurring school year, drop rows, truncate or perform I/O."""
    first, last = _start(week_start)
    try:
        if not isinstance(timezone, str) or not 1 <= len(timezone) <= 128:
            raise ValueError
        zone = ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise DomainError("invalid_field", "timezone") from None
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        raise DomainError("invalid_field", "events")
    lessons = []
    total = 0
    for event in events:
        if (
            type(event) is not dict
            or not {"start", "end", "summary"} <= event.keys()
            or set(event) - {"start", "end", "summary", "location"}
        ):
            raise DomainError("invalid_field", "events")
        if any(not isinstance(value, str) for value in event.values()):
            raise DomainError("invalid_field", "events")
        total += sum(len(value) for value in event.values())
        if total > 32768:
            raise DomainError("invalid_field", "events")
        start, end = _instant(event["start"], zone), _instant(event["end"], zone)
        if not first <= start.date() <= last or end.date() != start.date() or end <= start:
            raise DomainError("invalid_field", "events")
        lessons.append(
            {
                "weekday": start.weekday(),
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "subject": event["summary"],
                "room": event.get("location", ""),
                "materials": [],
            }
        )
    # Real existing timetable validation checks lengths, duplicates and overlap.
    lessons = _lessons(lessons)
    return {
        "valid_from": first.isoformat(),
        "valid_until": last.isoformat(),
        "lessons": lessons,
        "count": len(lessons),
    }
