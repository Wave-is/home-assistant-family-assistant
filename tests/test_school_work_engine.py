"""Independent transaction, privacy and lifecycle acceptance for school handoffs."""

import asyncio
import json
from datetime import timedelta

import pytest

from custom_components.family_assistant.assistant.plans import projection
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.messages import targets
from custom_components.family_assistant.telegram.router import route


@pytest.fixture
def school_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"] = sorted(
        set(state["settings"]["modules"]) | {"school", "routines"}
    )
    state["settings"]["timezone"] = "UTC"
    state["telegram"]["group_id"] = -10001
    for index, member in enumerate(state["members"].values(), 101):
        member["telegram_id"] = index
    return Engine(state, store.save)


def homework(now, **changes):
    return {
        "member": "child",
        "member_revision": 1,
        "title": "PRIVATE-HOMEWORK-CANARY",
        "due_at": (now + timedelta(hours=2)).isoformat(),
        "checklist": ["Read chapter"],
        "reminder_minutes": 15,
        "grace_minutes": 0,
        **changes,
    }


async def source(engine, now):
    routine = await engine.execute(
        "parent",
        "routines.save",
        {
            "title": "PRIVATE-BACKPACK-CANARY",
            "assignees": ["child"],
            "steps": [{"title": "PRIVATE-MATERIAL-CANARY"}],
        },
        "create-routine",
        now,
    )
    table = await engine.execute(
        "parent",
        "school.timetable_save",
        {
            "member": "child",
            "member_revision": 1,
            "title": "Reviewed school days",
            "valid_from": now.date().isoformat(),
            "valid_until": None,
            "exceptions": [],
            "backpack_routine": {"id": routine["id"], "revision": routine["revision"]},
            "lessons": [
                {
                    "weekday": day,
                    "start": "09:00",
                    "end": "09:45",
                    "subject": "Science",
                    "room": "",
                    "materials": ["PRIVATE-MATERIAL-CANARY"],
                }
                for day in range(7)
            ],
        },
        "create-timetable",
        now,
    )
    return {
        "timetable_id": table["id"],
        "timetable_revision": table["revision"],
        "member": "child",
        "member_revision": 1,
        "date": now.date().isoformat(),
        "routine_id": routine["id"],
        "routine_revision": routine["revision"],
    }


async def module_change(engine, now, remove):
    settings = engine.snapshot()["settings"]
    return await engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": [m for m in settings["modules"] if m != remove],
        },
        f"disable-{remove}",
        now,
    )


@pytest.mark.asyncio
async def test_homework_receipt_concurrent_replay_private_model_and_group(
    school_engine, store, now
):
    e = school_engine
    payload = homework(now)
    results = await asyncio.gather(
        *[e.execute("child", "school.homework_create", payload, "same", now) for _ in range(5)]
    )
    assert all(r == results[0] for r in results)
    assert len(e.snapshot()["tasks"]) == 1 and store.calls == 1
    assert set(results[0]) == {"id", "revision", "status"}
    assert "PRIVATE-HOMEWORK" not in json.dumps(e.snapshot()["processed"])
    child = e.view("child")["school"]["homework"][0]
    assert child["managed_by"] == "school" and child["delivery_scope"] == "private"
    assert "source" not in child
    assert e.view("sibling")["school"]["homework"] == []
    assert "PRIVATE-HOMEWORK" not in json.dumps(projection(e.view("parent")))
    assert "PRIVATE-HOMEWORK" not in await route(e, "parent", "/tasks", "group", now)
    notice = next(iter(e.snapshot()["outbox"].values()))
    resolved = targets(notice, e.snapshot())
    assert resolved and all(t["id"] != -10001 for t in resolved)
    restarted = Engine(store.value, store.save)
    assert (
        await restarted.execute("child", "school.homework_create", payload, "same", now)
        == results[0]
    )


@pytest.mark.asyncio
async def test_homework_store_and_batch_faults_are_atomic(school_engine, store, now):
    e = school_engine
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("child", "school.homework_create", homework(now), "fault", now)
    assert e.snapshot() == before
    store.fail = False
    with pytest.raises(DomainError):
        await e.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "school.homework_create", "payload": homework(now)},
                    {"action": "school.homework_create", "payload": homework(now, member="guest")},
                ]
            },
            "batch-fault",
            now,
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_homework_identity_refresh_is_atomic_private_and_durable(school_engine, store, now):
    e = school_engine
    created = await e.execute("child", "school.homework_create", homework(now), "create", now)
    task_id = created["id"]
    for actor, action, extra in (
        ("child", "tasks.check", {"checklist_index": 0, "done": True}),
        ("child", "tasks.start", {}),
        ("child", "tasks.submit", {"report": "FORMER-CHILD-REPORT"}),
        ("parent", "tasks.request_changes", {"note": "FORMER-REVIEW-NOTE"}),
    ):
        task = e.snapshot()["tasks"][task_id]
        await e.execute(
            actor, action, {"id": task_id, "revision": task["revision"], **extra}, action, now
        )
    await e.execute(
        "owner",
        "members.save",
        {"id": "child", "revision": 1, "name": "Reviewed child profile", "role": "child"},
        "new-epoch",
        now,
    )
    assert e.view("child")["school"]["homework"] == []
    task = e.snapshot()["tasks"][task_id]
    payload = {
        "id": task_id,
        "revision": task["revision"],
        "member_revision": 2,
        "title": task["title"],
        "due_at": task["due_at"],
        "reminder_minutes": 15,
        "grace_minutes": 0,
    }
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("parent", "school.homework_revise", payload, "rebind", now)
    assert e.snapshot() == before
    store.fail = False
    with pytest.raises(DomainError):
        await e.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "school.homework_revise", "payload": payload},
                    {"action": "school.homework_create", "payload": homework(now, member="guest")},
                ]
            },
            "failed-rebind-batch",
            now,
        )
    assert e.snapshot() == before
    receipt = await e.execute("parent", "school.homework_revise", payload, "rebind", now)
    assert receipt["status"] == "assigned"
    child_row = e.view("child")["school"]["homework"][0]
    assert child_row["report"] is None and not child_row["checklist"][0]["done"]
    assert "FORMER-" not in json.dumps(e.view("child"))
    parent_row = e.view("parent")["school"]["homework"][0]
    assert parent_row["previous_reports"][0]["report"] == "FORMER-CHILD-REPORT"
    restarted = Engine(store.value, store.save)
    assert (
        await restarted.execute("parent", "school.homework_revise", payload, "rebind", now)
        == receipt
    )
    assert restarted.view("child")["school"]["homework"] == [child_row]


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["parent", "child"])
async def test_generic_homework_edit_cannot_bypass_school_guard(school_engine, now, actor):
    e = school_engine
    task = await e.execute("child", "school.homework_create", homework(now), "create", now)
    before = e.snapshot()
    revise = {"id": task["id"], "revision": task["revision"], "title": "Bypass"}
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(actor, "tasks.revise", revise, "direct", now)
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            actor,
            "batch",
            {"commands": [{"action": "tasks.revise", "payload": revise}]},
            "batch",
            now,
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_materialized_homework_survives_archived_school_but_tasks_and_identity_revoke(
    school_engine, now
):
    e = school_engine
    bound = await source(e, now)
    payload = homework(
        now,
        lesson={k: bound[k] for k in ("timetable_id", "timetable_revision", "date")}
        | {"lesson_index": now.weekday()},
    )
    task = await e.execute("parent", "school.homework_create", payload, "homework", now)
    await e.execute(
        "parent",
        "school.timetable_archive",
        {
            "id": bound["timetable_id"],
            "revision": bound["timetable_revision"],
            "reason": "New term",
        },
        "archive",
        now,
    )
    assert len(e.view("child")["school"]["homework"]) == 1
    await module_change(e, now, "school")
    assert "school" not in e.view("child")
    started = await e.execute(
        "child", "tasks.start", {"id": task["id"], "revision": task["revision"]}, "start", now
    )
    assert started["status"] == "in_progress" and "source" not in started
    with pytest.raises(DomainError, match="module_disabled"):
        await e.execute("parent", "school.homework_create", payload, "homework", now)
    await module_change(e, now, "tasks")
    with pytest.raises(DomainError, match="module_disabled"):
        await e.execute(
            "child", "tasks.start", {"id": task["id"], "revision": task["revision"]}, "start", now
        )


@pytest.mark.asyncio
async def test_backpack_store_replay_date_dedup_and_nonce_isolation(school_engine, store, now):
    e = school_engine
    payload = await source(e, now)
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("child", "school.backpack_start", payload, "start", now)
    assert e.snapshot() == before
    store.fail = False
    results = await asyncio.gather(
        *[e.execute("child", "school.backpack_start", payload, "start", now) for _ in range(4)]
    )
    result = results[0]
    assert all(r == result for r in results)
    assert set(result) == {"id", "revision", "status", "run_id"}
    state = e.snapshot()
    run = state["routine_runs"][result["run_id"]]
    nonce = run["steps"][0]["nonce"]
    assert nonce and nonce not in json.dumps(state["audit"][-1])
    assert nonce not in json.dumps(state["school"])
    assert len(state["school"]["preparations"]) == 1 and len(state["routine_runs"]) == 1
    assert state["tasks"] == before["tasks"]
    assert len(e.view("child")["school"]["preparations"]) == 1
    assert e.view("sibling")["school"]["preparations"] == []
    restarted = Engine(store.value, store.save)
    assert (
        await restarted.execute("child", "school.backpack_start", payload, "start", now) == result
    )
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute("child", "school.backpack_start", payload, "second-operation", now)
    completed = await e.execute(
        "child",
        "routines.confirm",
        {"id": run["id"], "revision": run["revision"], "step": 0, "nonce": nonce},
        "confirm",
        now,
    )
    assert completed["status"] == "completed"
    assert e.view("child")["school"]["preparations"][0]["run_status"] == "completed"
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute("child", "school.backpack_start", payload, "after-complete", now)


@pytest.mark.asyncio
async def test_backpack_unrelated_active_run_not_adopted_and_batch_rolls_back(school_engine, now):
    e = school_engine
    payload = await source(e, now)
    before = e.snapshot()
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute(
            "child",
            "batch",
            {
                "commands": [
                    {"action": "school.backpack_start", "payload": payload},
                    {"action": "school.backpack_start", "payload": payload},
                ]
            },
            "batch",
            now,
        )
    assert e.snapshot() == before
    await e.execute(
        "child",
        "routines.start",
        {"id": payload["routine_id"], "revision": payload["routine_revision"], "member": "child"},
        "manual-start",
        now,
    )
    before = e.snapshot()
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute("child", "school.backpack_start", payload, "school-start", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_backpack_module_and_member_revoke_exact_receipt(school_engine, now):
    e = school_engine
    payload = await source(e, now)
    await e.execute("child", "school.backpack_start", payload, "start", now)
    member = e.snapshot()["members"]["child"]
    await e.execute(
        "owner",
        "members.save",
        {"id": "child", "revision": member["revision"], "name": "New child label", "role": "child"},
        "member",
        now,
    )
    assert e.view("child")["school"]["preparations"] == []
    with pytest.raises(DomainError, match="conflict"):
        await e.execute("child", "school.backpack_start", payload, "start", now)
    await module_change(e, now, "routines")
    with pytest.raises(DomainError, match="module_disabled"):
        await e.execute("child", "school.backpack_start", payload, "start", now)
