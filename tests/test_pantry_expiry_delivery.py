"""Pantry expiry reminders stay private, current, durable, and factual."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.notifications import Notifications
from custom_components.family_assistant.telegram.messages import render, targets


class Transport:
    def __init__(self):
        self.calls = []

    async def send(self, event, target):
        self.calls.append((deepcopy(event), deepcopy(target)))
        return f"receipt-{len(self.calls)}"


class ClaimGateEngine(Engine):
    """Pause after a durable claim so its authorization can change."""

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


def expiry_events(engine):
    return [
        event for event in engine.snapshot()["outbox"].values() if event["key"] == "pantry_expiry"
    ]


def enabled(engine, store, *, channels=True):
    state = engine.snapshot()
    state["settings"].update(
        pantry_expiry_reminders=True,
        pantry_expiry_days=3,
        timezone="UTC",
    )
    state["settings"]["modules"] = sorted({*state["settings"]["modules"], "pantry"})
    if channels:
        state["members"]["owner"].update(telegram_id=1001, language="ru")
        state["members"]["parent"].update(telegram_id=1002, language="uk")
        state["members"]["adult"]["telegram_id"] = 1003
        state["members"]["child"]["telegram_id"] = 1004
        state["telegram"]["group_id"] = -1000
    return Engine(state, store.save)


async def add_item(engine, at, *, expires_on="2026-09-08"):
    return await engine.execute(
        "parent",
        "pantry.item_save",
        {
            "name": "Synthetic milk",
            "unit": "l",
            "quantity": 1,
            "minimum_quantity": 0,
            "expires_on": expires_on,
            "note": "PARENT PRIVATE NOTE",
            "location": "PARENT PRIVATE LOCATION",
        },
        "add-expiring-item",
        at,
    )


@pytest.mark.asyncio
async def test_private_parent_fanout_and_restart_are_exactly_once(engine, store):
    at = datetime(2026, 9, 6, 9, tzinfo=UTC)
    engine = enabled(engine, store)
    item = await add_item(engine, at)
    assert await engine.tick(at)

    [event] = expiry_events(engine)
    assert event["recipient"] == "parents"
    assert event["data"] == {
        "id": item["id"],
        "source_revision": item["revision"],
        "name": "Synthetic milk",
        "expires_on": "2026-09-08",
    }
    resolved = targets(event, engine.snapshot())
    assert {(target["id"], target["language"]) for target in resolved} == {
        (1001, "ru"),
        (1002, "uk"),
    }
    assert all(target["id"] not in {1003, 1004, -1000} for target in resolved)

    transport = Transport()
    assert await Notifications(engine, targets, transport.send).run(at) == 2
    assert expiry_events(engine)[0]["state"] == "sent"
    assert len(transport.calls) == 2

    restarted = Engine(store.value, store.save)
    assert not await restarted.tick(at + timedelta(hours=1))
    assert await Notifications(restarted, targets, transport.send).run(at) == 0
    assert len(transport.calls) == 2
    assert len(expiry_events(restarted)) == 1


@pytest.mark.parametrize(
    ("language", "phrases"),
    [
        ("en", ("recorded expiry date", "Check it manually", "stock was not changed")),
        ("ru", ("записан срок годности", "Проверьте вручную", "остаток не изменён")),
        ("uk", ("записано термін придатності", "Перевірте вручну", "залишок не змінено")),
    ],
)
def test_messages_are_factual_localized_and_contain_no_private_metadata(
    engine, store, language, phrases
):
    state = enabled(engine, store).snapshot()
    item = {
        "id": "I000001",
        "revision": 1,
        "name": "Synthetic milk",
        "unit": "l",
        "quantity": 1,
        "minimum_quantity": 0,
        "expires_on": "2026-09-08",
        "note": "PARENT PRIVATE NOTE",
        "location": "PARENT PRIVATE LOCATION",
        "history": [{"reason": "PARENT PRIVATE HISTORY"}],
        "status": "active",
    }
    state["pantry"] = {"items": {item["id"]: item}}
    event = {
        "key": "pantry_expiry",
        "recipient": "parents",
        "data": {
            "id": item["id"],
            "source_revision": 1,
            "name": item["name"],
            "expires_on": item["expires_on"],
        },
    }
    message = render(event, {"id": 123, "language": language}, state)
    assert all(phrase in message["text"] for phrase in phrases)
    assert "Synthetic milk" in message["text"]
    assert "2026-09-08" in message["text"]
    assert "PARENT PRIVATE" not in message["text"]
    assert "quantity" not in message["text"].lower()
    assert message["link_preview_options"] == {"is_disabled": True}


@pytest.mark.asyncio
async def test_nonurgent_reminder_waits_for_quiet_hours(engine, store):
    at = datetime(2026, 9, 6, 9, tzinfo=UTC)
    engine = enabled(engine, store)
    state = engine.snapshot()
    state["settings"]["notifications"] = {
        "quiet_enabled": True,
        "quiet_start": "08:00",
        "quiet_end": "10:00",
        "timezone": "UTC",
    }
    engine = Engine(state, store.save)
    await add_item(engine, at)
    await engine.tick(at)
    transport = Transport()
    worker = Notifications(engine, targets, transport.send)

    assert await worker.run(at) == 0
    assert expiry_events(engine)[0]["state"] == "pending"
    assert await worker.run(at.replace(hour=10)) == 2
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_no_channel_waits_then_local_expiry_cutoff_supersedes(engine, store):
    at = datetime(2026, 9, 6, 9, tzinfo=UTC)
    engine = enabled(engine, store)
    await add_item(engine, at, expires_on="2026-09-06")
    await engine.tick(at)

    def deactivate_parents(ctx):
        ctx.state["members"]["owner"]["active"] = False
        ctx.state["members"]["parent"]["active"] = False

    await engine.system_update("synthetic_no_active_parent", at, deactivate_parents)
    transport = Transport()
    worker = Notifications(engine, targets, transport.send)

    assert await worker.run(at) == 0
    assert expiry_events(engine)[0]["state"] == "awaiting_channel"
    assert await worker.run(at + timedelta(days=1)) == 0
    assert expiry_events(engine)[0]["state"] == "superseded"
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation", ["revision", "archive", "quantity", "expiry", "policy", "module"]
)
async def test_obsolete_unsent_event_is_superseded_before_delivery(engine, store, revocation):
    at = datetime(2026, 9, 6, 9, tzinfo=UTC)
    engine = enabled(engine, store)
    item = await add_item(engine, at)
    await engine.tick(at)

    def revoke(ctx):
        current = ctx.state["pantry"]["items"][item["id"]]
        if revocation == "revision":
            current["revision"] += 1
        elif revocation == "archive":
            current["status"] = "archived"
        elif revocation == "quantity":
            current["quantity"] = 0
        elif revocation == "expiry":
            current["expires_on"] = None
        elif revocation == "policy":
            ctx.state["settings"]["pantry_expiry_reminders"] = False
        else:
            ctx.state["settings"]["modules"].remove("pantry")

    await engine.system_update(f"synthetic_{revocation}", at, revoke)
    transport = Transport()
    assert await Notifications(engine, targets, transport.send).run(at) == 0
    assert expiry_events(engine)[0]["state"] == "superseded"
    assert transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["source", "role"])
async def test_claim_is_reauthorized_against_current_source_and_recipient(
    engine, store, revocation
):
    at = datetime(2026, 9, 6, 9, tzinfo=UTC)
    engine = enabled(engine, store)
    state = engine.snapshot()
    state["members"]["owner"].pop("telegram_id", None)
    engine = Engine(state, store.save)
    item = await add_item(engine, at)
    await engine.tick(at)
    gated = ClaimGateEngine(engine.snapshot(), store.save)
    transport = Transport()
    worker = asyncio.create_task(Notifications(gated, targets, transport.send).run(at))

    try:
        await asyncio.wait_for(gated.claimed.wait(), timeout=2)

        def revoke(ctx):
            if revocation == "source":
                ctx.state["pantry"]["items"][item["id"]]["revision"] += 1
            else:
                ctx.state["members"]["parent"]["role"] = "adult"

        await gated.system_update(f"synthetic_{revocation}", at, revoke)
    finally:
        gated.release.set()

    assert await asyncio.wait_for(worker, timeout=2) == 0
    assert transport.calls == []
    [event] = expiry_events(gated)
    assert event["state"] == "superseded"
    assert next(iter(event["deliveries"].values()))["state"] == "superseded"


@pytest.mark.asyncio
async def test_failed_claim_never_sends_and_restart_retries(engine, store):
    at = datetime(2026, 9, 6, 9, tzinfo=UTC)
    engine = enabled(engine, store)
    await add_item(engine, at)
    await engine.tick(at)
    transport = Transport()
    store.fail = True
    with pytest.raises(OSError):
        await Notifications(engine, targets, transport.send).run(at)
    assert transport.calls == []

    store.fail = False
    restarted = Engine(store.value, store.save)
    assert await Notifications(restarted, targets, transport.send).run(at) == 2
    assert len(transport.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("state_name", ["sending", "sent", "uncertain"])
async def test_obsolete_adapter_does_not_recall_inflight_or_terminal_delivery(
    engine, store, state_name
):
    at = datetime(2026, 9, 6, 9, tzinfo=UTC)
    engine = enabled(engine, store)
    item = await add_item(engine, at)
    await engine.tick(at)

    def mark(ctx):
        event = expiry_events_from_state(ctx.state)[0]
        event["deliveries"] = {
            "synthetic": {
                "id": "synthetic",
                "target": {"channel": "telegram", "id": 1001, "language": "ru"},
                "state": state_name,
                "attempts": 1,
            }
        }
        if state_name == "sending":
            event["deliveries"]["synthetic"]["lease_until"] = (
                at + timedelta(minutes=1)
            ).isoformat()
        event["state"] = state_name
        ctx.state["pantry"]["items"][item["id"]]["revision"] += 1

    await engine.system_update(f"synthetic_{state_name}", at, mark)
    transport = Transport()
    assert await Notifications(engine, targets, transport.send).run(at) == 0
    assert expiry_events(engine)[0]["state"] == state_name
    assert transport.calls == []


def expiry_events_from_state(state):
    return [event for event in state["outbox"].values() if event["key"] == "pantry_expiry"]
