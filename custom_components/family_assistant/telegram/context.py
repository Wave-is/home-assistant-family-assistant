"""Resolve reply context without treating quoted Telegram text as authority.

Poll text is rendered only at delivery time and must not be copied automatically
into an assistant request through Telegram's reply metadata.  A user can still
explicitly paste the same words as new message content; that is ordinary,
untrusted user input rather than an automatic export of a prior private view.
"""

MAX_QUOTED_TEXT = 2000


def _own_bot_quote(message, bot):
    quoted = message.get("reply_to_message", {})
    bot_id = bot.get("id") if isinstance(bot, dict) else None
    sender_id = quoted.get("from", {}).get("id") if isinstance(quoted, dict) else None
    return type(bot_id) is int and type(sender_id) is int and sender_id == bot_id


def _reply_event(state, message, bot):
    if not _own_bot_quote(message, bot):
        return None
    quoted = message.get("reply_to_message", {})
    message_id, chat_id = quoted.get("message_id"), message.get("chat", {}).get("id")
    if type(message_id) is not int or type(chat_id) is not int:
        return None
    outbox = state.get("outbox", {}) if isinstance(state, dict) else {}
    if not isinstance(outbox, dict):
        return None
    for event in reversed(list(outbox.values())):
        if not isinstance(event, dict):
            continue
        deliveries = event.get("deliveries", {})
        if not isinstance(deliveries, dict):
            continue
        for delivery in deliveries.values():
            if not isinstance(delivery, dict):
                continue
            target = delivery.get("target", {})
            if (
                isinstance(target, dict)
                and target.get("channel") == "telegram"
                and target.get("bot_id") == bot["id"]
                and str(target.get("id")) == str(chat_id)
                and delivery.get("receipt") == str(message_id)
            ):
                return event
    return None


def reply_refs(state, message, bot):
    event = _reply_event(state, message, bot)
    if event is None or event.get("key") == "telegram_poll_reply":
        return ()
    data = event.get("data", {})
    if not isinstance(data, dict):
        return ()
    refs = data.get("refs", [data["id"]] if "id" in data else [])
    return tuple(refs) if isinstance(refs, list) else ()


def reply_quote(state, message, bot):
    """Return bounded untrusted quote text, suppressing private poll history."""
    quoted = message.get("reply_to_message", {})
    value = quoted.get("text") if isinstance(quoted, dict) else None
    if not isinstance(value, str):
        return ""
    bot_id = bot.get("id") if isinstance(bot, dict) else None
    sender_id = quoted.get("from", {}).get("id")
    if type(bot_id) is not int or type(sender_id) is not int:
        return ""
    if sender_id != bot_id:
        return value[:MAX_QUOTED_TEXT]
    event = _reply_event(state, message, bot)
    if event is None or event.get("key") == "telegram_poll_reply":
        return ""
    return value[:MAX_QUOTED_TEXT]


def result_refs(result):
    if "items" in result:
        return [ref for item in result["items"] for ref in result_refs(item)]
    return [result["id"]] if isinstance(result.get("id"), str) else []
