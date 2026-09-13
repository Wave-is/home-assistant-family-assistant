"""Native provider steps, real Engine/HA identity scope, synthetic remote inspection."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_school_reminder_options import config_flow  # noqa: F401

from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def native(config_flow, monkeypatch, engine):  # noqa: F811
    flow = config_flow.FamilyOptionsFlow()
    user = SimpleNamespace(id=engine.snapshot()["members"]["owner"]["ha_user_id"], is_active=True)
    flow.context = {"user_id": user.id}
    runtime = SimpleNamespace(engine=engine, updated=lambda: None)
    entry = SimpleNamespace(
        entry_id="synthetic-provider-entry",
        domain="family_assistant",
        state="loaded",
        runtime_data=runtime,
        options={},
    )
    runtime_module = ModuleType("custom_components.family_assistant.runtime")
    runtime_module.get_runtime = lambda hass, key: hass.data["family_assistant"]["entries"][key]
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    path = (
        Path(__file__).resolve().parents[1] / "custom_components/family_assistant/command_scope.py"
    )
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.command_scope", path
    )
    scope = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, scope)
    spec.loader.exec_module(scope)

    async def get_user(identifier):
        return user if identifier == user.id else None

    async def executor(fn, *args):
        return fn(*args)

    flow.config_entry = entry
    flow.hass = SimpleNamespace(
        data={"family_assistant": {"entries": {entry.entry_id: runtime}}},
        auth=SimpleNamespace(async_get_user=get_user),
        config_entries=SimpleNamespace(
            async_get_entry=lambda key: entry if key == entry.entry_id else None,
            async_entries=lambda domain: [entry] if domain == "family_assistant" else [],
        ),
        async_add_executor_job=executor,
    )
    selector = sys.modules["homeassistant.helpers.selector"]
    selector.TextSelectorConfig = dict
    selector.TextSelector = lambda config: str
    selector.TextSelectorType = SimpleNamespace(PASSWORD="password")
    client = ModuleType("homeassistant.helpers.aiohttp_client")
    client.async_get_clientsession = lambda hass: object()
    monkeypatch.setitem(sys.modules, client.__name__, client)
    return flow, entry, runtime, user


def inputs(kind):
    if kind == "conversation":
        return {
            "enabled": True,
            "primary_url": "https://model.example.invalid",
            "primary_model": "synthetic",
            "timeout": 15,
        }
    if kind == "search":
        return {"enabled": True, "url": "https://search.example.invalid"}
    if kind == "mikrotik":
        return {
            "enabled": True,
            "url": "https://router.example.invalid",
            "username": "synthetic-owner",
            "password": "synthetic-password",
        }
    return {"enabled": True, "token": "123456" + ":" + "a" * 32}


def provider(monkeypatch, kind, after=None, error=False):
    calls = []

    async def inspected(self, *args, **kwargs):
        calls.append(kind)
        if after:
            await after()
        if error:
            raise DomainError("provider_bad_response")
        return {"id": 123456, "username": "synthetic_bot"} if kind == "telegram" else []

    if kind == "conversation":
        from custom_components.family_assistant.assistant.provider import Ollama

        monkeypatch.setattr(Ollama, "inspect", inspected)
    elif kind == "search":
        from custom_components.family_assistant.assistant.search import Search

        monkeypatch.setattr(Search, "query", inspected)
    elif kind == "mikrotik":
        from custom_components.family_assistant.network import client

        monkeypatch.setattr(client, "certificate_context", lambda value: True)
        monkeypatch.setattr(client.RouterClient, "inspect", inspected)
    else:
        from custom_components.family_assistant.telegram.client import TelegramClient

        monkeypatch.setattr(TelegramClient, "inspect", inspected)
    return calls


KINDS = ("conversation", "search", "mikrotik", "telegram")


@pytest.mark.parametrize("kind", KINDS)
async def test_native_provider_steps_preserve_unrelated_options(native, monkeypatch, kind):
    flow, entry, _, _ = native
    entry.options = {"unrelated": {"keep": True}}
    calls = provider(monkeypatch, kind)
    step = getattr(flow, "async_step_" + kind)
    assert (await step())["type"] == "form"
    result = await step(inputs(kind))
    assert result["type"] == "create_entry" and result["data"]["unrelated"] == {"keep": True}
    assert calls == [kind]


@pytest.mark.parametrize("kind", KINDS)
async def test_displayed_provider_form_cannot_rebase_a_newer_options_change(
    native, monkeypatch, kind
):
    flow, entry, _, _ = native
    calls = provider(monkeypatch, kind)
    step = getattr(flow, "async_step_" + kind)
    await step()
    entry.options = {"newer": {"keep": True}}
    result = await step(inputs(kind))
    assert result == {"type": "abort", "reason": "conflict"} and calls == []
    assert entry.options == {"newer": {"keep": True}}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("drift", ["options", "owner", "ha_user", "reload", "backup"])
async def test_provider_await_rechecks_writes_and_private_error_forms(
    native, monkeypatch, now, kind, failed, drift
):
    flow, entry, runtime, user = native

    async def changed():
        if drift == "options":
            entry.options = {"newer": True}
        elif drift == "owner":
            await runtime.engine.system_update(
                "revoke-owner",
                now,
                lambda ctx: ctx.state["members"]["owner"].update(role="parent", revision=2),
            )
        elif drift == "ha_user":
            user.is_active = False
        elif drift == "reload":
            replacement = SimpleNamespace(engine=runtime.engine)
            entry.runtime_data = replacement
            flow.hass.data["family_assistant"]["entries"][entry.entry_id] = replacement
        else:
            flow.hass.data["family_assistant"]["backup"] = object()

    calls = provider(monkeypatch, kind, changed, failed)
    step = getattr(flow, "async_step_" + kind)
    await step()
    result = await step(inputs(kind))
    assert result["type"] == "abort", result
    assert result["reason"] in {"conflict", "forbidden", "backup_in_progress"}
    assert calls == [kind] and "data_schema" not in result and "data" not in result


async def test_clear_both_model_keys_is_honored_when_disabling_without_remote_io(
    native, monkeypatch
):
    flow, entry, _, _ = native
    entry.options = {
        "conversation": {
            "enabled": True,
            "primary": {
                "url": "https://primary.example.invalid",
                "model": "primary",
                "api_key": "synthetic-primary",
            },
            "fallback": {
                "url": "https://fallback.example.invalid",
                "model": "fallback",
                "api_key": "synthetic-fallback",
            },
        }
    }
    before = deepcopy(entry.options)
    calls = provider(monkeypatch, "conversation")
    await flow.async_step_conversation()
    result = await flow.async_step_conversation(
        {"enabled": False, "primary_clear_key": True, "fallback_clear_key": True}
    )
    assert result["type"] == "create_entry" and calls == []
    config = result["data"]["conversation"]
    assert config["enabled"] is False
    for key in ("primary", "fallback"):
        assert "api_key" not in config[key]
        assert config[key]["url"] == before["conversation"][key]["url"]
    assert entry.options == before


@pytest.mark.parametrize(
    "kind,secret,clear",
    [("mikrotik", "password", "clear_password"), ("telegram", "token", "clear_token")],
)
@pytest.mark.parametrize("remove", [False, True])
async def test_disable_keeps_credentials_unless_owner_explicitly_clears(
    native, monkeypatch, kind, secret, clear, remove
):
    flow, entry, _, _ = native
    entry.options = {
        kind: {"enabled": True, secret: "synthetic-private-value", "bot": {"id": 123456}}
    }
    calls = provider(monkeypatch, kind)
    step = getattr(flow, "async_step_" + kind)
    form = await step()
    assert clear in {key.schema for key in form["data_schema"].schema}
    marker = next(key for key in form["data_schema"].schema if key.schema == secret)
    from voluptuous import UNDEFINED

    assert marker.default is UNDEFINED
    result = await step({"enabled": False, clear: remove})
    assert result["type"] == "create_entry" and calls == []
    assert result["data"][kind]["enabled"] is False
    assert (secret in result["data"][kind]) is not remove
    if remove and kind == "telegram":
        assert "bot" not in result["data"][kind]


@pytest.mark.parametrize("clear", [False, True])
async def test_search_disable_retains_connection_and_honors_clear_without_query(
    native, monkeypatch, clear
):
    flow, entry, _, _ = native
    search = {
        "url": "https://search.example.invalid",
        "api_key": "synthetic-search-key",
        "allow_http": False,
    }
    entry.options = {
        "conversation": {"enabled": True, "search": search, "ha_agent": {"preserve": True}}
    }
    calls = provider(monkeypatch, "search")
    await flow.async_step_search()
    disabled = await flow.async_step_search({"enabled": False, "clear_key": clear})
    assert disabled["type"] == "create_entry" and calls == []
    saved = disabled["data"]["conversation"]["search"]
    assert saved["url"] == search["url"] and saved["enabled"] is False
    assert ("api_key" in saved) is not clear
    entry.options = disabled["data"]
    form = await flow.async_step_search()
    marker = next(key for key in form["data_schema"].schema if key.schema == "enabled")
    assert marker.default() is False
    enabled = await flow.async_step_search({"enabled": True})
    assert enabled["data"]["conversation"]["search"]["enabled"] is True and calls == ["search"]
    assert enabled["data"]["conversation"]["ha_agent"] == {"preserve": True}


@pytest.mark.parametrize("enabled,expected", [(True, 1), (False, 0), (None, 1)])
def test_readiness_counts_only_enabled_or_legacy_search(engine, enabled, expected):
    from custom_components.family_assistant.onboarding import item, readiness

    state = engine.snapshot()
    state["settings"]["modules"].append("conversation")
    search = {"url": "https://search.example.invalid"}
    if enabled is not None:
        search["enabled"] = enabled
    report = readiness(state, {"conversation": {"search": search}}, "owner")
    assert item(report, "models")["counts"]["search_enabled"] == expected


def models():
    return {
        "enabled": True,
        "primary": {
            "url": "https://primary.example.invalid",
            "model": "primary",
            "api_key": "synthetic-primary",
        },
        "fallback": {
            "url": "https://fallback.example.invalid",
            "model": "fallback",
            "api_key": "synthetic-fallback",
        },
        "search": {"url": "https://search.example.invalid", "enabled": False},
    }


def router():
    return {
        "enabled": True,
        "url": "https://router.example.invalid",
        "username": "synthetic-owner",
        "password": "synthetic-password",
        "allow_write": False,
        "allow_kid_control": False,
    }


def no_session(monkeypatch):
    def forbidden(*_args):
        raise AssertionError("A disabled provider must not initialize a transport")

    monkeypatch.setattr(
        sys.modules["homeassistant.helpers.aiohttp_client"], "async_get_clientsession", forbidden
    )


async def test_disabled_model_edits_and_fallback_choice_survive_reopen(native, monkeypatch):
    flow, entry, *_ = native
    entry.options = {"conversation": models(), "keep": True}
    original = deepcopy(entry.options)
    calls = provider(monkeypatch, "conversation")
    no_session(monkeypatch)
    form = await flow.async_step_conversation()
    values = form["data_schema"](
        {
            "enabled": False,
            "fallback_enabled": False,
            "primary_model": "changed-primary",
            "fallback_model": "changed-fallback",
            "timeout": 28,
            "allow_http": True,
        }
    )
    result = await flow.async_step_conversation(values)
    assert result["type"] == "create_entry" and calls == []
    saved = result["data"]["conversation"]
    assert saved["enabled"] is False and saved["fallback"]["enabled"] is False
    for key in ("primary", "fallback"):
        assert saved[key]["model"] == "changed-" + key
        assert saved[key]["timeout"] == 28 and saved[key]["allow_http"] is True
        assert saved[key]["api_key"] == models()[key]["api_key"]
    assert saved["search"] == models()["search"] and result["data"]["keep"] is True
    assert entry.options == original
    entry.options = result["data"]
    reopened = (await flow.async_step_conversation())["data_schema"]({})
    assert reopened["primary_model"] == "changed-primary" and reopened["timeout"] == 28
    assert reopened["fallback_enabled"] is False and reopened["enabled"] is False
    assert "primary_key" not in reopened and "fallback_key" not in reopened


async def test_fallback_disable_retains_key_then_reenable_inspects_both(native, monkeypatch):
    flow, entry, *_ = native
    entry.options = {"conversation": models()}
    calls = provider(monkeypatch, "conversation")
    form = await flow.async_step_conversation()
    disabled = await flow.async_step_conversation(form["data_schema"]({"fallback_enabled": False}))
    assert calls == ["conversation"]
    saved = disabled["data"]["conversation"]["fallback"]
    assert saved["enabled"] is False and saved["api_key"] == models()["fallback"]["api_key"]
    entry.options = disabled["data"]
    form = await flow.async_step_conversation()
    enabled = await flow.async_step_conversation(form["data_schema"]({"fallback_enabled": True}))
    assert calls == ["conversation"] * 3
    assert enabled["data"]["conversation"]["fallback"] == {**saved, "enabled": True}


@pytest.mark.parametrize("key", ["primary", "fallback"])
@pytest.mark.parametrize("secret_action", ["keep", "replace", "clear"])
async def test_disabled_model_endpoint_cannot_inherit_another_endpoint_key(
    native, monkeypatch, key, secret_action
):
    flow, entry, *_ = native
    entry.options = {"conversation": models()}
    before = deepcopy(entry.options)
    calls = provider(monkeypatch, "conversation")
    no_session(monkeypatch)
    form = await flow.async_step_conversation()
    values = {"enabled": False, key + "_url": "https://new.example.invalid"}
    if secret_action == "replace":
        values[key + "_key"] = "synthetic-replacement"
    elif secret_action == "clear":
        values[key + "_clear_key"] = True
        values[key + "_key"] = "synthetic-ignored"
    result = await flow.async_step_conversation(form["data_schema"](values))
    if secret_action == "keep":
        assert result["errors"]["base"] == "provider_key_scope"
    else:
        saved = result["data"]["conversation"][key]
        assert saved["url"] == values[key + "_url"]
        assert saved.get("api_key") == (
            "synthetic-replacement" if secret_action == "replace" else None
        )
    assert calls == [] and entry.options == before


@pytest.mark.parametrize(
    "kind,change",
    [
        (
            "conversation",
            {"primary_url": "http://model.example.invalid", "primary_clear_key": True},
        ),
        ("conversation", {"primary_model": ""}),
        ("mikrotik", {"url": "http://router.example.invalid", "clear_password": True}),
        ("mikrotik", {"username": "invalid:username", "clear_password": True}),
        ("mikrotik", {"allow_write": True}),
        ("telegram", {"token": "malformed-token"}),
    ],
)
async def test_disabled_provider_edits_still_validate_locally(native, monkeypatch, kind, change):
    flow, entry, *_ = native
    entry.options = {
        kind: models() if kind == "conversation" else router() if kind == "mikrotik" else {}
    }
    original = deepcopy(entry.options)
    calls = provider(monkeypatch, kind)
    no_session(monkeypatch)
    step = getattr(flow, "async_step_" + kind)
    form = await step()
    result = await step(form["data_schema"]({"enabled": False, **change}))
    assert result["type"] == "form" and result["errors"]["base"]
    assert calls == [] and entry.options == original


@pytest.mark.parametrize("clear", [False, True])
async def test_disabled_router_edits_preserve_every_nonsecret_control(native, monkeypatch, clear):
    flow, entry, *_ = native
    entry.options = {"mikrotik": router()}
    calls = provider(monkeypatch, "mikrotik")
    no_session(monkeypatch)
    edits = {
        "enabled": False,
        "url": "https://changed-router.example.invalid/rest",
        "username": "changed-owner",
        "password": "synthetic-new-password",
        "clear_password": clear,
        "ca_pem": "synthetic-certificate",
        "allow_write": True,
        "allow_kid_control": True,
        "ha_mac": "02:00:00:00:00:01",
        "management_mac": "02:00:00:00:00:02",
        "management_confirmed": True,
    }
    form = await flow.async_step_mikrotik()
    result = await flow.async_step_mikrotik(form["data_schema"](edits))
    assert result["type"] == "create_entry" and calls == []
    saved = result["data"]["mikrotik"]
    for key, value in edits.items():
        if key not in {"password", "clear_password"}:
            assert saved[key] == value
    assert saved.get("password") == (None if clear else edits["password"])
    assert "validation-only" not in repr(saved)
    entry.options = result["data"]
    reopened = (await flow.async_step_mikrotik())["data_schema"]({})
    assert "password" not in reopened
    assert all(
        reopened[key] == saved[key] for key in edits if key not in {"password", "clear_password"}
    )


@pytest.mark.parametrize("field", ["url", "username"])
async def test_disabled_router_cannot_carry_password_to_new_identity(native, monkeypatch, field):
    flow, entry, *_ = native
    entry.options = {"mikrotik": router()}
    calls = provider(monkeypatch, "mikrotik")
    no_session(monkeypatch)
    form = await flow.async_step_mikrotik()
    values = {
        "enabled": False,
        field: "https://new-router.example.invalid" if field == "url" else "another-owner",
    }
    result = await flow.async_step_mikrotik(form["data_schema"](values))
    assert result["errors"]["base"] == "network_credential_scope" and calls == []


@pytest.mark.parametrize("same", [False, True])
async def test_disabled_telegram_token_replacement_drops_only_unverified_identity(
    native, monkeypatch, same
):
    flow, entry, *_ = native
    token = inputs("telegram")["token"]
    entry.options = {"telegram": {"enabled": True, "token": token, "bot": {"id": 123456}}}
    calls = provider(monkeypatch, "telegram")
    no_session(monkeypatch)
    await flow.async_step_telegram()
    replacement = token if same else "234567" + ":" + "b" * 32
    result = await flow.async_step_telegram({"enabled": False, "token": replacement})
    saved = result["data"]["telegram"]
    assert saved["token"] == replacement and saved["enabled"] is False
    assert ("bot" in saved) is same and calls == []


async def test_disabled_router_local_certificate_await_is_still_fenced(native, monkeypatch):
    flow, entry, *_ = native
    entry.options = {"mikrotik": router()}
    provider(monkeypatch, "mikrotik")

    async def changed(fn, value):
        entry.options = {"newer": True}
        return fn(value)

    flow.hass.async_add_executor_job = changed
    form = await flow.async_step_mikrotik()
    result = await flow.async_step_mikrotik(
        form["data_schema"]({"enabled": False, "ca_pem": "synthetic-certificate"})
    )
    assert result == {"type": "abort", "reason": "conflict"}
    assert entry.options == {"newer": True}
