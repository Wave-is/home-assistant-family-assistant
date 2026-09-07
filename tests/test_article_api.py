"""Authenticated article WebSocket boundary and immutable scope tests."""

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
import voluptuous as vol

from custom_components.family_assistant.const import DOMAIN
from custom_components.family_assistant.domain.validation import DomainError

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "family_assistant" / "assistant" / "article_api.py"
ENTRY_ID = "entry_public"
ARTICLE_REVISION = "a" * 32
POLICY_REVISION = "b" * 32
URL = "https://public.example/article"
RESULT = {
    "answer": "Bounded public answer.",
    "sources": [
        {
            "title": "Public article",
            "url": "https://public.example/final",
            "requested_url": URL,
            "retrieved_at": "2026-09-07T12:00:00+00:00",
        }
    ],
}


class _ConfigEntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


@pytest.fixture
def article_api(monkeypatch):
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

    name = "custom_components.family_assistant.assistant._article_api_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _member(
    role="adult",
    *,
    revision=7,
    language="en",
    active=True,
    user_id="ha-user",
):
    return {
        "id": "member",
        "revision": revision,
        "active": active,
        "role": role,
        "language": language,
        "ha_user_id": user_id,
    }


def _options(*, enabled=True, allow_children=False, policy_revision=POLICY_REVISION):
    return {
        "conversation": {
            "enabled": True,
            "primary": {"model": "synthetic-model", "url": "https://model.invalid"},
        },
        "articles": {
            "enabled": enabled,
            "allow_children": allow_children,
            "revision": policy_revision,
        },
    }


class _Engine:
    def __init__(self, member=None):
        self.state = {
            "settings": {"modules": ["conversation"]},
            "members": {"member": member or _member()},
            "canary_private_state": URL,
        }
        self.snapshot_calls = 0
        self.actor_calls = []
        self.write_calls = 0

    def actor_for_ha(self, user_id):
        self.actor_calls.append(user_id)
        member = self.state["members"].get("member")
        if isinstance(member, dict) and member.get("ha_user_id") == user_id:
            return "member"
        raise DomainError("forbidden")

    def snapshot(self):
        self.snapshot_calls += 1
        return deepcopy(self.state)


class _Service:
    def __init__(self, cascade):
        self.cascade = cascade
        self.calls = []
        self.before_return = None
        self.error = None
        self.check_inside = True

    async def answer(
        self,
        actor,
        actor_revision,
        language,
        url,
        operation_id,
        now,
        *,
        scope_revision,
        scope_check,
    ):
        self.calls.append(
            {
                "actor": actor,
                "actor_revision": actor_revision,
                "language": language,
                "url": url,
                "operation_id": operation_id,
                "now": now,
                "scope_revision": scope_revision,
            }
        )
        if self.check_inside:
            await scope_check()
        if self.before_return is not None:
            result = self.before_return()
            if hasattr(result, "__await__"):
                await result
        if self.error is not None:
            raise self.error
        return deepcopy(RESULT)


class _Auth:
    def __init__(self, user):
        self.user = user
        self.calls = []
        self.before_return = []

    async def async_get_user(self, user_id):
        self.calls.append(user_id)
        if self.before_return:
            callback = self.before_return.pop(0)
            result = callback()
            if hasattr(result, "__await__"):
                await result
        if self.user is None or self.user.id != user_id:
            return None
        return self.user


class _ConfigEntries:
    def __init__(self, entry):
        self.entry = entry

    def async_get_entry(self, entry_id):
        return self.entry if self.entry is not None and entry_id == self.entry.entry_id else None


class _Connection:
    def __init__(self, user):
        self.user = user
        self.results = []
        self.errors = []

    def send_result(self, message_id, result):
        self.results.append((message_id, deepcopy(result)))

    def send_error(self, message_id, code, message):
        self.errors.append((message_id, code, message))


def _environment(*, role="adult", allow_children=False, admin=False):
    user = SimpleNamespace(id="ha-user", is_active=True, is_admin=admin)
    engine = _Engine(_member(role))
    cascade = object()
    assistant = SimpleNamespace(cascade=cascade)
    service = _Service(cascade)
    runtime = SimpleNamespace(
        engine=engine,
        assistant=assistant,
        articles=service,
        article_revision=ARTICLE_REVISION,
    )
    entry = SimpleNamespace(
        entry_id=ENTRY_ID,
        domain=DOMAIN,
        state=_ConfigEntryState.LOADED,
        runtime_data=runtime,
        options=_options(allow_children=allow_children),
    )
    auth = _Auth(user)
    hass = SimpleNamespace(
        auth=auth,
        config_entries=_ConfigEntries(entry),
        data={DOMAIN: {"entries": {ENTRY_ID: runtime}}},
    )
    connection = _Connection(user)
    return SimpleNamespace(
        hass=hass,
        connection=connection,
        entry=entry,
        runtime=runtime,
        engine=engine,
        service=service,
        assistant=assistant,
        cascade=cascade,
        auth=auth,
        user=user,
    )


def _message(**changes):
    value = {
        "id": 11,
        "type": "family_assistant/article",
        "entry_id": ENTRY_ID,
        "url": URL,
        "operation_id": "article-operation",
        "source_revision": ARTICLE_REVISION,
    }
    value.update(changes)
    return value


@pytest.mark.asyncio
async def test_non_admin_adult_success_is_exact_and_read_only(article_api):
    env = _environment(admin=False)

    await article_api.article(env.hass, env.connection, _message())

    assert env.connection.results == [(11, RESULT)]
    assert env.connection.errors == []
    assert env.service.calls == [
        {
            "actor": "member",
            "actor_revision": 7,
            "language": "en",
            "url": URL,
            "operation_id": "article-operation",
            "now": datetime(2026, 9, 7, 12, tzinfo=UTC),
            "scope_revision": ARTICLE_REVISION,
        }
    ]
    assert env.engine.write_calls == 0
    assert len(env.auth.calls) >= 3


def test_websocket_schema_is_exact_and_requires_generation(article_api):
    command = {key: value for key, value in _message().items() if key != "id"}
    valid = article_api.article.command_schema(command)
    assert valid["source_revision"] == ARTICLE_REVISION
    with pytest.raises(vol.Invalid):
        article_api.article.command_schema(
            {key: value for key, value in command.items() if key != "source_revision"}
        )
    with pytest.raises(vol.Invalid):
        article_api.article.command_schema({**command, "target_member": "child"})


@pytest.mark.asyncio
async def test_source_revision_is_checked_before_fetch(article_api):
    env = _environment()

    await article_api.article(
        env.hass,
        env.connection,
        _message(source_revision="c" * 32),
    )

    assert env.service.calls == []
    assert env.connection.results == []
    assert env.connection.errors == [(11, "conflict", "conflict")]


@pytest.mark.parametrize("role", ["owner", "parent", "adult"])
@pytest.mark.asyncio
async def test_privileged_and_adult_roles_do_not_require_ha_admin(article_api, role):
    env = _environment(role=role, admin=False)
    await article_api.article(env.hass, env.connection, _message())
    assert env.connection.results == [(11, RESULT)]


@pytest.mark.asyncio
async def test_child_needs_explicit_policy_and_guest_is_always_denied(article_api):
    denied = _environment(role="child", allow_children=False)
    await article_api.article(denied.hass, denied.connection, _message())
    assert denied.service.calls == []
    assert denied.connection.errors == [(11, "forbidden", "forbidden")]

    allowed = _environment(role="child", allow_children=True)
    await article_api.article(allowed.hass, allowed.connection, _message())
    assert allowed.connection.results == [(11, RESULT)]

    guest = _environment(role="guest", allow_children=True)
    await article_api.article(guest.hass, guest.connection, _message())
    assert guest.service.calls == []
    assert guest.connection.errors == [(11, "forbidden", "forbidden")]


@pytest.mark.parametrize(
    "change",
    [
        "entry",
        "unload",
        "runtime",
        "engine",
        "service",
        "assistant",
        "cascade",
        "article_revision",
        "policy_revision",
        "policy_enabled",
        "conversation_model",
        "conversation_url",
        "conversation_key",
        "conversation_fallback",
        "module",
        "member_revision",
        "member_role",
        "member_language",
        "member_binding",
        "ha_user_inactive",
    ],
)
@pytest.mark.asyncio
async def test_every_async_scope_dimension_is_rechecked_before_result(article_api, change):
    env = _environment()

    def mutate():
        if change == "entry":
            replacement = deepcopy(env.entry)
            replacement.runtime_data = env.runtime
            env.hass.config_entries.entry = replacement
        elif change == "unload":
            env.entry.state = _ConfigEntryState.NOT_LOADED
        elif change == "runtime":
            env.hass.data[DOMAIN]["entries"][ENTRY_ID] = SimpleNamespace()
        elif change == "engine":
            env.runtime.engine = _Engine()
        elif change == "service":
            env.runtime.articles = _Service(env.cascade)
        elif change == "assistant":
            env.runtime.assistant = SimpleNamespace(cascade=env.cascade)
        elif change == "cascade":
            env.assistant.cascade = object()
        elif change == "article_revision":
            env.runtime.article_revision = "c" * 32
        elif change == "policy_revision":
            env.entry.options["articles"]["revision"] = "c" * 32
        elif change == "policy_enabled":
            env.entry.options["articles"]["enabled"] = False
        elif change == "conversation_model":
            env.entry.options["conversation"]["primary"]["model"] = "changed-model"
        elif change == "conversation_url":
            env.entry.options["conversation"]["primary"]["url"] = "https://changed.invalid"
        elif change == "conversation_key":
            env.entry.options["conversation"]["primary"]["api_key"] = "changed-secret"
        elif change == "conversation_fallback":
            env.entry.options["conversation"]["fallback"] = {
                "model": "fallback",
                "url": "https://fallback.invalid",
            }
        elif change == "module":
            env.engine.state["settings"]["modules"] = []
        elif change == "member_revision":
            env.engine.state["members"]["member"]["revision"] += 1
        elif change == "member_role":
            env.engine.state["members"]["member"]["role"] = "parent"
        elif change == "member_language":
            env.engine.state["members"]["member"]["language"] = "ru"
        elif change == "member_binding":
            env.engine.state["members"]["member"]["ha_user_id"] = "other-user"
        elif change == "ha_user_inactive":
            env.user.is_active = False

    env.service.before_return = mutate
    await article_api.article(env.hass, env.connection, _message())

    assert env.connection.results == []
    assert len(env.connection.errors) == 1
    assert env.connection.errors[0][0] == 11
    assert env.connection.errors[0][1] in {
        "article_unavailable",
        "conflict",
        "forbidden",
        "module_disabled",
    }
    assert env.connection.errors[0][2] == env.connection.errors[0][1]
    assert URL not in repr(env.connection.errors)


@pytest.mark.asyncio
async def test_auth_await_boundary_reloads_runtime_not_preawait_object(article_api):
    env = _environment()
    replacement = SimpleNamespace()
    # First lookup authorizes initial scope. The service's guard then resolves
    # the entry before awaiting HA auth; replace runtime during that await.
    env.auth.before_return.extend(
        [
            lambda: None,
            lambda: env.hass.data[DOMAIN]["entries"].__setitem__(ENTRY_ID, replacement),
        ]
    )

    await article_api.article(env.hass, env.connection, _message())

    assert env.connection.results == []
    assert env.connection.errors == [(11, "article_unavailable", "article_unavailable")]


@pytest.mark.asyncio
async def test_provider_failures_are_code_only_and_stale_scope_overrides_them(article_api):
    current = _environment()
    current.service.error = RuntimeError(f"provider leaked {URL}")
    await article_api.article(current.hass, current.connection, _message())
    assert current.connection.errors == [(11, "article_unavailable", "article_unavailable")]
    assert URL not in repr(current.connection.errors)

    stale = _environment()
    stale.service.error = DomainError("provider_timeout")
    stale.service.before_return = lambda: stale.entry.options["articles"].__setitem__(
        "enabled", False
    )
    await article_api.article(stale.hass, stale.connection, _message())
    assert stale.connection.errors == [(11, "article_unavailable", "article_unavailable")]


@pytest.mark.asyncio
async def test_cancellation_propagates_without_reply(article_api):
    env = _environment()
    waiting = asyncio.Event()

    async def block():
        waiting.set()
        await asyncio.Event().wait()

    env.service.before_return = block
    task = asyncio.create_task(article_api.article(env.hass, env.connection, _message()))
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert env.connection.results == []
    assert env.connection.errors == []


def test_source_view_is_bounded_and_fail_closed(article_api):
    env = _environment()
    assert article_api.source_view(env.entry, env.runtime, "member") == {
        "enabled": True,
        "configured": True,
        "allowed": True,
        "revision": ARTICLE_REVISION,
    }

    env.engine.state["canary_url"] = URL
    env.entry.options["provider_secret"] = "opaque-secret"
    child = _environment(role="child", allow_children=False)
    assert article_api.source_view(child.entry, child.runtime, "member") == {
        "enabled": True,
        "configured": True,
        "allowed": False,
        "revision": None,
    }
    assert URL not in repr(article_api.source_view(env.entry, env.runtime, "member"))
    assert "opaque-secret" not in repr(article_api.source_view(env.entry, env.runtime, "member"))

    disabled = _environment()
    disabled.entry.options["articles"]["enabled"] = False
    disabled.runtime.articles = None
    assert article_api.source_view(disabled.entry, disabled.runtime, "member") == {
        "enabled": False,
        "configured": True,
        "allowed": False,
        "revision": None,
    }

    env.entry.options["articles"]["revision"] = "bad"
    assert article_api.source_view(env.entry, env.runtime, "member") == {
        "enabled": False,
        "configured": False,
        "allowed": False,
        "revision": None,
    }
