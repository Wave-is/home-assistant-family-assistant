"""Home Assistant clock and opt-in physical alarm adapter."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.components.siren import SirenEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .alarm_devices import AlarmDevices, AlarmNotStarted, AlarmPreparationCancelled
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
        from .alarm_binding import pending_controls, validate_binding

        siren_attempted = False
        try:
            state = self.hass.states.get(entity_id)
            if state is None:
                raise DomainError("device_unavailable")
            features = state.attributes.get("supported_features", 0)
            if (
                not features & SirenEntityFeature.TURN_OFF
                or not features & SirenEntityFeature.TURN_ON
            ):
                raise DomainError("device_unsupported")
            data = {"entity_id": entity_id}
            if on:
                checked = validate_binding(self.hass, binding)
                # Renew before the device's finite duration expires; no fixed ring count.
                if features & SirenEntityFeature.DURATION and not checked.get("duration_entity_id"):
                    data["duration"] = 35
                if features & SirenEntityFeature.VOLUME_SET and not checked.get("volume_entity_id"):
                    data["volume_level"] = checked["volume"]
                available = state.attributes.get("available_tones", [])
                if features & SirenEntityFeature.TONES and available:
                    tones = (
                        list(available.values()) if isinstance(available, dict) else list(available)
                    )
                    index = self._tone_index.get(entity_id, 0)
                    data["tone"] = tones[index % len(tones)]
                    self._tone_index[entity_id] = index + 1
            async with asyncio.timeout(10):
                if on:
                    for domain, service, payload in pending_controls(self.hass, checked):
                        if self._stopped or self.devices.desired().get(entity_id) != binding:
                            return False
                        validate_binding(self.hass, checked)
                        await self.hass.services.async_call(domain, service, payload, blocking=True)
                    # A helper's service receipt is not evidence that the target
                    # setting changed. Briefly allow its HA state to catch up.
                    for attempt in range(21):
                        if self._stopped or self.devices.desired().get(entity_id) != binding:
                            return False
                        validate_binding(self.hass, checked)
                        if not pending_controls(self.hass, checked):
                            break
                        if attempt == 20:
                            raise DomainError("device_command_failed")
                        await asyncio.sleep(0.1)
                # Once this await begins, even a failed receipt cannot prove
                # that the siren stayed off. Keep durable ownership for stop.
                siren_attempted = True
                await self.hass.services.async_call(
                    "siren", "turn_on" if on else "turn_off", data, blocking=True
                )
        except asyncio.CancelledError as error:
            if on and not siren_attempted:
                raise AlarmPreparationCancelled(*error.args) from None
            raise
        except (DomainError, HomeAssistantError, OSError, TimeoutError) as error:
            if on and not siren_attempted:
                code = error.code if isinstance(error, DomainError) else "device_command_failed"
                raise AlarmNotStarted(code) from None
            if isinstance(error, HomeAssistantError):
                raise DomainError("device_command_failed") from None
            raise

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
            from .school_reminder_health import synchronize as synchronize_school

            synchronize(self.hass, self.entry, self.runtime)
            synchronize_school(self.hass, self.entry, self.runtime, now)
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

        async def drain():
            if self._task:
                try:
                    await self._task
                except asyncio.CancelledError:
                    # Cancellation of the worker is not cancellation of stop.
                    # Its durable ownership still requires reconciliation.
                    if asyncio.current_task().cancelling():
                        raise
            # Interval callbacks are not in _task; wait for the in-flight send.
            while self._busy:
                await asyncio.sleep(0.05)
            await self.devices.reconcile(dt_util.utcnow(), stopping=True)

        cleanup = asyncio.create_task(drain())
        cancellation = None
        try:
            while True:
                try:
                    await asyncio.shield(cleanup)
                    break
                except asyncio.CancelledError as error:
                    cancellation = cancellation or error
                    if cleanup.done():
                        break
                except BaseException:
                    if cancellation is None:
                        raise
                    break
            cleanup.result()
        finally:
            if cancellation is not None:
                raise cancellation
