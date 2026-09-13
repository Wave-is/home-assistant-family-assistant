"""Actual runtime/Cascade/native adapter ordering; synthetic HTTP and HA only."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_ha_agent_provider import _setup_fixture, ha_modules  # noqa: F401

from custom_components.family_assistant.assistant import plans, provider
from custom_components.family_assistant.assistant.provider import ActorRequest, Ollama
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def configured(ha_modules, monkeypatch, engine, now):  # noqa: F811
    """Load real runtime with the same HA boundary used by native-agent unit tests."""
    ha_modules.ha_const.Platform = SimpleNamespace(
        SENSOR="sensor", CONVERSATION="conversation", CALENDAR="calendar"
    )
    core = ha_modules.homeassistant.core
    core.SupportsResponse = SimpleNamespace(ONLY="only")
    core.callback = lambda function: function
    exceptions = ha_modules.homeassistant.exceptions
    exceptions.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    storage = ModuleType("homeassistant.helpers.storage")
    storage.Store = object
    util = ModuleType("homeassistant.util")
    util.dt = SimpleNamespace(utcnow=lambda: now)
    http = ModuleType("homeassistant.helpers.aiohttp_client")
    sessions = []
    session = object()
    http.async_get_clientsession = lambda hass: sessions.append(hass) or session
    for name, module in ((storage.__name__, storage), (util.__name__, util), (http.__name__, http)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(
        sys.modules,
        "custom_components.family_assistant.assistant.ha_agent_provider",
        sys.modules[ha_modules.HAConversationAgent.__module__],
    )
    name = "custom_components.family_assistant._provider_order_runtime"
    path = Path(__file__).resolve().parents[1] / "custom_components/family_assistant/runtime.py"
    spec = importlib.util.spec_from_file_location(name, path)
    runtime_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, runtime_module)
    spec.loader.exec_module(runtime_module)

    def configure(*slots, enabled=True, module_enabled=True, fallback_enabled=True):
        env = _setup_fixture(ha_modules, engine)
        env.runtime = runtime_module.Runtime(engine)
        env.family_entry.runtime_data = env.runtime
        env.hass.data["family_assistant"]["entries"][env.family_entry.entry_id] = env.runtime
        config = {"enabled": enabled}
        for slot in slots:
            config[slot] = (
                deepcopy(env.config)
                if slot == "ha_agent"
                else {"url": f"https://{slot}.example.invalid", "model": slot, "timeout": 15}
            )
        if "fallback" in slots:
            config["fallback"]["enabled"] = fallback_enabled
        env.family_entry.options = {"conversation": config}
        if not module_enabled:
            engine._state["settings"]["modules"].remove("conversation")
        before = deepcopy(env.family_entry.options)
        runtime_module.async_configure_assistant(env.hass, env.family_entry)
        assert env.family_entry.options == before
        env.cascade = env.runtime.assistant.cascade if env.runtime.assistant else None
        env.session_requests = sessions
        env.runtime_module = runtime_module
        return env

    return configure


def names(cascade):
    return [item.model if isinstance(item, Ollama) else "ha_agent" for item in cascade.providers]


async def infer(env, **kwargs):
    return await env.cascade.generate(
        [{"role": "user", "content": "Synthetic question"}],
        plans.SCHEMA,
        plans.validate,
        actor_request=ActorRequest("parent", 1, "en"),
        **kwargs,
    )


@pytest.mark.parametrize(
    "slots, expected",
    [
        (("agy", "ha_agent", "primary", "fallback"), ["agy", "ha_agent", "primary", "fallback"]),
        (("ha_agent", "primary", "fallback"), ["ha_agent", "primary", "fallback"]),
        (("agy", "primary", "fallback"), ["agy", "primary", "fallback"]),
        (("agy", "ha_agent"), ["agy", "ha_agent"]),
        (("agy",), ["agy"]),
        (("ha_agent",), ["ha_agent"]),
        (("primary",), ["primary"]),
    ],
)
def test_configured_order_keeps_agy_first_without_inventing_a_transport(
    configured, slots, expected
):
    env = configured(*slots)
    assert names(env.cascade) == expected
    assert len(env.session_requests) == (0 if slots == ("ha_agent",) else 1)
    assert env.runtime.health == {}  # Construction is not a successful inference.
    if "agy" in slots:
        selected = next(
            item
            for item in env.cascade.providers
            if isinstance(item, Ollama) and item.model == "agy"
        )
        assert selected.url == "https://agy.example.invalid"


def test_disabled_fallback_is_retained_but_not_called(configured):
    env = configured("agy", "ha_agent", "primary", "fallback", fallback_enabled=False)
    assert names(env.cascade) == ["agy", "ha_agent", "primary"]
    assert env.family_entry.options["conversation"]["fallback"]["enabled"] is False


@pytest.mark.parametrize("enabled,module_enabled", [(False, True), (True, False)])
def test_inference_gates_do_not_create_transports(configured, enabled, module_enabled):
    env = configured("agy", "ha_agent", "primary", enabled=enabled, module_enabled=module_enabled)
    assert env.runtime.assistant is None and not env.session_requests
    assert (env.runtime.chat is not None) is module_enabled


@pytest.mark.parametrize("winner", ["agy", "ha_agent", "primary", "fallback"])
async def test_inference_uses_exact_precedence_and_stops_at_first_valid_result(
    configured, monkeypatch, winner
):
    env = configured("agy", "ha_agent", "primary", "fallback")
    calls = []
    order = ["agy", "ha_agent", "primary", "fallback"]

    async def request(session, method, url, **kwargs):
        model = kwargs["json"]["model"]
        calls.append(model)
        assert method == "POST" and url == f"https://{model}.example.invalid/api/chat"
        assert kwargs["json"]["stream"] is False
        if model != winner:
            raise DomainError("provider_timeout")
        return {"message": {"content": '{"kind":"answer","text":"Synthetic direct answer"}'}}

    def native():
        calls.append("ha_agent")
        if winner != "ha_agent":
            raise TimeoutError()

    env.mock_converse.on_call = native
    monkeypatch.setattr(provider, "request_json", request)
    result = await infer(env)
    assert result["kind"] == "answer"
    assert calls == order[: order.index(winner) + 1]
    assert env.runtime.health["conversation"] == ("connected" if winner == "agy" else "fallback")


@pytest.mark.parametrize(
    "change",
    [
        "permission",
        "inactive_user",
        "options",
        "actor_revision",
        "inflight_permission",
        "inflight_actor",
    ],
)
async def test_native_authorization_denial_after_agy_failure_never_reaches_direct_fallback(
    configured, monkeypatch, engine, change
):
    env = configured("agy", "ha_agent", "primary", "fallback")
    calls = []

    async def request(session, method, url, **kwargs):
        calls.append(kwargs["json"]["model"])
        raise DomainError("provider_timeout")

    monkeypatch.setattr(provider, "request_json", request)
    expected = "forbidden"
    if change == "permission":
        env.user_permissions.check_entity = lambda *_: False
    elif change == "inactive_user":
        env.user.is_active = False
    elif change == "options":
        env.family_entry.options["conversation"]["ha_agent"] = {**env.config, "timeout": 20}
        expected = "ha_agent_changed"
    elif change == "actor_revision":
        engine._state["members"]["parent"]["revision"] += 1
        expected = "conflict"
    elif change == "inflight_permission":
        env.mock_converse.on_call = lambda: setattr(
            env.user_permissions, "check_entity", lambda *_: False
        )
    else:
        env.mock_converse.on_call = lambda: engine._state["members"]["parent"].update(active=False)
    with pytest.raises(DomainError, match=expected):
        await infer(env)
    assert calls == ["agy"]
    assert env.cascade.failures == {0: "provider_timeout"}
    assert env.runtime.health == {}


async def test_member_without_ha_binding_can_use_explicit_direct_fallback(
    configured, monkeypatch, engine
):
    env = configured("agy", "ha_agent", "primary", "fallback")
    engine._state["members"]["parent"]["ha_user_id"] = ""
    calls = []

    async def request(session, method, url, **kwargs):
        model = kwargs["json"]["model"]
        calls.append(model)
        if model == "agy":
            raise DomainError("provider_timeout")
        return {"message": {"content": '{"kind":"answer","text":"Synthetic direct answer"}'}}

    monkeypatch.setattr(provider, "request_json", request)
    assert (await infer(env))["kind"] == "answer"
    assert calls == ["agy", "primary"] and not env.mock_converse.calls
    assert 1 not in env.cascade.cooldown and 1 not in env.cascade.failures


@pytest.mark.parametrize("failure", ["revoked_scope", "cancelled"])
async def test_agy_failure_cannot_bypass_scope_or_cancellation(configured, monkeypatch, failure):
    env = configured("agy", "ha_agent", "primary", "fallback")
    calls = []
    current = True

    async def request(session, method, url, **kwargs):
        nonlocal current
        calls.append(kwargs["json"]["model"])
        current = False
        if failure == "cancelled":
            raise asyncio.CancelledError()
        raise DomainError("provider_timeout")

    def scope():
        if not current:
            raise DomainError("forbidden")

    monkeypatch.setattr(provider, "request_json", request)
    with pytest.raises(asyncio.CancelledError if failure == "cancelled" else DomainError):
        await infer(env, scope_check=scope)
    assert calls == ["agy"] and not env.mock_converse.calls
    assert not env.cascade.failures and not env.cascade.cooldown and not env.runtime.health
