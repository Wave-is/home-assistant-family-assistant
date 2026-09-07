"""Telegram reply quotes cannot export send-time-only private poll text."""

from copy import deepcopy

from custom_components.family_assistant.telegram.context import (
    MAX_QUOTED_TEXT,
    reply_quote,
    reply_refs,
)

BOT = {"id": 1234}
CHAT = 1001


def delivered_event(key="telegram_reply", *, bot_id=1234, chat_id=CHAT):
    return {
        "id": "E000001",
        "key": key,
        "data": {"id": "T000001", "refs": ["T000001"]},
        "deliveries": {
            "D000001": {
                "state": "sent",
                "receipt": "77",
                "target": {
                    "channel": "telegram",
                    "id": chat_id,
                    "bot_id": bot_id,
                },
            }
        },
    }


def reply_message(text, *, sender_id=1234, chat_id=CHAT, message_id=77):
    return {
        "chat": {"id": chat_id},
        "text": "new explicit user message",
        "reply_to_message": {
            "from": {"id": sender_id, "is_bot": sender_id == BOT["id"]},
            "message_id": message_id,
            "text": text,
        },
    }


def test_proven_poll_reply_suppresses_quote_and_references():
    question = "PRIVATE_POLL_QUESTION_CANARY"
    choice = "PRIVATE_POLL_CHOICE_CANARY"
    state = {"outbox": {"E000001": delivered_event("telegram_poll_reply")}}
    message = reply_message(f"{question}\n1. {choice}")

    assert reply_quote(state, message, BOT) == ""
    assert reply_refs(state, message, BOT) == ()
    assert question not in reply_quote(state, message, BOT)
    assert choice not in reply_quote(state, message, BOT)


def test_unknown_or_mismatched_own_bot_quote_fails_closed():
    base = {"outbox": {"E000001": delivered_event()}}
    for state, message in (
        ({"outbox": {}}, reply_message("erased private history")),
        (base, reply_message("wrong chat", chat_id=CHAT + 1)),
        (
            {"outbox": {"E000001": delivered_event(bot_id=BOT["id"] + 1)}},
            reply_message("foreign bot receipt"),
        ),
        (
            {"outbox": {"E000001": delivered_event(chat_id=CHAT + 1)}},
            reply_message("foreign chat receipt"),
        ),
        (base, reply_message("wrong receipt", message_id=78)),
    ):
        assert reply_quote(state, message, BOT) == ""
        assert reply_refs(state, message, BOT) == ()


def test_proven_ordinary_own_bot_reply_retains_bounded_untrusted_quote_and_refs():
    state = {"outbox": {"E000001": delivered_event()}}
    value = "ordinary reply " + "x" * (MAX_QUOTED_TEXT + 20)
    message = reply_message(value)

    assert reply_quote(state, message, BOT) == value[:MAX_QUOTED_TEXT]
    assert reply_refs(state, message, BOT) == ("T000001",)

    data_id = deepcopy(state)
    data_id["outbox"]["E000001"]["data"] = {"id": "T000002"}
    assert reply_refs(data_id, message, BOT) == ("T000002",)


def test_user_or_third_party_quote_remains_explicit_untrusted_text_without_refs():
    value = "user explicitly supplied quote " + "y" * (MAX_QUOTED_TEXT + 20)
    message = reply_message(value, sender_id=9999)
    state = {"outbox": {"E000001": delivered_event()}}

    assert reply_quote(state, message, BOT) == value[:MAX_QUOTED_TEXT]
    assert reply_refs(state, message, BOT) == ()
    assert message["text"] == "new explicit user message"


def test_malformed_quote_metadata_is_empty_and_non_authoritative():
    state = {"outbox": {"E000001": delivered_event()}}
    for message in ({}, {"reply_to_message": {"from": {"id": True}, "text": "bad"}}):
        assert reply_quote(state, message, BOT) == ""
        assert reply_refs(state, message, BOT) == ()

    proven_receipt_without_text = {
        "chat": {"id": CHAT},
        "reply_to_message": {
            "from": {"id": BOT["id"]},
            "message_id": 77,
            "text": {"not": "text"},
        },
    }
    assert reply_quote(state, proven_receipt_without_text, BOT) == ""
    assert reply_refs(state, proven_receipt_without_text, BOT) == ("T000001",)
