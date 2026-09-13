"""Late, private, identity/options/HA-ACL checked Telegram observations."""

import re

from ..domain.validation import DomainError, timestamp
from ..notifications import DeliveryError
from . import config, observations
from .copy import render


def current(state, data, now):
    try:
        descriptor = data["home_status"]
        actor = state["members"][data["actor"]]
        return (
            isinstance(descriptor, dict)
            and set(descriptor) == {"section", "group_id", "config_marker"}
            and config.request(descriptor["section"], descriptor["group_id"]) is not None
            and isinstance(descriptor["config_marker"], str)
            and re.fullmatch(r"[0-9a-f]{64}", descriptor["config_marker"]) is not None
            and config.MODULE in state["settings"]["modules"]
            and actor.get("role") in config.ROLES
            and bool(actor.get("ha_user_id"))
            and actor.get("active") is True
            and data.get("private_context") is True
            and data.get("text") == ""
            and type(data.get("actor_revision")) is int
            and actor.get("revision") == data.get("actor_revision")
            and type(data.get("chat_id")) is int
            and data["chat_id"] > 0
            and data["chat_id"] == actor.get("telegram_id")
            and 0
            < (timestamp(data["expires_at"], "expires_at") - timestamp(now, "now")).total_seconds()
            <= 300
        )
    except (DomainError, KeyError, TypeError, ValueError, AttributeError):
        return False


async def payload(manager, event, target):
    from homeassistant.util import dt as dt_util

    data = event["data"]

    def guard(state):
        manager._manager_guard(state)
        if (
            not current(state, data, dt_util.utcnow())
            or event.get("recipient") != data["actor"]
            or target.get("id") != data["chat_id"]
            or data.get("bot_id") != manager.bot["id"]
            or observations.configuration_marker(
                manager.runtime, config.from_options(manager.entry.options)
            )
            != data["home_status"]["config_marker"]
        ):
            raise DomainError("forbidden")

    try:
        user = await observations.actor_user(
            manager.hass, manager.entry, manager.runtime, data["actor"], guard
        )
        guard(manager.runtime.engine.snapshot())
        descriptor = data["home_status"]
        snapshot = observations.project(
            manager.hass,
            manager.entry,
            manager.runtime,
            data["actor"],
            user,
            dt_util.utcnow(),
            section=descriptor["section"],
            group_id=descriptor["group_id"],
        )
        actor = manager.runtime.engine.snapshot()["members"][data["actor"]]
        result = {"chat_id": data["chat_id"], "text": render(snapshot, actor.get("language", "en"))}
        if data.get("reply_to"):
            result["reply_parameters"] = {
                "message_id": data["reply_to"],
                "allow_sending_without_reply": True,
            }
        return result
    except (DomainError, KeyError, TypeError, ValueError, AttributeError):
        raise DeliveryError("delivery_revoked") from None
