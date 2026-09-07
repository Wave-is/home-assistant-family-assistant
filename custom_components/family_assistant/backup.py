"""Quiesce household state and private media while Home Assistant snapshots config."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

BACKUP_TIMEOUT_SECONDS = 60
_ERROR = "backup_unavailable"


@dataclass(slots=True)
class _Lease:
    """The independently acquired portions of one runtime lease."""

    runtime: Any
    media_token: object | None = None
    media_acquired: bool = False
    engine_token: object | None = None
    engine_acquired: bool = False


@dataclass(slots=True)
class _Coordinator:
    """Process-local ownership for one Home Assistant backup generation."""

    generation: object = field(default_factory=object)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    released: asyncio.Event = field(default_factory=asyncio.Event)
    leases: list[_Lease] = field(default_factory=list)


def _domain_data(hass: HomeAssistant) -> dict:
    data = hass.data.setdefault(DOMAIN, {})
    data.setdefault("entries", {})
    return data


async def _acquire(coordinator: _Coordinator, runtimes: list[Any]) -> None:
    for runtime in runtimes:
        lease = _Lease(runtime)
        media_token = await runtime.media.async_pause_backup()
        lease.media_token = media_token
        lease.media_acquired = True
        coordinator.leases.append(lease)
        engine_token = await runtime.engine.async_begin_backup()
        lease.engine_token = engine_token
        lease.engine_acquired = True


async def _unwind(coordinator: _Coordinator) -> bool:
    """Release everything in reverse order and report whether a release failed."""
    failed = False
    for lease in reversed(coordinator.leases):
        if lease.engine_acquired:
            try:
                await lease.runtime.engine.async_end_backup(lease.engine_token)
            except Exception:  # noqa: BLE001 - never expose or skip later releases
                failed = True
            else:
                lease.engine_acquired = False
        if lease.media_acquired:
            try:
                await lease.runtime.media.async_resume_backup(lease.media_token)
            except Exception:  # noqa: BLE001 - never expose or skip later releases
                failed = True
            else:
                lease.media_acquired = False
    if not failed:
        coordinator.leases.clear()
    return failed


async def _finish_unwind(coordinator: _Coordinator) -> tuple[bool, bool]:
    """Finish owned cleanup even when the caller is cancelled again."""
    task = asyncio.create_task(_unwind(coordinator))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            continue
    return task.result(), cancelled


def _remove_if_current(data: dict, coordinator: _Coordinator) -> None:
    if data.get("backup") is coordinator:
        data.pop("backup", None)
        coordinator.released.set()


async def async_pre_backup(hass: HomeAssistant) -> None:
    """Drain mutable media work and freeze every loaded household."""
    data = _domain_data(hass)
    if "backup" in data:
        raise HomeAssistantError(_ERROR)

    coordinator = _Coordinator()
    # Registration and entry setup use presence of this key as their no-race gate.
    data["backup"] = coordinator
    setup_lock = data.setdefault("setup_lock", asyncio.Lock())

    async with coordinator.lock:
        try:
            async with asyncio.timeout(BACKUP_TIMEOUT_SECONDS):
                # Entry setup holds this across its initial Store load/save and runtime
                # registration. The marker above prevents another setup starting later.
                async with setup_lock:
                    entries = data.get("entries")
                    if not isinstance(entries, dict):
                        raise TypeError
                    runtimes = [entries[key] for key in sorted(entries)]
                await _acquire(coordinator, runtimes)
        except asyncio.CancelledError:
            failed, _ = await _finish_unwind(coordinator)
            if not failed:
                _remove_if_current(data, coordinator)
            raise
        except Exception:  # noqa: BLE001 - callback errors must be code-only
            failed, cancelled = await _finish_unwind(coordinator)
            if not failed:
                _remove_if_current(data, coordinator)
            if cancelled:
                raise asyncio.CancelledError from None
            raise HomeAssistantError(_ERROR) from None


async def async_post_backup(hass: HomeAssistant) -> None:
    """Resume a completed or failed backup generation; harmless without one."""
    data = hass.data.get(DOMAIN)
    if not isinstance(data, dict):
        return
    coordinator = data.get("backup")
    if not isinstance(coordinator, _Coordinator):
        return

    async with coordinator.lock:
        failed, cancelled = await _finish_unwind(coordinator)
        if not failed:
            _remove_if_current(data, coordinator)
    if cancelled:
        raise asyncio.CancelledError
    if failed:
        raise HomeAssistantError(_ERROR)
