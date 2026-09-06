"""Resolve reply targets only from our persisted delivery receipts, not quoted text."""


def reply_refs(state, message, bot):
    quoted = message.get("reply_to_message", {})
    if quoted.get("from", {}).get("id") != bot["id"]:
        return ()
    message_id, chat_id = quoted.get("message_id"), message.get("chat", {}).get("id")
    if type(message_id) is not int or type(chat_id) is not int:
        return ()
    for event in reversed(list(state["outbox"].values())):
        for delivery in event.get("deliveries", {}).values():
            target = delivery.get("target", {})
            if (
                target.get("channel") == "telegram"
                and target.get("bot_id") == bot["id"]
                and str(target.get("id")) == str(chat_id)
                and delivery.get("receipt") == str(message_id)
            ):
                data = event.get("data", {})
                return tuple(data.get("refs", [data["id"]] if "id" in data else []))
    return ()


def result_refs(result):
    if "items" in result:
        return [ref for item in result["items"] for ref in result_refs(item)]
    return [result["id"]] if isinstance(result.get("id"), str) else []
