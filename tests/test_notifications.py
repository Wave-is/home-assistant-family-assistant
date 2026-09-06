"""Outbox state and transport faults, without contacting any external service."""

from datetime import UTC, datetime, timedelta

import pytest
from test_alarms import schedule

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.notifications import (
    DeliveryError,
    Notifications,
    quiet_until,
)


class Transport:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.after_send = None

    async def send(self, event, target):
        self.calls.append((event["id"], target["id"]))
        if self.failure:
            raise self.failure
        if self.after_send:
            await self.after_send()
        return str(len(self.calls))


def resolve(event, state):
    return [{"channel": "synthetic", "id": "synthetic-parent", "language": "en"}]


async def pending(engine, now):
    await engine.execute(
        "owner", "tasks.create", {"title": "Pack bag", "assignee": "child"}, "create", now
    )


@pytest.mark.asyncio
async def test_send_once_after_receipt_and_restart(engine, store, now):
    await pending(engine, now)
    transport = Transport()
    assert await Notifications(engine, resolve, transport.send).run(now) == 1
    engine = Engine(store.value, store.save)
    assert await Notifications(engine, resolve, transport.send).run(now) == 0
    assert len(transport.calls) == 1
    assert next(iter(engine.snapshot()["outbox"].values()))["state"] == "sent"


@pytest.mark.asyncio
async def test_failure_before_send_retries_with_backoff_limit(engine, now):
    await pending(engine, now)
    transport = Transport()
    transport.failure = DeliveryError("connection_failed", retryable=True)
    worker = Notifications(engine, resolve, transport.send)
    assert await worker.run(now) == 1
    assert await worker.run(now + timedelta(seconds=1)) == 0
    for minute in range(1, 10):
        await worker.run(now + timedelta(minutes=minute))
    assert len(transport.calls) == 5
    assert next(iter(engine.snapshot()["outbox"].values()))["state"] == "failed"


@pytest.mark.asyncio
async def test_ambiguous_timeout_does_not_blindly_resend(engine, now):
    await pending(engine, now)
    transport = Transport()
    transport.failure = TimeoutError()
    worker = Notifications(engine, resolve, transport.send)
    await worker.run(now)
    await worker.run(now + timedelta(hours=1))
    assert len(transport.calls) == 1
    assert next(iter(engine.snapshot()["outbox"].values()))["state"] == "uncertain"


@pytest.mark.asyncio
async def test_crash_after_send_before_receipt_is_uncertain_on_restart(engine, store, now):
    await pending(engine, now)
    transport = Transport()

    async def fail_store():
        store.fail = True

    transport.after_send = fail_store
    with pytest.raises(OSError):
        await Notifications(engine, resolve, transport.send).run(now)
    store.fail = False
    engine = Engine(store.value, store.save)
    worker = Notifications(engine, resolve, transport.send)
    assert await worker.run(now + timedelta(seconds=31)) == 0
    assert len(transport.calls) == 1
    assert next(iter(engine.snapshot()["outbox"].values()))["state"] == "uncertain"


@pytest.mark.asyncio
async def test_failed_claim_save_never_sends(engine, store, now):
    await pending(engine, now)
    store.fail = True
    transport = Transport()
    with pytest.raises(OSError):
        await Notifications(engine, resolve, transport.send).run(now)
    assert transport.calls == []


@pytest.mark.asyncio
async def test_partial_fanout_does_not_resend_successful_recipient(engine, now):
    await pending(engine, now)
    transport = Transport()

    async def send(event, target):
        if target["id"] == "second":
            raise DeliveryError("blocked")
        return await transport.send(event, target)

    def targets(event, state):
        return resolve(event, state) + [{"channel": "synthetic", "id": "second"}]

    worker = Notifications(engine, targets, send)
    await worker.run(now)
    await worker.run(now + timedelta(minutes=5))
    assert len(transport.calls) == 1
    assert next(iter(engine.snapshot()["outbox"].values()))["state"] == "failed"


@pytest.mark.asyncio
async def test_waits_for_channel_and_suppresses_expired_challenge(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    transport = Transport()
    worker = Notifications(engine, lambda *_: [], transport.send)
    assert await worker.run(now) == 0
    assert next(iter(engine.snapshot()["outbox"].values()))["state"] == "awaiting_channel"
    worker.resolve = resolve
    assert await worker.run(now + timedelta(minutes=5)) == 0
    assert not transport.calls


def test_quiet_hours_overnight_and_daytime():
    policy = {
        "quiet_enabled": True,
        "quiet_start": "22:00",
        "quiet_end": "08:00",
        "timezone": "UTC",
    }
    assert quiet_until(datetime(2026, 9, 6, 23, tzinfo=UTC), policy) == datetime(
        2026, 9, 7, 8, tzinfo=UTC
    )
    assert quiet_until(datetime(2026, 9, 6, 7, tzinfo=UTC), policy) == datetime(
        2026, 9, 6, 8, tzinfo=UTC
    )
    assert quiet_until(datetime(2026, 9, 6, 8, tzinfo=UTC), policy) is None


@pytest.mark.asyncio
async def test_quiet_hours_do_not_silence_wake_up_challenges(engine, store, now):
    state = engine.snapshot()
    state["settings"]["notifications"] = {
        "quiet_enabled": True,
        "quiet_start": "07:00",
        "quiet_end": "10:00",
        "timezone": "UTC",
    }
    engine = Engine(state, store.save)
    await pending(engine, now)
    await schedule(engine, now)
    await engine.tick(now)
    transport = Transport()
    worker = Notifications(engine, resolve, transport.send)
    await worker.run(now)
    assert len(transport.calls) == 1
    events = engine.snapshot()["outbox"]
    assert events[transport.calls[0][0]]["key"] == "alarm_challenge"


@pytest.mark.asyncio
async def test_manual_retry_requires_parent_confirmation_and_audit(engine, now):
    await pending(engine, now)
    transport = Transport()
    transport.failure = TimeoutError()
    worker = Notifications(engine, resolve, transport.send)
    await worker.run(now)
    event_id = next(iter(engine.snapshot()["outbox"]))
    from custom_components.family_assistant.domain.validation import DomainError

    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child",
            "notifications.retry",
            {"id": event_id, "reason": "Check", "confirmed": True},
            "child-retry",
            now,
        )
    with pytest.raises(DomainError, match="retry_confirmation_required"):
        await engine.execute(
            "parent",
            "notifications.retry",
            {"id": event_id, "reason": "Check"},
            "retry-no-confirm",
            now,
        )
    await engine.execute(
        "parent",
        "notifications.retry",
        {"id": event_id, "reason": "Not received", "confirmed": True},
        "retry",
        now,
    )
    transport.failure = None
    await worker.run(now + timedelta(seconds=2))
    assert len(transport.calls) == 2
    event = engine.snapshot()["outbox"][event_id]
    assert event["state"] == "sent"
    assert len(next(iter(event["deliveries"].values()))["retry_history"]) == 1
