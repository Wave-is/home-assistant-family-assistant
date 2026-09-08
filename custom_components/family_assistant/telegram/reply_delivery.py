"""Identity-bound authorization for newly queued ordinary Telegram replies."""

from ..domain.validation import DomainError, timestamp


def current(event, state, now):
    """Keep legacy envelopes compatible, but never revive a pinned old identity."""
    data = event.get("data", {})
    if "admission_context" in data:
        from .admission import current as admission_current

        if not admission_current(state, data, now):
            return False
    if data.get("private_context") is True:
        actor = state.get("members", {}).get(data.get("actor"), {})
        if "actor_revision" not in data or data.get("chat_id") != actor.get("telegram_id"):
            return False
    if "actor_revision" not in data:
        return True
    try:
        actor = state["members"][data["actor"]]
        if (
            event.get("recipient") != actor["id"]
            or actor.get("active") is not True
            or type(data["actor_revision"]) is not int
            or data["actor_revision"] != actor.get("revision")
            or not actor.get("telegram_id")
            or data["chat_id"] not in {actor["telegram_id"], state["telegram"].get("group_id")}
            or type(data["chat_id"]) is not int
        ):
            return False
        if "expires_at" in data:
            return timestamp(now, "now") < timestamp(data["expires_at"], "expires_at")
        return True
    except (DomainError, KeyError, TypeError, ValueError, AttributeError):
        return False
