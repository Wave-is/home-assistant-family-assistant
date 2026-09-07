"""Authenticated dashboard chat with immutable runtime and identity scope."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..domain.validation import DomainError, text
from ..domain.validation import revision as strict_revision
from .chat_service import conversation_digest

_HEX = set("0123456789abcdef")
_LANGUAGES = {"en", "ru", "uk"}
_ROLES = {"owner", "parent", "adult", "child"}
_MAX_ACTIVE = 8
_MAX_ACTIVE_PER_USER = 2
_active = 0
_active_users: dict[str, int] = {}


def _marker(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 32
        or value.lower() != value
        or any(character not in _HEX for character in value)
    ):
        raise DomainError("chat_unavailable")
    return value


@dataclass(frozen=True)
class _Scope:
    entry: Any
    runtime: Any
    engine: Any
    service: Any
    assistant: Any
    cascade: Any
    search: Any
    source_revision: str
    conversation_digest: str
    assistant_config_digest: str
    user: Any
    connection_user: Any
    user_id: str
    actor: str
    actor_revision: int
    role: str
    language: str


def _entry_runtime(hass: Any, entry_id: str) -> tuple[Any, Any]:
    try:
        entry = hass.config_entries.async_get_entry(entry_id)
        entries = hass.data.get(DOMAIN, {}).get("entries", {})
        runtime = entries.get(entry_id) if isinstance(entries, dict) else None
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or runtime is None
            or entry.runtime_data is not runtime
        ):
            raise DomainError("chat_unavailable")
        return entry, runtime
    except DomainError:
        raise
    except (AttributeError, KeyError, TypeError):
        raise DomainError("chat_unavailable") from None


def _member(state: dict, actor: str, user_id: str) -> dict:
    member = state.get("members", {}).get(actor)
    if (
        not isinstance(member, dict)
        or member.get("id") != actor
        or member.get("active") is not True
        or member.get("role") not in _ROLES
        or member.get("language") not in _LANGUAGES
        or member.get("ha_user_id") != user_id
    ):
        raise DomainError("forbidden")
    strict_revision(member.get("revision"))
    modules = state.get("settings", {}).get("modules")
    if not isinstance(modules, list) or "conversation" not in modules:
        raise DomainError("module_disabled")
    return member


async def _current_scope(hass: Any, connection: Any, entry_id: str) -> _Scope:
    if not isinstance(entry_id, str) or not entry_id:
        raise DomainError("invalid_field", "entry_id")
    try:
        _entry_runtime(hass, entry_id)
        user_id = connection.user.id
        if not isinstance(user_id, str) or not user_id:
            raise DomainError("forbidden")
        user = await hass.auth.async_get_user(user_id)
        if (
            user is None
            or user.id != user_id
            or user.is_active is not True
            or connection.user.id != user_id
        ):
            raise DomainError("forbidden")
        entry, runtime = _entry_runtime(hass, entry_id)
        engine = runtime.engine
        actor = engine.actor_for_ha(user_id)
        member = _member(engine.snapshot(), actor, user_id)
        service = runtime.chat
        if service is None:
            raise DomainError("chat_unavailable")
        assistant = runtime.assistant
        cascade = getattr(assistant, "cascade", None)
        search = getattr(assistant, "search", None)
        options_digest = conversation_digest(dict(entry.options).get("conversation"))
        if runtime.assistant_config_digest != options_digest:
            raise DomainError("conflict")
        return _Scope(
            entry=entry,
            runtime=runtime,
            engine=engine,
            service=service,
            assistant=assistant,
            cascade=cascade,
            search=search,
            source_revision=_marker(runtime.assistant_revision),
            conversation_digest=options_digest,
            assistant_config_digest=runtime.assistant_config_digest,
            user=user,
            connection_user=connection.user,
            user_id=user_id,
            actor=actor,
            actor_revision=strict_revision(member["revision"]),
            role=member["role"],
            language=member["language"],
        )
    except DomainError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError):
        raise DomainError("chat_unavailable") from None


def _same_scope(expected: _Scope, current: _Scope) -> bool:
    return all(
        (
            current.entry is expected.entry,
            current.runtime is expected.runtime,
            current.engine is expected.engine,
            current.service is expected.service,
            current.assistant is expected.assistant,
            current.cascade is expected.cascade,
            current.search is expected.search,
            current.source_revision == expected.source_revision,
            current.conversation_digest == expected.conversation_digest,
            current.assistant_config_digest == expected.assistant_config_digest,
            current.user is expected.user,
            current.connection_user is expected.connection_user,
            current.user_id == expected.user_id,
            current.actor == expected.actor,
            current.actor_revision == expected.actor_revision,
            current.role == expected.role,
            current.language == expected.language,
        )
    )


async def _async_guard(hass, connection, entry_id, expected):
    if not _same_scope(expected, await _current_scope(hass, connection, entry_id)):
        raise DomainError("conflict")


def _locked_guard(hass: Any, expected: _Scope, state: dict) -> None:
    entry, runtime = _entry_runtime(hass, expected.entry.entry_id)
    member = _member(state, expected.actor, expected.user_id)
    assistant = runtime.assistant
    if (
        entry is not expected.entry
        or runtime is not expected.runtime
        or runtime.engine is not expected.engine
        or runtime.chat is not expected.service
        or assistant is not expected.assistant
        or getattr(assistant, "cascade", None) is not expected.cascade
        or getattr(assistant, "search", None) is not expected.search
        or _marker(runtime.assistant_revision) != expected.source_revision
        or conversation_digest(dict(entry.options).get("conversation"))
        != expected.conversation_digest
        or runtime.assistant_config_digest != expected.assistant_config_digest
        or expected.user.id != expected.user_id
        or expected.user.is_active is not True
        or expected.connection_user.id != expected.user_id
        or expected.connection_user.is_active is not True
        or member["revision"] != expected.actor_revision
        or member["role"] != expected.role
        or member["language"] != expected.language
    ):
        raise DomainError("conflict")


def source_view(entry: Any, runtime: Any, actor: str) -> dict[str, Any]:
    """Return only capability flags and the opaque request generation."""
    enabled = configured = allowed = False
    revision = None
    try:
        state = runtime.engine.snapshot()
        member = state.get("members", {}).get(actor)
        modules = state.get("settings", {}).get("modules", [])
        enabled = isinstance(modules, list) and "conversation" in modules
        assistant = runtime.assistant
        conversation = dict(entry.options).get("conversation")
        options_digest = conversation_digest(conversation)
        primary = conversation.get("primary") if isinstance(conversation, dict) else None
        configured = bool(
            isinstance(conversation, dict)
            and conversation.get("enabled") is True
            and isinstance(primary, dict)
            and isinstance(primary.get("model"), str)
            and primary["model"].strip()
            and assistant is not None
            and getattr(assistant, "cascade", None) is not None
        )
        allowed = bool(
            enabled
            and runtime.chat is not None
            and runtime.assistant_config_digest == options_digest
            and isinstance(member, dict)
            and member.get("id") == actor
            and member.get("active") is True
            and member.get("role") in _ROLES
            and member.get("language") in _LANGUAGES
            and type(member.get("revision")) is int
            and member["revision"] > 0
        )
        revision = _marker(runtime.assistant_revision) if allowed else None
    except (AttributeError, KeyError, TypeError, ValueError, DomainError):
        enabled = configured = allowed = False
        revision = None
    return {
        "enabled": enabled,
        "configured": configured,
        "allowed": allowed,
        "revision": revision,
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/chat",
        vol.Required("entry_id"): str,
        vol.Required("text"): str,
        vol.Required("operation_id"): str,
        vol.Required("session_id"): str,
        vol.Required("actor_revision"): int,
        vol.Required("source_revision"): str,
    }
)
@websocket_api.async_response
async def chat(hass: Any, connection: Any, msg: dict) -> None:
    global _active
    scope = None
    admitted_user = None
    admitted = False
    try:
        content = text(msg["text"], "text", 4096)
        operation = text(msg["operation_id"], "operation_id", 100)
        session = text(msg["session_id"], "session_id", 100)
        requested_revision = strict_revision(msg["actor_revision"])
        requested_source = _marker(msg["source_revision"])
        admitted_user = getattr(connection.user, "id", None)
        if not isinstance(admitted_user, str) or not admitted_user:
            raise DomainError("forbidden")
        if _active >= _MAX_ACTIVE or _active_users.get(admitted_user, 0) >= _MAX_ACTIVE_PER_USER:
            raise DomainError("chat_busy")
        # Reserve before the first HA-auth await. Event-loop execution is
        # atomic until `_current_scope` yields.
        _active += 1
        _active_users[admitted_user] = _active_users.get(admitted_user, 0) + 1
        admitted = True
        scope = await _current_scope(hass, connection, msg["entry_id"])
        if requested_revision != scope.actor_revision or requested_source != scope.source_revision:
            raise DomainError("conflict")

        async def scope_check():
            await _async_guard(hass, connection, msg["entry_id"], scope)

        def guard(state):
            _locked_guard(hass, scope, state)

        def notify():
            try:
                guard(scope.engine.snapshot())
            except DomainError:
                return
            scope.runtime.updated()

        reply = await scope.service.answer(
            runtime=scope.runtime,
            actor=scope.actor,
            actor_revision=scope.actor_revision,
            content=content,
            operation_id=operation,
            session_id=session,
            now=dt_util.utcnow(),
            guard=guard,
            scope_check=scope_check,
            on_commit=notify,
        )
        await scope_check()
        connection.send_result(msg["id"], {"reply": reply})
    except asyncio.CancelledError:
        raise
    except (DomainError, OSError, TimeoutError) as error:
        code = (
            error.code
            if isinstance(error, DomainError)
            else "provider_timeout"
            if isinstance(error, TimeoutError)
            else "storage_error"
        )
        if scope is not None:
            try:
                await _async_guard(hass, connection, msg["entry_id"], scope)
            except DomainError as scope_error:
                code = scope_error.code
            except Exception:
                code = "chat_unavailable"
        connection.send_error(msg["id"], code, code)
    except Exception:
        code = "chat_unavailable"
        if scope is not None:
            try:
                await _async_guard(hass, connection, msg["entry_id"], scope)
            except DomainError as scope_error:
                code = scope_error.code
            except Exception:
                code = "chat_unavailable"
        connection.send_error(msg["id"], code, code)
    finally:
        if admitted and admitted_user is not None:
            _active -= 1
            remaining = _active_users[admitted_user] - 1
            if remaining:
                _active_users[admitted_user] = remaining
            else:
                _active_users.pop(admitted_user, None)


__all__ = ["chat", "source_view"]
