"""Real Engine transactions, clock and identity epochs for private subscriptions."""

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest
from test_school_reminders import NOW, payload, state_fixture

from custom_components.family_assistant.domain import routines, school
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def reminder_engine(engine, store):
    state = engine.snapshot()
    fixture = state_fixture()
    state["settings"].update(fixture.pop("settings"))
    fixture["members"] = {
        key: {**state["members"][key], **member} for key, member in fixture["members"].items()
    }
    table = fixture["school"]["timetables"]["ST000001"]
    fixture["school"]["timetables"] = {}
    fixture["routines"] = {}
    state.update(fixture)
    ctx = Context(state, state["members"]["parent"], NOW, "synthetic-source")
    routine = routines.handle(
        ctx,
        "save",
        {
            "title": "Pack school bag",
            "assignees": ["child"],
            "steps": [{"title": "Pack books"}],
        },
    )
    school.handle(
        ctx,
        "timetable_save",
        {
            key: value
            for key, value in table.items()
            if key not in {"id", "revision", "status", "backpack_routine"}
        }
        | {"backpack_routine": {"id": routine["id"], "revision": routine["revision"]}},
    )
    return Engine(state, store.save)


async def subscribe(engine, actor="parent", operation="subscribe", **changes):
    return await engine.execute(
        actor,
        "school.preparation_reminder_access_set",
        payload(engine.snapshot(), actor, **changes),
        operation,
        NOW,
    )


def settings_payload(engine, **changes):
    state = engine.snapshot()["settings"]
    return {key: state[key] for key in ("name", "language", "modules")} | changes


@pytest.mark.asyncio
async def test_subscription_concurrent_receipt_and_reloaded_replay(reminder_engine, store):
    engine = reminder_engine
    original = payload(engine.snapshot())
    receipts = await asyncio.gather(*[subscribe(engine) for _ in range(5)])
    assert receipts == [{"member": "child", "enabled": True, "revision": 1}] * 5
    assert store.calls == 1
    assert len(engine.snapshot()["school"]["preparation_reminder_subscriptions"]) == 1
    assert engine.snapshot()["outbox"] == {}
    restored = Engine(store.value, store.save)
    assert (
        await restored.execute(
            "parent", "school.preparation_reminder_access_set", original, "subscribe", NOW
        )
        == receipts[0]
    )
    await subscribe(restored, operation="disable", subscription_revision=1, enabled=False)
    before = restored.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await restored.execute(
            "parent", "school.preparation_reminder_access_set", original, "subscribe", NOW
        )
    assert restored.snapshot() == before


@pytest.mark.asyncio
async def test_subscription_store_and_batch_failures_atomic(reminder_engine, store):
    engine = reminder_engine
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await subscribe(engine)
    assert engine.snapshot() == before
    store.fail = False
    with pytest.raises(DomainError):
        await engine.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {
                        "action": "school.preparation_reminder_access_set",
                        "payload": payload(before),
                    },
                    {
                        "action": "school.preparation_reminder_access_set",
                        "payload": payload(before),
                    },
                ]
            },
            "batch-failure",
            NOW,
        )
    assert engine.snapshot() == before
    await subscribe(engine)
    before_tick = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(NOW)
    assert engine.snapshot() == before_tick
    store.fail = False
    assert await engine.tick(NOW)
    state = engine.snapshot()
    assert len(state["outbox"]) == 1
    assert len(state["school"]["preparation_reminder_markers"]) == 1
    assert all(state[key] == before_tick[key] for key in ("tasks", "routine_runs", "court"))
    writes = store.calls
    assert not await engine.tick(NOW + timedelta(minutes=1))
    assert store.calls == writes
    restored = Engine(store.value, store.save)
    assert not await restored.tick(NOW + timedelta(minutes=2))
    assert restored.snapshot() == state


@pytest.mark.asyncio
async def test_subscription_replay_scope_and_private_projection(reminder_engine, store):
    engine = reminder_engine
    await subscribe(engine)
    parent_row = engine.view("parent", now=NOW)["school"]["preparation_reminders"]["self_targets"]
    assert next(row for row in parent_row if row["member"] == "child")["enabled"] is True
    child_rows = engine.view("child", now=NOW)["school"]["preparation_reminders"]["self_targets"]
    assert child_rows == [
        {
            "member": "child",
            "member_revision": 2,
            "recipient_revision": 2,
            "enabled": False,
            "subscription_revision": None,
        }
    ]
    assert "school" not in engine.view("adult", now=NOW)
    for change in ("school", "parent", "child"):
        state = engine.snapshot()
        if change == "school":
            state["settings"]["modules"].remove("school")
        else:
            state["members"][change]["revision"] += 1
        changed = Engine(state, store.save)
        with pytest.raises(DomainError):
            await changed.execute(
                "parent",
                "school.preparation_reminder_access_set",
                payload(engine.snapshot()),
                "subscribe",
                NOW,
            )
        assert changed.snapshot() == state


@pytest.mark.parametrize(
    "field,value",
    [
        ("school_preparation_reminders", 1),
        ("school_preparation_reminders", "true"),
        ("school_preparation_days_before", True),
        ("school_preparation_days_before", -1),
        ("school_preparation_days_before", 2),
        ("school_preparation_days_before", 1.0),
        ("school_preparation_time", "24:00"),
        ("school_preparation_time", "8:00"),
        ("school_preparation_time", None),
        ("school_preparation_time", "20:00:00"),
    ],
)
@pytest.mark.asyncio
async def test_settings_strict_invalid_is_atomic(reminder_engine, field, value):
    engine = reminder_engine
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner",
            "settings.save",
            settings_payload(engine, name="Changed", **{field: value}),
            "bad-policy",
            NOW,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_old_store_defaults_and_partial_settings_preservation(reminder_engine, store):
    state = reminder_engine.snapshot()
    for field in (
        "school_preparation_reminders",
        "school_preparation_days_before",
        "school_preparation_time",
    ):
        state["settings"].pop(field)
    old = Engine(state, store.save)
    assert old.view("parent", now=NOW)["school"]["preparation_reminders"]["policy"] == {
        "enabled": False,
        "days_before": 1,
        "time": "20:00",
        "timezone": "Europe/Kyiv",
    }
    await old.execute(
        "owner",
        "settings.save",
        settings_payload(
            old,
            school_preparation_reminders=True,
            school_preparation_days_before=0,
            school_preparation_time="07:00",
        ),
        "enable-policy",
        NOW,
    )
    expected = deepcopy(old.snapshot()["settings"])
    await old.execute("owner", "settings.save", settings_payload(old), "save-other-settings", NOW)
    assert old.snapshot()["settings"] == expected
    assert Engine(store.value, store.save).snapshot()["settings"] == expected
