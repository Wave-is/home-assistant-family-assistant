"""Private digest Telegram quotes never become automatic assistant context."""

from custom_components.family_assistant.telegram.context import reply_quote, reply_refs

BOT = {"id": 9001, "username": "family_test_bot"}
CHAT = 7001
MESSAGE_ID = 321
CANARY = "PRIVATE DIGEST QUESTION / TASK / SCHOOL CANARY"


def delivered_event(key="family_digest", *, bot_id=9001, chat_id=CHAT, receipt=MESSAGE_ID):
    return {
        "id": "event-1",
        "key": key,
        "recipient": "child",
        "data": {
            "schema": 1,
            "kind": "morning",
            "period_key": "2026-09-07/morning",
        },
        "state": "sent",
        "deliveries": {
            "delivery": {
                "state": "sent",
                "receipt": str(receipt),
                "target": {
                    "channel": "telegram",
                    "id": chat_id,
                    "bot_id": bot_id,
                },
            }
        },
    }


def reply_message(*, sender=9001, chat_id=CHAT, message_id=MESSAGE_ID, text=CANARY):
    return {
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": CHAT, "is_bot": False},
        "text": "ordinary new user text",
        "reply_to_message": {
            "message_id": message_id,
            "from": {"id": sender, "is_bot": sender == BOT["id"]},
            "text": text,
        },
    }


def test_proven_digest_delivery_exports_neither_quote_nor_refs():
    state = {"outbox": {"event-1": delivered_event()}}
    message = reply_message()
    assert reply_quote(state, message, BOT) == ""
    assert reply_refs(state, message, BOT) == ()
    exported = {
        "quoted_text": reply_quote(state, message, BOT),
        "refs": reply_refs(state, message, BOT),
    }
    assert CANARY not in repr(exported)


def test_own_bot_quote_without_exact_receipt_fails_closed():
    state = {"outbox": {"event-1": delivered_event(receipt=999)}}
    message = reply_message()
    assert reply_quote(state, message, BOT) == ""
    assert reply_refs(state, message, BOT) == ()


def test_foreign_bot_chat_or_delivery_target_cannot_authorize_digest_quote():
    for event, message in (
        (delivered_event(bot_id=9002), reply_message()),
        (delivered_event(chat_id=CHAT + 1), reply_message()),
        (delivered_event(), reply_message(chat_id=CHAT + 1)),
    ):
        state = {"outbox": {"event-1": event}}
        assert reply_quote(state, message, BOT) == ""
        assert reply_refs(state, message, BOT) == ()


def test_quote_from_a_different_bot_remains_bounded_untrusted_input():
    state = {"outbox": {"event-1": delivered_event()}}
    message = reply_message()  # authored by bot 9001
    other_bot = {"id": 9002}
    assert reply_quote(state, message, other_bot) == CANARY
    assert reply_refs(state, message, other_bot) == ()


def test_ordinary_proven_own_bot_delivery_keeps_bounded_untrusted_quote_and_refs():
    event = delivered_event(key="task_reminder")
    event["data"] = {"id": "T000001"}
    state = {"outbox": {"event-1": event}}
    message = reply_message(text="Ordinary prior reply")
    assert reply_quote(state, message, BOT) == "Ordinary prior reply"
    assert reply_refs(state, message, BOT) == ("T000001",)


def test_user_or_third_party_quote_remains_bounded_untrusted_user_input():
    message = reply_message(sender=CHAT, text="x" * 3000)
    assert reply_quote({"outbox": {}}, message, BOT) == "x" * 2000
    assert reply_refs({"outbox": {}}, message, BOT) == ()


def test_malformed_outbox_or_receipt_never_exports_digest_text():
    message = reply_message()
    for state in ({}, {"outbox": []}, {"outbox": {"bad": None}}, {"outbox": {"bad": {}}}):
        assert reply_quote(state, message, BOT) == ""
        assert reply_refs(state, message, BOT) == ()
