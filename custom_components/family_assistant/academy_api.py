"""Explicit Academy projection, separate from automatic assistant context."""

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .domain import academy
from .domain.validation import DomainError


@websocket_api.websocket_command({
    vol.Required("type"): "family_assistant/academy",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def read(hass, connection, msg):
    from .runtime import get_runtime

    try:
        runtime = get_runtime(hass, msg["entry_id"])
        actor_id = runtime.engine.actor_for_ha(connection.user.id)
        if runtime.engine.shadow_mode:
            raise DomainError("migration_shadow_read_only")
        state = runtime.engine.snapshot()
        result = academy.project(state, state["members"][actor_id], dt_util.utcnow())
        connection.send_result(msg["id"], result)
    except DomainError as error:
        connection.send_error(msg["id"], error.code, error.code)
