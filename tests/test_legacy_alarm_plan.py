"""Tests for alarm plan proposal generation from legacy review."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.migration.alarm_plan import (
    AlarmPlan,
    AlarmPlanError,
    build_alarm_plan,
)
from custom_components.family_assistant.migration.review import (
    ASSISTANT_KEY,
    COURT_KEY,
    read_store_pair,
)

STAMP = "2026-09-07T08:00:00+00:00"


def encoded(value):
    return json.dumps(value, ensure_ascii=True).encode()


def wrapped(data, key):
    return encoded({"key": key, "version": 1, "minor_version": 1, "data": data})


@pytest.fixture
def base_source_pair():
    ledger = {
        "schema_version": 1,
        "next_task_sequence": 1,
        "next_event_sequence": 1,
        "tasks": {},
        "history": [],
        "processed_commands": {},
    }
    alarms = {
        "schedules": {
            "old-child": {
                "weekday": {"enabled": True, "time": "07:00"},
                "weekend": {"enabled": False, "time": "09:30"},
            }
        },
        "runs": {
            "run-1": {
                "child": "old-child",
                "scheduled_at": STAMP,
                "confirmed_at": STAMP,
                "legacy_receipt": "receipt-abc",
                "challenge_secret": "sensitive-old-secret",
            }
        },
        "unknown_extra_alarm_field": {"arbitrary": 123},
    }
    assistant = {"ledger": ledger, "alarms": alarms}
    court = {
        "schema_version": 1,
        "week_id": "source-period",
        "opened_at": STAMP,
        "children": {"old-child": {"pluses": 0, "minuses": 0}},
        "history": [],
        "archived_weeks": [],
        "processed_messages": {},
    }
    members = {
        "child": {
            "id": "child",
            "revision": 2,
            "active": True,
            "role": "child",
            "name": "Synthetic Child",
        },
    }
    mapping = {
        "old-child": {"member_id": "child", "member_revision": 2},
    }
    return wrapped(assistant, ASSISTANT_KEY), wrapped(court, COURT_KEY), mapping, members


def test_build_alarm_plan_weekday_weekend_disabled_zero_penalty(base_source_pair):
    assistant, court, mapping, members = base_source_pair
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)

    plan = build_alarm_plan(review, "Europe/Paris", members=members)
    assert isinstance(plan, AlarmPlan)

    # Immutability
    with pytest.raises(FrozenInstanceError):
        plan._summary = b"new"

    # Repr privacy
    assert repr(plan) == "AlarmPlan(private=True, import_available=False)"

    # Summary checks
    summary = plan.summary()
    assert summary["mode"] == "alarm_plan_proposal"
    assert summary["schedule_proposals_count"] == 2
    assert summary["archived_schedules_count"] == 2
    assert summary["archived_runs_count"] == 1
    assert summary["import_available"] is False
    assert summary["coherence_verified"] is False
    assert "timezone" not in summary
    assert summary["previously_enabled_count"] == 1
    assert summary["review_fingerprint"] == review.summary()["fingerprint"]
    assert len(summary["fingerprint"]) == 64

    # No raw fields in repr or summary
    summary_str = json.dumps(summary)
    for forbidden in ("07:00", "09:30", "old-child", "sensitive", "receipt-abc"):
        assert forbidden not in summary_str
        assert forbidden not in repr(plan)

    # Private data inspection
    private = plan.private_data()
    proposals = private["proposals"]
    assert len(proposals) == 2

    weekday_prop = next(p for p in proposals if p["period"] == "weekday")
    assert weekday_prop["source_member"] == "old-child"
    payload_wd = weekday_prop["payload"]
    assert payload_wd == {
        "member": "child",
        "time": "07:00",
        "days": [0, 1, 2, 3, 4],
        "timezone": "Europe/Paris",
        "enabled": False,
        "profile": "gentle",
        "penalty": 0,
    }
    # Notice: enabled was True in source, but MUST be converted to False
    assert "id" not in payload_wd
    assert "revision" not in payload_wd

    weekend_prop = next(p for p in proposals if p["period"] == "weekend")
    assert weekend_prop["source_member"] == "old-child"
    payload_we = weekend_prop["payload"]
    assert payload_we == {
        "member": "child",
        "time": "09:30",
        "days": [5, 6],
        "timezone": "Europe/Paris",
        "enabled": False,
        "profile": "gentle",
        "penalty": 0,
    }


def test_byte_equality_of_private_archive_and_isolation(base_source_pair):
    assistant, court, mapping, members = base_source_pair
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    plan = build_alarm_plan(review, "UTC", members=members)

    private = plan.private_data()
    archive = private["archive"]

    # Archive preserves original schedules, inactive runs, unknown metadata
    assert archive["schedules"]["old-child"]["weekday"]["enabled"] is True
    assert archive["schedules"]["old-child"]["weekday"]["time"] == "07:00"
    assert archive["runs"]["run-1"]["legacy_receipt"] == "receipt-abc"
    assert archive["runs"]["run-1"]["challenge_secret"] == "sensitive-old-secret"
    assert archive == json.loads(assistant)["data"]["alarms"]

    # Verify byte equality across fresh private_data() calls
    archive_bytes_1 = json.dumps(archive, sort_keys=True).encode()
    archive_bytes_2 = json.dumps(plan.private_data()["archive"], sort_keys=True).encode()
    assert archive_bytes_1 == archive_bytes_2

    # Returned copies cannot mutate the original plan.
    private["proposals"].clear()
    private["archive"]["schedules"].clear()
    fresh = plan.private_data()
    assert len(fresh["proposals"]) == 2
    assert "old-child" in fresh["archive"]["schedules"]


def test_determinism_and_fingerprint_binding(base_source_pair):
    assistant, court, mapping, members = base_source_pair
    review1 = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    review2 = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)

    plan1 = build_alarm_plan(review1, "America/New_York", members=members)
    plan2 = build_alarm_plan(review2, "America/New_York", members=members)
    assert plan1.summary()["fingerprint"] == plan2.summary()["fingerprint"]

    # Different timezone changes fingerprint
    plan_tz = build_alarm_plan(review1, "Europe/London", members=members)
    assert plan1.summary()["fingerprint"] != plan_tz.summary()["fingerprint"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 3),
        ("active", False),
        ("role", "parent"),
        ("name", "Another synthetic identity"),
        ("telegram_id", 9001),
        ("ha_user_id", "another-synthetic-binding"),
    ],
)
def test_current_member_changes_revoke_the_review(base_source_pair, field, value):
    assistant, court, mapping, members = base_source_pair
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    changed = deepcopy(members)
    changed["child"][field] = value
    assert review.matches_members(members)
    assert not review.matches_members(changed)
    with pytest.raises(AlarmPlanError, match="^review_changed$"):
        build_alarm_plan(review, "UTC", members=changed)
    with pytest.raises(AlarmPlanError, match="^review_changed$"):
        build_alarm_plan(review, "UTC")


@pytest.mark.parametrize(
    "field,value",
    [
        ("_fingerprint", "x" * 64),
        ("_fingerprint", "é" * 64),
        ("_counts", b"{}"),
        ("_mapping", b"[]"),
        ("_mapping", b'{"duplicate": 1, "duplicate": 2}'),
        ("_mapping_revision", True),
        ("_source", None),
    ],
)
def test_forged_review_fields_fail_closed_without_echo(base_source_pair, field, value):
    from dataclasses import replace

    assistant, court, mapping, members = base_source_pair
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    forged = replace(review, **{field: value})
    assert not forged.matches_members(members)
    with pytest.raises(AlarmPlanError, match="^review_changed$"):
        build_alarm_plan(forged, "UTC", members=members)


@pytest.mark.parametrize("envelope", [True, False])
def test_source_without_alarm_bucket_remains_empty(base_source_pair, envelope):
    assistant, court, mapping, members = base_source_pair
    data = json.loads(assistant)["data"]
    data.pop("alarms")
    if not envelope:
        data = data["ledger"]
    review = read_store_pair(wrapped(data, ASSISTANT_KEY), court).review(
        mapping, members, mapping_revision=1
    )
    plan = build_alarm_plan(review, "UTC", members=members)
    assert plan.private_data() == {"proposals": [], "archive": {}}
    assert plan.summary()["schedule_proposals_count"] == 0


def test_review_validation_and_type_check():
    with pytest.raises(AlarmPlanError, match="^invalid_review$"):
        build_alarm_plan(None, "UTC")  # type: ignore

    with pytest.raises(AlarmPlanError, match="^invalid_review$"):
        build_alarm_plan("not a review", "UTC")  # type: ignore


@pytest.mark.parametrize(
    "tz",
    [
        "",
        "   ",
        "Invalid/Timezone",
        "Not_A_Tz",
        None,
        123,
        "UTC" * 50,
    ],
)
def test_missing_or_bad_timezone(base_source_pair, tz):
    assistant, court, mapping, members = base_source_pair
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)

    with pytest.raises(AlarmPlanError, match="^invalid_timezone$"):
        build_alarm_plan(review, tz)  # type: ignore


def test_missing_schedule_target_and_archive_only(base_source_pair):
    assistant_bytes, court_bytes, mapping, members = base_source_pair

    # 1. Archive-only target for schedule
    mapping_archive = {"old-child": {"archive_only": True}}
    # When mapping has archive_only for old-child, review itself or plan rejects it
    # review._required_subjects rejects archive_only for alarm schedule members
    # But even if forged or bypassed, build_alarm_plan must explicitly reject

    # Test forged review object with archive_only mapping
    from custom_components.family_assistant.migration.review import LegacyReview, LegacySource

    forged_source = LegacySource(assistant_bytes, court_bytes)
    forged_review = LegacyReview(
        forged_source,
        json.dumps(mapping_archive).encode(),
        1,
        "dummy_fp",
        b"{}",
    )
    with pytest.raises(AlarmPlanError, match="^review_changed$"):
        build_alarm_plan(forged_review, "UTC", members=members)

    # 2. Missing member mapping entirely
    forged_review_missing = LegacyReview(
        forged_source,
        json.dumps({}).encode(),
        1,
        "dummy_fp",
        b"{}",
    )
    with pytest.raises(AlarmPlanError, match="^review_changed$"):
        build_alarm_plan(forged_review_missing, "UTC", members=members)

    forged_review_unmapped = LegacyReview(
        forged_source,
        json.dumps({"other-person": {"member_id": "child", "member_revision": 2}}).encode(),
        1,
        "dummy_fp",
        b"{}",
    )
    with pytest.raises(AlarmPlanError, match="^review_changed$"):
        build_alarm_plan(forged_review_unmapped, "UTC", members=members)


def test_active_alarm_runs_rejected(base_source_pair):
    assistant_raw = json.loads(base_source_pair[0].decode())
    # Add an active alarm run (neither confirmed_at nor cancelled_at)
    assistant_raw["data"]["alarms"]["runs"]["active-run"] = {
        "child": "old-child",
        "scheduled_at": STAMP,
    }
    assistant = wrapped(assistant_raw["data"], ASSISTANT_KEY)
    court, mapping, members = base_source_pair[1:]

    # A review with active runs will fail preflight, but let's test forged review as well
    from custom_components.family_assistant.migration.review import LegacyReview, LegacySource

    forged_source = LegacySource(assistant, court)
    forged_review = LegacyReview(
        forged_source,
        json.dumps(mapping).encode(),
        1,
        "dummy_fp",
        b"{}",
    )
    with pytest.raises(AlarmPlanError, match="^review_changed$"):
        build_alarm_plan(forged_review, "UTC", members=members)


@pytest.mark.asyncio
async def test_actual_modern_engine_validation_on_fictional_state(base_source_pair):
    """Confirm modern Engine accepts the generated payloads via alarms.save without live effects."""
    assistant, court, mapping, members = base_source_pair
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    plan = build_alarm_plan(review, "America/Chicago", members=members)

    # Build a fresh fictional modern Engine state with child member
    state = new_state("owner-id", "Test Household")
    state["members"]["child"] = {
        "id": "child",
        "name": "Synthetic Child",
        "role": "child",
        "language": "en",
        "active": True,
        "revision": 2,
    }
    members = state["members"]
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    plan = build_alarm_plan(review, "America/Chicago", members=members)

    class DummyStore:
        def __init__(self):
            self.saved = None

        async def save(self, s):
            self.saved = deepcopy(s)

    store = DummyStore()
    engine = Engine(state, store.save)
    now = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)

    # Execute alarms.save for each proposed payload
    proposals = plan.private_data()["proposals"]
    for i, proposal in enumerate(proposals):
        payload = proposal["payload"]
        # Must execute cleanly through Engine
        record = await engine.execute("owner", "alarms.save", payload, f"op-{i}", now)
        assert record["member"] == "child"
        assert record["enabled"] is False
        assert record["profile"] == "gentle"
        assert record["penalty"] == 0
        assert record["timezone"] == "America/Chicago"
        assert record["id"].startswith("A")

    # Verify no alarm runs were triggered because enabled is False
    assert len(engine.snapshot()["alarm_runs"]) == 0
    # Engine alarms table now contains both schedules
    assert len(engine.snapshot()["alarms"]) == 2
