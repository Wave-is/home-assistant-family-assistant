"""Authenticated explicit article requests with immutable runtime scope."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..domain.validation import DomainError
from ..domain.validation import revision as strict_revision
from .article_options import _conversation_ready, _digest, _policy
from .chat_service import conversation_digest as provider_digest

_LANGUAGES = {"en", "ru", "uk"}
_ROLES = {"owner", "parent", "adult", "child"}
_HEX = set("0123456789abcdef")


@dataclass(frozen=True)
class _Scope:
    entry: Any
    runtime: Any
    engine: Any
    service: Any
    assistant: Any
    cascade: Any
    article_revision: str
    policy_revision: str
    conversation_digest: str
    policy_enabled: bool
    allow_children: bool
    user_id: str
    actor: str
    actor_revision: int
    role: str
    language: str


def _marker(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 32
        or value.lower() != value
        or any(character not in _HEX for character in value)
    ):
        raise DomainError("article_unavailable")
    return value


def _entry_runtime(hass: Any, entry_id: str) -> tuple[Any, Any]:
    try:
        entry = hass.config_entries.async_get_entry(entry_id)
        domain_data = hass.data.get(DOMAIN)
        entries = domain_data.get("entries") if isinstance(domain_data, dict) else None
        runtime = entries.get(entry_id) if isinstance(entries, dict) else None
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or runtime is None
            or getattr(entry, "runtime_data", None) is not runtime
        ):
            raise DomainError("article_unavailable")
        return entry, runtime
    except DomainError:
        raise
    except (AttributeError, KeyError, TypeError):
        raise DomainError("article_unavailable") from None


async def _current_scope(hass: Any, connection: Any, entry_id: str) -> _Scope:
    try:
        if not isinstance(entry_id, str) or not entry_id:
            raise DomainError("invalid_field", "entry_id")
        connection_user = connection.user
        user_id = connection_user.id
        if not isinstance(user_id, str) or not user_id:
            raise DomainError("forbidden")
        # Resolve once before the await, then discard it. The authoritative
        # entry/runtime lookup below happens only after HA user validation.
        _entry_runtime(hass, entry_id)
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
        actor_id = engine.actor_for_ha(user_id)
        state = engine.snapshot()
        members = state.get("members") if isinstance(state, dict) else None
        actor = members.get(actor_id) if isinstance(members, dict) else None
        if (
            not isinstance(actor_id, str)
            or not isinstance(actor, dict)
            or actor.get("id") != actor_id
            or actor.get("active") is not True
            or actor.get("role") not in _ROLES
            or actor.get("ha_user_id") != user_id
            or actor.get("language") not in _LANGUAGES
        ):
            raise DomainError("forbidden")
        actor_revision = strict_revision(actor.get("revision"))
        modules = state.get("settings", {}).get("modules")
        if not isinstance(modules, list) or "conversation" not in modules:
            raise DomainError("module_disabled")
        options = dict(entry.options)
        conversation_digest = _digest(options.get("conversation"))
        if runtime.assistant_config_digest != provider_digest(options.get("conversation")):
            raise DomainError("article_unavailable")
        policy = _policy(options)
        if policy.get("enabled") is not True:
            raise DomainError("article_unavailable")
        policy_revision = _marker(policy.get("revision"))
        allow_children = policy.get("allow_children")
        if type(allow_children) is not bool:
            raise DomainError("article_unavailable")
        if actor["role"] == "child" and not allow_children:
            raise DomainError("forbidden")
        if not _conversation_ready(runtime, state, options):
            raise DomainError("provider_not_configured")
        assistant = runtime.assistant
        service = runtime.articles
        article_revision = _marker(runtime.article_revision)
        cascade = getattr(assistant, "cascade", None)
        if service is None or cascade is None or getattr(service, "cascade", None) is not cascade:
            raise DomainError("article_unavailable")
        return _Scope(
            entry=entry,
            runtime=runtime,
            engine=engine,
            service=service,
            assistant=assistant,
            cascade=cascade,
            article_revision=article_revision,
            policy_revision=policy_revision,
            conversation_digest=conversation_digest,
            policy_enabled=True,
            allow_children=allow_children,
            user_id=user_id,
            actor=actor_id,
            actor_revision=actor_revision,
            role=actor["role"],
            language=actor["language"],
        )
    except DomainError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError):
        raise DomainError("article_unavailable") from None


def _same_scope(expected: _Scope, current: _Scope) -> bool:
    return (
        current.entry is expected.entry
        and current.runtime is expected.runtime
        and current.engine is expected.engine
        and current.service is expected.service
        and current.assistant is expected.assistant
        and current.cascade is expected.cascade
        and current.article_revision == expected.article_revision
        and current.policy_revision == expected.policy_revision
        and current.conversation_digest == expected.conversation_digest
        and current.policy_enabled == expected.policy_enabled
        and current.allow_children == expected.allow_children
        and current.user_id == expected.user_id
        and current.actor == expected.actor
        and current.actor_revision == expected.actor_revision
        and current.role == expected.role
        and current.language == expected.language
    )


async def _guard(hass: Any, connection: Any, entry_id: str, expected: _Scope) -> None:
    current = await _current_scope(hass, connection, entry_id)
    if not _same_scope(expected, current):
        raise DomainError("conflict")


def _source_policy(entry: Any) -> tuple[dict, bool]:
    try:
        options = dict(entry.options)
        return _policy(options), True
    except (DomainError, AttributeError, TypeError, ValueError):
        return {}, False


def source_view(entry: Any, runtime: Any, actor: str) -> dict[str, Any]:
    """Project only policy/readiness flags and an opaque runtime generation."""
    policy, valid_policy = _source_policy(entry)
    enabled = configured = allowed = False
    generation: str | None = None
    try:
        state = runtime.engine.snapshot()
        member = state.get("members", {}).get(actor)
        role = member.get("role") if isinstance(member, dict) else None
        permission = bool(
            valid_policy
            and isinstance(actor, str)
            and isinstance(member, dict)
            and member.get("id") == actor
            and member.get("active") is True
            and role in _ROLES
            and member.get("language") in _LANGUAGES
            and valid_revision(member.get("revision"))
            and (role != "child" or policy.get("allow_children") is True)
        )
        enabled = bool(valid_policy and policy.get("enabled") is True)
        options = dict(entry.options)
        conversation = options.get("conversation")
        primary = conversation.get("primary") if isinstance(conversation, dict) else None
        configured = bool(
            valid_policy
            and isinstance(conversation, dict)
            and conversation.get("enabled") is True
            and isinstance(primary, dict)
            and isinstance(primary.get("model"), str)
            and bool(primary["model"].strip())
        )
        assistant = runtime.assistant
        service = runtime.articles
        marker = runtime.article_revision
        cascade = getattr(assistant, "cascade", None)
        allowed = bool(
            permission
            and enabled
            and configured
            and runtime.assistant_config_digest == provider_digest(conversation)
            and _conversation_ready(runtime, state, options)
            and service is not None
            and cascade is not None
            and getattr(service, "cascade", None) is cascade
            and isinstance(marker, str)
            and len(marker) == 32
            and marker.lower() == marker
            and all(character in _HEX for character in marker)
        )
        generation = marker if allowed else None
    except (AttributeError, KeyError, TypeError, ValueError, DomainError):
        enabled = configured = allowed = False
        generation = None
    return {
        "enabled": enabled,
        "configured": configured,
        "allowed": allowed,
        "revision": generation,
    }


def valid_revision(value: Any) -> bool:
    return type(value) is int and 1 <= value <= 2**53 - 1


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/article",
        vol.Required("entry_id"): str,
        vol.Required("url"): str,
        vol.Required("operation_id"): str,
        vol.Required("source_revision"): str,
    }
)
@websocket_api.async_response
async def article(hass: Any, connection: Any, msg: dict) -> None:
    scope = None
    try:
        scope = await _current_scope(hass, connection, msg["entry_id"])
        if _marker(msg["source_revision"]) != scope.article_revision:
            raise DomainError("conflict")

        async def scope_check() -> None:
            await _guard(hass, connection, msg["entry_id"], scope)

        result = await scope.service.answer(
            scope.actor,
            scope.actor_revision,
            scope.language,
            msg["url"],
            msg["operation_id"],
            dt_util.utcnow(),
            scope_revision=scope.article_revision,
            scope_check=scope_check,
        )
        await scope_check()
        connection.send_result(msg["id"], result)
    except asyncio.CancelledError:
        raise
    except (DomainError, OSError, TimeoutError) as error:
        code = error.code if isinstance(error, DomainError) else "article_unavailable"
        if scope is not None:
            try:
                await _guard(hass, connection, msg["entry_id"], scope)
            except DomainError as scope_error:
                code = scope_error.code
            except Exception:
                code = "article_unavailable"
        connection.send_error(msg["id"], code, code)
    except Exception:
        code = "article_unavailable"
        if scope is not None:
            try:
                await _guard(hass, connection, msg["entry_id"], scope)
            except DomainError as scope_error:
                code = scope_error.code
            except Exception:
                code = "article_unavailable"
        connection.send_error(msg["id"], code, code)


__all__ = ["article", "source_view"]
