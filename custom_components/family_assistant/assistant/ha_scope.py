"""Immutable Home Assistant user/runtime scope for Assist and LLM tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntryState

from ..const import DOMAIN
from ..domain.validation import DomainError
from ..domain.validation import revision as strict_revision
from .chat_service import ScopedEngine, conversation_digest

_HEX = set("0123456789abcdef")
_LANGUAGES = {"en", "ru", "uk"}
_ROLES = {"owner", "parent", "adult", "child"}


def _marker(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 32
        or value.lower() != value
        or any(character not in _HEX for character in value)
    ):
        raise DomainError("chat_unavailable")
    return value


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


@dataclass(frozen=True)
class HAScope:
    hass: Any
    entry: Any
    runtime: Any
    engine: Any
    chat: Any
    assistant: Any
    cascade: Any
    search: Any
    source_revision: str
    config_digest: str
    user: Any
    user_id: str
    actor: str
    actor_revision: int
    role: str
    language: str

    async def check(self) -> None:
        current = await capture(
            self.hass,
            self.entry.entry_id,
            self.user_id,
            expected_runtime=self.runtime,
        )
        if not self.same(current):
            raise DomainError("conflict")

    def same(self, current: HAScope) -> bool:
        return all(
            (
                current.entry is self.entry,
                current.runtime is self.runtime,
                current.engine is self.engine,
                current.chat is self.chat,
                current.assistant is self.assistant,
                current.cascade is self.cascade,
                current.search is self.search,
                current.source_revision == self.source_revision,
                current.config_digest == self.config_digest,
                current.user is self.user,
                current.user_id == self.user_id,
                current.actor == self.actor,
                current.actor_revision == self.actor_revision,
                current.role == self.role,
                current.language == self.language,
            )
        )

    def locked_guard(self, state: dict) -> None:
        entry, runtime = _entry_runtime(self.hass, self.entry.entry_id)
        member = _member(state, self.actor, self.user_id)
        assistant = runtime.assistant
        if (
            entry is not self.entry
            or runtime is not self.runtime
            or runtime.engine is not self.engine
            or runtime.chat is not self.chat
            or assistant is not self.assistant
            or getattr(assistant, "cascade", None) is not self.cascade
            or getattr(assistant, "search", None) is not self.search
            or _marker(runtime.assistant_revision) != self.source_revision
            or conversation_digest(dict(entry.options).get("conversation")) != self.config_digest
            or runtime.assistant_config_digest != self.config_digest
            or self.user.id != self.user_id
            or self.user.is_active is not True
            or member["revision"] != self.actor_revision
            or member["role"] != self.role
            or member["language"] != self.language
        ):
            raise DomainError("conflict")

    def notify(self) -> None:
        try:
            self.locked_guard(self.engine.snapshot())
        except DomainError:
            return
        self.runtime.updated()

    def scoped_engine(self) -> ScopedEngine:
        return ScopedEngine(self.engine, self.locked_guard, self.notify)


async def capture(
    hass: Any,
    entry_id: str,
    user_id: str | None,
    *,
    expected_runtime: Any | None = None,
) -> HAScope:
    """Capture only a current active HA-bound non-guest household identity."""
    if not isinstance(entry_id, str) or not entry_id or not isinstance(user_id, str) or not user_id:
        raise DomainError("forbidden")
    _entry_runtime(hass, entry_id)
    try:
        user = await hass.auth.async_get_user(user_id)
        if user is None or user.id != user_id or user.is_active is not True:
            raise DomainError("forbidden")
        entry, runtime = _entry_runtime(hass, entry_id)
        if expected_runtime is not None and runtime is not expected_runtime:
            raise DomainError("conflict")
        engine = runtime.engine
        actor = engine.actor_for_ha(user_id)
        member = _member(engine.snapshot(), actor, user_id)
        chat = runtime.chat
        if chat is None:
            raise DomainError("chat_unavailable")
        digest = conversation_digest(dict(entry.options).get("conversation"))
        if runtime.assistant_config_digest != digest:
            raise DomainError("conflict")
        assistant = runtime.assistant
        return HAScope(
            hass=hass,
            entry=entry,
            runtime=runtime,
            engine=engine,
            chat=chat,
            assistant=assistant,
            cascade=getattr(assistant, "cascade", None),
            search=getattr(assistant, "search", None),
            source_revision=_marker(runtime.assistant_revision),
            config_digest=digest,
            user=user,
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


async def retire_legacy_refs(scope: HAScope, now) -> None:
    """Discard pre-epoch Assist refs; never migrate them to a new identity."""

    memory = scope.engine.snapshot().get("memory", {})
    if not isinstance(memory, dict) or "conversation_refs" not in memory:
        return

    def remove(ctx):
        ctx.state.setdefault("memory", {}).pop("conversation_refs", None)

    await scope.scoped_engine().system_update("assist_context_migration", now, remove)


__all__ = ["HAScope", "capture", "retire_legacy_refs"]
