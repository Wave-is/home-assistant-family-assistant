"""Optional post-create handoff to the read-only guided Options flow."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from weakref import WeakValueDictionary

from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlowResult,
    FlowType,
)
from homeassistant.data_entry_flow import FlowResultType

from .const import DOMAIN
from .domain.validation import revision as strict_revision

_LOGGER = logging.getLogger(__name__)

HANDOFF_KEY = "guided_onboarding_handoff"
_GUIDED_STEP = "guided_onboarding"
_LOCKS_KEY = "_guided_onboarding_handoff_locks"


@dataclass(frozen=True)
class _Scope:
    runtime: object
    actor: str
    actor_revision: int


def is_guided_handoff(value: object) -> bool:
    """Return whether value is the exact internal handoff sentinel."""
    return type(value) is dict and set(value) == {HANDOFF_KEY} and value[HANDOFF_KEY] is True


def _flow_id(flow: object) -> str | None:
    if not isinstance(flow, Mapping):
        return None
    value = flow.get("flow_id")
    return value if isinstance(value, str) and value else None


def _entry_flows(manager, entry_id: str) -> list[Mapping[str, Any]]:
    flows = manager.async_progress_by_handler(entry_id, include_uninitialized=True)
    if not isinstance(flows, list):
        raise TypeError("invalid options-flow progress")
    return [flow for flow in flows if isinstance(flow, Mapping)]


def _handoff_flows(manager, entry_id: str, user_id: str) -> list[Mapping[str, Any]]:
    by_handler = {
        flow_id: flow
        for flow in _entry_flows(manager, entry_id)
        if (flow_id := _flow_id(flow)) is not None
    }
    by_input = manager.async_progress_by_init_data_type(
        dict,
        is_guided_handoff,
        include_uninitialized=True,
    )
    if not isinstance(by_input, list):
        raise TypeError("invalid options-flow initialization progress")
    matches = []
    for candidate in by_input:
        flow_id = _flow_id(candidate)
        flow = by_handler.get(flow_id) if flow_id is not None else None
        if flow is None:
            continue
        context = flow.get("context")
        if (
            flow.get("handler") == entry_id
            and isinstance(context, Mapping)
            and context.get("source") == SOURCE_USER
            and context.get("user_id") == user_id
        ):
            matches.append(flow)
    return matches


def _live_landing(manager, flow: Mapping[str, Any], entry_id: str, user_id: str) -> bool:
    flow_id = _flow_id(flow)
    if flow_id is None:
        return False
    live = manager.async_get(flow_id)
    if not isinstance(live, Mapping):
        return False
    context = live.get("context")
    return (
        live.get("handler") == entry_id
        and live.get("step_id") == _GUIDED_STEP
        and isinstance(context, Mapping)
        and context.get("source") == SOURCE_USER
        and context.get("user_id") == user_id
    )


def _abort_new_handoffs(manager, entry_id: str, user_id: str, before: set[str]) -> None:
    """Abort only matching handoff flows introduced after the snapshot."""
    try:
        candidates = _handoff_flows(manager, entry_id, user_id)
    except Exception:  # The optional cleanup must not replace the original outcome.
        return
    for candidate in candidates:
        flow_id = _flow_id(candidate)
        if flow_id is None or flow_id in before:
            continue
        try:
            manager.async_abort(flow_id)
        except Exception:  # A concurrent Core cleanup is already a safe outcome.
            _LOGGER.debug("Optional guided onboarding flow was already unavailable")


async def _current_owner(hass, entry: ConfigEntry, user_id: str) -> _Scope | None:
    """Check the exact current entry, runtime, HA user and household owner."""
    try:
        manager = getattr(hass, "config_entries", None)
        if (
            manager is None
            or manager.async_get_entry(entry.entry_id) is not entry
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            return None
        user = await hass.auth.async_get_user(user_id)
        if (
            manager.async_get_entry(entry.entry_id) is not entry
            or entry.state is not ConfigEntryState.LOADED
            or user is None
            or user.id != user_id
            or user.is_active is not True
            or user.is_admin is not True
        ):
            return None
        domain_data = getattr(hass, "data", {}).get(DOMAIN)
        entries = domain_data.get("entries") if isinstance(domain_data, dict) else None
        runtime = entries.get(entry.entry_id) if isinstance(entries, dict) else None
        if runtime is None or getattr(entry, "runtime_data", None) is not runtime:
            return None
        actor = runtime.engine.actor_for_ha(user_id)
        projection = runtime.engine.view(actor)
        state = runtime.engine.snapshot()
        members = state.get("members") if isinstance(state, dict) else None
        member = members.get(actor) if isinstance(members, dict) else None
    except Exception:
        return None
    if (
        not isinstance(actor, str)
        or not isinstance(projection, dict)
        or projection.get("role") != "owner"
        or not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") != "owner"
        or member.get("ha_user_id") != user_id
    ):
        return None
    try:
        actor_revision = strict_revision(member.get("revision"))
    except Exception:
        return None
    return _Scope(runtime, actor, actor_revision)


def _same_scope(left: _Scope, right: _Scope | None) -> bool:
    return (
        right is not None
        and left.runtime is right.runtime
        and left.actor == right.actor
        and left.actor_revision == right.actor_revision
    )


def _handoff_lock(hass, entry_id: str) -> asyncio.Lock:
    # The lock survives runtime replacement while any attempt holds/waits on it.
    # Weak values avoid retaining removed entry IDs after the last attempt ends.
    locks = hass.data[DOMAIN].setdefault(_LOCKS_KEY, WeakValueDictionary())
    if not isinstance(locks, WeakValueDictionary):
        raise TypeError("invalid guided onboarding lock registry")
    lock = locks.get(entry_id)
    if lock is None:
        lock = asyncio.Lock()
        locks[entry_id] = lock
    return lock


async def async_post_create_handoff(
    hass,
    result: ConfigFlowResult,
    context: Mapping[str, Any],
) -> ConfigFlowResult:
    """Attach the optional exact-entry guided Options flow when it is safe."""
    if "next_flow" in result or context.get("source") != SOURCE_USER:
        return result
    user_id = context.get("user_id")
    entry = result.get("result")
    if not isinstance(user_id, str) or not user_id or not isinstance(entry, ConfigEntry):
        return result
    initial_scope = await _current_owner(hass, entry, user_id)
    if initial_scope is None:
        return result
    try:
        lock = _handoff_lock(hass, entry.entry_id)
    except Exception:
        _LOGGER.warning("Automatic guided onboarding handoff was skipped")
        return result
    async with lock:
        locked_scope = await _current_owner(hass, entry, user_id)
        if not _same_scope(initial_scope, locked_scope):
            return result
        manager = None
        before: set[str] = set()
        try:
            manager = hass.config_entries.options
            all_flows = _entry_flows(manager, entry.entry_id)
            before = {flow_id for flow in all_flows if (flow_id := _flow_id(flow)) is not None}
            matching = _handoff_flows(manager, entry.entry_id, user_id)
            if all_flows:
                if len(all_flows) != 1 or len(matching) != 1:
                    return result
                if not _live_landing(manager, matching[0], entry.entry_id, user_id):
                    return result
                if not _same_scope(locked_scope, await _current_owner(hass, entry, user_id)):
                    return result
                result["next_flow"] = (FlowType.OPTIONS_FLOW, _flow_id(matching[0]))
                return result

            guided = await manager.async_init(
                entry.entry_id,
                context={"source": SOURCE_USER, "user_id": user_id},
                data={HANDOFF_KEY: True},
            )
            flow_id = _flow_id(guided)
            if (
                not isinstance(guided, Mapping)
                or guided.get("type") is not FlowResultType.MENU
                or guided.get("step_id") != _GUIDED_STEP
                or flow_id is None
            ):
                _abort_new_handoffs(manager, entry.entry_id, user_id, before)
                return result
            current_flows = _entry_flows(manager, entry.entry_id)
            current_matching = _handoff_flows(manager, entry.entry_id, user_id)
            if (
                len(current_flows) != 1
                or len(current_matching) != 1
                or _flow_id(current_matching[0]) != flow_id
                or not _live_landing(manager, current_matching[0], entry.entry_id, user_id)
                or not _same_scope(locked_scope, await _current_owner(hass, entry, user_id))
            ):
                _abort_new_handoffs(manager, entry.entry_id, user_id, before)
                return result
            result["next_flow"] = (FlowType.OPTIONS_FLOW, flow_id)
            return result
        except asyncio.CancelledError:
            if manager is not None:
                _abort_new_handoffs(manager, entry.entry_id, user_id, before)
            raise
        except Exception:
            if manager is not None:
                _abort_new_handoffs(manager, entry.entry_id, user_id, before)
            _LOGGER.warning("Automatic guided onboarding handoff was skipped")
            return result
