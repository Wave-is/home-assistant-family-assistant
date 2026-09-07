"""Poll lifecycle through actual Home Assistant options, WebSockets, and Store reload."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from aiohttp import ClientSession


def _assert_review_descriptor(descriptor):
    assert set(descriptor) == {"kind", "mode", "review_id"}
    assert descriptor["kind"] == "polls" and descriptor["mode"] == "review"
    assert re.fullmatch(r"PR[A-Za-z0-9_-]{16}", descriptor["review_id"])
    assert not ({"poll_id", "option_id", "ballot_revision"} & descriptor.keys())


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/polls-smoke"
    )
    token = hass.auth.async_create_access_token(refresh)
    session = ClientSession()
    try:
        ws = await session.ws_connect("http://127.0.0.1:8123/api/websocket")
        assert (await ws.receive_json())["type"] == "auth_required"
        await ws.send_json({"type": "auth", "access_token": token})
        assert (await ws.receive_json())["type"] == "auth_ok"
        yield ws
        await ws.close()
    finally:
        await session.close()
        hass.auth.async_remove_refresh_token(refresh)


async def _request(hass, entry, user, identifier, action, payload=None, operation=None):
    async with _socket(hass, user) as ws:
        message = (
            {
                "id": identifier,
                "type": "family_assistant/view",
                "entry_id": entry.entry_id,
            }
            if action == "view"
            else {
                "id": identifier,
                "type": "family_assistant/execute",
                "entry_id": entry.entry_id,
                "action": action,
                "payload": payload,
                "operation_id": operation or f"polls-ha-{identifier}",
            }
        )
        await ws.send_json(message)
        return await ws.receive_json()


async def _set_polls(hass, entry, user, enabled):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    if flow["type"] == "abort":
        return flow
    assert flow["type"] == "menu" and flow["step_id"] == "init", flow
    form = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "general"}
    )
    if form["type"] == "abort":
        return form
    assert form["type"] == "form" and form["step_id"] == "general", form
    values = dict(form["data_schema"]({}))
    values["polls"] = enabled
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    await hass.async_block_till_done()
    return result


def _protected(engine):
    snapshot = engine.snapshot()
    return {
        key: deepcopy(snapshot[key])
        for key in (
            "tasks",
            "task_series",
            "shopping",
            "shopping_series",
            "court",
            "rewards",
            "alarms",
            "alarm_runs",
            "routine_runs",
            "alarm_outputs",
        )
    }


def _outbox_intents(engine):
    return {
        event_id: {
            key: deepcopy(event.get(key)) for key in ("recipient", "key", "data", "created_at")
        }
        for event_id, event in engine.snapshot()["outbox"].items()
    }


async def verify_polls(hass, entry, owner, child_id):
    """Verify poll opt-in, ballot privacy, aggregate closure, replay and reload."""
    from ha_telegram_smoke import SyntheticTelegram
    from homeassistant import config_entries

    from custom_components.family_assistant.telegram.manager import TelegramManager
    from custom_components.family_assistant.telegram.messages import render, targets

    engine = entry.runtime_data.engine
    child_record = engine.snapshot()["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None
    original_modules = list(engine.snapshot()["settings"]["modules"])

    denied_options = await _set_polls(hass, entry, child, True)
    assert denied_options["type"] == "abort" and denied_options["reason"] == "forbidden"
    assert engine.snapshot()["settings"]["modules"] == original_modules
    enabled = await _set_polls(hass, entry, owner, True)
    assert enabled["type"] == "create_entry", enabled
    engine = entry.runtime_data.engine
    assert "polls" in engine.snapshot()["settings"]["modules"]
    assert set(engine.snapshot()["settings"]["modules"]) == {*original_modules, "polls"}

    child_projection = await _request(hass, entry, child, 1, "view")
    assert child_projection["success"], child_projection
    assert set(child_projection["result"]["polls"]) == {"open", "closed", "archived"}

    before_effects = _protected(engine)
    existing_poll_ids = set(engine.snapshot()["polls"])
    clock = datetime.now(UTC).replace(microsecond=0)
    question = "SYNTHETIC_PRIVATE_POLL_QUESTION"
    choices = ("SYNTHETIC_PRIVATE_POLL_ALPHA", "SYNTHETIC_PRIVATE_POLL_BETA")
    child_record = engine.snapshot()["members"][child_id]
    owner_record = engine.snapshot()["members"]["owner"]
    payload = {
        "actor_revision": owner_record["revision"],
        "question": question,
        "options": list(choices),
        "eligible": [{"member": child_id, "revision": child_record["revision"]}],
        "closes_at": (clock + timedelta(hours=1)).isoformat(),
        "confirm_private_ballot_limits": True,
    }

    child_create = await _request(
        hass,
        entry,
        child,
        2,
        "polls.create",
        payload,
        "polls-ha-child-create",
    )
    assert not child_create["success"] and child_create["error"]["code"] == "forbidden"
    assert _protected(engine) == before_effects

    created_response = await _request(
        hass, entry, owner, 3, "polls.create", payload, "polls-ha-create"
    )
    assert created_response["success"], created_response
    created = created_response["result"]
    assert created["id"].startswith("PL") and created["id"] not in existing_poll_ids
    assert created["revision"] == 1 and created["status"] == "open"
    replayed_create = await _request(
        hass, entry, owner, 4, "polls.create", payload, "polls-ha-create"
    )
    assert replayed_create["success"] and replayed_create["result"] == created

    owner_open = (await _request(hass, entry, owner, 5, "view"))["result"]["polls"]
    owner_row = next(row for row in owner_open["open"] if row["id"] == created["id"])
    assert owner_row["id"] == created["id"]
    assert owner_row["can_vote"] is False and owner_row["own_ballot"] is None
    assert owner_row["eligible"] == [
        {"member": child_id, "member_revision": child_record["revision"], "current": True}
    ]
    assert "poll_ballots" not in repr(owner_open)

    owner_vote = await _request(
        hass,
        entry,
        owner,
        6,
        "polls.vote",
        {
            "id": created["id"],
            "definition_revision": 1,
            "voter_revision": owner_record["revision"],
            "option_id": "O2",
            "ballot_revision": None,
        },
        "polls-ha-owner-not-eligible",
    )
    assert not owner_vote["success"] and owner_vote["error"]["code"] == "forbidden"

    vote_payload = {
        "id": created["id"],
        "definition_revision": 1,
        "voter_revision": child_record["revision"],
        "option_id": "O1",
        "ballot_revision": None,
    }
    vote_response = await _request(
        hass, entry, child, 7, "polls.vote", vote_payload, "polls-ha-vote"
    )
    assert vote_response["success"], vote_response
    vote = vote_response["result"]
    assert vote == {"id": created["id"], "ballot_revision": 1}
    vote_replay = await _request(hass, entry, child, 8, "polls.vote", vote_payload, "polls-ha-vote")
    assert vote_replay["success"] and vote_replay["result"] == vote

    child_open = (await _request(hass, entry, child, 9, "view"))["result"]["polls"]
    child_row = next(row for row in child_open["open"] if row["id"] == created["id"])
    assert child_row["own_ballot"] == {"option_id": "O1", "revision": 1}
    assert not ({"eligible", "created_by", "results", "cast_count"} & child_row.keys())
    assert "poll_ballots" not in repr(child_open)
    owner_after_vote = next(
        row
        for row in (await _request(hass, entry, owner, 10, "view"))["result"]["polls"]["open"]
        if row["id"] == created["id"]
    )
    assert owner_after_vote["own_ballot"] is None
    assert "results" not in owner_after_vote and "cast_count" not in owner_after_vote

    # Exercise the actual TelegramManager route before closure. Durable replies
    # contain only descriptors; private question/choice text is resolved at send time.
    state = engine.snapshot()
    telegram_id = state["members"][child_id].get("telegram_id")
    group_id = state["telegram"].get("group_id")
    assert type(telegram_id) is int and type(group_id) is int
    bot_ids = [int(value) for value in state["telegram"].get("offsets", {})]
    assert bot_ids
    bot_id = bot_ids[0]
    SyntheticTelegram.sent = []
    telegram = TelegramManager(
        hass,
        entry,
        entry.runtime_data,
        SyntheticTelegram(None, None),
        {"id": bot_id, "username": "synthetic_family_bot"},
    )
    update_id = state["telegram"].get("offsets", {}).get(str(bot_id), 0) + 100

    async def receive(text, *, callback=False, private=True):
        nonlocal update_id
        update_id += 1
        chat_id = telegram_id if private else group_id
        envelope = {
            "message_id": update_id,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": {
                "id": chat_id,
                "type": "private" if private else "supergroup",
                "title": "Synthetic family group",
            },
            "from": {"id": bot_id} if callback else {"id": telegram_id, "is_bot": False},
        }
        update = {"update_id": update_id}
        if callback:
            update["callback_query"] = {
                "id": f"poll-callback-{update_id}",
                "from": {"id": telegram_id, "is_bot": False},
                "data": text,
                "message": envelope,
            }
        else:
            envelope["text"] = text
            update["message"] = envelope
        await telegram.process(update)
        prefix = f"tg:{bot_id}:{update_id}:reply:"
        event = next(
            event
            for event in engine.snapshot()["outbox"].values()
            if event["id"].startswith(prefix)
        )
        assert event["key"] == "telegram_poll_reply"
        return update, event

    before_poll_replies = set(_outbox_intents(engine))
    _, list_event = await receive("/polls")
    assert list_event["data"]["descriptor"] == {"kind": "polls", "mode": "list"}
    assert question not in repr(list_event) and all(
        choice not in repr(list_event) for choice in choices
    )
    list_target = targets(list_event, engine.snapshot())[0]
    list_message = render(list_event, list_target, engine.snapshot(), now=datetime.now(UTC))
    assert question in list_message["text"] and choices[1] in list_message["text"]
    option_callback = next(
        button["callback_data"]
        for row in list_message["reply_markup"]["inline_keyboard"]
        for button in row
        if button["callback_data"] == f"ps:v:{created['id']}:O2"
    )
    assert len(option_callback.encode()) <= 64

    _, review_event = await receive(option_callback, callback=True)
    descriptor = review_event["data"]["descriptor"]
    _assert_review_descriptor(descriptor)
    review_target = targets(review_event, engine.snapshot())[0]
    review_message = render(review_event, review_target, engine.snapshot(), now=datetime.now(UTC))
    assert question in review_message["text"] and choices[1] in review_message["text"]
    confirm_callback = next(
        button["callback_data"]
        for row in review_message["reply_markup"]["inline_keyboard"]
        for button in row
        if button["callback_data"].startswith("pr:y:")
    )
    assert len(confirm_callback.encode()) <= 64

    confirm_update, saved_event = await receive(confirm_callback, callback=True)
    assert saved_event["data"]["descriptor"] == {
        "kind": "polls",
        "mode": "saved",
        "action": "vote",
    }
    ballot = engine.snapshot()["poll_ballots"][created["id"]][child_id]
    assert ballot["option_id"] == "O2" and ballot["revision"] == 2
    canonical = f"tg:{bot_id}:{confirm_update['update_id']}:action"
    assert engine.snapshot()["processed"][canonical]["result"] == {
        "id": created["id"],
        "ballot_revision": 2,
    }
    _, retry_event = await receive(confirm_callback, callback=True)
    assert retry_event["data"]["descriptor"] == saved_event["data"]["descriptor"]
    assert engine.snapshot()["poll_ballots"][created["id"]][child_id]["revision"] == 2

    _, group_event = await receive("/polls", private=False)
    assert group_event["data"]["descriptor"] == {"kind": "polls", "mode": "private"}
    group_target = targets(group_event, engine.snapshot())[0]
    group_message = render(group_event, group_target, engine.snapshot(), now=datetime.now(UTC))
    assert question not in group_message["text"]
    assert all(choice not in group_message["text"] for choice in choices)
    assert not ({"reply_markup"} & group_message.keys())

    new_events = {
        event_id: event
        for event_id, event in _outbox_intents(engine).items()
        if event_id not in before_poll_replies
    }
    assert new_events and all(
        event["key"] == "telegram_poll_reply" for event in new_events.values()
    )
    assert question not in repr(new_events)
    assert all(choice not in repr(new_events) for choice in choices)
    assert engine.snapshot()["telegram"].get("plans", {}).get(canonical) is None
    # Drive the real notification claim/dispatch path into the synthetic client.
    worker = telegram.notifications
    live_clock = worker.clock
    delivery_start = datetime.now(UTC)
    try:
        for attempt in range(1, 91):
            delivery_now = delivery_start + timedelta(seconds=attempt * 2)
            worker.clock = lambda delivery_now=delivery_now: delivery_now
            await worker.run(delivery_now, limit=20)
            current_event = engine.snapshot()["outbox"][list_event["id"]]
            if current_event["state"] == "sent":
                break
    finally:
        worker.clock = live_clock
    current_event = engine.snapshot()["outbox"][list_event["id"]]
    delivery_status = {
        "state": current_event["state"],
        "deliveries": {
            delivery_id: {
                "state": delivery.get("state"),
                "error": delivery.get("error"),
            }
            for delivery_id, delivery in current_event.get("deliveries", {}).items()
        },
    }
    assert current_event["state"] == "sent", delivery_status
    assert any(question in message.get("text", "") for message in SyntheticTelegram.sent)

    close_payload = {
        "id": created["id"],
        "revision": created["revision"],
        "actor_revision": owner_record["revision"],
    }
    close_response = await _request(
        hass, entry, owner, 11, "polls.close", close_payload, "polls-ha-close"
    )
    assert close_response["success"], close_response
    closed = close_response["result"]
    assert closed == {"id": created["id"], "revision": 2, "status": "closed"}
    child_closed = next(
        row
        for row in (await _request(hass, entry, child, 12, "view"))["result"]["polls"]["closed"]
        if row["id"] == created["id"]
    )
    assert child_closed["results"] == [
        {"option_id": "O1", "count": 0},
        {"option_id": "O2", "count": 1},
    ]
    assert child_closed["cast_count"] == 1
    assert child_closed["own_ballot"] == {"option_id": "O2", "revision": 2}
    assert _protected(engine) == before_effects
    private_journals = str(
        {
            "audit": engine.snapshot()["audit"],
            "processed": engine.snapshot()["processed"],
            "outbox": engine.snapshot()["outbox"],
            "telegram": engine.snapshot()["telegram"].get("plans", {}),
        }
    )
    assert question not in private_journals
    assert all(choice not in private_journals for choice in choices)

    persisted = engine.snapshot()
    expected_polls = deepcopy(persisted["polls"])
    expected_ballots = deepcopy(persisted["poll_ballots"])
    expected_processed = {
        key: deepcopy(persisted["processed"][key])
        for key in ("polls-ha-create", "polls-ha-vote", "polls-ha-close")
    }
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == config_entries.ConfigEntryState.LOADED
    engine = entry.runtime_data.engine
    reloaded = engine.snapshot()
    assert reloaded["polls"] == expected_polls
    assert reloaded["poll_ballots"] == expected_ballots
    assert all(reloaded["processed"][key] == value for key, value in expected_processed.items())
    # Core unload normally records shutdown of the synthetic siren previously
    # exercised by another helper. That lifecycle receipt is not a poll effect.
    # Keep exact comparisons for every household bucket and then pin the new
    # output baseline for all subsequent poll module/replay operations.
    post_reload_effects = _protected(engine)
    for key in before_effects:
        if key != "alarm_outputs":
            assert post_reload_effects[key] == before_effects[key], key
    assert set(post_reload_effects["alarm_outputs"]) == set(before_effects["alarm_outputs"])
    before_effects["alarm_outputs"] = post_reload_effects["alarm_outputs"]

    before_replays = engine.snapshot()
    vote_after_reload = await _request(
        hass, entry, child, 13, "polls.vote", vote_payload, "polls-ha-vote"
    )
    close_after_reload = await _request(
        hass, entry, owner, 14, "polls.close", close_payload, "polls-ha-close"
    )
    assert vote_after_reload["success"] and vote_after_reload["result"] == vote
    assert close_after_reload["success"] and close_after_reload["result"] == closed
    assert engine.snapshot() == before_replays

    disabled = await _set_polls(hass, entry, owner, False)
    assert disabled["type"] == "create_entry", disabled
    engine = entry.runtime_data.engine
    assert "polls" not in engine.snapshot()["settings"]["modules"]
    for identifier, user in enumerate((owner, child), 15):
        hidden = await _request(hass, entry, user, identifier, "view")
        assert hidden["success"] and "polls" not in hidden["result"]
    disabled_replay = await _request(
        hass, entry, child, 17, "polls.vote", vote_payload, "polls-ha-vote"
    )
    assert not disabled_replay["success"]
    assert disabled_replay["error"]["code"] == "module_disabled"
    assert _protected(engine) == before_effects

    reenabled = await _set_polls(hass, entry, owner, True)
    assert reenabled["type"] == "create_entry", reenabled
    engine = entry.runtime_data.engine
    final = (await _request(hass, entry, child, 18, "view"))["result"]["polls"]
    assert any(row["id"] == created["id"] for row in final["closed"])
    assert engine.snapshot()["polls"] == expected_polls
    assert engine.snapshot()["poll_ballots"] == expected_ballots
    assert _protected(engine) == before_effects

    exposed = str([state.as_dict() for state in hass.states.async_all()])
    assert question not in exposed
    assert all(choice not in exposed for choice in choices)
    print(
        "PASS: actual HA polls opt-in, WebSocket authority, private ballots, aggregates, "
        "Store reload and exact replay"
    )
    return created["id"]
