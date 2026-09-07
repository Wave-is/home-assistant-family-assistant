"""Private, source-bound school preparation reminder tests."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import recurrence, school_reminders
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import quiet_until

NOW = datetime(2026, 9, 7, 17, 2, tzinfo=UTC)  # 20:02 Europe/Kyiv


def state_fixture(*, lesson_date="2026-09-08", lesson_time="08:30"):
    day = datetime.fromisoformat(f"{lesson_date}T00:00:00+00:00").date()
    return {
        "settings": {
            "modules": ["school", "routines"],
            "timezone": "Europe/Kyiv",
            "school_preparation_reminders": True,
            "school_preparation_days_before": 1,
            "school_preparation_time": "20:00",
        },
        "members": {
            "owner": {
                "id": "owner",
                "name": "Owner",
                "role": "owner",
                "active": True,
                "revision": 1,
            },
            "parent": {
                "id": "parent",
                "name": "Parent",
                "role": "parent",
                "active": True,
                "revision": 4,
            },
            "child": {
                "id": "child",
                "name": "Child",
                "role": "child",
                "active": True,
                "revision": 2,
            },
            "sibling": {
                "id": "sibling",
                "name": "Sibling",
                "role": "child",
                "active": True,
                "revision": 3,
            },
            "adult": {
                "id": "adult",
                "name": "Adult",
                "role": "adult",
                "active": True,
                "revision": 1,
            },
            "guest": {
                "id": "guest",
                "name": "Guest",
                "role": "guest",
                "active": True,
                "revision": 1,
            },
        },
        "school": {
            "timetables": {
                "ST000001": {
                    "id": "ST000001",
                    "revision": 5,
                    "member": "child",
                    "member_revision": 2,
                    "title": "School week",
                    "valid_from": "2026-01-01",
                    "valid_until": "2026-12-31",
                    "exceptions": [],
                    "lessons": [
                        {
                            "weekday": day.weekday(),
                            "start": lesson_time,
                            "end": "09:15",
                            "subject": "Mathematics",
                            "room": "12",
                            "materials": ["Workbook", "Pencil"],
                        }
                    ],
                    "backpack_routine": {"id": "RT000001", "revision": 7},
                    "status": "active",
                }
            },
            "preparations": {},
            "preparation_reminder_subscriptions": {},
            "preparation_reminder_markers": {},
        },
        "routines": {
            "RT000001": {
                "id": "RT000001",
                "revision": 7,
                "title": "Pack school bag",
                "description": "",
                "creator": "parent",
                "enabled": True,
                "assignees": ["child"],
                "steps": [
                    {
                        "title": "Pack books",
                        "confirmation": "manual",
                        "assignee": None,
                    }
                ],
            }
        },
        "outbox": {},
        "tasks": {},
        "routine_runs": {},
        "court": {},
        "sequences": {},
    }


def context(state, actor="parent", now=NOW, operation="school-reminder-test"):
    return Context(state, state["members"][actor], now, operation)


def payload(state, actor="parent", member="child", **changes):
    return {
        "member": member,
        "member_revision": state["members"][member]["revision"],
        "recipient_revision": state["members"][actor]["revision"],
        "subscription_revision": None,
        "enabled": True,
        **changes,
    }


def subscribe(state, actor="parent", member="child"):
    return school_reminders.handle(
        context(state, actor),
        "preparation_reminder_access_set",
        payload(state, actor, member),
    )


def rejected_unchanged(state, call, code="invalid_field"):
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code
    assert state == before


def generated(state, now=NOW):
    school_reminders.tick(context(state, "owner", now, "clock"))
    assert len(state["outbox"]) == 1
    return next(iter(state["outbox"].values()))


def test_self_subscription_is_revisioned_and_null_is_only_for_absent_record():
    state = state_fixture()
    created = subscribe(state)
    assert created == {"member": "child", "enabled": True, "revision": 1}
    stored = next(iter(state["school"]["preparation_reminder_subscriptions"].values()))
    assert stored == {
        "recipient": "parent",
        "recipient_revision": 4,
        "member": "child",
        "member_revision": 2,
        "enabled": True,
        "revision": 1,
    }
    rejected_unchanged(state, lambda: subscribe(state), "conflict")
    disabled = school_reminders.handle(
        context(state),
        "preparation_reminder_access_set",
        payload(state, subscription_revision=1, enabled=False),
    )
    assert disabled == {"member": "child", "enabled": False, "revision": 2}

    absent = state_fixture()
    rejected_unchanged(
        absent,
        lambda: school_reminders.handle(
            context(absent),
            "preparation_reminder_access_set",
            payload(absent, subscription_revision=1),
        ),
        "conflict",
    )
    rejected_unchanged(
        absent,
        lambda: school_reminders.handle(
            context(absent),
            "preparation_reminder_access_set",
            payload(absent, enabled=False),
        ),
        "invalid_transition",
    )


@pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, "1", 2**53])
def test_existing_subscription_requires_strict_positive_revision(bad):
    state = state_fixture()
    subscribe(state)
    rejected_unchanged(
        state,
        lambda: school_reminders.handle(
            context(state),
            "preparation_reminder_access_set",
            payload(state, subscription_revision=bad, enabled=False),
        ),
        "invalid_field" if bad not in {0, -1} else "invalid_field",
    )


def test_actor_is_recipient_and_child_can_only_subscribe_for_self():
    state = state_fixture()
    own = subscribe(state, "child", "child")
    assert own["enabled"] is True
    rejected_unchanged(
        state,
        lambda: school_reminders.handle(
            context(state, "sibling"),
            "preparation_reminder_access_set",
            payload(state, "sibling", "child"),
        ),
        "forbidden",
    )
    for actor in ("adult", "guest"):
        rejected_unchanged(
            state,
            lambda actor=actor: school_reminders.handle(
                context(state, actor),
                "preparation_reminder_access_set",
                payload(state, actor, "child"),
            ),
            "forbidden",
        )
    rejected_unchanged(
        state,
        lambda: school_reminders.handle(
            context(state),
            "preparation_reminder_access_set",
            payload(state, recipient_revision=3),
        ),
        "conflict",
    )


def test_view_is_pure_and_projects_only_the_actors_own_current_targets():
    state = state_fixture()
    subscribe(state, "parent", "child")
    subscribe(state, "child", "child")
    before = deepcopy(state)
    parent = school_reminders.view(state, state["members"]["parent"])
    assert parent == {
        "preparation_reminders": {
            "policy": {
                "enabled": True,
                "days_before": 1,
                "time": "20:00",
                "timezone": "Europe/Kyiv",
            },
            "self_targets": [
                {
                    "member": "child",
                    "member_revision": 2,
                    "recipient_revision": 4,
                    "enabled": True,
                    "subscription_revision": 1,
                },
                {
                    "member": "sibling",
                    "member_revision": 3,
                    "recipient_revision": 4,
                    "enabled": False,
                    "subscription_revision": None,
                },
            ],
        }
    }
    child = school_reminders.view(state, state["members"]["child"])
    assert child["preparation_reminders"]["self_targets"] == [
        {
            "member": "child",
            "member_revision": 2,
            "recipient_revision": 2,
            "enabled": True,
            "subscription_revision": 1,
        }
    ]
    assert (
        school_reminders.view(state, state["members"]["adult"])["preparation_reminders"][
            "self_targets"
        ]
        == []
    )
    assert state == before


def test_replay_requires_the_exact_current_private_subscription_and_receipt():
    state = state_fixture()
    request = payload(state)
    receipt = school_reminders.handle(context(state), "preparation_reminder_access_set", request)
    before = deepcopy(state)
    school_reminders.authorize_replay(
        context(state), "preparation_reminder_access_set", request, receipt
    )
    assert state == before
    rejected_unchanged(
        state,
        lambda: school_reminders.authorize_replay(
            context(state),
            "preparation_reminder_access_set",
            request,
            {**receipt, "enabled": False},
        ),
        "forbidden",
    )
    state["members"]["parent"]["revision"] = 5
    with pytest.raises(DomainError, match="conflict"):
        school_reminders.authorize_replay(
            context(state), "preparation_reminder_access_set", request, receipt
        )


def test_tick_creates_one_content_free_private_intent_without_other_effects():
    state = state_fixture()
    subscribe(state)
    unchanged = deepcopy(
        {key: state[key] for key in ("tasks", "routine_runs", "court", "sequences")}
    )
    event = generated(state)
    assert event["recipient"] == "parent"
    assert event["key"] == school_reminders.KEY
    assert set(event["data"]) == school_reminders.EVENT_FIELDS
    assert all(
        word not in repr(event["data"])
        for word in ("Mathematics", "Workbook", "Pencil", "School week", "Pack school bag")
    )
    assert event["data"]["expires_at"] == "2026-09-08T05:30:00+00:00"
    assert school_reminders.delivery_allowed(state, event, NOW)
    assert {key: state[key] for key in unchanged} == unchanged


def test_five_minute_window_has_no_offline_backlog_and_defaults_are_opt_in_off():
    state = state_fixture()
    subscribe(state)
    school_reminders.tick(context(state, "owner", NOW + timedelta(minutes=6)))
    assert state["outbox"] == {}
    state["settings"].pop("school_preparation_reminders")
    state["settings"].pop("school_preparation_days_before")
    state["settings"].pop("school_preparation_time")
    projected = school_reminders.view(state, state["members"]["parent"])
    assert projected["preparation_reminders"]["policy"] == {
        "enabled": False,
        "days_before": 1,
        "time": "20:00",
        "timezone": "Europe/Kyiv",
    }
    school_reminders.tick(context(state, "owner", NOW))
    assert state["outbox"] == {}


def test_dedup_key_survives_source_edits_and_disable_reenable_in_same_window():
    state = state_fixture()
    subscribe(state)
    original = generated(state)
    table = state["school"]["timetables"]["ST000001"]
    table["revision"] = 6
    school_reminders.tick(context(state, "owner", NOW + timedelta(minutes=1)))
    assert list(state["outbox"].values()) == [original]

    school_reminders.handle(
        context(state),
        "preparation_reminder_access_set",
        payload(state, subscription_revision=1, enabled=False),
    )
    school_reminders.handle(
        context(state),
        "preparation_reminder_access_set",
        payload(state, subscription_revision=2, enabled=True),
    )
    school_reminders.tick(context(state, "owner", NOW + timedelta(minutes=2)))
    assert len(state["outbox"]) == 1
    assert not school_reminders.delivery_allowed(state, original, NOW)


def test_marker_limit_fails_closed_without_throwing_or_partial_effects():
    state = state_fixture()
    subscribe(state)
    state["school"]["preparation_reminder_markers"] = {
        f"marker-{index}": {} for index in range(school_reminders.MAX_MARKERS)
    }
    before = deepcopy(state)
    school_reminders.tick(context(state, "owner", NOW))
    assert state == before


def test_marker_limit_is_rechecked_before_each_recipient_insert():
    state = state_fixture()
    subscribe(state)
    subscribe(state, actor="child")
    state["school"]["preparation_reminder_markers"] = {
        f"marker-{index}": {} for index in range(school_reminders.MAX_MARKERS - 1)
    }

    school_reminders.tick(context(state, "owner", NOW))

    assert len(state["school"]["preparation_reminder_markers"]) == school_reminders.MAX_MARKERS
    assert len(state["outbox"]) == 1


def test_dst_gap_is_skipped_and_autumn_fold_uses_one_first_occurrence():
    spring = state_fixture(lesson_date="2026-03-29")
    spring["settings"].update(school_preparation_days_before=0, school_preparation_time="03:30")
    subscribe(spring)
    school_reminders.tick(context(spring, "owner", datetime(2026, 3, 29, 1, 30, tzinfo=UTC)))
    assert spring["outbox"] == {}

    autumn = state_fixture(lesson_date="2026-10-25")
    autumn["settings"].update(school_preparation_days_before=0, school_preparation_time="03:30")
    subscribe(autumn)
    trigger = recurrence.local_clock(
        datetime(2026, 10, 25, tzinfo=UTC).date(), "03:30", "Europe/Kyiv"
    )
    assert trigger is not None and trigger.fold == 0
    generated(autumn, trigger.astimezone(UTC) + timedelta(minutes=2))
    school_reminders.tick(context(autumn, "owner", trigger.astimezone(UTC) + timedelta(minutes=3)))
    assert len(autumn["outbox"]) == 1


def test_quiet_hours_may_defer_only_until_the_first_lesson_expiry():
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    deferred = quiet_until(
        NOW,
        {
            "quiet_enabled": True,
            "timezone": "Europe/Kyiv",
            "quiet_start": "19:00",
            "quiet_end": "09:00",
        },
    )
    assert deferred is not None
    assert deferred.astimezone(UTC) > datetime.fromisoformat(event["data"]["expires_at"])
    assert not school_reminders.delivery_allowed(state, event, deferred)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state["school"]["timetables"]["ST000001"].update(status="archived"),
        lambda state: state["school"]["timetables"]["ST000001"].update(revision=6),
        lambda state: state["members"]["child"].update(revision=3),
        lambda state: state["members"]["parent"].update(revision=5),
        lambda state: next(
            iter(state["school"]["preparation_reminder_subscriptions"].values())
        ).update(enabled=False),
        lambda state: state["settings"].update(school_preparation_time="19:59"),
        lambda state: state["settings"]["modules"].remove("routines"),
        lambda state: state["routines"]["RT000001"].update(enabled=False),
        lambda state: state["school"]["timetables"]["ST000001"]["exceptions"].append("2026-09-08"),
        lambda state: state["school"]["preparations"].update(
            SP000001={
                "id": "SP000001",
                "timetable_id": "ST000001",
                "date": "2026-09-08",
            }
        ),
    ],
)
def test_delivery_race_rechecks_every_source_authority_and_policy(mutate):
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    changed = deepcopy(state)
    mutate(changed)
    assert not school_reminders.delivery_allowed(changed, event, NOW)


def test_malformed_or_foreign_events_fail_closed_without_state_changes():
    state = state_fixture()
    subscribe(state)
    event = generated(state)
    before = deepcopy(state)
    assert not school_reminders.delivery_allowed(state, {**event, "recipient": "child"}, NOW)
    assert not school_reminders.delivery_allowed(
        state, {**event, "data": {**event["data"], "materials": []}}, NOW
    )
    assert not school_reminders.delivery_allowed(state, event, None)
    assert state == before
