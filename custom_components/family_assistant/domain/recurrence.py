"""Local-calendar recurrence shared by family processes, bounded after downtime."""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .household import timezone
from .validation import DomainError, enum, fields


def clock(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise DomainError("invalid_field", "time")
    return value


def local_date(value):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise DomainError("invalid_field", "date") from None


def validate(payload):
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "recurrence")
    fields(
        payload,
        {
            "frequency",
            "interval",
            "start_date",
            "until",
            "weekdays",
            "month_day",
            "time",
            "timezone",
            "exceptions",
            "catchup_hours",
        },
        {"frequency", "start_date", "time", "timezone"},
    )
    frequency = enum(payload["frequency"], {"daily", "weekly", "monthly"}, "frequency")
    start = local_date(payload["start_date"])
    interval, catchup = payload.get("interval", 1), payload.get("catchup_hours", 24)
    if (
        type(interval) is not int
        or not 1 <= interval <= 52
        or type(catchup) is not int
        or not 0 <= catchup <= 48
    ):
        raise DomainError("invalid_field", "interval")
    weekdays = payload.get("weekdays", [start.weekday()])
    if (
        not isinstance(weekdays, list)
        or not weekdays
        or any(type(d) is not int or not 0 <= d <= 6 for d in weekdays)
    ):
        raise DomainError("invalid_field", "weekdays")
    month_day = payload.get("month_day", start.day)
    if type(month_day) is not int or not 1 <= month_day <= 31:
        raise DomainError("invalid_field", "month_day")
    until = payload.get("until")
    if until and local_date(until) < start:
        raise DomainError("invalid_field", "until")
    exceptions = payload.get("exceptions", [])
    if not isinstance(exceptions, list) or len(exceptions) > 366:
        raise DomainError("invalid_field", "exceptions")
    return {
        "frequency": frequency,
        "interval": interval,
        "start_date": start.isoformat(),
        "until": local_date(until).isoformat() if until else None,
        "time": clock(payload["time"]),
        "timezone": timezone(payload["timezone"]),
        "weekdays": sorted(set(weekdays)),
        "month_day": month_day,
        "exceptions": sorted({local_date(d).isoformat() for d in exceptions}),
        "catchup_hours": catchup,
    }


def matches(rule, day):
    start = local_date(rule["start_date"])
    if (
        day < start
        or rule.get("until")
        and day > local_date(rule["until"])
        or day.isoformat() in rule["exceptions"]
    ):
        return False
    if rule["frequency"] == "daily":
        return (day - start).days % rule["interval"] == 0
    if rule["frequency"] == "weekly":
        weeks = (
            (day - timedelta(days=day.weekday())) - (start - timedelta(days=start.weekday()))
        ).days // 7
        return day.weekday() in rule["weekdays"] and weeks % rule["interval"] == 0
    months = (day.year - start.year) * 12 + day.month - start.month
    return day.day == rule["month_day"] and months % rule["interval"] == 0


def local_clock(day, value, zone):
    result = datetime.combine(day, time.fromisoformat(clock(value)), ZoneInfo(zone))
    # Spring gaps are skipped. Autumn's first occurrence is selected once by date ID.
    if result.astimezone(UTC).astimezone(result.tzinfo).replace(tzinfo=None) != result.replace(
        tzinfo=None
    ):
        return None
    return result


def due(rule, now, *, not_before=None):
    """At most three local dates, oldest first; never replay weeks of missed work."""
    local = now.astimezone(ZoneInfo(rule["timezone"]))
    window = (
        timedelta(hours=rule["catchup_hours"]) if rule["catchup_hours"] else timedelta(minutes=1)
    )
    earliest = now.astimezone(UTC) - window
    if not_before is not None:
        earliest = max(earliest, not_before.astimezone(UTC))
    for offset in (2, 1, 0):
        day = local.date() - timedelta(days=offset)
        if not matches(rule, day):
            continue
        moment = local_clock(day, rule["time"], rule["timezone"])
        if moment and earliest <= moment.astimezone(UTC) <= now.astimezone(UTC):
            yield moment
