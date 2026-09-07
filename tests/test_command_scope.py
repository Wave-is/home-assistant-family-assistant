"""Generic HA command scopes fence queued writes to one identity/runtime epoch."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "family_assistant"
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def command_scope(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigEntryState(Enum):
        LOADED = "loaded"
        NOT_LOADED = "not_loaded"

    config_entries.ConfigEntryState = ConfigEntryState
    homeassistant.config_entries = config_entries
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    name = "custom_components.family_assistant._command_scope_test"
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "command_scope.py")
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    assert spec.loader is not None
    spec.loader.exec_module(loaded)
    return loaded


class Store:
    def __init__(self) -> None:
        self.calls = 0
        self.value = None
        self.block = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def save(self, state) -> None:
        self.calls += 1
        if self.block:
            self.entered.set()
            await self.release.wait()
        self.value = deepcopy(state)


class Auth:
    def __init__(self, user) -> None:
        self.user = user
        self.entered = asyncio.Event()
        self.release = None

    async def async_get_user(self, user_id):
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        return self.user if self.user is not None and self.user.id == user_id else None


class Runtime:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.notifications = 0

    def updated(self) -> None:
        self.notifications += 1


def harness(command_scope, *, store=None):
    store = store or Store()
    engine = Engine(new_state("ha-owner", "Scope household"), store.save)
    runtime = Runtime(engine)
    entry = SimpleNamespace(
        entry_id="scope-entry",
        domain="family_assistant",
        state=command_scope.ConfigEntryState.LOADED,
        runtime_data=runtime,
    )
    user = SimpleNamespace(id="ha-owner", is_active=True)
    auth = Auth(user)
    manager = SimpleNamespace(
        async_get_entry=lambda selected: entry if selected == entry.entry_id else None
    )
    hass = SimpleNamespace(
        auth=auth,
        config_entries=manager,
        data={"family_assistant": {"entries": {entry.entry_id: runtime}}},
    )
    return hass, entry, runtime, engine, store, user


@pytest.mark.asyncio
async def test_exact_self_profile_receipt_advances_only_its_own_scope(command_scope):
    hass, entry, runtime, engine, _store, user = harness(command_scope)
    scope = await command_scope.capture(hass, entry.entry_id, user.id, user)
    payload = {
        "id": scope.actor,
        "revision": scope.actor_revision,
        "name": "Reviewed owner name",
        "role": "owner",
        "language": "uk",
    }
    result = await engine.execute(
        scope.actor, "members.save", payload, "self-profile", NOW, guard=scope.guard
    )
    updated = await scope.after_execute("members.save", payload, "self-profile", result)
    assert updated.actor_revision == scope.actor_revision + 1
    assert updated.language == "uk" and updated.user_id == scope.user_id
    updated.notify()
    assert runtime.notifications == 1
    with pytest.raises(DomainError, match="conflict"):
        scope.guard(engine.snapshot())
    replay = await engine.execute(
        updated.actor, "members.save", payload, "self-profile", NOW, guard=updated.guard
    )
    assert replay == result
    assert await updated.after_execute("members.save", payload, "self-profile", replay) is updated


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    ["unrelated", "receipt", "payload", "result", "later_edit", "role", "binding", "inactive"],
)
async def test_self_profile_exception_cannot_rebase_unrelated_or_changed_authority(
    command_scope, drift
):
    hass, entry, _runtime, engine, _store, user = harness(command_scope)
    scope = await command_scope.capture(hass, entry.entry_id, user.id, user)
    payload = {
        "id": scope.actor,
        "revision": scope.actor_revision,
        "name": "Reviewed owner name",
        "role": "owner",
    }
    result = await engine.execute(
        scope.actor, "members.save", payload, "self-profile", NOW, guard=scope.guard
    )
    action, operation = "members.save", "self-profile"
    if drift == "unrelated":
        action = "shopping.add"
    elif drift == "receipt":
        operation = "not-the-receipt"
    elif drift == "payload":
        payload = {**payload, "name": "Unreviewed owner name"}
    elif drift == "result":
        result = {**result, "name": "Invented result"}
    else:

        def change(ctx):
            member = ctx.state["members"][scope.actor]
            if drift == "later_edit":
                member["revision"] += 1
            elif drift == "role":
                member["role"] = "parent"
            elif drift == "binding":
                member["ha_user_id"] = "another-user"
            else:
                member["active"] = False

        await engine.system_update("synthetic_scope_drift", NOW, change)
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await scope.after_execute(action, payload, operation, result)
    assert engine.snapshot() == before


async def assert_error(awaitable, code: str) -> None:
    with pytest.raises(DomainError) as caught:
        await awaitable
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_valid_scope_writes_notifies_and_exact_replay_does_not_write_again(
    command_scope,
) -> None:
    hass, entry, runtime, engine, store, user = harness(command_scope)
    scope = await command_scope.capture(hass, entry.entry_id, user.id, user)
    assert (scope.actor, scope.actor_revision, scope.role, scope.language) == (
        "owner",
        1,
        "owner",
        "en",
    )
    await scope.check()
    result = await scope.engine.execute(
        scope.actor,
        "shopping.add",
        {"name": "Scoped item"},
        "scoped-operation",
        NOW,
        guard=scope.guard,
    )
    await scope.check()
    scope.notify()
    assert runtime.notifications == 1
    calls = store.calls
    replay = await scope.engine.execute(
        scope.actor,
        "shopping.add",
        {"name": "Scoped item"},
        "scoped-operation",
        NOW,
        guard=scope.guard,
    )
    assert replay == result and store.calls == calls
    assert len(engine.snapshot()["shopping"]) == 1


@pytest.mark.asyncio
async def test_member_epoch_change_commits_before_queued_scope_and_blocks_its_write(
    command_scope,
) -> None:
    store = Store()
    hass, entry, _runtime, engine, _store, user = harness(command_scope, store=store)
    scope = await command_scope.capture(hass, entry.entry_id, user.id, user)
    store.block = True
    epoch_change = asyncio.create_task(
        engine.execute(
            "owner",
            "members.save",
            {"id": "owner", "revision": 1, "name": "Rebound owner", "role": "owner"},
            "advance-owner-epoch",
            NOW,
        )
    )
    await asyncio.wait_for(store.entered.wait(), 1)
    stale = asyncio.create_task(
        engine.execute(
            scope.actor,
            "shopping.add",
            {"name": "Must not be added"},
            "queued-stale-command",
            NOW,
            guard=scope.guard,
        )
    )
    await asyncio.sleep(0)
    store.release.set()
    await epoch_change
    await assert_error(stale, "conflict")
    assert not engine.snapshot()["shopping"]
    assert store.calls == 1


@pytest.mark.asyncio
async def test_user_revocation_and_runtime_replacement_fail_closed_without_writes(
    command_scope,
) -> None:
    hass, entry, runtime, engine, store, user = harness(command_scope)
    scope = await command_scope.capture(hass, entry.entry_id, user.id, user)
    store.block = True
    holder = asyncio.create_task(
        engine.execute(
            "owner",
            "shopping.add",
            {"name": "Already admitted item"},
            "active-user-holder",
            NOW,
        )
    )
    await asyncio.wait_for(store.entered.wait(), 1)
    stale = asyncio.create_task(
        engine.execute(
            scope.actor,
            "shopping.add",
            {"name": "Revoked user item"},
            "revoked-user",
            NOW,
            guard=scope.guard,
        )
    )
    await asyncio.sleep(0)
    user.is_active = False
    store.release.set()
    await holder
    await assert_error(stale, "forbidden")
    await assert_error(scope.check(), "forbidden")
    assert store.calls == 1
    assert {item["name"] for item in engine.snapshot()["shopping"].values()} == {
        "Already admitted item"
    }

    user.is_active = True
    replacement = Runtime(Engine(engine.snapshot(), Store().save))
    entry.runtime_data = replacement
    hass.data["family_assistant"]["entries"][entry.entry_id] = replacement
    await assert_error(scope.check(), "conflict")
    with pytest.raises(DomainError) as caught:
        scope.notify()
    assert caught.value.code == "conflict"
    assert runtime.notifications == 0


@pytest.mark.asyncio
async def test_same_id_ha_user_object_replacement_invalidates_scope(command_scope) -> None:
    hass, entry, _runtime, _engine, _store, user = harness(command_scope)
    scope = await command_scope.capture(hass, entry.entry_id, user.id, user)
    hass.auth.user = SimpleNamespace(id=user.id, is_active=True)
    await assert_error(scope.check(), "conflict")


@pytest.mark.asyncio
async def test_capture_rechecks_runtime_after_await_and_connection_identity(command_scope) -> None:
    hass, entry, _runtime, engine, _store, user = harness(command_scope)
    gate = asyncio.Event()
    hass.auth.release = gate
    pending = asyncio.create_task(command_scope.capture(hass, entry.entry_id, user.id, user))
    await asyncio.wait_for(hass.auth.entered.wait(), 1)
    replacement = Runtime(Engine(engine.snapshot(), Store().save))
    entry.runtime_data = replacement
    hass.data["family_assistant"]["entries"][entry.entry_id] = replacement
    gate.set()
    await assert_error(pending, "conflict")

    wrong = SimpleNamespace(id="different-user", is_active=True)
    await assert_error(command_scope.capture(hass, entry.entry_id, user.id, wrong), "forbidden")


@pytest.mark.asyncio
async def test_reload_invalidates_old_scope_but_fresh_scope_replays_persisted_receipt(
    command_scope,
) -> None:
    hass, entry, runtime, engine, store, user = harness(command_scope)
    old = await command_scope.capture(hass, entry.entry_id, user.id, user)
    result = await engine.execute(
        old.actor,
        "shopping.add",
        {"name": "Persisted replay item"},
        "persisted-scope-replay",
        NOW,
        guard=old.guard,
    )
    replacement_store = Store()
    replacement_engine = Engine(deepcopy(store.value), replacement_store.save)
    replacement = Runtime(replacement_engine)
    entry.runtime_data = replacement
    hass.data["family_assistant"]["entries"][entry.entry_id] = replacement
    await engine.async_close()
    await assert_error(old.check(), "conflict")

    fresh = await command_scope.capture(hass, entry.entry_id, user.id, user)
    replay = await fresh.engine.execute(
        fresh.actor,
        "shopping.add",
        {"name": "Persisted replay item"},
        "persisted-scope-replay",
        NOW,
        guard=fresh.guard,
    )
    assert replay == result
    assert replacement_store.calls == 0
    assert len(replacement_engine.snapshot()["shopping"]) == 1
    assert runtime.notifications == 0
