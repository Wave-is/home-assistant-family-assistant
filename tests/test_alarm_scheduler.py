"""Real scheduler/binding/Engine contracts with synthetic HA service boundaries."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from copy import deepcopy
from datetime import timedelta
from enum import IntFlag
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_alarms import answer, current, schedule

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def scheduler_module(monkeypatch, now):
    class Features(IntFlag):
        TURN_ON = 1
        TURN_OFF = 2
        TONES = 4
        VOLUME_SET = 8
        DURATION = 16

    class HomeAssistantError(Exception):
        pass

    modules = {
        name: ModuleType(name)
        for name in (
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.siren",
            "homeassistant.exceptions",
            "homeassistant.helpers",
            "homeassistant.helpers.event",
            "homeassistant.helpers.entity_registry",
            "homeassistant.util",
            "homeassistant.util.dt",
        )
    }
    modules["homeassistant.components.siren"].SirenEntityFeature = Features
    modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
    modules["homeassistant.helpers.event"].async_track_time_interval = lambda *args: None
    modules["homeassistant.helpers.entity_registry"].async_get = lambda hass: hass.registry
    modules["homeassistant.util.dt"].utcnow = lambda: now
    modules["homeassistant.util"].dt = modules["homeassistant.util.dt"]
    modules["homeassistant.helpers"].entity_registry = modules[
        "homeassistant.helpers.entity_registry"
    ]
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "custom_components.family_assistant._alarm_scheduler_test"
    path = Path(__file__).resolve().parents[1] / "custom_components/family_assistant/scheduler.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


class NativeServices:
    def __init__(self, states):
        self.states = states
        self.calls = []
        self.hook = None
        self.echo = True

    async def async_call(self, domain, service, payload, *, blocking):
        assert blocking is True
        assert (domain, service) in {
            ("number", "set_value"),
            ("select", "select_option"),
            ("siren", "turn_on"),
            ("siren", "turn_off"),
        }
        self.calls.append((domain, service, deepcopy(payload)))
        if self.hook:
            await self.hook(domain, service, payload)
        if self.echo:
            value = payload.get("value", payload.get("option"))
            if domain == "siren":
                value = "on" if service == "turn_on" else "off"
            self.states[payload["entity_id"]].state = str(value)


@pytest.fixture
def scheduler(scheduler_module, engine):
    states = {
        "siren.synthetic": SimpleNamespace(state="off", attributes={"supported_features": 3}),
        "number.synthetic_duration": SimpleNamespace(
            state="60", attributes={"min": 60, "max": 1800, "step": 1}
        ),
        "select.synthetic_volume": SimpleNamespace(
            state="low", attributes={"options": ["low", "middle", "high"]}
        ),
    }
    devices = dict.fromkeys(states, "synthetic-alarm-device")
    services = NativeServices(states)
    hass = SimpleNamespace(
        states=SimpleNamespace(get=states.get),
        services=services,
        registry=SimpleNamespace(async_get=lambda key: SimpleNamespace(device_id=devices.get(key))),
    )
    binding = {
        "entity_id": "siren.synthetic",
        "confirmed": True,
        "volume": 0.7,
        "duration_entity_id": "number.synthetic_duration",
        "duration_seconds": 420,
        "volume_entity_id": "select.synthetic_volume",
        "select_volume": "middle",
        "companion_device_id": "synthetic-alarm-device",
    }
    entry = SimpleNamespace(options={"alarm_devices": {"child": binding}})
    runtime = SimpleNamespace(engine=engine)
    worker = scheduler_module.Scheduler(hass, entry, runtime)
    return worker, states, devices, services


async def start(engine, now):
    await schedule(engine, now)
    await engine.tick(now)


@pytest.mark.parametrize("failure", ["unavailable", "service", "timeout", "os_error", "readback"])
async def test_known_prestart_failure_does_not_claim_manual_siren(
    scheduler, scheduler_module, engine, now, failure
):
    worker, states, _, services = scheduler
    await start(engine, now)
    if failure == "unavailable":
        states["number.synthetic_duration"].state = "unavailable"
    elif failure == "readback":
        services.echo = False
    else:

        async def fail(domain, service, payload):
            assert domain == "number"
            if failure == "timeout":
                raise TimeoutError("Synthetic helper timeout")
            if failure == "os_error":
                raise OSError("Synthetic helper connection failure")
            raise scheduler_module.HomeAssistantError("Synthetic helper failure")

        services.hook = fail
    await worker.devices.reconcile(now)
    record = engine.snapshot()["alarm_outputs"]["siren.synthetic"]
    assert record["status"] == "error" and record["owned"] is False
    assert not any(domain == "siren" for domain, _, _ in services.calls)
    await answer(engine, current(engine), now)
    states["siren.synthetic"].state = "on"
    services.hook, services.echo = None, True
    await worker.devices.reconcile(now + timedelta(seconds=16), stopping=True)
    assert not any(domain == "siren" for domain, _, _ in services.calls)
    assert states["siren.synthetic"].state == "on"


@pytest.mark.parametrize("helper", ["number", "select"])
@pytest.mark.parametrize("change", ["ack", "revoke", "remap", "stop"])
async def test_helper_await_rechecks_desire_and_registry_before_later_calls(
    scheduler, engine, now, helper, change
):
    worker, _, devices, services = scheduler
    await start(engine, now)

    async def changed(domain, service, payload):
        if domain != helper:
            return
        if change == "ack":
            await answer(engine, current(engine), now)
        elif change == "revoke":
            worker.entry.options = {"alarm_devices": {}}
        elif change == "remap":
            devices.update(dict.fromkeys(devices, "synthetic-replacement-device"))
        else:
            worker._stopped = True

    services.hook = changed
    await worker.devices.reconcile(now)
    assert [domain for domain, _, _ in services.calls] == (
        ["number"] if helper == "number" else ["number", "select"]
    )
    record = engine.snapshot()["alarm_outputs"]["siren.synthetic"]
    assert record["owned"] is False
    assert record["status"] == ("error" if change == "remap" else "superseded")


async def test_successful_controls_are_verified_before_start_and_ack_stops(scheduler, engine, now):
    worker, states, _, services = scheduler
    await start(engine, now)
    await worker.devices.reconcile(now)
    assert [(domain, service) for domain, service, _ in services.calls] == [
        ("number", "set_value"),
        ("select", "select_option"),
        ("siren", "turn_on"),
    ]
    assert services.calls[-1][2] == {"entity_id": "siren.synthetic"}
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic"]["owned"] is True
    await answer(engine, current(engine), now)
    await worker.devices.reconcile(now)
    assert services.calls[-1][:2] == ("siren", "turn_off")
    assert states["siren.synthetic"].state == "off"


@pytest.mark.parametrize("failure", ["timeout", "domain", "ha", "os_error"])
async def test_uncertain_siren_call_keeps_ownership_for_compensating_stop(
    scheduler, scheduler_module, engine, now, failure
):
    worker, states, _, services = scheduler
    await start(engine, now)

    async def unknown_result(domain, service, payload):
        if domain == "siren" and service == "turn_on":
            states[payload["entity_id"]].state = "on"
            if failure == "domain":
                raise DomainError("device_command_failed")
            if failure == "ha":
                raise scheduler_module.HomeAssistantError("Synthetic siren receipt loss")
            if failure == "os_error":
                raise OSError("Synthetic siren connection lost")
            raise TimeoutError("Synthetic receipt loss after start")

    services.hook = unknown_result
    await worker.devices.reconcile(now)
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic"]["owned"] is True
    await answer(engine, current(engine), now)
    services.hook = None
    await worker.devices.reconcile(now)
    assert services.calls[-1][:2] == ("siren", "turn_off")
    assert states["siren.synthetic"].state == "off"


async def test_failed_renewal_preparation_preserves_earlier_real_ownership(scheduler, engine, now):
    worker, states, _, services = scheduler
    await start(engine, now)
    await worker.devices.reconcile(now)
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic"]["owned"] is True
    states["number.synthetic_duration"].state = "60"

    async def fail_helper(domain, service, payload):
        if domain == "number":
            raise TimeoutError("Synthetic renewal preparation failure")

    services.hook = fail_helper
    await worker.devices.reconcile(now + timedelta(seconds=20))
    record = engine.snapshot()["alarm_outputs"]["siren.synthetic"]
    assert record["status"] == "error" and record["owned"] is True
    assert [domain for domain, _, _ in services.calls] == ["number", "select", "siren", "number"]
    await answer(engine, current(engine), now + timedelta(seconds=21))
    await worker.devices.reconcile(now + timedelta(seconds=21))
    assert services.calls[-1][:2] == ("siren", "turn_off")
    assert states["siren.synthetic"].state == "off"


@pytest.mark.parametrize("phase", ["number", "select", "readback", "siren"])
@pytest.mark.parametrize("cancellation", ["direct", "task"])
@pytest.mark.parametrize("previous_owned", [False, True])
async def test_cancelled_send_preserves_only_real_or_uncertain_ownership_after_restart(
    scheduler,
    scheduler_module,
    engine,
    store,
    now,
    monkeypatch,
    phase,
    cancellation,
    previous_owned,
):
    worker, states, _, services = scheduler
    await start(engine, now)
    if previous_owned:
        await worker.devices.reconcile(now)
        now += timedelta(seconds=20)
        states["number.synthetic_duration"].state = "60"
        states["select.synthetic_volume"].state = "low"
    first_call = len(services.calls)
    entered, blocked = asyncio.Event(), asyncio.Event()

    async def cancel_here():
        entered.set()
        if cancellation == "direct":
            raise asyncio.CancelledError("Synthetic cancellation")
        await blocked.wait()

    async def hook(domain, service, payload):
        if domain == phase:
            if domain == "siren":
                states[payload["entity_id"]].state = "on"  # Accepted before receipt loss.
            await cancel_here()

    services.hook = hook
    if phase == "readback":
        services.echo = False
        sleep = asyncio.sleep

        async def readback_sleep(delay):
            if delay == 0.1:
                await cancel_here()
            else:
                await sleep(delay)

        monkeypatch.setattr(scheduler_module.asyncio, "sleep", readback_sleep)
    pending = asyncio.create_task(worker.devices.reconcile(now))
    await entered.wait()
    if cancellation == "task":
        pending.cancel("Synthetic cancellation")
    with pytest.raises(asyncio.CancelledError) as cancelled:
        await pending
    assert cancelled.value.args == ("Synthetic cancellation",)
    assert pending.cancelled()
    expected_owned = previous_owned or phase == "siren"
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic"]["owned"] is expected_owned
    assert any(domain == "siren" for domain, _, _ in services.calls[first_call:]) is (
        phase == "siren"
    )

    await answer(engine, current(engine), now)
    restarted = Engine(store.value, store.save)
    worker.devices.engine = restarted
    services.hook, services.echo = None, True
    states["siren.synthetic"].state = "on"  # Could be a later, unrelated manual signal.
    first_stop = len(services.calls)
    await worker.devices.reconcile(now + timedelta(seconds=16), stopping=True)
    assert services.calls[first_stop:] == (
        [("siren", "turn_off", {"entity_id": "siren.synthetic"})] if expected_owned else []
    )
    assert states["siren.synthetic"].state == ("off" if expected_owned else "on")


@pytest.mark.parametrize("phase", ["number", "siren"])
@pytest.mark.parametrize("already_done", [False, True])
async def test_stop_survives_cancelled_worker_and_reconciles_only_owned_output(
    scheduler, engine, now, phase, already_done
):
    worker, states, _, services = scheduler
    await start(engine, now)
    entered, blocked = asyncio.Event(), asyncio.Event()

    async def hook(domain, service, payload):
        if domain == phase and service != "turn_off":
            states["siren.synthetic"].state = "on"
            entered.set()
            await blocked.wait()

    services.hook = hook
    worker._task = asyncio.create_task(worker.devices.reconcile(now))
    await entered.wait()
    if already_done:
        worker._task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker._task
    stopping = asyncio.create_task(worker.stop())
    await asyncio.sleep(0)
    if not already_done:
        worker._task.cancel()
    await stopping
    assert worker._task.cancelled() and not stopping.cancelled()
    stops = [call for call in services.calls if call[:2] == ("siren", "turn_off")]
    assert len(stops) == (1 if phase == "siren" else 0)
    assert states["siren.synthetic"].state == ("off" if phase == "siren" else "on")


@pytest.mark.parametrize("interval", [False, True])
async def test_stop_caller_cancellation_settles_compensating_stop_then_propagates(
    scheduler, engine, now, interval
):
    worker, states, _, services = scheduler
    await start(engine, now)
    started, finish_start, stopping_output, finish_stop = (asyncio.Event() for _ in range(4))

    async def hook(domain, service, payload):
        if domain == "siren" and service == "turn_on":
            states[payload["entity_id"]].state = "on"
            started.set()
            await finish_start.wait()
        if domain == "siren" and service == "turn_off":
            stopping_output.set()
            await finish_stop.wait()

    services.hook = hook

    async def run():
        worker._busy = True
        try:
            await worker.devices.reconcile(now)
        finally:
            worker._busy = False

    pending = asyncio.create_task(run())
    if not interval:
        worker._task = pending
    await started.wait()
    stopping = asyncio.create_task(worker.stop())
    await asyncio.sleep(0)
    stopping.cancel("Synthetic stop cancellation")
    await asyncio.sleep(0)
    assert not pending.cancelled()
    finish_start.set()
    await asyncio.wait_for(stopping_output.wait(), 1)
    stopping.cancel()  # Repeated caller cancellation must not abort physical cleanup.
    finish_stop.set()
    with pytest.raises(asyncio.CancelledError) as cancelled:
        await stopping
    assert cancelled.value.args == ("Synthetic stop cancellation",)
    assert stopping.cancelled() and not pending.cancelled()
    assert states["siren.synthetic"].state == "off"
    assert engine.snapshot()["alarm_outputs"]["siren.synthetic"]["owned"] is False
