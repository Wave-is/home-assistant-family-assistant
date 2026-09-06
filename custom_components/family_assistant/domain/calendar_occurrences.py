"""Bounded pure calendar recurrence expansion helper for Home Assistant integration."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .household import timezone as validate_timezone
from .recurrence import clock, local_clock, matches
from .recurrence import validate as validate_rule
from .validation import DomainError, enum, fields, text

STATUS_CHOICES = frozenset({"confirmed", "tentative", "cancelled"})


def _check_year(year: int) -> None:
    if not 1 <= year <= 9999:
        raise DomainError("command_too_large")


def _to_utc(dt: datetime) -> datetime:
    try:
        res = dt.astimezone(UTC)
        _check_year(res.year)
        return res
    except (OverflowError, DomainError):
        raise DomainError("command_too_large") from None


def _safe_add_days(d: date, days: int) -> date:
    try:
        res = d + timedelta(days=days)
        _check_year(res.year)
        return res
    except (OverflowError, DomainError):
        raise DomainError("command_too_large") from None


def _check_query_range(range_start: datetime, range_end: datetime) -> tuple[datetime, datetime]:
    for dt, fld in ((range_start, "range_start"), (range_end, "range_end")):
        if not isinstance(dt, datetime) or dt.tzinfo is None:
            raise DomainError("invalid_field", fld)
        try:
            if dt.utcoffset() is None:
                raise DomainError("invalid_field", fld)
        except Exception:
            raise DomainError("invalid_field", fld) from None
    start_utc = _to_utc(range_start)
    end_utc = _to_utc(range_end)
    if end_utc <= start_utc:
        raise DomainError("invalid_field", "range_end")
    if (end_utc - start_utc) > timedelta(days=367):
        raise DomainError("command_too_large")
    return start_utc, end_utc


def _parse_opt_text(value: object, field: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum:
        raise DomainError("invalid_field", field)
    return value.strip()


def _parse_event_times(record: dict) -> tuple[datetime | date, datetime | date, timedelta | int]:
    all_day = record["all_day"]
    s_raw, e_raw = record["start"], record["end"]
    if all_day:
        if not isinstance(s_raw, str) or not isinstance(e_raw, str):
            raise DomainError("invalid_field", "start")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s_raw) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", e_raw
        ):
            raise DomainError("invalid_field", "start")
        try:
            s_date, e_date = date.fromisoformat(s_raw), date.fromisoformat(e_raw)
            _check_year(s_date.year)
            _check_year(e_date.year)
        except (ValueError, DomainError):
            raise DomainError("invalid_field", "start") from None
        if e_date <= s_date:
            raise DomainError("invalid_field", "end")
        days = (e_date - s_date).days
        if days > 366:
            raise DomainError("command_too_large")
        return s_date, e_date, days
    if not isinstance(s_raw, str) or not isinstance(e_raw, str):
        raise DomainError("invalid_field", "start")
    try:
        s_dt, e_dt = datetime.fromisoformat(s_raw), datetime.fromisoformat(e_raw)
    except (ValueError, TypeError):
        raise DomainError("invalid_field", "start") from None
    for dt, fld in ((s_dt, "start"), (e_dt, "end")):
        if dt.tzinfo is None:
            raise DomainError("invalid_field", fld)
        try:
            if dt.utcoffset() is None:
                raise DomainError("invalid_field", fld)
        except Exception:
            raise DomainError("invalid_field", fld) from None
    s_utc = _to_utc(s_dt)
    e_utc = _to_utc(e_dt)
    if e_utc <= s_utc:
        raise DomainError("invalid_field", "end")
    dur = e_utc - s_utc
    if dur > timedelta(days=366):
        raise DomainError("command_too_large")
    return s_dt, e_dt, dur


def _expand(
    record: dict,
    range_start: datetime,
    range_end: datetime,
    display_timezone: str = "UTC",
    limit: int = 1000,
) -> list[dict]:
    if not isinstance(record, dict):
        raise DomainError("invalid_field", "record")
    fields(
        record,
        {
            "id",
            "title",
            "description",
            "location",
            "start",
            "end",
            "all_day",
            "timezone",
            "rule",
            "status",
        },
        {"id", "title", "start", "end", "all_day", "timezone", "status"},
    )
    rec_id = text(record["id"], "id", maximum=100)
    title = text(record["title"], "title", maximum=255)
    description = _parse_opt_text(record.get("description"), "description", 2000)
    location = _parse_opt_text(record.get("location"), "location", 500)
    if type(record["all_day"]) is not bool:
        raise DomainError("invalid_field", "all_day")
    all_day: bool = record["all_day"]
    tz_name = validate_timezone(record["timezone"])
    disp_tz_name = validate_timezone(display_timezone)
    disp_tz = ZoneInfo(disp_tz_name)
    raw_rule = record.get("rule")
    rule = validate_rule(raw_rule) if raw_rule is not None else None
    status = enum(record["status"], STATUS_CHOICES, "status")
    s_val, e_val, duration = _parse_event_times(record)

    if rule is not None:
        r_start_date = date.fromisoformat(rule["start_date"])
        if rule["timezone"] != tz_name:
            raise DomainError("invalid_field", "rule")
        if all_day:
            if rule["time"] != "00:00" or s_val != r_start_date:
                raise DomainError("invalid_field", "rule")
        else:
            s_local = s_val.astimezone(ZoneInfo(tz_name))
            if s_local.second != 0 or s_local.microsecond != 0:
                raise DomainError("invalid_field", "start")
            r_clock = clock(rule["time"])
            if s_local.date() != r_start_date or s_local.strftime("%H:%M") != r_clock:
                raise DomainError("invalid_field", "rule")
            first = local_clock(r_start_date, r_clock, tz_name)
            if first is None or _to_utc(first) != _to_utc(s_val):
                raise DomainError("invalid_field", "start")

    if type(limit) is not int or not 1 <= limit <= 5000:
        raise DomainError("invalid_field", "limit")
    q_start_utc, q_end_utc = _check_query_range(range_start, range_end)
    if status == "cancelled":
        return []

    results: list[dict] = []

    def make_entry(occ_id: str, s_str: str, e_str: str, sort_key: datetime) -> dict:
        return {
            "id": occ_id,
            "event_id": rec_id,
            "title": title,
            "description": description,
            "location": location,
            "start": s_str,
            "end": e_str,
            "all_day": all_day,
            "timezone": tz_name,
            "status": status,
            "_sort_key": sort_key,
        }

    if rule is None:
        if all_day:
            s_utc = _to_utc(datetime.combine(s_val, time.min, disp_tz))
            e_utc = _to_utc(datetime.combine(e_val, time.min, disp_tz))
            if e_utc > q_start_utc and s_utc < q_end_utc:
                results.append(make_entry(rec_id, s_val.isoformat(), e_val.isoformat(), s_utc))
        else:
            s_utc, e_utc = _to_utc(s_val), _to_utc(e_val)
            if e_utc > q_start_utc and s_utc < q_end_utc:
                s_iso = s_utc.isoformat().replace("+00:00", "Z")
                e_iso = e_utc.isoformat().replace("+00:00", "Z")
                results.append(make_entry(rec_id, s_iso, e_iso, s_utc))
        return [{k: v for k, v in r.items() if k != "_sort_key"} for r in results]

    rec_tz = ZoneInfo(tz_name)
    r_start_date = date.fromisoformat(rule["start_date"])

    if all_day:
        q_start_disp = range_start.astimezone(disp_tz).date()
        q_end_disp = range_end.astimezone(disp_tz).date()
        scan_start = max(r_start_date, _safe_add_days(q_start_disp, -int(duration)))
        scan_end = _safe_add_days(q_end_disp, 1)
        curr = scan_start
        while curr <= scan_end:
            if matches(rule, curr):
                cand_s = curr
                cand_e = _safe_add_days(cand_s, int(duration))
                s_utc = _to_utc(datetime.combine(cand_s, time.min, disp_tz))
                e_utc = _to_utc(datetime.combine(cand_e, time.min, disp_tz))
                if e_utc > q_start_utc and s_utc < q_end_utc:
                    if len(results) >= limit:
                        raise DomainError("command_too_large")
                    results.append(
                        make_entry(
                            f"{rec_id}@{cand_s.isoformat()}",
                            cand_s.isoformat(),
                            cand_e.isoformat(),
                            s_utc,
                        )
                    )
            if curr >= scan_end:
                break
            curr = _safe_add_days(curr, 1)
    else:
        dur_days = int(duration.total_seconds() // 86400) + 2
        q_start_rec = range_start.astimezone(rec_tz).date()
        q_end_rec = range_end.astimezone(rec_tz).date()
        scan_start = max(r_start_date, _safe_add_days(q_start_rec, -dur_days))
        scan_end = _safe_add_days(q_end_rec, 2)
        curr = scan_start
        while curr <= scan_end:
            if matches(rule, curr):
                cand_s_loc = local_clock(curr, rule["time"], tz_name)
                if cand_s_loc is not None:
                    s_utc = _to_utc(cand_s_loc)
                    e_utc = s_utc + duration
                    _check_year(e_utc.year)
                    if e_utc > q_start_utc and s_utc < q_end_utc:
                        if len(results) >= limit:
                            raise DomainError("command_too_large")
                        s_iso = s_utc.isoformat().replace("+00:00", "Z")
                        e_iso = e_utc.isoformat().replace("+00:00", "Z")
                        results.append(
                            make_entry(f"{rec_id}@{curr.isoformat()}", s_iso, e_iso, s_utc)
                        )
            if curr >= scan_end:
                break
            curr = _safe_add_days(curr, 1)

    results.sort(key=lambda x: x["_sort_key"])
    return [{k: v for k, v in r.items() if k != "_sort_key"} for r in results]


def expand(record, range_start, range_end, display_timezone="UTC", limit=1000):
    """Convert unrepresentable timezone/date arithmetic to a stable domain error."""
    try:
        return _expand(record, range_start, range_end, display_timezone, limit)
    except OverflowError:
        raise DomainError("command_too_large") from None
