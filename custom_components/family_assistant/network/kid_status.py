"""Pure schedule status calculation for native and normalized Kid Control profiles."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from . import kids


def _unknown_status() -> dict[str, Any]:
    """Conservative fallback outcome for invalid inputs, naive datetimes, or unmodeled features.

    When given invalid inputs (e.g. malformed profile dict, unparseable windows,
    invalid time zone) or naive datetimes (missing timezone offset), schedule_status
    fails conservatively by returning mode='unknown', allows=None, next_change_at=None,
    next_allows=None, and remaining_minutes=None, refusing to guess permissions or crash.
    """
    return {
        "mode": "unknown",
        "allows": None,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


def _parse_timezone(tz_input: Any) -> tzinfo:
    """Parse a timezone input into a tzinfo object (ZoneInfo, tzinfo, or ISO offset string)."""
    if isinstance(tz_input, tzinfo):
        return tz_input
    if isinstance(tz_input, str):
        cleaned = tz_input.strip()
        if not cleaned:
            raise ValueError("empty timezone")
        try:
            return ZoneInfo(cleaned)
        except (KeyError, ValueError):
            pass
        if cleaned == "Z":
            return UTC
        try:
            parsed = datetime.fromisoformat(f"2026-01-01T00:00:00{cleaned}")
            if parsed.tzinfo is not None:
                return parsed.tzinfo
        except ValueError:
            pass
    raise ValueError(f"invalid timezone: {type(tz_input).__name__}")


def _parse_intervals(window_str: str) -> list[tuple[int, int]]:
    """Convert canonical window string into integer minute intervals [(start, end), ...]."""
    if not window_str:
        return []
    intervals: list[tuple[int, int]] = []
    for part in window_str.split(","):
        part = part.strip()
        if not part:
            continue
        start_s, end_s = part.split("-")
        s_h, s_m = map(int, start_s.split(":"))
        e_h, e_m = map(int, end_s.split(":"))
        intervals.append((s_h * 60 + s_m, e_h * 60 + e_m))
    return intervals


def _is_allowed_at(dt: datetime, tz: tzinfo, schedule: dict[str, list[tuple[int, int]]]) -> bool:
    """Evaluate whether an aware datetime dt is permitted by the local weekly schedule."""
    loc = dt.astimezone(tz)
    day = kids.DAYS[loc.weekday()]
    intervals = schedule.get(day, [])
    sec = loc.hour * 3600 + loc.minute * 60 + loc.second + (loc.microsecond / 1_000_000.0)
    for s_m, e_m in intervals:
        if s_m * 60 <= sec < e_m * 60:
            return True
    return False


def _find_next_change(
    now: datetime, tz: tzinfo, schedule: dict[str, list[tuple[int, int]]]
) -> tuple[datetime | None, bool | None]:
    """Find the earliest scheduled transition strictly after now within an 8-day bounded horizon."""
    # now is guaranteed normalized to UTC
    current_allows = _is_allowed_at(now, tz, schedule)
    scan_end = now + timedelta(days=8)

    # All-week-open or all-week-closed schedules never change within the 8-day scan
    is_all_open = all(schedule.get(d) == [(0, 1440)] for d in kids.DAYS)
    is_all_closed = all(len(schedule.get(d, [])) == 0 for d in kids.DAYS)
    if is_all_open or is_all_closed:
        return None, None

    candidates: list[datetime] = []

    # 1. Identify DST transition points within the 8-day window using binary search per 24h day.
    # Anchor to whole seconds to keep transitions at exact integer second boundaries.
    base_anchor = now.replace(microsecond=0)
    for k in range(8):
        d0 = base_anchor + timedelta(days=k)
        d1 = base_anchor + timedelta(days=k + 1)
        if d0.astimezone(tz).utcoffset() != d1.astimezone(tz).utcoffset():
            low_sec = 0
            high_sec = int((d1 - d0).total_seconds())
            off0 = d0.astimezone(tz).utcoffset()
            while low_sec < high_sec:
                mid_sec = (low_sec + high_sec) // 2
                dt = d0 + timedelta(seconds=mid_sec)
                if dt.astimezone(tz).utcoffset() == off0:
                    low_sec = mid_sec + 1
                else:
                    high_sec = mid_sec
            candidates.append(d0 + timedelta(seconds=low_sec))

    # 2. Collect local clock interval boundaries (starts, ends, and midnight)
    start_date = (now.astimezone(tz) - timedelta(days=1)).date()
    end_date = (scan_end.astimezone(tz) + timedelta(days=1)).date()
    curr_date = start_date
    while curr_date <= end_date:
        day_name = kids.DAYS[curr_date.weekday()]
        times_to_check = {(0, 0)}  # midnight
        for s_m, e_m in schedule.get(day_name, []):
            times_to_check.add((s_m // 60, s_m % 60))
            if e_m < 1440:
                times_to_check.add((e_m // 60, e_m % 60))
        for h, m in times_to_check:
            for fold in (0, 1):
                try:
                    dt = datetime(
                        curr_date.year,
                        curr_date.month,
                        curr_date.day,
                        h,
                        m,
                        0,
                        fold=fold,
                        tzinfo=tz,
                    )
                    candidates.append(dt.astimezone(UTC))
                except (ValueError, OverflowError):
                    continue
        curr_date += timedelta(days=1)

    # 3. Filter candidates strictly > now and <= scan_end, sorted chronologically
    unique_cands = sorted({c for c in candidates if now < c <= scan_end})

    for cand in unique_cands:
        state_at = _is_allowed_at(cand, tz, schedule)
        state_before = _is_allowed_at(cand - timedelta(seconds=1), tz, schedule)
        if state_at != current_allows and state_before == current_allows:
            return cand, state_at

    return None, None


def schedule_status(row: Any, now: Any, timezone: Any) -> dict[str, Any]:
    """Compute pure configured schedule permission status for a Kid Control profile.

    Consumes a native or normalized Kid Control profile dict, an aware datetime now,
    and a timezone (str, ZoneInfo, or tzinfo).

    Returns a JSON-safe dict containing:
      - mode: 'unrestricted', 'paused', 'schedule', or 'unknown'
      - allows: bool or None
      - next_change_at: aware UTC ISO string or None
      - next_allows: bool or None
      - remaining_minutes: int (ceil minutes until next closure if allowed) or None

    Respects disabled before paused, weekday intervals, empty-deny schedules,
    00:00-24:00, midnight continuity, no phantom transitions at adjacent intervals,
    exact boundary semantics, and aware DST transitions. Fails conservatively
    for invalid/naive inputs by returning mode='unknown'.
    """
    # Validate aware datetime now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return _unknown_status()

    # Normalize aware now to UTC before scanning or elapsed-time calculations
    now_utc = now.astimezone(UTC)

    # Validate timezone
    try:
        tz = _parse_timezone(timezone)
    except Exception:
        return _unknown_status()

    # Validate profile row
    if not isinstance(row, dict):
        return _unknown_status()

    try:
        # Create shallow copy to prevent any mutation of caller's row
        row_copy = dict(row)
        if "name" not in row_copy:
            row_copy["name"] = "profile"
        for k in ("disabled", "paused"):
            if k in row_copy and isinstance(row_copy[k], bool):
                row_copy[k] = "true" if row_copy[k] else "false"
        canonical = kids.profile(row_copy)
    except Exception:
        return _unknown_status()

    # Non-empty tur-* schedules whose native semantics are unmodeled return unknown
    if any(canonical.get(f"tur-{d}") for d in kids.DAYS):
        return _unknown_status()

    # Respect disabled before paused
    if canonical.get("disabled") == "true":
        return {
            "mode": "unrestricted",
            "allows": True,
            "next_change_at": None,
            "next_allows": None,
            "remaining_minutes": None,
        }

    if canonical.get("paused") == "true":
        return {
            "mode": "paused",
            "allows": False,
            "next_change_at": None,
            "next_allows": None,
            "remaining_minutes": None,
        }

    # Active schedule evaluation
    try:
        schedule = {d: _parse_intervals(canonical[d]) for d in kids.DAYS}
        current_allows = _is_allowed_at(now_utc, tz, schedule)
        next_change, next_allows = _find_next_change(now_utc, tz, schedule)

        remaining_minutes = None
        if current_allows and next_change is not None:
            diff_sec = (next_change - now_utc).total_seconds()
            remaining_minutes = math.ceil(diff_sec / 60.0)

        return {
            "mode": "schedule",
            "allows": current_allows,
            "next_change_at": next_change.astimezone(UTC).isoformat() if next_change else None,
            "next_allows": next_allows,
            "remaining_minutes": remaining_minutes,
        }
    except Exception:
        return _unknown_status()
