"""Ephemeral HA readings under separate notification-purpose consent and HA ACL."""

from __future__ import annotations

from .domain import presence, presence_delivery
from .domain.validation import DomainError
from .presence_observations import (
    _current_actor,
    _ha_access,
    _may_read,
    _observation,
    _registered,
)


async def prepare(hass, entry, runtime, state, guard):
    """Resolve current consenting HA accounts; no entity state is read here."""
    guard()
    users = {}
    for member_id in state.get("members", {}):
        policy = presence_delivery.effective_policy(state, member_id)
        if policy is None or policy["approved_by"] in users:
            continue
        approver = state["members"][policy["approved_by"]]
        users[approver["id"]] = await hass.auth.async_get_user(approver["ha_user_id"])
        guard()

    def observe(current, member, policy, now):
        try:
            guard()
            if presence_delivery.effective_policy(current, member["id"]) != policy:
                return False
            user = users.get(policy["approved_by"])
            actor = _current_actor(hass, entry, runtime, policy["approved_by"], user, current)
            if actor is None or actor["revision"] != policy["approved_by_revision"]:
                return False
            config = presence.validate_options(dict(entry.options))
            source = config["sources"].get(member["id"])
            if source is None:
                return False
            binding = presence._valid_binding(current, member["id"], source)
            if binding is None or binding["revision"] != policy["binding_revision"]:
                return False
            registry, read_policy = _ha_access(hass)
            entity_id = source.get("entity_id")
            if not _registered(registry, entity_id) or not _may_read(user, entity_id, read_policy):
                return False
            observed = _observation(hass, entity_id)
            status, _reason, _at = presence._observation(observed, now, config["max_age_seconds"])
            return status == "reported_home"
        except (DomainError, AttributeError, KeyError, TypeError, ValueError, ImportError):
            return False

    return observe
