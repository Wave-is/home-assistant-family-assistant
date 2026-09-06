"""Owner-only recipe provider setup; credentials never enter household projections."""

from copy import deepcopy
from uuid import uuid4

import voluptuous as vol
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..assistant.http import endpoint
from ..domain.validation import DomainError
from .mealie import Mealie


def _scope(flow):
    runtime, actor = flow._authorized_runtime()
    member = runtime.engine.snapshot()["members"][actor]
    return (
        runtime,
        actor,
        member["revision"],
        deepcopy(flow.config_entry.options.get("recipes", {})),
    )


def _same_scope(current, expected):
    return expected is not None and current[0] is expected[0] and current[1:] == expected[1:]


async def options_step(flow, user_input=None):
    try:
        current_scope = _scope(flow)
    except DomainError as err:
        return flow.async_abort(reason=err.code)
    current = current_scope[3]
    errors = {}
    if user_input is not None:
        expected = getattr(flow, "_recipes_displayed_scope", None)
        try:
            # Freeze the form that was actually displayed, not a later configuration.
            if not _same_scope(current_scope, expected):
                raise DomainError("conflict")
            enabled = user_input.get("enabled")
            if type(enabled) is not bool:
                raise DomainError("invalid_field", "enabled")
            if type(user_input.get("clear_token", False)) is not bool:
                raise DomainError("invalid_field", "clear_token")
            config = {**current, "enabled": enabled}
            if user_input.get("clear_token"):
                config.pop("token", None)
            if enabled:
                allow_http = user_input.get("allow_http", False)
                if type(allow_http) is not bool:
                    raise DomainError("invalid_field", "allow_http")
                url = endpoint(user_input.get("url", ""), allow_http=allow_http)
                supplied = user_input.get("token", "")
                if url != current.get("url") and current.get("token") and not supplied:
                    raise DomainError("provider_key_scope")
                config.update(
                    url=url,
                    token=supplied or config.get("token", ""),
                    allow_http=allow_http,
                    timeout=user_input.get("timeout", 15),
                )
                await Mealie(async_get_clientsession(flow.hass), config).inspect()
        except DomainError as err:
            errors["base"] = err.code
        # Recheck successful AND failed requests. A former owner must receive no
        # private settings form or old provider error; an identity/configuration
        # round trip must not commit an intent reviewed under the previous epoch.
        try:
            current_scope = _scope(flow)
        except DomainError as err:
            return flow.async_abort(reason=err.code)
        current = current_scope[3]
        if not _same_scope(current_scope, expected):
            errors["base"] = "conflict"
        if not errors:
            config["revision"] = uuid4().hex
            options = dict(flow.config_entry.options)
            options["recipes"] = config
            return flow.async_create_entry(title="", data=options)
    flow._recipes_displayed_scope = current_scope
    return flow.async_show_form(
        step_id="recipes",
        data_schema=vol.Schema(
            {
                vol.Required("enabled", default=current.get("enabled", False)): bool,
                vol.Optional("url", default=current.get("url", "")): str,
                vol.Optional("token"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required("clear_token", default=False): bool,
                vol.Required("allow_http", default=current.get("allow_http", False)): bool,
                vol.Required("timeout", default=current.get("timeout", 15)): vol.All(
                    int, vol.Range(min=5, max=30)
                ),
            }
        ),
        errors=errors,
    )
