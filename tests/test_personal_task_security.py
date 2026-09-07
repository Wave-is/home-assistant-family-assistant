"""Owner authority does not override another member's private reminder scope."""

import json
from copy import deepcopy

import pytest
from test_family_calendar import enable_calendar
from test_personal_tasks import create

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.task_delivery import current_task_event
from custom_components.family_assistant.domain.validation import DomainError


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "parent", "sibling", "adult"])
async def test_other_people_cannot_view_or_act_even_by_batch(engine, now, actor):
    item = await create(engine, now)
    view = engine.view(actor, now=now)
    assert item["title"] not in json.dumps(view) and item["id"] not in json.dumps(view)
    for action in ["complete", "archive", "accept", "cancel", "start", "revise"]:
        command = {
            "action": f"tasks.{action}",
            "payload": {"id": item["id"], "revision": item["revision"]},
        }
        for is_batch in [False, True]:
            before = engine.snapshot()
            with pytest.raises(DomainError, match="forbidden"):
                await engine.execute(
                    actor,
                    "batch" if is_batch else command["action"],
                    {"commands": [command]} if is_batch else command["payload"],
                    "attempt",
                    now,
                )
            assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_mixed_batch_does_not_leak_through_parent_audit(engine, now):
    result = await engine.execute(
        "child",
        "batch",
        {
            "commands": [
                {
                    "action": "tasks.create",
                    "payload": {"title": "Synthetic secret", "assignee": "child", "personal": True},
                },
                {
                    "action": "tasks.create",
                    "payload": {"title": "Shared chore", "assignee": "child"},
                },
            ]
        },
        "mixed-personal",
        now,
    )
    for actor in ["owner", "parent"]:
        view = engine.view(actor, now=now)
        assert "Synthetic secret" not in json.dumps(view)
        assert not any(event["id"] == "mixed-personal" for event in view["audit"])
        assert any(item["title"] == "Shared chore" for item in view["tasks"])
    assert result["items"][0]["delivery_scope"] == "personal"


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "child"])
async def test_personal_record_cannot_be_published_as_calendar_link(engine, now, actor):
    await enable_calendar(engine, now)
    task = await create(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            actor,
            "calendar.save",
            {
                "title": "Synthetic event",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
                "participants": ["child"],
                "task_ids": [task["id"]],
            },
            "link-personal",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "child"])
async def test_rebound_identity_cannot_view_act_replay_or_receive(engine, store, now, actor):
    item = await create(engine, now, actor)
    state = engine.snapshot()
    state["members"][actor]["revision"] += 1
    changed = Engine(state, store.save)
    assert item["title"] not in json.dumps(changed.view(actor, now=now))
    with pytest.raises(DomainError, match="forbidden"):
        await create(changed, now, actor)
    with pytest.raises(DomainError, match="forbidden"):
        await changed.execute(
            actor,
            "tasks.complete",
            {"id": item["id"], "revision": item["revision"]},
            "complete",
            now,
        )
    event = next(iter(state["outbox"].values()))
    assert not current_task_event(state, event)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "task_review",
        "task_overdue",
        "task_incident_closed",
        "task_assigned",
        "task_reminder",
        "task_personal_due",
    ],
)
@pytest.mark.parametrize("recipient", ["family", "parents", "owner", "child"])
async def test_forged_parent_review_and_wrong_recipients_are_rejected(engine, now, key, recipient):
    item = await create(engine, now)
    state = engine.snapshot()
    event = deepcopy(next(iter(state["outbox"].values())))
    event.update(key=key, recipient=recipient)
    event["data"]["due_at"] = item["due_at"]
    expected = recipient == "child" and key in {
        "task_assigned",
        "task_reminder",
        "task_personal_due",
    }
    assert current_task_event(state, event) is expected
    if expected:
        del event["data"]["member_revision"]
        assert not current_task_event(state, event)


@pytest.mark.asyncio
async def test_delivery_review_and_its_audit_remain_personal(engine, store, now):
    await create(engine, now, "parent")
    state = engine.snapshot()
    event = next(iter(state["outbox"].values()))
    event["state"] = "failed"
    engine = Engine(state, store.save)
    assert engine.view("owner", now=now)["delivery_issues"] == []
    assert len(engine.view("parent", now=now)["delivery_issues"]) == 1
    payload = {"id": event["id"], "reason": "Synthetic personal reason"}
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("owner", "notifications.resolve", payload, "owner-resolve", now)
    await engine.execute("parent", "notifications.resolve", payload, "self-resolve", now)
    assert payload["reason"] not in json.dumps(engine.view("owner", now=now))
    state = engine.snapshot()
    state["members"]["parent"]["revision"] += 1
    restored = Engine(state, store.save)
    with pytest.raises(DomainError, match="forbidden"):
        await restored.execute("parent", "notifications.resolve", payload, "self-resolve", now)
