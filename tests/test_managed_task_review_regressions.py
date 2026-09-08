"""Actual Engine guards for managed revisions, private receipt replay and audit."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import school_work, task_access
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError

CANARY = "REVIEW-REGRESSION-CANARY-c892"


@pytest.fixture
def managed_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"] = sorted(
        set(state["settings"]["modules"]) | {"school", "routines", "maintenance", "pantry"}
    )
    state["settings"]["timezone"] = "UTC"
    state["telegram"]["group_id"] = -10001
    for index, member in enumerate(state["members"].values(), 101):
        member["telegram_id"] = index
    return Engine(state, store.save)


def homework_payload(now, **changes):
    return {
        "member": "child",
        "member_revision": 1,
        "title": "School homework assignment",
        "due_at": (now + timedelta(hours=3)).isoformat(),
        "checklist": ["Complete exercises"],
        "reminder_minutes": 15,
        "grace_minutes": 0,
        **changes,
    }


def asset_payload(engine, **changes):
    return {
        "name": "Synthetic appliance",
        "category": "Appliance",
        "location": "Utility room",
        "responsible_member": "child",
        "responsible_member_revision": engine.snapshot()["members"]["child"]["revision"],
        "warranty": {"expires_on": None, "vendor": CANARY, "reference": "LOCAL-REF-1"},
        "consumables": [],
        "note": CANARY,
        **changes,
    }


def fault_payload(engine, asset_record, **changes):
    return {
        "asset_id": asset_record["id"],
        "asset_revision": asset_record["revision"],
        "reporter_member_revision": engine.snapshot()["members"]["child"]["revision"],
        "summary": "Reported leak",
        "details": CANARY,
        "attachment_ids": [],
        **changes,
    }


# ===========================================================================
# Claim (a): School homework generic revise assignee stale source investigation
# ===========================================================================


@pytest.mark.asyncio
async def test_generic_tasks_revise_on_school_homework_is_forbidden(managed_engine, now):
    """Generic task revision cannot bypass the school source binding."""
    e = managed_engine
    hw = await e.execute(
        "parent", "school.homework_create", homework_payload(now), "hw-create", now
    )
    task_id = hw["id"]
    task = e.snapshot()["tasks"][task_id]

    assert school_work.is_homework_task(task)
    assert school_work.current_homework(e.snapshot(), task)
    assert task["source"]["member"] == "child"
    assert task["source"]["member_revision"] == 1
    assert task["assignee"] == "child"

    before_state = e.snapshot()

    # Attempt 1: Parent attempts generic tasks.revise with assignee="sibling"
    revise_payload = {
        "id": task_id,
        "revision": task["revision"],
        "assignee": "sibling",
        "title": "Attempted bypass title",
    }
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute("parent", "tasks.revise", revise_payload, "generic-revise-attempt", now)

    # Attempt 2: Child attempts generic tasks.revise
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute("child", "tasks.revise", revise_payload, "child-generic-revise", now)

    # Attempt 3: Batch execution of generic tasks.revise
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "parent",
            "batch",
            {"commands": [{"action": "tasks.revise", "payload": revise_payload}]},
            "batch-revise-attempt",
            now,
        )

    # State must be completely untouched
    assert e.snapshot() == before_state
    task_after = e.snapshot()["tasks"][task_id]
    assert school_work.current_homework(e.snapshot(), task_after)
    assert task_after["source"]["member"] == "child"
    assert task_after["assignee"] == "child"


@pytest.mark.asyncio
async def test_school_homework_revise_rejects_assignee_change_and_preserves_binding(
    managed_engine, now
):
    """The school revision contract preserves the assigned child."""
    e = managed_engine
    hw = await e.execute(
        "parent", "school.homework_create", homework_payload(now), "hw-create-2", now
    )
    task_id = hw["id"]
    task = e.snapshot()["tasks"][task_id]

    # Attempting to supply 'assignee' or 'member' to school.homework_revise fails field validation
    invalid_revise = {
        "id": task_id,
        "revision": task["revision"],
        "member_revision": 1,
        "title": "Updated homework title",
        "due_at": (now + timedelta(hours=4)).isoformat(),
        "reminder_minutes": 15,
        "grace_minutes": 0,
        "assignee": "sibling",
    }
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute(
            "parent", "school.homework_revise", invalid_revise, "hw-revise-invalid", now
        )

    # Legitimate revision through school.homework_revise updates member_revision and title
    valid_revise = {
        "id": task_id,
        "revision": task["revision"],
        "member_revision": 1,
        "title": "Properly updated title",
        "due_at": (now + timedelta(hours=4)).isoformat(),
        "reminder_minutes": 15,
        "grace_minutes": 0,
    }
    receipt = await e.execute(
        "parent", "school.homework_revise", valid_revise, "hw-revise-valid", now
    )
    assert receipt["id"] == task_id

    updated_task = e.snapshot()["tasks"][task_id]
    assert updated_task["title"] == "Properly updated title"
    assert updated_task["source"]["member"] == "child"
    assert updated_task["source"]["member_revision"] == 1
    assert school_work.current_homework(e.snapshot(), updated_task)


# ===========================================================================
# Claim (b): Replay authorization and audit scope investigation
# ===========================================================================


@pytest.mark.asyncio
async def test_reassigned_private_task_receipt_replay_is_forbidden(managed_engine, now):
    """Verify task_access.authorize_replay blocks receipt replay after private task reassignment."""
    e = managed_engine
    asset = await e.execute("parent", "maintenance.asset_save", asset_payload(e), "asset-1", now)
    fault = await e.execute(
        "child", "maintenance.fault_report", fault_payload(e, asset), "fault-1", now
    )
    task_id = fault["task_id"]

    initial_task = e.snapshot()["tasks"][task_id]
    assert task_access.private_task(initial_task)
    assert initial_task["assignee"] == "child"

    # Child accepts the assigned maintenance task
    accept_receipt = await e.execute(
        "child",
        "tasks.accept",
        {"id": task_id, "revision": initial_task["revision"]},
        "child-accept-op",
        now,
    )
    assert accept_receipt["delivery_scope"] == "private"
    assert accept_receipt["status"] == "accepted"

    # Parent reassigns the private maintenance task to sibling
    current_rev = e.snapshot()["tasks"][task_id]["revision"]
    await e.execute(
        "parent",
        "tasks.revise",
        {"id": task_id, "revision": current_rev, "assignee": "sibling"},
        "parent-reassign-op",
        now,
    )

    reassigned_task = e.snapshot()["tasks"][task_id]
    assert reassigned_task["assignee"] == "sibling"
    assert not task_access.may_view(e.snapshot(), e.snapshot()["members"]["child"], reassigned_task)

    # Former assignee (child) attempts to replay the accept receipt: must be forbidden
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "child",
            "tasks.accept",
            {"id": task_id, "revision": initial_task["revision"]},
            "child-accept-op",
            now,
        )


@pytest.mark.asyncio
async def test_reassigned_photo_task_receipt_replay_is_forbidden(managed_engine, now):
    """Compact photo receipts still require the current assignment."""
    e = managed_engine
    photo_task = await e.execute(
        "parent",
        "tasks.create",
        {
            "title": "Photo evidence task",
            "assignee": "child",
            "report_type": "photo",
        },
        "photo-create-op",
        now,
    )
    task_id = photo_task["id"]

    # Child accepts the photo task; compact receipt {id, revision, status} without delivery_scope
    accept_receipt = await e.execute(
        "child",
        "tasks.accept",
        {"id": task_id, "revision": photo_task["revision"]},
        "child-photo-accept-op",
        now,
    )
    assert set(accept_receipt.keys()) == {"id", "revision", "status"}

    # Parent reassigns task to sibling
    current_rev = e.snapshot()["tasks"][task_id]["revision"]
    await e.execute(
        "parent",
        "tasks.revise",
        {"id": task_id, "revision": current_rev, "assignee": "sibling"},
        "reassign-photo-op",
        now,
    )

    # Former assignee (child) attempts replay: blocked by photo current-task guard
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "child",
            "tasks.accept",
            {"id": task_id, "revision": photo_task["revision"]},
            "child-photo-accept-op",
            now,
        )


@pytest.mark.asyncio
async def test_replay_fingerprint_and_cross_actor_isolation(managed_engine, now):
    """Verify replay cache enforces actor binding via fingerprint, preventing cross-actor replay."""
    e = managed_engine
    task = await e.execute(
        "parent",
        "tasks.create",
        {"title": "Trash duty", "assignee": "child"},
        "create-task-op",
        now,
    )
    task_id = task["id"]

    await e.execute(
        "child",
        "tasks.accept",
        {"id": task_id, "revision": task["revision"]},
        "child-accept-unique",
        now,
    )

    # Sibling attempts to replay child's operation ID: fails with idempotency_conflict
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await e.execute(
            "sibling",
            "tasks.accept",
            {"id": task_id, "revision": task["revision"]},
            "child-accept-unique",
            now,
        )


@pytest.mark.asyncio
async def test_audit_log_visibility_is_parent_only_and_personal_filtered(managed_engine, now):
    """Only parents see audits, excluding another member's personal tasks."""
    e = managed_engine

    # 1. Child executes personal task creation
    personal_task = await e.execute(
        "child",
        "tasks.create",
        {
            "title": "Private child reminder",
            "assignee": "child",
            "personal": True,
            "due_at": (now + timedelta(hours=1)).isoformat(),
        },
        "child-personal-create",
        now,
    )

    # 2. Parent executes household maintenance asset creation
    await e.execute(
        "parent", "maintenance.asset_save", asset_payload(e), "parent-asset-create", now
    )

    # 3. Verify child and guest view projections contain NO audit key
    child_view = e.view("child", now=now)
    guest_view = e.view("guest", now=now)
    assert "audit" not in child_view
    assert "audit" not in guest_view

    # 4. Verify parent view contains audit log, but child personal task is filtered out
    parent_view = e.view("parent", now=now)
    assert "audit" in parent_view
    audit_actions = [entry["action"] for entry in parent_view["audit"]]
    assert "maintenance.asset_save" in audit_actions
    assert all(entry["result"].get("id") != personal_task["id"] for entry in parent_view["audit"])
