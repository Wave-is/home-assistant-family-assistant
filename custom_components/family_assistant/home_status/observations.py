"""Current-role/current-HA-permission on-demand source reads, never retained."""

import inspect

from ..domain.validation import DomainError
from . import config, facts


def ha_access(hass):
    from homeassistant.auth.permissions.const import POLICY_READ
    from homeassistant.helpers import entity_registry

    return entity_registry.async_get(hass), POLICY_READ


def authority(hass, entry, runtime, actor_id, user):
    state = runtime.engine.snapshot()
    actor = state.get("members", {}).get(actor_id)
    if (
        hass.config_entries.async_get_entry(entry.entry_id) is not entry
        or getattr(entry, "runtime_data", None) is not runtime
        or not isinstance(actor, dict)
        or actor.get("active") is not True
        or actor.get("role") not in config.ROLES
        or getattr(user, "is_active", None) is not True
        or actor.get("ha_user_id") != getattr(user, "id", None)
        or runtime.engine.actor_for_ha(user.id) != actor_id
    ):
        raise DomainError("forbidden")
    if runtime.engine.shadow_mode:
        raise DomainError("migration_shadow_read_only")
    if config.MODULE not in state["settings"]["modules"]:
        raise DomainError("module_disabled")
    return actor, config.from_options(entry.options)


def readable(registry, user, policy, source):
    try:
        row = registry.async_get(source["entity_id"])
        return (
            row is not None
            and row.entity_id == source["entity_id"]
            and row.id == source["registry_id"]
            and user.permissions.check_entity(source["entity_id"], policy) is True
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def select(hass, entry, runtime, actor_id, user, query):
    query = config.request(**query)
    actor, configured = authority(hass, entry, runtime, actor_id, user)
    registry, policy = ha_access(hass)
    sources = [
        source
        for source in config.visible_sources(configured, actor["role"], query)
        if readable(registry, user, policy, source)
    ]
    return configured, sources


def configuration_marker(runtime, configured):
    """A module/settings epoch cannot revive an older queued descriptor."""
    return config.marker(
        {
            "config": configured,
            "settings_revision": runtime.engine.snapshot().get("settings_revision", 1),
        }
    )


def access_marker(hass, entry, runtime, actor_id, user):
    """Opaque revocation metadata only: never call states.get from a family refresh."""
    try:
        configured, sources = select(hass, entry, runtime, actor_id, user, config.request())
        return _access_marker(runtime, actor_id, user, configured, sources)
    except (DomainError, AttributeError, KeyError, TypeError, ValueError):
        return None


def _access_marker(runtime, actor_id, user, configured, sources):
    actor = runtime.engine.snapshot()["members"][actor_id]
    return config.marker(
        {
            "configuration": configuration_marker(runtime, configured),
            "actor": actor_id,
            "revision": actor["revision"],
            "user": user.id,
            "permitted_sources": [source["id"] for source in sources],
        }
    )


def project(hass, entry, runtime, actor_id, user, now, *, section="home", group_id=None):
    configured, sources = select(
        hass, entry, runtime, actor_id, user, config.request(section, group_id)
    )
    rows = []
    for source in sources:
        # select checked both role and source ACL before even invoking states.get.
        row = facts.normalize(
            source, hass.states.get(source["entity_id"]), now, configured["max_age_seconds"]
        )
        rows.append((source, row))
    return {
        "access_marker": _access_marker(runtime, actor_id, user, configured, sources),
        "generated_at": now.isoformat(),
        "config_revision": configured["revision"],
        "max_age_seconds": configured["max_age_seconds"],
        "energy": [row for source, row in rows if source["section"] == "energy"],
        "active": [row for source, row in rows if source["section"] == "active"],
        "groups": [
            {
                "id": group["id"],
                "title": group["title"],
                "rows": [row for source, row in rows if source["group_id"] == group["id"]],
            }
            for group in configured["groups"]
            if any(source["group_id"] == group["id"] for source, _ in rows)
        ],
    }


async def actor_user(hass, entry, runtime, actor_id, guard):
    """Resolve the explicit sender's HA account, fencing the await boundary."""
    guard(runtime.engine.snapshot())
    before = runtime.engine.snapshot()["members"].get(actor_id)
    marker = configuration_marker(runtime, config.from_options(entry.options))
    if not isinstance(before, dict) or not before.get("ha_user_id"):
        raise DomainError("forbidden")
    user = hass.auth.async_get_user(before["ha_user_id"])
    if inspect.isawaitable(user):
        user = await user
    guard(runtime.engine.snapshot())
    after, configured = authority(hass, entry, runtime, actor_id, user)
    if after != before or configuration_marker(runtime, configured) != marker:
        raise DomainError("conflict")
    return user
