"""Background effects wait through backup freezes without repeating external I/O."""

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import Notifications


def _targets(event, state):
    member = state["members"].get(event["recipient"], {})
    if not member.get("active") or not member.get("telegram_id"):
        return []
    return [
        {
            "channel": "telegram",
            "id": member["telegram_id"],
            "language": member.get("language", "en"),
        }
    ]


def _only_event(state):
    events = list(state["outbox"].values())
    assert len(events) == 1
    return events[0]


async def _task_notification(engine, store, now):
    state = engine.snapshot()
    state["members"]["child"]["telegram_id"] = 1002
    current = Engine(state, store.save)
    await current.execute(
        "owner",
        "tasks.create",
        {"title": "Pack school bag", "assignee": "child"},
        "create-background-backup-task",
        now,
    )
    return current


class ClaimGateEngine(Engine):
    """Pause after the durable claim and before final dispatch authorization."""

    def __init__(self, state, persist):
        super().__init__(state, persist)
        self.claimed = asyncio.Event()
        self.release_claim = asyncio.Event()

    async def background_update(self, kind, now, change):
        result = await super().background_update(kind, now, change)
        if kind == "outbox_claim" and result is not None:
            self.claimed.set()
            await self.release_claim.wait()
        return result


@pytest.mark.asyncio
async def test_sent_receipt_waits_for_thaw_without_repeating_transport(engine, store, now):
    current = await _task_notification(engine, store, now)
    sent = []
    transport_returned = asyncio.Event()
    backup_token = None

    async def send(event, target):
        nonlocal backup_token
        sent.append((event["id"], deepcopy(target)))
        backup_token = await current.async_begin_backup()
        transport_returned.set()
        return "telegram-receipt-1"

    worker = asyncio.create_task(Notifications(current, _targets, send).run(now))
    await asyncio.wait_for(transport_returned.wait(), timeout=2)
    await asyncio.sleep(0)

    assert not worker.done()
    assert len(sent) == 1
    frozen = current.snapshot()
    event = _only_event(frozen)
    delivery = next(iter(event["deliveries"].values()))
    assert event["state"] == "sending"
    assert delivery["state"] == "sending"
    assert "receipt" not in delivery
    persisted_frozen = deepcopy(store.value)

    competing = asyncio.create_task(Notifications(current, _targets, send).run(now))
    await asyncio.sleep(0)
    assert not competing.done()
    assert store.value == persisted_frozen
    assert len(sent) == 1

    await current.async_end_backup(backup_token)
    assert await asyncio.wait_for(worker, timeout=2) == 1
    assert await asyncio.wait_for(competing, timeout=2) == 0

    finished = current.snapshot()
    event = _only_event(finished)
    delivery = next(iter(event["deliveries"].values()))
    assert event["state"] == "sent"
    assert delivery["state"] == "sent"
    assert delivery["receipt"] == "telegram-receipt-1"
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_cancelling_receipt_wait_does_not_thaw_or_resend(engine, store, now):
    current = await _task_notification(engine, store, now)
    sent = []
    transport_returned = asyncio.Event()
    backup_token = None

    async def send(event, target):
        nonlocal backup_token
        sent.append((event["id"], deepcopy(target)))
        backup_token = await current.async_begin_backup()
        transport_returned.set()
        return "receipt-lost-with-worker"

    worker = asyncio.create_task(Notifications(current, _targets, send).run(now))
    await asyncio.wait_for(transport_returned.wait(), timeout=2)
    await asyncio.sleep(0)
    persisted_frozen = deepcopy(store.value)

    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker

    assert current.snapshot() == persisted_frozen
    assert store.value == persisted_frozen
    with pytest.raises(DomainError, match="backup_in_progress"):
        await current.system_update("probe_backup_lease", now, lambda _ctx: None)

    await current.async_end_backup(backup_token)
    restarted_worker = Notifications(current, _targets, send)
    assert await restarted_worker.run(now + timedelta(seconds=20)) == 0
    event = _only_event(current.snapshot())
    delivery = next(iter(event["deliveries"].values()))
    assert event["state"] == "sending"
    assert delivery["state"] == "sending"
    assert len(sent) == 1

    assert await restarted_worker.run(now + timedelta(seconds=31)) == 0
    event = _only_event(current.snapshot())
    delivery = next(iter(event["deliveries"].values()))
    assert event["state"] == "uncertain"
    assert delivery["state"] == "uncertain"
    assert delivery["error"] == "delivery_uncertain"
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_dispatch_reauthorizes_recipient_after_backup_thaw(engine, store, now):
    seeded = await _task_notification(engine, store, now)
    current = ClaimGateEngine(seeded.snapshot(), store.save)
    sent = []

    async def send(event, target):
        sent.append((deepcopy(event), deepcopy(target)))
        return "unexpected"

    worker = asyncio.create_task(Notifications(current, _targets, send).run(now))
    await asyncio.wait_for(current.claimed.wait(), timeout=2)
    backup_token = await current.async_begin_backup()
    assert sent == []

    await current.async_end_backup(backup_token)

    def relink(ctx):
        ctx.state["members"]["child"]["telegram_id"] = 2002

    await current.system_update("relink_after_backup", now, relink)
    current.release_claim.set()

    assert await asyncio.wait_for(worker, timeout=2) == 0
    assert sent == []
    event = _only_event(current.snapshot())
    assert event["state"] == "superseded"
    assert {item["state"] for item in event["deliveries"].values()} == {"superseded"}


@pytest.mark.asyncio
async def test_cancelled_background_update_never_runs_or_releases_backup(engine, store, now):
    current = await _task_notification(engine, store, now)
    backup_token = await current.async_begin_backup()
    before = current.snapshot()
    persisted_before = deepcopy(store.value)
    called = []

    def change(ctx):
        called.append(True)
        ctx.state["settings"]["name"] = "Must not be stored"

    waiting = asyncio.create_task(current.background_update("cancelled_update", now, change))
    await asyncio.sleep(0)
    assert not waiting.done()
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert called == []
    assert current.snapshot() == before
    assert store.value == persisted_before
    with pytest.raises(DomainError, match="backup_in_progress"):
        await current.system_update("still_frozen", now, lambda _ctx: None)

    await current.async_end_backup(backup_token)
    assert current.snapshot() == before
