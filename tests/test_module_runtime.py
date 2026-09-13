"""Module reconciliation wiring complements actual HA transport acceptance."""

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant.module_runtime import reconcile, signature, watch


@pytest.fixture
def harness(engine, monkeypatch):
    calls = []
    adapter = ModuleType("custom_components.family_assistant.runtime")

    async def stop_chat(runtime):
        calls.append("stop_chat")
        runtime.chat = None

    async def stop_articles(runtime):
        calls.append("stop_articles")

    def assistant(_hass, entry):
        calls.append("assistant")
        entry.runtime_data.chat = (
            object() if "conversation" in signature(entry.runtime_data) else None
        )

    async def network(_hass, _entry):
        calls.append("network")

    async def school(_hass, _entry):
        calls.append("school")

    adapter.async_stop_chat = stop_chat
    adapter.async_stop_articles = stop_articles
    adapter.async_configure_assistant = assistant
    adapter.async_configure_network = network
    adapter.async_configure_online_school = school
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    runtime = SimpleNamespace(
        engine=engine,
        listeners=set(),
        module_task=None,
        module_signature=None,
        options_lock=asyncio.Lock(),
        health={},
        chat=None,
    )
    runtime.updated = lambda: [listener() for listener in tuple(runtime.listeners)]
    entry = SimpleNamespace(entry_id="synthetic", runtime_data=runtime)
    hass = SimpleNamespace(
        data={"family_assistant": {"entries": {entry.entry_id: runtime}}},
        async_create_task=lambda task, _name: asyncio.create_task(task),
    )
    watch(hass, entry, runtime)
    return hass, entry, runtime, calls


async def set_modules(engine, modules, now):
    await engine.execute(
        "owner",
        "settings.save",
        {
            "name": "Synthetic",
            "language": "en",
            "modules": modules,
        },
        "modules-" + "-".join(modules),
        now,
    )


async def test_module_switch_only_reconciles_affected_services(harness, now):
    hass, entry, runtime, calls = harness
    original = signature(runtime)
    await set_modules(runtime.engine, sorted(original | {"conversation"}), now)
    runtime.updated()
    task = runtime.module_task
    runtime.updated()
    assert runtime.module_task is task
    await task
    assert calls == ["stop_chat", "stop_articles", "assistant"]
    assert runtime.chat is not None and runtime.module_task is None
    calls.clear()
    await set_modules(runtime.engine, sorted(signature(runtime) | {"mikrotik"}), now)
    await reconcile(hass, entry, runtime)
    assert calls == ["network"]


async def test_backup_wait_rechecks_replaced_runtime(harness, now):
    hass, entry, runtime, calls = harness
    await set_modules(runtime.engine, sorted(signature(runtime) | {"conversation"}), now)
    released = asyncio.Event()
    hass.data["family_assistant"]["backup"] = SimpleNamespace(released=released)
    task = asyncio.create_task(reconcile(hass, entry, runtime))
    await asyncio.sleep(0)
    assert not task.done() and not calls
    hass.data["family_assistant"]["entries"][entry.entry_id] = object()
    released.set()
    await task
    assert not calls


async def test_failure_is_reported_without_busy_retry(harness, monkeypatch, now):
    hass, entry, runtime, calls = harness
    adapter = sys.modules["custom_components.family_assistant.runtime"]

    async def fail(_hass, _entry):
        calls.append("failed")
        raise OSError("synthetic local configuration failure")

    monkeypatch.setattr(adapter, "async_configure_network", fail)
    await set_modules(runtime.engine, sorted(signature(runtime) | {"mikrotik"}), now)
    runtime.updated()
    await runtime.module_task
    assert runtime.health["module_settings"] == "not_ready"
    assert runtime.module_task is None and calls == ["failed"]
    runtime.updated()
    assert runtime.module_task is None
