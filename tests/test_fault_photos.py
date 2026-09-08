"""Fault-image scope through real Engine transactions; finalizer is a trusted fixture."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_maintenance_engine import asset_payload, fault_payload

from custom_components.family_assistant.assistant.plans import projection
from custom_components.family_assistant.domain import fault_photos, media
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def setup(engine, store, now, *, reporter="child"):
    state = engine.snapshot()
    state["settings"]["modules"].append("maintenance")
    e = Engine(state, store.save)
    asset = await e.execute(
        "parent", "maintenance.asset_save", asset_payload(e, reportable=True), "asset", now
    )
    fault = await e.execute(
        reporter, "maintenance.fault_report", fault_payload(e, asset), "fault", now
    )
    return e, fault


def reserve_payload(e, fault, actor="child"):
    return {
        "purpose": "maintenance_fault",
        "fault_id": fault["id"],
        "fault_revision": fault["revision"],
        "uploader_revision": e.snapshot()["members"][actor]["revision"],
    }


async def upload(e, fault, now, actor="child", operation="upload"):
    reserved = await e.execute(
        actor, "media.reserve", reserve_payload(e, fault, actor), operation, now
    )
    return await e.system_update(
        f"{operation}-verified",
        now,
        lambda ctx: media.finalize(
            ctx,
            actor,
            reserved["id"],
            reserved["revision"],
            "image/png",
            100,
            "a" * 64,
        ),
    )


def attach_payload(e, fault, uploaded, actor="child"):
    return {
        "id": fault["id"],
        "revision": fault["revision"],
        "actor_member_revision": e.snapshot()["members"][actor]["revision"],
        "media": {"id": uploaded["id"], "revision": uploaded["revision"]},
    }


def metadata(e, now, media_id, actor):
    state = e.snapshot()
    return media.read_metadata(state, state["members"][actor], media_id, now)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "parent", "child", "sibling"])
async def test_scoped_reporter_assignee_parent_image_is_not_a_completion_report(
    engine, store, now, actor
):
    e, fault = await setup(engine, store, now, reporter="sibling")
    before = e.snapshot()
    assert e.view(actor, now=now)["maintenance"]["faults"][0]["can_upload_photo"] is True
    uploaded = await upload(e, fault, now, actor)
    # Available bytes remain private to their uploader, even from other parents.
    for viewer in ("owner", "parent", "child", "sibling", "adult", "guest"):
        if viewer == actor:
            assert metadata(e, now, uploaded["id"], viewer)["status"] == "available"
        else:
            with pytest.raises(DomainError):
                metadata(e, now, uploaded["id"], viewer)
    payload = attach_payload(e, fault, uploaded, actor)
    result = await e.execute(actor, "maintenance.fault_photo_attach", payload, "attach", now)
    assert result == {"id": fault["id"], "revision": 2, "status": "reported"}
    for viewer in ("owner", "parent", "child", "sibling"):
        attachment = metadata(e, now, uploaded["id"], viewer)
        assert attachment["purpose"] == "maintenance_fault" and attachment["status"] == "attached"
        row = e.view(viewer, now=now)["maintenance"]["faults"][0]
        assert row["can_upload_photo"] is False
        assert row["photo_attachment"] == attachment
        assert "blob_key" not in repr(row) and "sha256" not in repr(row)
        if viewer in {"child", "sibling"}:
            assert "photo_history" not in row
    for viewer in ("adult", "guest"):
        with pytest.raises(DomainError):
            metadata(e, now, uploaded["id"], viewer)
        if viewer == "guest":
            assert "maintenance" not in e.view(viewer, now=now)
        else:
            assert e.view(viewer, now=now)["maintenance"]["faults"] == []
    for bucket in ("tasks", "outbox", "court", "alarm_runs", "routine_runs"):
        assert e.snapshot()[bucket] == before[bucket]
    assert "maintenance" not in projection(e.view("parent", now=now))
    restored = Engine(deepcopy(store.value), store.save)
    state, writes = restored.snapshot(), store.calls
    assert (
        await restored.execute(actor, "maintenance.fault_photo_attach", payload, "attach", now)
        == result
    )
    assert restored.snapshot() == state and store.calls == writes


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["adult", "guest"])
async def test_reporting_permission_for_equipment_does_not_grant_another_fault_image(
    engine, store, now, actor
):
    e, fault = await setup(engine, store, now)
    before = e.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(actor, "media.reserve", reserve_payload(e, fault, actor), "denied", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_attach_atomic_store_failure_and_batch_rollback(engine, store, now):
    e, fault = await setup(engine, store, now)
    uploaded = await upload(e, fault, now)
    payload = attach_payload(e, fault, uploaded)
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("child", "maintenance.fault_photo_attach", payload, "attach", now)
    assert e.snapshot() == before
    store.fail = False
    with pytest.raises(DomainError):
        await e.execute(
            "child",
            "batch",
            {
                "commands": [
                    {"action": "maintenance.fault_photo_attach", "payload": payload},
                    {"action": "maintenance.asset_retire", "payload": {}},
                ]
            },
            "failed-batch",
            now,
        )
    assert e.snapshot() == before
    assert e.snapshot()["media"][uploaded["id"]]["status"] == "available"


@pytest.mark.asyncio
async def test_owner_purge_revokes_reads_keeps_fault_history_and_replays_after_collector(
    engine, store, now
):
    e, fault = await setup(engine, store, now)
    uploaded = await upload(e, fault, now)
    attached = await e.execute(
        "child", "maintenance.fault_photo_attach", attach_payload(e, fault, uploaded), "attach", now
    )
    purge = {
        **attach_payload(e, attached, {**uploaded, "revision": 3}, "owner"),
        "reason": "Private deletion reason",
    }
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("owner", "maintenance.fault_photo_purge", purge, "purge", now)
    assert e.snapshot() == before
    store.fail = False
    result = await e.execute("owner", "maintenance.fault_photo_purge", purge, "purge", now)
    assert result["revision"] == 3
    for viewer in ("owner", "parent", "child", "sibling"):
        with pytest.raises(DomainError):
            metadata(e, now, uploaded["id"], viewer)
    fault_row = e.snapshot()["maintenance"]["faults"][fault["id"]]
    assert fault_row["attachment_ids"] == [] and len(fault_row["photo_history"]) == 2
    assert fault_row["photo_history"][-1]["reason"] == "Private deletion reason"
    assert "Private deletion reason" not in repr(e.view("child", now=now)["maintenance"])
    assert e.snapshot()["tasks"] == before["tasks"] and e.snapshot()["outbox"] == before["outbox"]
    await e.system_update("collector", now, lambda ctx: media.finish_delete(ctx, uploaded["id"], 4))
    await e.system_update("reap", now + timedelta(days=2), media.reap_deleted)
    assert uploaded["id"] not in e.snapshot()["media"]
    assert await e.execute("owner", "maintenance.fault_photo_purge", purge, "purge", now) == result
    # Replacement after an explicit purge retains the earlier history.
    later = now + timedelta(days=2)
    replacement = await upload(e, result, later, operation="replacement")
    await e.execute(
        "child",
        "maintenance.fault_photo_attach",
        attach_payload(e, result, replacement),
        "reattach",
        later,
    )
    assert len(e.snapshot()["maintenance"]["faults"][fault["id"]]["photo_history"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["parent", "child", "sibling", "adult", "guest"])
async def test_nonowners_cannot_purge_an_attached_fault_photo(engine, store, now, actor):
    e, fault = await setup(engine, store, now, reporter="sibling")
    uploaded = await upload(e, fault, now)
    attached = await e.execute(
        "child", "maintenance.fault_photo_attach", attach_payload(e, fault, uploaded), "attach", now
    )
    purge = {
        **attach_payload(e, attached, {**uploaded, "revision": 3}, actor),
        "reason": "Reviewed",
    }
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(actor, "maintenance.fault_photo_purge", purge, "denied", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["uploader", "assignment", "fault", "source", "tasks", "maintenance", "expired", "blob"],
)
async def test_reservation_or_upload_drift_cannot_attach(engine, store, now, change):
    e, fault = await setup(engine, store, now, reporter="sibling")
    uploaded = await upload(e, fault, now)
    request = attach_payload(e, fault, uploaded)
    state = e.snapshot()
    task = state["tasks"][fault["task_id"]]
    if change == "uploader":
        state["members"]["child"]["revision"] += 1
    elif change == "assignment":
        task.update(assignee="adult", assignee_revision=1)
    elif change == "fault":
        state["maintenance"]["faults"][fault["id"]]["revision"] += 1
    elif change == "source":
        task["source"]["fault_id"] = "unrelated-fault"
    elif change in {"tasks", "maintenance"}:
        state["settings"]["modules"].remove(change)
    elif change == "expired":
        state["media"][uploaded["id"]]["expires_at"] = now.isoformat()
    else:
        state["media"][uploaded["id"]]["blob_key"] = "../not-a-blob"
    e = Engine(state, store.save)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute("child", "maintenance.fault_photo_attach", request, "drift", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_fault_and_task_report_media_are_not_interchangeable(engine, store, now):
    e, fault = await setup(engine, store, now)
    uploaded = await upload(e, fault, now)
    task = await e.execute(
        "parent",
        "tasks.create",
        {"title": "Photo completion", "assignee": "child", "report_type": "photo"},
        "photo-task",
        now,
    )
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "child",
            "tasks.submit",
            {
                "id": task["id"],
                "revision": task["revision"],
                "media": {"id": uploaded["id"], "revision": 2},
            },
            "wrong-purpose",
            now,
        )
    assert e.snapshot() == before
    reserved = await e.execute(
        "child",
        "media.reserve",
        {
            "purpose": "task_report",
            "task_id": task["id"],
            "task_revision": task["revision"],
            "uploader_revision": 1,
        },
        "report-reserve",
        now,
    )
    report = await e.system_update(
        "report-verified",
        now,
        lambda ctx: media.finalize(ctx, "child", reserved["id"], 1, "image/png", 100, "b" * 64),
    )
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "child",
            "maintenance.fault_photo_attach",
            attach_payload(e, fault, report),
            "inverse-purpose",
            now,
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_reserve_exact_replay_then_attachment_and_epoch_revoke(engine, store, now):
    e, fault = await setup(engine, store, now)
    payload = reserve_payload(e, fault)
    receipt = await e.execute("child", "media.reserve", payload, "reserve", now)
    before, writes = e.snapshot(), store.calls
    assert await e.execute("child", "media.reserve", payload, "reserve", now) == receipt
    assert e.snapshot() == before and store.calls == writes
    available = await e.system_update(
        "verify",
        now,
        lambda ctx: media.finalize(ctx, "child", receipt["id"], 1, "image/png", 100, "a" * 64),
    )
    request = attach_payload(e, fault, available)
    await e.execute("child", "maintenance.fault_photo_attach", request, "attach", now)
    with pytest.raises(DomainError):
        await e.execute("child", "media.reserve", payload, "reserve", now)
    state = e.snapshot()
    state["members"]["child"]["revision"] += 1
    e = Engine(state, store.save)
    assert e.view("child", now=now)["maintenance"]["faults"] == []
    with pytest.raises(DomainError):
        await e.execute("child", "maintenance.fault_photo_attach", request, "attach", now)
    with pytest.raises(DomainError):
        metadata(e, now, receipt["id"], "child")
    assert metadata(e, now, receipt["id"], "parent")["status"] == "attached"


@pytest.mark.asyncio
async def test_history_capacity_is_explicit_not_silent_truncation(engine, store, now):
    e, fault = await setup(engine, store, now)
    uploaded = await upload(e, fault, now)
    state = e.snapshot()
    state["maintenance"]["faults"][fault["id"]]["photo_history"] = [
        {}
    ] * fault_photos.MAX_PHOTO_EVENTS
    e = Engine(state, store.save)
    before = e.snapshot()
    with pytest.raises(DomainError, match="quota_exceeded"):
        await e.execute(
            "child",
            "maintenance.fault_photo_attach",
            attach_payload(e, fault, uploaded),
            "capacity",
            now,
        )
    assert e.snapshot() == before
