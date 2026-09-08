"""Fail-closed malformed records, competing images and terminal fault work."""

import pytest
from test_fault_photos import attach_payload, metadata, reserve_payload, setup, upload
from test_maintenance_engine import fault_payload

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["assignment", "source", "task"])
async def test_boolean_task_provenance_is_not_an_integer_identity(engine, store, now, field):
    e, fault = await setup(engine, store, now)
    state = e.snapshot()
    task = state["tasks"][fault["task_id"]]
    if field == "assignment":
        task["assignee_revision"] = True
    elif field == "source":
        task["source"]["asset_revision"] = True
    else:
        task["revision"] = True
    e = Engine(state, store.save)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "parent", "media.reserve", reserve_payload(e, fault, "parent"), "bool-pin", now
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, True, 0, -1, 1.0, "1", 2**53])
async def test_incomplete_fault_withholds_upload_without_breaking_projection(
    engine, store, now, bad
):
    e, fault = await setup(engine, store, now)
    state = e.snapshot()
    row = state["maintenance"]["faults"][fault["id"]]
    if bad is None:
        row.pop("revision")
    else:
        row["revision"] = bad
    e = Engine(state, store.save)
    assert e.view("parent", now=now)["maintenance"]["faults"][0]["can_upload_photo"] is False
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute("child", "media.reserve", reserve_payload(e, fault), "invalid", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_competing_reservation_cannot_replace_committed_attachment(engine, store, now):
    e, fault = await setup(engine, store, now)
    one = await upload(e, fault, now, operation="one")
    two = await upload(e, fault, now, operation="two")
    await e.execute(
        "child", "maintenance.fault_photo_attach", attach_payload(e, fault, one), "first", now
    )
    before = e.snapshot()
    for target in (fault, {**fault, "revision": 2}):
        with pytest.raises(DomainError):
            await e.execute(
                "child",
                "maintenance.fault_photo_attach",
                attach_payload(e, target, two),
                "replace",
                now,
            )
        assert e.snapshot() == before
    assert e.snapshot()["media"][two["id"]]["status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["submitted", "completed", "cancelled", "archived"])
async def test_terminal_task_keeps_old_evidence_but_accepts_no_new_photo(
    engine, store, now, status
):
    e, fault = await setup(engine, store, now)
    uploaded = await upload(e, fault, now)
    empty = e.snapshot()
    empty["tasks"][fault["task_id"]]["status"] = status
    blocked = Engine(empty, store.save)
    with pytest.raises(DomainError):
        await blocked.execute(
            "parent", "media.reserve", reserve_payload(blocked, fault, "parent"), "closed", now
        )
    await e.execute(
        "child", "maintenance.fault_photo_attach", attach_payload(e, fault, uploaded), "attach", now
    )
    state = e.snapshot()
    state["tasks"][fault["task_id"]]["status"] = status
    e = Engine(state, store.save)
    assert metadata(e, now, uploaded["id"], "child")["status"] == "attached"
    assert e.view("parent", now=now)["maintenance"]["faults"][0]["can_upload_photo"] is False


@pytest.mark.asyncio
async def test_cross_fault_attach_and_purge_deny_other_reverse_reference(engine, store, now):
    e, first = await setup(engine, store, now)
    asset = next(iter(e.snapshot()["maintenance"]["assets"].values()))
    second = await e.execute(
        "child",
        "maintenance.fault_report",
        fault_payload(e, asset, summary="Another distinct observation"),
        "second-fault",
        now,
    )
    uploaded = await upload(e, first, now)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "child",
            "maintenance.fault_photo_attach",
            attach_payload(e, second, uploaded),
            "cross",
            now,
        )
    assert e.snapshot() == before
    await e.execute(
        "child", "maintenance.fault_photo_attach", attach_payload(e, first, uploaded), "attach", now
    )
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "owner",
            "maintenance.fault_photo_purge",
            {
                **attach_payload(e, second, {**uploaded, "revision": 3}, "owner"),
                "reason": "Wrong fault",
            },
            "cross-purge",
            now,
        )
    assert e.snapshot() == before
