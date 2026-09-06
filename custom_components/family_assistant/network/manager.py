"""Optional inventory polling. Unavailable observations retain the last good data."""

import asyncio
from datetime import timedelta

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from ..domain.validation import DomainError
from .config import identity, protected
from .ha_inventory import collect
from .inventory import build
from .lease_executor import LeaseExecutor


class NetworkManager:
    def __init__(self, hass, entry, runtime, client):
        self.hass, self.entry, self.runtime, self.client = hass, entry, runtime, client
        self._task = self._unsub = None
        self._lock = asyncio.Lock()
        self._stopped = False
        self._last_attempt = None
        self._effects_task = None
        self._backend = identity(entry.options.get("mikrotik", {}))
        self._protected = protected(entry.options.get("mikrotik", {}))

    def start(self):
        self._unsub = async_track_time_interval(self.hass, self._interval, timedelta(minutes=2))
        self._task = self.hass.async_create_background_task(
            self._interval(None), "Family network inventory"
        )
        self.request_effects()

    def request_effects(self):
        plans = self.runtime.engine.snapshot()["network"].get("plans", {})
        if (
            not self._stopped
            and (self._effects_task is None or self._effects_task.done())
            and any(p["status"] in {"queued", "applying", "rolling_back"} for p in plans.values())
        ):
            self._effects_task = self.hass.async_create_background_task(
                self._effects(), "Family selected lease changes"
            )

    def _authorized(self, plan):
        config = self.entry.options.get("mikrotik", {})
        state = self.runtime.engine.snapshot()
        member = state["members"].get(plan["actor"], {})
        return bool(
            not self._stopped
            and config.get("enabled")
            and config.get("allow_write") is True
            and identity(config) == self._backend == plan.get("backend")
            and "mikrotik" in state["settings"]["modules"]
            and member.get("active")
            and member.get("role") == "owner"
        )

    async def _effects(self):
        async with self._lock:
            plans = self.runtime.engine.snapshot()["network"].get("plans", {})
            for plan in plans.values():
                if self._stopped or plan["status"] not in {"queued", "applying", "rolling_back"}:
                    continue

                async def persist(progress, plan_id=plan["id"]):
                    def save(ctx):
                        current = ctx.state["network"]["plans"][plan_id]
                        current.update(progress=progress, status=progress["status"])
                        if progress["status"] in {
                            "applied",
                            "rolled_back",
                            "review_required",
                            "failed",
                        } and not current.get("notified"):
                            ctx.notify(
                                current["actor"],
                                "network_plan_finished",
                                {"id": plan_id, "status": progress["status"]},
                            )
                            current["notified"] = True

                    await self.runtime.engine.system_update(
                        "network_progress", dt_util.utcnow(), save
                    )

                try:
                    executor = LeaseExecutor(
                        self.client,
                        {
                            k: v
                            for k, v in plan.items()
                            if k not in {"progress", "status", "notified", "dhcp_recovery"}
                        },
                        persist,
                        lambda plan=plan: self._authorized(plan),
                        protected_macs=self._protected,
                    )
                    await executor.run(
                        dt_util.utcnow(),
                        plan.get("progress"),
                        dhcp_recovery=plan.get("dhcp_recovery", False),
                    )
                except DomainError as err:
                    progress = dict(plan.get("progress") or {})
                    progress.update(
                        status="review_required" if progress else "failed", failure=err.code
                    )
                    try:
                        await persist(progress)
                    except OSError:
                        self.runtime.health["mikrotik"] = "storage_error"
                        return
                except OSError:
                    self.runtime.health["mikrotik"] = "storage_error"
                    return
                finally:
                    self.runtime.updated()
        self._last_attempt = None
        await self._interval(None)

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
                for device in observed["devices"]:
                    if device["mac"] in self._protected:
                        device["protected"] = True

                def save(ctx):
                    ctx.state["network"]["inventory"] = observed
                    ctx.state["network"].update(
                        tables=tables,
                        backend=self._backend,
                        protected_macs=self._protected,
                        writable=self.entry.options.get("mikrotik", {}).get("allow_write") is True,
                    )

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
        if self._effects_task and not self._effects_task.done():
            self._effects_task.cancel()
            try:
                await self._effects_task
            except asyncio.CancelledError:
                pass
        # A UI refresh may be running outside our startup task. Wait for it to
        # finish without publishing stale data after option replacement.
        async with self._lock:
            pass
