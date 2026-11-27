"""Authorized course, parent plan, provider and Mini App configuration API."""
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .academy import accountability, courses, mini_auth, providers, telegram
from .academy.household import AcademyError, learner_stamp, require_module, project
from .command_scope import capture
from .domain.validation import DomainError

ACTIONS = {"catalog","preview","read","plan","act","settings","mini_config",
           "provider_config","schedule","skip","court_review"}


@websocket_api.websocket_command({
    vol.Required("type"):"family_assistant/academy_course",
    vol.Required("entry_id"):str,
    vol.Required("action"):vol.In(ACTIONS),
    vol.Optional("payload",default=dict):dict,
})
@websocket_api.async_response
async def academy_course(hass,connection,msg):
    try:
        scope = await capture(hass,msg["entry_id"],connection.user.id,connection.user)
        await scope.check()
        state = scope.engine.snapshot()
        require_module(state)
        if scope.engine.shadow_mode or scope.role not in {"owner","parent","child"}:
            raise AcademyError("forbidden")
        action,payload,now = msg["action"],msg.get("payload",{}),dt_util.utcnow()
        if action == "catalog":
            if set(payload)-{"group"}:
                raise AcademyError("invalid_field")
            result = courses.index(payload.get("group","all"))
        elif action == "preview":
            if scope.role not in {"owner","parent"}:
                raise AcademyError("forbidden")
            result = courses.preview(payload)
        elif action == "read":
            if set(payload)-{"member_id"}:
                raise AcademyError("invalid_field")
            result = courses.read(state,scope.actor,now,payload.get("member_id"))
        elif action == "settings":
            if payload or scope.role!="owner":
                raise AcademyError("forbidden")
            result = {"mini":state.get("academy_mini",{"enabled":False,"revision":0,"origin":""}),
                      "providers":providers.public(state)}
        else:
            def change(ctx):
                require_module(ctx.state)
                if action == "plan":
                    return courses.save_plan(ctx.state,scope.actor,now,payload)
                if action == "act":
                    return courses.action(ctx.state,scope.actor,now,payload)
                if action == "mini_config":
                    return mini_auth.configure(ctx.state,scope.actor,payload)
                if action == "provider_config":
                    return providers.configure(ctx.state,scope.actor,payload)
                if action == "court_review":
                    return accountability.review(ctx.state,scope.actor,now,payload)
                if action == "schedule":
                    if set(payload)!={"kind","args"} or type(payload["args"]) is not list:
                        raise AcademyError("invalid_field")
                    telegram.configure(ctx.state,msg["entry_id"],scope.actor,now,
                                       payload["kind"],payload["args"])
                    return {"saved":True}
                if action == "skip":
                    if set(payload)!={"args"} or type(payload["args"]) is not list:
                        raise AcademyError("invalid_field")
                    telegram.skip(ctx.state,scope.actor,payload["args"])
                    return {"saved":True}
                raise AcademyError("unknown_action")
            result = await scope.engine.system_update("academy_course",now,change,guard=scope.guard)
            await scope.check()
            current = scope.engine.snapshot()
            require_module(current)
            if action == "act":
                learner_stamp(current,scope.actor,payload["epoch"])
            elif action in {"plan","court_review"}:
                child = courses.read(current,scope.actor,dt_util.utcnow(),payload["member_id"])
                if child["student"]["epoch"] != payload["epoch"]:
                    raise AcademyError("conflict")
            scope.notify()
        connection.send_result(msg["id"],result)
    except (AcademyError,DomainError) as error:
        connection.send_error(msg["id"],error.code,error.code)
    except OSError:
        connection.send_error(msg["id"],"storage_error","storage_error")
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        connection.send_error(msg["id"],"invalid_field","invalid_field")
