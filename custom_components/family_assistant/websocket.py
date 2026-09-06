"""Frontend API with per-request household identity checks."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .domain.validation import DomainError


def async_register_api(hass):
    for handler in (households, view, execute):
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
        data = runtime.engine.view(actor_id)
        if data["role"] in {"owner", "parent"}:
            data["health"] = dict(runtime.health)
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
    from .runtime import get_runtime

    try:
        runtime = get_runtime(hass, msg["entry_id"])
        actor_id = runtime.engine.actor_for_ha(connection.user.id)
        result = await runtime.engine.execute(
            actor_id, msg["action"], msg["payload"], msg["operation_id"], dt_util.utcnow()
        )
        runtime.updated()
        connection.send_result(msg["id"], result)
    except DomainError as err:
        connection.send_error(msg["id"], err.code, err.code)
    except OSError:
        connection.send_error(msg["id"], "storage_error", "storage_error")
