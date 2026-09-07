"""Exact, bounded retention for private school preparation reminders."""

import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import school_reminders, school_retention
from custom_components.family_assistant.domain.context import Context

DAY = date(2026, 9, 8)
EXPIRES = datetime(2026, 9, 8, 5, 30, tzinfo=UTC)
CREATED = datetime(2026, 9, 7, 17, 2, tzinfo=UTC)


def state_fixture():
    return {
        "settings": {"modules": ["school", "routines"], "timezone": "Europe/Kyiv"},
        "members": {
            "parent": {
                "id": "parent",
                "name": "Parent",
                "role": "parent",
                "active": True,
                "revision": 1,
            }
        },
        "school": {"preparation_reminder_markers": {}},
        "outbox": {},
    }


def context(state, now, operation="retention"):
    return Context(state, state["members"]["parent"], now, operation)


def add_pair(
    state,
    *,
    day=DAY,
    created=CREATED,
    expires=EXPIRES,
    event_id="school-event",
    event_state="sent",
    delivery_state="sent",
):
    data = {
        "timetable_id": "ST000001",
        "timetable_revision": 4,
        "member": "child",
        "member_revision": 3,
        "recipient_revision": 2,
        "date": day.isoformat(),
        "routine_id": "RT000001",
        "routine_revision": 5,
        "subscription_revision": 6,
        "policy_fingerprint": "a" * 64,
        "expires_at": expires.isoformat(),
    }
    event = {
        "id": event_id,
        "recipient": "parent",
        "key": school_reminders.KEY,
        "data": data,
        "created_at": created.isoformat(),
        "state": event_state,
        "attempts": 1,
    }
    if delivery_state is not None:
        event["deliveries"] = {"telegram:bot": {"state": delivery_state}}
    marker = {
        "event_id": event_id,
        "timetable_revision": 4,
        "member_revision": 3,
        "recipient_revision": 2,
        "routine_revision": 5,
        "subscription_revision": 6,
    }
    marker_key = json.dumps(["parent", "ST000001", day.isoformat()], separators=(",", ":"))
    state["outbox"][event_id] = event
    state["school"]["preparation_reminder_markers"][marker_key] = marker
    return marker_key, marker, event


def test_contract_constants_match_actual_reminder_schema():
    assert school_retention.KEY == school_reminders.KEY
    assert school_retention.MAX_RECORDS == school_reminders.MAX_MARKERS
    assert school_retention.EVENT_FIELDS == school_reminders.EVENT_FIELDS


@pytest.mark.parametrize("event_state", ["sent", "superseded", "resolved"])
def test_success_terminal_pair_prunes_only_at_exact_horizon(event_state):
    state = state_fixture()
    add_pair(
        state,
        event_state=event_state,
        delivery_state="uncertain" if event_state == "resolved" else "sent",
    )
    before = deepcopy(state)
    assert (
        school_retention.prune(
            context(state, EXPIRES + timedelta(days=35) - timedelta(microseconds=1))
        )
        == 0
    )
    assert state == before

    assert school_retention.prune(context(state, EXPIRES + timedelta(days=35))) == 1
    assert state["outbox"] == {}
    assert state["school"]["preparation_reminder_markers"] == {}
    assert state["school"]["preparation_reminder_retention"]["through_date"] == DAY.isoformat()


def test_failed_pair_uses_ninety_day_horizon():
    state = state_fixture()
    add_pair(state, event_state="failed", delivery_state="failed")
    assert (
        school_retention.prune(context(state, EXPIRES + timedelta(days=90) - timedelta(seconds=1)))
        == 0
    )
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=90))) == 1


@pytest.mark.parametrize(
    ("event_state", "delivery_state"),
    [
        ("pending", "pending"),
        ("awaiting_channel", None),
        ("sending", "sending"),
        ("uncertain", "uncertain"),
    ],
)
def test_active_and_uncertain_states_are_never_deleted(event_state, delivery_state):
    state = state_fixture()
    add_pair(state, event_state=event_state, delivery_state=delivery_state)
    before = deepcopy(state)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 0
    assert state == before


@pytest.mark.parametrize(
    ("event_state", "delivery_state"),
    [("sent", "sending"), ("sent", "failed"), ("failed", "uncertain"), ("sent", "new")],
)
def test_incompatible_or_unknown_delivery_state_is_retained(event_state, delivery_state):
    state = state_fixture()
    add_pair(state, event_state=event_state, delivery_state=delivery_state)
    before = deepcopy(state)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 0
    assert state == before


@pytest.mark.parametrize("event_state", ["sent", "failed"])
def test_sent_or_failed_without_a_delivery_record_is_retained(event_state):
    state = state_fixture()
    add_pair(state, event_state=event_state, delivery_state=None)
    before = deepcopy(state)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 0
    assert state == before
    assert school_retention.health_stats(state)["retention_errors"] == 1


@pytest.mark.parametrize("event_state", ["superseded", "resolved"])
def test_explicit_non_delivery_terminal_state_can_retire_without_deliveries(event_state):
    state = state_fixture()
    add_pair(state, event_state=event_state, delivery_state=None)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 1


@pytest.mark.parametrize(
    "break_lineage",
    [
        lambda marker_key, marker, event: marker.update(subscription_revision=7),
        lambda marker_key, marker, event: marker.update(member_revision=True),
        lambda marker_key, marker, event: event["data"].update(date="2026-09-09"),
        lambda marker_key, marker, event: event["data"].update(extra="private"),
        lambda marker_key, marker, event: event.update(recipient="sibling"),
        lambda marker_key, marker, event: event.update(created_at="not-a-time"),
        lambda marker_key, marker, event: marker.update(extra=True),
    ],
)
def test_malformed_or_mismatched_lineage_fails_closed(break_lineage):
    state = state_fixture()
    marker_key, marker, event = add_pair(state)
    break_lineage(marker_key, marker, event)
    state["outbox"]["unrelated"] = {
        "id": "unrelated",
        "key": "task_reminder",
        "state": "sent",
    }
    before = deepcopy(state)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 0
    assert state == before
    assert school_retention.health_stats(state)["unpaired"] >= 1


def test_future_date_cannot_poison_monotonic_watermark():
    state = state_fixture()
    _key, _marker, event = add_pair(state)
    event["data"]["date"] = "9999-12-31"
    marker = state["school"]["preparation_reminder_markers"].pop(_key)
    state["school"]["preparation_reminder_markers"]['["parent","ST000001","9999-12-31"]'] = marker
    before = deepcopy(state)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 0
    assert state == before


def test_noncanonical_duplicate_marker_key_is_not_pruned():
    state = state_fixture()
    marker_key, marker, _event = add_pair(state)
    state["school"]["preparation_reminder_markers"].pop(marker_key)
    state["school"]["preparation_reminder_markers"]['["parent", "ST000001", "2026-09-08"]'] = marker
    before = deepcopy(state)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 0
    assert state == before


def test_watermark_is_monotonic_when_an_older_pair_is_pruned_later():
    state = state_fixture()
    add_pair(state)
    now = EXPIRES + timedelta(days=100)
    assert school_retention.prune(context(state, now)) == 1
    first = deepcopy(state["school"]["preparation_reminder_retention"])

    older = date(2026, 9, 7)
    older_expires = datetime(2026, 9, 7, 5, 30, tzinfo=UTC)
    add_pair(
        state,
        day=older,
        created=datetime(2026, 9, 6, 17, 2, tzinfo=UTC),
        expires=older_expires,
        event_id="older",
    )
    assert school_retention.prune(context(state, now)) == 1
    assert state["school"]["preparation_reminder_retention"] == first


def test_creation_guard_blocks_pruned_dates_and_clock_rollback_is_counts_only():
    state = state_fixture()
    add_pair(state)
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=35))) == 1
    assert school_retention.creation_allowed(state, DAY) is False
    assert school_retention.creation_allowed(state, DAY - timedelta(days=1)) is False
    assert school_retention.creation_allowed(state, DAY + timedelta(days=1)) is True

    health = school_retention.health_stats(state, datetime(2026, 9, 8, 8, tzinfo=UTC))
    assert health["clock_rollback"] is True
    assert "2026-09-08" not in repr(health)
    assert "parent" not in repr(health)


def test_capacity_counts_markers_and_retained_events_independently(monkeypatch):
    monkeypatch.setattr(school_retention, "MAX_RECORDS", 1)
    marker_state = state_fixture()
    marker_state["school"]["preparation_reminder_markers"]["malformed"] = {"event_id": "missing"}
    assert school_retention.creation_allowed(marker_state, DAY) is False
    marker_health = school_retention.health_stats(marker_state)
    assert marker_health["capacity"] is True
    assert marker_health["markers"] == 1

    event_state = state_fixture()
    event_state["outbox"]["orphan"] = {
        "id": "orphan",
        "recipient": "private-canary",
        "key": school_reminders.KEY,
        "state": "uncertain",
    }
    assert school_retention.creation_allowed(event_state, DAY) is False
    event_health = school_retention.health_stats(event_state)
    assert event_health["retained"] == 1
    assert event_health["unresolved"] == 1
    assert "private-canary" not in repr(event_health)


def test_malformed_retention_state_blocks_creation_and_never_deletes():
    state = state_fixture()
    add_pair(state)
    state["school"]["preparation_reminder_retention"] = {"through_date": DAY.isoformat()}
    before = deepcopy(state)
    assert school_retention.creation_allowed(state, DAY + timedelta(days=1)) is False
    assert school_retention.prune(context(state, EXPIRES + timedelta(days=1000))) == 0
    assert state == before
    assert school_retention.health_stats(state)["retention_errors"] == 1


def test_noop_is_pure_and_does_not_create_missing_namespaces():
    state = {
        "settings": {"timezone": "UTC"},
        "members": {"parent": {"id": "parent", "role": "parent", "active": True, "revision": 1}},
    }
    before = deepcopy(state)
    assert school_retention.prune(context(state, CREATED)) == 0
    assert school_retention.health_stats(state) == {
        "markers": 0,
        "retained": 0,
        "unresolved": 0,
        "unpaired": 0,
        "retention_errors": 0,
        "capacity": False,
        "clock_rollback": False,
    }
    assert state == before
