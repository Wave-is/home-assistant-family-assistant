"""Comprehensive tests for bounded pure calendar occurrence expansion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.family_assistant.domain.calendar_occurrences import expand
from custom_components.family_assistant.domain.validation import DomainError


def _rec(all_day: bool = False, **kwargs) -> dict:
    if all_day:
        base = {
            "id": "evt-1",
            "title": "All Day Event",
            "description": "Desc",
            "location": "Home",
            "start": "2026-06-01",
            "end": "2026-06-02",
            "all_day": True,
            "timezone": "UTC",
            "rule": None,
            "status": "confirmed",
        }
    else:
        base = {
            "id": "evt-1",
            "title": "Timed Event",
            "description": "Desc",
            "location": "Home",
            "start": "2026-06-01T10:00:00Z",
            "end": "2026-06-01T11:00:00Z",
            "all_day": False,
            "timezone": "UTC",
            "rule": None,
            "status": "confirmed",
        }
    base.update(kwargs)
    return base


def test_oneoff_overlap_and_exclusive_bounds():
    rec = _rec(start="2026-06-01T10:00:00Z", end="2026-06-01T12:00:00Z")
    assert (
        expand(rec, datetime(2026, 6, 1, 12, tzinfo=UTC), datetime(2026, 6, 1, 14, tzinfo=UTC))
        == []
    )
    assert (
        expand(rec, datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 10, tzinfo=UTC)) == []
    )
    res = expand(rec, datetime(2026, 6, 1, 11, tzinfo=UTC), datetime(2026, 6, 1, 13, tzinfo=UTC))
    assert len(res) == 1
    assert res[0]["id"] == "evt-1" and res[0]["event_id"] == "evt-1"
    assert res[0]["start"] == "2026-06-01T10:00:00Z" and res[0]["end"] == "2026-06-01T12:00:00Z"


def test_allday_displayzone_ordering_and_negative_offset():
    rec = _rec(all_day=True, start="2026-06-02", end="2026-06-03")
    ny = "America/New_York"
    q_start = datetime(2026, 6, 1, 23, tzinfo=ZoneInfo(ny))
    q_end = datetime(2026, 6, 2, 0, tzinfo=ZoneInfo(ny))
    assert expand(rec, q_start, q_end, display_timezone=ny) == []
    q_end2 = datetime(2026, 6, 2, 1, tzinfo=ZoneInfo(ny))
    res = expand(rec, q_start, q_end2, display_timezone=ny)
    assert len(res) == 1
    assert res[0]["start"] == "2026-06-02" and res[0]["end"] == "2026-06-03"


def test_recurring_daily_weekly_monthly_exclusions_until():
    rule = {
        "frequency": "daily",
        "interval": 2,
        "start_date": "2026-06-01",
        "time": "10:00",
        "timezone": "UTC",
        "exceptions": ["2026-06-03"],
        "until": "2026-06-07",
    }
    res = expand(
        _rec(rule=rule), datetime(2026, 6, 1, 0, tzinfo=UTC), datetime(2026, 6, 10, 0, tzinfo=UTC)
    )
    assert len(res) == 3
    assert [r["id"] for r in res] == ["evt-1@2026-06-01", "evt-1@2026-06-05", "evt-1@2026-06-07"]
    w_rule = {
        "frequency": "weekly",
        "interval": 1,
        "start_date": "2026-06-01",
        "weekdays": [0, 2],
        "time": "10:00",
        "timezone": "UTC",
    }
    assert (
        len(
            expand(
                _rec(rule=w_rule),
                datetime(2026, 6, 1, 0, tzinfo=UTC),
                datetime(2026, 6, 8, 0, tzinfo=UTC),
            )
        )
        == 2
    )
    m_rule = {
        "frequency": "monthly",
        "interval": 1,
        "start_date": "2026-01-15",
        "month_day": 15,
        "time": "10:00",
        "timezone": "UTC",
    }
    res_m = expand(
        _rec(start="2026-01-15T10:00:00Z", end="2026-01-15T11:00:00Z", rule=m_rule),
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 4, 1, tzinfo=UTC),
    )
    assert len(res_m) == 3


def test_dst_gap_and_fold_with_elapsed_duration():
    rule_spring = {
        "frequency": "daily",
        "interval": 1,
        "start_date": "2026-03-28",
        "time": "03:30",
        "timezone": "Europe/Kyiv",
    }
    rec_spring = _rec(
        start="2026-03-28T03:30:00+02:00",
        end="2026-03-28T04:30:00+02:00",
        timezone="Europe/Kyiv",
        rule=rule_spring,
    )
    res_sp = expand(
        rec_spring,
        datetime(2026, 3, 28, 0, tzinfo=ZoneInfo("Europe/Kyiv")),
        datetime(2026, 3, 31, 0, tzinfo=ZoneInfo("Europe/Kyiv")),
    )
    assert [r["id"] for r in res_sp] == ["evt-1@2026-03-28", "evt-1@2026-03-30"]

    rule_fall = {
        "frequency": "daily",
        "interval": 1,
        "start_date": "2026-10-24",
        "time": "03:30",
        "timezone": "Europe/Kyiv",
    }
    rec_fall = _rec(
        start="2026-10-24T03:30:00+03:00",
        end="2026-10-24T05:00:00+03:00",
        timezone="Europe/Kyiv",
        rule=rule_fall,
    )
    res_fa = expand(
        rec_fall,
        datetime(2026, 10, 24, 0, tzinfo=ZoneInfo("Europe/Kyiv")),
        datetime(2026, 10, 26, 0, tzinfo=ZoneInfo("Europe/Kyiv")),
    )
    assert len(res_fa) == 2
    t0_s, t0_e = (
        datetime.fromisoformat(res_fa[1]["start"]),
        datetime.fromisoformat(res_fa[1]["end"]),
    )
    assert (t0_e - t0_s) == timedelta(hours=1, minutes=30)


def test_same_zone_fold_query_distinction():
    tz = ZoneInfo("Europe/Kyiv")
    # First 03:30 fold 0 is UTC 00:30; second 03:30 fold 1 is UTC 01:30
    q1 = datetime(2026, 10, 25, 3, 30, fold=0, tzinfo=tz)
    q2 = datetime(2026, 10, 25, 3, 30, fold=1, tzinfo=tz)
    rec = _rec(start="2026-10-25T00:00:00Z", end="2026-10-25T01:00:00Z")
    # The folded query spans an hour in UTC and overlaps the event.
    assert len(expand(rec, q1, q2)) == 1
    # Reversed or equal without fold difference would fail
    with pytest.raises(DomainError):
        expand(rec, q2, q1)


def test_empty_optional_fields_allowed():
    rec = _rec(description="", location="")
    res = expand(rec, datetime(2026, 6, 1, 0, tzinfo=UTC), datetime(2026, 6, 2, 0, tzinfo=UTC))
    assert len(res) == 1
    assert res[0]["description"] == "" and res[0]["location"] == ""


def test_malformed_exact_date_rejected():
    for bad_date in ("2026-W23-1", "2026/06/01", "2026-6-1", "2026-06-01T"):
        with pytest.raises(DomainError):
            expand(
                _rec(all_day=True, start=bad_date, end="2026-06-02"),
                datetime(2026, 6, 1, tzinfo=UTC),
                datetime(2026, 6, 2, tzinfo=UTC),
            )


def test_cancelled_and_validation_before_trusting_status():
    rec = _rec(status="cancelled")
    assert (
        expand(rec, datetime(2026, 6, 1, 0, tzinfo=UTC), datetime(2026, 6, 2, 0, tzinfo=UTC)) == []
    )
    with pytest.raises(DomainError):
        expand(
            _rec(status="cancelled", start="bad-start"),
            datetime(2026, 6, 1, 0, tzinfo=UTC),
            datetime(2026, 6, 2, 0, tzinfo=UTC),
        )
    with pytest.raises(DomainError):
        expand(
            _rec(status="unknown"),
            datetime(2026, 6, 1, 0, tzinfo=UTC),
            datetime(2026, 6, 2, 0, tzinfo=UTC),
        )


def test_series_first_start_cannot_silently_move_from_second_fold_to_first():
    rule = {
        "frequency": "daily",
        "start_date": "2026-10-25",
        "time": "03:30",
        "timezone": "Europe/Kyiv",
    }
    with pytest.raises(DomainError, match="invalid_field"):
        expand(
            _rec(
                start="2026-10-25T03:30:00+02:00",
                end="2026-10-25T04:30:00+02:00",
                timezone="Europe/Kyiv",
                rule=rule,
            ),
            datetime(2026, 10, 25, tzinfo=UTC),
            datetime(2026, 10, 26, tzinfo=UTC),
        )


def test_long_duration_overlap_bounded_and_ancient_series():
    rule = {
        "frequency": "daily",
        "interval": 30,
        "start_date": "2020-01-01",
        "time": "10:00",
        "timezone": "UTC",
    }
    rec = _rec(start="2020-01-01T10:00:00Z", end="2020-01-11T10:00:00Z", rule=rule)
    res = expand(rec, datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 3, tzinfo=UTC))
    assert len(res) == 1
    assert res[0]["id"] == "evt-1@2026-05-29"


def test_invalid_ranges_limits_overflow_and_naive_datetimes():
    rec = _rec()
    q_s, q_e = datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 2, tzinfo=UTC)
    with pytest.raises(DomainError):
        expand(rec, datetime(2026, 6, 1), q_e)
    with pytest.raises(DomainError):
        expand(rec, q_e, q_s)
    with pytest.raises(DomainError):
        expand(rec, q_s, q_s + timedelta(days=368))
    with pytest.raises(DomainError):
        expand(_rec(start="2026-01-01T00:00:00Z", end="2027-02-01T00:00:00Z"), q_s, q_e)
    with pytest.raises(DomainError):
        expand(rec, q_s, q_e, limit=0)
    with pytest.raises(DomainError):
        expand(rec, q_s, q_e, limit=5001)
    rule_daily = {
        "frequency": "daily",
        "interval": 1,
        "start_date": "2026-06-01",
        "time": "10:00",
        "timezone": "UTC",
    }
    with pytest.raises(DomainError) as exc:
        expand(_rec(rule=rule_daily), q_s, q_s + timedelta(days=10), limit=2)
    assert exc.value.code == "command_too_large"
    with pytest.raises(DomainError):
        expand(
            _rec(start="2026-06-01T10:00:15Z", end="2026-06-01T11:00:00Z", rule=rule_daily),
            q_s,
            q_e,
        )
    # A representable distant query is valid, even when it has no matches.
    assert (
        expand(
            rec,
            datetime(9999, 12, 30, tzinfo=UTC),
            datetime(9999, 12, 31, 23, tzinfo=ZoneInfo("Pacific/Auckland")),
        )
        == []
    )
    # Converting a positive offset at year 1 to UTC really does overflow.
    with pytest.raises(DomainError):
        expand(
            _rec(start="0001-01-01T00:00:00+14:00", end="0001-01-02T00:00:00+14:00"),
            q_s,
            q_e,
        )
