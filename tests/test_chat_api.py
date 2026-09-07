"""Dashboard chat WebSocket pins HA, household and provider scope."""

import asyncio
import importlib.util
import sys
from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import voluptuous as vol

from custom_components.family_assistant.assistant.chat_service import conversation_digest
from custom_components.family_assistant.const import DOMAIN
from custom_components.family_assistant.domain.validation import DomainError

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "family_assistant" / "assistant" / "chat_api.py"
ENTRY_ID = "entry_public"
SOURCE = "a" * 32


class _ConfigEntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


@pytest.fixture
def chat_api(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    components = ModuleType("homeassistant.components")
    websocket_api = ModuleType("homeassistant.components.websocket_api")
    config_entries = ModuleType("homeassistant.config_entries")
    util = ModuleType("homeassistant.util")
    dt_util = ModuleType("homeassistant.util.dt")

    def websocket_command(schema):
        command_schema = vol.Schema(schema, extra=vol.PREVENT_EXTRA)

        def decorate(function):
            function.command_schema = command_schema
            return function

        return decorate

    websocket_api.websocket_command = websocket_command
    websocket_api.async_response = lambda function: function
    config_entries.ConfigEntryState = _ConfigEntryState
    dt_util.utcnow = lambda: datetime(2026, 9, 7, 12, tzinfo=UTC)
    components.websocket_api = websocket_api
    util.dt = dt_util
    homeassistant.components = components
    homeassistant.config_entries = config_entries
    homeassistant.util = util
    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.websocket_api": websocket_api,
        "homeassistant.config_entries": config_entries,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_util,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "custom_components.family_assistant.assistant._chat_api_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _member(**changes):
    value = {
        "id": "member",
        "revision": 7,
        "active": True,
        "role": "adult",
        "language": "en",
        "ha_user_id": "ha-user",
    }
    value.update(changes)
    return value


class _Engine:
    def __init__(self):
        self.state = {
            "settings": {"modules": ["conversation"]},
            "members": {"member": _member()},
        }

    def actor_for_ha(self, user_id):
        if self.state["members"]["member"].get("ha_user_id") == user_id:
            return "member"
        raise DomainError("forbidden")

    def snapshot(self):
        return deepcopy(self.state)


class _Service:
    def __init__(self):
        self.calls = []
        self.change = None

    async def answer(self, **kwargs):
        hidden = {"guard", "scope_check", "runtime"}
        self.calls.append({key: value for key, value in kwargs.items() if key not in hidden})
        if self.change:
            self.change()
        kwargs["guard"](kwargs["runtime"].engine.snapshot())
        await kwargs["scope_check"]()
        return "safe reply"


class _Connection:
    def __init__(self, user):
        self.user = user
        self.results = []
        self.errors = []

    def send_result(self, message_id, result):
        self.results.append((message_id, result))

    def send_error(self, message_id, code, message):
        self.errors.append((message_id, code, message))


def _env(*, configured=True):
    user = SimpleNamespace(id="ha-user", is_active=True, is_admin=False)
    engine = _Engine()
    cascade = object() if configured else None
    assistant = SimpleNamespace(cascade=cascade, search=None) if configured else None
    service = _Service()
    options = {
        "conversation": {
            "enabled": configured,
            "primary": {"model": "model", "url": "https://provider.invalid"}
            if configured
            else None,
        }
    }
    runtime = SimpleNamespace(
        engine=engine,
        chat=service,
        assistant=assistant,
        assistant_revision=SOURCE,
        assistant_config_digest=conversation_digest(options["conversation"]),
    )
    entry = SimpleNamespace(
        entry_id=ENTRY_ID,
        domain=DOMAIN,
        state=_ConfigEntryState.LOADED,
        runtime_data=runtime,
        options=options,
    )
    config_entries = SimpleNamespace(
        async_get_entry=lambda entry_id: entry if entry_id == ENTRY_ID else None
    )

    async def get_user(user_id):
        return user if user_id == user.id else None

    hass = SimpleNamespace(
        auth=SimpleNamespace(async_get_user=get_user),
        config_entries=config_entries,
        data={DOMAIN: {"entries": {ENTRY_ID: runtime}}},
    )
    return SimpleNamespace(
        user=user,
        engine=engine,
        service=service,
        runtime=runtime,
        entry=entry,
        hass=hass,
        connection=_Connection(user),
    )


def _message(**changes):
    result = {
        "id": 9,
        "type": "family_assistant/chat",
        "entry_id": ENTRY_ID,
        "text": "/ping",
        "operation_id": "chat-operation",
        "session_id": "dashboard-session",
        "actor_revision": 7,
        "source_revision": SOURCE,
    }
    result.update(changes)
    return result


def test_schema_requires_exact_generation_and_actor_revision(chat_api):
    command = {key: value for key, value in _message().items() if key != "id"}
    assert chat_api.chat.command_schema(command)["actor_revision"] == 7
    for field in ("source_revision", "actor_revision"):
        with pytest.raises(vol.Invalid):
            chat_api.chat.command_schema(
                {key: value for key, value in command.items() if key != field}
            )
    with pytest.raises(vol.Invalid):
        chat_api.chat.command_schema({**command, "quoted_text": "not accepted"})


@pytest.mark.asyncio
async def test_unconfigured_model_still_allows_deterministic_chat(chat_api):
    env = _env(configured=False)
    await chat_api.chat(env.hass, env.connection, _message())
    assert env.connection.results == [(9, {"reply": "safe reply"})]
    assert env.service.calls[0]["actor"] == "member"
    assert env.service.calls[0]["actor_revision"] == 7
    assert chat_api.source_view(env.entry, env.runtime, "member") == {
        "enabled": True,
        "configured": False,
        "allowed": True,
        "revision": SOURCE,
    }


@pytest.mark.parametrize(
    "change",
    [
        "member_revision",
        "role",
        "language",
        "binding",
        "module",
        "user_inactive",
        "runtime",
        "service",
        "assistant",
        "provider",
        "options",
        "generation",
        "entry",
    ],
)
@pytest.mark.asyncio
async def test_scope_drift_is_code_only_and_returns_no_reply(chat_api, change):
    env = _env()

    def mutate():
        member = env.engine.state["members"]["member"]
        if change == "member_revision":
            member["revision"] += 1
        elif change == "role":
            member["role"] = "parent"
        elif change == "language":
            member["language"] = "ru"
        elif change == "binding":
            member["ha_user_id"] = "other"
        elif change == "module":
            env.engine.state["settings"]["modules"] = []
        elif change == "user_inactive":
            env.user.is_active = False
        elif change == "runtime":
            env.hass.data[DOMAIN]["entries"][ENTRY_ID] = SimpleNamespace()
        elif change == "service":
            env.runtime.chat = _Service()
        elif change == "assistant":
            env.runtime.assistant = SimpleNamespace(
                cascade=env.runtime.assistant.cascade, search=None
            )
        elif change == "provider":
            env.runtime.assistant.cascade = object()
        elif change == "options":
            env.entry.options["conversation"]["primary"]["url"] = "https://changed.invalid"
        elif change == "generation":
            env.runtime.assistant_revision = "b" * 32
        elif change == "entry":
            env.entry.state = _ConfigEntryState.NOT_LOADED

    env.service.change = mutate
    await chat_api.chat(env.hass, env.connection, _message(text="private canary"))
    assert env.connection.results == []
    assert len(env.connection.errors) == 1
    assert env.connection.errors[0][1] == env.connection.errors[0][2]
    assert "private canary" not in repr(env.connection.errors)


@pytest.mark.asyncio
async def test_stale_wire_versions_fail_before_service(chat_api):
    for changes in ({"actor_revision": 6}, {"source_revision": "b" * 32}):
        env = _env()
        await chat_api.chat(env.hass, env.connection, _message(**changes))
        assert env.service.calls == []
        assert env.connection.errors == [(9, "conflict", "conflict")]


@pytest.mark.asyncio
async def test_options_change_before_listener_never_uses_old_provider(chat_api):
    env = _env()
    env.entry.options["conversation"]["primary"]["url"] = "https://new.invalid"
    await chat_api.chat(env.hass, env.connection, _message(text="private family context"))
    assert env.service.calls == []
    assert env.connection.results == []
    assert env.connection.errors == [(9, "conflict", "conflict")]
    assert "private family context" not in repr(env.connection.errors)


def test_guest_and_removed_module_source_fail_closed(chat_api):
    env = _env()
    env.engine.state["members"]["member"]["role"] = "guest"
    assert chat_api.source_view(env.entry, env.runtime, "member")["allowed"] is False
    env.engine.state["members"]["member"]["role"] = "adult"
    env.engine.state["settings"]["modules"] = []
    assert chat_api.source_view(env.entry, env.runtime, "member") == {
        "enabled": False,
        "configured": True,
        "allowed": False,
        "revision": None,
    }


@pytest.mark.asyncio
async def test_endpoint_admission_precedes_blocked_ha_authority_await(chat_api):
    env = _env()
    started = 0
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_user(_user_id):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()
        return env.user

    env.hass.auth.async_get_user = blocked_user
    first = asyncio.create_task(
        chat_api.chat(env.hass, env.connection, _message(id=31, operation_id="one"))
    )
    second = asyncio.create_task(
        chat_api.chat(env.hass, env.connection, _message(id=32, operation_id="two"))
    )
    await both_started.wait()
    third_connection = _Connection(env.user)
    await chat_api.chat(
        env.hass,
        third_connection,
        _message(id=33, operation_id="three"),
    )
    assert third_connection.errors == [(33, "chat_busy", "chat_busy")]
    assert started == 2
    release.set()
    await first
    await second


@pytest.mark.asyncio
async def test_cancelled_authority_lookup_releases_endpoint_admission(chat_api):
    env = _env()
    started = asyncio.Event()

    async def blocked_user(_user_id):
        started.set()
        await asyncio.Event().wait()

    env.hass.auth.async_get_user = blocked_user
    request = asyncio.create_task(chat_api.chat(env.hass, env.connection, _message()))
    await started.wait()
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert chat_api._active == 0
    assert chat_api._active_users == {}
    assert env.connection.results == [] and env.connection.errors == []
