"""A virtual siren verifies renewal, failure, restart and acknowledgement races."""

from datetime import timedelta

import pytest
from test_alarms import answer, current, schedule

from custom_components.family_assistant.alarm_devices import AlarmDevices
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
