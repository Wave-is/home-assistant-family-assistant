"""Optional inventory polling. Unavailable observations retain the last good data."""

import asyncio
from datetime import timedelta

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from ..domain.validation import DomainError
from .ha_inventory import collect
from .inventory import build


class NetworkManager:
    def __init__(self, hass, entry, runtime, client):
        self.hass, self.entry, self.runtime, self.client = hass, entry, runtime, client
        self._task = self._unsub = None
        self._lock = asyncio.Lock()
        self._stopped = False
        self._last_attempt = None

    def start(self):
        self._unsub = async_track_time_interval(self.hass, self._interval, timedelta(minutes=2))
        self._task = self.hass.async_create_background_task(
            self._interval(None), "Family network inventory"
        )

    async def _interval(self, _now):
        try:
            await self.refresh()
        except (DomainError, OSError):
            pass  # Stable health key is set by refresh; no router data in logs.

    async def refresh(self):
        if self._stopped or "mikrotik" not in self.runtime.engine.snapshot()["settings"]["modules"]:
            raise DomainError("module_disabled")
        async with self._lock:
            now = dt_util.utcnow()
            if self._last_attempt and now - self._last_attempt < timedelta(seconds=5):
                previous_error = self.runtime.health.get("mikrotik")
                if previous_error and previous_error != "network_connected":
                    raise DomainError(previous_error)
                return
            self._last_attempt = now
            try:
                async with asyncio.timeout(45):
                    tables = await self.client.inventory()
                if self._stopped:
                    return
                observed = build(tables, collect(self.hass), now)

                def save(ctx):
                    ctx.state["network"]["inventory"] = observed

                await self.runtime.engine.system_update("network_inventory", now, save)
                self.runtime.health["mikrotik"] = "network_connected"
                self.runtime.updated()
            except (DomainError, OSError, TimeoutError) as err:
                code = (
                    err.code
                    if isinstance(err, DomainError)
                    else ("network_timeout" if isinstance(err, TimeoutError) else "storage_error")
                )
                self.runtime.health["mikrotik"] = code
                if isinstance(err, TimeoutError):
                    raise DomainError(code) from None
                raise

    async def stop(self):
        self._stopped = True
        if self._unsub:
            self._unsub()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # A UI refresh may be running outside our startup task. Wait for it to
        # finish without publishing stale data after option replacement.
        async with self._lock:
            pass
