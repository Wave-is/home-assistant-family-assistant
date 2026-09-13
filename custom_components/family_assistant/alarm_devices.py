"""Reconcile explicitly assigned sirens against durable alarm state.

This adapter does not claim to hear sound. A service call and a reported entity
state are separate observations. A physical sound/volume check is still needed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from .domain.engine import Engine
from .domain.validation import DomainError, timestamp


class AlarmNotStarted(DomainError):
    """Sender knows no siren turn_on was attempted, despite preparation calls."""


class AlarmPreparationCancelled(asyncio.CancelledError):
    """Cancellation before the sender attempted the main siren service."""


class AlarmDevices:
    def __init__(
        self,
        engine: Engine,
        bindings: Callable[[], dict],
        read: Callable[[str], dict | None],
        send: Callable[[str, bool, dict], Awaitable[bool | None]],
    ) -> None:
        self.engine = engine
        self.bindings = bindings
        self.read = read
        self.send = send
        self._lock = asyncio.Lock()

    def desired(self) -> dict:
        state = self.engine.snapshot()
        desired = {}
        for member, binding in self.bindings().items():
            # Only a siren explicitly opted in from the owner options flow.
            entity = binding.get("entity_id", "")
            if not binding.get("confirmed") or not entity.startswith("siren."):
                continue
            if any(
                run["member"] == member and run["siren_desired"]
                for run in state["alarm_runs"].values()
            ):
                desired[entity] = binding
        return desired

    async def reconcile(self, now: datetime, *, stopping=False) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            desired = {} if stopping else self.desired()
            previous = self.engine.snapshot()["alarm_outputs"]
            for entity in set(desired) | set(previous):
                on = entity in desired
                binding = desired.get(entity, {})
                record = previous.get(entity, {})
                observed = self.read(entity)
                observed_state = (observed or {}).get("state", "unavailable")
                if not on and not record.get("owned"):
                    continue  # Never stop a siren that this integration did not start.
                retry = record.get("retry_at")
                if retry and now < timestamp(retry, "retry_at") and record.get("desired") == on:
                    continue
                renew = record.get("renew_at")
                if on and observed_state == "on" and renew and now < timestamp(renew, "renew_at"):
                    continue
                if not on and observed_state == "off":
                    await self._receipt(
                        entity, now, owned=False, desired=False, status="reported_off"
                    )
                    continue
                # Keep a durable ownership marker before the first external call.
                try:
                    await self._receipt(
                        entity,
                        now,
                        owned=True,
                        desired=on,
                        status="requested",
                        attempted_at=now.isoformat(),
                    )
                except asyncio.CancelledError as error:
                    # Engine settles a cancelled Store write before raising.
                    # No sender was entered, so its durable intent is not proof
                    # that this integration started the siren.
                    try:
                        await self._cancel_before_start(entity, now, record)
                    finally:
                        raise error
                if observed_state in {"unavailable", "unknown"}:
                    await self._failed(
                        entity, now, "device_unavailable", owned=bool(record.get("owned"))
                    )
                    continue
                try:
                    # Store persistence yielded; acknowledgement or a binding
                    # change must not cause one last stale ring.
                    if on and self.desired().get(entity) != binding:
                        await self._receipt(
                            entity,
                            now,
                            owned=bool(record.get("owned")),
                            desired=False,
                            status="superseded",
                        )
                        continue
                    sent = await self.send(entity, on, binding)
                    if on and sent is False:
                        # Companion controls can yield before the siren call.
                        # Never stop an unowned siren we did not actually start.
                        await self._receipt(
                            entity,
                            now,
                            owned=bool(record.get("owned")),
                            desired=False,
                            status="superseded",
                        )
                        continue
                except AlarmPreparationCancelled as error:
                    try:
                        await self._cancel_before_start(entity, now, record)
                    finally:
                        raise error
                except AlarmNotStarted:
                    # The sender completed no siren call. Restore the prior
                    # ownership atomically with the failure receipt; a later
                    # manual signal must not become ours to silence.
                    await self._failed(
                        entity, now, "device_command_failed", owned=bool(record.get("owned"))
                    )
                    continue
                except (DomainError, OSError, TimeoutError):
                    await self._failed(entity, now, "device_command_failed")
                    continue
                # Acknowledgement could arrive while turn_on was in flight.
                if on and (stopping or entity not in self.desired()):
                    try:
                        await self.send(entity, False, {})
                        on = False
                    except (DomainError, OSError, TimeoutError):
                        await self._failed(entity, now, "device_command_failed")
                        continue
                observed_state = (self.read(entity) or {}).get("state", "unavailable")
                expected = "on" if on else "off"
                await self._receipt(
                    entity,
                    now,
                    desired=on,
                    owned=on or observed_state != "off",
                    status=f"reported_{expected}"
                    if observed_state == expected
                    else "awaiting_state",
                    renew_at=(now + timedelta(seconds=20)).isoformat(),
                    retry_at=None,
                    last_error=None,
                )

    async def _cancel_before_start(self, entity: str, now: datetime, previous: dict) -> None:
        """Settle ownership restoration even if the caller is cancelled again."""
        cleanup = asyncio.create_task(
            self._receipt(
                entity,
                now,
                owned=bool(previous.get("owned")),
                desired=False,
                status="superseded",
            )
        )
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                continue
        cleanup.result()

    async def _receipt(self, entity: str, now: datetime, **values) -> None:
        def update(ctx):
            record = ctx.state["alarm_outputs"].setdefault(entity, {})
            record.update(values)

        await self.engine.background_update("alarm_output", now, update)

    async def _failed(
        self, entity: str, now: datetime, code: str, *, owned: bool | None = None
    ) -> None:
        def failed(ctx):
            record = ctx.state["alarm_outputs"][entity]
            if owned is not None:
                record["owned"] = owned
            record.update(
                status="error", last_error=code, retry_at=(now + timedelta(seconds=15)).isoformat()
            )
            if not record.get("notified"):
                ctx.notify("parents", "alarm_device_error", {"entity_id": entity, "error": code})
                record["notified"] = True

        await self.engine.background_update("alarm_output_error", now, failed)

    async def close_incidents(self, now: datetime) -> None:
        def update(ctx):
            for entity, record in ctx.state["alarm_outputs"].items():
                if record.get("notified") and record.get("status") in {
                    "reported_on",
                    "reported_off",
                }:
                    ctx.notify("parents", "alarm_device_recovered", {"entity_id": entity})
                    record["notified"] = False

        await self.engine.background_update("alarm_output_recovered", now, update)
