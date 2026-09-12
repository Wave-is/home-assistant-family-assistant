"""Explicit owner consent for future technical observations, never raw conversations."""

from uuid import uuid4

import voluptuous as vol
from homeassistant.util import dt as dt_util

from .command_scope import capture
from .domain.developer_diagnostics import configuration
from .domain.validation import DomainError


async def options_step(flow, user_input=None):
    try:
        from .flow_identity import user_id as flow_user_id

        user_id = flow_user_id(flow)
        scope = await capture(flow.hass, flow.config_entry.entry_id, user_id)
        if scope.role != "owner" or scope.engine.shadow_mode:
            raise DomainError("forbidden")
        current = configuration(scope.engine.snapshot())
        if not current["available"]:
            raise DomainError("invalid_field")
        old_scope = getattr(flow, "_developer_scope", None)
        if old_scope is not None:
            await old_scope.check()
        pin = (scope.runtime, scope.user_id, scope.actor, scope.actor_revision)
        previous_pin = getattr(flow, "_developer_pin", None)
        if previous_pin is not None and previous_pin != pin:
            raise DomainError("conflict")
        if previous_pin is None:
            flow._developer_scope = scope
            flow._developer_pin = pin
            flow._developer_generation = current["generation"]
        frozen = getattr(flow, "_developer_payload", None)
        errors = {}
        if user_input is not None:
            if (
                previous_pin is None
                or not isinstance(user_input, dict)
                or set(user_input) != {"enabled"}
                or type(user_input["enabled"]) is not bool
            ):
                raise DomainError("invalid_field")
            payload = {
                "enabled": user_input["enabled"],
                "expected_generation": flow._developer_generation,
            }
            # A lost response retries this exact command, never a newly rebased toggle.
            if frozen is None:
                flow._developer_payload, flow._developer_operation = payload, uuid4().hex
            if flow._developer_payload != payload:
                raise DomainError("conflict")
            try:
                result = await scope.engine.execute(
                    scope.actor,
                    "settings.developer_policy",
                    payload,
                    flow._developer_operation,
                    dt_util.utcnow(),
                    guard=scope.guard,
                )
                await scope.check()
                after = configuration(scope.engine.snapshot())
                if not after["available"] or (after["generation"], after["enabled"]) != (
                    result["generation"],
                    result["enabled"],
                ):
                    raise DomainError("conflict")
                scope.runtime.updated()
                return flow.async_abort(reason="developer_policy_saved")
            except OSError:
                # The original expected generation and operation survive either a
                # failed write or a lost response after commit. Engine alone checks
                # the exact receipt; never accept the new generation as a new intent.
                await scope.check()
                errors["base"] = "storage_error"
        selected = getattr(flow, "_developer_payload", None) or current
        return flow.async_show_form(
            step_id="developer_diagnostics",
            data_schema=vol.Schema({vol.Required("enabled", default=selected["enabled"]): bool}),
            errors=errors,
        )
    except DomainError as error:
        return flow.async_abort(reason=error.code)
