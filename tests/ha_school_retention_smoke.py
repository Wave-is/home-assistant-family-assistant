"""Actual Home Assistant acceptance helper for school reminder retention health."""

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch


class MemoryStore:
    def __init__(self):
        self.value = None
        self.fail = False
        self.calls = 0

    async def save(self, state):
        self.calls += 1
        if self.fail:
            raise OSError("synthetic persistence failure")
        self.value = deepcopy(state)


class FaultingStore:
    """Inject a failure before delegating to the real HA Store."""

    def __init__(self, store):
        self.store = store
        self.fail = False

    async def save(self, state):
        if self.fail:
            raise OSError("synthetic persistence failure")
        await self.store.async_save(state)


def _engine(store, *, child_subscription=False, orphan=False):
    from custom_components.family_assistant.domain import routines, school, school_reminders
    from custom_components.family_assistant.domain.context import Context
    from custom_components.family_assistant.domain.engine import Engine, new_state

    state = new_state(
        "school-retention-owner",
        "School retention smoke",
        modules=["school", "routines"],
        timezone="Europe/Kyiv",
    )
    state["settings"].update(
        school_preparation_reminders=True,
        school_preparation_days_before=1,
        school_preparation_time="20:00",
    )
    for member_id, role in (("parent", "parent"), ("child", "child")):
        state["members"][member_id] = {
            "id": member_id,
            "name": member_id.title(),
            "role": role,
            "language": "en",
            "ha_user_id": f"school-retention-{member_id}",
            "aliases": [],
            "active": True,
            "revision": 1,
        }
    now = datetime(2026, 9, 7, 17, 2, tzinfo=UTC)
    ctx = Context(state, state["members"]["parent"], now, "school-retention-source")
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
            "member": "child",
            "member_revision": 1,
            "title": "School week",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "exceptions": [],
            "lessons": [
                {
                    "weekday": 1,
                    "start": "08:30",
                    "end": "09:15",
                    "subject": "Mathematics",
                    "room": "12",
                    "materials": ["Workbook"],
                }
            ],
            "backpack_routine": {"id": routine["id"], "revision": routine["revision"]},
        },
    )
    for actor_id in ["parent", "child"] if child_subscription else ["parent"]:
        actor = state["members"][actor_id]
        school_reminders.handle(
            Context(state, actor, now, f"school-retention-subscribe-{actor_id}"),
            school_reminders.ACTION,
            {
                "member": "child",
                "member_revision": 1,
                "recipient_revision": 1,
                "subscription_revision": None,
                "enabled": True,
            },
        )
    if orphan:
        state["outbox"]["retained-canary"] = {
            "id": "retained-canary",
            "recipient": "private-canary",
            "key": school_reminders.KEY,
            "data": {},
            "created_at": now.isoformat(),
            "state": "uncertain",
            "attempts": 1,
        }
    return Engine(state, store.save), now


async def verify_school_retention(hass, entry):
    """Verify real Engine persistence plus the real HA IssueRegistry boundary."""
    from homeassistant.helpers import issue_registry as ir
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant import school_reminder_health
    from custom_components.family_assistant.domain import school_reminders, school_retention
    from custom_components.family_assistant.domain.engine import Engine

    store = Store(hass, 1, f"family_assistant.school_retention_smoke.{entry.entry_id}")
    persist = FaultingStore(store)
    engine, now = _engine(persist)
    await store.async_save(engine.snapshot())
    assert await engine.tick(now)
    event = next(
        value
        for value in engine.snapshot()["outbox"].values()
        if value.get("key") == school_reminders.KEY
    )
    event_id = event["id"]

    def sent(ctx):
        current = ctx.state["outbox"][event_id]
        current["state"] = "sent"
        current["deliveries"] = {"telegram:synthetic": {"state": "sent"}}

    await engine.system_update("school-retention-sent", now, sent)
    expires = datetime.fromisoformat(event["data"]["expires_at"])
    prune_at = expires + school_retention.SUCCESS_RETENTION
    before = engine.snapshot()
    persist.fail = True
    try:
        await engine.tick(prune_at)
    except OSError:
        pass
    else:
        raise AssertionError("synthetic Store failure was not propagated")
    assert engine.snapshot() == before
    assert await store.async_load() == before

    persist.fail = False
    assert await engine.tick(prune_at)
    after = engine.snapshot()
    assert event_id not in after["outbox"]
    assert after["school"]["preparation_reminder_retention"]["through_date"] == "2026-09-08"
    stored = await store.async_load()
    assert stored == after
    reloaded = Engine(stored, persist.save)
    assert (
        reloaded.snapshot()["school"]["preparation_reminder_retention"]
        == after["school"]["preparation_reminder_retention"]
    )
    assert not await reloaded.tick(now)
    assert not any(
        value.get("key") == school_reminders.KEY for value in reloaded.snapshot()["outbox"].values()
    )

    cap_store = MemoryStore()
    capped, cap_now = _engine(cap_store, child_subscription=True, orphan=True)
    with patch.object(school_retention, "MAX_RECORDS", 2):
        assert await capped.tick(cap_now)
    capped_state = capped.snapshot()
    assert (
        sum(
            value.get("key") == school_reminders.KEY
            for value in capped_state["outbox"].values()
            if isinstance(value, dict)
        )
        == 2
    )
    assert len(capped_state["school"]["preparation_reminder_markers"]) == 1

    class SnapshotEngine:
        def __init__(self, value):
            self.value = value

        def snapshot(self):
            return deepcopy(self.value)

    fake_entry = SimpleNamespace(entry_id=f"{entry.entry_id}_school_retention_smoke")
    runtime = SimpleNamespace(engine=SnapshotEngine(capped_state), health={})
    issue_id = f"{fake_entry.entry_id}_school_retention"
    with patch.object(school_retention, "MAX_RECORDS", 2):
        stats = school_reminder_health.synchronize(hass, fake_entry, runtime, cap_now)
    assert stats["capacity"] is True
    assert stats["unpaired"] == 1
    assert "private-canary" not in repr(stats)
    assert runtime.health == {"school_retention": "school_retention_attention"}
    registry = ir.async_get(hass)
    assert registry.async_get_issue("family_assistant", issue_id) is not None

    base_health = {
        "settings": {"timezone": "UTC"},
        "school": {"preparation_reminder_markers": {}},
        "outbox": {},
    }
    runtime.engine.value = deepcopy(base_health)
    runtime.engine.value["school"]["preparation_reminder_markers"]["broken"] = {
        "event_id": "missing"
    }
    stats = school_reminder_health.synchronize(hass, fake_entry, runtime, cap_now)
    assert stats["capacity"] is False and stats["unpaired"] == 1
    assert registry.async_get_issue("family_assistant", issue_id) is not None

    runtime.engine.value = deepcopy(base_health)
    runtime.engine.value["school"]["preparation_reminder_retention"] = {
        "through_date": "2026-09-08"
    }
    stats = school_reminder_health.synchronize(hass, fake_entry, runtime, cap_now)
    assert stats["retention_errors"] == 1
    assert registry.async_get_issue("family_assistant", issue_id) is not None

    runtime.engine.value = deepcopy(base_health)
    runtime.engine.value["school"]["preparation_reminder_retention"] = {
        "through_date": "2026-09-08",
        "updated_at": cap_now.isoformat(),
    }
    stats = school_reminder_health.synchronize(
        hass, fake_entry, runtime, datetime(2026, 9, 8, 8, tzinfo=UTC)
    )
    assert stats["clock_rollback"] is True
    assert registry.async_get_issue("family_assistant", issue_id) is not None

    runtime.engine.value = base_health
    stats = school_reminder_health.synchronize(hass, fake_entry, runtime, cap_now)
    assert stats["capacity"] is False
    assert runtime.health == {}
    assert registry.async_get_issue("family_assistant", issue_id) is None
    print("PASS school reminder retention: Engine/Store/rollback/cap/Repair")
