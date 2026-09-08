"""Durable private reminder holds, ordinary urgent traffic, and pre-send races."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_notifications import Transport
from test_presence_delivery import enabled, payload

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.notifications import Notifications
from custom_components.family_assistant.telegram.messages import targets


async def setup(engine, store, now, *, count=1, dashboard_only=False):
    e, _, action, actor, _ = await enabled(engine, store, now)
    state = e.snapshot()
    state["members"]["child"]["telegram_id"] = 101
    if dashboard_only:
        state["presence"]["delivery_preferences"] = {}
    e = Engine(state, store.save)
    for number in range(count):
        await e.execute(
            "owner",
            "tasks.create",
            {"title": f"Synthetic task {number}", "assignee": "child"},
            f"task-{number}",
            now,
        )
    transport = Transport()
    observations = {"home": False, "calls": 0, "prepare": 0}

    async def prepare(_state):
        observations["prepare"] += 1

        def observe(_current, member, policy, at):
            observations["calls"] += 1
            assert member["id"] == "child" and policy["status"] == "enabled"
            return observations["home"]

        return observe

    return (
        e,
        Notifications(e, targets, transport.send, presence_prepare=prepare),
        transport,
        observations,
        action,
        actor,
    )


@pytest.mark.asyncio
async def test_away_unknown_defer_without_send_attempt_and_return_once_after_store_reload(
    engine, store, now
):
    e, worker, transport, readings, _, _ = await setup(engine, store, now)
    assert await worker.run(now) == 0 and not transport.calls
    event = next(iter(e.snapshot()["outbox"].values()))
    delivery = next(iter(event["deliveries"].values()))
    assert event["state"] == delivery["state"] == "pending"
    assert event["attempts"] == delivery["attempts"] == 0
    assert "presence_started_at" in delivery and "presence_deadline" in delivery
    assert not any(
        key in repr(e.snapshot()["presence"])
        for key in ("observed_at", "reported_home", "reported_away")
    )
    calls = readings["calls"]
    assert await worker.run(now + timedelta(seconds=20)) == 0 and readings["calls"] == calls
    restored = Engine(deepcopy(store.value), store.save)
    readings["home"] = True
    restarted = Notifications(
        restored, targets, transport.send, presence_prepare=worker.presence_prepare
    )
    assert await restarted.run(now + timedelta(minutes=1)) == 1
    assert await restarted.run(now + timedelta(minutes=2)) == 0
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_return_queue_drains_slowly_but_alarm_closure_does_not_wait(engine, store, now):
    e, worker, transport, readings, _, _ = await setup(engine, store, now, count=3)
    assert await worker.run(now, 20) == 0
    readings["home"] = True
    assert await worker.run(now + timedelta(minutes=1), 20) == 1

    def closure(ctx):
        ctx.notify("child", "alarm_closed", {"member": "child", "stage": "awake"})

    await e.system_update("synthetic-closure", now + timedelta(minutes=1), closure)
    assert await worker.run(now + timedelta(minutes=1, seconds=2), 20) == 1
    assert len(transport.calls) == 2
    assert await worker.run(now + timedelta(minutes=3), 20) == 1
    assert await worker.run(now + timedelta(minutes=5), 20) == 1
    assert await worker.run(now + timedelta(minutes=7), 20) == 0


@pytest.mark.asyncio
async def test_wait_expiry_is_terminal_and_never_sends_stale_content_on_later_return(
    engine, store, now
):
    e, worker, transport, readings, action, actor = await setup(engine, store, now)
    await e.execute(
        actor, action, payload(preference_revision=1, max_wait_minutes=15), "short-wait", now
    )
    assert await worker.run(now) == 0
    readings["home"] = True
    assert await worker.run(now + timedelta(minutes=15)) == 0
    event = next(iter(e.snapshot()["outbox"].values()))
    delivery = next(iter(event["deliveries"].values()))
    assert delivery["state"] == event["state"] == "superseded"
    assert delivery["error"] == "presence_wait_expired"
    assert await worker.run(now + timedelta(days=1)) == 0 and not transport.calls


@pytest.mark.asyncio
async def test_opt_out_releases_hold_without_further_observation(engine, store, now):
    e, worker, transport, readings, action, actor = await setup(engine, store, now)
    await worker.run(now)
    await e.execute(actor, action, payload(preference_revision=1, enabled=False), "withdraw", now)
    calls = readings["calls"]
    assert await worker.run(now + timedelta(seconds=1)) == 1
    assert readings["calls"] == calls and len(transport.calls) == 1


@pytest.mark.asyncio
async def test_no_policy_never_reads_presence_and_missing_adapter_with_policy_never_assumes_home(
    engine, store, now
):
    e, worker, transport, readings, _, _ = await setup(engine, store, now, dashboard_only=True)
    assert await worker.run(now) == 1 and readings["prepare"] == readings["calls"] == 0
    other, _, other_transport, _, _, _ = await setup(engine, store, now)
    assert await Notifications(other, targets, other_transport.send).run(now) == 0
    assert not other_transport.calls


@pytest.mark.asyncio
async def test_home_to_away_between_claim_and_dispatch_returns_pending_not_uncertain(
    engine, store, now
):
    e, worker, transport, readings, _, _ = await setup(engine, store, now)
    readings["home"] = True
    normal_prepare = worker.presence_prepare

    async def changing_prepare(state):
        result = await normal_prepare(state)
        if readings["prepare"] >= 2:
            readings["home"] = False
        return result

    worker.presence_prepare = changing_prepare
    assert await worker.run(now) == 0 and not transport.calls
    event = next(iter(e.snapshot()["outbox"].values()))
    assert event["state"] == "pending"
    assert all(delivery["state"] == "pending" for delivery in event["deliveries"].values())


@pytest.mark.asyncio
async def test_failed_hold_persistence_does_not_send_or_keep_partial_state(engine, store, now):
    e, worker, transport, _, _, _ = await setup(engine, store, now)
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await worker.run(now)
    assert e.snapshot() == before and not transport.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["member_epoch", "member_link", "ambiguous", "stamp_boolean"])
async def test_held_delivery_never_changes_its_recipient(engine, store, now, change):
    e, worker, transport, readings, _, _ = await setup(engine, store, now)
    assert await worker.run(now) == 0
    state = e.snapshot()
    if change == "member_epoch":
        state["members"]["child"]["revision"] += 1
    elif change == "member_link":
        state["members"]["child"]["telegram_id"] = 102
    elif change == "ambiguous":
        state["members"]["sibling"]["telegram_id"] = 101
    else:
        event = next(iter(state["outbox"].values()))
        next(iter(event["deliveries"].values()))["presence_recipient"]["member_revision"] = True
    restored = Engine(state, store.save)
    readings["home"] = True
    worker = Notifications(
        restored, targets, transport.send, presence_prepare=worker.presence_prepare
    )
    assert await worker.run(now + timedelta(minutes=1)) == 0 and not transport.calls
    assert next(iter(restored.snapshot()["outbox"].values()))["state"] == "superseded"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", ["alarm_closed", "alarm_missed", "alarm_device_error", "plain_reply"]
)
async def test_ungated_lane_never_prepares_or_reads_presence(engine, store, now, key):
    e, worker, transport, readings, _, _ = await setup(engine, store, now)
    state = e.snapshot()
    state["outbox"] = {}
    e = Engine(state, store.save)
    await e.system_update("synthetic-notice", now, lambda ctx: ctx.notify("child", key, {}))
    worker = Notifications(e, targets, transport.send, presence_prepare=worker.presence_prepare)
    assert await worker.run(now) == 1 and len(transport.calls) == 1
    assert readings["prepare"] == readings["calls"] == 0


@pytest.mark.asyncio
async def test_shortening_wait_does_not_extend_an_existing_deadline(engine, store, now):
    e, worker, transport, readings, action, actor = await setup(engine, store, now)
    await worker.run(now)
    await e.execute(
        actor, action, payload(preference_revision=1, max_wait_minutes=15), "shorten", now
    )
    assert await worker.run(now + timedelta(minutes=1)) == 0
    state = e.snapshot()
    deadline = next(iter(next(iter(state["outbox"].values()))["deliveries"].values()))[
        "presence_deadline"
    ]
    assert deadline == (now + timedelta(minutes=15)).isoformat()
    await e.execute(
        actor, action, payload(preference_revision=2, max_wait_minutes=1440), "lengthen", now
    )
    readings["home"] = True
    assert await worker.run(now + timedelta(minutes=15)) == 0 and not transport.calls


@pytest.mark.asyncio
async def test_revocation_during_dispatch_store_write_is_rechecked_before_send(engine, store, now):
    e, worker, transport, readings, _, _ = await setup(engine, store, now)
    await worker.run(now)
    readings["home"] = True
    state = e.snapshot()

    async def save_and_revoke(value):
        await store.save(value)
        # Catch-up permission was allowed before the Store await, revoked while
        # its rate reservation was being committed. Third preparation must see it.
        if value["presence"].get("delivery_rates"):
            readings["home"] = False

    restored = Engine(state, save_and_revoke)
    worker = Notifications(
        restored, targets, transport.send, presence_prepare=worker.presence_prepare
    )
    assert await worker.run(now + timedelta(minutes=1)) == 0 and not transport.calls
    event = next(iter(restored.snapshot()["outbox"].values()))
    assert event["state"] == "pending"
    assert all(item["state"] == "pending" for item in event["deliveries"].values())


@pytest.mark.asyncio
async def test_withdrawal_after_downtime_does_not_revive_an_expired_hold(engine, store, now):
    e, worker, transport, readings, action, actor = await setup(engine, store, now)
    await e.execute(actor, action, payload(preference_revision=1, max_wait_minutes=15), "cap", now)
    await worker.run(now)
    await e.execute(
        actor, action, payload(preference_revision=2, enabled=False), "withdraw-late", now
    )
    calls = readings["calls"]
    assert await worker.run(now + timedelta(minutes=16)) == 0
    assert readings["calls"] == calls and not transport.calls
    assert next(iter(e.snapshot()["outbox"].values()))["state"] == "superseded"
