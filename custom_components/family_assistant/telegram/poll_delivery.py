"""Current-recipient checks for opaque, short-lived poll reply descriptors."""

from ..domain.validation import DomainError, timestamp
from .polls import render_reply

KEY = "telegram_poll_reply"


def current(event, state, now):
    """Fail closed on expiry, identity changes, or a stale private review.

    Only the constant direct-chat instruction may be addressed to the current
    family group. Questions, results and review buttons never fall back there.
    """
    try:
        data = event["data"]
        actor = state["members"][data["actor"]]
        descriptor = data["descriptor"]
        if (
            event.get("key") != KEY
            or event.get("recipient") != actor["id"]
            or actor.get("active") is not True
            or type(data.get("actor_revision")) is not int
            or actor.get("revision") != data["actor_revision"]
            or type(data.get("bot_id")) is not int
            or data["bot_id"] <= 0
            or type(data.get("chat_id")) is not int
            or not actor.get("telegram_id")
            or timestamp(now, "now") >= timestamp(data["expires_at"], "expires_at")
        ):
            return False
        if data["chat_id"] != actor["telegram_id"] and not (
            descriptor == {"kind": "polls", "mode": "private"}
            and data["chat_id"] == state["telegram"].get("group_id")
        ):
            return False
        # Render transiently to validate exact descriptor and source revisions;
        # no resulting private content is retained in the durable event.
        render_reply(state, actor["id"], descriptor, now, actor.get("language", "en"))
        return True
    except (DomainError, KeyError, TypeError, ValueError, AttributeError):
        return False
