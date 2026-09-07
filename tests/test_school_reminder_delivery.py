"""Delivery boundary tests for private School preparation reminders."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import school_reminders
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.notifications import DeliveryError, Notifications
from custom_components.family_assistant.telegram.messages import render, targets

NOW = datetime(2026, 9, 7, 17, 2, tzinfo=UTC)


class Transport:
    def __init__(self):
        self.calls = []

    async def send(self, event, target):
        self.calls.append((deepcopy(event), deepcopy(target)))
        return f"message-{len(self.calls)}"


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class ClaimGateEngine(Engine):
    """Pause only after the delivery claim has been durably persisted."""

    def __init__(self, state, persist):
        super().__init__(state, persist)
        self.claimed = asyncio.Event()
        self.release = asyncio.Event()

    async def system_update(self, kind, now, change):
        result = await super().system_update(kind, now, change)
        if kind == "outbox_claim" and result is not None:
            self.claimed.set()
            await self.release.wait()
        return result


def enabled(engine, store, *, many_materials=False):
    state = engine.snapshot()
    state["settings"].update(
        modules=sorted({*state["settings"]["modules"], "school", "routines"}),
        timezone="Europe/Kyiv",
        school_preparation_reminders=True,
        school_preparation_days_before=1,
        school_preparation_time="20:00",
    )
    state["members"]["owner"].update(telegram_id=1001, language="en")
    state["members"]["parent"].update(telegram_id=1002, language="en", name="Parent Current")
    state["members"]["child"].update(telegram_id=1003, language="uk", name="Child Current")
    state["telegram"]["group_id"] = -1000
    lessons = [
        {
            "weekday": 1,
            "start": "08:30",
            "end": "09:15",
            "subject": "Mathematics",
            "room": "12",
            "materials": ["Workbook", "Pencil"],
        }
    ]
    if many_materials:
        lessons = [
            {
                "weekday": 1,
                "start": start,
                "end": end,
                "subject": f"Subject {lesson_index}",
                "room": "",
                "materials": [
                    f"Material {lesson_index}-{material_index}" for material_index in range(10)
                ],
            }
            for lesson_index, (start, end) in enumerate(
                (("08:30", "09:15"), ("10:00", "10:45"), ("12:00", "12:45"))
            )
        ]
    state["school"] = {
        "timetables": {
            "ST000001": {
                "id": "ST000001",
                "revision": 5,
                "member": "child",
                "member_revision": state["members"]["child"]["revision"],
                "title": "Current school week",
                "valid_from": "2026-01-01",
                "valid_until": "2026-12-31",
                "exceptions": [],
                "lessons": lessons,
                "backpack_routine": {"id": "RT000001", "revision": 7},
                "status": "active",
            }
        },
        "preparations": {},
        "preparation_reminder_subscriptions": {},
        "preparation_reminder_markers": {},
    }
    state["routines"]["RT000001"] = {
        "id": "RT000001",
        "revision": 7,
        "title": "Pack school bag",
        "description": "PRIVATE ROUTINE DESCRIPTION",
        "creator": "parent",
        "enabled": True,
        "assignees": ["child"],
        "steps": [
            {
                "title": "PRIVATE ROUTINE STEP",
                "confirmation": "manual",
                "assignee": None,
            }
        ],
    }
    return Engine(state, store.save)


async def seed_event(engine):
    def seed(ctx):
        parent = ctx.state["members"]["parent"]
        child = ctx.state["members"]["child"]
        school_reminders.handle(
            Context(ctx.state, parent, ctx.now, "parent-school-reminder-opt-in"),
            school_reminders.ACTION,
            {
                "member": child["id"],
                "member_revision": child["revision"],
                "recipient_revision": parent["revision"],
                "subscription_revision": None,
                "enabled": True,
            },
        )
        school_reminders.tick(ctx)

    await engine.system_update("seed_school_reminder", NOW, seed)
    [event] = [
        item for item in engine.snapshot()["outbox"].values() if item["key"] == school_reminders.KEY
    ]
    return event


@pytest.mark.asyncio
async def test_private_target_and_localized_render_resolve_content_only_at_send_time(engine, store):
    engine = enabled(engine, store, many_materials=True)
    event = await seed_event(engine)
    state = engine.snapshot()

    assert event["recipient"] == "parent"
    assert set(event["data"]) == school_reminders.EVENT_FIELDS
    assert not any(
        canary in repr(event)
        for canary in (
            "Parent Current",
            "Child Current",
            "Current school week",
            "Pack school bag",
            "Material 0-0",
            "PRIVATE",
        )
    )
    assert targets(event, state) == [{"channel": "telegram", "id": 1002, "language": "en"}]
    assert all(target["id"] not in {-1000, 1001, 1003} for target in targets(event, state))

    phrases = {
        "en": ("School preparation", "nothing was started automatically", "more"),
        "ru": ("Подготовка к школе", "автоматически ничего не запускалось", "ещё"),
        "uk": ("Підготовка до школи", "автоматично нічого не запускалося", "ще"),
    }
    for language, expected in phrases.items():
        message = render(event, {"id": 1002, "language": language}, state)
        assert message["chat_id"] == 1002
        assert len(message["text"]) <= 4000
        assert all(phrase in message["text"] for phrase in expected)
        assert "Child Current" in message["text"]
        assert "Current school week" in message["text"]
        assert "Pack school bag" in message["text"]
        assert "Material 0-0" in message["text"]
        assert "PRIVATE ROUTINE" not in message["text"]
        assert message["link_preview_options"] == {"is_disabled": True}
        assert "parse_mode" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state["settings"].update(school_preparation_reminders=False),
        lambda state: state["school"]["timetables"]["ST000001"].update(revision=6),
        lambda state: state["routines"]["RT000001"].update(enabled=False),
        lambda state: state["members"]["child"].update(revision=2),
    ],
)
async def test_claim_gate_supersedes_revoked_source_before_transport(engine, store, mutate):
    engine = enabled(engine, store)
    event = await seed_event(engine)
    await engine.system_update("revoke_before_claim", NOW, lambda ctx: mutate(ctx.state))
    transport = Transport()

    assert await Notifications(engine, targets, transport.send).run(NOW) == 0
    assert transport.calls == []
    stored = engine.snapshot()["outbox"][event["id"]]
    assert stored["state"] == "superseded"
    assert not stored.get("deliveries")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state["settings"].update(school_preparation_time="20:01"),
        lambda state: state["school"]["timetables"]["ST000001"].update(status="archived"),
        lambda state: state["routines"]["RT000001"].update(revision=8),
        lambda state: state["members"]["parent"].update(revision=2),
    ],
)
async def test_final_dispatch_gate_rechecks_after_persisted_claim(engine, store, mutate):
    seeded = enabled(engine, store)
    event = await seed_event(seeded)
    gated = ClaimGateEngine(seeded.snapshot(), store.save)
    transport = Transport()
    running = asyncio.create_task(Notifications(gated, targets, transport.send).run(NOW))
    await asyncio.wait_for(gated.claimed.wait(), timeout=2)

    await gated.system_update("revoke_after_claim", NOW, lambda ctx: mutate(ctx.state))
    gated.release.set()
    assert await asyncio.wait_for(running, timeout=2) == 0
    assert transport.calls == []
    stored = gated.snapshot()["outbox"][event["id"]]
    assert stored["state"] == "superseded"
    assert {item["state"] for item in stored["deliveries"].values()} == {"superseded"}


@pytest.mark.asyncio
async def test_final_dispatch_gate_uses_live_time_after_persisted_claim(engine, store):
    seeded = enabled(engine, store)
    event = await seed_event(seeded)
    gated = ClaimGateEngine(seeded.snapshot(), store.save)
    transport = Transport()
    clock = Clock(NOW)
    worker = Notifications(gated, targets, transport.send, clock=clock)
    running = asyncio.create_task(worker.run(NOW))
    await asyncio.wait_for(gated.claimed.wait(), timeout=2)

    clock.now = datetime.fromisoformat(event["data"]["expires_at"])
    gated.release.set()
    assert await asyncio.wait_for(running, timeout=2) == 0
    assert transport.calls == []
    stored = gated.snapshot()["outbox"][event["id"]]
    assert stored["state"] == "superseded"
    assert {item["state"] for item in stored["deliveries"].values()} == {"superseded"}


@pytest.mark.asyncio
async def test_quiet_hours_that_begin_after_claim_defer_without_sending(engine, store):
    seeded = enabled(engine, store)
    event = await seed_event(seeded)
    gated = ClaimGateEngine(seeded.snapshot(), store.save)
    transport = Transport()
    clock = Clock(NOW)
    worker = Notifications(gated, targets, transport.send, clock=clock)
    running = asyncio.create_task(worker.run(NOW))
    await asyncio.wait_for(gated.claimed.wait(), timeout=2)

    await gated.system_update(
        "quiet_after_claim",
        NOW,
        lambda ctx: ctx.state["settings"].update(
            notifications={
                "quiet_enabled": True,
                "quiet_start": "20:03",
                "quiet_end": "20:30",
                "timezone": "Europe/Kyiv",
            }
        ),
    )
    clock.now = NOW + timedelta(minutes=1)
    gated.release.set()
    assert await asyncio.wait_for(running, timeout=2) == 0
    assert transport.calls == []
    stored = gated.snapshot()["outbox"][event["id"]]
    assert stored["state"] == "pending"
    assert {item["state"] for item in stored["deliveries"].values()} == {"pending"}


@pytest.mark.asyncio
async def test_quiet_hours_never_extend_delivery_past_first_lesson(engine, store):
    engine = enabled(engine, store)
    event = await seed_event(engine)
    await engine.system_update(
        "enable_quiet_hours",
        NOW,
        lambda ctx: ctx.state["settings"].update(
            notifications={
                "quiet_enabled": True,
                "quiet_start": "20:00",
                "quiet_end": "09:00",
                "timezone": "Europe/Kyiv",
            }
        ),
    )
    transport = Transport()
    worker = Notifications(engine, targets, transport.send)

    assert await worker.run(NOW) == 0
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "pending"
    expiry = datetime.fromisoformat(event["data"]["expires_at"])
    assert await worker.run(expiry) == 0
    assert transport.calls == []
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "superseded"


@pytest.mark.asyncio
async def test_target_and_render_fail_closed_after_source_revocation(engine, store):
    engine = enabled(engine, store)
    event = await seed_event(engine)
    state = engine.snapshot()
    state["routines"]["RT000001"]["revision"] = 8

    assert targets(event, state) == []
    with pytest.raises(DeliveryError) as caught:
        render(event, {"id": 1002, "language": "en"}, state)
    assert caught.value.code == "delivery_revoked"


@pytest.mark.asyncio
async def test_render_rejects_a_target_that_is_not_the_current_private_binding(engine, store):
    engine = enabled(engine, store)
    event = await seed_event(engine)
    state = engine.snapshot()

    with pytest.raises(DeliveryError) as caught:
        render(event, {"id": -1000, "language": "en"}, state)
    assert caught.value.code == "delivery_revoked"
