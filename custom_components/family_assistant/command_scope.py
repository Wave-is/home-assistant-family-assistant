"""Immutable Home Assistant command scope with a synchronous Engine write fence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from homeassistant.config_entries import ConfigEntryState

from .const import DOMAIN, LANGUAGES, ROLES
from .domain.engine import Engine
from .domain.validation import DomainError
from .domain.validation import revision as strict_revision


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise DomainError("invalid_field" if field == "entry_id" else "forbidden", field)
    return value


def _entry_runtime(hass: Any, entry_id: str) -> tuple[Any, Any, Engine]:
    try:
        entry = hass.config_entries.async_get_entry(entry_id)
        domain_data = hass.data.get(DOMAIN)
        entries = domain_data.get("entries") if isinstance(domain_data, dict) else None
        runtime = entries.get(entry_id) if isinstance(entries, dict) else None
        engine = getattr(runtime, "engine", None)
        if (
            entry is None
            or getattr(entry, "domain", None) != DOMAIN
            or getattr(entry, "state", None) is not ConfigEntryState.LOADED
            or runtime is None
            or getattr(entry, "runtime_data", None) is not runtime
            or not isinstance(engine, Engine)
        ):
            raise DomainError("not_ready")
        return entry, runtime, engine
    except DomainError:
        raise
    except (AttributeError, KeyError, TypeError):
        raise DomainError("not_ready") from None


def _active_user(user: Any, user_id: str) -> bool:
    return (
        user is not None
        and getattr(user, "id", None) == user_id
        and getattr(user, "is_active", None) is True
    )


def _member(state: dict, actor: str, user_id: str) -> tuple[dict, int]:
    try:
        members = state.get("members") if isinstance(state, dict) else None
        member = members.get(actor) if isinstance(members, dict) else None
        if (
            not isinstance(member, dict)
            or member.get("id") != actor
            or member.get("active") is not True
            or member.get("ha_user_id") != user_id
            or member.get("role") not in ROLES
            or member.get("language") not in LANGUAGES
        ):
            raise DomainError("forbidden")
        return member, strict_revision(member.get("revision"))
    except DomainError as error:
        if error.code == "forbidden":
            raise
        raise DomainError("forbidden") from None
    except (AttributeError, KeyError, TypeError):
        raise DomainError("forbidden") from None


@dataclass(frozen=True)
class CommandScope:
    """One exact loaded runtime, HA identity and family-member epoch."""

    _hass: Any
    _entry: Any
    runtime: Any
    engine: Engine
    _user: Any
    _connection_user: Any | None
    user_id: str
    actor: str
    actor_revision: int
    role: str
    language: str

    def _structural(self) -> None:
        try:
            entry, runtime, engine = _entry_runtime(self._hass, self._entry.entry_id)
        except DomainError:
            raise DomainError("conflict") from None
        if entry is not self._entry or runtime is not self.runtime or engine is not self.engine:
            raise DomainError("conflict")

    def _identity(self, state: dict) -> None:
        if not _active_user(self._user, self.user_id) or (
            self._connection_user is not None
            and not _active_user(self._connection_user, self.user_id)
        ):
            raise DomainError("forbidden")
        member, revision = _member(state, self.actor, self.user_id)
        if (
            revision != self.actor_revision
            or member["role"] != self.role
            or member["language"] != self.language
        ):
            raise DomainError("conflict")

    async def check(self) -> None:
        """Re-read the HA user, then recheck the captured scope after that await."""
        self._structural()
        try:
            user = await self._hass.auth.async_get_user(self.user_id)
        except (AttributeError, KeyError, TypeError):
            raise DomainError("forbidden") from None
        if not _active_user(user, self.user_id):
            raise DomainError("forbidden")
        if user is not self._user:
            raise DomainError("conflict")
        self._structural()
        self._identity(self.engine.snapshot())

    def guard(self, state: dict) -> None:
        """Validate the captured scope synchronously against Engine's locked state."""
        self._structural()
        self._identity(state)

    async def after_execute(self, action, payload, operation_id, result) -> CommandScope:
        """Allow only the exact committed self-profile edit to advance this scope.

        A same-user owner rename/language edit legitimately advances its member
        revision. This is not a general rebase: the exact durable receipt and
        current row must match, and role, active state and HA binding cannot change.
        """
        try:
            await self.check()
            return self
        except DomainError as error:
            if error.code != "conflict":
                raise
        self._structural()
        if (
            self.role != "owner"
            or action != "members.save"
            or not isinstance(payload, dict)
            or payload.get("id") != self.actor
            or type(payload.get("revision")) is not int
            or payload["revision"] != self.actor_revision
            or not isinstance(result, dict)
            or type(result.get("revision")) is not int
            or result["revision"] != self.actor_revision + 1
        ):
            raise DomainError("conflict")
        state = self.engine.snapshot()
        current, revision = _member(state, self.actor, self.user_id)
        try:
            fingerprint = hashlib.sha256(
                json.dumps(
                    [self.actor, action, payload],
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode()
            ).hexdigest()
        except (TypeError, ValueError):
            raise DomainError("conflict") from None
        receipt = state.get("processed", {}).get(operation_id)
        if (
            current != result
            or current["role"] != self.role
            or not isinstance(receipt, dict)
            or receipt.get("fingerprint") != fingerprint
            or receipt.get("role") != self.role
            or receipt.get("result") != result
        ):
            raise DomainError("conflict")
        updated = replace(self, actor_revision=revision, language=current["language"])
        await updated.check()
        return updated

    def notify(self) -> None:
        """Notify only the exact still-current runtime after an awaited post-check."""
        self.guard(self.engine.snapshot())
        updated = getattr(self.runtime, "updated", None)
        if not callable(updated):
            raise DomainError("not_ready")
        updated()


async def capture(
    hass: Any,
    entry_id: str,
    user_id: str,
    connection_user: Any | None = None,
) -> CommandScope:
    """Capture one current HA command authority without crossing an await unchecked."""
    entry_id = _identifier(entry_id, "entry_id")
    user_id = _identifier(user_id, "user_id")
    entry_before, runtime_before, _engine_before = _entry_runtime(hass, entry_id)
    if connection_user is not None and not _active_user(connection_user, user_id):
        raise DomainError("forbidden")
    try:
        user = await hass.auth.async_get_user(user_id)
    except (AttributeError, KeyError, TypeError):
        raise DomainError("forbidden") from None
    if not _active_user(user, user_id):
        raise DomainError("forbidden")
    if connection_user is not None and not _active_user(connection_user, user_id):
        raise DomainError("forbidden")
    entry, runtime, engine = _entry_runtime(hass, entry_id)
    if entry is not entry_before or runtime is not runtime_before or engine is not _engine_before:
        raise DomainError("conflict")
    try:
        actor = engine.actor_for_ha(user_id)
    except (DomainError, AttributeError, KeyError, TypeError):
        raise DomainError("forbidden") from None
    member, actor_revision = _member(engine.snapshot(), actor, user_id)
    return CommandScope(
        _hass=hass,
        _entry=entry,
        runtime=runtime,
        engine=engine,
        _user=user,
        _connection_user=connection_user,
        user_id=user_id,
        actor=actor,
        actor_revision=actor_revision,
        role=member["role"],
        language=member["language"],
    )


__all__ = ["CommandScope", "capture"]
