"""Typed editing, reassignment and deadline removal preserve task state."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.validation import DomainError


async def create(engine, now, **extra):
    return await engine.execute(
        "parent",
        "tasks.create",
        {
            "title": "Synthetic task",
            "assignee": "child",
            "due_at": (now + timedelta(hours=1)).isoformat(),
            **extra,
        },
        "create",
        now,
    )


@pytest.mark.asyncio
async def test_unchanged_reassignment_or_instant_does_not_reset_progress(engine, now):
    item = await create(engine, now)
    started = await engine.execute("child", "tasks.start", {"id": item["id"]}, "start", now)
    updated = await engine.execute(
        "parent",
        "tasks.revise",
        {
            "id": item["id"],
            "revision": started["revision"],
            "assignee": "child",
            "title": "Updated",
            "due_at": "2026-09-06T12:00:00+03:00",
        },
        "edit",
        now,
    )
    assert updated["status"] == "in_progress" and updated["due_at"] == item["due_at"]
    assert updated["title"] == "Updated"


@pytest.mark.asyncio
async def test_clearing_deadline_supersedes_old_reminder_and_replays(engine, now):
    item = await create(engine, now)
    await engine.tick(now)
    assert any(e["key"] == "task_reminder" for e in engine.snapshot()["outbox"].values())
    current = engine.snapshot()["tasks"][item["id"]]
    payload = {"id": item["id"], "revision": current["revision"], "due_at": None}
    cleared = await engine.execute("parent", "tasks.revise", payload, "clear", now)
    assert cleared["due_at"] is None
    assert await engine.execute("parent", "tasks.revise", payload, "clear", now) == cleared
    assert all(
        e["state"] == "superseded"
        for e in engine.snapshot()["outbox"].values()
        if e["key"] == "task_reminder"
    )
    await engine.tick(now + timedelta(days=2))
    assert not engine.snapshot()["court"]


@pytest.mark.asyncio
async def test_reassignment_preserves_report_and_supersedes_old_private_assignment(engine, now):
    item = await create(engine, now)
    await engine.execute(
        "child", "tasks.submit", {"id": item["id"], "report": "Old report"}, "report", now
    )
    await engine.execute(
        "parent", "tasks.request_changes", {"id": item["id"], "note": "Review note"}, "review", now
    )
    reassigned = await engine.execute(
        "parent", "tasks.revise", {"id": item["id"], "assignee": "sibling"}, "reassign", now
    )
    assert reassigned["status"] == "assigned" and reassigned["report"] is None
    assert reassigned["previous_reports"] == [
        {
            "assignee": "child",
            "report": "Old report",
            "review_note": "Review note",
            "reassigned_at": now.isoformat(),
        }
    ]
    assert not engine.view("child")["tasks"]
    assert engine.view("sibling")["tasks"][0]["id"] == item["id"]
    for event in engine.snapshot()["outbox"].values():
        if event["key"] == "task_assigned":
            assert event["state"] == (
                "pending" if event["recipient"] == "sibling" else "superseded"
            )
        if event["key"] == "task_review":
            assert event["state"] == "superseded"


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [None, True, False, 1.0, "1", 0, -1])
async def test_explicit_invalid_revision_never_bypasses_concurrency(engine, now, revision):
    item = await create(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "tasks.revise",
            {"id": item["id"], "revision": revision, "title": "Bad"},
            "invalid",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_action_specific_fields_prevent_silently_ignored_mutations(engine, now):
    item = await create(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent", "tasks.complete", {"id": item["id"], "due_at": None}, "wrong-action", now
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_guest_assignment_and_duplicate_archive_rejected(engine, now):
    with pytest.raises(DomainError, match="invalid_field"):
        await create(engine, now, assignee="guest")
    item = await create(engine, now)
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent", "tasks.revise", {"id": item["id"], "assignee": "guest"}, "guest", now
        )
    archived = await engine.execute("parent", "tasks.archive", {"id": item["id"]}, "archive", now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "tasks.archive",
            {"id": item["id"], "revision": archived["revision"]},
            "again",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_edit_storage_failure_keeps_deadline_and_outbox(engine, store, now):
    item = await create(engine, now)
    await engine.tick(now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute(
            "parent", "tasks.revise", {"id": item["id"], "due_at": None}, "clear", now
        )
    assert engine.snapshot() == before
