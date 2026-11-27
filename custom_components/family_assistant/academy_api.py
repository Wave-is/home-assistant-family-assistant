"""Authenticated Academy channel; writes use the existing household transaction."""

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .academy.household import AcademyError, learner_stamp, mutate, project, require_module
from .command_scope import capture
from .domain.validation import DomainError


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/academy",
        vol.Required("entry_id"): str,
        vol.Required("action"): vol.In({"read", "enroll", "start", "answer", "hint",
                                        "reveal", "pause", "resume"}),
        vol.Optional("payload", default=dict): dict,
    }
)
@websocket_api.async_response
async def academy(hass, connection, msg):
    try:
        entry_id = msg["entry_id"]
        scope = await capture(hass, entry_id, connection.user.id, connection.user)
        await scope.check()
        if scope.engine.shadow_mode:
            raise DomainError("migration_shadow_read_only")
        action, payload = msg["action"], msg.get("payload", {})
        now = dt_util.utcnow()
        if action == "read":
            if set(payload) - {"member_id"}:
                raise AcademyError("invalid_field")
            result = project(scope.engine.snapshot(), entry_id, scope.actor, now,
                             payload.get("member_id"))
        else:
            result = await scope.engine.system_update(
                "academy", now,
                lambda ctx: mutate(ctx.state, entry_id, scope.actor, now, action, payload),
                guard=scope.guard,
            )
            # A revoked role/identity/module must not receive even a replay receipt.
            await scope.check()
            state = scope.engine.snapshot()
            require_module(state)
            if action != "enroll":
                learner_stamp(state, scope.actor, payload["epoch"])
            else:
                current = project(state, entry_id, scope.actor, dt_util.utcnow(),
                                  payload["member_id"])["student"]
                if current != result:
                    raise AcademyError("conflict")
            scope.notify()
        connection.send_result(msg["id"], result)
    except (AcademyError, DomainError) as error:
        connection.send_error(msg["id"], error.code, error.code)
    except OSError:
        connection.send_error(msg["id"], "storage_error", "storage_error")
    except (ValueError, TypeError, KeyError, AttributeError):
        connection.send_error(msg["id"], "invalid_field", "invalid_field")
