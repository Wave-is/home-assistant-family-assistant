"""Independent school acceptance through real transactions and private projections."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError

CANARY = "SCHOOL-PRIVATE-MATERIAL-1f23"
INVALID_REVISIONS = [None, True, False, 1.0, "1", 0, -1, 2**53]


@pytest.fixture
def school_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"].append("school")
    return Engine(state, store.save)


def payload(engine, member="child", **changes):
    return {
        "member": member,
        "member_revision": engine.snapshot()["members"][member]["revision"],
        "title": f"Timetable {member}",
        "valid_from": "2026-09-01",
        "valid_until": "2026-12-31",
        "exceptions": [],
        "backpack_routine": None,
        "lessons": [
            {
                "weekday": 0,
                "start": "09:00",
                "end": "09:45",
                "subject": "Science",
                "room": "Room 2",
                "materials": [CANARY],
            }
        ],
        **changes,
    }


async def save(engine, now, *, actor="parent", operation="school-save", **changes):
    return await engine.execute(
        actor, "school.timetable_save", payload(engine, **changes), operation, now
    )


def tables(engine):
    return engine.snapshot()["school"]["timetables"]


async def member_change(engine, now, member="child", **changes):
    record = engine.snapshot()["members"][member]
    return await engine.execute(
        "owner",
        "members.save",
        {
            "id": member,
            "revision": record["revision"],
            "name": record["name"],
            "role": record["role"],
            **changes,
        },
        f"school-member-{member}-{record['revision']}",
        now,
    )


@pytest.mark.asyncio
async def test_school_create_opaque_receipt_privacy_and_no_other_module_effects(
    school_engine, store, now
):
    before = school_engine.snapshot()
    receipt = await save(school_engine, now)
    assert receipt == {"id": "ST000001", "revision": 1, "status": "active"}
    state = school_engine.snapshot()
    for bucket in ("outbox", "routine_runs", "tasks", "court", "calendar", "shopping", "pantry"):
        assert state[bucket] == before[bucket]
    assert CANARY not in json.dumps({"audit": state["audit"], "processed": state["processed"]})
    for actor in ("owner", "parent", "child"):
        assert CANARY in json.dumps(school_engine.view(actor, now=now)["school"])
        assert CANARY not in json.dumps(plans.projection(school_engine.view(actor, now=now)))
    for actor in ("sibling", "adult", "guest"):
        assert CANARY not in json.dumps(school_engine.view(actor, now=now))
    child = school_engine.view("child", now=now)["school"]["timetables"][0]
    assert "history" not in child and "created_by" not in child
    child["lessons"][0]["materials"].append("tampered projection")
    assert tables(school_engine)[receipt["id"]]["lessons"][0]["materials"] == [CANARY]
    restarted = Engine(store.value, store.save)
    assert (
        restarted.view("child", now=now)["school"] == school_engine.view("child", now=now)["school"]
    )


@pytest.mark.asyncio
async def test_school_concurrent_duplicate_is_one_commit_and_restart_replay_is_exact(
    school_engine, store, now
):
    command = payload(school_engine)
    results = await asyncio.gather(
        *[
            school_engine.execute(
                "parent", "school.timetable_save", command, "same-school-command", now
            )
            for _ in range(6)
        ]
    )
    assert all(result == results[0] for result in results)
    assert store.calls == 1 and len(tables(school_engine)) == 1
    restarted = Engine(store.value, store.save)
    assert (
        await restarted.execute(
            "parent", "school.timetable_save", command, "same-school-command", now
        )
        == results[0]
    )
    assert store.calls == 1


@pytest.mark.asyncio
async def test_school_store_failure_and_batch_failure_commit_nothing(school_engine, store, now):
    before = school_engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await save(school_engine, now)
    assert school_engine.snapshot() == before
    store.fail = False
    malformed = payload(school_engine, member="sibling", lessons=[])
    with pytest.raises(DomainError):
        await school_engine.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "school.timetable_save", "payload": payload(school_engine)},
                    {"action": "school.timetable_save", "payload": malformed},
                ]
            },
            "school-atomic-failure",
            now,
        )
    assert school_engine.snapshot() == before
    assert store.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", INVALID_REVISIONS)
async def test_school_member_revision_is_strict_before_first_create(
    school_engine, store, now, revision
):
    before = school_engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await save(school_engine, now, member_revision=revision)
    assert school_engine.snapshot() == before and store.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", INVALID_REVISIONS)
async def test_school_edit_and_archive_require_strict_record_revision(
    school_engine, store, now, revision
):
    receipt = await save(school_engine, now)
    before, writes = school_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await save(
            school_engine,
            now,
            operation="school-edit",
            id=receipt["id"],
            revision=revision,
            title="Changed",
        )
    with pytest.raises(DomainError, match="invalid_field"):
        await school_engine.execute(
            "parent",
            "school.timetable_archive",
            {"id": receipt["id"], "revision": revision, "reason": "New term"},
            "school-archive",
            now,
        )
    assert school_engine.snapshot() == before and store.calls == writes


@pytest.mark.asyncio
async def test_school_reviewed_child_identity_change_requires_explicit_fresh_review(
    school_engine, now
):
    command = payload(school_engine)
    await member_change(school_engine, now, name="Renamed child")
    with pytest.raises(DomainError, match="conflict"):
        await school_engine.execute(
            "parent", "school.timetable_save", command, "stale-child-review", now
        )
    receipt = await save(school_engine, now)
    await member_change(school_engine, now, role="adult")
    assert "school" not in school_engine.view("child", now=now)
    await member_change(school_engine, now, role="child")
    assert school_engine.view("child", now=now)["school"] == {
        "online": {"sources": []},
        "timetables": [],
        "upcoming": [],
        "homework": [],
        "preparations": [],
        "preparation_reminders": {
            "policy": {"enabled": False, "days_before": 1, "time": "20:00", "timezone": "UTC"},
            "self_targets": [
                {
                    "member": "child",
                    "member_revision": 4,
                    "recipient_revision": 4,
                    "enabled": False,
                    "subscription_revision": None,
                }
            ],
        },
    }
    refreshed = await save(
        school_engine,
        now,
        operation="review-returned-child",
        id=receipt["id"],
        revision=receipt["revision"],
    )
    assert refreshed["revision"] == 2
    assert school_engine.view("child", now=now)["school"]["timetables"]


@pytest.mark.asyncio
async def test_school_one_active_archive_and_full_replacement(school_engine, now):
    receipt = await save(school_engine, now, exceptions=["2026-09-14"])
    with pytest.raises(DomainError, match="conflict"):
        await save(school_engine, now, operation="duplicate-active")
    changed = await save(
        school_engine,
        now,
        operation="replace-school",
        id=receipt["id"],
        revision=1,
        title="Autumn revised",
    )
    assert tables(school_engine)[receipt["id"]]["exceptions"] == []
    with pytest.raises(DomainError, match="conflict"):
        await save(school_engine, now, operation="stale-replace", id=receipt["id"], revision=1)
    archived = await school_engine.execute(
        "parent",
        "school.timetable_archive",
        {"id": receipt["id"], "revision": changed["revision"], "reason": "Term changed"},
        "archive-school",
        now,
    )
    assert archived["status"] == "archived"
    assert school_engine.view("child", now=now)["school"] == {
        "online": {"sources": []},
        "timetables": [],
        "upcoming": [],
        "homework": [],
        "preparations": [],
        "preparation_reminders": {
            "policy": {"enabled": False, "days_before": 1, "time": "20:00", "timezone": "UTC"},
            "self_targets": [
                {
                    "member": "child",
                    "member_revision": 1,
                    "recipient_revision": 1,
                    "enabled": False,
                    "subscription_revision": None,
                }
            ],
        },
    }
    with pytest.raises(DomainError, match="invalid_transition"):
        await save(
            school_engine,
            now,
            operation="edit-archived",
            id=receipt["id"],
            revision=archived["revision"],
        )
    new = await save(school_engine, now, operation="next-term", title="Next term")
    assert new["id"] != receipt["id"] and len(tables(school_engine)) == 2
    assert len(school_engine.view("parent", now=now)["school"]["timetables"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["child", "sibling", "adult", "guest"])
async def test_school_nonparents_cannot_create_or_archive(school_engine, now, actor):
    with pytest.raises(DomainError, match="forbidden"):
        await save(school_engine, now, actor=actor)
    created = await save(school_engine, now)
    with pytest.raises(DomainError, match="forbidden"):
        await school_engine.execute(
            actor,
            "school.timetable_archive",
            {"id": created["id"], "revision": 1, "reason": "Not permitted"},
            "unauthorized-archive",
            now,
        )


@pytest.mark.asyncio
async def test_school_module_and_actor_revocation_apply_to_old_receipts(school_engine, now):
    command = payload(school_engine)
    await school_engine.execute("parent", "school.timetable_save", command, "school-original", now)
    settings = school_engine.snapshot()["settings"]
    await school_engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": [m for m in settings["modules"] if m != "school"],
        },
        "school-disable",
        now,
    )
    with pytest.raises(DomainError, match="module_disabled"):
        await school_engine.execute(
            "parent", "school.timetable_save", command, "school-original", now
        )
    assert "school" not in school_engine.view("parent", now=now)
    await school_engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": settings["modules"],
        },
        "school-enable",
        now,
    )
    await member_change(school_engine, now, member="parent", role="adult")
    with pytest.raises(DomainError, match="forbidden"):
        await school_engine.execute(
            "parent", "school.timetable_save", command, "school-original", now
        )


@pytest.mark.asyncio
async def test_school_tick_is_inert_and_agenda_uses_household_local_day_and_exceptions(
    school_engine, now
):
    await save(school_engine, now, exceptions=["2026-09-14"])
    before = school_engine.snapshot()
    monday_local = datetime(2026, 9, 6, 22, 30, tzinfo=UTC)
    assert await school_engine.tick(monday_local) is False
    assert school_engine.snapshot() == before
    rows = school_engine.view("child", now=monday_local)["school"]["upcoming"]
    assert [row["date"] for row in rows] == ["2026-09-07"]
    assert rows[0]["materials"] == [CANARY]
    rows[0]["materials"].clear()
    assert school_engine.snapshot() == before
    assert deepcopy(school_engine.view("parent"))["school"]["upcoming"] == []
