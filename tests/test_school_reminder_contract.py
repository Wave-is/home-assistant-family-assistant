"""Adversarial privacy and source-currentness contract for School reminders."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import school_reminders
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 7, 17, 2, tzinfo=UTC)


def reminder_state():
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
                "name": "PARENT-NAME-CANARY",
                "role": "parent",
                "active": True,
                "revision": 4,
            },
            "child": {
                "id": "child",
                "name": "CHILD-NAME-CANARY",
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
        },
        "school": {
            "timetables": {
                "ST000001": {
                    "id": "ST000001",
                    "revision": 5,
                    "member": "child",
                    "member_revision": 2,
                    "title": "TIMETABLE-TITLE-CANARY",
                    "valid_from": "2026-01-01",
                    "valid_until": "2026-12-31",
                    "exceptions": [],
                    "lessons": [
                        {
                            "weekday": 1,
                            "start": "08:30",
                            "end": "09:15",
                            "subject": "SUBJECT-CANARY",
                            "room": "ROOM-CANARY",
                            "materials": ["MATERIAL-CANARY"],
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
                "title": "ROUTINE-TITLE-CANARY",
                "description": "ROUTINE-DESCRIPTION-CANARY",
                "creator": "parent",
                "enabled": True,
                "assignees": ["child"],
                "steps": [
                    {
                        "title": "ROUTINE-STEP-CANARY",
                        "confirmation": "manual",
                        "assignee": None,
                    }
                ],
            }
        },
        "outbox": {},
        "tasks": {"sentinel": {"private": "TASK-CANARY"}},
        "routine_runs": {"sentinel": {"private": "RUN-CANARY"}},
        "court": {"sentinel": {"points": 17}},
        "alarms": {"sentinel": {"enabled": True}},
        "network": {"sentinel": {"device": "DEVICE-CANARY"}},
        "audit": [],
        "sequences": {},
    }


def context(state, actor="parent", *, now=NOW, operation="school-reminder-contract"):
    return Context(state, state["members"][actor], now, operation)


def request(state, actor="parent", member="child", **changes):
    return {
        "member": member,
        "member_revision": state["members"][member]["revision"],
        "recipient_revision": state["members"][actor]["revision"],
        "subscription_revision": None,
        "enabled": True,
        **changes,
    }


def subscribe(state, actor="parent", member="child", **changes):
    return school_reminders.handle(
        context(state, actor),
        school_reminders.ACTION,
        request(state, actor, member, **changes),
    )


def event_for(state, recipient="parent"):
    return next(event for event in state["outbox"].values() if event["recipient"] == recipient)


def reject_unchanged(state, call, code):
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code
    assert state == before


def test_subscription_is_actor_owned_child_scoped_and_replay_epoch_bound():
    state = reminder_state()
    child_payload = request(state, "child")
    receipt = school_reminders.handle(
        context(state, "child"), school_reminders.ACTION, child_payload
    )
    assert receipt == {"member": "child", "enabled": True, "revision": 1}
    school_reminders.authorize_replay(
        context(state, "child"), school_reminders.ACTION, child_payload, receipt
    )

    reject_unchanged(
        state,
        lambda: school_reminders.handle(
            context(state, "sibling"),
            school_reminders.ACTION,
            request(state, "sibling", "child"),
        ),
        "forbidden",
    )
    reject_unchanged(
        state,
        lambda: school_reminders.handle(
            context(state, "parent"),
            school_reminders.ACTION,
            request(state, recipient_revision=state["members"]["parent"]["revision"] + 1),
        ),
        "conflict",
    )
    reject_unchanged(
        state,
        lambda: school_reminders.handle(
            context(state, "parent"),
            school_reminders.ACTION,
            {**request(state), "recipient": "child"},
        ),
        "invalid_field",
    )

    state["members"]["child"]["revision"] += 1
    with pytest.raises(DomainError) as caught:
        school_reminders.authorize_replay(
            context(state, "child"), school_reminders.ACTION, child_payload, receipt
        )
    assert caught.value.code == "conflict"


@pytest.mark.parametrize(
    ("member", "member_revision"),
    [("child", 2), ("child", 999), ("missing", 1), ("adult", 1)],
)
def test_child_cross_target_subscription_has_no_member_or_revision_oracle(member, member_revision):
    state = reminder_state()
    cross_target = {
        "member": member,
        "member_revision": member_revision,
        "recipient_revision": state["members"]["sibling"]["revision"],
        "subscription_revision": None,
        "enabled": True,
    }
    reject_unchanged(
        state,
        lambda: school_reminders.handle(
            context(state, "sibling"), school_reminders.ACTION, cross_target
        ),
        "forbidden",
    )


def test_views_never_union_different_recipients_subscriptions():
    state = reminder_state()
    subscribe(state, "parent")
    subscribe(state, "child")
    school_reminders.handle(
        context(state, "parent"),
        school_reminders.ACTION,
        request(state, subscription_revision=1, enabled=False),
    )

    parent = school_reminders.view(state, state["members"]["parent"])
    child = school_reminders.view(state, state["members"]["child"])
    sibling = school_reminders.view(state, state["members"]["sibling"])
    adult = school_reminders.view(state, state["members"]["adult"])
    assert parent["preparation_reminders"]["self_targets"][0]["enabled"] is False
    assert parent["preparation_reminders"]["self_targets"][0]["subscription_revision"] == 2
    assert child["preparation_reminders"]["self_targets"] == [
        {
            "member": "child",
            "member_revision": 2,
            "recipient_revision": 2,
            "enabled": True,
            "subscription_revision": 1,
        }
    ]
    assert sibling["preparation_reminders"]["self_targets"] == [
        {
            "member": "sibling",
            "member_revision": 3,
            "recipient_revision": 3,
            "enabled": False,
            "subscription_revision": None,
        }
    ]
    assert adult == {"preparation_reminders": {"policy": None, "self_targets": []}}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state["settings"].update(school_preparation_reminders=False),
        lambda state: state["settings"].update(school_preparation_time="20:01"),
        lambda state: state["school"]["timetables"]["ST000001"].update(revision=6),
        lambda state: state["school"]["timetables"]["ST000001"].update(status="archived"),
        lambda state: state["members"]["child"].update(revision=3),
        lambda state: state["members"]["child"].update(role="adult"),
        lambda state: state["members"]["parent"].update(revision=5),
        lambda state: state["routines"]["RT000001"].update(revision=8),
        lambda state: state["routines"]["RT000001"].update(enabled=False),
        lambda state: state["routines"]["RT000001"].update(assignees=[]),
        lambda state: next(
            iter(state["school"]["preparation_reminder_subscriptions"].values())
        ).update(enabled=False),
        lambda state: state["school"]["preparations"].update(
            SP000001={
                "id": "SP000001",
                "timetable_id": "ST000001",
                "date": "2026-09-08",
            }
        ),
    ],
)
def test_durable_intent_delivery_rejects_every_current_authority_drift(mutate):
    state = reminder_state()
    subscribe(state)
    school_reminders.tick(context(state, "owner", operation="reminder-tick"))
    event = deepcopy(event_for(state))
    changed = deepcopy(state)
    mutate(changed)
    before = deepcopy(changed)
    assert not school_reminders.delivery_allowed(changed, event, NOW)
    assert changed == before


def test_marker_is_once_per_recipient_timetable_day_across_source_edit_and_reenable():
    state = reminder_state()
    subscribe(state, "parent")
    subscribe(state, "child")
    school_reminders.tick(context(state, "owner", operation="first-tick"))
    assert len(state["outbox"]) == 2
    assert len(state["school"]["preparation_reminder_markers"]) == 2
    original = deepcopy(event_for(state, "parent"))

    table = state["school"]["timetables"]["ST000001"]
    table["revision"] = 6
    state["routines"]["RT000001"]["revision"] = 8
    table["backpack_routine"]["revision"] = 8
    school_reminders.handle(
        context(state, "parent"),
        school_reminders.ACTION,
        request(state, subscription_revision=1, enabled=False),
    )
    school_reminders.handle(
        context(state, "parent"),
        school_reminders.ACTION,
        request(state, subscription_revision=2, enabled=True),
    )
    school_reminders.tick(
        context(state, "owner", now=NOW + timedelta(minutes=2), operation="second-tick")
    )

    assert len(state["outbox"]) == 2
    assert len(state["school"]["preparation_reminder_markers"]) == 2
    assert not school_reminders.delivery_allowed(state, original, NOW)


def test_tick_and_delivery_are_content_free_pure_and_have_no_domain_side_effects():
    state = reminder_state()
    protected = {
        key: deepcopy(state[key]) for key in ("tasks", "routine_runs", "court", "alarms", "network")
    }
    receipt = subscribe(state)
    school_reminders.tick(context(state, "owner", operation="content-free-tick"))
    event = event_for(state)

    assert set(event["data"]) == school_reminders.EVENT_FIELDS
    rendered = repr({"receipt": receipt, "outbox": state["outbox"], "audit": state["audit"]})
    for canary in (
        "PARENT-NAME-CANARY",
        "CHILD-NAME-CANARY",
        "TIMETABLE-TITLE-CANARY",
        "SUBJECT-CANARY",
        "ROOM-CANARY",
        "MATERIAL-CANARY",
        "ROUTINE-TITLE-CANARY",
        "ROUTINE-DESCRIPTION-CANARY",
        "ROUTINE-STEP-CANARY",
    ):
        assert canary not in rendered
    assert all(state[key] == value for key, value in protected.items())
    before = deepcopy(state)
    assert school_reminders.delivery_allowed(state, event, NOW)
    assert state == before


def test_delivery_event_cannot_be_retargeted_or_detached_from_its_marker():
    state = reminder_state()
    subscribe(state)
    school_reminders.tick(context(state, "owner", operation="binding-tick"))
    event = deepcopy(event_for(state))

    forged_recipient = deepcopy(event)
    forged_recipient["recipient"] = "child"
    forged_recipient["data"]["recipient_revision"] = 2
    assert not school_reminders.delivery_allowed(state, forged_recipient, NOW)

    wrong_event_id = deepcopy(event)
    wrong_event_id["id"] = "N-FORGED"
    assert not school_reminders.delivery_allowed(state, wrong_event_id, NOW)

    extra_content = deepcopy(event)
    extra_content["data"]["materials"] = ["MATERIAL-CANARY"]
    assert not school_reminders.delivery_allowed(state, extra_content, NOW)
