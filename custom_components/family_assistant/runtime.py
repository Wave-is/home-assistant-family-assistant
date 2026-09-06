"""Home Assistant adapter for persistence, authenticated commands and entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SCHEMA_VERSION
from .domain.engine import Engine, new_state
from .domain.validation import DomainError

PLATFORMS = [Platform.SENSOR]


@dataclass
class Runtime:
    engine: Engine
    listeners: set = field(default_factory=set)
    health: dict = field(default_factory=dict)
    scheduler: Any = None
    telegram: Any = None

    @callback
    def updated(self) -> None:
        for listener in tuple(self.listeners):
            listener()
        if self.scheduler:
            self.scheduler.request()


def get_runtime(hass, entry_id: str) -> Runtime:
    entry = hass.config_entries.async_get_entry(entry_id)
    runtime = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry_id)
    if entry is None or entry.domain != DOMAIN or runtime is None:
        raise DomainError("not_ready")
    return runtime


async def async_setup_runtime(hass, entry) -> bool:
    from .websocket import async_register_api

    data = hass.data.setdefault(DOMAIN, {"entries": {}})
    store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}")
    state = await store.async_load()
    if state is None:
        state = new_state(
            entry.data["owner_user_id"],
            entry.title,
            entry.data.get("language", "en"),
            entry.data.get("modules"),
        )
        state["members"]["owner"]["name"] = entry.data["owner_name"]
        for member in entry.data.get("initial_members", []):
            state["members"][member["id"]] = member
        await store.async_save(state)
    runtime = Runtime(Engine(state, store.async_save))
    data["entries"][entry.entry_id] = runtime
    entry.runtime_data = runtime
    if not data.get("api_registered"):
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/family_assistant/frontend",
                    str(Path(__file__).parent / "frontend"),
                    cache_headers=False,
                ),
            ]
        )
        async_register_api(hass)

        async def execute(call):
            try:
                selected = get_runtime(hass, call.data["entry_id"])
                actor_id = selected.engine.actor_for_ha(call.context.user_id)
                result = await selected.engine.execute(
                    actor_id,
                    call.data["action"],
                    call.data.get("payload", {}),
                    call.data["operation_id"],
                    dt_util.utcnow(),
                )
                selected.updated()
                return {"result": result}
            except DomainError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key=err.code
                ) from err

        import voluptuous as vol

        hass.services.async_register(
            DOMAIN,
            "execute",
            execute,
            schema=vol.Schema(
                {
                    vol.Required("entry_id"): str,
                    vol.Required("action"): str,
                    vol.Required("operation_id"): str,
                    vol.Optional("payload", default={}): dict,
                }
            ),
            supports_response=SupportsResponse.ONLY,
        )
        data["api_registered"] = True
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        from .scheduler import Scheduler

        runtime.scheduler = Scheduler(hass, entry, runtime)
        runtime.scheduler.start()
        await async_configure_telegram(hass, entry)
        entry.async_on_unload(entry.add_update_listener(async_options_updated))
    except Exception:
        data["entries"].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_runtime(hass, entry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = hass.data[DOMAIN]["entries"].pop(entry.entry_id)
    if runtime.telegram:
        await runtime.telegram.stop()
    if runtime.scheduler:
        await runtime.scheduler.stop()
    runtime.listeners.clear()
    return True


async def async_configure_telegram(hass, entry):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .telegram.client import TelegramClient
    from .telegram.manager import TelegramManager

    runtime = entry.runtime_data
    if runtime.telegram:
        await runtime.telegram.stop()
        runtime.telegram = None
    config = entry.options.get("telegram", {})
    if config.get("enabled"):
        runtime.telegram = TelegramManager(
            hass,
            entry,
            runtime,
            TelegramClient(async_get_clientsession(hass), config["token"]),
            config["bot"],
        )
        runtime.telegram.start()
    else:
        runtime.health.pop("telegram", None)


async def async_options_updated(hass, entry):
    await async_configure_telegram(hass, entry)
    entry.runtime_data.updated()


def safe_diagnostics(runtime: Runtime) -> dict[str, Any]:
    """Construct a counts-only export; do not attempt to blacklist every secret."""
    state = runtime.engine.snapshot()
    return {
        "schema_version": state["schema_version"],
        "revision": state["revision"],
        "modules": state["settings"]["modules"],
        "health": dict(runtime.health),
        "counts": {
            key: len(state[key])
            for key in ("members", "shopping", "tasks", "court", "alarms", "alarm_runs", "outbox")
        },
    }
