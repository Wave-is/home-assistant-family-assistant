"""Synthetic tests for pure weekly court period bounds and score summarization."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import pytest

from custom_components.family_assistant.domain.court_periods import period_bounds, summarize
from custom_components.family_assistant.domain.validation import DomainError


class NaiveTz(tzinfo):
    """Custom tzinfo returning None for utcoffset, representing naive/unspecified offset."""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return "NaiveTz"


def test_exact_boundary_half_open():
    now_exact = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
    start, end = period_bounds(now_exact, "UTC", weekday=0, clock="00:00")
    assert start == datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
    assert start <= now_exact < end

    just_before = now_exact - timedelta(microseconds=1)
    prev_start, prev_end = period_bounds(just_before, "UTC", weekday=0, clock="00:00")
    assert prev_start == datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
    assert prev_end == datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
    assert prev_start <= just_before < prev_end


def test_dst_short_week_gap_and_fold():
    # Europe/London DST transition spring 2026: March 29, 01:00 -> 02:00 (clocks jump forward 1 hr)
    # A boundary set at Sunday (weekday=6) 01:30 falls in the spring gap.
    now = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    start, end = period_bounds(now, "Europe/London", weekday=6, clock="01:30")
    # 01:30 doesn't exist on March 29 in London (gap jumps 01:00 GMT to 02:00 BST).
    # First valid wall minute is 02:00 BST -> 01:00 UTC
    assert start == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
    # The following Sunday April 5, 01:30 exists (01:30 BST = 00:30 UTC)
    assert end == datetime(2026, 4, 5, 0, 30, tzinfo=UTC)
    assert start <= now < end
    # Total duration of this spring week in UTC is 7 days minus 30 mins (167.5 hours)
    assert end - start == timedelta(days=6, hours=23, minutes=30)

    # London autumn 2026: October 25, 02:00 -> 01:00 (long week, fold 0 chosen).
    # 01:30 fold 0 is BST (00:30 UTC); fold 1 is GMT (01:30 UTC).
    now_autumn = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    start_fall, end_fall = period_bounds(now_autumn, "Europe/London", weekday=6, clock="01:30")
    assert start_fall == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    # Next Sunday Nov 1 is 01:30 GMT = 01:30 UTC
    assert end_fall == datetime(2026, 11, 1, 1, 30, tzinfo=UTC)
    assert start_fall <= now_autumn < end_fall
    # Total duration of this autumn week in UTC is 7 days plus 1 hour (169 hours)
    assert end_fall - start_fall == timedelta(days=7, hours=1)


def test_non_hour_timezone():
    # Asia/Kolkata is UTC+05:30
    now = datetime(2026, 9, 9, 10, 0, tzinfo=UTC)
    start, end = period_bounds(now, "Asia/Kolkata", weekday=2, clock="15:30")
    # Wednesday is weekday=2. 2026-09-09 is Wednesday.
    # 15:30 IST = 10:00 UTC
    assert start == datetime(2026, 9, 9, 10, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 16, 10, 0, tzinfo=UTC)


def test_timezone_aware_now_with_non_utc_offset():
    # now passed in with non-UTC offset (e.g. UTC+03:00)
    tz_plus3 = timezone(timedelta(hours=3))
    now = datetime(2026, 9, 9, 13, 0, tzinfo=tz_plus3)  # 10:00 UTC
    start, end = period_bounds(now, "Asia/Kolkata", weekday=2, clock="15:30")
    assert start == datetime(2026, 9, 9, 10, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
    assert start <= now < end


def test_samoa_dateline_skip_explicit_boundaries():
    # Apia (Pacific/Apia) skipped December 30, 2011 entirely (moved from UTC-10 to UTC+14).
    # Thursday Dec 29, 2011 was followed directly by Saturday Dec 31, 2011.
    # A period starting Friday (weekday=4) at 00:00 has no Friday Dec 30.
    # Scanning forward lands on Saturday Dec 31 at 00:00 local (which was 10:00 UTC on Dec 30).
    now = datetime(2011, 12, 31, 1, 0, tzinfo=ZoneInfo("Pacific/Apia"))
    start, end = period_bounds(now, "Pacific/Apia", weekday=4, clock="00:00")
    # Local Saturday 2011-12-31 00:00 in Apia (UTC+14) corresponds to 2011-12-30 10:00 UTC
    assert start == datetime(2011, 12, 30, 10, 0, tzinfo=UTC)
    # Next Friday 2012-01-06 00:00 in Apia (UTC+14) corresponds to 2012-01-05 10:00 UTC
    assert end == datetime(2012, 1, 5, 10, 0, tzinfo=UTC)
    assert start <= now.astimezone(UTC) < end
    # Duration in UTC is 6 days (due to the skipped 24-hour day)
    assert end - start == timedelta(days=6)


def test_year_limits_practical_and_overflow():
    start, end = period_bounds(datetime(1, 1, 2, tzinfo=UTC), "UTC")
    assert start == datetime(1, 1, 1, tzinfo=UTC)
    assert end == datetime(1, 1, 8, tzinfo=UTC)
    # Before epoch practical year 1900
    now_1900 = datetime(1900, 1, 3, 12, 0, tzinfo=UTC)  # Wednesday
    start_1900, end_1900 = period_bounds(now_1900, "UTC", weekday=0, clock="00:00")
    assert start_1900 == datetime(1900, 1, 1, 0, 0, tzinfo=UTC)
    assert end_1900 == datetime(1900, 1, 8, 0, 0, tzinfo=UTC)

    # Year 9999 near upper bound: base_d + timedelta(days=7) will overflow Python datetime year 9999
    now_9999 = datetime(9999, 12, 30, 12, 0, tzinfo=UTC)
    with pytest.raises(DomainError, match="invalid_field") as exc_info:
        period_bounds(now_9999, "UTC", weekday=0, clock="00:00")
    assert exc_info.value.field == "now"


def test_validation_period_bounds():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    # Naive now
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(datetime(2026, 9, 6, 12, 0), "UTC")
    assert exc.value.field == "now"
    # Custom tzinfo with utcoffset() returning None
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(datetime(2026, 9, 6, 12, 0, tzinfo=NaiveTz()), "UTC")
    assert exc.value.field == "now"
    # Non-datetime now
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds("2026-09-06T12:00:00Z", "UTC")
    assert exc.value.field == "now"
    # Invalid timezone
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(now, "Invalid/Zone")
    assert exc.value.field == "timezone"
    # Weekday not bool, must be int 0..6
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(now, "UTC", weekday=True)
    assert exc.value.field == "weekday"
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(now, "UTC", weekday=7)
    assert exc.value.field == "weekday"
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(now, "UTC", weekday=-1)
    assert exc.value.field == "weekday"
    # Clock exact HH:MM
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(now, "UTC", clock="24:00")
    assert exc.value.field == "clock"
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(now, "UTC", clock="7:00")
    assert exc.value.field == "clock"
    with pytest.raises(DomainError, match="invalid_field") as exc:
        period_bounds(now, "UTC", clock="07:00:00")
    assert exc.value.field == "clock"


def test_summarize_scores_and_reversals_no_mutation():
    start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)
    records = [
        {
            "id": "C000001",
            "member": "M000002",
            "points": 10,
            "status": "active",
            "created_at": "2026-09-02T10:00:00Z",
            "reason": "Cleaned room",
        },
        {
            "id": "C000002",
            "member": "M000002",
            "points": -5,
            "status": "active",
            "created_at": "2026-09-03T12:00:00Z",
            "reason": "Late for dinner",
        },
        {
            "id": "C000003",
            "member": "M000002",
            "points": -20,
            "status": "reversed",
            "created_at": "2026-09-04T08:00:00Z",
            "reason": "Misunderstanding",
            "reversal": {"reason": "Dismissed upon appeal"},
        },
        {
            "id": "C000004",
            "member": "M000001",
            "points": 15,
            "status": "active",
            "created_at": "2026-09-05T14:00:00Z",
            "reason": "Helped sibling",
        },
        # Outside period (too early)
        {
            "id": "C000000",
            "member": "M000001",
            "points": 10,
            "status": "active",
            "created_at": "2026-08-31T23:59:59Z",
            "reason": "Old",
        },
        # Outside period (exact end)
        {
            "id": "C000005",
            "member": "M000001",
            "points": 10,
            "status": "active",
            "created_at": "2026-09-08T00:00:00Z",
            "reason": "Next period",
        },
    ]
    snapshot = deepcopy(records)

    result = summarize(records, start, end)

    # Verify input not mutated
    assert records == snapshot

    # Verify events contains original IDs only
    assert result["events"] == ["C000001", "C000002", "C000003", "C000004"]

    # Verify rows sorted by member id
    rows = result["rows"]
    assert len(rows) == 2
    assert rows[0]["member"] == "M000001"
    assert rows[0]["active_positives"] == 15
    assert rows[0]["active_negatives"] == 0
    assert rows[0]["total"] == 15
    assert rows[0]["active_count"] == 1
    assert rows[0]["reversed_count"] == 0

    assert rows[1]["member"] == "M000002"
    assert rows[1]["active_positives"] == 10
    assert rows[1]["active_negatives"] == -5
    assert rows[1]["total"] == 5
    assert rows[1]["active_count"] == 2
    assert rows[1]["reversed_count"] == 1


def test_summarize_rejects_duplicate_record_ids():
    start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)
    duplicate_records = [
        {
            "id": "C000001",
            "member": "M000001",
            "points": 10,
            "status": "active",
            "created_at": "2026-09-02T10:00:00Z",
            "reason": "Cleaned room",
        },
        {
            "id": "C000001",
            "member": "M000001",
            "points": 10,
            "status": "active",
            "created_at": "2026-09-02T10:00:00Z",
            "reason": "Cleaned room",
        },
    ]
    with pytest.raises(DomainError, match="invalid_field") as exc:
        summarize(duplicate_records, start, end)
    assert exc.value.field == "id"


def test_summarize_rejects_malformed_and_naive():
    start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)

    # Naive bounds
    with pytest.raises(DomainError, match="invalid_field"):
        summarize([], datetime(2026, 9, 1, 0, 0), end)
    with pytest.raises(DomainError, match="invalid_field"):
        summarize([], start, datetime(2026, 9, 8, 0, 0))
    # Custom tzinfo with utcoffset() returning None
    with pytest.raises(DomainError, match="invalid_field"):
        summarize([], datetime(2026, 9, 1, 0, 0, tzinfo=NaiveTz()), end)
    # Inverted bounds
    with pytest.raises(DomainError, match="invalid_field"):
        summarize([], end, start)

    # Malformed points: bool, 0, out of range, float, str
    for bad_pts in (True, False, 0, 101, -101, 5.5, "10"):
        bad_rec = [
            {
                "id": "C01",
                "member": "M1",
                "points": bad_pts,
                "status": "active",
                "created_at": "2026-09-02T10:00:00Z",
            }
        ]
        with pytest.raises(DomainError, match="invalid_field"):
            summarize(bad_rec, start, end)

    # Naive or malformed created_at
    bad_time_rec = [
        {
            "id": "C01",
            "member": "M1",
            "points": 5,
            "status": "active",
            "created_at": "2026-09-02T10:00:00",
        }
    ]
    with pytest.raises(DomainError, match="invalid_field"):
        summarize(bad_time_rec, start, end)

    # Malformed status
    bad_status_rec = [
        {
            "id": "C01",
            "member": "M1",
            "points": 5,
            "status": "unknown",
            "created_at": "2026-09-02T10:00:00Z",
        }
    ]
    with pytest.raises(DomainError, match="invalid_field"):
        summarize(bad_status_rec, start, end)

    # Malformed / too long id and reason
    bad_id_rec = [
        {
            "id": "x" * 81,
            "member": "M1",
            "points": 5,
            "status": "active",
            "created_at": "2026-09-02T10:00:00Z",
        }
    ]
    with pytest.raises(DomainError, match="invalid_field"):
        summarize(bad_id_rec, start, end)

    bad_reason_rec = [
        {
            "id": "C01",
            "member": "M1",
            "points": 5,
            "status": "active",
            "created_at": "2026-09-02T10:00:00Z",
            "reason": "r" * 501,
        }
    ]
    with pytest.raises(DomainError, match="invalid_field"):
        summarize(bad_reason_rec, start, end)
