"""Authenticated control-center projections and adapters to canonical commands."""

from copy import deepcopy

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.util import dt as dt_util

from .command_scope import capture
from .domain import settings
from .domain.validation import DomainError, text, timestamp
from .panel_readiness import capabilities, member_readiness


def enrollment_view(record, now):
    """Only owner-facing status, without reusable invitation secrets."""
    result = {
        key: deepcopy(record[key])
        for key in ("id", "kind", "member", "state", "expires_at", "candidate")
        if key in record
    }
    if result["state"] in {"issued", "captured"} and now >= timestamp(
        result["expires_at"], "expires_at"
    ):
        result["state"] = "expired"
    return result


def telegram_status(runtime, options, state):
    """Configured, polling and observed delivery are separate facts."""
    manager = runtime.telegram
    bot = getattr(manager, "bot", {}) or {}
    config = options.get("telegram", {}) or {}
    health = runtime.health.get("telegram")
    observation = state.get("telegram", {}).get("observations", {}).get(str(bot.get("id")), {})
    if observation.get("config_digest") != getattr(manager, "_telegram_options_digest", None):
        observation = {}
    sent = []
    for event in state.get("outbox", {}).values():
        for delivery in event.get("deliveries", {}).values():
            target = delivery.get("target", {})
            if (
                delivery.get("state") == "sent"
                and delivery.get("sent_at")
                and target.get("channel") == "telegram"
                and bot.get("id") is not None
                and target.get("bot_id") == bot["id"]
            ):
                sent.append(delivery["sent_at"])
    active = [m for m in state["members"].values() if m.get("active")]
    group = state.get("telegram", {}).get("group_id")
    return {
        "configured": bool(config.get("token")),
        "bot_connected": manager is not None and health == "connected",
        "health": health or "not_configured",
        "bot_username": bot.get("username"),
        "group_ok": bool(group),
        "group_name": state.get("telegram", {}).get("group_name"),
        "members_linked": sum(type(m.get("telegram_id")) is int for m in active),
        "members_total": len(active),
        "send_ok": True if sent else None,
        "send_checked_at": max(sent) if sent else None,
        "commands_ok": True if observation.get("command_received_at") else None,
        "commands_checked_at": observation.get("command_received_at"),
        "text_ok": True if observation.get("text_received_at") else None,
        "text_checked_at": observation.get("text_received_at"),
    }


def project(runtime, entry, actor, now):
    """Expose editable member fields only to the owner; never return tokens."""
    view = runtime.engine.view(actor, now=now)
    state = runtime.engine.snapshot()
    privileged = view["role"] in {"owner", "parent"}
    result = {
        "view": view,
        "settings_revision": settings.current_revision(state),
        "onboarding": settings.onboarding(state),
        "members": [],
        "connections": {},
        "capabilities": [],
    }
    if view["role"] == "owner":
        result["enrollments"] = [
            enrollment_view(record, now)
            for record in state.get("enrollments", {}).values()
            if record["state"] in {"issued", "captured"}
            and now < timestamp(record["expires_at"], "expires_at")
        ]
        keys = (
            "id",
            "name",
            "role",
            "language",
            "active",
            "revision",
            "aliases",
            "ha_user_id",
            "birth_date",
            "avatar",
        )
        result["members"] = [
            {
                **{key: deepcopy(member[key]) for key in keys if key in member},
                "telegram_linked": type(member.get("telegram_id")) is int,
            }
            for member in state["members"].values()
        ]
    else:
        result["members"] = deepcopy(view["members"])
    if privileged:
        view["health"] = dict(runtime.health)
        options = dict(entry.options)
        conversation = options.get("conversation", {}) or {}
        result["connections"] = {
            "telegram": telegram_status(runtime, options, state),
            "conversation": {
                "configured": conversation.get("enabled") is True,
                "available": runtime.assistant is not None,
                "health": runtime.health.get("conversation"),
            },
            "mikrotik": {
                "configured": bool(options.get("mikrotik")),
                "available": runtime.network is not None,
                "health": runtime.health.get("mikrotik"),
            },
            "recipes": {
                "configured": bool(options.get("recipes")),
                "available": runtime.recipes is not None,
            },
        }
    visible = (
        result["members"] if privileged else [m for m in result["members"] if m["id"] == actor]
    )
    # Account/configuration details never enter the non-parent projection.
    checks = member_readiness(state, dict(entry.options) if privileged else {}, visible)
    if privileged:
        result["member_readiness"] = checks
    result["capabilities"] = capabilities(
        state,
        {"conversation": runtime.assistant is not None, "mikrotik": runtime.network is not None},
        runtime.health,
        checks,
    )
    return result


async def _scope(hass, connection, msg, *, owner=False):
    scope = await capture(hass, msg["entry_id"], connection.user.id, connection.user)
    await scope.check()
    if (owner and scope.role != "owner") or scope.role not in {"owner", "parent"}:
        raise DomainError("forbidden")
    return scope


def _error(connection, msg, error):
    code = error.code if isinstance(error, DomainError) else "storage_error"
    connection.send_error(msg["id"], code, code)


@websocket_api.websocket_command(
    {vol.Required("type"): "family_assistant/panel", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def panel(hass, connection, msg):
    try:
        scope = await capture(hass, msg["entry_id"], connection.user.id, connection.user)
        await scope.check()
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        connection.send_result(
            msg["id"], project(scope.runtime, entry, scope.actor, dt_util.utcnow())
        )
    except DomainError as error:
        _error(connection, msg, error)


async def _patch(hass, connection, msg, changes):
    try:
        scope = await _scope(hass, connection, msg, owner=True)
        payload = {"revision": msg["revision"], "changes": changes}
        result = await scope.engine.execute(
            scope.actor,
            "settings.patch",
            payload,
            msg["operation_id"],
            dt_util.utcnow(),
            guard=scope.guard,
        )
        await scope.after_execute("settings.patch", payload, msg["operation_id"], result)
        scope.notify()
        connection.send_result(msg["id"], {"settings": result, "success": True})
    except (DomainError, OSError) as error:
        _error(connection, msg, error)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/settings_save",
        vol.Required("entry_id"): str,
        vol.Required("settings"): dict,
        vol.Required("revision"): int,
        vol.Required("operation_id"): str,
    }
)
@websocket_api.async_response
async def settings_save(hass, connection, msg):
    await _patch(hass, connection, msg, msg["settings"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/module_toggle",
        vol.Required("entry_id"): str,
        vol.Required("module"): str,
        vol.Required("enabled"): bool,
        vol.Required("revision"): int,
        vol.Required("operation_id"): str,
    }
)
@websocket_api.async_response
async def module_toggle(hass, connection, msg):
    try:
        scope = await _scope(hass, connection, msg, owner=True)
        payload = {key: msg[key] for key in ("revision", "module", "enabled")}
        result = await scope.engine.execute(
            scope.actor,
            "settings.module_toggle",
            payload,
            msg["operation_id"],
            dt_util.utcnow(),
            guard=scope.guard,
        )
        await scope.after_execute("settings.module_toggle", payload, msg["operation_id"], result)
        scope.notify()
        connection.send_result(msg["id"], {"settings": result, "success": True})
    except (DomainError, OSError) as error:
        _error(connection, msg, error)


@websocket_api.websocket_command(
    {vol.Required("type"): "family_assistant/telegram_verify", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def telegram_verify(hass, connection, msg):
    try:
        scope = await _scope(hass, connection, msg)
        entry = hass.config_entries.async_get_entry(msg["entry_id"])
        connection.send_result(
            msg["id"], telegram_status(scope.runtime, dict(entry.options), scope.engine.snapshot())
        )
    except DomainError as error:
        _error(connection, msg, error)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/telegram_invite",
        vol.Required("entry_id"): str,
        vol.Optional("member_id"): str,
        vol.Optional("kind", default="member"): vol.In({"member", "group"}),
    }
)
@websocket_api.async_response
async def telegram_invite(hass, connection, msg):
    from .telegram.enrollment import Enrollment

    try:
        scope = await _scope(hass, connection, msg, owner=True)
        kind = msg.get("kind", "member")
        if (kind == "member" and not msg.get("member_id")) or (
            kind == "group" and "member_id" in msg
        ):
            raise DomainError("invalid_field", "member_id")
        manager = scope.runtime.telegram
        bot = getattr(manager, "bot", {}) or {}
        username = bot.get("username")
        if not username or manager is None:
            raise DomainError("telegram_unavailable")

        class GuardedEngine:
            async def system_update(self, kind, now, change):
                return await scope.engine.system_update(kind, now, change, guard=scope.guard)

        issued = await Enrollment(GuardedEngine()).issue(
            scope.actor, kind, dt_util.utcnow(), member_id=msg.get("member_id")
        )
        await scope.check()
        if scope.runtime.telegram is not manager:
            raise DomainError("conflict")
        scope.notify()
        connection.send_result(
            msg["id"],
            {
                **issued,
                "kind": kind,
                "member": msg.get("member_id"),
                "state": "issued",
                "url": f"https://t.me/{username}?start={issued['code']}"
                if kind == "member"
                else None,
                "instruction": (
                    f"https://t.me/{username}?start={issued['code']}"
                    if kind == "member"
                    else f"/family_setup@{username} {issued['code']}"
                ),
                "bot_username": username,
            },
        )
    except (DomainError, OSError) as error:
        _error(connection, msg, error)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/telegram_enrollment",
        vol.Required("entry_id"): str,
        vol.Required("enrollment_id"): str,
    }
)
@websocket_api.async_response
async def telegram_enrollment(hass, connection, msg):
    try:
        scope = await _scope(hass, connection, msg, owner=True)
        record = scope.engine.snapshot().get("enrollments", {}).get(msg["enrollment_id"])
        if record is None:
            raise DomainError("not_found")
        connection.send_result(msg["id"], enrollment_view(record, dt_util.utcnow()))
    except DomainError as error:
        _error(connection, msg, error)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/telegram_enrollment_confirm",
        vol.Required("entry_id"): str,
        vol.Required("enrollment_id"): str,
        vol.Required("candidate"): {vol.Required("chat_id"): int, vol.Required("user_id"): int},
    }
)
@websocket_api.async_response
async def telegram_enrollment_confirm(hass, connection, msg):
    """Confirm the displayed identity inside the canonical transaction lock."""
    from .telegram.enrollment import Enrollment

    try:
        scope = await _scope(hass, connection, msg, owner=True)
        expected = msg["candidate"]
        if any(type(value) is not int for value in expected.values()):
            raise DomainError("invalid_field", "candidate")

        class GuardedEngine:
            async def system_update(self, kind, now, change):
                def checked(ctx):
                    record = ctx.state.get("enrollments", {}).get(msg["enrollment_id"], {})
                    candidate = record.get("candidate", {})
                    if not candidate or any(
                        candidate.get(key) != value for key, value in expected.items()
                    ):
                        raise DomainError("conflict")
                    if record.get("state") == "confirmed":
                        linked = (
                            ctx.state["telegram"].get("group_id") == expected["chat_id"]
                            if record["kind"] == "group"
                            else ctx.state["members"].get(record["member"], {}).get("telegram_id")
                            == expected["user_id"]
                        )
                        if not linked:
                            raise DomainError("conflict")
                        return {"linked": True, "kind": record["kind"]}
                    return change(ctx)

                return await scope.engine.system_update(kind, now, checked, guard=scope.guard)

        result = await Enrollment(GuardedEngine()).confirm(
            scope.actor, msg["enrollment_id"], dt_util.utcnow()
        )
        # Linking the owner's own Telegram account advances that member revision.
        # Only refresh authorization for the notification/read response, never a write.
        current = await _scope(hass, connection, msg, owner=True)
        if current.runtime is not scope.runtime or current.actor != scope.actor:
            raise DomainError("conflict")
        current.notify()
        connection.send_result(msg["id"], result)
    except (DomainError, OSError) as error:
        _error(connection, msg, error)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "family_assistant/ai_sandbox_test",
        vol.Required("entry_id"): str,
        vol.Required("text"): str,
    }
)
@websocket_api.async_response
async def ai_sandbox_test(hass, connection, msg):
    """Parse only: no execute, live tools, jobs, notifications or provider calls."""
    from .court.parser import parse_message
    from .telegram.alarm_commands import parsed as parse_alarm
    from .telegram.intents import parse

    try:
        scope = await _scope(hass, connection, msg)
        raw = text(msg["text"], "text", 2000)
        now = dt_util.utcnow()
        state = scope.engine.snapshot()
        alarm_operations = parse_alarm(state, scope.engine.view(scope.actor, now=now), raw)
        if alarm_operations is not None:
            if "alarms" not in state["settings"]["modules"]:
                raise DomainError("module_disabled")
            connection.send_result(
                msg["id"],
                {
                    "recognized": True,
                    "simulated": True,
                    "intent": "alarm_commands",
                    "payload": {"operations": alarm_operations},
                },
            )
            return
        assessment = parse_message(raw, members=state["members"].values())
        if assessment.action == "assessments" and "court" in state["settings"]["modules"]:
            connection.send_result(
                msg["id"],
                {
                    "recognized": True,
                    "simulated": True,
                    "intent": "court.award",
                    "payload": {
                        "assessments": [
                            {
                                "member": item.child,
                                "points": 1 if item.kind == "plus" else -1,
                                "reason": item.reason,
                            }
                            for item in assessment.assessments
                        ]
                    },
                },
            )
            return
        intent = parse(state, scope.engine.view(scope.actor, now=now), raw, now)
        connection.send_result(
            msg["id"],
            {
                "recognized": intent is not None,
                "simulated": True,
                "intent": intent.action if intent else None,
                "payload": intent.payload if intent else None,
            },
        )
    except DomainError as error:
        _error(connection, msg, error)
