"""Home Assistant adapter for persistence, authenticated commands and entities."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SCHEMA_VERSION
from .domain.engine import Engine, new_state
from .domain.validation import DomainError

PLATFORMS = [Platform.SENSOR, Platform.CONVERSATION, Platform.CALENDAR]


@dataclass
class Runtime:
    engine: Engine
    listeners: set = field(default_factory=set)
    health: dict = field(default_factory=dict)
    scheduler: Any = None
    telegram: Any = None
    assistant: Any = None
    network: Any = None
    recipes: Any = None
    recipes_revision: str = ""
    media: Any = None
    media_unsub: Any = None
    media_task: Any = None
    options_lock: Any = field(default_factory=asyncio.Lock)

    @callback
    def updated(self) -> None:
        for listener in tuple(self.listeners):
            listener()
        if self.scheduler:
            self.scheduler.request()
        if self.network:
            self.network.request_effects()


def get_runtime(hass, entry_id: str) -> Runtime:
    entry = hass.config_entries.async_get_entry(entry_id)
    runtime = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry_id)
    if entry is None or entry.domain != DOMAIN or runtime is None:
        raise DomainError("not_ready")
    return runtime


async def async_setup_runtime(hass, entry) -> bool:
    """Serialize entry lifecycle with the integration's backup platform."""
    data = hass.data.setdefault(DOMAIN, {"entries": {}})
    lock = data.setdefault("setup_lock", asyncio.Lock())
    async with lock:
        if data.get("backup"):
            raise ConfigEntryNotReady("backup_in_progress")
        return await _async_setup_runtime(hass, entry)


async def _async_setup_runtime(hass, entry) -> bool:
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
            timezone=entry.data.get("timezone", hass.config.time_zone),
            template=entry.data.get("template", "manual"),
        )
        state["members"]["owner"]["name"] = entry.data["owner_name"]
        for member in entry.data.get("initial_members", []):
            state["members"][member["id"]] = member
        await store.async_save(state)
    runtime = Runtime(Engine(state, store.async_save))
    data["entries"][entry.entry_id] = runtime
    entry.runtime_data = runtime
    from .media_storage import MediaStorage

    runtime.media = MediaStorage(
        runtime.engine,
        Path(
            hass.config.path(
                "family_assistant_data", hashlib.sha256(entry.entry_id.encode()).hexdigest()
            )
        ),
        dt_util.utcnow,
    )
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
        from .media_http import async_register_media

        async_register_media(hass)

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
        await async_configure_presence(hass, entry)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        from .scheduler import Scheduler

        runtime.scheduler = Scheduler(hass, entry, runtime)
        runtime.scheduler.start()
        from homeassistant.helpers.event import async_track_time_interval

        async def reconcile_media(_now):
            if runtime.media_task and not runtime.media_task.done():
                return

            async def collect():
                try:
                    if await runtime.media.collect():
                        runtime.health.pop("media", None)
                except (DomainError, OSError, TimeoutError):
                    runtime.health["media"] = "media_unavailable"

            runtime.media_task = hass.async_create_task(
                collect(), "Family Assistant private media cleanup"
            )

        runtime.media_unsub = async_track_time_interval(hass, reconcile_media, timedelta(minutes=1))
        await reconcile_media(dt_util.utcnow())
        async_configure_assistant(hass, entry)
        await async_configure_network(hass, entry)
        await async_configure_telegram(hass, entry)
        async_configure_recipes(hass, entry)
        from .llm_api import async_register

        async_register(hass, entry)
        entry.async_on_unload(entry.add_update_listener(async_options_updated))
    except Exception:
        await async_stop_media(runtime)
        if runtime.network:
            await runtime.network.stop()
        if runtime.telegram:
            await runtime.telegram.stop()
        if runtime.scheduler:
            await runtime.scheduler.stop()
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        data["entries"].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_runtime(hass, entry) -> bool:
    data = hass.data.get(DOMAIN, {})
    lock = data.setdefault("setup_lock", asyncio.Lock())
    while True:
        async with lock:
            coordinator = data.get("backup")
            if coordinator is None:
                return await _async_unload_runtime(hass, entry)
        # Returning False poisons the HA entry as FAILED_UNLOAD. Wait outside
        # the setup lock: pre-backup may still be draining an earlier setup.
        # Only a completed unwind releases this coordinator generation.
        await coordinator.released.wait()


async def _async_unload_runtime(hass, entry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = hass.data[DOMAIN]["entries"].pop(entry.entry_id)
    await async_stop_media(runtime)
    if runtime.network:
        await runtime.network.stop()
    if runtime.telegram:
        await runtime.telegram.stop()
    if runtime.scheduler:
        await runtime.scheduler.stop()
    runtime.listeners.clear()
    return True


async def async_stop_media(runtime):
    if runtime.media_unsub:
        runtime.media_unsub()
        runtime.media_unsub = None
    if runtime.media:
        await runtime.media.stop()
    if runtime.media_task:
        await runtime.media_task


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
    async with entry.runtime_data.options_lock:
        await async_configure_presence(hass, entry)
        async_configure_assistant(hass, entry)
        async_configure_recipes(hass, entry)
        await async_configure_network(hass, entry)
        await async_configure_telegram(hass, entry)
        entry.runtime_data.updated()


async def async_configure_presence(hass, entry):
    """Reconcile source pins, never observations; stale Options fail closed."""
    from .domain import presence

    runtime = entry.runtime_data
    try:
        await runtime.engine.system_update(
            "presence_sources",
            dt_util.utcnow(),
            lambda ctx: presence.sync_bindings(ctx, dict(entry.options)),
        )
    except DomainError as error:
        runtime.health["presence"] = error.code
    except OSError:
        runtime.health["presence"] = "storage_error"
    else:
        runtime.health.pop("presence", None)


def async_configure_recipes(hass, entry):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .recipes.mealie import Mealie

    runtime = entry.runtime_data
    config = entry.options.get("recipes", {})
    runtime.recipes = None
    runtime.recipes_revision = config.get("revision", "")
    runtime.health.pop("recipes", None)
    if config.get("enabled"):
        try:
            if not isinstance(runtime.recipes_revision, str) or not runtime.recipes_revision:
                raise DomainError("invalid_field", "revision")
            runtime.recipes = Mealie(async_get_clientsession(hass), config)
        except DomainError as err:
            runtime.health["recipes"] = err.code


def async_configure_assistant(hass, entry):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .assistant.provider import Cascade, Ollama
    from .assistant.search import Search
    from .assistant.service import Assistant

    runtime = entry.runtime_data
    runtime.assistant = None
    config = entry.options.get("conversation", {})
    if config.get("enabled") and config.get("primary"):
        session = async_get_clientsession(hass)
        providers = [
            Ollama(session, config[key]) for key in ("primary", "fallback") if config.get(key)
        ]
        search = Search(session, config["search"]) if config.get("search") else None
        runtime.assistant = Assistant(runtime.engine, Cascade(providers, runtime.health), search)
    else:
        runtime.health.pop("conversation", None)


async def async_configure_network(hass, entry):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .network.client import RouterClient, certificate_context
    from .network.manager import NetworkManager

    runtime = entry.runtime_data
    if runtime.network:
        await runtime.network.stop()
        runtime.network = None
    config = entry.options.get("mikrotik", {})
    if config.get("enabled") and "mikrotik" in runtime.engine.snapshot()["settings"]["modules"]:
        context = await hass.async_add_executor_job(certificate_context, config.get("ca_pem", ""))
        runtime.network = NetworkManager(
            hass, entry, runtime, RouterClient(async_get_clientsession(hass), config, context)
        )
        runtime.network.start()
    else:
        runtime.health.pop("mikrotik", None)


def safe_diagnostics(runtime: Runtime) -> dict[str, Any]:
    """Construct a counts-only export; do not attempt to blacklist every secret."""
    state = runtime.engine.snapshot()
    from .domain.digests import health_stats as digest_health_stats
    from .domain.media import health_stats

    try:
        media_capacity = health_stats(state, dt_util.utcnow())
    except DomainError:
        media_capacity = {"capacity": "unavailable"}
    return {
        "schema_version": state["schema_version"],
        "revision": state["revision"],
        "modules": state["settings"]["modules"],
        "health": dict(runtime.health),
        "media_capacity": media_capacity,
        "digest_capacity": digest_health_stats(state),
        "counts": {
            key: len(state[key])
            for key in ("members", "shopping", "tasks", "court", "alarms", "alarm_runs", "outbox")
        },
    }
