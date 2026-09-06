"""End-to-end domain scenarios for shopping, tasks, court and membership."""

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError


async def test_child_purchase_requires_approval_then_tracks_partial_amount(engine, now):
    item = await engine.execute(
        "child", "shopping.add", {"name": "Apples", "quantity": 5, "unit": "kg"}, "a", now
    )
    assert item["status"] == "pending"
    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "child", "shopping.purchase", {"id": item["id"], "revision": item["revision"]}, "b", now
        )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child", "shopping.approve", {"id": item["id"], "revision": item["revision"]}, "b", now
        )
    await engine.execute(
        "parent", "shopping.approve", {"id": item["id"], "revision": item["revision"]}, "c", now
    )
    partial = await engine.execute(
        "child",
        "shopping.purchase",
        {
            "id": item["id"],
            "revision": engine.snapshot()["shopping"][item["id"]]["revision"],
            "quantity": 2,
        },
        "d",
        now,
    )
    assert partial["purchased"] == 2
    assert partial["status"] == "approved"
    for bad in ({"quantity": 4}, {"quantity": -1}, {"quantity": True}, {"unit": "l"}):
        with pytest.raises(DomainError):
            await engine.execute(
                "child",
                "shopping.purchase",
                {
                    "id": item["id"],
                    "revision": engine.snapshot()["shopping"][item["id"]]["revision"],
                    **bad,
                },
                "e",
                now,
            )
    done = await engine.execute(
        "child",
        "shopping.purchase",
        {"id": item["id"], "revision": engine.snapshot()["shopping"][item["id"]]["revision"]},
        "f",
        now,
    )
    assert done["status"] == "purchased"
    assert engine.snapshot()["tasks"] == {}


async def test_task_full_review_workflow_and_private_view(engine, now):
    item = await engine.execute(
        "parent",
        "tasks.create",
        {"title": "Tidy desk", "assignee": "child", "checklist": ["Books", "Pencils"]},
        "a",
        now,
    )
    assert engine.view("sibling")["tasks"] == []
    assert engine.view("child")["tasks"][0]["id"] == item["id"]
    await engine.execute(
        "child",
        "tasks.check",
        {"id": item["id"], "revision": item["revision"], "checklist_index": 0, "done": True},
        "b",
        now,
    )
    submitted = await engine.execute(
        "child",
        "tasks.submit",
        {
            "id": item["id"],
            "revision": engine.snapshot()["tasks"][item["id"]]["revision"],
            "report": "Ready",
        },
        "c",
        now,
    )
    assert submitted["status"] == "submitted"
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child",
            "tasks.complete",
            {"id": item["id"], "revision": engine.snapshot()["tasks"][item["id"]]["revision"]},
            "d",
            now,
        )
    revised = await engine.execute(
        "parent",
        "tasks.request_changes",
        {
            "id": item["id"],
            "revision": engine.snapshot()["tasks"][item["id"]]["revision"],
            "note": "Pencils too",
        },
        "e",
        now,
    )
    assert revised["status"] == "needs_changes"
    await engine.execute(
        "child",
        "tasks.submit",
        {
            "id": item["id"],
            "revision": engine.snapshot()["tasks"][item["id"]]["revision"],
            "report": "Fixed",
        },
        "f",
        now,
    )
    completed = await engine.execute(
        "owner",
        "tasks.complete",
        {"id": item["id"], "revision": engine.snapshot()["tasks"][item["id"]]["revision"]},
        "g",
        now,
    )
    assert completed["status"] == "completed"
    assert completed["closed_at"]
    archived = await engine.execute(
        "parent", "tasks.archive", {"id": item["id"], "revision": completed["revision"]}, "h", now
    )
    assert archived["previous_status"] == "completed"
    assert len(engine.snapshot()["audit"]) == 7


async def test_parent_can_confirm_work_without_child_message(engine, now):
    task = await engine.execute(
        "parent", "tasks.create", {"title": "Sweep", "assignee": "child"}, "a", now
    )
    result = await engine.execute(
        "parent", "tasks.complete", {"id": task["id"], "revision": task["revision"]}, "b", now
    )
    assert result["status"] == "completed"


async def test_child_cannot_change_parent_deadline_or_others_task(engine, now):
    task = await engine.execute(
        "parent", "tasks.create", {"title": "Sweep", "assignee": "child"}, "a", now
    )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child",
            "tasks.revise",
            {"id": task["id"], "revision": task["revision"], "title": "Skip"},
            "b",
            now,
        )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "sibling",
            "tasks.submit",
            {"id": task["id"], "revision": task["revision"], "report": "Ready"},
            "b",
            now,
        )


async def test_court_reversal_keeps_reason_and_does_not_change_other_events(engine, now):
    first = await engine.execute(
        "parent",
        "court.award",
        {"member": "child", "points": -1, "reason": "Missed chore"},
        "a",
        now,
    )
    second = await engine.execute(
        "parent", "court.award", {"member": "child", "points": 2, "reason": "Helped"}, "b", now
    )
    appeal = await engine.execute(
        "child",
        "court.appeal",
        {"id": first["id"], "revision": first["revision"], "reason": "Was done"},
        "c",
        now,
    )
    await engine.execute(
        "parent",
        "court.reverse",
        {"id": first["id"], "revision": appeal["revision"], "reason": "Confirmed"},
        "d",
        now,
    )
    records = engine.snapshot()["court"]
    assert records[first["id"]]["reason"] == "Missed chore"
    assert records[first["id"]]["status"] == "reversed"
    assert records[second["id"]]["status"] == "active"
    assert engine.view("sibling")["court"] == []


async def test_owner_cannot_remove_last_owner(engine, now):
    with pytest.raises(DomainError, match="last_owner"):
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": "owner",
                "revision": engine.snapshot()["members"]["owner"]["revision"],
                "name": "Owner",
                "role": "adult",
            },
            "a",
            now,
        )


async def test_duplicate_ha_identity_rejected(engine, now):
    with pytest.raises(DomainError, match="duplicate_identity"):
        await engine.execute(
            "owner",
            "members.save",
            {"name": "New person", "role": "adult", "ha_user_id": "synthetic-child"},
            "a",
            now,
        )


async def test_disabled_module_cannot_be_invoked(store, now):
    engine = Engine(new_state("synthetic", "Example", modules=[]), store.save)
    with pytest.raises(DomainError, match="module_disabled"):
        await engine.execute("owner", "shopping.add", {"name": "Milk"}, "a", now)


def test_ha_actor_resolution_uses_identity_not_name(engine):
    assert engine.actor_for_ha("synthetic-child") == "child"
    for identity in (None, "Child", "synthetic-other"):
        with pytest.raises(DomainError, match="forbidden"):
            engine.actor_for_ha(identity)


@pytest.mark.asyncio
async def test_owner_cannot_unlink_last_dashboard_identity(engine, now):
    with pytest.raises(DomainError, match="last_owner"):
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": "owner",
                "name": "Owner",
                "revision": engine.snapshot()["members"]["owner"]["revision"],
                "role": "owner",
                "ha_user_id": None,
            },
            "unlink",
            now,
        )


@pytest.mark.asyncio
async def test_batch_notifications_do_not_overwrite_each_other(engine, now):
    await engine.execute(
        "owner",
        "batch",
        {
            "commands": [
                {"action": "tasks.create", "payload": {"title": "Clean desk", "assignee": "child"}},
                {"action": "tasks.create", "payload": {"title": "Pack bag", "assignee": "child"}},
            ]
        },
        "two-tasks",
        now,
    )
    assert len(engine.snapshot()["outbox"]) == 2
