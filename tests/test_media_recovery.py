"""Crash recovery, bounded inventory and backup pause tests using real files."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import media, task_access
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.media_recovery import (
    ORPHAN_GRACE_SECONDS,
    SCAN_LIMIT,
    TEMP_GRACE_SECONDS,
    DirectoryInventory,
    remove_abandoned,
)
from custom_components.family_assistant.media_storage import MediaStorage
from tests import test_media_storage as storage_tests

# Reuse the established real Engine/filesystem fixture rather than replacing the
# storage contract with a local mock.
media_env = storage_tests.media_env
allowed = storage_tests.allowed
attach_report = storage_tests.attach_report
chunks = storage_tests.chunks
decode = storage_tests.decode
error_code = storage_tests.error_code
metadata = storage_tests.metadata
mutate = storage_tests.mutate
reserve = storage_tests.reserve
stored_blob = storage_tests.stored_blob


def make_old(path, clock, seconds):
    value = clock().timestamp() - seconds
    if path.is_symlink():
        try:
            os.utime(path, (value, value), follow_symlinks=False)
        except NotImplementedError:
            return False
    else:
        os.utime(path, (value, value))
    return True


async def deleting(engine, clock, media_id, revision):
    def change(ctx):
        ctx.now = clock()
        return media.expire_pending(ctx, media_id, revision)

    return await engine.system_update("test_media_deleting", clock(), change)


@pytest.mark.asyncio
async def test_stale_temp_and_orphan_are_removed_but_fresh_candidates_are_retained(media_env):
    _, _, clock, root = media_env
    root.mkdir()
    stale_temp = root / ".upload-abcdefgh"
    fresh_temp = root / ".upload-ijklmnop"
    stale_blob = root / ("a" * 64)
    fresh_blob = root / ("b" * 64)
    for path in (stale_temp, fresh_temp, stale_blob, fresh_blob):
        path.write_bytes(path.name.encode())
    make_old(stale_temp, clock, TEMP_GRACE_SECONDS + 1)
    make_old(stale_blob, clock, ORPHAN_GRACE_SECONDS + 1)

    inventory = DirectoryInventory(root)
    stamps, complete = inventory.scan()
    assert complete is True
    by_name = {stamp.name: stamp for stamp in stamps}
    assert remove_abandoned(root, by_name[stale_temp.name], clock().timestamp(), set()) is True
    assert remove_abandoned(root, by_name[fresh_temp.name], clock().timestamp(), set()) is False
    assert remove_abandoned(root, by_name[stale_blob.name], clock().timestamp(), set()) is True
    assert remove_abandoned(root, by_name[fresh_blob.name], clock().timestamp(), set()) is False
    assert not stale_temp.exists() and not stale_blob.exists()
    assert fresh_temp.exists() and fresh_blob.exists()


@pytest.mark.asyncio
async def test_recovery_protects_every_referenced_blob_status(media_env):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    available = await reserve(engine, clock)
    attached = await reserve(engine, clock)
    pending_delete = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)

    root.mkdir(exist_ok=True)
    stored_blob(engine, root, reserved["id"]).write_bytes(b"reserved residue")
    await storage.put(
        "synthetic-child", available["id"], 1, chunks(b"available bytes"), guard=allowed
    )
    attached_receipt = await storage.put(
        "synthetic-child", attached["id"], 1, chunks(b"attached bytes"), guard=allowed
    )
    await attach_report(engine, clock, attached["id"], attached_receipt["revision"])
    clock.value += timedelta(hours=1, seconds=1)
    await deleting(engine, clock, pending_delete["id"], pending_delete["revision"])
    stored_blob(engine, root, pending_delete["id"]).write_bytes(b"deleting residue")

    paths = [
        stored_blob(engine, root, receipt["id"]) for receipt in (reserved, available, attached)
    ]
    paths.append(stored_blob(engine, root, pending_delete["id"]))
    for path in paths:
        make_old(path, clock, ORPHAN_GRACE_SECONDS + 1)
    await storage._recover_files()
    assert all(path.exists() for path in paths)
    assert {record["status"] for record in engine.snapshot()["media"].values()} == {
        "reserved",
        "available",
        "attached",
        "deleting",
    }


@pytest.mark.asyncio
async def test_hardlink_publish_crash_removes_only_temp_then_exact_retry_and_expiry(media_env):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    record = engine.snapshot()["media"][reserved["id"]]
    content = b"crash boundary image"
    root.mkdir()
    temporary = root / ".upload-abcdefgh"
    destination = root / record["blob_key"]
    temporary.write_bytes(content)
    os.link(temporary, destination)
    make_old(temporary, clock, TEMP_GRACE_SECONDS + 1)
    make_old(destination, clock, TEMP_GRACE_SECONDS + 1)
    assert temporary.stat().st_nlink == destination.stat().st_nlink == 2

    storage = MediaStorage(engine, root, clock, decoder=decode)
    await storage.collect()
    assert not temporary.exists()
    assert destination.exists() and destination.stat().st_nlink == 1
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "reserved"

    available = await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(content), guard=allowed
    )
    assert available == {"id": reserved["id"], "revision": 2, "status": "available"}
    assert destination.read_bytes() == content
    clock.value += timedelta(hours=24, seconds=1)
    await storage.collect()
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "deleted"
    assert not destination.exists()


@pytest.mark.asyncio
async def test_unknown_symlink_and_external_hardlink_are_retained_with_fixed_failure(
    media_env, tmp_path
):
    engine, _, clock, root = media_env
    root.mkdir()
    unknown = root / "unknown-private-name"
    unknown.write_bytes(b"unknown")
    external = tmp_path / "outside-hardlink-source"
    external.write_bytes(b"external")
    external_link = root / ("c" * 64)
    os.link(external, external_link)
    retained = [unknown, external_link]
    symlink = root / ("d" * 64)
    try:
        symlink.symlink_to(external)
    except OSError:
        symlink = None
    else:
        retained.append(symlink)
    for path in retained:
        make_old(path, clock, ORPHAN_GRACE_SECONDS + 1)

    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as failed:
        await storage.collect()
    assert error_code(failed) == "media_unavailable"
    assert str(root) not in str(failed.value)
    assert unknown.exists() and external_link.exists() and external.exists()
    if symlink is not None:
        assert symlink.is_symlink()


@pytest.mark.asyncio
async def test_large_inventory_advances_in_bounded_batches_until_complete(media_env):
    engine, _, clock, root = media_env
    root.mkdir()
    total = SCAN_LIMIT * 2 + 8
    for index in range(total):
        path = root / f"{index:064x}"
        path.write_bytes(b"orphan")
        make_old(path, clock, ORPHAN_GRACE_SECONDS + 1)
    storage = MediaStorage(engine, root, clock, decoder=decode)

    counts = []
    for _ in range(3):
        await storage.collect()
        counts.append(len(list(root.iterdir())))
    assert counts == [total - SCAN_LIMIT, 8, 0]


def test_changed_after_inventory_scan_is_restat_and_retained(media_env):
    _, _, clock, root = media_env
    root.mkdir()
    candidate = root / ("e" * 64)
    candidate.write_bytes(b"old")
    make_old(candidate, clock, ORPHAN_GRACE_SECONDS + 1)
    inventory = DirectoryInventory(root)
    stamps, complete = inventory.scan()
    assert complete is True and len(stamps) == 1
    candidate.write_bytes(b"changed after scan")

    assert remove_abandoned(root, stamps[0], clock().timestamp(), set()) is False
    assert candidate.read_bytes() == b"changed after scan"


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["corrupt", "missing"])
async def test_attached_historical_damage_keeps_metadata_and_recovers(media_env, damage):
    engine, store, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    content = b"retained historical report"
    available = await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(content), guard=allowed
    )
    await attach_report(engine, clock, reserved["id"], available["revision"])

    def archive(ctx):
        task_access.archive_report(ctx, ctx.state["tasks"]["T000001"], "reassigned_at")

    await engine.system_update("test_archive_report", clock(), archive)
    before = engine.snapshot()
    calls = store.calls
    blob = stored_blob(engine, root, reserved["id"])
    if damage == "corrupt":
        blob.write_bytes(b"corrupt")
    else:
        blob.unlink()

    with pytest.raises(DomainError) as failed:
        await storage.collect()
    assert error_code(failed) == "media_unavailable"
    assert str(root) not in str(failed.value)
    after = engine.snapshot()
    assert after["media"] == before["media"]
    assert (
        after["tasks"]["T000001"]["previous_reports"]
        == before["tasks"]["T000001"]["previous_reports"]
    )
    assert store.calls == calls

    blob.write_bytes(content)
    await storage.collect()
    assert engine.snapshot()["media"] == before["media"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_record",
    [
        {"status": "available", "blob_key": "not-a-key"},
        {"id": "MALFORMED", "status": "reserved", "expires_at": "2000-01-01T00:00:00+00:00"},
        {"id": "MALFORMED", "status": "deleting", "revision": True},
    ],
)
async def test_malformed_metadata_blocks_orphan_guessing_but_not_safe_record_expiry(
    media_env, bad_record
):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    root.mkdir()
    referenced = stored_blob(engine, root, reserved["id"])
    referenced.write_bytes(b"reserved")
    orphan = root / ("f" * 64)
    orphan.write_bytes(b"unowned but not safely guessable")

    def corrupt_inventory(ctx):
        ctx.state["media"]["MALFORMED"] = bad_record

    await mutate(engine, clock, corrupt_inventory)
    clock.value += timedelta(hours=1, seconds=1)
    make_old(orphan, clock, ORPHAN_GRACE_SECONDS + 1)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as failed:
        await storage.collect()
    assert error_code(failed) == "media_unavailable"
    state = engine.snapshot()
    assert state["media"][reserved["id"]]["status"] == "deleted"
    assert not referenced.exists()
    assert orphan.exists()
    assert state["media"]["MALFORMED"] == bad_record


@pytest.mark.asyncio
async def test_backup_pause_drains_inflight_upload_and_denies_new_io(media_env):
    engine, _, clock, root = media_env
    first = await reserve(engine, clock)
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused_decoder(path):
        entered.set()
        await release.wait()
        return metadata(path.read_bytes())

    storage = MediaStorage(engine, root, clock, decoder=paused_decoder)
    upload = asyncio.create_task(
        storage.put("synthetic-child", first["id"], 1, chunks(b"first"), guard=allowed)
    )
    await asyncio.wait_for(entered.wait(), 1)
    pause = asyncio.create_task(storage.async_pause_backup())
    await asyncio.sleep(0)
    assert not pause.done()
    with pytest.raises(DomainError) as blocked:
        await storage.put("synthetic-child", first["id"], 1, chunks(b"not read"), guard=allowed)
    assert error_code(blocked) == "media_unavailable"

    release.set()
    assert (await asyncio.wait_for(upload, 1))["status"] == "available"
    token = await asyncio.wait_for(pause, 1)
    with pytest.raises(DomainError) as frozen_get:
        await storage.get("synthetic-child", first["id"], 2, guard=allowed)
    assert error_code(frozen_get) == "media_unavailable"
    await storage.async_resume_backup(token)
    _, content = await storage.get("synthetic-child", first["id"], 2, guard=allowed)
    assert content == b"first"


@pytest.mark.asyncio
async def test_cancelled_pause_resumes_and_wrong_or_old_token_cannot_thaw_newer_pause(media_env):
    engine, _, clock, root = media_env
    first = await reserve(engine, clock)
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused_decoder(path):
        entered.set()
        await release.wait()
        return metadata(path.read_bytes())

    storage = MediaStorage(engine, root, clock, decoder=paused_decoder)
    upload = asyncio.create_task(
        storage.put("synthetic-child", first["id"], 1, chunks(b"first"), guard=allowed)
    )
    await asyncio.wait_for(entered.wait(), 1)
    cancelled = asyncio.create_task(storage.async_pause_backup())
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    release.set()
    await asyncio.wait_for(upload, 1)

    token = await storage.async_pause_backup()
    with pytest.raises(DomainError) as repeated:
        await storage.async_pause_backup()
    assert error_code(repeated) == "media_unavailable"
    await storage.async_resume_backup(object())
    with pytest.raises(DomainError) as wrong:
        await storage.get("synthetic-child", first["id"], 2, guard=allowed)
    assert error_code(wrong) == "media_unavailable"
    await storage.async_resume_backup(token)

    newer = await storage.async_pause_backup()
    await storage.async_resume_backup(token)
    with pytest.raises(DomainError) as old:
        await storage.get("synthetic-child", first["id"], 2, guard=allowed)
    assert error_code(old) == "media_unavailable"
    await storage.async_resume_backup(newer)
    _, content = await storage.get("synthetic-child", first["id"], 2, guard=allowed)
    assert content == b"first"


@pytest.mark.asyncio
async def test_collect_is_skipped_while_paused_and_storage_remains_stopped(media_env):
    engine, store, clock, root = media_env
    reserved = await reserve(engine, clock)
    clock.value += timedelta(hours=1, seconds=1)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    token = await storage.async_pause_backup()
    calls = store.calls
    await storage.collect()
    assert store.calls == calls
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "reserved"
    await storage.async_resume_backup(token)
    await storage.collect()
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "deleted"

    await storage.stop()
    with pytest.raises(DomainError) as stopped_pause:
        await storage.async_pause_backup()
    assert error_code(stopped_pause) == "media_unavailable"
    await storage.async_resume_backup(object())
    calls = store.calls
    await storage.collect()
    assert store.calls == calls
    with pytest.raises(DomainError) as stopped_put:
        await storage.put("synthetic-child", reserved["id"], 1, chunks(b"never"), guard=allowed)
    assert error_code(stopped_put) == "media_unavailable"
