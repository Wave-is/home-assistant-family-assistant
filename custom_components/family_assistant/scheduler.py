"""Home Assistant clock and opt-in physical alarm adapter."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.components.siren import SirenEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .alarm_devices import AlarmDevices
from .domain.validation import DomainError
from .routine_observations import collect as collect_routine_observations


class Scheduler:
    def __init__(self, hass, entry, runtime):
        self.hass, self.entry, self.runtime = hass, entry, runtime
        self._unsub = None
        self._busy = False
        self._stopped = False
        self._task = None
        self._tone_index = {}
        self.devices = AlarmDevices(
            runtime.engine, lambda: entry.options.get("alarm_devices", {}), self._read, self._send
        )

    def _read(self, entity_id):
        state = self.hass.states.get(entity_id)
        return {"state": state.state, "attributes": dict(state.attributes)} if state else None

    async def _send(self, entity_id, on, binding):
        state = self.hass.states.get(entity_id)
        if state is None:
            raise DomainError("device_unavailable")
        features = state.attributes.get("supported_features", 0)
        if not features & SirenEntityFeature.TURN_OFF or not features & SirenEntityFeature.TURN_ON:
            raise DomainError("device_unsupported")
        data = {"entity_id": entity_id}
        if on:
            # Renew before the device's finite duration expires; no fixed ring count.
            if features & SirenEntityFeature.DURATION:
                data["duration"] = 35
            if features & SirenEntityFeature.VOLUME_SET:
                data["volume_level"] = binding.get("volume", 0.5)
            available = state.attributes.get("available_tones", [])
            if features & SirenEntityFeature.TONES and available:
                tones = list(available.values()) if isinstance(available, dict) else list(available)
                index = self._tone_index.get(entity_id, 0)
                data["tone"] = tones[index % len(tones)]
                self._tone_index[entity_id] = index + 1
        try:
            async with asyncio.timeout(10):
                await self.hass.services.async_call(
                    "siren", "turn_on" if on else "turn_off", data, blocking=True
                )
        except HomeAssistantError:
            raise DomainError("device_command_failed") from None

    def start(self):
        self._unsub = async_track_time_interval(self.hass, self._interval, timedelta(seconds=5))
        self.request()

    async def _interval(self, now):
        await self.run(now)

    def request(self):
        if not self._stopped and not self._busy and (self._task is None or self._task.done()):
            self._task = self.hass.async_create_task(
                self.run(dt_util.utcnow()), "Family Assistant state reconciliation"
            )

    async def run(self, now):
        if self._busy or self._stopped:
            return
        self._busy = True
        try:
            observations = collect_routine_observations(
                self.runtime.engine.snapshot(), self.hass.states.get
            )
            if await self.runtime.engine.tick(now, routine_observations=observations):
                self.runtime.updated()
            await self.devices.reconcile(now)
            await self.devices.close_incidents(now)
            from .digest_health import synchronize

            synchronize(self.hass, self.entry, self.runtime)
            self.runtime.health.pop("scheduler", None)
        except DomainError as error:
            if error.code != "backup_in_progress":
                self.runtime.health["scheduler"] = "scheduler_failed"
        except (OSError, TimeoutError):
            # No raw provider data or exceptions in logs or exported diagnostics.
            self.runtime.health["scheduler"] = "scheduler_failed"
        finally:
            self._busy = False

    async def stop(self):
        self._stopped = True
        if self._unsub:
            self._unsub()
        if self._task and not self._task.done():
            await self._task
        # Interval callbacks are not in _task; wait for the bounded in-flight send.
        while self._busy:
            await asyncio.sleep(0.05)
        await self.devices.reconcile(dt_util.utcnow(), stopping=True)
