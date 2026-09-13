"""Home Assistant adapter for persistence, authenticated commands and entities."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

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
    chat: Any = None
    assistant_revision: str = ""
    assistant_config_digest: str = ""
    articles: Any = None
    article_revision: str = ""
    network: Any = None
    recipes: Any = None
    recipes_revision: str = ""
    media: Any = None
    media_unsub: Any = None
    media_task: Any = None
    price_watcher: Any = None
    options_lock: Any = field(default_factory=asyncio.Lock)
    module_signature: Any = None
    module_task: Any = None

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
    from .migration.shadow_entry import validate_entry_state
    from .websocket import async_register_api

    data = hass.data.setdefault(DOMAIN, {"entries": {}})
    store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}")
    state = await store.async_load()
    try:
        validate_entry_state(entry.data, state)
    except DomainError as error:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key=error.code) from None
    if "frontend_resource" not in data:
        from homeassistant.components.http import StaticPathConfig

        from .frontend_resources import async_prepare_frontend_resource

        resource = await async_prepare_frontend_resource(hass)
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(path.url_path, path.filesystem_path, path.cache_headers)
                for path in resource.static_paths
            ]
        )
        data["frontend_resource"] = resource
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
        async_register_api(hass)
        from .media_http import async_register_media

        async_register_media(hass)

        async def execute(call):
            from .command_scope import capture

            try:
                scope = await capture(hass, call.data["entry_id"], call.context.user_id)
                await scope.check()
                result = await scope.engine.execute(
                    scope.actor,
                    call.data["action"],
                    call.data.get("payload", {}),
                    call.data["operation_id"],
                    dt_util.utcnow(),
                    guard=scope.guard,
                )
                scope = await scope.after_execute(
                    call.data["action"],
                    call.data.get("payload", {}),
                    call.data["operation_id"],
                    result,
                )
                scope.notify()
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
        await async_configure_frontend(hass, runtime)
        if runtime.engine.shadow_mode:
            # A shadow entry never constructs providers, device/media workers,
            # presence readers or an effect scheduler, regardless of its Options.
            runtime.health["migration"] = "migration_shadow_read_only"
            # No entity publication either: generic household automations must not
            # mistake shadow sensor state changes for real family activity.
            entry.async_on_unload(entry.add_update_listener(async_options_updated))
            return True
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
        from .price_watch_fetcher import PriceWatchScheduler

        runtime.price_watcher = PriceWatchScheduler(hass, entry, runtime)
        runtime.price_watcher.start()
        from .llm_api import async_register

        async_register(hass, entry)
        entry.async_on_unload(entry.add_update_listener(async_options_updated))
        from .module_runtime import watch

        watch(hass, entry, runtime)
        # Platforms are forwarded before optional managers are configured. In
        # particular the Assist entity must publish its now-ready chat state
        # even when the scheduler has no domain change to announce.
        runtime.updated()
    except Exception:
        await async_stop_chat(runtime)
        await async_stop_articles(runtime)
        await async_stop_media(runtime)
        if runtime.price_watcher:
            runtime.price_watcher.stop()
        if runtime.network:
            await runtime.network.stop()
        if runtime.telegram:
            await runtime.telegram.stop()
        if runtime.scheduler:
            await runtime.scheduler.stop()
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        data["entries"].pop(entry.entry_id, None)
        await runtime.engine.async_close()
        from .panel_registration import unregister_if_unused

        unregister_if_unused(hass)
        raise
    return True


async def async_configure_frontend(hass, runtime):
    """Keep card discovery independent of household/provider availability."""
    from homeassistant.helpers import issue_registry as ir

    from .frontend_resources import async_ensure_frontend_resource

    try:
        result = await async_ensure_frontend_resource(hass, hass.data[DOMAIN]["frontend_resource"])
        attention = result.status not in {"created", "updated", "current", "yaml_current"}
    except Exception:  # noqa: BLE001 - no user URLs or filesystem exceptions in diagnostics
        attention = True
    for selected in hass.data[DOMAIN].get("entries", {}).values():
        if attention:
            selected.health["frontend"] = "frontend_resource_attention"
        else:
            selected.health.pop("frontend", None)
    if attention:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "frontend_resource",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="frontend_resource_attention",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "frontend_resource")

    from .panel_registration import register

    if not register(hass):
        runtime.health["frontend"] = "frontend_resource_attention"


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
    platforms = [] if entry.runtime_data.engine.shadow_mode else PLATFORMS
    if platforms and not await hass.config_entries.async_unload_platforms(entry, platforms):
        return False
    runtime = hass.data[DOMAIN]["entries"].pop(entry.entry_id)
    if runtime.module_task is not None:
        runtime.module_task.cancel()
        with suppress(asyncio.CancelledError):
            await runtime.module_task
        runtime.module_task = None
    await async_stop_chat(runtime)
    await async_stop_articles(runtime)
    await async_stop_media(runtime)
    if runtime.price_watcher:
        runtime.price_watcher.stop()
    if runtime.network:
        await runtime.network.stop()
    if runtime.telegram:
        await runtime.telegram.stop()
    if runtime.scheduler:
        await runtime.scheduler.stop()
    # Retire this exact Store writer before another runtime loads its state.
    # Failed platform unload above deliberately leaves the live Engine open.
    await runtime.engine.async_close()
    runtime.listeners.clear()
    from .panel_registration import unregister_if_unused

    unregister_if_unused(hass)
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
    if entry.runtime_data.engine.shadow_mode:
        return
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
    data = hass.data.get(DOMAIN, {})
    lock = data.setdefault("setup_lock", asyncio.Lock())
    selected = entry.runtime_data
    while True:
        async with lock:
            if (
                data.get("entries", {}).get(entry.entry_id) is not selected
                or entry.runtime_data is not selected
                or selected is None
            ):
                return
            coordinator = data.get("backup")
            if coordinator is None:
                if selected.engine.shadow_mode:
                    return
                async with selected.options_lock:
                    from .module_runtime import signature

                    modules_before = signature(selected)
                    await async_stop_chat(selected)
                    await async_stop_articles(selected)
                    await async_configure_presence(hass, entry)
                    async_configure_assistant(hass, entry)
                    async_configure_recipes(hass, entry)
                    await async_configure_network(hass, entry)
                    await async_configure_telegram(hass, entry)
                    selected.module_signature = modules_before
                    selected.updated()
                return
        await coordinator.released.wait()


async def async_configure_presence(hass, entry):
    """Reconcile source pins, never observations; stale Options fail closed."""
    from .domain import presence

    runtime = entry.runtime_data
    if runtime.engine.shadow_mode:
        return
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
    if entry.runtime_data.engine.shadow_mode:
        return
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


async def async_stop_articles(runtime):
    """Discard transient public-page answers and settle only owned requests."""
    if runtime.articles is not None:
        previous = runtime.articles
        runtime.articles = None
        runtime.article_revision = uuid4().hex
        await previous.async_stop()


async def async_stop_chat(runtime):
    """Invalidate and settle owned dashboard requests before replacing providers."""
    previous = runtime.chat
    runtime.chat = None
    runtime.assistant_revision = uuid4().hex
    if previous is not None:
        await previous.async_stop()


def async_configure_assistant(hass, entry):
    if entry.runtime_data.engine.shadow_mode:
        return
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .assistant.article_service import ArticleService
    from .assistant.chat_service import ChatService, conversation_digest
    from .assistant.provider import Cascade, Ollama
    from .assistant.search import Search
    from .assistant.service import Assistant

    runtime = entry.runtime_data
    if runtime.chat is not None:
        runtime.chat.close()
    runtime.chat = None
    runtime.assistant_revision = uuid4().hex
    runtime.assistant_config_digest = conversation_digest(dict(entry.options).get("conversation"))
    if runtime.articles is not None:
        runtime.articles.close()
    runtime.articles = None
    runtime.article_revision = uuid4().hex
    runtime.assistant = None
    if "conversation" in runtime.engine.snapshot()["settings"]["modules"]:
        # Deterministic family commands do not require an enabled model.
        runtime.chat = ChatService()
    config = entry.options.get("conversation", {})
    if (
        "conversation" in runtime.engine.snapshot()["settings"]["modules"]
        and config.get("enabled")
        and (config.get("primary") or config.get("ha_agent") or config.get("agy"))
    ):
        # A native HA-only provider owns its transport. Do not create another
        # HTTP session (or initialize discovery/DNS) unless a direct source needs it.
        search_config = config.get("search", {})
        search_enabled = bool(search_config) and search_config.get("enabled", True)
        direct = [
            config[key]
            for key in ("agy", "primary", "fallback")
            if config.get(key) and (key != "fallback" or config[key].get("enabled", True))
        ]
        session = async_get_clientsession(hass) if direct or search_enabled else None
        providers = []
        if config.get("ha_agent"):
            from .assistant.ha_agent_provider import HAConversationAgent

            providers.append(HAConversationAgent(hass, entry, config["ha_agent"]))
        providers.extend(Ollama(session, provider) for provider in direct)
        search = Search(session, search_config) if search_enabled else None
        runtime.assistant = Assistant(runtime.engine, Cascade(providers, runtime.health), search)
        article_policy = entry.options.get("articles", {})
        if (
            isinstance(article_policy, dict)
            and set(article_policy) == {"enabled", "allow_children", "revision"}
            and article_policy["enabled"] is True
            and type(article_policy["allow_children"]) is bool
            and isinstance(article_policy["revision"], str)
            and len(article_policy["revision"]) == 32
            and all(character in "0123456789abcdef" for character in article_policy["revision"])
            and "conversation" in runtime.engine.snapshot()["settings"]["modules"]
        ):
            runtime.articles = ArticleService(runtime.assistant.cascade)
    else:
        runtime.health.pop("conversation", None)


async def async_configure_network(hass, entry):
    if entry.runtime_data.engine.shadow_mode:
        return
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
    from .domain.school_retention import health_stats as school_health_stats

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
        "school_reminder_capacity": school_health_stats(state, dt_util.utcnow()),
        "counts": {
            key: len(state[key])
            for key in ("members", "shopping", "tasks", "court", "alarms", "alarm_runs", "outbox")
        },
    }
