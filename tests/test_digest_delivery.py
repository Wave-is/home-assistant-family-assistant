"""Durable, private delivery boundary tests for family digests."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.notifications import Notifications
from custom_components.family_assistant.telegram.messages import render, targets

NOW = datetime(2026, 9, 7, 7, 2, tzinfo=UTC)


class Store:
    def __init__(self):
        self.calls = 0
        self.value = None
        self.fail_calls = set()

    async def save(self, state):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise OSError("synthetic store failure")
        self.value = deepcopy(state)


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


class RenderingTransport:
    def __init__(self, engine, clock):
        self.engine = engine
        self.clock = clock
        self.calls = []

    async def send(self, event, target):
        message = render(event, target, self.engine.snapshot(), now=self.clock())
        self.calls.append((deepcopy(event), deepcopy(target), message))
        return f"message-{len(self.calls)}"


class ClaimGateEngine(Engine):
    """Pause after claim persistence but before final dispatch authorization."""

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


def initial_state(*, title="Original current title"):
    state = new_state(
        "synthetic-owner",
        "Digest household",
        modules=["tasks", "digests"],
        timezone="UTC",
    )
    state["settings"].update(
        language="en",
        digest_policy_revision=1,
        digest_morning_enabled=True,
        digest_morning_time="07:00",
        digest_evening_enabled=False,
        digest_evening_time="19:00",
        digest_weekly_enabled=False,
        digest_weekly_weekday=6,
        digest_weekly_time="18:00",
    )
    state["members"]["owner"].update(
        name="Current Owner",
        language="en",
        telegram_id=987654321,
    )
    state["telegram"]["group_id"] = -100999888777
    state["tasks"]["T000001"] = {
        "id": "T000001",
        "revision": 1,
        "title": title,
        "assignee": "owner",
        "assignee_revision": 1,
        "creator": "owner",
        "created_at": (NOW - timedelta(days=1)).isoformat(),
        "due_at": (NOW + timedelta(hours=3)).isoformat(),
        "status": "assigned",
        "report_type": "text",
        "report": None,
        "deadline_policy": {"reminder_minutes": 0, "grace_minutes": 30, "penalty": 0},
        "checklist": [],
    }
    return state


async def seeded(store=None):
    store = store or Store()
    engine = Engine(initial_state(), store.save)
    await engine.execute(
        "owner",
        "digests.access_set",
        {
            "recipient_revision": 1,
            "subscription_revision": None,
            "morning": True,
            "evening": False,
            "weekly": False,
        },
        "digest-consent",
        NOW - timedelta(minutes=1),
    )
    assert await engine.tick(NOW)
    events = [
        event for event in engine.snapshot()["outbox"].values() if event["key"] == "family_digest"
    ]
    assert len(events) == 1
    return engine, store, events[0]


@pytest.mark.asyncio
async def test_real_target_and_render_use_fresh_state_not_persisted_content():
    engine, _store, event = await seeded()
    descriptor = repr(event["data"])
    for canary in (
        "Original current title",
        "Current Owner",
        "987654321",
        "-100999888777",
        "synthetic-owner",
    ):
        assert canary not in descriptor
    assert targets(event, engine.snapshot()) == [
        {"channel": "telegram", "id": 987654321, "language": "en"}
    ]

    await engine.system_update(
        "fresh-digest-content",
        NOW,
        lambda ctx: ctx.state["tasks"]["T000001"].update(title="Fresh send-time title"),
    )
    clock = Clock()
    transport = RenderingTransport(engine, clock)
    assert await Notifications(engine, targets, transport.send, clock=clock).run(NOW) == 1
    assert len(transport.calls) == 1
    _sent_event, target, message = transport.calls[0]
    assert target == {"channel": "telegram", "id": 987654321, "language": "en"}
    assert message["chat_id"] == 987654321
    assert "Fresh send-time title" in message["text"]
    assert "Original current title" not in message["text"]
    assert message["link_preview_options"] == {"is_disabled": True}
    assert "parse_mode" not in message
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "sent"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["module", "policy_aba", "member", "subscription"])
async def test_claim_rejects_revoked_scope_before_any_transport(change):
    engine, _store, event = await seeded()

    def revoke(ctx):
        if change == "module":
            ctx.state["settings"]["modules"].remove("digests")
            ctx.state["settings"]["digest_policy_revision"] += 1
        elif change == "policy_aba":
            ctx.state["settings"]["digest_policy_revision"] += 2
        elif change == "member":
            ctx.state["members"]["owner"]["revision"] += 1
        else:
            ctx.state["digest_subscriptions"]["owner"].update(morning=False, revision=2)

    await engine.system_update(f"revoke-{change}", NOW, revoke)
    transport = RenderingTransport(engine, Clock())
    assert await Notifications(engine, targets, transport.send).run(NOW) == 0
    assert transport.calls == []
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "superseded"


@pytest.mark.asyncio
async def test_missing_binding_has_no_family_fallback_or_send():
    engine, _store, event = await seeded()
    await engine.system_update(
        "remove-private-binding",
        NOW,
        lambda ctx: ctx.state["members"]["owner"].pop("telegram_id"),
    )
    state = engine.snapshot()
    assert targets(event, state) == []
    transport = RenderingTransport(engine, Clock())
    assert await Notifications(engine, targets, transport.send).run(NOW) == 0
    assert transport.calls == []
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "awaiting_channel"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["module", "policy_aba", "member", "subscription", "binding", "content"]
)
async def test_final_dispatch_rechecks_scope_after_durable_claim(change):
    original, store, event = await seeded()
    engine = ClaimGateEngine(original.snapshot(), store.save)
    clock = Clock()
    transport = RenderingTransport(engine, clock)
    running = asyncio.create_task(
        Notifications(engine, targets, transport.send, clock=clock).run(NOW)
    )
    await asyncio.wait_for(engine.claimed.wait(), timeout=2)

    def revoke(ctx):
        if change == "module":
            ctx.state["settings"]["modules"].remove("digests")
            ctx.state["settings"]["digest_policy_revision"] += 1
        elif change == "policy_aba":
            ctx.state["settings"]["digest_policy_revision"] += 2
        elif change == "member":
            ctx.state["members"]["owner"]["revision"] += 1
        elif change == "subscription":
            ctx.state["digest_subscriptions"]["owner"].update(morning=False, revision=2)
        elif change == "binding":
            ctx.state["members"]["owner"]["telegram_id"] = 123456789
        else:
            ctx.state["tasks"].clear()

    await engine.system_update(f"revoke-after-claim-{change}", NOW, revoke)
    engine.release.set()
    assert await asyncio.wait_for(running, timeout=2) == 0
    assert transport.calls == []
    stored = engine.snapshot()["outbox"][event["id"]]
    assert stored["state"] == "superseded"
    assert {delivery["state"] for delivery in stored["deliveries"].values()} == {"superseded"}


@pytest.mark.asyncio
async def test_quiet_hours_defer_but_expiry_supersedes_instead_of_late_send():
    engine, _store, event = await seeded()
    await engine.system_update(
        "digest-quiet-hours",
        NOW,
        lambda ctx: ctx.state["settings"].update(
            notifications={
                "quiet_enabled": True,
                "quiet_start": "06:00",
                "quiet_end": "14:00",
                "timezone": "UTC",
            }
        ),
    )
    clock = Clock()
    transport = RenderingTransport(engine, clock)
    worker = Notifications(engine, targets, transport.send, clock=clock)
    assert await worker.run(NOW) == 0
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "pending"

    clock.now = datetime.fromisoformat(event["data"]["expires_at"])
    assert await worker.run(NOW) == 0
    assert transport.calls == []
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "superseded"


@pytest.mark.asyncio
async def test_backup_wait_uses_fresh_clock_and_does_not_release_stale_digest():
    engine, store, event = await seeded()
    clock = Clock()
    transport = RenderingTransport(engine, clock)
    worker = Notifications(engine, targets, transport.send, clock=clock)
    token = await engine.async_begin_backup()
    calls_before = store.calls
    running = asyncio.create_task(worker.run(NOW))
    await asyncio.sleep(0)
    assert not running.done()
    assert store.calls == calls_before
    assert transport.calls == []

    clock.now = datetime.fromisoformat(event["data"]["expires_at"])
    await engine.async_end_backup(token)
    assert await asyncio.wait_for(running, timeout=2) == 0
    assert transport.calls == []
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "superseded"


@pytest.mark.asyncio
async def test_claim_store_failure_sends_nothing_and_retry_sends_exactly_once():
    store = Store()
    engine, _store, event = await seeded(store)
    store.fail_calls.add(store.calls + 1)
    clock = Clock()
    transport = RenderingTransport(engine, clock)
    worker = Notifications(engine, targets, transport.send, clock=clock)
    with pytest.raises(OSError, match="synthetic store failure"):
        await worker.run(NOW)
    assert transport.calls == []
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "pending"

    assert await worker.run(NOW) == 1
    assert len(transport.calls) == 1
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "sent"


@pytest.mark.asyncio
async def test_finish_store_failure_never_blindly_duplicates_an_inflight_send():
    store = Store()
    engine, _store, event = await seeded(store)
    # Claim persists once; final dispatch is read-only; the following persistence is finish.
    store.fail_calls.add(store.calls + 2)
    clock = Clock()
    transport = RenderingTransport(engine, clock)
    worker = Notifications(engine, targets, transport.send, clock=clock)
    with pytest.raises(OSError, match="synthetic store failure"):
        await worker.run(NOW)
    assert len(transport.calls) == 1
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "sending"

    assert await worker.run(NOW) == 0
    clock.now = NOW + timedelta(seconds=31)
    assert await worker.run(NOW) == 0
    assert len(transport.calls) == 1
    assert engine.snapshot()["outbox"][event["id"]]["state"] == "uncertain"
