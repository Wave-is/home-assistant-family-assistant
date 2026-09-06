"""Focused synthetic tests for task series editing parity, concurrency, and validation."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import new_state
from custom_components.family_assistant.domain.validation import DomainError


def payload(now, **extra):
    return {
        "title": "Clean kitchen",
        "assignees": ["child"],
        "rule": {
            "frequency": "daily",
            "start_date": now.date().isoformat(),
            "time": "18:00",
            "timezone": "UTC",
        },
        "due_time": "19:00",
        **extra,
    }


def _make_state(creator_role="parent", creator_active=True):
    state = new_state("synthetic-owner", "Example household")
    state["members"]["parent"] = {
        "id": "parent",
        "name": "Parent",
        "role": creator_role,
        "language": "en",
        "ha_user_id": "synthetic-parent",
        "aliases": [],
        "active": creator_active,
        "revision": 1,
    }
    state["members"]["child"] = {
        "id": "child",
        "name": "Child",
        "role": "child",
        "language": "en",
        "ha_user_id": "synthetic-child",
        "aliases": [],
        "active": True,
        "revision": 1,
    }
    state["members"]["sibling"] = {
        "id": "sibling",
        "name": "Sibling",
        "role": "child",
        "language": "en",
        "ha_user_id": "synthetic-sibling",
        "aliases": [],
        "active": True,
        "revision": 1,
    }
    state["members"]["guest"] = {
        "id": "guest",
        "name": "Guest",
        "role": "guest",
        "language": "en",
        "ha_user_id": "synthetic-guest",
        "aliases": [],
        "active": True,
        "revision": 1,
    }
    return state


def _make_ctx(state, actor_id="parent", now=None, op_id="test-op"):
    now = now or datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
    actor = state["members"].get(actor_id, {"id": actor_id, "role": "system"})
    return Context(state, actor, now, op_id)


@pytest.mark.asyncio
async def test_creation_rejects_revision_and_requires_parent(engine, now):
    before = engine.snapshot()
    # Reject non-parent actors
    for actor in ("child", "guest", "adult"):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(actor, "tasks.series_save", payload(now), "denied-create", now)
    assert engine.snapshot() == before

    # Creation with revision must be rejected
    for bad_rev in (1, 2, 0, -1, "1", None, True):
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute(
                "parent",
                "tasks.series_save",
                payload(now, revision=bad_rev),
                f"bad-create-{bad_rev}",
                now,
            )
    assert engine.snapshot() == before

    # Valid creation succeeds with initial revision 1
    created = await engine.execute("parent", "tasks.series_save", payload(now), "create-1", now)
    assert created["id"].startswith("D")
    assert created["revision"] == 1
    assert created["creator"] == "parent"
    assert created["enabled"] is True
    assert created["rotation"] is False
    assert created["report_type"] == "text"
    assert created["checklist"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_revision", [None, True, False, "1", 1.0, 0, -1])
async def test_malformed_and_missing_revision_rejected_on_edit_and_enable(
    engine, now, bad_revision
):
    created = await engine.execute("parent", "tasks.series_save", payload(now), "create", now)
    series_id = created["id"]
    for action, change in (
        ("series_enable", {"enabled": False}),
        ("series_save", payload(now, title="Updated")),
    ):
        before = engine.snapshot()
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute(
                "parent",
                f"tasks.{action}",
                {**change, "id": series_id, "revision": bad_revision},
                f"bad-{action}-{type(bad_revision).__name__}",
                now,
            )
        assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_stale_revision_conflict_on_edit_and_enable(engine, now):
    created = await engine.execute("parent", "tasks.series_save", payload(now), "create", now)
    series_id = created["id"]
    rev = created["revision"]
    for action, change in (("series_enable", {"enabled": False}), ("series_save", payload(now))):
        before = engine.snapshot()
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute(
                "parent", f"tasks.{action}", {**change, "id": series_id}, f"missing-{action}", now
            )
        assert engine.snapshot() == before

    # Wrong / stale revision on save causes conflict
    before = engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "tasks.series_save",
            payload(now, id=series_id, revision=rev + 1),
            "stale-save",
            now,
        )
    assert engine.snapshot() == before

    # Wrong / stale revision on enable causes conflict
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "tasks.series_enable",
            {"id": series_id, "revision": rev + 5, "enabled": False},
            "stale-enable",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_partial_optional_preservation_and_explicit_clearing(engine, now):
    initial = payload(
        now,
        rotation=True,
        report_type="photo",
        checklist=["First step", "Second step"],
        enabled=True,
        reminder_minutes=30,
        grace_minutes=15,
        penalty=-2,
    )
    created = await engine.execute("parent", "tasks.series_save", initial, "create-full", now)
    series_id = created["id"]
    rev = created["revision"]

    assert created["rotation"] is True
    assert created["report_type"] == "photo"
    assert created["checklist"] == ["First step", "Second step"]
    assert created["deadline_policy"] == {
        "reminder_minutes": 30,
        "grace_minutes": 15,
        "penalty": -2,
    }

    # Partial edit without specifying rotation, report_type, checklist, enabled, or deadline_policy
    # should preserve the old values
    partial_payload = {
        "id": series_id,
        "revision": rev,
        "title": "Deep clean kitchen",
        "assignees": ["child", "sibling"],
        "rule": created["rule"],
        "due_time": "20:00",
    }
    updated = await engine.execute(
        "parent", "tasks.series_save", partial_payload, "partial-edit", now
    )
    assert updated["revision"] == rev + 1
    assert updated["title"] == "Deep clean kitchen"
    assert updated["assignees"] == ["child", "sibling"]
    assert updated["due_time"] == "20:00"
    assert updated["rotation"] is True
    assert updated["report_type"] == "photo"
    assert updated["checklist"] == ["First step", "Second step"]
    assert updated["enabled"] is True
    assert updated["deadline_policy"] == {
        "reminder_minutes": 30,
        "grace_minutes": 15,
        "penalty": -2,
    }

    # Explicit clearing / resetting of optional fields works
    clear_payload = {
        "id": series_id,
        "revision": updated["revision"],
        "title": "Reset chore",
        "assignees": ["child"],
        "rule": created["rule"],
        "due_time": "19:00",
        "rotation": False,
        "report_type": "none",
        "checklist": [],
        "enabled": True,
        "penalty": 0,
    }
    cleared = await engine.execute("parent", "tasks.series_save", clear_payload, "clear-edit", now)
    assert cleared["revision"] == updated["revision"] + 1
    assert cleared["rotation"] is False
    assert cleared["report_type"] == "none"
    assert cleared["checklist"] == []
    assert cleared["deadline_policy"]["penalty"] == 0
    # Unmentioned reminder_minutes and grace_minutes from previous deadline_policy retained
    assert cleared["deadline_policy"]["reminder_minutes"] == 30
    assert cleared["deadline_policy"]["grace_minutes"] == 15


@pytest.mark.asyncio
async def test_preserve_creator_cursor_and_occurrences_across_other_parent_edit(engine, now):
    created = await engine.execute("parent", "tasks.series_save", payload(now), "create-p", now)
    series_id = created["id"]

    # Trigger a tick so that occurrence and cursor are recorded
    tick_time = datetime.combine(now.date(), datetime.min.time()).replace(
        hour=18, minute=30, tzinfo=UTC
    )
    assert await engine.tick(tick_time)
    snapshot = engine.snapshot()
    series_in_state = snapshot["task_series"][series_id]
    assert series_in_state["cursor"] == 1
    assert len(series_in_state["occurrences"]) == 1
    saved_occurrences = deepcopy(series_in_state["occurrences"])

    # Revoke parent's role to child
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": engine.snapshot()["members"]["parent"]["revision"],
            "name": "Parent",
            "role": "child",
            "language": "en",
            "active": True,
        },
        "revoke-parent",
        tick_time,
    )

    # Now owner (another privileged parent) edits the task series
    rev = series_in_state["revision"]
    edited = await engine.execute(
        "owner",
        "tasks.series_save",
        {
            "id": series_id,
            "revision": rev,
            "title": "Clean kitchen by Owner",
            "assignees": ["child"],
            "rule": series_in_state["rule"],
            "due_time": series_in_state["due_time"],
        },
        "owner-edit",
        tick_time + timedelta(minutes=5),
    )

    # Creator must remain original creator ("parent") and NOT be resurrected / changed to "owner"
    assert edited["creator"] == "parent"
    # Cursor and occurrences must be preserved
    assert edited["cursor"] == 1
    assert edited["occurrences"] == saved_occurrences

    # Because creator "parent" is revoked (role is child), ticking next day must NOT create tasks
    next_day_tick = tick_time + timedelta(days=1)
    await engine.tick(next_day_tick)
    snap_after = engine.snapshot()["task_series"][series_id]
    # No new occurrence created for next day because creator was revoked!
    assert len(snap_after["occurrences"]) == 1


@pytest.mark.asyncio
async def test_idempotent_enable_and_replay(engine, now):
    created = await engine.execute("parent", "tasks.series_save", payload(now), "create", now)
    series_id = created["id"]
    rev = created["revision"]

    enable_payload = {"id": series_id, "revision": rev, "enabled": False}
    disabled = await engine.execute(
        "parent", "tasks.series_enable", enable_payload, "op-enable-1", now
    )
    assert disabled["enabled"] is False
    assert disabled["revision"] == rev + 1

    # Replay returns the exact same result without double-touching revision.
    replay = await engine.execute(
        "parent", "tasks.series_enable", enable_payload, "op-enable-1", now
    )
    assert replay == disabled
    assert engine.snapshot()["task_series"][series_id]["revision"] == rev + 1


@pytest.mark.asyncio
async def test_store_failure_rolls_back_series_save_and_enable(engine, store, now):
    created = await engine.execute("parent", "tasks.series_save", payload(now), "create", now)
    series_id = created["id"]
    before = engine.snapshot()

    # Store failure during series_save
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute(
            "parent",
            "tasks.series_save",
            payload(now, id=series_id, revision=created["revision"], title="Will fail"),
            "failing-save",
            now,
        )
    assert engine.snapshot() == before

    # Store failure during series_enable
    with pytest.raises(OSError):
        await engine.execute(
            "parent",
            "tasks.series_enable",
            {"id": series_id, "revision": created["revision"], "enabled": False},
            "failing-enable",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_inactive_and_guest_targets_cannot_receive_tasks(engine, now):
    # Cannot create or edit series with a guest assignee
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent", "tasks.series_save", payload(now, assignees=["guest"]), "guest-create", now
        )

    created = await engine.execute(
        "parent", "tasks.series_save", payload(now, assignees=["child"]), "valid-create", now
    )
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "tasks.series_save",
            payload(now, id=created["id"], revision=created["revision"], assignees=["guest"]),
            "guest-edit",
            now,
        )

    # Deactivate child assignee
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": engine.snapshot()["members"]["child"]["revision"],
            "name": "Child",
            "role": "child",
            "language": "en",
            "active": False,
        },
        "deactivate-child",
        now,
    )

    # Tick when child is inactive -> no tasks generated
    tick_time = datetime.combine(now.date(), datetime.min.time()).replace(
        hour=18, minute=30, tzinfo=UTC
    )
    assert not await engine.tick(tick_time)
    assert not engine.snapshot()["tasks"]
    assert not engine.snapshot()["task_series"][created["id"]]["occurrences"]
