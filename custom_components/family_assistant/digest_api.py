"""Explicit authenticated preview, never model context or an automatic export."""

from datetime import timedelta
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .domain import digest_content
from .domain.validation import DomainError, enum


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/digest_preview",
        vol.Required("entry_id"): str,
        vol.Required("kind"): str,
    }
)
@websocket_api.async_response
async def preview(hass, connection, msg):
    from .runtime import get_runtime

    try:
        kind = enum(msg["kind"], digest_content.KINDS, "kind")
        runtime = get_runtime(hass, msg["entry_id"])
        actor_id = runtime.engine.actor_for_ha(connection.user.id)
        state = runtime.engine.snapshot()
        actor = state["members"][actor_id]
        if actor["role"] == "guest":
            raise DomainError("forbidden")
        if "digests" not in state["settings"]["modules"]:
            raise DomainError("module_disabled")
        now = dt_util.utcnow()
        today = now.astimezone(ZoneInfo(state["settings"]["timezone"])).date()
        start = today if kind == "morning" else today + timedelta(days=1)
        end = start + timedelta(days=7 if kind == "weekly" else 1)
        result = digest_content.snapshot(
            state, actor, kind, start.isoformat(), end.isoformat(), now
        )
        # There is no await between current authorization, projection and reply.
        connection.send_result(msg["id"], result)
    except DomainError as error:
        connection.send_error(msg["id"], error.code, error.code)
    except (ValueError, OverflowError, KeyError, TypeError):
        connection.send_error(msg["id"], "invalid_field", "invalid_field")
