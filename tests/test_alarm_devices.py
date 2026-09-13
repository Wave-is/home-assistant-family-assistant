"""A virtual siren verifies renewal, failure, restart and acknowledgement races."""

import asyncio
from datetime import timedelta

import pytest
from test_alarms import answer, current, schedule

from custom_components.family_assistant.alarm_devices import AlarmDevices, AlarmPreparationCancelled
from custom_components.family_assistant.domain.engine import Engine


class VirtualSiren:
    def __init__(self):
        self.state = "off"
        self.calls = []
        self.fail = False
        self.on_send = None

    def read(self, entity):
        return {"state": self.state}

    async def send(self, entity, on, options):
        self.calls.append((entity, on))
        if self.fail:
            raise OSError("Synthetic device timeout")
        self.state = "on" if on else "off"
        if self.on_send:
            callback, self.on_send = self.on_send, None
            await callback()


def driver(engine, siren, confirmed=True):
    return AlarmDevices(
        engine,
        lambda: {
            "child": {"entity_id": "siren.synthetic_alarm", "confirmed": confirmed, "volume": 0.5}
        },
        siren.read,
        siren.send,
    )


@pytest.mark.asyncio
async def test_continuous_renewal_and_immediate_first_answer_stop(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    output = driver(engine, siren)
    for second in (0, 5, 10, 20, 40, 60, 80):
        await output.reconcile(now + timedelta(seconds=second))
    assert len(siren.calls) == 5  # No "ring twice then give up" counter.
    assert all(on for _, on in siren.calls)
    await answer(engine, current(engine), now + timedelta(seconds=81))
    await output.reconcile(now + timedelta(seconds=81))
    assert not siren.calls[-1][1]
    assert siren.state == "off"
    assert not engine.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]["owned"]


@pytest.mark.asyncio
async def test_restart_knows_ownership_and_stops_cancelled_run(engine, store, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    await driver(engine, siren).reconcile(now)
    engine = Engine(store.value, store.save)
    await engine.execute(
        "parent", "alarms.cancel", {"id": current(engine)["id"], "reason": "Checked"}, "cancel", now
    )
    await driver(engine, siren).reconcile(now)
    assert siren.state == "off"


@pytest.mark.asyncio
async def test_inflight_start_cannot_outlive_acknowledgement(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    siren.on_send = lambda: answer(engine, current(engine), now)
    await driver(engine, siren).reconcile(now)
    assert [on for _, on in siren.calls] == [True, False]


@pytest.mark.asyncio
async def test_failed_device_retries_but_does_not_spam(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    siren.fail = True
    output = driver(engine, siren)
    for second in range(0, 61, 5):
        await output.reconcile(now + timedelta(seconds=second))
    assert len(siren.calls) == 5
    errors = [e for e in engine.snapshot()["outbox"].values() if e["key"] == "alarm_device_error"]
    assert len(errors) == 1
    siren.fail = False
    await output.reconcile(now + timedelta(seconds=75))
    await output.close_incidents(now + timedelta(seconds=75))
    await output.close_incidents(now + timedelta(seconds=76))
    closed = [
        e for e in engine.snapshot()["outbox"].values() if e["key"] == "alarm_device_recovered"
    ]
    assert len(closed) == 1


@pytest.mark.asyncio
async def test_does_not_touch_unowned_or_not_opted_in_siren(engine, now):
    siren = VirtualSiren()
    siren.state = "on"
    await driver(engine, siren).reconcile(now, stopping=True)
    assert siren.calls == []
    await schedule(engine, now)
    await engine.tick(now)
    await driver(engine, siren, confirmed=False).reconcile(now)
    assert siren.calls == []


@pytest.mark.asyncio
async def test_failed_intent_save_never_starts_hardware(engine, store, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    store.fail = True
    with pytest.raises(OSError):
        await driver(engine, siren).reconcile(now)
    assert siren.calls == []


@pytest.mark.asyncio
async def test_acknowledgement_during_intent_save_never_rings(engine, now, monkeypatch):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    output = driver(engine, siren)
    receipt = output._receipt

    async def acknowledged(entity, stamp, **values):
        await receipt(entity, stamp, **values)
        if values.get("status") == "requested":
            await answer(engine, current(engine), now)

    monkeypatch.setattr(output, "_receipt", acknowledged)
    await output.reconcile(now)
    assert siren.calls == []
    assert not engine.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]["owned"]


@pytest.mark.asyncio
async def test_aborted_helper_preparation_does_not_stop_an_unowned_siren(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    output = driver(engine, siren)

    async def aborted(entity, on, options):
        assert on
        await answer(engine, current(engine), now)
        return False

    output.send = aborted
    await output.reconcile(now)
    assert not siren.calls
    assert not engine.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]["owned"]


@pytest.mark.asyncio
async def test_unavailable_is_not_called_and_uncertain_stop_retried(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    siren.state = "unavailable"
    output = driver(engine, siren)
    await output.reconcile(now)
    assert not siren.calls
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]["status"] == "error"
    siren.state = "off"
    await output.reconcile(now + timedelta(seconds=15))
    siren.fail = True
    await output.reconcile(now + timedelta(seconds=16), stopping=True)
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]["owned"]
    siren.fail = False
    await output.reconcile(now + timedelta(seconds=31), stopping=True)
    assert siren.state == "off"


@pytest.mark.asyncio
async def test_unavailable_before_start_never_claims_or_stops_manual_siren(engine, store, now):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    siren.state = "unavailable"
    output = driver(engine, siren)
    await output.reconcile(now)
    record = engine.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]
    assert record["status"] == "error" and record["owned"] is False
    await answer(engine, current(engine), now)
    siren.state = "on"  # A later manual signal is not this failed attempt's output.
    restarted = Engine(store.value, store.save)
    await driver(restarted, siren).reconcile(now + timedelta(seconds=16), stopping=True)
    assert not siren.calls and siren.state == "on"


@pytest.mark.parametrize("previous_owned", [False, True])
async def test_cancelled_intent_save_settles_without_claiming_an_unstarted_siren(
    engine, store, now, previous_owned
):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    output = driver(engine, siren)
    if previous_owned:
        await output.reconcile(now)
        now += timedelta(seconds=20)
    entered, release = asyncio.Event(), asyncio.Event()
    intercepted = False

    async def persist(state):
        nonlocal intercepted
        record = state["alarm_outputs"].get("siren.synthetic_alarm", {})
        if not intercepted and record.get("status") == "requested":
            intercepted = True
            entered.set()
            await release.wait()
        await store.save(state)

    engine._persist = persist
    first_call = len(siren.calls)
    pending = asyncio.create_task(output.reconcile(now))
    await entered.wait()
    pending.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert pending.cancelled() and len(siren.calls) == first_call
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]["owned"] is previous_owned
    await answer(engine, current(engine), now)
    restarted = Engine(store.value, store.save)
    siren.state = "on"
    await driver(restarted, siren).reconcile(now + timedelta(seconds=16), stopping=True)
    assert siren.calls[first_call:] == (
        [("siren.synthetic_alarm", False)] if previous_owned else []
    )
    assert siren.state == ("off" if previous_owned else "on")


async def test_repeated_cancellation_does_not_abandon_prestart_ownership_restoration(
    engine, store, now
):
    await schedule(engine, now)
    await engine.tick(now)
    siren = VirtualSiren()
    output = driver(engine, siren)
    entered, release = asyncio.Event(), asyncio.Event()

    async def cancelled(entity, on, binding):
        raise AlarmPreparationCancelled("Synthetic first cancellation")

    async def persist(state):
        record = state["alarm_outputs"].get("siren.synthetic_alarm", {})
        if record.get("status") == "superseded":
            entered.set()
            await release.wait()
        await store.save(state)

    output.send, engine._persist = cancelled, persist
    pending = asyncio.create_task(output.reconcile(now))
    await entered.wait()
    pending.cancel("Synthetic second cancellation")
    await asyncio.sleep(0)
    pending.cancel("Synthetic third cancellation")
    release.set()
    with pytest.raises(asyncio.CancelledError) as cancellation:
        await pending
    assert cancellation.value.args == ("Synthetic first cancellation",)
    assert pending.cancelled() and not siren.calls
    restarted = Engine(store.value, store.save)
    assert restarted.snapshot()["alarm_outputs"]["siren.synthetic_alarm"]["owned"] is False
    siren.state = "on"
    await driver(restarted, siren).reconcile(now, stopping=True)
    assert not siren.calls and siren.state == "on"
