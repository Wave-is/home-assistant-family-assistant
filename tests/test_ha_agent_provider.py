"""Tests for HAConversationAgent bounded official-Ollama provider adapter."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from enum import Enum
from pathlib import Path
from types import MappingProxyType, ModuleType, SimpleNamespace
from typing import Any

import pytest

from custom_components.family_assistant.assistant.provider import (
    ActorProviderUnavailable,
    ActorRequest,
)
from custom_components.family_assistant.const import DOMAIN
from custom_components.family_assistant.domain.validation import DomainError

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "family_assistant" / "assistant" / "ha_agent_provider.py"

_HA_VERSION = "2026.8.2"
_DEFAULT_PROMPT = "Default instructions prompt"


class _ConversationResult:
    def __init__(self, speech, error=None):
        self.speech = speech
        self.error = error

    def as_dict(self):
        return {
            "response": {
                "response_type": "error" if self.error else "action_done",
                "speech": {"plain": {"speech": self.speech}},
            }
        }


class _ConfigEntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


class _ConversationEntityFeature:
    CONTROL = 1


def _load(monkeypatch, name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ha_modules(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    ha_const = ModuleType("homeassistant.const")
    components = ModuleType("homeassistant.components")
    conversation = ModuleType("homeassistant.components.conversation")
    ollama = ModuleType("homeassistant.components.ollama")
    ollama_conv = ModuleType("homeassistant.components.ollama.conversation")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")
    exceptions = ModuleType("homeassistant.exceptions")
    helpers = ModuleType("homeassistant.helpers")
    er_module = ModuleType("homeassistant.helpers.entity_registry")
    llm = ModuleType("homeassistant.helpers.llm")
    auth_permissions = ModuleType("homeassistant.auth.permissions")
    auth_permissions_const = ModuleType("homeassistant.auth.permissions.const")

    ha_const.__version__ = _HA_VERSION
    auth_permissions_const.POLICY_READ = "read"

    class OllamaConversationEntity:
        supported_features = 0
        available = True

        def __init__(self, subentry=None, entry=None):
            self.subentry = subentry
            self.entry = entry

    class Context:
        def __init__(self, user_id=None, id=None):
            self.user_id = user_id
            self.id = id or "synthetic-context"

    config_entries.ConfigEntryState = _ConfigEntryState
    conversation.ConversationEntityFeature = _ConversationEntityFeature
    conversation.ConversationResult = _ConversationResult
    llm.DEFAULT_INSTRUCTIONS_PROMPT = _DEFAULT_PROMPT
    core.Context = Context
    core.HomeAssistant = object

    ollama_conv.OllamaConversationEntity = OllamaConversationEntity
    ollama.conversation = ollama_conv
    components.ollama = ollama
    components.conversation = conversation

    homeassistant.const = ha_const
    homeassistant.components = components
    homeassistant.config_entries = config_entries
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.helpers.entity_registry = er_module
    homeassistant.helpers.llm = llm

    replacements = {
        "homeassistant": homeassistant,
        "homeassistant.const": ha_const,
        "homeassistant.components": components,
        "homeassistant.components.conversation": conversation,
        "homeassistant.components.ollama": ollama,
        "homeassistant.components.ollama.conversation": ollama_conv,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": er_module,
        "homeassistant.helpers.llm": llm,
        "homeassistant.auth": ModuleType("homeassistant.auth"),
        "homeassistant.auth.permissions": auth_permissions,
        "homeassistant.auth.permissions.const": auth_permissions_const,
    }
    for name, module in replacements.items():
        monkeypatch.setitem(sys.modules, name, module)

    provider_module = _load(
        monkeypatch,
        "custom_components.family_assistant.assistant._ha_agent_provider_test",
        MODULE_PATH,
    )

    return SimpleNamespace(
        homeassistant=homeassistant,
        ha_const=ha_const,
        conversation=conversation,
        ollama_conv=ollama_conv,
        OllamaConversationEntity=OllamaConversationEntity,
        er=er_module,
        llm=llm,
        Context=Context,
        HAConversationAgent=provider_module.HAConversationAgent,
    )


class _MockConverse:
    def __init__(
        self,
        response_speech='{"kind": "answer", "text": "Valid response"}',
        error_code=None,
        delay=0,
    ):
        self.calls: list[dict[str, Any]] = []
        self.response_speech = response_speech
        self.error_code = error_code
        self.delay = delay
        self.on_call = None

    async def __call__(
        self,
        hass,
        text,
        conversation_id,
        context,
        language,
        agent_id,
        extra_system_prompt=None,
    ):
        call_info = {
            "hass": hass,
            "text": text,
            "conversation_id": conversation_id,
            "context": context,
            "language": language,
            "agent_id": agent_id,
            "extra_system_prompt": extra_system_prompt,
        }
        self.calls.append(call_info)
        if self.on_call is not None:
            res = self.on_call()
            if asyncio.iscoroutine(res):
                await res
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return _ConversationResult(self.response_speech, self.error_code)


def _setup_fixture(ha_modules, engine, config=None, member_id="parent"):
    if config is None:
        config = {"type": "ha_agent", "entity_id": "conversation.ollama", "timeout": 15}

    subentry = SimpleNamespace(subentry_id="subentry-1", data=MappingProxyType({}))
    agent = ha_modules.OllamaConversationEntity(subentry=subentry)

    ollama_entry = SimpleNamespace(
        entry_id="ollama-entry-1",
        domain="ollama",
        state=_ConfigEntryState.LOADED,
        subentries=MappingProxyType({"subentry-1": subentry}),
        data=MappingProxyType({}),
        options=MappingProxyType({}),
        runtime_data=object(),
    )
    agent.entry = ollama_entry

    reg_entry = SimpleNamespace(
        entity_id="conversation.ollama",
        domain="conversation",
        platform="ollama",
        disabled_by=None,
        config_entry_id="ollama-entry-1",
        config_subentry_id="subentry-1",
    )

    if "conversation" not in engine._state["settings"]["modules"]:
        engine._state["settings"]["modules"].append("conversation")

    runtime = SimpleNamespace(engine=engine, listeners=set(), updates=0)
    family_entry = SimpleNamespace(
        entry_id="family-entry-1",
        domain=DOMAIN,
        state=_ConfigEntryState.LOADED,
        runtime_data=runtime,
        options={"conversation": {"enabled": True, "ha_agent": config}},
    )

    user_permissions = SimpleNamespace(check_entity=lambda entity_id, policy: True)
    parent_user = SimpleNamespace(
        id=f"synthetic-{member_id}",
        is_active=True,
        permissions=user_permissions,
    )

    async def get_user(user_id):
        if user_id == parent_user.id:
            return parent_user
        return None

    state_obj = SimpleNamespace(state="idle")
    hass = SimpleNamespace(
        auth=SimpleNamespace(async_get_user=get_user),
        config_entries=SimpleNamespace(
            async_get_entry=lambda entry_id: (
                family_entry
                if entry_id == family_entry.entry_id
                else (ollama_entry if entry_id == ollama_entry.entry_id else None)
            )
        ),
        states=SimpleNamespace(
            get=lambda entity_id: state_obj if entity_id == "conversation.ollama" else None
        ),
        data={DOMAIN: {"entries": {family_entry.entry_id: runtime}}},
    )

    mock_converse = _MockConverse()

    env = SimpleNamespace(
        hass=hass,
        family_entry=family_entry,
        ollama_entry=ollama_entry,
        subentry=subentry,
        agent=agent,
        reg_entry=reg_entry,
        user=parent_user,
        user_permissions=user_permissions,
        runtime=runtime,
        mock_converse=mock_converse,
        config=config,
        HAConversationAgent=ha_modules.HAConversationAgent,
    )

    registry = SimpleNamespace(
        async_get=lambda entity_id: env.reg_entry if entity_id == "conversation.ollama" else None
    )
    ha_modules.er.async_get = lambda _hass: registry
    ha_modules.conversation.async_converse = mock_converse
    ha_modules.conversation.async_get_agent = lambda _hass, entity_id: (
        env.agent if entity_id == "conversation.ollama" else None
    )

    return env


def _messages():
    return [
        {"role": "system", "content": "You are a family planning assistant."},
        {"role": "user", "content": "Buy 2 apples"},
    ]


def _schema():
    return {
        "type": "object",
        "properties": {"kind": {"const": "answer"}, "text": {"type": "string"}},
    }


# --- 1. Core Version Verification ---


@pytest.mark.asyncio
async def test_unsupported_ha_version_rejected(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    ha_modules.ha_const.__version__ = "2026.9.0"
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)

    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.inspect()

    req = ActorRequest("parent", 1, "en")
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.generate_for_actor(_messages(), _schema(), req)

    assert len(env.mock_converse.calls) == 0


# --- 2. Target & Class Verification (Deny Subclass, Default, Custom, Family) ---


@pytest.mark.asyncio
async def test_deny_subclass_custom_default_family(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    # Subclass
    class SubclassOllama(ha_modules.OllamaConversationEntity):
        pass

    env.agent = SubclassOllama(subentry=env.subentry)
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0

    # Custom entity
    class CustomConversationEntity:
        supported_features = 0
        available = True

    env.agent = CustomConversationEntity()
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0

    # Wrong platform in registry
    env.agent = ha_modules.OllamaConversationEntity(subentry=env.subentry)
    env.reg_entry.platform = "homeassistant"
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


# --- 3. Deny CONTROL Feature and Configured LLM API ---


@pytest.mark.asyncio
async def test_deny_control_feature(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    env.agent.supported_features = 1  # ConversationEntityFeature.CONTROL
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["entry_data", "subentry_data", "inherited_entry"])
async def test_deny_configured_llm_api(ha_modules, engine, location):
    env = _setup_fixture(ha_modules, engine)
    if location == "entry_data":
        env.ollama_entry.data = MappingProxyType({"llm_hass_api": "assist"})
    elif location == "subentry_data":
        env.subentry.data = MappingProxyType({"llm_hass_api": "assist"})
    elif location == "inherited_entry":
        env.ollama_entry.data = MappingProxyType({"llm_hass_api": "assist"})

    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


# --- 4. Forbidden Prompt Template vs Default/Absent ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt_val,should_succeed",
    [
        (None, True),
        ("", True),
        (_DEFAULT_PROMPT, True),
        ("You are an assistant. {{ states('sensor.secret') }}", False),
        ("Arbitrary template prompt", False),
    ],
)
async def test_prompt_template_restriction(ha_modules, engine, prompt_val, should_succeed):
    env = _setup_fixture(ha_modules, engine)
    if prompt_val is not None:
        env.subentry.data = MappingProxyType({"prompt": prompt_val})
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    if should_succeed:
        await adapter.inspect()
        res = await adapter.generate_for_actor(_messages(), _schema(), req)
        assert res["kind"] == "answer"
        assert len(env.mock_converse.calls) == 1
    else:
        with pytest.raises(DomainError, match="ha_agent_unsupported"):
            await adapter.inspect()
        with pytest.raises(DomainError, match="ha_agent_unsupported"):
            await adapter.generate_for_actor(_messages(), _schema(), req)
        assert len(env.mock_converse.calls) == 0


# --- 5. Target Absent, Disabled or Stale ---


@pytest.mark.asyncio
async def test_target_absent_or_disabled(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    # Disabled
    env.reg_entry.disabled_by = "user"
    with pytest.raises(DomainError, match="ha_agent_unavailable"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unavailable"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0

    # Unloaded entry
    env.reg_entry.disabled_by = None
    env.ollama_entry.state = _ConfigEntryState.NOT_LOADED
    with pytest.raises(DomainError, match="ha_agent_unavailable"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unavailable"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0

    # Agent absent
    env.ollama_entry.state = _ConfigEntryState.LOADED
    ha_modules.conversation.async_get_agent = lambda _hass, _id: None
    with pytest.raises(DomainError, match="ha_agent_unavailable"):
        await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_unavailable"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


# --- 6. Exact User and Fresh Conversation Verification ---


@pytest.mark.asyncio
async def test_exact_user_and_fresh_conversation(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine, member_id="child")
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("child", 1, "en")

    res = await adapter.generate_for_actor(_messages(), _schema(), req)
    assert res["kind"] == "answer"
    assert len(env.mock_converse.calls) == 1

    call = env.mock_converse.calls[0]
    assert call["conversation_id"] is None
    assert call["context"].user_id == "synthetic-child"
    assert call["context"].user_id != "synthetic-parent"
    assert call["language"] == "en"
    assert call["agent_id"] == "conversation.ollama"
    assert "Respond strictly in JSON matching the following schema" in call["extra_system_prompt"]
    assert "Buy 2 apples" in call["text"]


# --- 7. Missing Binding vs Revoked Binding & Guest Denial ---


@pytest.mark.asyncio
async def test_missing_ha_binding_raises_actor_provider_unavailable(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    engine._state["members"]["parent"]["ha_user_id"] = None
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    with pytest.raises(ActorProviderUnavailable, match="ha_agent_account_required"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


@pytest.mark.asyncio
async def test_revoked_binding_fails_forbidden(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    # User is deactivated in HA
    env.user.is_active = False
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    with pytest.raises(DomainError, match="forbidden"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


@pytest.mark.asyncio
async def test_permission_denied_fails_forbidden(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    env.user_permissions.check_entity = lambda entity_id, policy: False
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    with pytest.raises(DomainError, match="forbidden"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


@pytest.mark.asyncio
async def test_guest_actor_fails_forbidden(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine, member_id="guest")
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("guest", 1, "en")

    with pytest.raises(DomainError, match="forbidden"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


# --- 8. Config / Actor / Target Changes During Auth and Inference ---


@pytest.mark.asyncio
@pytest.mark.parametrize("change_point", ["auth", "inference"])
async def test_actor_revision_change_fails_conflict(ha_modules, engine, change_point):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    if change_point == "auth":
        orig_get_user = env.hass.auth.async_get_user

        async def get_user_and_mutate(user_id):
            engine._state["members"]["parent"]["revision"] = 2
            return await orig_get_user(user_id)

        env.hass.auth.async_get_user = get_user_and_mutate
    else:

        def on_call():
            engine._state["members"]["parent"]["revision"] = 2

        env.mock_converse.on_call = on_call

    with pytest.raises(DomainError, match="conflict"):
        await adapter.generate_for_actor(_messages(), _schema(), req)


@pytest.mark.asyncio
@pytest.mark.parametrize("change_point", ["auth", "inference"])
async def test_target_subentry_change_fails_ha_agent_changed(ha_modules, engine, change_point):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    if change_point == "auth":
        orig_get_user = env.hass.auth.async_get_user

        async def get_user_and_mutate(user_id):
            env.ollama_entry.subentries = MappingProxyType(
                {"subentry-1": SimpleNamespace(subentry_id="subentry-1", data={"model": "changed"})}
            )
            return await orig_get_user(user_id)

        env.hass.auth.async_get_user = get_user_and_mutate
    else:

        def on_call():
            env.ollama_entry.subentries = MappingProxyType(
                {"subentry-1": SimpleNamespace(subentry_id="subentry-1", data={"model": "changed"})}
            )

        env.mock_converse.on_call = on_call

    with pytest.raises(DomainError, match="ha_agent_changed"):
        await adapter.generate_for_actor(_messages(), _schema(), req)


@pytest.mark.asyncio
async def test_family_options_changed_fail_generation_but_inspection_is_independent(
    ha_modules, engine
):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    env.family_entry.options["conversation"]["ha_agent"] = {
        "type": "ha_agent",
        "entity_id": "conversation.different",
        "timeout": 15,
    }

    await adapter.inspect()
    with pytest.raises(DomainError, match="ha_agent_changed"):
        await adapter.generate_for_actor(_messages(), _schema(), req)
    assert len(env.mock_converse.calls) == 0


# --- 9. Output Validation: Malformed, Duplicates, Nonfinite, Fences, Bounds ---


@pytest.mark.asyncio
async def test_valid_output_parsing(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    env.mock_converse.response_speech = '{"kind": "answer", "text": "All good"}'
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    res = await adapter.generate_for_actor(_messages(), _schema(), req)
    assert res == {"kind": "answer", "text": "All good"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_speech",
    [
        '{"a": 1, "a": 2}',  # Duplicate keys
        '{"value": NaN}',  # Nonfinite NaN
        '{"value": Infinity}',  # Nonfinite Infinity
        '```json\n{"kind": "answer"}\n```',  # Markdown fence not salvaged
        '["kind", "answer"]',  # Not an object
        '"just a string"',  # Scalar string
        "12345",  # Scalar number
        "{bad json",  # Syntax error
        "",  # Empty
        " " * 10,  # Whitespace
        '{"kind": "answer", "text": "' + "x" * 25000 + '"}',  # Output length > 20000
    ],
)
async def test_malformed_output_rejected(ha_modules, engine, bad_speech):
    env = _setup_fixture(ha_modules, engine)
    env.mock_converse.response_speech = bad_speech
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    with pytest.raises(DomainError, match="provider_bad_response"):
        await adapter.generate_for_actor(_messages(), _schema(), req)


# --- 10. Timeout Verification ---


@pytest.mark.asyncio
async def test_timeout_raises_provider_timeout(ha_modules, engine):
    config = {"type": "ha_agent", "entity_id": "conversation.ollama", "timeout": 5}
    env = _setup_fixture(ha_modules, engine, config=config)
    env.mock_converse.delay = 10  # Longer than timeout=5
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    with pytest.raises(DomainError, match="provider_timeout"):
        await adapter.generate_for_actor(_messages(), _schema(), req)


# --- 11. Bounded Input and Config Validation ---


@pytest.mark.asyncio
async def test_oversized_input_rejected_before_converse(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    req = ActorRequest("parent", 1, "en")

    huge_messages = [{"role": "user", "content": "A" * 205_000}]
    with pytest.raises(DomainError, match="invalid_field"):
        await adapter.generate_for_actor(huge_messages, _schema(), req)
    assert len(env.mock_converse.calls) == 0


def test_invalid_config_validation(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    # Extra key
    with pytest.raises(DomainError, match="invalid_field"):
        env.HAConversationAgent(
            env.hass,
            env.family_entry,
            {"type": "ha_agent", "entity_id": "conversation.ollama", "unknown": True},
        )
    # Wrong type
    with pytest.raises(DomainError, match="invalid_field"):
        env.HAConversationAgent(
            env.hass, env.family_entry, {"type": "other", "entity_id": "conversation.ollama"}
        )
    # Bad entity_id
    with pytest.raises(DomainError, match="invalid_field"):
        env.HAConversationAgent(
            env.hass, env.family_entry, {"type": "ha_agent", "entity_id": "light.ollama"}
        )
    # Timeout out of range
    with pytest.raises(DomainError, match="invalid_field"):
        env.HAConversationAgent(
            env.hass,
            env.family_entry,
            {"type": "ha_agent", "entity_id": "conversation.ollama", "timeout": 2},
        )
    with pytest.raises(DomainError, match="invalid_field"):
        env.HAConversationAgent(
            env.hass,
            env.family_entry,
            {"type": "ha_agent", "entity_id": "conversation.ollama", "timeout": 61},
        )
    adapter = env.HAConversationAgent(env.hass, env.family_entry, {**env.config, "timeout": 60})
    assert adapter.timeout == 60


@pytest.mark.asyncio
async def test_no_generate_fallback_inventing_identity(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    with pytest.raises(DomainError, match="forbidden"):
        await adapter.generate(_messages(), _schema())
    assert len(env.mock_converse.calls) == 0


@pytest.mark.asyncio
async def test_photo_input_never_silently_loses_image_in_native_converse(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    messages = _messages()
    messages[-1]["images"] = ["synthetic_base64"]
    with pytest.raises(ActorProviderUnavailable, match="provider_images_unsupported"):
        await adapter.generate_for_actor(messages, _schema(), ActorRequest("parent", 1, "en"))
    assert not env.mock_converse.calls


@pytest.mark.asyncio
async def test_target_review_before_selection_persists_ids_not_provider_data(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    env.family_entry.options = {}
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    proof = await adapter.inspect()
    assert proof.binding == {
        "config_entry_id": "ollama-entry-1",
        "config_subentry_id": "subentry-1",
    }
    adapter.validate_review(proof)
    assert not env.mock_converse.calls
    wrong = {**env.config, "binding": {**proof.binding, "config_subentry_id": "different"}}
    with pytest.raises(DomainError, match="ha_agent_changed"):
        await env.HAConversationAgent(env.hass, env.family_entry, wrong).inspect()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["unknown", "2026-09-08T00:00:00+00:00", "unavailable", None])
async def test_native_last_activity_is_not_connection_health(ha_modules, engine, state):
    env = _setup_fixture(ha_modules, engine)
    env.hass.states.get = lambda _id: SimpleNamespace(state=state) if state is not None else None
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    if state in {None, "unavailable"}:
        with pytest.raises(DomainError, match="ha_agent_unavailable"):
            await adapter.inspect()
    else:
        await adapter.inspect()
    assert not env.mock_converse.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["data", "options", "subentry"])
@pytest.mark.parametrize("value", ["none", "None", "assist", ["assist"], True, 0])
async def test_mapping_proxy_api_sources_never_bypass_no_tools(ha_modules, engine, location, value):
    env = _setup_fixture(ha_modules, engine)
    values = MappingProxyType({"llm_hass_api": value})
    if location == "subentry":
        env.subentry.data = values
    else:
        setattr(env.ollama_entry, location, values)
    with pytest.raises(DomainError, match="ha_agent_unsupported"):
        await env.HAConversationAgent(env.hass, env.family_entry, env.config).inspect()
    assert not env.mock_converse.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["client", "options", "nested", "registry", "agent_entry"])
async def test_target_changes_during_inference_are_not_provider_failures(
    ha_modules, engine, changed
):
    env = _setup_fixture(ha_modules, engine)
    nested = {"model_options": {"temperature": 0.3}}
    env.ollama_entry.data = MappingProxyType(nested)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)

    def change():
        if changed == "client":
            env.ollama_entry.runtime_data = object()
        elif changed == "options":
            env.ollama_entry.options = MappingProxyType({"other": "changed"})
        elif changed == "nested":
            nested["model_options"]["temperature"] = 0.9
        elif changed == "registry":
            env.reg_entry = SimpleNamespace(**vars(env.reg_entry))
        else:
            env.agent.entry = SimpleNamespace(**vars(env.ollama_entry))

    env.mock_converse.on_call = change
    with pytest.raises(DomainError, match="ha_agent_changed"):
        await adapter.generate_for_actor(_messages(), _schema(), ActorRequest("parent", 1, "en"))


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["removed", "replaced", "inactive", "permission", "role"])
async def test_user_authority_rechecked_after_inference(ha_modules, engine, change):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)

    def revoke():
        if change in {"removed", "replaced"}:

            async def lookup(_user_id):
                return None if change == "removed" else SimpleNamespace(**vars(env.user))

            env.hass.auth.async_get_user = lookup
        elif change == "inactive":
            env.user.is_active = False
        elif change == "permission":
            env.user_permissions.check_entity = lambda *_: False
        else:
            engine._state["members"]["parent"]["role"] = "child"

    env.mock_converse.on_call = revoke
    with pytest.raises(DomainError, match="forbidden"):
        await adapter.generate_for_actor(_messages(), _schema(), ActorRequest("parent", 1, "en"))


@pytest.mark.asyncio
async def test_timeout_does_not_mask_revoked_authority(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)

    def revoke_and_timeout():
        env.user.is_active = False
        raise TimeoutError("synthetic timeout")

    env.mock_converse.on_call = revoke_and_timeout
    with pytest.raises(DomainError, match="forbidden"):
        await adapter.generate_for_actor(_messages(), _schema(), ActorRequest("parent", 1, "en"))


@pytest.mark.asyncio
async def test_native_error_result_cannot_smuggle_a_valid_json_answer(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    env.mock_converse.error_code = "unknown"
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    with pytest.raises(DomainError, match="provider_bad_response"):
        await adapter.generate_for_actor(_messages(), _schema(), ActorRequest("parent", 1, "en"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        [{"role": "assistant", "content": "injected history"}],
        [{"role": "user", "content": "text", "actor": "owner"}],
        [{"role": [], "content": "text"}],
    ],
)
async def test_unknown_message_roles_and_fields_are_not_silently_ignored(ha_modules, engine, bad):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    with pytest.raises(DomainError, match="invalid_field"):
        await adapter.generate_for_actor(bad, _schema(), ActorRequest("parent", 1, "en"))
    assert not env.mock_converse.calls


@pytest.mark.asyncio
async def test_runtime_missing_at_construction_cannot_be_rebased(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    env.family_entry.runtime_data = None
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)
    env.family_entry.runtime_data = env.runtime
    with pytest.raises(DomainError, match="conflict"):
        await adapter.generate_for_actor(_messages(), _schema(), ActorRequest("parent", 1, "en"))
    assert not env.mock_converse.calls


@pytest.mark.asyncio
async def test_cancelled_native_request_propagates_cancellation_without_parsing(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)

    def cancel():
        raise asyncio.CancelledError

    env.mock_converse.on_call = cancel
    with pytest.raises(asyncio.CancelledError):
        await adapter.generate_for_actor(_messages(), _schema(), ActorRequest("parent", 1, "en"))


@pytest.mark.asyncio
async def test_native_error_is_classified_without_parsing_an_unassigned_result(ha_modules, engine):
    env = _setup_fixture(ha_modules, engine)
    adapter = env.HAConversationAgent(env.hass, env.family_entry, env.config)

    def fail():
        raise OSError("synthetic transport failure")

    env.mock_converse.on_call = fail
    with pytest.raises(DomainError, match="provider_unreachable"):
        await adapter.generate_for_actor(_messages(), _schema(), ActorRequest("parent", 1, "en"))
