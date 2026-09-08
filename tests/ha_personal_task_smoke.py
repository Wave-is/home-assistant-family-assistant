"""Personal reminder lifecycle via real HA authentication, websocket and Store."""

from datetime import UTC, datetime, timedelta


async def verify_personal_tasks(hass, entry, owner, child_id):
    from aiohttp import WSMsgType
    from ha_school_smoke import _request, _socket
    from ha_telegram_smoke import SyntheticTelegram, process_current
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.const import DOMAIN, SCHEMA_VERSION
    from custom_components.family_assistant.telegram.manager import TelegramManager

    # This section asserts whole-Store equality after denied commands. Drain the
    # fixture clock first: an unrelated five-second reconciliation may legitimately
    # commit between websocket roundtrips. The later entry reload restores it.
    await entry.runtime_data.scheduler.stop()
    engine = entry.runtime_data.engine
    child = await hass.auth.async_get_user(engine.snapshot()["members"][child_id]["ha_user_id"])
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    created = await _request(
        hass,
        entry,
        child,
        1,
        "tasks.create",
        {
            "title": "Synthetic own-only HA reminder",
            "assignee": child_id,
            "personal": True,
            "due_at": due,
        },
        "personal-ha-create",
    )
    assert created["success"], created.get("error", {}).get("code")
    task = created["result"]
    assert task["delivery_scope"] == "personal" and task["report_type"] == "none"
    before = engine.snapshot()
    parent_view = (await _request(hass, entry, owner, 2, "view"))["result"]
    assert not any(item["id"] == task["id"] for item in parent_view["tasks"])
    assert not any(row["id"] == "personal-ha-create" for row in parent_view["audit"])
    for action in ["complete", "revise", "archive", "cancel"]:
        denied = await _request(
            hass,
            entry,
            owner,
            3,
            f"tasks.{action}",
            {"id": task["id"], "revision": task["revision"]},
            f"personal-ha-denied-{action}",
        )
        assert not denied["success"] and denied["error"]["code"] == "forbidden"
    assert engine.snapshot() == before
    denied_link = await _request(
        hass,
        entry,
        owner,
        3,
        "calendar.save",
        {
            "title": "Synthetic link must not publish",
            "start": due,
            "end": (datetime.fromisoformat(due) + timedelta(hours=1)).isoformat(),
            "participants": [child_id],
            "task_ids": [task["id"]],
        },
        "personal-ha-denied-link",
    )
    assert not denied_link["success"] and denied_link["error"]["code"] == "invalid_field"
    assert engine.snapshot() == before
    # Already authenticated websocket cannot continue after HA user deactivation.
    async with _socket(hass, child) as ws:
        await hass.auth.async_update_user(child, is_active=False)
        try:
            # Native HA actively terminates authenticated sessions on revocation;
            # there is no connection left on which to expect an API error reply.
            closed = await ws.receive(timeout=5)
            assert closed.type == WSMsgType.CLOSE and closed.data == 1000
            assert engine.snapshot() == before
        finally:
            await hass.auth.async_update_user(child, is_active=True)
    bot = {"id": 1000, "username": "synthetic_family_bot"}
    receiver = TelegramManager(hass, entry, entry.runtime_data, SyntheticTelegram(None, None), bot)
    state = engine.snapshot()
    telegram_id = state["members"][child_id]["telegram_id"]
    update_id = max(state["telegram"].get("offsets", {}).get("1000", 0) + 1, 90000)
    await process_current(
        entry.runtime_data,
        receiver,
        {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "text": "/tasks",
                "from": {"id": telegram_id, "is_bot": False},
                "chat": {"id": telegram_id, "type": "private"},
            },
        },
    )
    reply = next(
        event
        for event in engine.snapshot()["outbox"].values()
        if event["id"].startswith(f"tg:1000:{update_id}:reply:")
        and event["key"] == "telegram_reply"
    )
    assert reply["data"]["private_context"] is True and task["title"] in reply["data"]["text"]
    assert reply["data"]["refs"] == []  # Read-only lists have no mutation receipt.
    for action, expected in [("complete", "completed"), ("archive", "archived")]:
        payload = {"id": task["id"], "revision": task["revision"]}
        result = await _request(
            hass, entry, child, 4, f"tasks.{action}", payload, f"personal-ha-{action}"
        )
        assert result["success"], result.get("error", {}).get("code")
        task = result["result"]
        assert task["status"] == expected
        replay = await _request(
            hass, entry, child, 4, f"tasks.{action}", payload, f"personal-ha-{action}"
        )
        assert replay["result"] == task
    # Existing runtime Store key/version are authoritative; use the Store API.
    saved = await Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}").async_load()
    assert saved["tasks"][task["id"]] == engine.snapshot()["tasks"][task["id"]]
    assert saved["outbox"][reply["id"]]["data"]["private_context"] is True
    assert engine.snapshot()["court"] == before["court"]
    print(
        "PASS: personal reminder HA websocket scope, active-user revocation, "
        "self completion, Store, exact replay and persistent private Telegram list context"
    )
    return task["id"]
