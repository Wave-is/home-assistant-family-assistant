"""Independent maintenance acceptance through transactions and real delivery gates."""

import asyncio
import json
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.assistant.plans import projection
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.task_delivery import current_task_event
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import Notifications
from custom_components.family_assistant.telegram.messages import targets
from custom_components.family_assistant.telegram.router import route

CANARY = "MAINTENANCE-PRIVATE-NOTE-b381"


@pytest.fixture
def maintenance_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"] += ["maintenance", "pantry"]
    state["telegram"]["group_id"] = -10001
    for index, member in enumerate(state["members"].values(), 101):
        member["telegram_id"] = index
    return Engine(state, store.save)


def asset_payload(engine, **changes):
    return {
        "name": "Reviewed filter",
        "category": "Appliance",
        "location": "Synthetic utility room",
        "responsible_member": "child",
        "responsible_member_revision": engine.snapshot()["members"]["child"]["revision"],
        "warranty": {"expires_on": None, "vendor": CANARY, "reference": "LOCAL-1"},
        "consumables": [],
        "note": CANARY,
        **changes,
    }


async def asset(engine, now, **changes):
    return await engine.execute(
        "parent", "maintenance.asset_save", asset_payload(engine, **changes), "asset", now
    )


def fault_payload(engine, record, **changes):
    return {
        "asset_id": record["id"],
        "asset_revision": record["revision"],
        "reporter_member_revision": engine.snapshot()["members"]["child"]["revision"],
        "summary": "Private observed fault",
        "details": CANARY,
        "attachment_ids": [],
        **changes,
    }


async def fault(engine, now, record, *, operation="fault"):
    return await engine.execute(
        "child", "maintenance.fault_report", fault_payload(engine, record), operation, now
    )


def service_payload(record, now):
    return {
        "asset_id": record["id"],
        "asset_revision": record["revision"],
        "title": "Private reviewed service",
        "assignees": [{"id": "child", "revision": 1}],
        "rotation": False,
        "rule": {
            "frequency": "daily",
            "start_date": now.date().isoformat(),
            "time": "09:00",
            "timezone": "UTC",
        },
        "due_time": "10:00",
        "checklist": ["Record observations"],
        "enabled": True,
        "reminder_minutes": 15,
        "grace_minutes": 0,
    }


async def members_change(engine, now, member="child", **changes):
    previous = engine.snapshot()["members"][member]
    return await engine.execute(
        "owner",
        "members.save",
        {
            "id": member,
            "revision": previous["revision"],
            "name": previous["name"],
            "role": previous["role"],
            **changes,
        },
        f"member-{member}-{previous['revision']}",
        now,
    )


async def modules(engine, now, values):
    settings = engine.snapshot()["settings"]
    return await engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": values,
        },
        f"modules-{engine.snapshot()['revision']}",
        now,
    )


@pytest.mark.asyncio
async def test_fault_private_projection_opaque_replay_and_atomic_store(
    maintenance_engine, store, now
):
    e = maintenance_engine
    record = await asset(e, now)
    assert e.view("sibling")["maintenance"]["assets"] == []
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await fault(e, now, record)
    assert e.snapshot() == before
    store.fail = False
    result = await fault(e, now, record)
    assert set(result) == {"id", "revision", "status", "task_id"}
    reloaded = Engine(store.value, store.save)
    assert await fault(reloaded, now, record) == result
    state = e.snapshot()
    task = state["tasks"][result["task_id"]]
    assert task["source"]["kind"] == "maintenance_fault"
    assert task["assignee_revision"] == 1 and task["delivery_scope"] == "private"
    assert task["deadline_policy"]["penalty"] == 0
    assert CANARY not in json.dumps(task)
    assert len(state["tasks"]) == 1
    assert CANARY not in json.dumps(state["processed"])
    assert e.view("sibling")["tasks"] == []
    assert "source" not in e.view("child")["tasks"][0]
    assert task["title"] not in json.dumps(projection(e.view("parent")))
    assert task["title"] not in await route(e, "parent", "/tasks", "group-list", now)
    assert task["title"] in await route(e, "parent", "/tasks", "dm-list", now, private=True)
    event = next(iter(state["outbox"].values()))
    assert current_task_event(state, event)
    assert all(t["id"] != -10001 for t in targets(event, state))


@pytest.mark.asyncio
async def test_private_task_first_replay_and_batch_receipts_redact_source(maintenance_engine, now):
    e = maintenance_engine
    created = await fault(e, now, await asset(e, now))
    task_id = created["task_id"]
    payload = {"id": task_id, "revision": 1}
    first = await e.execute("child", "tasks.start", payload, "child-start", now)
    assert first["delivery_scope"] == "private" and "source" not in first
    assert await e.execute("child", "tasks.start", payload, "child-start", now) == first
    batch_payload = {
        "commands": [
            {
                "action": "tasks.submit",
                "payload": {
                    "id": task_id,
                    "revision": first["revision"],
                    "report": "Checked privately",
                },
            }
        ]
    }
    batch = await e.execute("child", "batch", batch_payload, "child-batch", now)
    assert "source" not in json.dumps(batch)
    assert "private" in json.dumps(batch)
    assert await e.execute("child", "batch", batch_payload, "child-batch", now) == batch
    stored = e.snapshot()["tasks"][task_id]
    assert stored["source"]["kind"] == "maintenance_fault"
    parent = await e.execute(
        "parent",
        "tasks.complete",
        {"id": task_id, "revision": stored["revision"]},
        "parent-complete",
        now,
    )
    assert parent["source"] == stored["source"]


@pytest.mark.asyncio
async def test_reassigned_private_task_keeps_former_reports_parent_only(maintenance_engine, now):
    e = maintenance_engine
    made = await fault(e, now, await asset(e, now))
    task_id = made["task_id"]
    report = await e.execute(
        "child",
        "tasks.submit",
        {"id": task_id, "revision": 1, "report": "FORMER-REPORT-PRIVATE"},
        "old-report",
        now,
    )
    review = await e.execute(
        "parent",
        "tasks.request_changes",
        {"id": task_id, "revision": report["revision"], "note": "FORMER-REVIEW-PRIVATE"},
        "old-review",
        now,
    )
    reassigned = await e.execute(
        "parent",
        "tasks.revise",
        {"id": task_id, "revision": review["revision"], "assignee": "sibling"},
        "transfer",
        now,
    )
    assert reassigned["previous_reports"][0]["report"] == "FORMER-REPORT-PRIVATE"
    assert e.view("parent")["tasks"][0]["previous_reports"]
    payload = {"id": task_id, "revision": reassigned["revision"]}
    first = await e.execute("sibling", "tasks.start", payload, "new-start", now)
    replay = await e.execute("sibling", "tasks.start", payload, "new-start", now)
    for result in [first, replay, e.view("sibling")["tasks"][0]]:
        assert "previous_reports" not in result
        assert "FORMER-" not in json.dumps(result)


@pytest.mark.asyncio
async def test_model_preview_cannot_exfiltrate_private_task_title_by_guessed_id(
    maintenance_engine, now
):
    e = maintenance_engine
    created = await fault(e, now, await asset(e, now))
    before = e.snapshot()
    model = Assistant(e, None)
    with pytest.raises(DomainError, match="not_found"):
        await model._propose(
            "parent",
            "complete the referenced task",
            "private-model-op",
            "Pprivate",
            {
                "kind": "commands",
                "commands": [
                    {
                        "action": "tasks.complete",
                        "payload": {"id": created["task_id"]},
                    }
                ],
            },
            e.view("parent"),
            now,
            {},
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_reportable_is_explicit_and_fault_epoch_cannot_rebind(maintenance_engine, now):
    e = maintenance_engine
    record = await asset(e, now, responsible_member="adult", responsible_member_revision=1)
    payload = fault_payload(e, record)
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute("child", "maintenance.fault_report", payload, "deny", now)
    updated = await e.execute(
        "parent",
        "maintenance.asset_save",
        asset_payload(
            e,
            id=record["id"],
            revision=record["revision"],
            reportable=True,
            responsible_member="adult",
            responsible_member_revision=1,
        ),
        "reportable",
        now,
    )
    result = await fault(e, now, updated)
    assert len(e.view("child")["maintenance"]["faults"]) == 1
    await members_change(e, now, name="Updated child")
    assert e.view("child")["maintenance"]["faults"] == []
    assert e.view("child")["maintenance"]["assets"][0]["can_report"]
    assert e.snapshot()["tasks"][result["task_id"]]["assignee"] == "adult"


@pytest.mark.asyncio
async def test_private_task_epoch_and_replay_revoke_then_parent_reassigns(maintenance_engine, now):
    e = maintenance_engine
    result = await fault(e, now, await asset(e, now))
    task = e.snapshot()["tasks"][result["task_id"]]
    payload = {"id": task["id"], "revision": task["revision"]}
    started = await e.execute("child", "tasks.start", payload, "start-private", now)
    await members_change(e, now, name="New identity binding")
    assert e.view("child")["tasks"] == []
    assert e.view("child")["maintenance"]["faults"] == []
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute("child", "tasks.start", payload, "start-private", now)
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "child",
            "tasks.submit",
            {
                "id": task["id"],
                "revision": started["revision"],
                "report": "old scope",
            },
            "submit-stale",
            now,
        )
    current = await e.execute(
        "parent",
        "tasks.revise",
        {
            "id": task["id"],
            "revision": started["revision"],
            "assignee": "sibling",
        },
        "reassign-private",
        now,
    )
    assert e.view("child")["tasks"] == []
    assert len(e.view("sibling")["tasks"]) == 1
    assert current["source"] == task["source"]


@pytest.mark.asyncio
async def test_service_uses_existing_tick_and_private_tasks_then_retirement_stops_generation(
    maintenance_engine, now
):
    e = maintenance_engine
    record = await asset(e, now)
    payload = service_payload(record, now)
    series = await e.execute("parent", "maintenance.service_save", payload, "service", now)
    assert e.view("parent")["task_series"] == []
    assert e.view("child")["task_series"] == []
    for action, body in [
        (
            "tasks.series_enable",
            {"id": series["id"], "revision": series["revision"], "enabled": False},
        ),
        (
            "tasks.series_save",
            {"id": series["id"], "revision": series["revision"], "title": "Bypass"},
        ),
    ]:
        with pytest.raises(DomainError, match="forbidden"):
            await e.execute("parent", action, body, action, now)
    tick = now.replace(hour=9)
    await e.tick(tick)
    state = e.snapshot()
    assert len(state["tasks"]) == 1
    task = next(iter(state["tasks"].values()))
    assert task["source"] == {
        "kind": "maintenance_service",
        "asset_id": record["id"],
        "asset_revision": 1,
        "series_id": series["id"],
        "series_revision": 1,
    }
    assert task["delivery_scope"] == "private"
    assert await e.tick(tick) is False
    await e.execute(
        "parent",
        "maintenance.asset_retire",
        {
            "id": record["id"],
            "revision": 1,
            "reason": "Retired equipment",
        },
        "retire",
        tick,
    )
    await e.tick(tick + timedelta(days=1))
    assert len(e.snapshot()["tasks"]) == 1
    overdue = next(x for x in e.snapshot()["outbox"].values() if x["key"] == "task_overdue")
    assert overdue["recipient"] == "parents"
    assert all(t["id"] != -10001 for t in targets(overdue, e.snapshot()))
    task = e.snapshot()["tasks"][task["id"]]
    finished = await e.execute(
        "parent",
        "tasks.complete",
        {
            "id": task["id"],
            "revision": task["revision"],
        },
        "finish-materialized",
        tick + timedelta(days=1),
    )
    assert finished["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled", ["maintenance", "tasks"])
async def test_dependent_module_replay_and_generation_gate(maintenance_engine, now, disabled):
    e = maintenance_engine
    record = await asset(e, now)
    await fault(e, now, record)
    series = await e.execute(
        "parent", "maintenance.service_save", service_payload(record, now), "service", now
    )
    await modules(e, now, [m for m in e.snapshot()["settings"]["modules"] if m != disabled])
    with pytest.raises(DomainError, match="module_disabled"):
        await fault(e, now, record)
    await e.tick(now.replace(hour=9))
    assert len(e.snapshot()["tasks"]) == 1
    assert not e.snapshot()["task_series"][series["id"]]["occurrences"]


@pytest.mark.asyncio
async def test_batch_rollback_does_not_leave_created_asset_task_or_notice(maintenance_engine, now):
    e = maintenance_engine
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "maintenance.asset_save", "payload": asset_payload(e)},
                    {"action": "maintenance.fault_report", "payload": {}},
                ]
            },
            "bad-batch",
            now,
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_announced_closure_survives_another_overdue_generation(
    maintenance_engine, store, now
):
    e = maintenance_engine
    result = await fault(e, now, await asset(e, now))
    task = e.snapshot()["tasks"][result["task_id"]]
    task = await e.execute(
        "parent",
        "tasks.revise",
        {
            "id": task["id"],
            "revision": task["revision"],
            "due_at": (now + timedelta(minutes=5)).isoformat(),
            "grace_minutes": 0,
        },
        "deadline",
        now,
    )
    await e.tick(now + timedelta(minutes=6))
    state = e.snapshot()
    opened = next(x for x in state["outbox"].values() if x["key"] == "task_overdue")
    opened["deliveries"] = {"test": {"state": "sent"}}
    opened["state"] = "sent"
    e = Engine(state, store.save)
    await e.execute(
        "parent",
        "tasks.revise",
        {
            "id": task["id"],
            "revision": task["revision"],
            "due_at": (now + timedelta(minutes=10)).isoformat(),
        },
        "later-deadline",
        now + timedelta(minutes=7),
    )
    closure = next(x for x in e.snapshot()["outbox"].values() if x["key"] == "task_incident_closed")
    assert closure["data"]["original_event_id"] == opened["id"]
    await e.tick(now + timedelta(minutes=11))
    assert e.snapshot()["incidents"][f"task:{task['id']}"]["generation"] == 2
    assert current_task_event(e.snapshot(), closure)
    assert all(t["id"] != -10001 for t in targets(closure, e.snapshot()))


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["module", "reassign", "member", "complete"])
async def test_task_dispatch_rechecks_after_durable_claim(maintenance_engine, now, change):
    e = maintenance_engine
    result = await fault(e, now, await asset(e, now))
    task = e.snapshot()["tasks"][result["task_id"]]
    entered, release = asyncio.Event(), asyncio.Event()
    original = e.system_update

    async def gated(kind, moment, callback):
        value = await original(kind, moment, callback)
        if kind == "outbox_claim" and value is not None:
            entered.set()
            await release.wait()
        return value

    e.system_update = gated
    sent = []

    async def send(event, target):
        sent.append((deepcopy(event), deepcopy(target)))
        return "unexpected"

    running = asyncio.create_task(Notifications(e, targets, send).run(now))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if change == "module":
            await modules(e, now, [m for m in e.snapshot()["settings"]["modules"] if m != "tasks"])
        elif change == "member":
            await members_change(e, now, name="Another binding")
        else:
            action = "tasks.revise" if change == "reassign" else "tasks.complete"
            await e.execute(
                "parent",
                action,
                {
                    "id": task["id"],
                    "revision": task["revision"],
                    **({"assignee": "sibling"} if change == "reassign" else {}),
                },
                "change-claimed-task",
                now,
            )
    finally:
        release.set()
    await asyncio.wait_for(running, 2)
    # A reassignment may legitimately send the newly created sibling notice,
    # never the original claimed child's notice.
    original_id = next(iter(e.snapshot()["outbox"]))
    assert all(event["id"] != original_id for event, _ in sent)
    assert e.snapshot()["outbox"][original_id]["state"] == "superseded"
