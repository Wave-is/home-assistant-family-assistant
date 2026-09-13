"""Explicit authenticated read API; not part of automatic assistant context."""

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from ..domain.validation import DomainError
from .observations import project


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/home_status",
        vol.Required("entry_id"): str,
        vol.Optional("section", default="home"): str,
        vol.Optional("group_id"): str,
    }
)
@websocket_api.async_response
async def read(hass, connection, msg):
    from ..runtime import get_runtime

    try:
        runtime = get_runtime(hass, msg["entry_id"])
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        actor = runtime.engine.actor_for_ha(connection.user.id)
        result = project(
            hass,
            entry,
            runtime,
            actor,
            connection.user,
            dt_util.utcnow(),
            section=msg.get("section", "home"),
            group_id=msg.get("group_id"),
        )
        connection.send_result(msg["id"], result)
    except DomainError as error:
        connection.send_error(msg["id"], error.code, error.code)
    except (ValueError, TypeError, KeyError, AttributeError):
        connection.send_error(msg["id"], "invalid_field", "invalid_field")
