"""Read-only recipe requests with authority checks before and after transport."""

import voluptuous as vol
from homeassistant.components import websocket_api

from ..domain.validation import DomainError


def source_view(runtime, view):
    if view["role"] not in {"owner", "parent"}:
        return None
    enabled = "pantry" in view["settings"]["modules"] and runtime.recipes is not None
    return {
        "enabled": enabled,
        "provider": "mealie",
        "revision": runtime.recipes_revision,
    }


def _scope(hass, connection, entry_id):
    from ..runtime import get_runtime

    runtime = get_runtime(hass, entry_id)
    actor = runtime.engine.actor_for_ha(connection.user.id)
    view = runtime.engine.view(actor)
    if view["role"] not in {"owner", "parent"}:
        raise DomainError("forbidden")
    if "pantry" not in view["settings"]["modules"]:
        raise DomainError("module_disabled")
    if runtime.recipes is None:
        raise DomainError("not_ready")
    member = next(m for m in view["members"] if m["id"] == actor)
    return runtime, actor, member["revision"], runtime.recipes, runtime.recipes_revision


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/recipes",
        vol.Required("entry_id"): str,
        vol.Required("kind"): vol.In({"search", "get"}),
        vol.Optional("query", default=""): str,
        vol.Optional("page", default=1): int,
        vol.Optional("slug"): str,
    }
)
@websocket_api.async_response
async def recipes(hass, connection, msg):
    scope = None
    try:
        scope = _scope(hass, connection, msg["entry_id"])
        runtime, _, _, provider, revision = scope
        if type(msg["page"]) is not int or not 1 <= msg["page"] <= 1000:
            raise DomainError("invalid_field", "page")
        if msg["kind"] == "search":
            if "slug" in msg:
                raise DomainError("invalid_field", "slug")
            result = await provider.search(msg["query"], msg["page"])
        else:
            if msg["query"] or msg["page"] != 1:
                raise DomainError("invalid_field", "kind")
            result = {"candidate": await provider.recipe(msg.get("slug"))}
        if _scope(hass, connection, msg["entry_id"]) != scope:
            raise DomainError("conflict")
        runtime.health["recipes"] = "connected"
        connection.send_result(msg["id"], {"source_revision": revision, **result})
    except DomainError as err:
        code = err.code
        if scope is not None:
            # Errors also describe private provider state. Prefer current authority
            # and configuration errors after an in-flight request loses its scope.
            try:
                if _scope(hass, connection, msg["entry_id"]) != scope:
                    raise DomainError("conflict")
            except DomainError as scope_error:
                code = scope_error.code
            else:
                if code.startswith("provider_"):
                    scope[0].health["recipes"] = code
        connection.send_error(msg["id"], code, code)
