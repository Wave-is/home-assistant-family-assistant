"""Real isolated HA: natural commands and durable reviewer reminders, no devices."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta


async def verify_command_completion(hass, owner):
    from ha_digests_smoke import _execute
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.telegram.router import route

    flow = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner.id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Synthetic command completion",
            "owner_name": "Owner",
            "language": "ru",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"shopping": True, "tasks": True, "court": True}
    )
    assert created["type"] == "create_entry", created
    entry = created["result"]
    await hass.async_block_till_done()
    child_user = await hass.auth.async_create_user("Synthetic command child")
    try:
        assert entry.state == ConfigEntryState.LOADED
        await entry.runtime_data.scheduler.stop()
        response = await _execute(
            hass,
            entry,
            owner,
            1,
            "members.save",
            {"name": "Роман", "role": "child", "language": "ru", "ha_user_id": child_user.id},
            "completion-child",
        )
        assert response["success"], response
        child = response["result"]["id"]
        engine = entry.runtime_data.engine
        now = datetime.now(UTC)
        task_command = "задача Роман убрать стол на завтра с фотоотчетом"
        await route(engine, "owner", task_command, "completion-grammar-task", now, private=True)
        task = next(iter(engine.snapshot()["tasks"].values()))
        assert task["title"] == "убрать стол" and task["assignee"] == child
        assert task["report_type"] == "photo"
        assert datetime.fromisoformat(task["due_at"]).date() == (now + timedelta(days=1)).date()
        shopping_command = "добавь 2 кг яблок в покупки"
        await route(engine, "owner", shopping_command, "completion-grammar-buy", now, private=True)
        purchase = next(iter(engine.snapshot()["shopping"].values()))
        assert purchase["name"] == "яблок" and float(purchase["quantity"]) == 2
        assert purchase["unit"] == "кг"
        reply = await route(
            engine, "owner", "покажи задачи Роман", "completion-list", now, private=True
        )
        assert "убрать стол" in reply
        response = await _execute(
            hass,
            entry,
            owner,
            2,
            "tasks.create",
            {"title": "Synthetic review", "assignee": child, "review_minutes": 5},
            "completion-review-task",
        )
        assert response["success"], response
        review_task = response["result"]
        submitted = await _execute(
            hass,
            entry,
            child_user,
            3,
            "tasks.submit",
            {"id": review_task["id"], "revision": review_task["revision"], "report": "Done"},
            "completion-submit",
        )
        assert submitted["success"], submitted
        clock = datetime.fromisoformat(submitted["result"]["submitted_at"]) + timedelta(minutes=6)
        await engine.tick(clock)
        state = engine.snapshot()
        reminders = [e for e in state["outbox"].values() if e["key"] == "task_review_overdue"]
        assert len(reminders) == 1 and reminders[0]["recipient"] == "parents"
        assert not state["court"]
        saved = await Store(hass, 1, f"family_assistant.{entry.entry_id}").async_load()
        assert saved["tasks"] == state["tasks"] and saved["shopping"] == state["shopping"]
        baseline = deepcopy(state)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED
        await entry.runtime_data.scheduler.stop()
        engine = entry.runtime_data.engine
        assert engine.snapshot()["tasks"] == baseline["tasks"]
        await engine.tick(clock + timedelta(minutes=1))
        await route(engine, "owner", task_command, "completion-grammar-task", now, private=True)
        await route(engine, "owner", shopping_command, "completion-grammar-buy", now, private=True)
        state = engine.snapshot()
        assert len(state["tasks"]) == 2 and len(state["shopping"]) == 1
        assert len([e for e in state["outbox"].values() if e["key"] == "task_review_overdue"]) == 1
        current = state["tasks"][review_task["id"]]
        completed = await _execute(
            hass,
            entry,
            owner,
            4,
            "tasks.complete",
            {"id": current["id"], "revision": current["revision"]},
            "completion-approve",
        )
        assert completed["success"], completed
        assert engine.snapshot()["outbox"][reminders[0]["id"]]["state"] == "superseded"
        assert not engine.snapshot()["court"]
        print(
            "PASS: actual HA natural task report/deadline and shopping quantity commands, "
            "scoped list, native reviewer policy/submit/Store/reload/replay/completion"
        )
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
