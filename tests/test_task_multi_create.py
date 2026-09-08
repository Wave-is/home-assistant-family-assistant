"""One atomic assignment, separate per-member lifecycles and reviewed identity."""

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def command(member, revision=1, **extra):
    return {
        "action": "tasks.create",
        "payload": {
            "title": "Synthetic independent chore",
            "assignee": member,
            "assignee_revision": revision,
            "checklist": ["Prepare", "Finish"],
            "report_type": "text",
            **extra,
        },
    }


@pytest.mark.parametrize("revision", [None, True, False, 0, -1, 1.0, "1", 2**53, [], {}])
async def test_malformed_create_assignee_revision_never_writes(engine, store, now, revision):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent", "tasks.create", command("child", revision)["payload"], "bad", now
        )
    assert engine.snapshot() == before
    assert store.calls == 0


@pytest.mark.parametrize("bad_target", ["stale", "guest", "inactive", "missing"])
async def test_batch_rejects_whole_group_before_any_persistence(engine, store, now, bad_target):
    state = engine.snapshot()
    if bad_target == "inactive":
        state["members"]["sibling"]["active"] = False
    engine = Engine(state, store.save)
    target = {"guest": "guest", "missing": "missing"}.get(bad_target, "sibling")
    commands = [command("child"), command(target, 2 if bad_target == "stale" else 1)]
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute("parent", "batch", {"commands": commands}, "group", now)
    assert engine.snapshot() == before
    assert store.calls == 0


async def test_group_creates_distinct_records_once_and_survives_reload(engine, store, now):
    payload = {"commands": [command("child"), command("sibling")]}
    before = engine.snapshot()
    result = await engine.execute("parent", "batch", payload, "group", now)
    items = result["items"]
    assert len({item["id"] for item in items}) == 2
    assert [item["assignee"] for item in items] == ["child", "sibling"]
    assert all(item["assignee_revision"] == 1 for item in items)
    saved = engine.snapshot()
    assert saved["revision"] == before["revision"] + 1
    assert len(saved["audit"]) == len(before["audit"]) + 1
    assert store.calls == 1 and store.value == saved
    restarted = Engine(store.value, store.save)
    assert await restarted.execute("parent", "batch", payload, "group", now) == result
    assert restarted.snapshot() == saved and store.calls == 1


async def test_group_disk_failure_does_not_partially_create_then_exact_retry(engine, store, now):
    payload = {"commands": [command("child"), command("sibling")]}
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("parent", "batch", payload, "group", now)
    assert engine.snapshot() == before and store.value is None
    store.fail = False
    result = await engine.execute("parent", "batch", payload, "group", now)
    assert len(result["items"]) == len(engine.snapshot()["tasks"]) == 2


async def test_child_cannot_assign_sibling_in_group(engine, store, now):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child", "batch", {"commands": [command("child"), command("sibling")]}, "group", now
        )
    assert engine.snapshot() == before and store.calls == 0


async def test_reviewed_target_is_checked_after_waiting_for_another_write(engine, store, now):
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_save(state):
        entered.set()
        await release.wait()
        await store.save(state)

    engine = Engine(engine.snapshot(), delayed_save)
    update = asyncio.create_task(
        engine.execute(
            "owner",
            "members.save",
            {
                "id": "sibling",
                "revision": 1,
                "name": "Renamed synthetic child",
                "role": "child",
            },
            "member-update",
            now,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        pending = asyncio.create_task(
            engine.execute(
                "parent",
                "batch",
                {
                    "commands": [command("child"), command("sibling")],
                },
                "reviewed-group",
                now,
            )
        )
        release.set()
        await update
        with pytest.raises(DomainError, match="conflict"):
            await pending
        assert not engine.snapshot()["tasks"] and store.calls == 1
    finally:
        release.set()
        await update


async def test_legacy_unpinned_creation_remains_compatible(engine, now):
    payload = command("child")["payload"]
    payload.pop("assignee_revision")
    result = await engine.execute("parent", "tasks.create", payload, "legacy-create", now)
    assert result["assignee"] == "child" and result["assignee_revision"] == 1


async def test_independent_reports_checklists_and_overdue_penalty(engine, store, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": "en",
            "modules": settings["modules"],
            "automatic_penalties": True,
            "daily_penalty_cap": 1,
        },
        "opt-in",
        now,
    )
    result = await engine.execute(
        "parent",
        "batch",
        {
            "commands": [
                command(
                    member,
                    due_at=(now + timedelta(hours=1)).isoformat(),
                    grace_minutes=0,
                    penalty=-1,
                )
                for member in ("child", "sibling")
            ]
        },
        "group",
        now,
    )
    first, second = result["items"]
    untouched = deepcopy(engine.snapshot()["tasks"][second["id"]])
    first = await engine.execute(
        "child",
        "tasks.check",
        {
            "id": first["id"],
            "revision": first["revision"],
            "checklist_index": 0,
            "done": True,
        },
        "check-first",
        now,
    )
    first = await engine.execute(
        "child",
        "tasks.submit",
        {
            "id": first["id"],
            "revision": first["revision"],
            "report": "Synthetic completed report",
        },
        "report-first",
        now,
    )
    await engine.execute(
        "parent",
        "tasks.complete",
        {
            "id": first["id"],
            "revision": first["revision"],
        },
        "approve-first",
        now,
    )
    assert engine.snapshot()["tasks"][second["id"]] == untouched
    await engine.tick(now + timedelta(hours=2))
    restarted = Engine(store.value, store.save)
    await restarted.tick(now + timedelta(hours=3))
    penalties = restarted.snapshot()["court"]
    assert len(penalties) == 1
    assert penalties[f"task:{second['id']}"]["points"] == -1
    assert penalties[f"task:{second['id']}"]["member"] == "sibling"
