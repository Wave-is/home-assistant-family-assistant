"""Serial, bounded read-only polling, fenced against settings and identity changes."""

import asyncio
from copy import deepcopy
from datetime import timedelta

from ..domain import online_school as domain
from ..domain.validation import DomainError, timestamp
from .delivery import enqueue
from .provider import RespublikaClient


async def poll(engine, options, now, *, current, paused=lambda: False, factory=None):
    """One pass. Options/current are private adapter-only values, never projections."""
    for source_id, config in options.get("sources", {}).items():
        if paused() or current() != options:
            return
        state = engine.snapshot()
        source = domain.current_source(
            state, source_id, config.get("generation"), config.get("member_revision")
        )
        if source is None or not config.get("enabled"):
            continue
        last = source.get("last_attempt")
        interval = (
            timedelta(hours=1)
            if source.get("status") in {"online_school_auth_failed", "online_school_rate_limited"}
            else timedelta(minutes=15)
        )
        due = last is None or now - timestamp(last, "last_attempt") >= interval
        if due:
            client = None
            snapshot = None
            code = None
            try:
                client = (factory or RespublikaClient)(
                    config["url"], config["username"], config["password"]
                )
                async with asyncio.timeout(90):
                    snapshot = await client.fetch(config["student_id"], config["timezone"], now)
                snapshot = domain.normalize_snapshot(snapshot)
                if snapshot["student_id"] != config["student_id"]:
                    raise DomainError("online_school_student_mismatch")
                if snapshot["timezone"] != config["timezone"]:
                    raise DomainError("online_school_invalid_response")
            except DomainError as error:
                code = (
                    error.code
                    if error.code in domain.FAILURES
                    else "online_school_invalid_response"
                )
            except TimeoutError:
                code = "online_school_timeout"
            except Exception:  # noqa: BLE001 - no provider exception payload or URL may reach logs
                code = "online_school_unavailable"
            finally:
                if client is not None:
                    await client.close()
            if paused() or current() != options:
                return

            def commit(ctx, source_id=source_id, config=config, code=code, snapshot=snapshot):
                if paused() or current() != options:
                    return
                if code:
                    domain.record_failure(
                        ctx.state,
                        source_id,
                        config["generation"],
                        config["member_revision"],
                        code,
                        now,
                    )
                else:
                    result = domain.apply_snapshot(
                        ctx.state,
                        source_id,
                        config["generation"],
                        config["member_revision"],
                        snapshot,
                        now,
                    )
                    if result["applied"]:
                        enqueue(ctx, source_id, result["changes"] if not result["baseline"] else [])

            await engine.background_update("online_school_sync", now, commit)

        # Digest clock is independent from fetch cadence; good cached facts only.
        def digest(ctx, source_id=source_id):
            if not paused() and current() == options:
                enqueue(ctx, source_id, [])

        await engine.background_update("online_school_digest", now, digest)


class SchoolManager:
    def __init__(self, hass, entry, runtime):
        self.hass, self.entry, self.runtime = hass, entry, runtime
        self.options = deepcopy(entry.options.get("online_school", {}))
        self.task = None
        self.unsubscribe = None

    def start(self):
        from homeassistant.helpers.event import async_track_time_interval
        from homeassistant.util import dt as dt_util

        self.unsubscribe = async_track_time_interval(self.hass, self.request, timedelta(minutes=1))
        self.request(dt_util.utcnow())

    def request(self, now):
        if self.task is not None and not self.task.done():
            return

        async def run():
            try:
                await poll(
                    self.runtime.engine,
                    self.options,
                    now,
                    current=lambda: self.entry.options.get("online_school", {}),
                    paused=lambda: bool(self.hass.data.get("family_assistant", {}).get("backup")),
                )
                self.runtime.health.pop("online_school", None)
                self.runtime.updated()
            except DomainError as error:
                if error.code != "backup_in_progress":
                    self.runtime.health["online_school"] = "online_school_unavailable"
            except Exception:  # noqa: BLE001 - sanitized adapter health only
                self.runtime.health["online_school"] = "online_school_unavailable"

        self.task = self.hass.async_create_background_task(run(), "Family Assistant online school")

    async def stop(self):
        if self.unsubscribe:
            self.unsubscribe()
            self.unsubscribe = None
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
