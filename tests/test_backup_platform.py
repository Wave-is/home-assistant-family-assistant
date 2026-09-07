"""Backup platform quiescing tests; no backup archive or live HA is used."""

from __future__ import annotations

import asyncio
import importlib
import sys
from copy import deepcopy
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.media_storage import MediaStorage


class _HomeAssistantError(Exception):
    pass


@pytest.fixture
def platform(monkeypatch):
    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = _HomeAssistantError
    homeassistant = ModuleType("homeassistant")
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions)
    sys.modules.pop("custom_components.family_assistant.backup", None)
    module = importlib.import_module("custom_components.family_assistant.backup")
    yield module
    sys.modules.pop("custom_components.family_assistant.backup", None)


class Media:
    def __init__(self, name, log, *, pause=None, resume=None, resume_error=False):
        self.name = name
        self.log = log
        self.pause = pause
        self.resume = resume
        self.resume_error = resume_error

    async def async_pause_backup(self):
        self.log.append(f"pause:{self.name}")
        if self.pause:
            await self.pause()
        return f"media:{self.name}"

    async def async_resume_backup(self, token):
        self.log.append(f"resume:{self.name}:{token}")
        if self.resume:
            await self.resume()
        if self.resume_error:
            raise RuntimeError("synthetic resume failure")


class StubEngine:
    def __init__(self, name, log, *, begin=None, end_error=False):
        self.name = name
        self.log = log
        self.begin = begin
        self.end_error = end_error

    async def async_begin_backup(self):
        self.log.append(f"begin:{self.name}")
        if self.begin:
            await self.begin()
        return f"engine:{self.name}"

    async def async_end_backup(self, token):
        self.log.append(f"end:{self.name}:{token}")
        if self.end_error:
            raise RuntimeError("synthetic end failure")


def runtime(
    name,
    log,
    *,
    pause=None,
    resume=None,
    begin=None,
    resume_error=False,
    end_error=False,
):
    return SimpleNamespace(
        media=Media(name, log, pause=pause, resume=resume, resume_error=resume_error),
        engine=StubEngine(name, log, begin=begin, end_error=end_error),
    )


def hass(entries=None):
    return SimpleNamespace(data={"family_assistant": {"entries": entries or {}}})


async def test_deterministic_acquire_and_reverse_release(platform):
    log = []
    instance = hass()
    instance.data["family_assistant"]["entries"] = {
        "z-entry": runtime("z", log),
        "a-entry": runtime("a", log),
    }

    await platform.async_pre_backup(instance)
    assert "backup" in instance.data["family_assistant"]
    coordinator = instance.data["family_assistant"]["backup"]
    assert not coordinator.released.is_set()
    assert log == ["pause:a", "begin:a", "pause:z", "begin:z"]

    await platform.async_post_backup(instance)
    assert log[4:] == [
        "end:z:engine:z",
        "resume:z:media:z",
        "end:a:engine:a",
        "resume:a:media:a",
    ]
    assert "backup" not in instance.data["family_assistant"]
    assert coordinator.released.is_set()
    await platform.async_post_backup(instance)
    assert len(log) == 8


async def test_marker_precedes_setup_barrier_and_snapshot_includes_drained_setup(platform):
    log = []
    instance = hass({"a": runtime("a", log)})
    setup_lock = asyncio.Lock()
    instance.data["family_assistant"]["setup_lock"] = setup_lock
    await setup_lock.acquire()

    pre = asyncio.create_task(platform.async_pre_backup(instance))
    await asyncio.sleep(0)
    assert "backup" in instance.data["family_assistant"]
    assert log == []

    # This represents a setup which entered the lock before the backup marker and
    # completes its initial persistence plus registration before releasing it.
    instance.data["family_assistant"]["entries"]["b"] = runtime("b", log)
    setup_lock.release()
    await pre
    assert log == ["pause:a", "begin:a", "pause:b", "begin:b"]

    # A later setup observes the marker while holding the same barrier and must not
    # register a runtime outside the frozen snapshot.
    async with setup_lock:
        assert "backup" in instance.data["family_assistant"]
    await platform.async_post_backup(instance)


async def test_partial_engine_failure_unwinds_every_acquired_piece(platform):
    log = []

    async def fail():
        raise DomainError("conflict")

    instance = hass(
        {
            "a": runtime("a", log),
            "b": runtime("b", log, begin=fail),
        }
    )
    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_pre_backup(instance)

    assert log == [
        "pause:a",
        "begin:a",
        "pause:b",
        "begin:b",
        "resume:b:media:b",
        "end:a:engine:a",
        "resume:a:media:a",
    ]
    assert "backup" not in instance.data["family_assistant"]


async def test_timeout_is_bounded_and_unwinds(platform, monkeypatch):
    released = asyncio.Event()
    log = []

    async def hang():
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    monkeypatch.setattr(platform, "BACKUP_TIMEOUT_SECONDS", 0.01)
    instance = hass({"a": runtime("a", log, pause=hang)})
    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_pre_backup(instance)
    assert released.is_set()
    assert log == ["pause:a"]
    assert "backup" not in instance.data["family_assistant"]


async def test_timeout_while_draining_setup_lock_clears_marker(platform, monkeypatch):
    instance = hass()
    setup_lock = asyncio.Lock()
    instance.data["family_assistant"]["setup_lock"] = setup_lock
    await setup_lock.acquire()
    monkeypatch.setattr(platform, "BACKUP_TIMEOUT_SECONDS", 0.01)
    try:
        with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
            await platform.async_pre_backup(instance)
    finally:
        setup_lock.release()
    assert "backup" not in instance.data["family_assistant"]


async def test_external_cancellation_releases_partial_lease_and_propagates(platform):
    entered = asyncio.Event()
    log = []

    async def hang():
        entered.set()
        await asyncio.Event().wait()

    instance = hass({"a": runtime("a", log, begin=hang)})
    task = asyncio.create_task(platform.async_pre_backup(instance))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert log == ["pause:a", "begin:a", "resume:a:media:a"]
    assert "backup" not in instance.data["family_assistant"]


async def test_cancellation_during_error_unwind_is_not_replaced(platform):
    entered = asyncio.Event()
    release = asyncio.Event()
    log = []

    async def fail():
        raise DomainError("conflict")

    async def wait_to_resume():
        entered.set()
        await release.wait()

    instance = hass({"a": runtime("a", log, begin=fail, resume=wait_to_resume)})
    task = asyncio.create_task(platform.async_pre_backup(instance))
    await entered.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "backup" not in instance.data["family_assistant"]


async def test_overlapping_pre_rejected_and_post_cannot_thaw_early(platform):
    entered = asyncio.Event()
    release = asyncio.Event()
    log = []

    async def pause():
        entered.set()
        await release.wait()

    instance = hass({"a": runtime("a", log, pause=pause)})
    first = asyncio.create_task(platform.async_pre_backup(instance))
    await entered.wait()
    generation = instance.data["family_assistant"]["backup"].generation

    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_pre_backup(instance)
    assert instance.data["family_assistant"]["backup"].generation is generation

    post = asyncio.create_task(platform.async_post_backup(instance))
    await asyncio.sleep(0)
    assert not post.done()
    assert not any(item.startswith("resume:") for item in log)
    release.set()
    await first
    await post
    assert log == ["pause:a", "begin:a", "end:a:engine:a", "resume:a:media:a"]


async def test_post_attempts_all_releases_before_fixed_error(platform):
    log = []
    instance = hass(
        {
            "a": runtime("a", log, end_error=True),
            "b": runtime("b", log, resume_error=True),
        }
    )
    await platform.async_pre_backup(instance)
    coordinator = instance.data["family_assistant"]["backup"]

    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_post_backup(instance)
    assert log[4:] == [
        "end:b:engine:b",
        "resume:b:media:b",
        "end:a:engine:a",
        "resume:a:media:a",
    ]
    assert "backup" in instance.data["family_assistant"]
    assert not coordinator.released.is_set()

    instance.data["family_assistant"]["entries"]["a"].engine.end_error = False
    instance.data["family_assistant"]["entries"]["b"].media.resume_error = False
    await platform.async_post_backup(instance)
    assert "backup" not in instance.data["family_assistant"]
    assert coordinator.released.is_set()


async def test_actual_engine_and_media_are_frozen_until_post(platform, tmp_path):
    writes = []

    async def persist(state):
        writes.append(deepcopy(state))

    engine = Engine(new_state("owner-ha", "Synthetic household"), persist)
    storage = MediaStorage(engine, tmp_path, lambda: datetime.now(UTC))
    instance = hass({"entry": SimpleNamespace(engine=engine, media=storage)})

    await platform.async_pre_backup(instance)
    with pytest.raises(DomainError, match="backup_in_progress"):
        await engine.system_update("synthetic", datetime.now(UTC), lambda ctx: None)
    with pytest.raises(DomainError, match="media_unavailable"):
        await storage.async_pause_backup()
    await platform.async_post_backup(instance)
    assert await engine.system_update("synthetic", datetime.now(UTC), lambda ctx: {"ok": True}) == {
        "ok": True
    }
    token = await storage.async_pause_backup()
    await storage.async_resume_backup(token)
    await storage.stop()
    assert writes == []
