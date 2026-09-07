"""Personal reminders use real transactions, own-only delivery and no court."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.task_delivery import current_task_event
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram.messages import render, targets


async def create(engine, now, actor="child", **extra):
    return await engine.execute(
        actor,
        "tasks.create",
        {
            "title": "Fictional private appointment",
            "assignee": actor,
            "personal": True,
            "due_at": (now + timedelta(hours=1)).isoformat(),
            **extra,
        },
        "personal-create",
        now,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "parent", "child", "adult"])
async def test_personal_self_completion_archive_and_reload(engine, store, now, actor):
    task = await create(engine, now, actor)
    assert task["delivery_scope"] == "personal"
    assert task["report_type"] == "none"
    assert task["deadline_policy"] == {"reminder_minutes": 0, "grace_minutes": 0, "penalty": 0}
    for action, expected in [("complete", "completed"), ("archive", "archived")]:
        payload = {"id": task["id"], "revision": task["revision"]}
        task = await engine.execute(actor, f"tasks.{action}", payload, action, now)
        assert task["status"] == expected
        assert await engine.execute(actor, f"tasks.{action}", payload, action, now) == task
    restored = Engine(store.value, store.save)
    assert restored.view(actor, now=now)["tasks"] == engine.view(actor, now=now)["tasks"]
    assert not restored.snapshot()["court"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"report_type": "text"},
        {"report_type": "photo"},
        {"grace_minutes": 1},
        {"penalty": -1},
        {"personal": "true"},
        {"personal": 1},
        {"assignee": "sibling"},
    ],
)
async def test_personal_invalid_creation_is_atomic(engine, now, extra):
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await create(engine, now, **extra)
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["child", "owner"])
@pytest.mark.parametrize(
    "action,extra",
    [
        ("submit", {"report": "No parent review"}),
        ("request_changes", {"note": "No review"}),
        ("revise", {"assignee": "parent"}),
        ("revise", {"penalty": -1}),
        ("revise", {"grace_minutes": 1}),
    ],
)
async def test_personal_policy_cannot_be_broadened(engine, now, actor, action, extra):
    task = await create(engine, now, actor)
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute(
            actor,
            f"tasks.{action}",
            {"id": task["id"], "revision": task["revision"], **extra},
            "invalid",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_due_once_across_reload_without_family_incidents_or_penalties(engine, store, now):
    task = await create(engine, now, reminder_minutes=15)
    await engine.tick(now + timedelta(minutes=45))
    await engine.tick(now + timedelta(hours=1))
    restored = Engine(store.value, store.save)
    await restored.tick(now + timedelta(days=4))
    state = restored.snapshot()
    events = [event for event in state["outbox"].values() if event["data"].get("id") == task["id"]]
    assert [event["key"] for event in events] == [
        "task_assigned",
        "task_reminder",
        "task_personal_due",
    ]
    assert all(
        event["recipient"] == "child" and current_task_event(state, event) for event in events
    )
    assert not state["court"] and not state["incidents"]
    current = state["tasks"][task["id"]]
    await restored.execute(
        "child",
        "tasks.complete",
        {"id": task["id"], "revision": current["revision"]},
        "complete",
        now + timedelta(days=4),
    )
    assert all(not current_task_event(restored.snapshot(), event) for event in events)


@pytest.mark.asyncio
async def test_removal_of_deadline_supersedes_due_notice(engine, now):
    task = await create(engine, now)
    await engine.tick(now + timedelta(hours=1))
    await engine.execute(
        "child",
        "tasks.revise",
        {"id": task["id"], "revision": task["revision"], "due_at": None},
        "remove-due",
        now + timedelta(hours=1),
    )
    state = engine.snapshot()
    due = next(event for event in state["outbox"].values() if event["key"] == "task_personal_due")
    assert due["state"] == "superseded" and not current_task_event(state, due)


@pytest.mark.asyncio
async def test_personal_due_persistence_failure_does_not_consume_reminder(engine, store, now):
    await create(engine, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(now + timedelta(hours=1))
    assert engine.snapshot() == before
    store.fail = False
    await engine.tick(now + timedelta(hours=1))
    assert sum(event["key"] == "task_personal_due" for event in store.value["outbox"].values()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "uk", "en"])
async def test_due_real_telegram_render_is_self_only_and_revoked(engine, now, language):
    task = await create(engine, now)
    await engine.tick(now + timedelta(hours=1))
    state = engine.snapshot()
    state["telegram"]["group_id"] = -112233
    state["members"]["child"].update(telegram_id=1122, language=language)
    state["members"]["owner"].update(telegram_id=3344)
    event = next(event for event in state["outbox"].values() if event["key"] == "task_personal_due")
    selected = targets(event, state)
    assert selected == [{"channel": "telegram", "id": 1122, "language": language}]
    message = render(event, selected[0], state)
    assert task["title"] in message["text"] and message["chat_id"] == 1122
    changed = deepcopy(state)
    changed["members"]["child"]["revision"] += 1
    assert targets(event, changed) == []
    with pytest.raises(DeliveryError, match="delivery_revoked"):
        render(event, selected[0], changed)
    with pytest.raises(DeliveryError, match="delivery_revoked"):
        render(event, {**selected[0], "id": -112233}, state)
