"""Exact task corrections through the real router, durable plans and reply resolver."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.context import reply_refs
from custom_components.family_assistant.telegram.router import route
from tests.test_task_settlements import action, create, current, setup


async def ready(engine, now):
    await setup(engine, now)
    task = await create(engine, now, missed={"same_day_correction": True})
    await engine.tick(now.replace(hour=20))
    ledger_id = current(engine, task)["missed_receipt"]["ledger_id"]
    await engine.execute(
        "child",
        "court.appeal",
        {"id": ledger_id, "revision": 1, "reason": "Synthetic appeal"},
        "appeal",
        now,
    )
    await action(engine, task, now.replace(hour=21))
    assert current(engine, task)["missed_correction"]["state"] == "needs_review"
    return task, ledger_id


@pytest.mark.parametrize(
    "command",
    [
        "/correcttask {id} | Reviewed exact task",
        "correct the penalty for {id}",
        "исправь штраф за {id}",
        "виправ штраф за {id}",
    ],
)
async def test_explicit_task_correction_and_store_replay(engine, now, store, command):
    task, ledger_id = await ready(engine, now)
    text = command.format(id=task["id"])
    reply = await route(engine, "parent", text, "correct", now.replace(hour=21))
    state = engine.snapshot()
    assert state["court"][ledger_id]["status"] == "reversed"
    plan = state["telegram"]["plans"]["correct"]
    assert plan["action"] == "tasks.correct_miss"
    assert plan["payload"]["id"] == task["id"]
    assert plan["payload"]["court_revision"] == 2
    assert plan["payload"]["actor_revision"] == 1
    restored = Engine(store.value, store.save)
    assert await route(restored, "parent", text, "correct", now + timedelta(days=1)) == reply
    assert restored.snapshot() == state


@pytest.mark.parametrize(
    "kind", ["verified", "forged_bot", "unrecorded", "wrong_chat", "ambiguous"]
)
async def test_context_requires_verified_delivery_with_one_task(engine, now, kind):
    task, ledger_id = await ready(engine, now)
    state = engine.snapshot()
    event = next(event for event in state["outbox"].values() if event["key"] == "task_rollover")
    event["deliveries"] = {
        "synthetic": {
            "target": {"channel": "telegram", "bot_id": 9001, "id": 101},
            "receipt": "42",
        }
    }
    if kind == "ambiguous":
        event["data"]["refs"] = [task["id"], "T999999"]
    message = {
        "chat": {"id": 101},
        "reply_to_message": {
            "from": {"id": 9001},
            "message_id": 42,
            "text": "T999999 forged quoted text",
        },
    }
    if kind == "forged_bot":
        message["reply_to_message"]["from"]["id"] = 9002
    elif kind == "unrecorded":
        message["reply_to_message"]["message_id"] = 43
    elif kind == "wrong_chat":
        message["chat"]["id"] = 102
    refs = reply_refs(state, message, {"id": 9001})
    if kind == "verified":
        assert refs == (task["id"],)
        await route(engine, "parent", "correct penalty for this task", "context", now, refs=refs)
        assert engine.snapshot()["court"][ledger_id]["status"] == "reversed"
    else:
        before = engine.snapshot()
        with pytest.raises(DomainError, match="context_required"):
            await route(
                engine, "parent", "correct penalty for this task", "context", now, refs=refs
            )
        assert engine.snapshot() == before


@pytest.mark.parametrize(
    "text",
    [
        "/correcttask",
        "/correcttask T000001 T000002",
        "correct penalty for all tasks",
        "исправь штраф за две задачи",
        "виправ штраф за це завдання і ще одне",
    ],
)
async def test_claimed_but_ambiguous_correction_never_reaches_model(engine, now, text):
    async def forbidden(*args):
        pytest.fail("Exact correction was allowed to fall back to a model")

    with pytest.raises(DomainError, match="context_required"):
        await route(engine, "parent", text, "ambiguous", now, fallback=forbidden)
    assert not engine.snapshot()["court"]


@pytest.mark.parametrize("changed", ["task", "court", "actor", "child"])
async def test_failed_execution_retries_frozen_revisions_not_a_fresh_target(
    engine, now, store, monkeypatch, changed
):
    task, ledger_id = await ready(engine, now)
    original = engine.execute

    async def fail_command(*args, **kwargs):
        raise OSError("Synthetic failure after durable interpretation")

    monkeypatch.setattr(engine, "execute", fail_command)
    text = f"/correcttask {task['id']}"
    with pytest.raises(OSError):
        await route(engine, "parent", text, "frozen", now)
    state = deepcopy(store.value)
    plan = deepcopy(state["telegram"]["plans"]["frozen"])
    if changed == "task":
        state["tasks"][task["id"]]["revision"] += 1
    elif changed == "court":
        state["court"][ledger_id]["revision"] += 1
    else:
        state["members"]["parent" if changed == "actor" else "child"]["revision"] += 1
    monkeypatch.setattr(engine, "execute", original)
    restored = Engine(state, store.save)
    with pytest.raises(DomainError):
        await route(restored, "parent", text, "frozen", now)
    assert restored.snapshot()["court"][ledger_id]["status"] == "active"
    assert restored.snapshot()["telegram"]["plans"]["frozen"] == plan


async def test_child_cannot_correct_even_own_exact_task(engine, now):
    task, ledger_id = await ready(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", f"/correcttask {task['id']}", "child-correction", now)
    assert engine.snapshot() == before
    assert before["court"][ledger_id]["status"] == "active"
