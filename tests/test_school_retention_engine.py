"""Engine integration for bounded school reminder retention and replay floors."""

from copy import deepcopy

import pytest
from test_school_reminders import NOW, payload, state_fixture

from custom_components.family_assistant.domain import (
    routines,
    school,
    school_reminders,
    school_retention,
)
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import timestamp


@pytest.fixture
def retention_engine(engine, store):
    state = engine.snapshot()
    source = state_fixture()
    state["settings"].update(source.pop("settings"))
    source["members"] = {
        key: {**state["members"][key], **member} for key, member in source["members"].items()
    }
    table = source["school"]["timetables"]["ST000001"]
    source["school"]["timetables"] = {}
    source["routines"] = {}
    state.update(source)
    ctx = Context(state, state["members"]["parent"], NOW, "retention-source")
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


async def subscribe(engine, actor="parent", operation="retention-subscribe"):
    return await engine.execute(
        actor,
        "school.preparation_reminder_access_set",
        payload(engine.snapshot(), actor, member="child"),
        operation,
        NOW,
    )


async def generate(engine):
    await subscribe(engine)
    assert await engine.tick(NOW)
    state = engine.snapshot()
    event = next(
        event for event in state["outbox"].values() if event.get("key") == school_reminders.KEY
    )
    return event["id"]


async def terminal(engine, event_id, state="sent", delivery="sent"):
    def change(ctx):
        event = ctx.state["outbox"][event_id]
        event["state"] = state
        event["deliveries"] = {"telegram:bot": {"state": delivery}}

    await engine.system_update("school-retention-terminal", NOW, change)


def settings_payload(engine, modules):
    settings = engine.snapshot()["settings"]
    return {
        "name": settings["name"],
        "language": settings["language"],
        "modules": modules,
    }


@pytest.mark.asyncio
async def test_terminal_pair_prune_is_atomic_persisted_and_runs_module_off(retention_engine, store):
    engine = retention_engine
    event_id = await generate(engine)
    await terminal(engine, event_id)
    modules = [item for item in engine.snapshot()["settings"]["modules"] if item != "school"]
    await engine.execute(
        "owner",
        "settings.save",
        settings_payload(engine, modules),
        "school-module-off",
        NOW,
    )
    before = engine.snapshot()
    expires = timestamp(before["outbox"][event_id]["data"]["expires_at"], "expires_at")
    prune_now = expires + school_retention.SUCCESS_RETENTION

    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(prune_now)
    assert engine.snapshot() == before

    store.fail = False
    assert await engine.tick(prune_now)
    after = engine.snapshot()
    assert event_id not in after["outbox"]
    assert after["school"]["preparation_reminder_markers"] == {}
    assert after["school"]["preparation_reminder_retention"]["through_date"] == "2026-09-08"
    assert after["settings"]["modules"] == modules
    assert all(after[key] == before[key] for key in ("tasks", "routine_runs", "court"))

    restored = Engine(store.value, store.save)
    assert (
        restored.snapshot()["school"]["preparation_reminder_retention"]
        == after["school"]["preparation_reminder_retention"]
    )


@pytest.mark.asyncio
async def test_clock_rollback_floor_prevents_same_school_date_reissue(retention_engine):
    engine = retention_engine
    event_id = await generate(engine)
    await terminal(engine, event_id)
    event = engine.snapshot()["outbox"][event_id]
    expires = timestamp(event["data"]["expires_at"], "expires_at")
    assert await engine.tick(expires + school_retention.SUCCESS_RETENTION)
    retired = deepcopy(engine.snapshot()["school"]["preparation_reminder_retention"])

    writes_before = engine.snapshot()["revision"]
    assert not await engine.tick(NOW)
    rolled_back = engine.snapshot()
    assert rolled_back["revision"] == writes_before
    assert rolled_back["school"]["preparation_reminder_retention"] == retired
    assert not any(
        event.get("key") == school_reminders.KEY for event in rolled_back["outbox"].values()
    )


@pytest.mark.asyncio
async def test_retained_event_cap_is_rechecked_before_each_notify(retention_engine, monkeypatch):
    engine = retention_engine
    await subscribe(engine, "parent", "parent-subscribe")
    await subscribe(engine, "child", "child-subscribe")

    def orphan(ctx):
        ctx.state["outbox"]["retained-orphan"] = {
            "id": "retained-orphan",
            "recipient": "parent",
            "key": school_reminders.KEY,
            "data": {},
            "created_at": NOW.isoformat(),
            "state": "uncertain",
            "attempts": 1,
        }

    await engine.system_update("school-retention-cap", NOW, orphan)
    before_effects = deepcopy(
        {key: engine.snapshot()[key] for key in ("tasks", "routine_runs", "court")}
    )
    monkeypatch.setattr(school_retention, "MAX_RECORDS", 2)
    assert await engine.tick(NOW)
    state = engine.snapshot()
    events = [
        event for event in state["outbox"].values() if event.get("key") == school_reminders.KEY
    ]
    assert len(events) == 2
    assert len(state["school"]["preparation_reminder_markers"]) == 1
    assert {key: state[key] for key in before_effects} == before_effects


@pytest.mark.asyncio
async def test_capacity_or_malformed_floor_causes_no_write_or_notification(
    retention_engine, store, monkeypatch
):
    state = retention_engine.snapshot()
    state["school"]["preparation_reminder_markers"]["malformed"] = {"event_id": "missing"}
    engine = Engine(state, store.save)
    before = engine.snapshot()
    monkeypatch.setattr(school_retention, "MAX_RECORDS", 1)
    calls = store.calls
    assert not await engine.tick(NOW)
    assert engine.snapshot() == before
    assert store.calls == calls

    state = retention_engine.snapshot()
    state["school"]["preparation_reminder_retention"] = {"through_date": "2026-09-08"}
    engine = Engine(state, store.save)
    before = engine.snapshot()
    calls = store.calls
    assert not await engine.tick(NOW)
    assert engine.snapshot() == before
    assert store.calls == calls
