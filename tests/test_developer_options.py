"""Actual command scope and Engine fence technical-diagnostics consent and retries."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_command_scope import NOW, harness
from test_command_scope import command_scope as command_scope

from custom_components.family_assistant.domain.developer_diagnostics import configuration


@pytest.fixture
def options(monkeypatch, command_scope):
    util = ModuleType("homeassistant.util")
    util.dt = SimpleNamespace(utcnow=lambda: NOW)
    monkeypatch.setitem(sys.modules, "homeassistant.util", util)
    monkeypatch.setitem(
        sys.modules, "custom_components.family_assistant.command_scope", command_scope
    )
    path = Path(__file__).parents[1] / "custom_components/family_assistant/developer_options.py"
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant._developer_options_test", path
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class Flow:
    def __init__(self, hass, entry, user):
        self.hass, self.config_entry = hass, entry
        self.context = {"user_id": user.id}
        self.fail_response = False

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        if self.fail_response and kwargs["reason"] == "developer_policy_saved":
            raise OSError("PRIVATE_RESPONSE_CANARY")
        return {"type": "abort", **kwargs}


@pytest.mark.asyncio
async def test_default_no_consent_and_exact_commit_response_loss(options, command_scope):
    hass, entry, _runtime, engine, store, user = harness(command_scope)
    flow = Flow(hass, entry, user)
    form = await options.options_step(flow)
    assert form["data_schema"]({}) == {"enabled": False}
    assert store.calls == 0
    flow.fail_response = True
    result = await options.options_step(flow, {"enabled": True})
    assert result["errors"] == {"base": "storage_error"}
    committed = engine.snapshot()
    assert configuration(committed)["generation"] == 2
    calls = store.calls
    flow.fail_response = False
    assert await options.options_step(flow, {"enabled": True}) == {
        "type": "abort",
        "reason": "developer_policy_saved",
    }
    assert engine.snapshot() == committed and store.calls == calls


@pytest.mark.asyncio
async def test_failed_store_retries_original_generation(options, command_scope):
    hass, entry, _runtime, engine, store, user = harness(command_scope)
    flow = Flow(hass, entry, user)
    await options.options_step(flow)
    original = engine._persist

    async def fail(_state):
        raise OSError("PRIVATE_STORE_CANARY")

    engine._persist = fail
    result = await options.options_step(flow, {"enabled": True})
    assert result["errors"] == {"base": "storage_error"}
    operation = flow._developer_operation
    assert not configuration(engine.snapshot())["enabled"]
    engine._persist = original
    result = await options.options_step(flow, {"enabled": True})
    assert result["reason"] == "developer_policy_saved"
    assert flow._developer_operation == operation
    assert configuration(engine.snapshot())["generation"] == 2
    assert store.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["policy", "epoch", "inactive", "user_object", "runtime"])
async def test_changed_scope_or_consent_never_rebases(options, command_scope, changed):
    hass, entry, runtime, engine, _store, user = harness(command_scope)
    flow = Flow(hass, entry, user)
    await options.options_step(flow)
    if changed == "policy":
        await engine.execute(
            "owner",
            "settings.developer_policy",
            {"enabled": True, "expected_generation": 1},
            "another-consent",
            NOW,
        )
    elif changed == "epoch":
        await engine.execute(
            "owner",
            "members.save",
            {"id": "owner", "name": "Changed owner", "role": "owner", "revision": 1},
            "changed-owner",
            NOW,
        )
    elif changed == "inactive":
        user.is_active = False
    elif changed == "user_object":
        hass.auth.user = SimpleNamespace(id=user.id, is_active=True)
    else:
        entry.runtime_data = SimpleNamespace(engine=engine)
        hass.data["family_assistant"]["entries"][entry.entry_id] = entry.runtime_data
    before = engine.snapshot()
    result = await options.options_step(flow, {"enabled": True})
    assert result["type"] == "abort" and result["reason"] in {"conflict", "forbidden"}
    assert engine.snapshot() == before and runtime.notifications == 0


@pytest.mark.asyncio
async def test_old_committed_enable_cannot_claim_success_after_optout(options, command_scope):
    hass, entry, _runtime, engine, _store, user = harness(command_scope)
    flow = Flow(hass, entry, user)
    await options.options_step(flow)
    flow.fail_response = True
    await options.options_step(flow, {"enabled": True})
    flow.fail_response = False
    await engine.execute(
        "owner",
        "settings.developer_policy",
        {"enabled": False, "expected_generation": 2},
        "optout",
        NOW,
    )
    before = engine.snapshot()
    result = await options.options_step(flow, {"enabled": True})
    assert result == {"type": "abort", "reason": "conflict"}
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"enabled": 1}, {"enabled": True, "extra": False}])
async def test_strict_payload(options, command_scope, payload):
    hass, entry, _runtime, engine, store, user = harness(command_scope)
    flow = Flow(hass, entry, user)
    await options.options_step(flow)
    result = await options.options_step(flow, payload)
    assert result == {"type": "abort", "reason": "invalid_field"}
    assert store.calls == 0 and engine.snapshot()["processed"] == {}


@pytest.mark.asyncio
async def test_optout_during_final_authority_read_prevents_stale_success(options, command_scope):
    hass, entry, runtime, engine, _store, user = harness(command_scope)
    flow = Flow(hass, entry, user)
    await options.options_step(flow)
    original_read = hass.auth.async_get_user
    changed = False

    async def read(user_id):
        nonlocal changed
        if not changed and configuration(engine.snapshot())["enabled"]:
            changed = True
            await engine.execute(
                "owner",
                "settings.developer_policy",
                {"enabled": False, "expected_generation": 2},
                "final-read-optout",
                NOW,
            )
        return await original_read(user_id)

    hass.auth.async_get_user = read
    result = await options.options_step(flow, {"enabled": True})
    assert result == {"type": "abort", "reason": "conflict"}
    assert not configuration(engine.snapshot())["enabled"]
    assert runtime.notifications == 0
