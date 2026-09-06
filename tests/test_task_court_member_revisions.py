"""Strict optimistic-revision contracts for existing mutable records."""

import pytest

from custom_components.family_assistant.domain.validation import DomainError

OMITTED = object()
BAD_REVISIONS = (OMITTED, None, True, 1.0, "1", 0, 2**53)
TASK_ACTIONS = (
    ("revise", "parent", {"title": "Changed"}),
    ("submit", "child", {"report": "Done"}),
    ("check", "child", {"checklist_index": 0, "done": True}),
    ("request_changes", "parent", {"note": "Try again"}),
    ("accept", "child", {}),
    ("start", "child", {}),
    ("complete", "parent", {}),
    ("cancel", "parent", {}),
    ("archive", "parent", {}),
)
COURT_ACTIONS = (
    ("appeal", "child", {"reason": "Please review"}),
    ("reverse", "parent", {"reason": "Correction"}),
    ("resolve_appeal", "parent", {"reason": "Reviewed", "decision": "reverse"}),
)


async def reject_without_write(engine, store, actor, action, payload, operation, now, code):
    before = engine.snapshot()
    calls = store.calls
    with pytest.raises(DomainError, match=code) as caught:
        await engine.execute(actor, action, payload, operation, now)
    assert caught.value.code == code
    assert engine.snapshot() == before
    assert store.calls == calls


async def create_task(engine, now, operation):
    return await engine.execute(
        "parent",
        "tasks.create",
        {"title": "Tidy desk", "assignee": "child", "checklist": ["Books"]},
        operation,
        now,
    )


async def create_court_record(engine, now, operation):
    return await engine.execute(
        "parent",
        "court.award",
        {"member": "child", "points": -1, "reason": "Synthetic score"},
        operation,
        now,
    )


@pytest.mark.parametrize("bad_revision", BAD_REVISIONS)
@pytest.mark.parametrize(("command", "actor", "extra"), TASK_ACTIONS)
async def test_every_task_mutation_rejects_missing_or_malformed_revision(
    engine, store, now, command, actor, extra, bad_revision
):
    task = await create_task(engine, now, f"task-create:{command}:{bad_revision!r}")
    payload = {"id": task["id"], **extra}
    if bad_revision is not OMITTED:
        payload["revision"] = bad_revision
    await reject_without_write(
        engine,
        store,
        actor,
        f"tasks.{command}",
        payload,
        f"task-bad:{command}:{bad_revision!r}",
        now,
        "invalid_field",
    )


@pytest.mark.parametrize(("command", "actor", "extra"), TASK_ACTIONS)
async def test_every_task_mutation_rejects_stale_positive_revision(
    engine, store, now, command, actor, extra
):
    task = await create_task(engine, now, f"task-stale-create:{command}")
    await engine.execute(
        "child",
        "tasks.start",
        {"id": task["id"], "revision": task["revision"]},
        f"task-advance:{command}",
        now,
    )
    await reject_without_write(
        engine,
        store,
        actor,
        f"tasks.{command}",
        {"id": task["id"], "revision": task["revision"], **extra},
        f"task-stale:{command}",
        now,
        "conflict",
    )


@pytest.mark.parametrize("bad_revision", BAD_REVISIONS)
@pytest.mark.parametrize(("command", "actor", "extra"), COURT_ACTIONS)
async def test_every_court_mutation_rejects_missing_or_malformed_revision(
    engine, store, now, command, actor, extra, bad_revision
):
    record = await create_court_record(engine, now, f"court-create:{command}:{bad_revision!r}")
    payload = {"id": record["id"], **extra}
    if bad_revision is not OMITTED:
        payload["revision"] = bad_revision
    await reject_without_write(
        engine,
        store,
        actor,
        f"court.{command}",
        payload,
        f"court-bad:{command}:{bad_revision!r}",
        now,
        "invalid_field",
    )


@pytest.mark.parametrize(("command", "actor", "extra"), COURT_ACTIONS)
async def test_every_court_mutation_rejects_stale_positive_revision(
    engine, store, now, command, actor, extra
):
    record = await create_court_record(engine, now, f"court-stale-create:{command}")
    await engine.execute(
        "child",
        "court.appeal",
        {"id": record["id"], "revision": record["revision"], "reason": "First review"},
        f"court-advance:{command}",
        now,
    )
    await reject_without_write(
        engine,
        store,
        actor,
        f"court.{command}",
        {"id": record["id"], "revision": record["revision"], **extra},
        f"court-stale:{command}",
        now,
        "conflict",
    )


@pytest.mark.parametrize("bad_revision", BAD_REVISIONS)
async def test_existing_member_rejects_missing_or_malformed_revision(
    engine, store, now, bad_revision
):
    payload = {"id": "parent", "name": "Changed", "role": "parent"}
    if bad_revision is not OMITTED:
        payload["revision"] = bad_revision
    await reject_without_write(
        engine,
        store,
        "owner",
        "members.save",
        payload,
        f"member-bad:{bad_revision!r}",
        now,
        "invalid_field",
    )


async def test_existing_member_rejects_stale_revision_without_restoring_privilege(
    engine, store, now
):
    original = engine.snapshot()["members"]["parent"]
    changed = await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": original["revision"],
            "name": "Parent",
            "role": "adult",
            "active": False,
        },
        "member-demote",
        now,
    )
    assert changed["role"] == "adult" and changed["active"] is False
    await reject_without_write(
        engine,
        store,
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": original["revision"],
            "name": "Stale parent",
            "role": "parent",
            "active": True,
        },
        "member-stale-restore",
        now,
        "conflict",
    )


async def test_member_creation_allows_explicit_id_but_forbids_any_revision(engine, store, now):
    explicit = await engine.execute(
        "owner",
        "members.save",
        {"id": "fixture-member", "name": "Fixture", "role": "adult"},
        "member-explicit-create",
        now,
    )
    assert explicit["id"] == "fixture-member" and explicit["revision"] == 1

    generated = await engine.execute(
        "owner",
        "members.save",
        {"name": "Generated", "role": "adult"},
        "member-generated-create",
        now,
    )
    assert generated["id"].startswith("M") and generated["revision"] == 1

    await reject_without_write(
        engine,
        store,
        "owner",
        "members.save",
        {"name": "Invalid creation", "role": "adult", "revision": 1},
        "member-create-revision",
        now,
        "invalid_field",
    )
    await reject_without_write(
        engine,
        store,
        "owner",
        "members.save",
        {"id": "missing-member", "name": "Missing", "role": "adult", "revision": 1},
        "member-missing-edit",
        now,
        "not_found",
    )
    assert "missing-member" not in engine.snapshot()["members"]
