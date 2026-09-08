"""Owner-authorized read of a strictly deidentified technical defect report."""

import json
from pathlib import Path

import voluptuous as vol
from homeassistant.components import websocket_api

from .command_scope import capture
from .domain.developer_diagnostics import build_report, configuration
from .domain.validation import DomainError


def _public_version():
    # Only the installed public package manifest; never ConfigEntry/provider data.
    return json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))[
        "version"
    ]


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/developer_report",
        vol.Required("entry_id"): str,
        vol.Required("expected_generation"): int,
    }
)
@websocket_api.async_response
async def report(hass, connection, msg):
    try:
        scope = await capture(hass, msg["entry_id"], connection.user.id, connection.user)
        if scope.role != "owner" or scope.engine.shadow_mode:
            raise DomainError("forbidden")
        version = await hass.async_add_executor_job(_public_version)
        await scope.check()
        state = scope.engine.snapshot()
        current = configuration(state)
        if (
            type(msg["expected_generation"]) is not int
            or not current["available"]
            or msg["expected_generation"] != current["generation"]
        ):
            raise DomainError("conflict")
        result = build_report(state, version=version)
        connection.send_result(msg["id"], result)
    except DomainError as error:
        connection.send_error(msg["id"], error.code, error.code)
    except (ValueError, KeyError, TypeError, OSError):
        connection.send_error(msg["id"], "invalid_field", "invalid_field")


def source_view(runtime, actor):
    state = runtime.engine.snapshot()
    if state["members"][actor]["role"] != "owner" or runtime.engine.shadow_mode:
        return None
    return configuration(state)
