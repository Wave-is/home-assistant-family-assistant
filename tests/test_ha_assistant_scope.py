"""Standard HA Assist and LLM tools keep one current identity/runtime scope."""

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

from custom_components.family_assistant.assistant.chat_service import (
    ChatService,
    conversation_digest,
)
from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.const import DOMAIN

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "family_assistant"
SOURCE = "a" * 32


class _ConfigEntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


class _HomeAssistantError(Exception):
    def __init__(self, *, translation_domain, translation_key):
        del translation_domain
        self.translation_key = translation_key
        super().__init__(translation_key)


class _IntentResponseErrorCode(Enum):
    FAILED_TO_HANDLE = "failed_to_handle"


@pytest.fixture
def modules(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    components = ModuleType("homeassistant.components")
    conversation = ModuleType("homeassistant.components.conversation")
    config_entries = ModuleType("homeassistant.config_entries")
    core = ModuleType("homeassistant.core")
    exceptions = ModuleType("homeassistant.exceptions")
    helpers = ModuleType("homeassistant.helpers")
    intent = ModuleType("homeassistant.helpers.intent")
    entity = ModuleType("homeassistant.helpers.entity")
    llm = ModuleType("homeassistant.helpers.llm")
    util = ModuleType("homeassistant.util")
    dt_util = ModuleType("homeassistant.util.dt")

    class ConversationEntity:
        async def async_added_to_hass(self):
            return None

        def async_on_remove(self, _callback):
            return None

    class ConversationEntityFeature:
        CONTROL = 1

    class AssistantContent:
        def __init__(self, **values):
            self.__dict__.update(values)

    class ConversationResult:
        def __init__(self, **values):
            self.__dict__.update(values)

    class IntentResponse:
        def __init__(self, language):
            self.language = language
            self.speech = None
            self.error = None

        def async_set_speech(self, value):
            self.speech = value

        def async_set_error(self, code, message):
            self.error = code
            self.speech = message

    class API:
        def __init__(self, **values):
            self.__dict__.update(values)

    class Tool:
        pass

    class APIInstance:
        def __init__(self, **values):
            self.__dict__.update(values)

    conversation.AssistantContent = AssistantContent
    conversation.ConversationEntity = ConversationEntity
    conversation.ConversationEntityFeature = ConversationEntityFeature
    conversation.ConversationResult = ConversationResult
    config_entries.ConfigEntryState = _ConfigEntryState
    core.callback = lambda function: function
    exceptions.HomeAssistantError = _HomeAssistantError
    intent.IntentResponse = IntentResponse
    intent.IntentResponseErrorCode = _IntentResponseErrorCode
    entity.DeviceInfo = lambda **values: values
    llm.API = API
    llm.Tool = Tool
    llm.APIInstance = APIInstance
    llm.async_register_api = lambda _hass, _api: lambda: None
    dt_util.utcnow = lambda: datetime(2026, 9, 7, 12, tzinfo=UTC)
    components.conversation = conversation
    helpers.intent = intent
    helpers.llm = llm
    util.dt = dt_util
    homeassistant.components = components
    homeassistant.config_entries = config_entries
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.util = util
    replacements = {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.conversation": conversation,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.intent": intent,
        "homeassistant.helpers.entity": entity,
        "homeassistant.helpers.llm": llm,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_util,
    }
    for name, module in replacements.items():
        monkeypatch.setitem(sys.modules, name, module)

    scope = _load(
        monkeypatch,
        "custom_components.family_assistant.assistant.ha_scope",
        BASE / "assistant" / "ha_scope.py",
    )
    conversation_module = _load(
        monkeypatch,
        "custom_components.family_assistant._conversation_scope_test",
        BASE / "conversation.py",
    )
    llm_module = _load(
        monkeypatch,
        "custom_components.family_assistant._llm_scope_test",
        BASE / "llm_api.py",
    )
    return SimpleNamespace(
        scope=scope,
        conversation=conversation_module,
        llm=llm_module,
        HomeAssistantError=_HomeAssistantError,
    )


def _load(monkeypatch, name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


async def _enable(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "enable-ha-assistant-scope",
        now,
    )


def _environment(engine):
    options = {"conversation": {"enabled": False, "primary": None}}
    user = SimpleNamespace(id="synthetic-parent", is_active=True)
    runtime = SimpleNamespace(
        engine=engine,
        chat=ChatService(),
        assistant=None,
        assistant_revision=SOURCE,
        assistant_config_digest=conversation_digest(options["conversation"]),
        listeners=set(),
        updates=0,
    )
    runtime.updated = lambda: setattr(runtime, "updates", runtime.updates + 1)
    entry = SimpleNamespace(
        entry_id="entry",
        title="Household",
        domain=DOMAIN,
        state=_ConfigEntryState.LOADED,
        runtime_data=runtime,
        options=options,
        async_on_unload=lambda _callback: None,
    )

    async def get_user(user_id):
        return user if user_id == user.id else None

    hass = SimpleNamespace(
        auth=SimpleNamespace(async_get_user=get_user),
        config_entries=SimpleNamespace(
            async_get_entry=lambda entry_id: entry if entry_id == entry.entry_id else None
        ),
        data={DOMAIN: {"entries": {entry.entry_id: runtime}}},
    )
    return SimpleNamespace(hass=hass, entry=entry, runtime=runtime, user=user)


class _ChatLog:
    def __init__(self, conversation_id="conversation"):
        self.conversation_id = conversation_id
        self.contents = []

    def async_add_assistant_content_without_tools(self, content):
        self.contents.append(content.content)


def _user_input(text, context_id="context", user_id="synthetic-parent"):
    return SimpleNamespace(
        text=text,
        language="en",
        agent_id="agent",
        context=SimpleNamespace(id=context_id, user_id=user_id),
    )


@pytest.mark.asyncio
async def test_assist_uses_chat_service_exact_retry_and_discards_legacy_refs(modules, engine, now):
    await _enable(engine, now)
    env = _environment(engine)

    def legacy(ctx):
        ctx.state["memory"]["conversation_refs"] = {"old": ["private-old-id"]}

    await engine.system_update("legacy_refs", now, legacy)
    entity = modules.conversation.FamilyConversation(env.entry)
    entity.hass = env.hass
    first_log = _ChatLog()
    first = await entity._async_handle_message(
        _user_input("/buy Scoped milk", "same-context"), first_log
    )
    second = await entity._async_handle_message(
        _user_input("/buy Scoped milk", "same-context"), _ChatLog()
    )
    assert first.response.speech == second.response.speech
    assert [row["name"] for row in engine.snapshot()["shopping"].values()] == ["Scoped milk"]
    assert "conversation_refs" not in engine.snapshot()["memory"]

    conflict = await entity._async_handle_message(
        _user_input("/buy Different", "same-context"), _ChatLog()
    )
    assert "different action" in conflict.response.speech
    assert conflict.response.error is _IntentResponseErrorCode.FAILED_TO_HANDLE
    assert len(engine.snapshot()["shopping"]) == 1


@pytest.mark.asyncio
async def test_old_conversation_entity_cannot_bind_replacement_runtime(modules, engine, now):
    await _enable(engine, now)
    env = _environment(engine)
    entity = modules.conversation.FamilyConversation(env.entry)
    entity.hass = env.hass
    env.entry.runtime_data = SimpleNamespace()
    env.hass.data[DOMAIN]["entries"]["entry"] = env.entry.runtime_data
    result = await entity._async_handle_message(_user_input("/buy Hidden"), _ChatLog())
    assert "record changed" in result.response.speech
    assert result.response.error is _IntentResponseErrorCode.FAILED_TO_HANDLE
    assert not engine.snapshot()["shopping"]


class _BlockedProvider:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, _messages, _schema):
        self.started.set()
        await self.release.wait()
        return {"kind": "answer", "text": "stale private response"}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["inactive", "epoch", "module", "provider"])
async def test_assist_returns_no_stale_model_content_after_scope_change(
    modules, engine, now, change
):
    await _enable(engine, now)
    env = _environment(engine)
    provider = _BlockedProvider()
    env.runtime.assistant = Assistant(engine, Cascade([provider], {}))
    entity = modules.conversation.FamilyConversation(env.entry)
    entity.hass = env.hass
    request = asyncio.create_task(
        entity._async_handle_message(_user_input("Unknown family question"), _ChatLog())
    )
    await provider.started.wait()
    if change == "inactive":
        env.user.is_active = False
    elif change == "epoch":
        member = engine.snapshot()["members"]["parent"]
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": "parent",
                "revision": member["revision"],
                "name": "Parent rebound",
                "role": "parent",
                "language": "en",
            },
            "rebind-parent",
            now,
        )
    elif change == "module":
        settings = engine.snapshot()["settings"]
        await engine.execute(
            "owner",
            "settings.save",
            {
                **settings,
                "modules": [item for item in settings["modules"] if item != "conversation"],
            },
            "disable-conversation",
            now,
        )
    else:
        env.runtime.assistant_revision = "b" * 32
    provider.release.set()
    result = await request
    assert "stale private response" not in result.response.speech
    assert not engine.snapshot()["proposals"]


def _llm_context(user_id="synthetic-parent", context_id="llm-context"):
    return SimpleNamespace(context=SimpleNamespace(user_id=user_id, id=context_id))


@pytest.mark.asyncio
async def test_llm_read_requires_fresh_real_ha_user(modules, engine, now):
    await _enable(engine, now)
    env = _environment(engine)
    api = await modules.llm.FamilyAPI(env.hass, env.entry).async_get_api_instance(_llm_context())
    read = next(tool for tool in api.tools if tool.name == "ReadFamily")
    result = await read.async_call(
        env.hass, SimpleNamespace(tool_args={}, id="read"), _llm_context()
    )
    assert "shopping" in result
    env.user.is_active = False
    with pytest.raises(modules.HomeAssistantError) as error:
        await read.async_call(env.hass, SimpleNamespace(tool_args={}, id="read-2"), _llm_context())
    assert error.value.translation_key == "forbidden"


@pytest.mark.asyncio
async def test_external_llm_prepare_is_preview_only_and_exact_without_own_model(
    modules, engine, now
):
    await _enable(engine, now)
    env = _environment(engine)
    api = await modules.llm.FamilyAPI(env.hass, env.entry).async_get_api_instance(_llm_context())
    prepare = next(tool for tool in api.tools if tool.name == "PrepareFamilyPlan")
    args = {
        "request": "Add preview milk",
        "commands": [{"action": "shopping.add", "payload": {"name": "Preview milk"}}],
    }
    tool = SimpleNamespace(tool_args=args, id="prepare-1")
    first = await prepare.async_call(env.hass, tool, _llm_context())
    second = await prepare.async_call(env.hass, tool, _llm_context())
    assert first == second
    assert first["applied"] is False
    assert len(engine.snapshot()["proposals"]) == 1
    assert not engine.snapshot()["shopping"]

    changed = deepcopy(args)
    changed["commands"][0]["payload"]["name"] = "Different"
    with pytest.raises(modules.HomeAssistantError) as error:
        await prepare.async_call(
            env.hass,
            SimpleNamespace(tool_args=changed, id="prepare-1"),
            _llm_context(),
        )
    assert error.value.translation_key == "idempotency_conflict"
    assert len(engine.snapshot()["proposals"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["epoch", "module", "provider", "options", "runtime"])
async def test_llm_instance_does_not_cross_epoch_options_or_runtime(modules, engine, now, change):
    await _enable(engine, now)
    env = _environment(engine)
    api = await modules.llm.FamilyAPI(env.hass, env.entry).async_get_api_instance(_llm_context())
    read = next(tool for tool in api.tools if tool.name == "ReadFamily")
    if change == "epoch":
        member = engine.snapshot()["members"]["parent"]
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": "parent",
                "revision": member["revision"],
                "name": "Same-role rebound",
                "role": "parent",
                "language": "en",
            },
            "llm-rebind",
            now,
        )
    elif change == "module":
        settings = engine.snapshot()["settings"]
        await engine.execute(
            "owner",
            "settings.save",
            {
                **settings,
                "modules": [item for item in settings["modules"] if item != "conversation"],
            },
            "llm-disable",
            now,
        )
    elif change == "provider":
        env.runtime.assistant = SimpleNamespace(cascade=object(), search=None)
    elif change == "options":
        env.entry.options["conversation"] = {
            "enabled": True,
            "primary": {"model": "changed", "url": "https://changed.invalid"},
        }
    else:
        env.entry.runtime_data = SimpleNamespace()
        env.hass.data[DOMAIN]["entries"]["entry"] = env.entry.runtime_data
    with pytest.raises(modules.HomeAssistantError) as error:
        await read.async_call(env.hass, SimpleNamespace(tool_args={}, id="read"), _llm_context())
    assert error.value.translation_key in {"chat_unavailable", "conflict", "module_disabled"}
