"""Real isolated HA: natural commands and durable reviewer reminders, no devices."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta


async def _assigned_shopping(hass, entry, owner, child_user, child, now):
    from ha_digests_smoke import _execute

    from custom_components.family_assistant.telegram.router import route

    engine = entry.runtime_data.engine
    command = "поручи Роман купить 2 кг груш"
    operation = "completion-assigned-shopping"
    answer = await route(engine, "owner", command, operation, now, private=True)
    row = next(item for item in engine.snapshot()["shopping"].values() if item["name"] == "груш")
    assert (row["buyer"], row["quantity"], row["unit"]) == (child, 2, "кг")
    assert "buyer_revision" not in row
    mine = await route(engine, child, "/shopping mine", "completion-buy-mine", now, private=True)
    assert "груш" in mine and "яблок" not in mine
    shared = await route(engine, child, "/shopping", "completion-buy-shared", now, private=True)
    assert "груш" in shared and "яблок" in shared
    decorated = await _execute(
        hass,
        entry,
        owner,
        20,
        "shopping.edit",
        {
            "id": row["id"],
            "revision": row["revision"],
            "name": row["name"],
            "category": "Synthetic fruit",
            "store": "Synthetic market",
            "note": "Shared",
            "barcode": "96385074",
            "buyer": child,
        },
        "completion-shopping-metadata",
    )
    assert decorated["success"], decorated
    # The responsible buyer is metadata, not an exclusive purchase permission.
    helped = await _execute(
        hass,
        entry,
        owner,
        21,
        "shopping.purchase",
        {"id": row["id"], "revision": decorated["result"]["revision"], "quantity": 1},
        "completion-shopping-helper",
    )
    assert helped["success"] and helped["result"]["purchased"] == 1, helped
    before = engine.snapshot()["shopping"][row["id"]]
    assignment = f"change buyer {row['id']} to Owner"
    assigned_answer = await route(
        engine, "owner", assignment, "completion-shopping-reassign", now, private=True
    )
    edited = engine.snapshot()["shopping"][row["id"]]
    assert edited["buyer"] == "owner"
    for field in (
        "name",
        "quantity",
        "unit",
        "purchased",
        "status",
        "creator",
        "category",
        "store",
        "note",
        "barcode",
    ):
        assert edited[field] == before[field], field
    # Exact buyer identity is checked under the authenticated Engine lock.
    state = engine.snapshot()
    stale = await _execute(
        hass,
        entry,
        owner,
        22,
        "shopping.add",
        {
            "name": "Must not exist",
            "buyer": child,
            "buyer_revision": state["members"][child]["revision"] + 1,
        },
        "completion-shopping-stale-buyer",
    )
    assert not stale["success"] and engine.snapshot() == state, stale
    forbidden = await _execute(
        hass,
        entry,
        child_user,
        23,
        "shopping.edit",
        {
            **{key: edited[key] for key in ("id", "revision", "name", "category", "store", "note")},
            "buyer": child,
        },
        "completion-shopping-child-reassign",
    )
    assert not forbidden["success"] and engine.snapshot() == state, forbidden
    await route(
        engine,
        "owner",
        f"сними покупателя {row['id']}",
        "completion-shopping-unassign",
        now,
        private=True,
    )
    assert engine.snapshot()["shopping"][row["id"]]["buyer"] is None
    # Replaying the earlier assignment after reload must not undo this clearing.
    return [
        (command, operation, answer),
        (assignment, "completion-shopping-reassign", assigned_answer),
    ]


async def verify_command_completion(hass, owner):
    from ha_digests_smoke import _execute
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.telegram.context import result_refs
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
        store = Store(hass, 1, f"family_assistant.{entry.entry_id}")
        shopping_replays = await _assigned_shopping(hass, entry, owner, child_user, child, now)
        numbered_operation = "completion-numbered-tasks"
        numbered_command = (
            "создай 2 задачи для Роман на завтра с фотоотчетом:\n"
            "1. Подготовить Книгу\n"
            "2. для Owner: Проверить Рюкзак через неделю без отчета"
        )
        numbered_reply = await route(
            engine, "owner", numbered_command, numbered_operation, now, private=True
        )
        numbered_state = engine.snapshot()
        numbered_plan = deepcopy(numbered_state["telegram"]["plans"][numbered_operation])
        numbered_receipt = deepcopy(numbered_state["processed"][numbered_operation]["result"])
        first, second = numbered_receipt["items"]
        numbered_ids = [first["id"], second["id"]]
        assert len(set(numbered_ids)) == 2
        assert all(identifier in numbered_reply for identifier in numbered_ids)
        assert result_refs(numbered_receipt) == numbered_ids
        assert (first["title"], first["assignee"], first["report_type"]) == (
            "Подготовить Книгу",
            child,
            "photo",
        )
        assert (second["title"], second["assignee"], second["report_type"]) == (
            "Проверить Рюкзак",
            "owner",
            "none",
        )
        assert datetime.fromisoformat(first["due_at"]).date() == (now + timedelta(days=1)).date()
        assert datetime.fromisoformat(second["due_at"]).date() == (now + timedelta(days=7)).date()
        for command, item in zip(
            numbered_plan["payload"]["commands"], numbered_receipt["items"], strict=True
        ):
            assert command["action"] == "tasks.create"
            assert command["payload"]["assignee_revision"] == item["assignee_revision"]
            assert command["payload"]["due_at"] == item["due_at"]
        persisted = await store.async_load()
        assert persisted["telegram"]["plans"][numbered_operation] == numbered_plan
        assert persisted["processed"][numbered_operation]["result"] == numbered_receipt

        # These are the real grammar and Engine on a native synthetic ConfigEntry.
        # A valid first line must not become a task or pending plan on any rejection.
        for suffix, actor, content, expected in (
            (
                "child",
                engine.actor_for_ha(child_user.id),
                "2 tasks:\n1. task Роман Первое дело\n2. task Owner Чужое дело",
                "forbidden",
            ),
            (
                "unknown",
                "owner",
                "2 tasks:\n1. task Роман Первое дело\n2. for Unconfigured Member: Второе дело",
                "unknown_member",
            ),
            (
                "nested",
                "owner",
                "2 tasks for Роман:\n1. Первое дело\n2. 2 tasks for Owner: Второе дело",
                "invalid_field",
            ),
        ):
            before_rejection = engine.snapshot()
            stored_before_rejection = await store.async_load()
            try:
                await route(
                    engine, actor, content, f"completion-numbered-{suffix}", now, private=True
                )
            except DomainError as error:
                assert error.code == expected, (suffix, error.code)
            else:
                raise AssertionError(f"Numbered batch unexpectedly accepted: {suffix}")
            assert engine.snapshot() == before_rejection
            assert await store.async_load() == stored_before_rejection

        # Exercise authenticated domain atomicity too: the second create fails
        # its recipient revision after the first has modified only working state.
        stale_batch = deepcopy(numbered_plan["payload"])
        stale_batch["commands"][1]["payload"]["assignee_revision"] += 1
        before_atomic = engine.snapshot()
        stored_before_atomic = await store.async_load()
        rejected = await _execute(
            hass, entry, owner, 10, "batch", stale_batch, "completion-numbered-atomic"
        )
        assert not rejected["success"], rejected
        assert engine.snapshot() == before_atomic
        assert await store.async_load() == stored_before_atomic

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
        saved = await store.async_load()
        assert saved["tasks"] == state["tasks"] and saved["shopping"] == state["shopping"]
        assert saved["telegram"]["plans"][numbered_operation] == numbered_plan
        assert saved["processed"][numbered_operation]["result"] == numbered_receipt
        baseline = deepcopy(state)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED
        await entry.runtime_data.scheduler.stop()
        engine = entry.runtime_data.engine
        assert engine.snapshot()["tasks"] == baseline["tasks"]
        assert engine.snapshot()["shopping"] == baseline["shopping"]
        shopping_before_replay = engine.snapshot()
        for content, operation, expected_reply in shopping_replays:
            assert (
                await route(engine, "owner", content, operation, now, private=True)
                == expected_reply
            )
        assert engine.snapshot() == shopping_before_replay
        assert (await store.async_load())["shopping"] == baseline["shopping"]
        # A later received date must replay the original plan and IDs, not resolve
        # "tomorrow" again or create another batch after native Store reload.
        before_replay = engine.snapshot()
        stored_before_replay = await store.async_load()
        assert (
            await route(
                engine,
                "owner",
                numbered_command,
                numbered_operation,
                now + timedelta(days=3),
                private=True,
            )
            == numbered_reply
        )
        assert engine.snapshot() == before_replay
        assert await store.async_load() == stored_before_replay
        assert (
            result_refs(engine.snapshot()["processed"][numbered_operation]["result"])
            == numbered_ids
        )
        for item in numbered_receipt["items"]:
            assert engine.snapshot()["tasks"][item["id"]] == baseline["tasks"][item["id"]]
        await engine.tick(clock + timedelta(minutes=1))
        await route(engine, "owner", task_command, "completion-grammar-task", now, private=True)
        await route(engine, "owner", shopping_command, "completion-grammar-buy", now, private=True)
        state = engine.snapshot()
        assert len(state["tasks"]) == 4 and len(state["shopping"]) == 2
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
            "scoped list, numbered two-task atomic creation/denial/rollback/task IDs/date-stable "
            "replay, assigned shared shopping/filter/metadata/helper purchase/"
            "stale identity/replay, "
            "native reviewer policy/submit/Store/reload/replay/completion"
        )
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
