"""Frontend API with per-request household identity checks."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .domain.validation import DomainError


def async_register_api(hass):
    from .assistant.article_api import article
    from .assistant.chat_api import chat
    from .developer_api import report as developer_report
    from .digest_api import preview as digest_preview
    from .panel_api import (
        ai_sandbox_test,
        module_toggle,
        panel,
        settings_save,
        telegram_enrollment,
        telegram_enrollment_confirm,
        telegram_invite,
        telegram_verify,
    )
    from .recipes.api import recipes
    from .school_import_api import preview as school_calendar_preview

    for handler in (
        households,
        view,
        execute,
        chat,
        article,
        network_refresh,
        recipes,
        digest_preview,
        school_calendar_preview,
        developer_report,
        panel,
        settings_save,
        module_toggle,
        telegram_enrollment,
        telegram_enrollment_confirm,
        telegram_invite,
        telegram_verify,
        ai_sandbox_test,
    ):
        websocket_api.async_register_command(hass, handler)


@websocket_api.websocket_command({vol.Required("type"): "family_assistant/households"})
@websocket_api.async_response
async def households(hass, connection, msg):
    result = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id)
        if runtime is None:
            continue
        try:
            runtime.engine.actor_for_ha(connection.user.id)
        except DomainError:
            continue
        result.append({"entry_id": entry.entry_id, "title": entry.title})
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "family_assistant/view", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def view(hass, connection, msg):
    from .runtime import get_runtime

    try:
        runtime = get_runtime(hass, msg["entry_id"])
        actor_id = runtime.engine.actor_for_ha(connection.user.id)
        now = dt_util.utcnow()
        data = runtime.engine.view(actor_id, now=now)
        if data["role"] != "guest" and "conversation" in data["settings"]["modules"]:
            from .assistant.article_api import source_view as article_source_view
            from .assistant.chat_api import source_view as conversation_source_view

            data["conversation_source"] = conversation_source_view(
                hass.config_entries.async_get_entry(msg["entry_id"]), runtime, actor_id
            )
            data["article_source"] = article_source_view(
                hass.config_entries.async_get_entry(msg["entry_id"]), runtime, actor_id
            )
        if data["role"] != "guest" and "presence" in data["settings"]["modules"]:
            from .presence_observations import project

            data["presence"] = project(
                hass,
                hass.config_entries.async_get_entry(msg["entry_id"]),
                runtime,
                actor_id,
                connection.user,
                now,
            )
        if data["role"] in {"owner", "parent"}:
            data["health"] = dict(runtime.health)
            from .recipes.api import source_view

            data["recipe_source"] = source_view(runtime, data)
        if data["role"] == "owner" and not runtime.engine.shadow_mode:
            from .developer_api import source_view as developer_source_view

            data["developer_diagnostics"] = developer_source_view(runtime, actor_id)
        connection.send_result(msg["id"], data)
    except DomainError as err:
        connection.send_error(msg["id"], err.code, err.code)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/execute",
        vol.Required("entry_id"): str,
        vol.Required("action"): str,
        vol.Required("payload"): dict,
        vol.Required("operation_id"): str,
    }
)
@websocket_api.async_response
async def execute(hass, connection, msg):
    from .command_scope import capture

    try:
        scope = await capture(hass, msg["entry_id"], connection.user.id, connection.user)
        await scope.check()
        result = await scope.engine.execute(
            scope.actor,
            msg["action"],
            msg["payload"],
            msg["operation_id"],
            dt_util.utcnow(),
            guard=scope.guard,
        )
        scope = await scope.after_execute(
            msg["action"], msg["payload"], msg["operation_id"], result
        )
        scope.notify()
        connection.send_result(msg["id"], result)
    except DomainError as err:
        connection.send_error(msg["id"], err.code, err.code)
    except OSError:
        connection.send_error(msg["id"], "storage_error", "storage_error")


@websocket_api.websocket_command(
    {vol.Required("type"): "family_assistant/network_refresh", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def network_refresh(hass, connection, msg):
    from .runtime import get_runtime

    try:
        runtime = get_runtime(hass, msg["entry_id"])
        actor = runtime.engine.actor_for_ha(connection.user.id)
        if runtime.engine.view(actor)["role"] not in {"owner", "parent"}:
            raise DomainError("forbidden")
        if runtime.network is None:
            raise DomainError("network_not_configured")
        await runtime.network.refresh()
        if runtime.engine.actor_for_ha(connection.user.id) != actor or runtime.engine.view(actor)[
            "role"
        ] not in {"owner", "parent"}:
            raise DomainError("forbidden")
        connection.send_result(msg["id"], runtime.engine.view(actor)["network"])
    except DomainError as err:
        connection.send_error(msg["id"], err.code, err.code)
    except OSError:
        connection.send_error(msg["id"], "storage_error", "storage_error")
