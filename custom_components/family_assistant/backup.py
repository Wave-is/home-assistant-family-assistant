"""Quiesce household state and private media while Home Assistant snapshots config."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

BACKUP_TIMEOUT_SECONDS = 60
RELEASE_TIMEOUT_SECONDS = 10
_ERROR = "backup_unavailable"
_STALE = "stale_recovery"

PHASE_ACQUIRING = "acquiring"
PHASE_FROZEN = "frozen"
PHASE_RELEASING = "releasing"
PHASE_RECOVERY = "recovery_required"
PHASE_RELEASED = "released"


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
    phase: str = PHASE_ACQUIRING
    issue_created: bool = False


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
    loop = asyncio.get_running_loop()
    deadline = loop.time() + BACKUP_TIMEOUT_SECONDS

    async def release(call) -> bool:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        try:
            async with asyncio.timeout(min(RELEASE_TIMEOUT_SECONDS, remaining)):
                await call()
        except asyncio.CancelledError:
            # _finish_unwind owns and shields this task, so this is cancellation
            # raised by the owned release itself. Retain its acquired flag.
            return False
        except Exception:  # noqa: BLE001 - fixed error, keep trying later leases
            return False
        return True

    for lease in reversed(coordinator.leases):
        if lease.engine_acquired:
            if await release(
                lambda lease=lease: lease.runtime.engine.async_end_backup(lease.engine_token)
            ):
                lease.engine_acquired = False
            else:
                failed = True
        if lease.media_acquired:
            if await release(
                lambda lease=lease: lease.runtime.media.async_resume_backup(lease.media_token)
            ):
                lease.media_acquired = False
            else:
                failed = True
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


def _show_recovery(hass: HomeAssistant, coordinator: _Coordinator) -> None:
    coordinator.phase = PHASE_RECOVERY
    try:
        from .backup_recovery import create_issue

        create_issue(hass)
    except Exception:  # noqa: BLE001 - visibility must not replace the safety gate
        return
    coordinator.issue_created = True


def _remove_if_current(hass: HomeAssistant, data: dict, coordinator: _Coordinator) -> None:
    if data.get("backup") is not coordinator:
        return
    coordinator.phase = PHASE_RELEASED
    data.pop("backup", None)
    coordinator.released.set()
    if coordinator.issue_created:
        coordinator.issue_created = False
        try:
            from .backup_recovery import delete_issue

            delete_issue(hass)
        except Exception:  # noqa: BLE001 - a stale issue cannot refreeze released data
            return


def recovery_identity(hass: HomeAssistant) -> tuple[_Coordinator, object] | None:
    """Return process-local recovery identity, never serialize its generation."""
    data = hass.data.get(DOMAIN)
    if not isinstance(data, dict):
        return None
    coordinator = data.get("backup")
    if not isinstance(coordinator, _Coordinator) or coordinator.phase != PHASE_RECOVERY:
        return None
    return coordinator, coordinator.generation


def recovery_matches(hass: HomeAssistant, coordinator: _Coordinator, generation: object) -> bool:
    """Check that a captured Repair still names the exact recoverable generation."""
    current = recovery_identity(hass)
    return bool(
        current
        and current[0] is coordinator
        and current[1] is generation
        and coordinator.generation is generation
    )


async def async_retry_recovery(
    hass: HomeAssistant, coordinator: _Coordinator, generation: object
) -> None:
    """Retry only unreleased leases from one failed unwind generation."""
    data = hass.data.get(DOMAIN)
    if not isinstance(data, dict):
        raise HomeAssistantError(_STALE)
    async with coordinator.lock:
        if not recovery_matches(hass, coordinator, generation):
            raise HomeAssistantError(_STALE)
        coordinator.phase = PHASE_RELEASING
        failed, cancelled = await _finish_unwind(coordinator)
        if failed:
            _show_recovery(hass, coordinator)
        else:
            _remove_if_current(hass, data, coordinator)
    if cancelled:
        raise asyncio.CancelledError
    if failed:
        raise HomeAssistantError(_ERROR)


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
                coordinator.phase = PHASE_FROZEN
        except asyncio.CancelledError:
            coordinator.phase = PHASE_RELEASING
            failed, _ = await _finish_unwind(coordinator)
            if not failed:
                _remove_if_current(hass, data, coordinator)
            else:
                _show_recovery(hass, coordinator)
            raise
        except Exception:  # noqa: BLE001 - callback errors must be code-only
            coordinator.phase = PHASE_RELEASING
            failed, cancelled = await _finish_unwind(coordinator)
            if not failed:
                _remove_if_current(hass, data, coordinator)
            else:
                _show_recovery(hass, coordinator)
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
        if coordinator.phase == PHASE_ACQUIRING:
            raise HomeAssistantError(_ERROR)
        if coordinator.phase == PHASE_RELEASED:
            return
        coordinator.phase = PHASE_RELEASING
        failed, cancelled = await _finish_unwind(coordinator)
        if not failed:
            _remove_if_current(hass, data, coordinator)
        else:
            _show_recovery(hass, coordinator)
    if cancelled:
        raise asyncio.CancelledError
    if failed:
        raise HomeAssistantError(_ERROR)
