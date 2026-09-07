"""Telegram commands remain bound to the sender and adapter that reviewed them."""

from __future__ import annotations

import asyncio
import importlib
import sys
from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant.const import DOMAIN
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError


class ConfigEntryState(Enum):
    LOADED = "loaded"


@pytest.fixture
def manager_module(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntryState = ConfigEntryState
    helpers = ModuleType("homeassistant.helpers")
    issue_registry = ModuleType("homeassistant.helpers.issue_registry")
    issue_registry.IssueSeverity = SimpleNamespace(WARNING="warning")
    issue_registry.async_create_issue = lambda *_args, **_kwargs: None
    issue_registry.async_delete_issue = lambda *_args, **_kwargs: None
    util = ModuleType("homeassistant.util")
    dt = ModuleType("homeassistant.util.dt")
    dt.utcnow = lambda: NOW
    dt.parse_datetime = datetime.fromisoformat
    util.dt = dt
    helpers.issue_registry = issue_registry
    homeassistant.config_entries = config_entries
    homeassistant.helpers = helpers
    homeassistant.util = util
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.issue_registry", issue_registry)
    monkeypatch.setitem(sys.modules, "homeassistant.util", util)
    monkeypatch.setitem(sys.modules, "homeassistant.util.dt", dt)
    sys.modules.pop("custom_components.family_assistant.telegram.manager", None)
    module = importlib.import_module("custom_components.family_assistant.telegram.manager")
    yield module
    sys.modules.pop("custom_components.family_assistant.telegram.manager", None)


NOW = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
BOT = {"id": 9001, "username": "synthetic_family_bot"}


class Runtime(SimpleNamespace):
    def __init__(self, engine):
        super().__init__(
            engine=engine,
            health={},
            telegram=None,
            assistant=None,
            assistant_revision="",
            assistant_config_digest="",
        )

    def updated(self):
        return None


class BlockingStore:
    def __init__(self):
        self.value = None
        self.block = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def save(self, state):
        if self.block:
            self.started.set()
            await self.release.wait()
        self.value = deepcopy(state)


class Client:
    def __init__(self):
        self.calls = []

    async def call(self, method, data):
        self.calls.append((method, deepcopy(data)))
        return {"message_id": 1}


class ConfigEntries:
    def __init__(self, entry):
        self.entry = entry

    def async_get_entry(self, entry_id):
        return self.entry if self.entry.entry_id == entry_id else None


class Hass:
    def __init__(self, entry, runtime):
        self.config_entries = ConfigEntries(entry)
        self.data = {DOMAIN: {"entries": {entry.entry_id: runtime}}}


def fixture(manager_module):
    state = new_state("owner-ha", "Synthetic household")
    state["settings"]["modules"].append("conversation")
    state["members"]["owner"]["telegram_id"] = 101
    state["telegram"]["group_id"] = -101
    store = BlockingStore()
    engine = Engine(state, store.save)
    runtime = Runtime(engine)
    entry = SimpleNamespace(
        entry_id="synthetic-entry",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        options={"telegram": {"bots": [BOT]}, "conversation": {}},
        runtime_data=runtime,
    )
    hass = Hass(entry, runtime)
    client = Client()
    manager = manager_module.TelegramManager(hass, entry, runtime, client, BOT)
    runtime.telegram = manager
    return engine, store, entry, runtime, manager, client


def update(update_id=10, *, group=False, text="/buy Bread | 1 | pc"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": 101, "is_bot": False},
            "chat": {"id": -101 if group else 101, "type": "supergroup" if group else "private"},
            "text": text,
            "date": int(NOW.timestamp()),
        },
    }


async def blocked_update(engine, store, change):
    store.block = True
    task = asyncio.create_task(engine.system_update("identity_change", NOW, change))
    await asyncio.wait_for(store.started.wait(), 1)
    return task


@pytest.mark.asyncio
async def test_member_rebind_committing_ahead_of_command_rejects_locked_mutation(
    monkeypatch, manager_module
):
    engine, store, _entry, _runtime, manager, client = fixture(manager_module)
    monkeypatch.setattr(
        "custom_components.family_assistant.telegram.manager.dt_util.utcnow", lambda: NOW
    )

    def rebind(ctx):
        ctx.state["members"]["owner"]["revision"] += 1

    rebind_task = await blocked_update(engine, store, rebind)
    command_task = asyncio.create_task(manager.process(update()))
    await asyncio.sleep(0)
    store.release.set()
    await rebind_task
    with pytest.raises(DomainError, match="forbidden"):
        await command_task

    state = engine.snapshot()
    assert state["shopping"] == {}
    assert state["outbox"] == {}
    assert state["telegram"].get("offsets", {}) == {}
    assert client.calls == []


@pytest.mark.asyncio
async def test_group_binding_change_rejects_command_reply_and_offset(monkeypatch, manager_module):
    engine, store, _entry, _runtime, manager, client = fixture(manager_module)
    monkeypatch.setattr(
        "custom_components.family_assistant.telegram.manager.dt_util.utcnow", lambda: NOW
    )

    def move_group(ctx):
        ctx.state["telegram"]["group_id"] = -202

    move_task = await blocked_update(engine, store, move_group)
    command_task = asyncio.create_task(manager.process(update(group=True)))
    await asyncio.sleep(0)
    store.release.set()
    await move_task
    with pytest.raises(DomainError, match="forbidden"):
        await command_task

    assert engine.snapshot()["shopping"] == {}
    assert engine.snapshot()["outbox"] == {}
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["manager", "client", "options", "runtime"])
async def test_adapter_drift_while_command_waits_is_fail_closed(monkeypatch, manager_module, drift):
    engine, store, entry, runtime, manager, client = fixture(manager_module)
    monkeypatch.setattr(
        "custom_components.family_assistant.telegram.manager.dt_util.utcnow", lambda: NOW
    )

    def hold(ctx):
        ctx.state["telegram"].setdefault("offsets", {})["unrelated"] = 1

    hold_task = await blocked_update(engine, store, hold)
    command_task = asyncio.create_task(manager.process(update()))
    await asyncio.sleep(0)
    if drift == "manager":
        runtime.telegram = object()
    elif drift == "client":
        manager.client = Client()
    elif drift == "options":
        entry.options = {**entry.options, "telegram": {"bots": [{**BOT, "username": "changed"}]}}
    else:
        manager.hass.data[DOMAIN]["entries"][entry.entry_id] = Runtime(engine)
    store.release.set()
    await hold_task
    with pytest.raises(DomainError, match="forbidden"):
        await command_task

    assert engine.snapshot()["shopping"] == {}
    assert engine.snapshot()["outbox"] == {}
    assert client.calls == []


@pytest.mark.asyncio
async def test_successful_direct_command_records_one_action_reply_and_offset(
    monkeypatch, manager_module
):
    engine, _store, _entry, _runtime, manager, client = fixture(manager_module)
    monkeypatch.setattr(
        "custom_components.family_assistant.telegram.manager.dt_util.utcnow", lambda: NOW
    )
    await manager.process(update())
    state = engine.snapshot()
    assert len(state["shopping"]) == 1
    assert (
        len([event for event in state["outbox"].values() if event["key"] == "telegram_reply"]) == 1
    )
    assert state["telegram"]["offsets"][str(BOT["id"])] == 11
    assert client.calls == []


@pytest.mark.asyncio
async def test_old_processed_receipt_not_replayed_after_member_epoch_change(
    monkeypatch, manager_module
):
    engine, _store, _entry, _runtime, manager, _client = fixture(manager_module)
    monkeypatch.setattr(
        "custom_components.family_assistant.telegram.manager.dt_util.utcnow", lambda: NOW
    )
    await manager.process(update())
    before = engine.snapshot()

    def revoke(ctx):
        ctx.state["members"]["owner"]["revision"] += 1

    await engine.system_update("identity_change", NOW, revoke)
    await manager.process(update())
    after = engine.snapshot()
    assert after["shopping"] == before["shopping"]
    assert after["outbox"] == before["outbox"]


@pytest.mark.asyncio
async def test_provider_completion_after_sender_rebind_is_cancelled_without_reply(
    monkeypatch, manager_module
):
    engine, _store, entry, runtime, manager, _client = fixture(manager_module)
    monkeypatch.setattr(
        "custom_components.family_assistant.telegram.manager.dt_util.utcnow", lambda: NOW
    )
    started = asyncio.Event()
    release = asyncio.Event()

    class Cascade:
        async def generate(self, _messages, _schema, validate, *, scope_check=None):
            started.set()
            await release.wait()
            if scope_check is not None:
                scope_check()
            return validate({"kind": "answer", "text": "private model result"})

    runtime.assistant_revision = "a" * 32
    runtime.assistant_config_digest = manager_module.conversation_digest(
        entry.options["conversation"]
    )
    runtime.assistant = manager_module.Assistant(engine, Cascade())
    await manager.jobs.enqueue(
        "owner",
        "synthetic inference",
        "tg:provider-race",
        NOW,
        [],
        bot_id=BOT["id"],
        chat_id=101,
        reply_to=None,
    )
    worker = asyncio.create_task(manager._conversations())
    try:
        await asyncio.wait_for(started.wait(), 1)

        def rebind(ctx):
            ctx.state["members"]["owner"]["revision"] += 1

        await engine.system_update("identity_change", NOW, rebind)
        release.set()
        async with asyncio.timeout(3):
            while engine.snapshot()["assistant_jobs"]["tg:provider-race"]["status"] == "pending":
                await asyncio.sleep(0.01)
        state = engine.snapshot()
        assert state["assistant_jobs"]["tg:provider-race"]["status"] == "cancelled"
        assert not any(
            event["id"].startswith("tg:provider-race:model-result:")
            for event in state["outbox"].values()
        )
    finally:
        release.set()
        manager._stopped = True
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
