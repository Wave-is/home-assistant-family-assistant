"""Comprehensive pure tests for Kid Control schedule status calculation."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from custom_components.family_assistant.network.kid_status import schedule_status


def test_standard_date_allowed():
    """Standard Monday within 08:00-20:00 in UTC."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-20:00",
    }
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)  # Monday 10:00 UTC
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "schedule",
        "allows": True,
        "next_change_at": "2026-09-07T20:00:00+00:00",
        "next_allows": False,
        "remaining_minutes": 600,
    }


def test_standard_date_before_window():
    """Standard Monday before 08:00-20:00 opens."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-20:00",
    }
    now = datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC)  # Monday 06:00 UTC
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "schedule",
        "allows": False,
        "next_change_at": "2026-09-07T08:00:00+00:00",
        "next_allows": True,
        "remaining_minutes": None,
    }


def test_standard_date_after_window():
    """Standard Monday after 08:00-20:00 closes, next change is Tuesday 08:00."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-20:00",
        "tue": "08:00-20:00",
    }
    now = datetime(2026, 9, 7, 21, 0, 0, tzinfo=UTC)  # Monday 21:00 UTC
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "schedule",
        "allows": False,
        "next_change_at": "2026-09-08T08:00:00+00:00",
        "next_allows": True,
        "remaining_minutes": None,
    }


def test_multiple_windows_same_day():
    """Multiple intervals on same day: 08:00-12:00 and 14:00-18:00."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-12:00,14:00-18:00",
    }
    # 1. Inside first window at 10:00
    now1 = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    s1 = schedule_status(row, now1, "UTC")
    assert s1["allows"] is True
    assert s1["next_change_at"] == "2026-09-07T12:00:00+00:00"
    assert s1["next_allows"] is False
    assert s1["remaining_minutes"] == 120

    # 2. In between windows at 13:00
    now2 = datetime(2026, 9, 7, 13, 0, 0, tzinfo=UTC)
    s2 = schedule_status(row, now2, "UTC")
    assert s2["allows"] is False
    assert s2["next_change_at"] == "2026-09-07T14:00:00+00:00"
    assert s2["next_allows"] is True
    assert s2["remaining_minutes"] is None

    # 3. Inside second window at 15:00
    now3 = datetime(2026, 9, 7, 15, 0, 0, tzinfo=UTC)
    s3 = schedule_status(row, now3, "UTC")
    assert s3["allows"] is True
    assert s3["next_change_at"] == "2026-09-07T18:00:00+00:00"
    assert s3["next_allows"] is False
    assert s3["remaining_minutes"] == 180


def test_native_profile_durations():
    """Consume RouterOS native durations like 8h-22h and 7h30m-1d."""
    row = {
        "name": "Child",
        "disabled": "no",
        "paused": "no",
        "mon": "8h-22h",
        "tue": "7h30m-1d",
    }
    now_mon = datetime(2026, 9, 7, 9, 0, 0, tzinfo=UTC)
    s_mon = schedule_status(row, now_mon, "UTC")
    assert s_mon["mode"] == "schedule"
    assert s_mon["allows"] is True
    assert s_mon["next_change_at"] == "2026-09-07T22:00:00+00:00"


def test_respect_disabled_before_paused():
    """Disabled takes priority over paused; mode is unrestricted."""
    row = {
        "name": "Child",
        "disabled": "yes",
        "paused": "yes",
        "mon": "08:00-20:00",
    }
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "unrestricted",
        "allows": True,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


def test_paused_mode():
    """Paused with disabled=false returns mode paused."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "true",
        "mon": "08:00-20:00",
    }
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "paused",
        "allows": False,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


def test_all_week_open():
    """All days configured 00:00-24:00 (or native 0h-24h)."""
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        **{d: "00:00-24:00" for d in days},
    }
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "schedule",
        "allows": True,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


def test_all_week_closed():
    """All days configured with empty windows."""
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        **{d: "" for d in days},
    }
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "schedule",
        "allows": False,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


def test_midnight_continuity():
    """Monday 20:00-24:00 seamlessly joins Tuesday 00:00-08:00 without phantom midnight event."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "20:00-24:00",
        "tue": "00:00-08:00",
    }
    # At Monday 23:30, next closure is Tuesday 08:00
    now_mon = datetime(2026, 9, 7, 23, 30, 0, tzinfo=UTC)
    s_mon = schedule_status(row, now_mon, "UTC")
    assert s_mon["allows"] is True
    assert s_mon["next_change_at"] == "2026-09-08T08:00:00+00:00"
    assert s_mon["next_allows"] is False
    assert s_mon["remaining_minutes"] == 510  # 30m + 480m = 510m

    # Exactly at Tuesday 00:00:00, still allowed, next closure is 08:00
    now_tue = datetime(2026, 9, 8, 0, 0, 0, tzinfo=UTC)
    s_tue = schedule_status(row, now_tue, "UTC")
    assert s_tue["allows"] is True
    assert s_tue["next_change_at"] == "2026-09-08T08:00:00+00:00"
    assert s_tue["next_allows"] is False
    assert s_tue["remaining_minutes"] == 480


def test_midnight_closure_when_next_day_closed():
    """Monday 20:00-24:00 closes at midnight because Tuesday starts at 08:00."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "20:00-24:00",
        "tue": "08:00-16:00",
    }
    now = datetime(2026, 9, 7, 23, 45, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status["allows"] is True
    assert status["next_change_at"] == "2026-09-08T00:00:00+00:00"
    assert status["next_allows"] is False
    assert status["remaining_minutes"] == 15


def test_adjacent_intervals_merged_no_phantom():
    """Same-day adjacent intervals 08:00-12:00,12:00-16:00 have no phantom event at 12:00."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-12:00,12:00-16:00",
    }
    now = datetime(2026, 9, 7, 11, 45, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status["allows"] is True
    assert status["next_change_at"] == "2026-09-07T16:00:00+00:00"
    assert status["next_allows"] is False
    assert status["remaining_minutes"] == 255


def test_exact_boundary_semantics():
    """Test start inclusive [start, end) and end exclusive."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-12:00",
    }
    # 1. 1 microsecond before start: False
    t_before = datetime(2026, 9, 7, 7, 59, 59, 999999, tzinfo=UTC)
    s_before = schedule_status(row, t_before, "UTC")
    assert s_before["allows"] is False
    assert s_before["next_change_at"] == "2026-09-07T08:00:00+00:00"
    assert s_before["next_allows"] is True

    # 2. Exactly at start: True
    t_start = datetime(2026, 9, 7, 8, 0, 0, 0, tzinfo=UTC)
    s_start = schedule_status(row, t_start, "UTC")
    assert s_start["allows"] is True
    assert s_start["next_change_at"] == "2026-09-07T12:00:00+00:00"
    assert s_start["next_allows"] is False
    assert s_start["remaining_minutes"] == 240

    # 3. 1 microsecond before end: True, 1 minute remaining ceil
    t_end_minus = datetime(2026, 9, 7, 11, 59, 59, 999999, tzinfo=UTC)
    s_end_minus = schedule_status(row, t_end_minus, "UTC")
    assert s_end_minus["allows"] is True
    assert s_end_minus["next_change_at"] == "2026-09-07T12:00:00+00:00"
    assert s_end_minus["next_allows"] is False
    assert s_end_minus["remaining_minutes"] == 1

    # 4. Exactly at end: False
    t_end = datetime(2026, 9, 7, 12, 0, 0, 0, tzinfo=UTC)
    s_end = schedule_status(row, t_end, "UTC")
    assert s_end["allows"] is False
    assert s_end["remaining_minutes"] is None

    # 5. Non-whole minute ceiling (e.g. 29m 30s remaining -> 30)
    t_mid = datetime(2026, 9, 7, 11, 30, 30, 0, tzinfo=UTC)
    s_mid = schedule_status(row, t_mid, "UTC")
    assert s_mid["allows"] is True
    assert s_mid["remaining_minutes"] == 30


def test_non_hour_offset_iana():
    """Asia/Kolkata (UTC+05:30) timezone with local schedule."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-20:00",
    }
    # Monday 08:00 IST is Monday 02:30 UTC
    # Monday 20:00 IST is Monday 14:30 UTC
    now = datetime(2026, 9, 7, 4, 0, 0, tzinfo=UTC)  # 09:30 IST (allowed)
    status = schedule_status(row, now, "Asia/Kolkata")
    assert status["allows"] is True
    assert status["next_change_at"] == "2026-09-07T14:30:00+00:00"
    assert status["next_allows"] is False
    assert status["remaining_minutes"] == 630  # from 04:00 UTC to 14:30 UTC = 10.5h = 630m


def test_non_hour_offset_fixed_string_and_tzinfo():
    """Fixed offset string '+05:30' and datetime.timezone object."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-20:00",
    }
    now = datetime(2026, 9, 7, 4, 0, 0, tzinfo=UTC)

    # String fixed offset
    s_str = schedule_status(row, now, "+05:30")
    assert s_str["allows"] is True
    assert s_str["next_change_at"] == "2026-09-07T14:30:00+00:00"

    # tzinfo object
    tz_obj = timezone(timedelta(hours=5, minutes=30))
    s_obj = schedule_status(row, now, tz_obj)
    assert s_obj["allows"] is True
    assert s_obj["next_change_at"] == "2026-09-07T14:30:00+00:00"


def test_dst_gap_spring_forward():
    """Europe/London gap on 2026-03-29: 01:00 GMT jumps to 02:00 BST at 01:00 UTC."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "sun": "01:30-03:00",
    }
    tz = ZoneInfo("Europe/London")

    # 1. At 00:50 UTC (00:50 GMT): closed.
    # At 01:00 UTC, clock jumps to 02:00 BST (inside 01:30-03:00)!
    now_before = datetime(2026, 3, 29, 0, 50, 0, tzinfo=UTC)
    s_before = schedule_status(row, now_before, tz)
    assert s_before["allows"] is False
    assert s_before["next_change_at"] == "2026-03-29T01:00:00+00:00"
    assert s_before["next_allows"] is True

    # 2. At 01:10 UTC (02:10 BST): allowed. Closes at 02:00 UTC (03:00 BST)!
    now_during = datetime(2026, 3, 29, 1, 10, 0, tzinfo=UTC)
    s_during = schedule_status(row, now_during, tz)
    assert s_during["allows"] is True
    assert s_during["next_change_at"] == "2026-03-29T02:00:00+00:00"
    assert s_during["next_allows"] is False
    assert s_during["remaining_minutes"] == 50


def test_dst_gap_spring_forward_subsecond_precision():
    """Subsecond now yields a whole-second transition across the spring-forward gap."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "sun": "01:30-03:00",
    }
    tz = "Europe/London"
    now = datetime(2026, 3, 29, 0, 50, 0, 123456, tzinfo=UTC)
    res = schedule_status(row, now, tz)
    assert res["allows"] is False
    assert res["next_change_at"] == "2026-03-29T01:00:00+00:00"
    assert res["next_allows"] is True


def test_dst_fold_reopening_local_zoneinfo_both_folds():
    """Europe/London fold 2026-10-25: 00:30-01:30 reopens at 01:00 UTC (01:00 GMT, fold 1)."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "sun": "00:30-01:30",
    }
    tz = ZoneInfo("Europe/London")

    # Fold 0: 01:50 BST is 00:50 UTC, closed.
    # The clock falls back to 01:00 GMT at 01:00 UTC, reopening 00:30-01:30 until 01:30 UTC.
    now_fold0 = datetime(2026, 10, 25, 1, 50, tzinfo=tz, fold=0)
    res_fold0 = schedule_status(row, now_fold0, tz)
    assert res_fold0["allows"] is False
    assert res_fold0["next_change_at"] == "2026-10-25T01:00:00+00:00"
    assert res_fold0["next_allows"] is True
    assert res_fold0["remaining_minutes"] is None

    # Fold 1: 01:10 GMT is 01:10 UTC, inside reopened window. Next closes at 01:30 UTC (01:30 GMT).
    now_fold1 = datetime(2026, 10, 25, 1, 10, tzinfo=tz, fold=1)
    res_fold1 = schedule_status(row, now_fold1, tz)
    assert res_fold1["allows"] is True
    assert res_fold1["next_change_at"] == "2026-10-25T01:30:00+00:00"
    assert res_fold1["next_allows"] is False
    assert res_fold1["remaining_minutes"] == 20

    # Fold 1 after window: 01:50 GMT is 01:50 UTC, closed. Next opening is next Sunday 00:30 GMT.
    now_fold1_after = datetime(2026, 10, 25, 1, 50, tzinfo=tz, fold=1)
    res_fold1_after = schedule_status(row, now_fold1_after, tz)
    assert res_fold1_after["allows"] is False
    assert res_fold1_after["next_change_at"] == "2026-11-01T00:30:00+00:00"
    assert res_fold1_after["next_allows"] is True


def test_dst_gap_entirely_skipped_window():
    """If window is 01:00-02:00 during spring forward, clock never reaches it."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "sun": "01:00-02:00",
        "mon": "08:00-12:00",
    }
    now = datetime(2026, 3, 29, 0, 30, 0, tzinfo=UTC)
    status = schedule_status(row, now, "Europe/London")
    assert status["allows"] is False
    # Next opening is Monday 08:00 BST = 07:00 UTC
    assert status["next_change_at"] == "2026-03-30T07:00:00+00:00"


def test_dst_fold_fall_back():
    """Europe/London fold on 2026-10-25: 02:00 BST falls back to 01:00 GMT at 01:00 UTC."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "sun": "01:15-01:45",
    }
    tz = ZoneInfo("Europe/London")

    # Pass 1 (fold 0):
    # 00:00 UTC -> 01:00 BST (closed), opens at 00:15 UTC (01:15 BST)
    s1 = schedule_status(row, datetime(2026, 10, 25, 0, 0, 0, tzinfo=UTC), tz)
    assert s1["allows"] is False
    assert s1["next_change_at"] == "2026-10-25T00:15:00+00:00"

    # 00:20 UTC -> 01:20 BST (allowed), closes at 00:45 UTC (01:45 BST)
    s2 = schedule_status(row, datetime(2026, 10, 25, 0, 20, 0, tzinfo=UTC), tz)
    assert s2["allows"] is True
    assert s2["next_change_at"] == "2026-10-25T00:45:00+00:00"

    # 00:50 UTC -> 01:50 BST (closed), opens at 01:15 UTC (01:15 GMT, fold 1)
    s3 = schedule_status(row, datetime(2026, 10, 25, 0, 50, 0, tzinfo=UTC), tz)
    assert s3["allows"] is False
    assert s3["next_change_at"] == "2026-10-25T01:15:00+00:00"

    # Pass 2 (fold 1):
    # 01:20 UTC -> 01:20 GMT (allowed), closes at 01:45 UTC (01:45 GMT)
    s4 = schedule_status(row, datetime(2026, 10, 25, 1, 20, 0, tzinfo=UTC), tz)
    assert s4["allows"] is True
    assert s4["next_change_at"] == "2026-10-25T01:45:00+00:00"


def test_dst_fold_continuous_window():
    """Schedule 01:00-02:00 stays open throughout the entire 2-hour fold period."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "sun": "01:00-02:00",
    }
    tz = ZoneInfo("Europe/London")
    # At 00:30 UTC (01:30 BST fold 0), closure is at 02:00 UTC (02:00 GMT)!
    now = datetime(2026, 10, 25, 0, 30, 0, tzinfo=UTC)
    status = schedule_status(row, now, tz)
    assert status["allows"] is True
    assert status["next_change_at"] == "2026-10-25T02:00:00+00:00"
    assert status["remaining_minutes"] == 90


def test_tur_schedule_returns_unknown():
    """Non-empty tur-* schedule whose native semantics are unmodeled returns unknown."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-20:00",
        "tur-mon": "08:00-12:00",
    }
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status == {
        "mode": "unknown",
        "allows": None,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


def test_empty_tur_schedule_is_ignored():
    """Empty tur-* schedules do not trigger unknown mode."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": "false",
        "mon": "08:00-20:00",
        "tur-mon": "",
    }
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    assert status["mode"] == "schedule"
    assert status["allows"] is True


@pytest.mark.parametrize(
    "invalid_row",
    [
        None,
        123,
        "profile",
        [],
        {"name": ""},
        {"name": "x" * 200},
        {"name": "Child", "disabled": "maybe"},
        {"name": "Child", "paused": "invalid"},
        {"name": "Child", "mon": "invalid"},
        {"name": "Child", "mon": "25:00-26:00"},
        {"name": "Child", "mon": "08:00-08:00"},
        {"name": "Child", "mon": "22:00-08:00"},
    ],
)
def test_invalid_row_fails_conservatively(invalid_row):
    """Invalid profile inputs return unknown rather than raising."""
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    status = schedule_status(invalid_row, now, "UTC")
    assert status == {
        "mode": "unknown",
        "allows": None,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


@pytest.mark.parametrize(
    "invalid_now",
    [
        None,
        datetime(2026, 9, 7, 10, 0, 0),  # Naive datetime
        "2026-09-07T10:00:00Z",
        1700000000,
    ],
)
def test_invalid_now_fails_conservatively(invalid_now):
    """Naive datetimes and non-datetimes fail conservatively."""
    row = {"name": "Child", "mon": "08:00-20:00"}
    status = schedule_status(row, invalid_now, "UTC")
    assert status == {
        "mode": "unknown",
        "allows": None,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


@pytest.mark.parametrize(
    "invalid_tz",
    [
        None,
        "",
        "   ",
        "Invalid/Timezone",
        123,
        [],
    ],
)
def test_invalid_timezone_fails_conservatively(invalid_tz):
    """Invalid timezone values fail conservatively."""
    row = {"name": "Child", "mon": "08:00-20:00"}
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, invalid_tz)
    assert status == {
        "mode": "unknown",
        "allows": None,
        "next_change_at": None,
        "next_allows": None,
        "remaining_minutes": None,
    }


def test_no_mutation_of_input():
    """Function must not mutate row input or any nested structures."""
    row = {
        "name": "Child",
        "disabled": "false",
        "paused": False,  # bool form should not be replaced in caller's dict
        "mon": "8h-20h",
    }
    snapshot = deepcopy(row)
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    schedule_status(row, now, "UTC")
    assert row == snapshot
    assert row["paused"] is False  # stayed bool in caller's dict


def test_result_is_json_serializable():
    """Return dictionary must be strictly JSON-serializable."""
    row = {"name": "Child", "mon": "08:00-20:00"}
    now = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    status = schedule_status(row, now, "UTC")
    dumped = json.dumps(status)
    loaded = json.loads(dumped)
    assert loaded == status
