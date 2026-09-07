"""Bounded calendar proposals use the actual school lesson contract."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.school import _lessons
from custom_components.family_assistant.domain.school_import import calendar_week
from custom_components.family_assistant.domain.validation import DomainError


def event(**changes):
    return {
        "start": "2026-09-07T06:00:00+00:00",
        "end": "2026-09-07T06:45:00+00:00",
        "summary": "Fictional mathematics",
        "location": "12",
        **changes,
    }


def proposal(events, **changes):
    return calendar_week(
        events, **{"week_start": "2026-09-07", "timezone": "Europe/Kyiv", **changes}
    )


def test_real_contract_explicit_single_week_offset_conversion_sort_and_no_mutation():
    source = [event(start="2026-09-08T10:00:00+03:00", end="2026-09-08T10:45:00+03:00"), event()]
    before = deepcopy(source)
    result = proposal(source)
    assert result["valid_from"] == "2026-09-07" and result["valid_until"] == "2026-09-13"
    assert result["count"] == 2
    assert result["lessons"] == _lessons(result["lessons"])
    assert [(v["weekday"], v["start"], v["end"]) for v in result["lessons"]] == [
        (0, "09:00", "09:45"),
        (1, "10:00", "10:45"),
    ]
    assert all(v["materials"] == [] for v in result["lessons"])
    result["lessons"][0]["subject"] = "Changed output"
    assert source == before and proposal(source)["lessons"][0]["subject"] != "Changed output"


@pytest.mark.parametrize(
    "events",
    [
        None,
        {},
        "private",
        [],
        [event()] * 101,
        [None],
        [{"start": "private"}],
        [{**event(), "description": "private"}],
        [event(summary=None)],
        [event(location=False)],
    ],
)
def test_invalid_shapes_are_fixed_errors(events):
    with pytest.raises(DomainError) as failure:
        proposal(events)
    assert failure.value.code == "invalid_field" and "private" not in str(failure.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"start": "2026-09-07", "end": "2026-09-08"},
        {"start": "2026-09-07T09:00:00"},
        {"start": "2026-09-07T06:00:01Z"},
        {"end": "2026-09-07T06:45:00.001Z"},
        {"end": "2026-09-07T06:00:00Z"},
        {"end": "2026-09-07T05:00:00Z"},
        {"start": "2026-09-06T06:00:00Z", "end": "2026-09-06T06:45:00Z"},
        {"start": "2026-09-14T06:00:00Z", "end": "2026-09-14T06:45:00Z"},
        {"start": "2026-09-07T20:45:00Z", "end": "2026-09-07T21:30:00Z"},
        {"summary": ""},
        {"summary": "x" * 121},
        {"location": "x" * 81},
        {"start": "x" * 100000},
    ],
)
def test_unrepresentable_events_refused_without_dropping_rows(changes):
    with pytest.raises(DomainError):
        proposal([event(**changes)])


@pytest.mark.parametrize(
    "week",
    [None, True, "2026-09-08", "2026-W37-1", "2026-9-7", "2026-02-30", "0000-01-01", "9999-12-27"],
)
def test_invalid_week(week):
    with pytest.raises(DomainError):
        proposal([event()], week_start=week)


@pytest.mark.parametrize("zone", [None, True, "", "Invalid/Unknown", "x" * 129, "../UTC"])
def test_invalid_timezone(zone):
    with pytest.raises(DomainError):
        proposal([event()], timezone=zone)


def test_duplicates_and_overlaps_refused():
    for extra in [event(), event(start="2026-09-07T06:30:00Z", end="2026-09-07T07:00:00Z")]:
        with pytest.raises(DomainError):
            proposal([event(), extra])


def test_dst_ambiguous_clocks_cannot_be_silently_mapped_to_first_fold():
    for start in ("2026-10-25T00:00:00Z", "2026-10-25T01:00:00Z"):
        end = start.replace(":00:00Z", ":30:00Z")
        with pytest.raises(DomainError):
            proposal(
                [event(start=start, end=end)], week_start="2026-10-19", timezone="Europe/Berlin"
            )


def test_dst_week_keeps_local_school_clock():
    result = proposal(
        [event(start="2026-03-29T07:00:00Z", end="2026-03-29T07:45:00Z")],
        week_start="2026-03-23",
        timezone="Europe/Berlin",
    )
    assert result["lessons"][0]["weekday"] == 6
    assert result["lessons"][0]["start"] == "09:00"


def test_utc_day_difference_is_mapped_to_target_local_week():
    result = proposal([event(start="2026-09-06T22:00:00Z", end="2026-09-06T22:45:00Z")])
    assert result["lessons"][0]["weekday"] == 0 and result["lessons"][0]["start"] == "01:00"
