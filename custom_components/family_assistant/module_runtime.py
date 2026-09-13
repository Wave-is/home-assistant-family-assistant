"""Targeted reconciliation after canonical module switches, without a HA reload."""

import asyncio

from .const import DOMAIN
from .domain.validation import DomainError


def signature(runtime):
    return frozenset(runtime.engine.snapshot()["settings"]["modules"])


def watch(hass, entry, runtime):
    """Observe all canonical writers; never start another Telegram poller."""
    runtime.module_signature = signature(runtime)

    def changed():
        if runtime.engine.shadow_mode or runtime.module_signature == signature(runtime):
            return
        if runtime.module_task is not None and not runtime.module_task.done():
            return
        runtime.module_task = hass.async_create_task(
            reconcile(hass, entry, runtime), "Family Assistant module settings"
        )

    runtime.listeners.add(changed)


async def reconcile(hass, entry, runtime):
    from .runtime import (
        async_configure_assistant,
        async_configure_network,
        async_configure_online_school,
        async_stop_articles,
        async_stop_chat,
    )

    data = hass.data.get(DOMAIN, {})
    lock = data.setdefault("setup_lock", asyncio.Lock())
    desired = None
    try:
        while True:
            async with lock:
                if (
                    data.get("entries", {}).get(entry.entry_id) is not runtime
                    or entry.runtime_data is not runtime
                    or runtime.engine.shadow_mode
                ):
                    return
                coordinator = data.get("backup")
                if coordinator is None:
                    async with runtime.options_lock:
                        desired = signature(runtime)
                        changed = desired ^ (runtime.module_signature or frozenset())
                        if "conversation" in changed:
                            await async_stop_chat(runtime)
                            await async_stop_articles(runtime)
                            async_configure_assistant(hass, entry)
                        if "mikrotik" in changed:
                            await async_configure_network(hass, entry)
                        if "school" in changed:
                            await async_configure_online_school(hass, entry)
                        runtime.module_signature = desired
                        runtime.health.pop("module_settings", None)
                    break
            await coordinator.released.wait()
    except (DomainError, OSError, ValueError):
        # Do not spin if configured credentials/CA settings cannot be loaded.
        # A later settings/Options update can retry; expose failure, not success.
        runtime.module_signature = desired
        runtime.health["module_settings"] = "not_ready"
    finally:
        runtime.module_task = None
    if data.get("entries", {}).get(entry.entry_id) is runtime:
        runtime.updated()
