"""Pure weekly court period bounds and score summarization helpers."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .validation import DomainError, text

_CLOCK_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _validate_clock(value: Any) -> tuple[int, int]:
    if not isinstance(value, str) or not _CLOCK_RE.fullmatch(value):
        raise DomainError("invalid_field", "clock")
    h, m = value.split(":")
    return int(h), int(m)


def _validate_weekday(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 6:
        raise DomainError("invalid_field", "weekday")
    return value


def _resolve_zone(value: Any) -> ZoneInfo:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise DomainError("invalid_field", "timezone")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise DomainError("invalid_field", "timezone") from None


def _resolve_boundary(target_date: date, target_time: time, tz: ZoneInfo) -> datetime:
    """Resolve local date + time to aware UTC datetime, earliest valid fold, forward scan on gap."""
    for day_offset in range(2):
        try:
            cur_date = target_date + timedelta(days=day_offset)
        except (ValueError, OverflowError):
            raise DomainError("invalid_field", "date") from None
        start_min = target_time.hour * 60 + target_time.minute if day_offset == 0 else 0
        for minute_offset in range(start_min, 1440):
            h, m = divmod(minute_offset, 60)
            wall_dt = datetime(cur_date.year, cur_date.month, cur_date.day, h, m)
            for f in (0, 1):
                candidate = wall_dt.replace(tzinfo=tz, fold=f)
                back_wall = candidate.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
                if back_wall == wall_dt:
                    return candidate.astimezone(UTC)
    raise DomainError("invalid_field", "date")


def period_bounds(
    now: datetime,
    zone: str,
    weekday: int = 0,
    clock: str = "00:00",
) -> tuple[datetime, datetime]:
    """Calculate current weekly period [start, end) in UTC containing now."""
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise DomainError("invalid_field", "now")
    tz = _resolve_zone(zone)
    w_day = _validate_weekday(weekday)
    h, m = _validate_clock(clock)
    b_time = time(h, m)

    try:
        now_utc = now.astimezone(UTC)
        now_local = now.astimezone(tz)
        local_d = now_local.date()

        if not 1 <= local_d.year <= 9999:
            raise DomainError("invalid_field", "now")

        offset = (local_d.weekday() - w_day) % 7
        anchor = local_d - timedelta(days=offset)

        start_utc = _resolve_boundary(anchor, b_time, tz)
        if start_utc > now_utc:
            anchor -= timedelta(days=7)
            start_utc = _resolve_boundary(anchor, b_time, tz)
        end_utc = _resolve_boundary(anchor + timedelta(days=7), b_time, tz)
        if start_utc <= now_utc < end_utc:
            return start_utc, end_utc
    except DomainError:
        raise
    except (ValueError, OverflowError):
        raise DomainError("invalid_field", "now") from None

    raise DomainError("invalid_field", "period")


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            raise DomainError("invalid_field", field_name) from None
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise DomainError("invalid_field", field_name)
    try:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise DomainError("invalid_field", field_name) from None


def summarize(
    records: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Aggregate court scores by member within [start, end) period without mutating input."""
    if not isinstance(records, list):
        raise DomainError("invalid_field", "records")
    start_utc = _parse_timestamp(start, "start")
    end_utc = _parse_timestamp(end, "end")
    if start_utc >= end_utc:
        raise DomainError("invalid_field", "period")

    seen_ids: set[str] = set()
    events: list[str] = []
    members: dict[str, dict[str, Any]] = {}

    for item in records:
        if not isinstance(item, dict):
            raise DomainError("invalid_field", "record")

        rec_id = text(item.get("id"), "id", 80)
        if rec_id in seen_ids:
            raise DomainError("invalid_field", "id")
        seen_ids.add(rec_id)

        member_id = text(item.get("member"), "member", 80)

        pts = item.get("points")
        if type(pts) is not int or not -100 <= pts <= 100 or pts == 0:
            raise DomainError("invalid_field", "points")

        status = item.get("status")
        if status not in {"active", "reversed"}:
            raise DomainError("invalid_field", "status")

        if "reason" in item:
            text(item["reason"], "reason", 500)

        created_dt = _parse_timestamp(item.get("created_at"), "created_at")

        if not (start_utc <= created_dt < end_utc):
            continue

        events.append(rec_id)

        if member_id not in members:
            members[member_id] = {
                "member": member_id,
                "active_positives": 0,
                "active_negatives": 0,
                "total": 0,
                "active_count": 0,
                "reversed_count": 0,
            }

        row = members[member_id]
        if status == "active":
            row["active_count"] += 1
            if pts > 0:
                row["active_positives"] += pts
            else:
                row["active_negatives"] += pts
            row["total"] += pts
        else:
            row["reversed_count"] += 1

    sorted_rows = [members[m_id] for m_id in sorted(members)]
    return {"rows": sorted_rows, "events": events}
