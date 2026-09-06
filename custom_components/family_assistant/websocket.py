"""Frontend API with per-request household identity checks."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .domain.validation import DomainError, text


def async_register_api(hass):
    for handler in (households, view, execute, chat):
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


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/chat",
        vol.Required("entry_id"): str,
        vol.Required("text"): str,
        vol.Required("operation_id"): str,
        vol.Required("session_id"): str,
    }
)
@websocket_api.async_response
async def chat(hass, connection, msg):
    import hashlib

    from .runtime import get_runtime
    from .telegram.context import result_refs
    from .telegram.router import route

    try:
        content = text(msg["text"], "text", 4096)
        operation = text(msg["operation_id"], "operation_id", 100)
        session_id = text(msg["session_id"], "session_id", 100)
        runtime = get_runtime(hass, msg["entry_id"])
        actor = runtime.engine.actor_for_ha(connection.user.id)
        role = runtime.engine.view(actor)["role"]
        if "conversation" not in runtime.engine.view(actor)["settings"]["modules"]:
            raise DomainError("module_disabled")
        key = hashlib.sha256(f"{actor}:{session_id}".encode()).hexdigest()
        refs = runtime.engine.snapshot()["memory"].get("dashboard_refs", {}).get(key, [])

        async def fallback(actor, content, operation_id, now, refs):
            if not runtime.assistant:
                raise DomainError("provider_not_configured")
            return await runtime.assistant.respond(actor, content, operation_id, now, refs)

        reply = await route(
            runtime.engine, actor, content, operation, dt_util.utcnow(), refs, fallback=fallback
        )
        if (
            runtime.engine.actor_for_ha(connection.user.id) != actor
            or runtime.engine.view(actor)["role"] != role
        ):
            raise DomainError("forbidden")

        def save(ctx):
            result = ctx.state["processed"].get(operation, {}).get("result", {})
            if result:
                ctx.state["memory"].setdefault("dashboard_refs", {})[key] = result_refs(result)

        await runtime.engine.system_update("dashboard_context", dt_util.utcnow(), save)
        runtime.updated()
        connection.send_result(msg["id"], {"reply": reply})
    except (DomainError, OSError, TimeoutError) as err:
        code = (
            err.code
            if isinstance(err, DomainError)
            else ("provider_timeout" if isinstance(err, TimeoutError) else "storage_error")
        )
        connection.send_error(msg["id"], code, code)
