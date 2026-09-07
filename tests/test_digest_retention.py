"""Bounded digest marker/outbox retention tests."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from custom_components.family_assistant.domain import digests
from custom_components.family_assistant.domain.context import Context

MORNING = datetime(2026, 9, 7, 4, 2, tzinfo=UTC)


def fixture(now=MORNING):
    return {
        "settings": {
            "modules": ["digests", "tasks"],
            "timezone": "Europe/Kyiv",
            "language": "en",
            "digest_policy_revision": 1,
            "digest_morning_enabled": True,
            "digest_morning_time": "07:00",
            "digest_evening_enabled": False,
            "digest_evening_time": "19:00",
            "digest_weekly_enabled": False,
            "digest_weekly_weekday": 6,
            "digest_weekly_time": "18:00",
        },
        "members": {
            "parent": {
                "id": "parent",
                "name": "Parent",
                "role": "parent",
                "language": "en",
                "active": True,
                "revision": 1,
                "telegram_id": 1001,
            }
        },
        "digest_subscriptions": {
            "parent": {
                "recipient": "parent",
                "recipient_revision": 1,
                "morning": True,
                "evening": False,
                "weekly": False,
                "revision": 1,
                "updated_at": now.isoformat(),
            }
        },
        "digest_markers": {},
        "outbox": {},
        "tasks": {
            "T1": {
                "id": "T1",
                "title": "Current task",
                "status": "assigned",
                "assignee": "parent",
                "revision": 1,
                "due_at": (now + timedelta(hours=5)).isoformat(),
            }
        },
    }


def ctx(state, now, operation="retention"):
    return Context(state, state["members"]["parent"], now, operation)


def generated(state, now=MORNING):
    digests.tick(ctx(state, now, "clock"))
    assert len(state["outbox"]) == 1 and len(state["digest_markers"]) == 1
    return next(iter(state["outbox"].values()))


def test_daily_terminal_pair_prunes_only_after_exact_horizon():
    state = fixture()
    event = generated(state)
    event["state"] = "sent"
    scheduled = datetime.fromisoformat(event["data"]["scheduled_at"])
    before = deepcopy(state)
    assert digests.prune(ctx(state, scheduled + timedelta(days=35) - timedelta(seconds=1))) == 0
    assert state == before
    assert digests.prune(ctx(state, scheduled + timedelta(days=35))) == 1
    assert state["digest_markers"] == {}
    assert state["outbox"] == {}


def test_weekly_terminal_pair_uses_sixteen_week_horizon():
    now = datetime(2026, 9, 6, 15, 2, tzinfo=UTC)
    state = fixture(now)
    state["settings"].update(
        digest_morning_enabled=False,
        digest_weekly_enabled=True,
        digest_weekly_time="18:00",
    )
    state["digest_subscriptions"]["parent"].update(morning=False, weekly=True)
    state["tasks"]["T1"]["due_at"] = "2026-09-07T08:00:00+00:00"
    event = generated(state, now)
    assert event["data"]["kind"] == "weekly"
    event["state"] = "resolved"
    scheduled = datetime.fromisoformat(event["data"]["scheduled_at"])
    assert digests.prune(ctx(state, scheduled + timedelta(weeks=16) - timedelta(seconds=1))) == 0
    assert digests.prune(ctx(state, scheduled + timedelta(weeks=16))) == 1


def test_failed_pair_is_retained_for_ninety_days():
    state = fixture()
    event = generated(state)
    event["state"] = "failed"
    event["deliveries"] = {"d": {"state": "failed"}}
    scheduled = datetime.fromisoformat(event["data"]["scheduled_at"])
    assert digests.prune(ctx(state, scheduled + timedelta(days=90) - timedelta(seconds=1))) == 0
    assert digests.prune(ctx(state, scheduled + timedelta(days=90))) == 1


def test_active_uncertain_and_inflight_pairs_are_never_pruned():
    for event_state, delivery_state in (
        ("pending", "pending"),
        ("awaiting_channel", None),
        ("sending", "sending"),
        ("uncertain", "uncertain"),
    ):
        state = fixture()
        event = generated(state)
        event["state"] = event_state
        if delivery_state is not None:
            event["deliveries"] = {"d": {"state": delivery_state}}
        before = deepcopy(state)
        assert digests.prune(ctx(state, MORNING + timedelta(days=1000))) == 0
        assert state == before


def test_terminal_event_with_inflight_delivery_is_not_claimed_recalled():
    state = fixture()
    event = generated(state)
    event["state"] = "sent"
    event["deliveries"] = {"d": {"state": "sending"}}
    before = deepcopy(state)
    assert digests.prune(ctx(state, MORNING + timedelta(days=1000))) == 0
    assert state == before


def test_terminal_event_with_unknown_delivery_state_is_retained_fail_closed():
    state = fixture()
    event = generated(state)
    event["state"] = "sent"
    event["deliveries"] = {"d": {"state": "invented"}}
    before = deepcopy(state)
    assert digests.prune(ctx(state, MORNING + timedelta(days=1000))) == 0
    assert state == before


def test_explicitly_resolved_uncertain_delivery_is_prunable_after_horizon():
    state = fixture()
    event = generated(state)
    event["state"] = "resolved"
    event["deliveries"] = {"d": {"state": "uncertain"}}
    scheduled = datetime.fromisoformat(event["data"]["scheduled_at"])
    assert digests.prune(ctx(state, scheduled + timedelta(days=35))) == 1


def test_mismatched_marker_or_event_is_retained_and_unrelated_outbox_untouched():
    state = fixture()
    event = generated(state)
    event["state"] = "sent"
    state["outbox"]["other"] = {
        "id": "other",
        "key": "task_reminder",
        "recipient": "parent",
        "state": "sent",
        "created_at": MORNING.isoformat(),
        "data": {},
    }
    marker = next(iter(state["digest_markers"].values()))
    marker["subscription_revision"] = 2
    before = deepcopy(state)
    assert digests.prune(ctx(state, MORNING + timedelta(days=1000))) == 0
    assert state == before

    marker["subscription_revision"] = 1
    assert digests.prune(ctx(state, MORNING + timedelta(days=1000))) == 1
    assert state["outbox"] == {"other": before["outbox"]["other"]}


def test_tick_prunes_before_capacity_and_can_create_current_period(monkeypatch):
    state = fixture()
    old = generated(state)
    old["state"] = "sent"
    old_marker_key = next(iter(state["digest_markers"]))
    old_marker = state["digest_markers"][old_marker_key]
    old["data"]["scheduled_at"] = (MORNING - timedelta(days=40)).isoformat()
    old["created_at"] = old["data"]["scheduled_at"]
    old["data"]["expires_at"] = (MORNING - timedelta(days=40) + timedelta(hours=6)).isoformat()
    old["data"]["period_key"] = "2026-07-29/morning"
    old["data"]["window_start"] = "2026-07-29"
    old["data"]["window_end"] = "2026-07-30"
    old_marker["event_id"] = old["id"]
    state["digest_markers"] = {'["parent","morning","2026-07-29/morning"]': old_marker}
    monkeypatch.setattr(digests, "MAX_RECORDS", 1)
    digests.tick(ctx(state, MORNING, "new-period"))
    assert len(state["digest_markers"]) == 1
    assert len(state["outbox"]) == 1
    assert next(iter(state["outbox"].values()))["data"]["period_key"] == "2026-09-07/morning"


def test_capacity_stops_new_events_and_health_is_counts_only(monkeypatch):
    state = fixture()
    monkeypatch.setattr(digests, "MAX_RECORDS", 1)
    state["digest_markers"]["malformed-retained"] = {"event_id": "missing"}
    before = deepcopy(state)
    digests.tick(ctx(state, MORNING, "capacity"))
    assert state == before
    assert digests.health_stats(state) == {
        "markers": 1,
        "retained": 0,
        "unresolved": 0,
        "capacity": True,
    }


def test_prune_noop_does_not_create_missing_buckets_or_churn_state():
    state = fixture()
    state.pop("digest_markers")
    before = deepcopy(state)
    assert digests.prune(ctx(state, MORNING)) == 0
    assert state == before


def test_malformed_retention_state_fails_closed_without_unrelated_deletion():
    state = fixture()
    state["digest_markers"] = []
    unrelated = {"id": "other", "key": "other", "state": "sent"}
    state["outbox"]["other"] = unrelated
    stats = digests.health_stats(state)
    assert stats["capacity"] is True
    assert state["outbox"]["other"] is unrelated


def test_retired_period_cannot_reappear_after_restart_clock_or_policy_rollback():
    import json

    state = fixture()
    event = generated(state)
    event["state"] = "sent"
    assert digests.prune(ctx(state, MORNING + timedelta(days=40))) == 1
    assert state["digest_retired"] == {"morning": "2026-09-07"}
    restored = json.loads(json.dumps(state))
    restored["settings"].update(digest_morning_time="07:01", digest_policy_revision=3)
    digests.tick(ctx(restored, MORNING, "clock-rolled-back"))
    assert not restored["outbox"] and not restored["digest_markers"]
    # A later legitimate date remains usable, without resetting retired history.
    restored["tasks"]["T1"]["due_at"] = (MORNING + timedelta(days=41, hours=3)).isoformat()
    digests.tick(ctx(restored, MORNING + timedelta(days=41), "current-period"))
    assert len(restored["outbox"]) == 1
    assert restored["digest_retired"] == {"morning": "2026-09-07"}


def test_retention_floor_is_monotonic_and_does_not_erase_older_uncertain_events():
    state = fixture()
    event = generated(state)
    event["state"] = "uncertain"
    state["digest_retired"] = {"morning": "2026-09-08"}
    before = deepcopy(state)
    assert digests.prune(ctx(state, MORNING + timedelta(days=200))) == 0
    assert state == before
    event["state"] = "resolved"
    assert digests.prune(ctx(state, MORNING + timedelta(days=200))) == 1
    assert state["digest_retired"] == {"morning": "2026-09-08"}


def test_malformed_retired_dates_fail_closed_without_deletion_or_creation():
    for retired in ([], {"morning": "2026-99-01"}, {"morning": True}, {"invented": "2026-09-07"}):
        state = fixture()
        event = generated(state)
        event["state"] = "sent"
        state["digest_retired"] = retired
        before = deepcopy(state)
        digests.tick(ctx(state, MORNING + timedelta(days=1000)))
        assert state == before
        assert digests.health_stats(state)["capacity"] is True


def test_noncanonical_period_window_is_not_pruned_or_used_as_retirement_floor():
    state = fixture()
    event = generated(state)
    event["state"] = "sent"
    event["data"]["window_end"] = "2099-01-01"
    before = deepcopy(state)
    assert digests.prune(ctx(state, MORNING + timedelta(days=1000))) == 0
    assert state == before
