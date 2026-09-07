"""Explicit retained-photo purge and bounded tombstone lifecycle tests."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from custom_components.family_assistant import media_storage as storage_module
from custom_components.family_assistant.domain import media, task_access
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.media_storage import MediaStorage


class MemoryStore:
    def __init__(self) -> None:
        self.value = None
        self.calls = 0
        self.fail_next = False

    async def save(self, state) -> None:
        self.calls += 1
        if self.fail_next:
            self.fail_next = False
            raise OSError("synthetic store failure")
        self.value = deepcopy(state)


class Clock:
    def __init__(self, now) -> None:
        self.value = now

    def __call__(self):
        return self.value


async def chunks(content: bytes):
    yield content


async def allowed() -> None:
    return None


async def decode(path: Path) -> dict:
    content = path.read_bytes()
    return {
        "mime_type": "image/png",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "width": 1,
        "height": 1,
    }


def retention_state() -> dict:
    state = new_state("synthetic-owner", "Synthetic retention household")
    for member_id, role in (("parent", "parent"), ("child", "child"), ("sibling", "child")):
        state["members"][member_id] = {
            "id": member_id,
            "name": member_id.title(),
            "role": role,
            "language": "en",
            "ha_user_id": f"synthetic-{member_id}",
            "aliases": [],
            "active": True,
            "revision": 1,
        }
    return state


async def execute(engine, actor, action, payload, operation, now):
    return await engine.execute(actor, action, payload, operation, now)


async def attached_environment(tmp_path, now):
    store = MemoryStore()
    engine = Engine(retention_state(), store.save)
    clock = Clock(now)
    root = tmp_path / "media"
    task = await execute(
        engine,
        "parent",
        "tasks.create",
        {"title": "Private retained photo", "assignee": "child", "report_type": "photo"},
        "create-photo",
        now,
    )
    reserve_payload = {
        "purpose": "task_report",
        "task_id": task["id"],
        "task_revision": task["revision"],
        "uploader_revision": 1,
    }
    reserved = await execute(
        engine, "child", "media.reserve", reserve_payload, "reserve-photo", now
    )
    storage = MediaStorage(engine, root, clock, decoder=decode)
    content = b"synthetic retained png"
    available = await storage.put(
        "synthetic-child",
        reserved["id"],
        reserved["revision"],
        chunks(content),
        guard=allowed,
    )
    submitted = await execute(
        engine,
        "child",
        "tasks.submit",
        {
            "id": task["id"],
            "revision": task["revision"],
            "media": {"id": available["id"], "revision": available["revision"]},
        },
        "submit-photo",
        now,
    )
    return engine, store, storage, clock, root, task, submitted, reserved, reserve_payload, content


def purge_payload(engine, task_id, media_id, **changes):
    state = engine.snapshot()
    task = state["tasks"][task_id]
    record = state["media"][media_id]
    return {
        "id": task_id,
        "revision": task["revision"],
        "report_generation": record["scope"]["report_generation"],
        "media_id": media_id,
        "media_revision": record["revision"],
        "reason": "Owner reviewed retained private photo",
        "confirmed": True,
        **changes,
    }


@pytest.mark.asyncio
async def test_owner_purge_is_atomic_content_free_and_collector_finishes(tmp_path, now):
    env = await attached_environment(tmp_path, now)
    engine, _store, storage, _clock, root, task, _submitted, reserved, _payload, _content = env
    before = engine.snapshot()
    original_task = deepcopy(before["tasks"][task["id"]])
    original_outbox = deepcopy(before["outbox"])
    blob = root / before["media"][reserved["id"]]["blob_key"]

    receipt = await execute(
        engine,
        "owner",
        "tasks.report_media_purge",
        purge_payload(engine, task["id"], reserved["id"]),
        "purge-photo",
        now,
    )

    state = engine.snapshot()
    changed = state["tasks"][task["id"]]
    assert receipt == {"id": task["id"], "revision": changed["revision"], "status": "submitted"}
    assert changed["status"] == original_task["status"]
    assert changed["report"] == original_task["report"]
    assert changed["deadline_policy"] == original_task["deadline_policy"]
    assert changed["checklist"] == original_task["checklist"]
    assert changed["report_media_purged_at"] == now.isoformat()
    assert "report_media" not in changed
    assert reserved["id"] not in str(changed)
    assert "Owner reviewed" not in str(changed)
    assert state["outbox"] == original_outbox
    assert state["media"][reserved["id"]]["status"] == "deleting"
    assert state["media"][reserved["id"]]["revision"] == 4
    assert blob.is_file()

    assert await storage.collect()
    deleted = engine.snapshot()["media"][reserved["id"]]
    assert deleted["status"] == "deleted" and deleted["revision"] == 5
    assert set(deleted) == {
        "id",
        "revision",
        "status",
        "created_at",
        "updated_at",
        "deleted_at",
    }
    assert not blob.exists()


@pytest.mark.asyncio
async def test_historical_reference_purge_and_archive_marker_survive(tmp_path, now):
    env = await attached_environment(tmp_path, now)
    engine, *_rest, task, _submitted, reserved, _reserve_payload, _content = env
    current = engine.snapshot()["tasks"][task["id"]]
    changed = await execute(
        engine,
        "parent",
        "tasks.request_changes",
        {"id": task["id"], "revision": current["revision"], "note": "Review again"},
        "request-photo-change",
        now,
    )
    revised = await execute(
        engine,
        "parent",
        "tasks.revise",
        {"id": task["id"], "revision": changed["revision"], "assignee": "sibling"},
        "reassign-photo",
        now,
    )
    assert revised["status"] == "assigned"
    payload = purge_payload(engine, task["id"], reserved["id"])

    await execute(engine, "owner", "tasks.report_media_purge", payload, "purge-history", now)

    historical = engine.snapshot()["tasks"][task["id"]]["previous_reports"][0]
    assert historical["report_generation"] == 1
    assert historical["report_media_purged_at"] == now.isoformat()
    assert "report_media" not in historical and reserved["id"] not in str(historical)

    # The same marker is retained if it occupies the current report slot when
    # ordinary task lifecycle code archives that report later.
    direct = engine.snapshot()
    current = direct["tasks"][task["id"]]
    current["report_generation"] = 2
    current["report_media_purged_at"] = now.isoformat()
    ctx = Context(direct, direct["members"]["parent"], now, "archive-purged")
    task_access.archive_report(ctx, current, "reassigned_at")
    assert current["previous_reports"][-1]["report_generation"] == 2
    assert current["previous_reports"][-1]["report_media_purged_at"] == now.isoformat()
    assert "report_media_purged_at" not in current


@pytest.mark.asyncio
async def test_purge_validation_authority_and_stale_inputs_are_write_free(tmp_path, now):
    env = await attached_environment(tmp_path, now)
    engine, *_rest, task, _submitted, reserved, _reserve_payload, _content = env
    valid = purge_payload(engine, task["id"], reserved["id"])
    cases = [
        ("parent", valid, "forbidden"),
        ("child", valid, "forbidden"),
        ("owner", {**valid, "confirmed": False}, "invalid_field"),
        ("owner", {**valid, "reason": ""}, "invalid_field"),
        ("owner", {**valid, "revision": valid["revision"] + 1}, "conflict"),
        ("owner", {**valid, "media_revision": True}, "invalid_field"),
        ("owner", {**valid, "report_generation": 2}, "conflict"),
        ("owner", {**valid, "extra": "private"}, "invalid_field"),
    ]
    for index, (actor, payload, code) in enumerate(cases):
        before = engine.snapshot()
        with pytest.raises(DomainError) as caught:
            await execute(engine, actor, "tasks.report_media_purge", payload, f"bad-{index}", now)
        assert caught.value.code == code
        assert engine.snapshot() == before

    state = engine.snapshot()
    state["settings"]["modules"].remove("tasks")
    disabled = Engine(state, MemoryStore().save)
    with pytest.raises(DomainError, match="module_disabled"):
        await execute(disabled, "owner", "tasks.report_media_purge", valid, "disabled-purge", now)


@pytest.mark.asyncio
async def test_store_failure_retry_restart_unlink_failure_and_backup_gate(
    tmp_path, now, monkeypatch
):
    env = await attached_environment(tmp_path, now)
    engine, store, storage, clock, root, task, _submitted, reserved, _payload, _content = env
    payload = purge_payload(engine, task["id"], reserved["id"])
    before = engine.snapshot()
    store.fail_next = True
    with pytest.raises(OSError):
        await execute(engine, "owner", "tasks.report_media_purge", payload, "purge-retry", now)
    assert engine.snapshot() == before

    expected = await execute(
        engine, "owner", "tasks.report_media_purge", payload, "purge-retry", now
    )
    assert (
        await execute(engine, "owner", "tasks.report_media_purge", payload, "purge-retry", now)
        == expected
    )

    restarted_store = MemoryStore()
    restarted = Engine(store.value, restarted_store.save)
    restarted_storage = MediaStorage(restarted, root, clock, decoder=decode)
    original_unlink = storage_module._unlink_blob

    def fail_unlink(_root, _key):
        raise OSError("synthetic unlink failure")

    monkeypatch.setattr(storage_module, "_unlink_blob", fail_unlink)
    with pytest.raises(DomainError, match="media_unavailable"):
        await restarted_storage.collect()
    assert restarted.snapshot()["media"][reserved["id"]]["status"] == "deleting"
    monkeypatch.setattr(storage_module, "_unlink_blob", original_unlink)
    assert await restarted_storage.collect()
    assert restarted.snapshot()["media"][reserved["id"]]["status"] == "deleted"

    token = await restarted.async_begin_backup()
    frozen = restarted.snapshot()
    with pytest.raises(DomainError, match="backup_in_progress"):
        await execute(
            restarted,
            "owner",
            "tasks.report_media_purge",
            payload,
            "blocked-purge",
            now,
        )
    assert restarted.snapshot() == frozen
    await restarted.async_end_backup(token)
    await storage.stop()
    await restarted_storage.stop()


@pytest.mark.asyncio
async def test_old_reserve_replay_after_reap_fails_closed_without_recreation(tmp_path, now):
    env = await attached_environment(tmp_path, now)
    (
        engine,
        _store,
        storage,
        clock,
        _root,
        task,
        _submitted,
        reserved,
        reserve_payload,
        _content,
    ) = env
    purge = purge_payload(engine, task["id"], reserved["id"])
    purged = await execute(
        engine,
        "owner",
        "tasks.report_media_purge",
        purge,
        "purge-before-reap",
        now,
    )
    assert await storage.collect()
    clock.value = now + timedelta(hours=24)
    assert await storage.collect()
    assert reserved["id"] not in engine.snapshot()["media"]
    before = engine.snapshot()

    assert (
        await execute(
            engine,
            "owner",
            "tasks.report_media_purge",
            purge,
            "purge-before-reap",
            clock(),
        )
        == purged
    )
    assert engine.snapshot() == before

    # The task revision was advanced by the purge, so replay authority fails at
    # the exact original target before it even needs the reaped media row.
    with pytest.raises(DomainError, match="conflict"):
        await execute(
            engine,
            "child",
            "media.reserve",
            reserve_payload,
            "reserve-photo",
            clock(),
        )

    assert engine.snapshot() == before
    assert reserved["id"] not in engine.snapshot()["media"]


def tombstone(media_id: str, deleted_at, revision=5) -> dict:
    moment = deleted_at.isoformat()
    return {
        "id": media_id,
        "revision": revision,
        "status": "deleted",
        "created_at": moment,
        "updated_at": moment,
        "deleted_at": moment,
    }


def test_reap_is_age_ordered_bounded_and_health_is_aggregate_only(now):
    state = retention_state()
    old = now - timedelta(hours=25)
    recent = now - timedelta(hours=23)
    for index in range(media.MAX_REAP + 5):
        media_id = f"M{index:032x}"
        state["media"][media_id] = tombstone(media_id, old + timedelta(seconds=index))
    recent_id = "M" + "f" * 32
    state["media"][recent_id] = tombstone(recent_id, recent)
    ctx = Context(state, {"id": "system", "role": "system"}, now, "reap")

    assert media.reap_deleted(ctx) == {"reaped": media.MAX_REAP}
    assert len(state["media"]) == 6 and recent_id in state["media"]
    assert media.reap_deleted(ctx) == {"reaped": 5}
    assert media.reap_deleted(ctx) == {"reaped": 0}
    stats = media.health_stats(state, now)
    assert stats == {
        "nondeleted": 0,
        "tombstones": 1,
        "reapable_tombstones": 0,
        "pending": 0,
        "deleting": 0,
        "verified_bytes": 0,
        "capacity": "ok",
    }
    assert recent_id not in str(stats)


def test_reap_never_forgets_a_malformed_tombstone_with_private_ownership(now):
    state = retention_state()
    media_id = "M" + "a" * 32
    state["media"][media_id] = {
        **tombstone(media_id, now - timedelta(days=2)),
        "blob_key": "b" * 64,
    }
    before = deepcopy(state)
    ctx = Context(state, {"id": "system", "role": "system"}, now, "malformed-reap")

    with pytest.raises(DomainError, match="invalid_field"):
        media.reap_deleted(ctx)

    assert state == before


def test_live_and_recent_tombstone_capacity_apply_backpressure(engine, now):
    state = engine.snapshot()
    state["media"] = {
        f"M{index:032x}": tombstone(f"M{index:032x}", now) for index in range(media.MAX_TOMBSTONES)
    }
    task = {
        "id": "T000099",
        "revision": 1,
        "status": "assigned",
        "title": "Capacity",
        "assignee": "child",
        "assignee_revision": 1,
        "creator": "parent",
        "report_type": "photo",
        "report": None,
        "checklist": [],
    }
    state["tasks"][task["id"]] = task
    before = deepcopy(state)
    with pytest.raises(DomainError, match="quota_exceeded"):
        media.handle(
            Context(state, state["members"]["child"], now, "capacity"),
            "reserve",
            {
                "purpose": "task_report",
                "task_id": task["id"],
                "task_revision": 1,
                "uploader_revision": 1,
            },
        )
    assert state == before
    assert media.health_stats(state, now)["capacity"] == "blocked"


def test_tombstone_ceiling_keeps_newly_unlinked_record_recoverable(engine, now):
    state = engine.snapshot()
    state["media"] = {
        f"M{index:032x}": tombstone(f"M{index:032x}", now) for index in range(media.MAX_TOMBSTONES)
    }
    deleting_id = "M" + "f" * 32
    state["media"][deleting_id] = {
        "id": deleting_id,
        "revision": 4,
        "uploader": "child",
        "uploader_revision": 1,
        "purpose": "task_report",
        "mime_type": "image/png",
        "size_bytes": 10,
        "sha256": "a" * 64,
        "status": "deleting",
        "scope": {"kind": "task_report"},
        "blob_key": "b" * 64,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": None,
    }
    before = deepcopy(state)

    with pytest.raises(DomainError, match="quota_exceeded"):
        media.finish_delete(
            Context(state, {"id": "system", "role": "system"}, now, "finish-at-cap"),
            deleting_id,
            4,
        )

    assert state == before
    assert state["media"][deleting_id]["status"] == "deleting"


def capacity_task(state):
    state["tasks"]["T000099"] = {
        "id": "T000099",
        "revision": 1,
        "status": "assigned",
        "title": "Synthetic capacity",
        "assignee": "child",
        "assignee_revision": 1,
        "creator": "parent",
        "report_type": "photo",
        "report": None,
        "checklist": [],
    }
    return {
        "purpose": "task_report",
        "task_id": "T000099",
        "task_revision": 1,
        "uploader_revision": 1,
    }


@pytest.mark.parametrize("status", ["attached", "deleting"])
@pytest.mark.parametrize("extra", [0, 1, media.MAX_FILE_BYTES])
def test_byte_health_matches_room_for_next_reservation(engine, now, status, extra):
    state = engine.snapshot()
    payload = capacity_task(state)
    # Exactly 240 MiB leaves room for one maximum reservation; one more byte does not.
    state["media"] = {
        f"M{index:032x}": {"status": status, "size_bytes": media.MAX_FILE_BYTES}
        for index in range(24)
    }
    if extra:
        state["media"]["M" + "f" * 32] = {"status": status, "size_bytes": extra}
    before = deepcopy(state)
    stats = media.health_stats(state, now)
    assert stats["verified_bytes"] == 24 * media.MAX_FILE_BYTES + extra
    assert stats["capacity"] == ("blocked" if extra else "near_limit")
    ctx = Context(state, state["members"]["child"], now, "byte-capacity")
    if extra:
        with pytest.raises(DomainError, match="quota_exceeded"):
            media.handle(ctx, "reserve", payload)
        assert state == before
    else:
        assert media.handle(ctx, "reserve", payload)["status"] == "reserved"


def test_deleting_unknown_size_still_occupies_one_full_reservation(engine, now):
    state = engine.snapshot()
    payload = capacity_task(state)
    state["media"] = {
        f"M{index:032x}": {"status": "deleting", "size_bytes": None} for index in range(25)
    }
    assert media.health_stats(state, now)["verified_bytes"] == media.MAX_VERIFIED_BYTES
    assert media.health_stats(state, now)["capacity"] == "blocked"
    with pytest.raises(DomainError, match="quota_exceeded"):
        media.handle(
            Context(state, state["members"]["child"], now, "deleting-cap"), "reserve", payload
        )


@pytest.mark.parametrize("pending", [17, 18, 19, 20])
def test_household_pending_health_matches_reservations(engine, now, pending):
    state = engine.snapshot()
    payload = capacity_task(state)
    state["media"] = {
        f"M{index:032x}": {
            "status": "available",
            "size_bytes": 100,
            "uploader": f"synthetic-{index}",
        }
        for index in range(pending)
    }
    expected = "blocked" if pending == 20 else "near_limit" if pending >= 18 else "ok"
    assert media.health_stats(state, now)["capacity"] == expected
    ctx = Context(state, state["members"]["child"], now, "pending-cap")
    if pending == 20:
        before = deepcopy(state)
        with pytest.raises(DomainError, match="quota_exceeded"):
            media.handle(ctx, "reserve", payload)
        assert state == before
    else:
        assert media.handle(ctx, "reserve", payload)["status"] == "reserved"


def test_per_member_pending_limit_does_not_claim_household_is_blocked(engine, now):
    state = engine.snapshot()
    payload = capacity_task(state)
    state["media"] = {
        f"M{index:032x}": {"status": "available", "size_bytes": 100, "uploader": "child"}
        for index in range(media.MAX_PENDING_MEMBER)
    }
    assert media.health_stats(state, now)["capacity"] == "ok"
    with pytest.raises(DomainError, match="quota_exceeded"):
        media.handle(
            Context(state, state["members"]["child"], now, "member-cap"), "reserve", payload
        )
    assert (
        media.handle(
            Context(state, state["members"]["parent"], now, "other-member"), "reserve", payload
        )["status"]
        == "reserved"
    )
