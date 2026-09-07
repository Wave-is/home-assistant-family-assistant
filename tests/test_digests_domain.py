"""Private digest consent, scheduling and delivery authority tests."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import digests
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

MORNING = datetime(2026, 9, 7, 4, 2, tzinfo=UTC)  # 07:02 Europe/Kyiv


def state_fixture(*, modules=None, now=MORNING):
    modules = ["digests", "tasks"] if modules is None else modules
    return {
        "settings": {
            "modules": modules,
            "timezone": "Europe/Kyiv",
            "language": "en",
            "digest_morning_enabled": True,
            "digest_morning_time": "07:00",
            "digest_evening_enabled": False,
            "digest_evening_time": "19:00",
            "digest_weekly_enabled": False,
            "digest_weekly_weekday": 6,
            "digest_weekly_time": "18:00",
        },
        "members": {
            "owner": {
                "id": "owner",
                "name": "Owner",
                "role": "owner",
                "language": "en",
                "active": True,
                "revision": 1,
                "telegram_id": 1001,
            },
            "parent": {
                "id": "parent",
                "name": "Parent",
                "role": "parent",
                "language": "ru",
                "active": True,
                "revision": 4,
                "telegram_id": 1002,
            },
            "adult": {
                "id": "adult",
                "name": "Adult",
                "role": "adult",
                "language": "uk",
                "active": True,
                "revision": 2,
                "telegram_id": 1003,
            },
            "child": {
                "id": "child",
                "name": "Child",
                "role": "child",
                "language": "en",
                "active": True,
                "revision": 3,
                "telegram_id": 1004,
            },
            "sibling": {
                "id": "sibling",
                "name": "Sibling",
                "role": "child",
                "language": "en",
                "active": True,
                "revision": 5,
                "telegram_id": 1005,
            },
            "guest": {
                "id": "guest",
                "name": "Guest",
                "role": "guest",
                "language": "en",
                "active": True,
                "revision": 1,
                "telegram_id": 1006,
            },
        },
        "digest_subscriptions": {},
        "digest_markers": {},
        "outbox": {},
        "tasks": {
            "T000001": {
                "id": "T000001",
                "title": "Own task",
                "status": "assigned",
                "assignee": "parent",
                "due_at": (now + timedelta(hours=5)).isoformat(),
                "revision": 1,
            },
            "T000002": {
                "id": "T000002",
                "title": "Sibling secret title",
                "status": "assigned",
                "assignee": "sibling",
                "due_at": (now + timedelta(hours=6)).isoformat(),
                "revision": 1,
                "report": "REPORT-CANARY",
            },
        },
        "sequences": {},
    }


def context(state, actor="parent", now=MORNING, operation="digest-test"):
    return Context(state, state["members"][actor], now, operation)


def payload(state, actor="parent", **changes):
    return {
        "recipient_revision": state["members"][actor]["revision"],
        "subscription_revision": None,
        "morning": True,
        "evening": False,
        "weekly": False,
        **changes,
    }


def subscribe(state, actor="parent", **changes):
    return digests.handle(context(state, actor), "access_set", payload(state, actor, **changes))


def rejected_unchanged(state, call, code):
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code
    assert state == before


def generated(state, now=MORNING):
    digests.tick(context(state, "owner", now, "clock"))
    assert len(state["outbox"]) == 1
    return next(iter(state["outbox"].values()))


def test_self_consent_create_update_and_opaque_receipts():
    state = state_fixture()
    result = subscribe(state)
    assert result == {"revision": 1, "status": "enabled"}
    assert state["digest_subscriptions"]["parent"] == {
        "recipient": "parent",
        "recipient_revision": 4,
        "morning": True,
        "evening": False,
        "weekly": False,
        "revision": 1,
        "updated_at": MORNING.isoformat(),
    }
    rejected_unchanged(state, lambda: subscribe(state), "conflict")
    disabled = subscribe(
        state,
        subscription_revision=1,
        morning=False,
    )
    assert disabled == {"revision": 2, "status": "disabled"}
    assert set(disabled) == {"revision", "status"}


@pytest.mark.parametrize("actor", ["owner", "parent", "adult", "child"])
def test_each_current_non_guest_can_only_create_own_subscription(actor):
    state = state_fixture()
    subscribe(state, actor)
    assert set(state["digest_subscriptions"]) == {actor}
    assert (
        state["digest_subscriptions"][actor]["recipient_revision"]
        == state["members"][actor]["revision"]
    )


def test_new_disabled_subscription_guest_and_disabled_module_are_rejected():
    state = state_fixture()
    rejected_unchanged(
        state,
        lambda: subscribe(state, morning=False),
        "invalid_transition",
    )
    rejected_unchanged(state, lambda: subscribe(state, "guest"), "forbidden")
    state["settings"]["modules"].remove("digests")
    rejected_unchanged(state, lambda: subscribe(state), "module_disabled")


@pytest.mark.parametrize("bad", [None, True, False, 0, -1, 1.0, "1", 2**53])
def test_existing_subscription_requires_strict_current_revision(bad):
    state = state_fixture()
    subscribe(state)
    rejected_unchanged(
        state,
        lambda: subscribe(state, subscription_revision=bad, evening=True),
        "conflict" if bad is None else "invalid_field",
    )


@pytest.mark.parametrize("field", ["morning", "evening", "weekly"])
def test_consent_flags_are_strict_booleans(field):
    state = state_fixture()
    rejected_unchanged(state, lambda: subscribe(state, **{field: 1}), "invalid_field")


def test_member_epoch_change_requires_explicit_reconsent_and_revokes_replay():
    state = state_fixture()
    request = payload(state)
    result = subscribe(state)
    digests.authorize_replay(context(state), "access_set", request, result)

    state["members"]["parent"]["revision"] = 5
    projected = digests.view(state, state["members"]["parent"])
    assert projected["self"] == {
        "recipient_revision": 5,
        "subscription_revision": 1,
        "morning": False,
        "evening": False,
        "weekly": False,
        "can_edit": True,
        "health": "ok",
    }
    with pytest.raises(DomainError, match="conflict"):
        digests.authorize_replay(context(state), "access_set", request, result)

    renewed = subscribe(state, subscription_revision=1)
    assert renewed == {"revision": 2, "status": "enabled"}
    assert state["digest_subscriptions"]["parent"]["recipient_revision"] == 5


def test_control_projection_is_self_only_pure_and_guest_or_module_off_empty():
    state = state_fixture()
    subscribe(state, "parent")
    subscribe(state, "child")
    before = deepcopy(state)
    parent = digests.view(state, state["members"]["parent"])
    assert state == before
    assert parent["self"]["recipient_revision"] == 4
    assert parent["self"]["subscription_revision"] == 1
    assert "child" not in str(parent)
    assert digests.view(state, state["members"]["guest"]) == {"policy": None, "self": None}
    state["settings"]["modules"].remove("digests")
    assert digests.view(state, state["members"]["parent"]) == {
        "policy": None,
        "self": None,
    }


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("digest_morning_enabled", 1),
        ("digest_evening_enabled", "false"),
        ("digest_weekly_enabled", None),
        ("digest_morning_time", "7:00"),
        ("digest_evening_time", "25:00"),
        ("digest_weekly_time", "18:00:01"),
        ("digest_weekly_weekday", True),
        ("digest_weekly_weekday", 7),
        ("timezone", "Invalid/Zone"),
    ],
)
def test_policy_is_strict(field, bad):
    state = state_fixture()
    state["settings"][field] = bad
    with pytest.raises(DomainError, match="invalid_field"):
        digests.policy(state)


def test_tick_creates_content_free_descriptor_marker_and_private_target():
    state = state_fixture()
    subscribe(state)
    tasks_before = deepcopy(state["tasks"])
    event = generated(state)
    assert state["tasks"] == tasks_before
    assert event["recipient"] == "parent"
    assert event["key"] == "family_digest"
    assert set(event["data"]) == digests.EVENT_FIELDS
    serialized = str({"event": event, "markers": state["digest_markers"]})
    for secret in ("Own task", "Sibling secret title", "REPORT-CANARY"):
        assert secret not in serialized
    assert len(state["digest_markers"]) == 1
    marker = next(iter(state["digest_markers"].values()))
    assert marker["event_id"] == event["id"]
    assert digests.delivery_allowed(state, event, MORNING)
    assert digests.target(state, event, MORNING) == {
        "channel": "telegram",
        "id": 1002,
        "language": "ru",
    }


def test_tick_is_idempotent_and_noop_ticks_do_not_churn_state():
    state = state_fixture()
    subscribe(state)
    before = deepcopy(state)
    digests.tick(context(state, "owner", MORNING - timedelta(minutes=10), "early"))
    assert state == before

    generated(state)
    after = deepcopy(state)
    digests.tick(context(state, "owner", MORNING + timedelta(minutes=1), "same-window"))
    assert state == after
    state["tasks"]["T000001"]["title"] = "Changed source"
    digests.tick(context(state, "owner", MORNING + timedelta(minutes=2), "source-edit"))
    assert len(state["outbox"]) == 1
    assert len(state["digest_markers"]) == 1


@pytest.mark.parametrize(
    "change",
    ["module", "policy", "recipient_epoch", "recipient_role", "subscription", "marker"],
)
def test_delivery_rechecks_every_durable_authority_boundary(change):
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    if change == "module":
        state["settings"]["modules"].remove("digests")
    elif change == "policy":
        state["settings"]["digest_morning_time"] = "07:01"
    elif change == "recipient_epoch":
        state["members"]["parent"]["revision"] += 1
    elif change == "recipient_role":
        state["members"]["parent"].update(role="guest", revision=5)
    elif change == "subscription":
        state["digest_subscriptions"]["parent"].update(morning=False, revision=2)
    else:
        state["digest_markers"].clear()
    assert not digests.delivery_allowed(state, event, MORNING + timedelta(minutes=1))
    assert digests.target(state, event, MORNING + timedelta(minutes=1)) is None


def test_binding_change_updates_private_target_without_changing_descriptor():
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    state["members"]["parent"]["telegram_id"] = 2002
    assert digests.delivery_allowed(state, event, MORNING)
    assert digests.target(state, event, MORNING)["id"] == 2002
    state["members"]["parent"]["telegram_id"] = -100
    assert digests.target(state, event, MORNING) is None


@pytest.mark.parametrize("telegram_id", [None, True, False, 0, -1, "1002"])
def test_private_target_requires_a_positive_integer_member_binding(telegram_id):
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    state["members"]["parent"]["telegram_id"] = telegram_id
    assert digests.target(state, event, MORNING) is None


def test_empty_current_content_and_expiry_block_delivery_and_supersede_unsent():
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    state["tasks"].clear()
    assert not digests.delivery_allowed(state, event, MORNING)
    digests.tick(context(state, "owner", MORNING + timedelta(minutes=1), "sweep"))
    assert event["state"] == "superseded"

    expiring = state_fixture()
    subscribe(expiring)
    event = generated(expiring)
    assert not digests.delivery_allowed(expiring, event, MORNING + timedelta(hours=6))


def test_no_content_creates_neither_marker_nor_outbox_and_does_not_churn():
    state = state_fixture()
    state["tasks"].clear()
    subscribe(state)
    before = deepcopy(state)
    digests.tick(context(state, "owner", MORNING, "empty"))
    assert state == before


def test_policy_epoch_prevents_a_to_b_to_a_event_revival_without_duplicate():
    state = state_fixture()
    state["settings"]["digest_policy_revision"] = 1
    subscribe(state)
    event = generated(state)
    state["settings"]["digest_policy_revision"] = 3
    assert not digests.delivery_allowed(state, event, MORNING)
    digests.tick(context(state, "owner", MORNING + timedelta(minutes=1), "aba"))
    assert event["state"] == "superseded"
    assert len(state["digest_markers"]) == 1
    assert len(state["outbox"]) == 1


def test_late_morning_policy_expires_at_local_midnight_not_six_hours_later():
    now = datetime(2026, 9, 7, 23, 2, tzinfo=UTC)
    state = state_fixture(now=now)
    state["settings"].update(timezone="UTC", digest_morning_time="23:00")
    state["tasks"]["T000001"]["due_at"] = "2026-09-07T23:30:00+00:00"
    subscribe(state)
    event = generated(state, now)
    assert event["data"]["window_start"] == "2026-09-07"
    assert event["data"]["expires_at"] == "2026-09-08T00:00:00+00:00"
    assert digests.delivery_allowed(state, event, datetime(2026, 9, 7, 23, 59, tzinfo=UTC))
    assert not digests.delivery_allowed(state, event, datetime(2026, 9, 8, 0, 0, tzinfo=UTC))


def test_morning_expiry_uses_household_local_midnight_across_dst_offset():
    now = datetime(2026, 3, 29, 19, 2, tzinfo=UTC)  # 21:02 Europe/Berlin, UTC+2
    state = state_fixture(now=now)
    state["settings"].update(timezone="Europe/Berlin", digest_morning_time="21:00")
    state["tasks"]["T000001"]["due_at"] = "2026-03-29T20:00:00+00:00"
    subscribe(state)
    event = generated(state, now)
    assert event["data"]["scheduled_at"] == "2026-03-29T19:00:00+00:00"
    assert event["data"]["expires_at"] == "2026-03-29T22:00:00+00:00"


def test_weekly_schedule_window_and_spring_gap_or_fall_fold_are_deterministic():
    weekly = state_fixture(now=datetime(2026, 9, 6, 15, 2, tzinfo=UTC))
    weekly["settings"].update(
        digest_morning_enabled=False,
        digest_weekly_enabled=True,
        digest_weekly_time="18:00",
    )
    weekly["tasks"]["T000001"]["due_at"] = "2026-09-07T08:00:00+00:00"
    subscribe(weekly, weekly=True, morning=False)
    event = generated(weekly, datetime(2026, 9, 6, 15, 2, tzinfo=UTC))
    assert event["data"]["window_start"] == "2026-09-07"
    assert event["data"]["window_end"] == "2026-09-14"
    assert event["data"]["period_key"] == "2026-W36/weekly:2026-09-06"

    gap = state_fixture(now=datetime(2026, 3, 29, 0, 30, tzinfo=UTC))
    gap["settings"].update(timezone="Europe/Berlin", digest_morning_time="02:30")
    gap["tasks"]["T000001"]["due_at"] = "2026-03-29T10:00:00+00:00"
    subscribe(gap)
    before = deepcopy(gap)
    digests.tick(context(gap, "owner", datetime(2026, 3, 29, 1, 30, tzinfo=UTC), "gap"))
    assert gap == before

    fold = state_fixture(now=datetime(2026, 10, 25, 0, 32, tzinfo=UTC))
    fold["settings"].update(timezone="Europe/Berlin", digest_morning_time="02:30")
    fold["tasks"]["T000001"]["due_at"] = "2026-10-25T10:00:00+00:00"
    subscribe(fold)
    generated(fold, datetime(2026, 10, 25, 0, 32, tzinfo=UTC))
    digests.tick(context(fold, "owner", datetime(2026, 10, 25, 1, 32, tzinfo=UTC), "fold2"))
    assert len(fold["outbox"]) == 1


def test_malformed_descriptor_and_snapshot_state_fail_closed_without_mutation():
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    for mutation in (
        lambda value: value["data"].update(schema=True),
        lambda value: value["data"].update(window_end="2026-09-09"),
        lambda value: value["data"].update(expires_at="bad"),
        lambda value: value.update(recipient="sibling"),
    ):
        malformed = deepcopy(event)
        mutation(malformed)
        before = deepcopy(state)
        assert not digests.delivery_allowed(state, malformed, MORNING)
        assert state == before


def test_health_stats_and_self_health_are_counts_only():
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    event["state"] = "uncertain"
    stats = digests.health_stats(state)
    assert stats == {"markers": 1, "retained": 1, "unresolved": 1, "capacity": False}
    projected = digests.view(state, state["members"]["parent"])
    assert projected["self"]["health"] == "attention"
    assert "T000001" not in str(stats)
