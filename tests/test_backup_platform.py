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
    helpers = ModuleType("homeassistant.helpers")
    issue_registry = ModuleType("homeassistant.helpers.issue_registry")
    issues = {}

    class IssueSeverity:
        ERROR = "error"

    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.async_create_issue = lambda _hass, domain, issue_id, **kwargs: (
        issues.__setitem__((domain, issue_id), kwargs)
    )
    issue_registry.async_delete_issue = lambda _hass, domain, issue_id: issues.pop(
        (domain, issue_id), None
    )
    helpers.issue_registry = issue_registry
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.issue_registry", issue_registry)
    sys.modules.pop("custom_components.family_assistant.backup_recovery", None)
    sys.modules.pop("custom_components.family_assistant.backup", None)
    module = importlib.import_module("custom_components.family_assistant.backup")
    module._test_issues = issues
    yield module
    sys.modules.pop("custom_components.family_assistant.backup", None)
    sys.modules.pop("custom_components.family_assistant.backup_recovery", None)


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
    def __init__(self, name, log, *, begin=None, end=None, end_error=False):
        self.name = name
        self.log = log
        self.begin = begin
        self.end = end
        self.end_error = end_error

    async def async_begin_backup(self):
        self.log.append(f"begin:{self.name}")
        if self.begin:
            await self.begin()
        return f"engine:{self.name}"

    async def async_end_backup(self, token):
        self.log.append(f"end:{self.name}:{token}")
        if self.end:
            await self.end()
        if self.end_error:
            raise RuntimeError("synthetic end failure")


def runtime(
    name,
    log,
    *,
    pause=None,
    resume=None,
    begin=None,
    end=None,
    resume_error=False,
    end_error=False,
):
    return SimpleNamespace(
        media=Media(name, log, pause=pause, resume=resume, resume_error=resume_error),
        engine=StubEngine(name, log, begin=begin, end=end, end_error=end_error),
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


async def test_partial_pre_cleanup_failure_enters_recovery(platform):
    log = []

    async def fail():
        raise DomainError("conflict")

    selected = runtime("a", log, begin=fail, resume_error=True)
    instance = hass({"a": selected})
    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_pre_backup(instance)

    coordinator = instance.data["family_assistant"]["backup"]
    assert coordinator.phase == platform.PHASE_RECOVERY
    assert coordinator.leases[0].engine_acquired is False
    assert coordinator.leases[0].media_acquired is True
    assert platform.recovery_identity(instance) == (
        coordinator,
        coordinator.generation,
    )

    selected.media.resume_error = False
    await platform.async_retry_recovery(instance, coordinator, coordinator.generation)
    assert coordinator.released.is_set()
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
    assert coordinator.phase == platform.PHASE_RECOVERY
    assert platform._test_issues == {
        ("family_assistant", "backup_recovery"): {
            "is_fixable": True,
            "is_persistent": False,
            "severity": "error",
            "translation_key": "backup_recovery",
        }
    }

    instance.data["family_assistant"]["entries"]["a"].engine.end_error = False
    instance.data["family_assistant"]["entries"]["b"].media.resume_error = False
    await platform.async_post_backup(instance)
    assert "backup" not in instance.data["family_assistant"]
    assert coordinator.released.is_set()
    assert platform._test_issues == {}


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


async def test_only_failed_release_is_retried_for_exact_generation(platform):
    log = []
    instance = hass(
        {
            "a": runtime("a", log),
            "b": runtime("b", log, end_error=True),
        }
    )
    await platform.async_pre_backup(instance)
    coordinator = instance.data["family_assistant"]["backup"]
    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_post_backup(instance)
    before_retry = list(log)
    assert platform.recovery_identity(instance) == (
        coordinator,
        coordinator.generation,
    )

    instance.data["family_assistant"]["entries"]["b"].engine.end_error = False
    await platform.async_retry_recovery(instance, coordinator, coordinator.generation)
    assert log[len(before_retry) :] == ["end:b:engine:b"]
    assert coordinator.phase == platform.PHASE_RELEASED
    assert coordinator.released.is_set()
    assert "backup" not in instance.data["family_assistant"]


async def test_frozen_or_stale_generation_never_releases(platform):
    log = []
    instance = hass({"a": runtime("a", log)})
    await platform.async_pre_backup(instance)
    coordinator = instance.data["family_assistant"]["backup"]
    assert coordinator.phase == platform.PHASE_FROZEN
    assert platform.recovery_identity(instance) is None

    with pytest.raises(_HomeAssistantError, match="^stale_recovery$"):
        await platform.async_retry_recovery(instance, coordinator, coordinator.generation)
    assert log == ["pause:a", "begin:a"]
    await platform.async_post_backup(instance)


async def test_release_timeout_settles_before_exact_retry(platform, monkeypatch):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def hang():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    log = []
    selected = runtime("a", log, resume=hang)
    instance = hass({"a": selected})
    await platform.async_pre_backup(instance)
    coordinator = instance.data["family_assistant"]["backup"]
    monkeypatch.setattr(platform, "BACKUP_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_post_backup(instance)
    assert entered.is_set() and cancelled.is_set()
    assert coordinator.phase == platform.PHASE_RECOVERY
    assert coordinator.leases[0].engine_acquired is False
    assert coordinator.leases[0].media_acquired is True

    selected.media.resume = None
    await platform.async_retry_recovery(instance, coordinator, coordinator.generation)
    assert log[-1] == "resume:a:media:a"
    assert coordinator.released.is_set()


async def test_per_release_timeout_still_attempts_later_owned_leases(platform, monkeypatch):
    cancelled = asyncio.Event()

    async def hang():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    log = []
    instance = hass(
        {
            "a": runtime("a", log),
            "b": runtime("b", log, end=hang),
        }
    )
    await platform.async_pre_backup(instance)
    coordinator = instance.data["family_assistant"]["backup"]
    monkeypatch.setattr(platform, "RELEASE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(platform, "BACKUP_TIMEOUT_SECONDS", 1)

    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_post_backup(instance)

    assert cancelled.is_set()
    assert log[4:] == [
        "end:b:engine:b",
        "resume:b:media:b",
        "end:a:engine:a",
        "resume:a:media:a",
    ]
    assert coordinator.leases[1].engine_acquired is True
    assert coordinator.leases[1].media_acquired is False
    assert coordinator.leases[0].engine_acquired is False
    assert coordinator.leases[0].media_acquired is False

    instance.data["family_assistant"]["entries"]["b"].engine.end = None
    await platform.async_retry_recovery(instance, coordinator, coordinator.generation)
    assert coordinator.released.is_set()


@pytest.mark.parametrize("component", ["engine", "media"])
async def test_owned_release_cancelled_error_becomes_recoverable(platform, component):
    async def cancel_itself():
        raise asyncio.CancelledError

    log = []
    selected = runtime(
        "a",
        log,
        end=cancel_itself if component == "engine" else None,
        resume=cancel_itself if component == "media" else None,
    )
    instance = hass({"a": selected})
    await platform.async_pre_backup(instance)
    coordinator = instance.data["family_assistant"]["backup"]

    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_post_backup(instance)
    assert coordinator.phase == platform.PHASE_RECOVERY
    assert coordinator.leases[0].engine_acquired is (component == "engine")
    assert coordinator.leases[0].media_acquired is (component == "media")
    assert not coordinator.released.is_set()

    selected.engine.end = None
    selected.media.resume = None
    await platform.async_retry_recovery(instance, coordinator, coordinator.generation)
    assert coordinator.released.is_set()


async def test_issue_registry_failure_never_clears_or_replaces_safety_error(platform, monkeypatch):
    issue_registry = sys.modules["homeassistant.helpers.issue_registry"]

    def fail_visibility(*_args, **_kwargs):
        raise RuntimeError("synthetic issue registry failure")

    monkeypatch.setattr(issue_registry, "async_create_issue", fail_visibility)
    log = []
    instance = hass({"a": runtime("a", log, end_error=True)})
    await platform.async_pre_backup(instance)
    with pytest.raises(_HomeAssistantError, match="^backup_unavailable$"):
        await platform.async_post_backup(instance)
    coordinator = instance.data["family_assistant"]["backup"]
    assert coordinator.phase == platform.PHASE_RECOVERY
    assert coordinator.issue_created is False
    assert not coordinator.released.is_set()

    instance.data["family_assistant"]["entries"]["a"].engine.end_error = False
    await platform.async_retry_recovery(instance, coordinator, coordinator.generation)
