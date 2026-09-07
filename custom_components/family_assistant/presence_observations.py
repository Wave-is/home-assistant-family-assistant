"""Ephemeral, permission-checked Home Assistant presence observations."""

from __future__ import annotations

from copy import deepcopy

from .domain import presence
from .domain.validation import DomainError
from .domain.validation import revision as strict_revision

EMPTY = {"self": None, "shared": []}


def _ha_access(hass):
    """Load Home Assistant APIs lazily so the pure domain suite needs no HA install."""
    from homeassistant.auth.permissions.const import POLICY_READ
    from homeassistant.helpers import entity_registry

    return entity_registry.async_get(hass), POLICY_READ


def _current_actor(hass, entry, runtime, actor_id, user, state):
    if (
        getattr(entry, "runtime_data", None) is not runtime
        or not isinstance(actor_id, str)
        or not actor_id
        or not isinstance(getattr(user, "id", None), str)
        or not user.id
        or getattr(user, "is_active", None) is not True
    ):
        return None
    config_entries = getattr(hass, "config_entries", None)
    get_entry = getattr(config_entries, "async_get_entry", None)
    if not callable(get_entry) or get_entry(getattr(entry, "entry_id", None)) is not entry:
        return None
    member = state.get("members", {}).get(actor_id) if isinstance(state, dict) else None
    try:
        valid = (
            isinstance(member, dict)
            and member.get("id") == actor_id
            and member.get("active") is True
            and member.get("role") != "guest"
            and strict_revision(member.get("revision")) >= 1
            and member.get("ha_user_id") == user.id
            and runtime.engine.actor_for_ha(user.id) == actor_id
        )
    except (DomainError, AttributeError, KeyError, TypeError, ValueError):
        return None
    return member if valid else None


def _registered(registry, entity_id: str) -> bool:
    try:
        record = registry.async_get(entity_id)
        return record is not None and getattr(record, "entity_id", None) == entity_id
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _may_read(user, entity_id: str, policy_read) -> bool:
    try:
        return user.permissions.check_entity(entity_id, policy_read) is True
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _observation(hass, entity_id: str) -> dict | None:
    try:
        observed = hass.states.get(entity_id)
        if observed is None:
            return None
        value = observed.state
        try:
            reported = observed.last_reported
        except AttributeError:
            reported = observed.last_updated
        return {"state": value, "observed_at": reported}
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def project(hass, entry, runtime, actor_id: str, user, now) -> dict:
    """Return one synchronous, non-retained, authenticated presence projection."""
    try:
        state = runtime.engine.snapshot()
    except (AttributeError, KeyError, TypeError, ValueError):
        return deepcopy(EMPTY)
    actor = _current_actor(hass, entry, runtime, actor_id, user, state)
    if actor is None:
        return deepcopy(EMPTY)
    try:
        options = deepcopy(dict(entry.options))
        selected = presence.select_sources(state, actor, options)
    except (DomainError, AttributeError, KeyError, TypeError, ValueError):
        options, selected = {}, {}
    observations = {}
    try:
        registry, policy_read = _ha_access(hass)
    except (ImportError, AttributeError, KeyError, TypeError, ValueError):
        registry, policy_read = None, None
    if registry is not None:
        for member_id, entity_id in selected.items():
            if not _registered(registry, entity_id) or not _may_read(user, entity_id, policy_read):
                continue
            value = _observation(hass, entity_id)
            if value is not None:
                observations[member_id] = value
    return presence.view(state, actor, options, observations, now)
