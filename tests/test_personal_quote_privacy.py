"""Automatically quoting personal task replies must not export them to a model."""

from datetime import timedelta

import pytest
from test_digest_quote_privacy import BOT, delivered_event, reply_message
from test_personal_tasks import create

from custom_components.family_assistant.domain.task_access import event_visible
from custom_components.family_assistant.telegram.context import (
    PersonalReply,
    reply_quote,
    reply_refs,
)
from custom_components.family_assistant.telegram.reply_delivery import current
from custom_components.family_assistant.telegram.router import route


@pytest.mark.parametrize(
    "key", ["task_assigned", "task_reminder", "task_personal_due", "telegram_reply"]
)
def test_personal_event_quotes_are_not_exported_but_ids_allow_fresh_local_commands(key):
    event = delivered_event(key)
    event["data"].update(id="T000001", refs=["T000001"])
    state = {"outbox": {"event-1": event}, "tasks": {"T000001": {"delivery_scope": "personal"}}}
    assert reply_quote(state, reply_message(), BOT) == ""
    assert reply_refs(state, reply_message(), BOT) == ("T000001",)


def test_read_only_list_without_command_receipt_is_persistently_private():
    event = delivered_event("telegram_reply")
    event["data"].update(private_context=True, refs=[])
    # A retained flag survives task archival/removal and requires no text matching.
    assert reply_quote({"outbox": {"event-1": event}}, reply_message(), BOT) == ""


@pytest.mark.asyncio
async def test_real_route_marks_personal_list_and_confirmation_but_not_shared_group(engine, now):
    item = await create(engine, now)
    private = await route(engine, "child", "/tasks", "list", now, private=True)
    assert isinstance(private, PersonalReply) and item["title"] in private
    group = await route(engine, "child", "/tasks", "group-list", now, private=False)
    assert not isinstance(group, PersonalReply) and item["title"] not in group
    done = await route(engine, "child", f"/approve {item['id']}", "complete", now, private=True)
    assert isinstance(done, PersonalReply) and item["title"] in done


def test_personal_reply_envelope_never_allows_group_fallback(now):
    state = {
        "members": {"child": {"id": "child", "active": True, "telegram_id": 123, "revision": 2}},
        "telegram": {"group_id": -456},
    }
    event = {
        "key": "telegram_reply",
        "recipient": "child",
        "data": {
            "actor": "child",
            "actor_revision": 2,
            "private_context": True,
            "chat_id": 123,
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
    }
    assert current(event, state, now)
    assert event_visible(state, {"id": "child"}, event)
    assert not event_visible(state, {"id": "owner"}, event)
    event["data"]["chat_id"] = -456
    assert not current(event, state, now)
    event["data"]["chat_id"] = 123
    del event["data"]["actor_revision"]
    assert not current(event, state, now)
