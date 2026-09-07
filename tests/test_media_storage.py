"""Private blob storage tests using real files and the real media domain."""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from custom_components.family_assistant import media_storage as storage_module
from custom_components.family_assistant.domain import media
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.media_storage import MAX_CHUNK, MAX_IO, MediaStorage


class MemoryStore:
    def __init__(self) -> None:
        self.value = None
        self.fail = False
        self.fail_at = None
        self.calls = 0

    async def save(self, state) -> None:
        self.calls += 1
        if self.fail or self.calls == self.fail_at:
            raise OSError("synthetic private store path")
        self.value = deepcopy(state)


class Clock:
    def __init__(self, now) -> None:
        self.value = now

    def __call__(self):
        return self.value


def error_code(error: pytest.ExceptionInfo[DomainError]) -> str:
    return error.value.code


def metadata(content: bytes, mime_type: str = "image/png") -> dict:
    return {
        "mime_type": mime_type,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "width": 1,
        "height": 1,
    }


async def decode(path: Path) -> dict:
    return metadata(path.read_bytes())


async def chunks(*values):
    for value in values:
        yield value


async def allowed() -> None:
    return None


@pytest.fixture
def media_env(tmp_path, now):
    state = new_state("synthetic-owner", "Synthetic household")
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
    state["media"] = {}
    state["tasks"]["T000001"] = {
        "id": "T000001",
        "revision": 1,
        "status": "assigned",
        "title": "Synthetic private image report",
        "assignee": "child",
        "assignee_revision": 1,
        "creator": "parent",
        "report_type": "photo",
        "report": None,
        "checklist": [],
    }
    store = MemoryStore()
    engine = Engine(state, store.save)
    clock = Clock(now)
    root = tmp_path / "entry-media"
    return engine, store, clock, root


async def reserve(engine, clock, *, actor="child", task_revision=1):
    def change(ctx: Context):
        ctx.actor = ctx.state["members"][actor]
        return media.handle(
            ctx,
            "reserve",
            {
                "purpose": "task_report",
                "task_id": "T000001",
                "task_revision": task_revision,
                "uploader_revision": ctx.actor["revision"],
            },
        )

    return await engine.system_update("test_media_reserve", clock(), change)


async def mutate(engine, clock, change) -> None:
    await engine.system_update("test_media_mutation", clock(), change)


async def attach_report(engine, clock, media_id, revision):
    def change(ctx):
        ctx.actor = ctx.state["members"]["child"]
        return media.attach_task_report(
            ctx,
            ctx.state["tasks"]["T000001"],
            {"id": media_id, "revision": revision},
        )

    return await engine.system_update("test_media_attach", clock(), change)


def stored_blob(engine, root, media_id) -> Path:
    return root / engine.snapshot()["media"][media_id]["blob_key"]


@pytest.mark.asyncio
async def test_success_get_exact_replay_and_wrong_body_never_overwrites(media_env):
    engine, _, clock, root = media_env
    receipt = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    content = b"synthetic verified image bytes"

    available = await storage.put(
        "synthetic-child", receipt["id"], receipt["revision"], chunks(content), guard=allowed
    )
    assert available == {"id": receipt["id"], "revision": 2, "status": "available"}
    blob = stored_blob(engine, root, receipt["id"])
    assert blob.read_bytes() == content
    assert [path for path in root.iterdir() if not path.name.startswith(".upload-")] == [blob]

    projected, downloaded = await storage.get(
        "synthetic-child", receipt["id"], available["revision"], guard=allowed
    )
    assert downloaded == content
    assert projected == {
        "id": receipt["id"],
        "revision": 2,
        "purpose": "task_report",
        "mime_type": "image/png",
        "size_bytes": len(content),
        "status": "available",
    }
    assert (
        await storage.put(
            "synthetic-child", receipt["id"], receipt["revision"], chunks(content), guard=allowed
        )
        == available
    )

    with pytest.raises(DomainError) as wrong:
        await storage.put(
            "synthetic-child",
            receipt["id"],
            receipt["revision"],
            chunks(b"different verified bytes"),
            guard=allowed,
        )
    assert error_code(wrong) == "conflict"
    assert blob.read_bytes() == content
    assert not any(path.name.startswith(".upload-") for path in root.iterdir())


@pytest.mark.asyncio
async def test_store_failure_after_publish_is_recoverable_by_exact_retry(media_env):
    engine, store, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    content = b"recoverable image"
    store.fail = True
    with pytest.raises(DomainError) as failed:
        await storage.put("synthetic-child", reserved["id"], 1, chunks(content), guard=allowed)
    assert error_code(failed) == "media_unavailable"
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "reserved"
    assert stored_blob(engine, root, reserved["id"]).read_bytes() == content

    store.fail = False
    assert await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(content), guard=allowed
    ) == {"id": reserved["id"], "revision": 2, "status": "available"}
    assert stored_blob(engine, root, reserved["id"]).read_bytes() == content


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", ["uploader", "task"])
async def test_stale_authority_before_put_has_no_file_side_effect(media_env, subject):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)

    def change(ctx):
        record = (
            ctx.state["members"]["child"]
            if subject == "uploader"
            else ctx.state["tasks"]["T000001"]
        )
        record["revision"] += 1

    await mutate(engine, clock, change)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as denied:
        await storage.put(
            "synthetic-child", reserved["id"], 1, chunks(b"never stored"), guard=allowed
        )
    assert error_code(denied) in {"forbidden", "conflict"}
    assert not root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(("subject", "code"), (("uploader", "forbidden"), ("task", "conflict")))
async def test_authority_change_during_stream_cleans_temporary(media_env, subject, code):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)

    async def changing_chunks():
        yield b"first"

        def change(ctx):
            record = (
                ctx.state["members"]["child"]
                if subject == "uploader"
                else ctx.state["tasks"]["T000001"]
            )
            record["revision"] += 1

        await mutate(engine, clock, change)
        yield b"second"

    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as denied:
        await storage.put("synthetic-child", reserved["id"], 1, changing_chunks(), guard=allowed)
    assert error_code(denied) == code
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("subject", "code"), (("uploader", "forbidden"), ("task", "conflict")))
async def test_authority_change_during_decoder_cleans_temporary(media_env, subject, code):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused_decoder(path):
        entered.set()
        await release.wait()
        return metadata(path.read_bytes())

    storage = MediaStorage(engine, root, clock, decoder=paused_decoder)
    pending = asyncio.create_task(
        storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    )
    await entered.wait()

    def change(ctx):
        record = (
            ctx.state["members"]["child"]
            if subject == "uploader"
            else ctx.state["tasks"]["T000001"]
        )
        record["revision"] += 1

    await mutate(engine, clock, change)
    release.set()
    with pytest.raises(DomainError) as denied:
        await pending
    assert error_code(denied) == code
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_guard_revocation_after_publish_retains_exact_recoverable_blob(media_env):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    calls = 0

    async def guard():
        nonlocal calls
        calls += 1
        if calls == 4:
            raise DomainError("forbidden")

    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as denied:
        await storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=guard)
    assert error_code(denied) == "forbidden"
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "reserved"
    assert stored_blob(engine, root, reserved["id"]).read_bytes() == b"image"
    assert await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed
    ) == {"id": reserved["id"], "revision": 2, "status": "available"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("subject", "code"), (("uploader", "forbidden"), ("task", "conflict")))
async def test_get_rechecks_guard_and_identity_after_read(media_env, subject, code):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    available = await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(b"private image"), guard=allowed
    )
    calls = 0

    async def revoke_after_read():
        nonlocal calls
        calls += 1
        if calls == 2:

            def change(ctx):
                record = (
                    ctx.state["members"]["child"]
                    if subject == "uploader"
                    else ctx.state["tasks"]["T000001"]
                )
                record["revision"] += 1

            await mutate(engine, clock, change)

    with pytest.raises(DomainError) as denied:
        await storage.get(
            "synthetic-child", reserved["id"], available["revision"], guard=revoke_after_read
        )
    assert error_code(denied) == code


@pytest.mark.asyncio
async def test_cross_actor_entry_root_and_invalid_blob_key_are_denied(media_env, tmp_path):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    available = await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(b"private image"), guard=allowed
    )
    for user in ("synthetic-sibling", "unknown-ha-user"):
        with pytest.raises(DomainError) as denied:
            await storage.get(user, reserved["id"], available["revision"], guard=allowed)
        assert error_code(denied) == "forbidden"

    wrong_root = MediaStorage(engine, tmp_path / "different-entry", clock, decoder=decode)
    with pytest.raises(DomainError) as absent:
        await wrong_root.get(
            "synthetic-child", reserved["id"], available["revision"], guard=allowed
        )
    assert error_code(absent) == "media_unavailable"

    other_state = new_state("other-owner", "Other household")
    other_engine = Engine(other_state, MemoryStore().save)
    other = MediaStorage(other_engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as cross_entry:
        await other.get("other-owner", reserved["id"], available["revision"], guard=allowed)
    assert error_code(cross_entry) == "forbidden"

    def corrupt_key(ctx):
        ctx.state["media"][reserved["id"]]["blob_key"] = "../private-image"

    await mutate(engine, clock, corrupt_key)
    with pytest.raises(DomainError) as escaped:
        await storage.get("synthetic-child", reserved["id"], available["revision"], guard=allowed)
    assert error_code(escaped) in {"invalid_field", "media_unavailable"}


@pytest.mark.asyncio
async def test_root_escape_and_linked_blob_are_denied(media_env, tmp_path, monkeypatch):
    engine, _, clock, _ = media_env
    reserved = await reserve(engine, clock)
    escaped_root = tmp_path / "private" / ".." / "escaped"
    storage = MediaStorage(engine, escaped_root, clock, decoder=decode)
    with pytest.raises(DomainError) as escaped:
        await storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    assert error_code(escaped) == "media_unavailable"
    assert not (tmp_path / "escaped").exists()

    safe_root = tmp_path / "safe-entry"
    safe = MediaStorage(engine, safe_root, clock, decoder=decode)
    available = await safe.put(
        "synthetic-child", reserved["id"], 1, chunks(b"private image"), guard=allowed
    )
    blob = stored_blob(engine, safe_root, reserved["id"])
    outside = tmp_path / "outside-private-image"
    blob.replace(outside)
    os.link(outside, blob)
    with pytest.raises(DomainError) as linked:
        await safe.get("synthetic-child", reserved["id"], available["revision"], guard=allowed)
    assert error_code(linked) == "media_unavailable"

    monkeypatch.setattr(Path, "is_symlink", lambda path: path == blob)
    with pytest.raises(DomainError) as symlinked:
        await safe.get("synthetic-child", reserved["id"], available["revision"], guard=allowed)
    assert error_code(symlinked) == "media_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", [None, True, False, 0, -1, 1.0, "1", 2**53])
async def test_invalid_revisions_do_not_create_files(media_env, revision):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as invalid:
        await storage.put(
            "synthetic-child", reserved["id"], revision, chunks(b"image"), guard=allowed
        )
    assert error_code(invalid) == "invalid_field"
    assert not root.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("values", "code"),
    [
        ((), "media_invalid"),
        ((b"x" * (MAX_CHUNK + 1),), "media_invalid"),
        ((bytearray(b"not bytes"),), "media_invalid"),
        ((b"x" * MAX_CHUNK,) * 40 + (b"x",), "media_too_large"),
    ],
)
async def test_zero_bad_chunk_and_oversize_cleanup(media_env, values, code):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as invalid:
        await storage.put("synthetic-child", reserved["id"], 1, chunks(*values), guard=allowed)
    assert error_code(invalid) == code
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_busy_same_media_and_global_concurrency_limit(media_env):
    engine, _, clock, root = media_env
    reservations = [await reserve(engine, clock) for _ in range(MAX_IO + 1)]
    entered = [asyncio.Event() for _ in range(MAX_IO)]
    release = asyncio.Event()
    decoder_calls = 0

    async def paused(path):
        nonlocal decoder_calls
        index = decoder_calls
        decoder_calls += 1
        entered[index].set()
        await release.wait()
        return metadata(path.read_bytes())

    storage = MediaStorage(engine, root, clock, decoder=paused)
    active = [
        asyncio.create_task(
            storage.put(
                "synthetic-child",
                reservation["id"],
                1,
                chunks(f"image-{index}".encode()),
                guard=allowed,
            )
        )
        for index, reservation in enumerate(reservations[:MAX_IO])
    ]
    await asyncio.gather(*(event.wait() for event in entered))
    with pytest.raises(DomainError) as same:
        await storage.put(
            "synthetic-child", reservations[0]["id"], 1, chunks(b"same"), guard=allowed
        )
    assert error_code(same) == "media_unavailable"
    with pytest.raises(DomainError) as global_limit:
        await storage.put(
            "synthetic-child", reservations[-1]["id"], 1, chunks(b"third"), guard=allowed
        )
    assert error_code(global_limit) == "media_unavailable"
    release.set()
    assert all(result["status"] == "available" for result in await asyncio.gather(*active))


@pytest.mark.asyncio
async def test_corrupted_blob_is_never_returned(media_env):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    available = await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(b"original image"), guard=allowed
    )
    blob = stored_blob(engine, root, reserved["id"])
    blob.write_bytes(b"corrupt image")
    with pytest.raises(DomainError) as corrupt:
        await storage.get("synthetic-child", reserved["id"], available["revision"], guard=allowed)
    assert error_code(corrupt) == "media_unavailable"


@pytest.mark.asyncio
async def test_cancelled_put_cleans_temp_and_releases_capacity(media_env):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    entered = asyncio.Event()

    async def paused(_path):
        entered.set()
        await asyncio.Event().wait()

    storage = MediaStorage(engine, root, clock, decoder=paused)
    pending = asyncio.create_task(
        storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    )
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert storage._active == 0
    assert storage._busy == set()
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_cancellation_waits_for_inflight_file_thread_before_cleanup(media_env, monkeypatch):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    entered, release = threading.Event(), threading.Event()
    original_sync = storage_module._sync_close
    original_cleanup = storage_module._cleanup

    def blocked_sync(stream):
        entered.set()
        assert release.wait(2)
        original_sync(stream)

    def ordered_cleanup(stream, path):
        assert release.is_set(), "cleanup raced the active file worker"
        original_cleanup(stream, path)

    monkeypatch.setattr(storage_module, "_sync_close", blocked_sync)
    monkeypatch.setattr(storage_module, "_cleanup", ordered_cleanup)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    pending = asyncio.create_task(
        storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    )
    assert await asyncio.to_thread(entered.wait, 1)
    pending.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert storage._active == 0
    assert storage._busy == set()
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_stop_drains_active_operation_and_rejects_new_work(media_env):
    engine, _, clock, root = media_env
    first, second = await reserve(engine, clock), await reserve(engine, clock)
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused(path):
        entered.set()
        await release.wait()
        return metadata(path.read_bytes())

    storage = MediaStorage(engine, root, clock, decoder=paused)
    active = asyncio.create_task(
        storage.put("synthetic-child", first["id"], 1, chunks(b"image"), guard=allowed)
    )
    await entered.wait()
    stopping = asyncio.create_task(storage.stop())
    await asyncio.sleep(0)
    assert not stopping.done()
    with pytest.raises(DomainError) as stopped:
        await storage.put("synthetic-child", second["id"], 1, chunks(b"other"), guard=allowed)
    assert error_code(stopped) == "media_unavailable"
    release.set()
    with pytest.raises(DomainError) as interrupted:
        await active
    assert error_code(interrupted) == "media_unavailable"
    await asyncio.wait_for(stopping, 1)
    assert list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_decoder_and_cleanup_os_errors_are_code_only(media_env, monkeypatch):
    engine, _, clock, root = media_env
    first = await reserve(engine, clock)

    async def broken_decoder(path):
        raise OSError(f"synthetic decoder path {path}")

    storage = MediaStorage(engine, root, clock, decoder=broken_decoder)
    with pytest.raises(DomainError) as decoder_error:
        await storage.put("synthetic-child", first["id"], 1, chunks(b"image"), guard=allowed)
    assert error_code(decoder_error) == "media_unavailable"
    assert str(root) not in str(decoder_error.value)

    second = await reserve(engine, clock)

    def broken_cleanup(_stream, path):
        raise OSError(f"synthetic cleanup path {path}")

    monkeypatch.setattr(storage_module, "_cleanup", broken_cleanup)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    with pytest.raises(DomainError) as cleanup_error:
        await storage.put("synthetic-child", second["id"], 1, chunks(b"image"), guard=allowed)
    assert error_code(cleanup_error) == "media_unavailable"
    assert str(root) not in str(cleanup_error.value)


@pytest.mark.asyncio
async def test_available_expiry_and_guard_error_do_not_leak_paths(media_env):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)

    async def private_guard():
        raise OSError(f"private entry path {root}")

    with pytest.raises(DomainError) as denied:
        await storage.put(
            "synthetic-child", reserved["id"], 1, chunks(b"image"), guard=private_guard
        )
    assert error_code(denied) == "media_unavailable"
    assert str(root) not in str(denied.value)

    clock.value += timedelta(hours=1, seconds=1)
    with pytest.raises(DomainError) as expired:
        await storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    assert error_code(expired) == "forbidden"
    assert not root.exists()


@pytest.mark.asyncio
async def test_collect_expired_reserved_without_file_to_content_free_tombstone(media_env):
    engine, store, clock, root = media_env
    reserved = await reserve(engine, clock)
    clock.value += timedelta(hours=1, seconds=1)
    storage = MediaStorage(engine, root, clock, decoder=decode)

    await storage.collect()
    record = engine.snapshot()["media"][reserved["id"]]
    assert record["status"] == "deleted" and record["revision"] == 3
    assert set(record) == {
        "id",
        "revision",
        "status",
        "created_at",
        "updated_at",
        "deleted_at",
    }
    assert not root.exists()
    calls = store.calls
    await storage.collect()
    assert store.calls == calls
    assert engine.snapshot()["media"][reserved["id"]] == record


@pytest.mark.asyncio
async def test_collect_expired_available_unlinks_blob_but_retains_attached(media_env):
    engine, store, clock, root = media_env
    expiring = await reserve(engine, clock)
    retained = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    expiring_available = await storage.put(
        "synthetic-child", expiring["id"], 1, chunks(b"expiring"), guard=allowed
    )
    retained_available = await storage.put(
        "synthetic-child", retained["id"], 1, chunks(b"retained"), guard=allowed
    )
    attached = await attach_report(engine, clock, retained["id"], retained_available["revision"])
    expiring_blob = stored_blob(engine, root, expiring["id"])
    retained_blob = stored_blob(engine, root, retained["id"])
    clock.value += timedelta(hours=24, seconds=1)

    await storage.collect()
    state = engine.snapshot()
    assert state["media"][expiring["id"]]["status"] == "deleted"
    assert state["media"][expiring["id"]]["revision"] == expiring_available["revision"] + 2
    assert not expiring_blob.exists()
    assert state["media"][retained["id"]]["status"] == "attached"
    assert state["media"][retained["id"]]["revision"] == attached["revision"]
    assert retained_blob.read_bytes() == b"retained"
    calls = store.calls
    await storage.collect()
    assert store.calls == calls


@pytest.mark.asyncio
async def test_collect_begin_store_failure_never_unlinks_available_blob(media_env):
    engine, store, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    await storage.put(
        "synthetic-child", reserved["id"], 1, chunks(b"persisted image"), guard=allowed
    )
    blob = stored_blob(engine, root, reserved["id"])
    clock.value += timedelta(hours=24, seconds=1)
    store.fail = True

    with pytest.raises(DomainError) as failed:
        await storage.collect()
    assert error_code(failed) == "media_unavailable"
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "available"
    assert blob.read_bytes() == b"persisted image"
    store.fail = False
    await storage.collect()
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "deleted"
    assert not blob.exists()


@pytest.mark.asyncio
async def test_collect_unlink_failure_stays_deleting_and_retries_code_only(media_env, monkeypatch):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    await storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    blob = stored_blob(engine, root, reserved["id"])
    clock.value += timedelta(hours=24, seconds=1)
    original_unlink = storage_module._unlink_blob

    def fail_unlink(_root, _key):
        raise OSError(f"synthetic private unlink {blob}")

    monkeypatch.setattr(storage_module, "_unlink_blob", fail_unlink)
    with pytest.raises(DomainError) as failed:
        await storage.collect()
    assert error_code(failed) == "media_unavailable"
    assert str(blob) not in str(failed.value)
    deleting = engine.snapshot()["media"][reserved["id"]]
    assert deleting["status"] == "deleting" and deleting["revision"] == 3
    assert blob.exists()

    monkeypatch.setattr(storage_module, "_unlink_blob", original_unlink)
    await storage.collect()
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "deleted"
    assert not blob.exists()


@pytest.mark.asyncio
async def test_collect_finish_store_failure_resumes_after_already_missing_blob(media_env):
    engine, store, clock, root = media_env
    reserved = await reserve(engine, clock)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    await storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    blob = stored_blob(engine, root, reserved["id"])
    clock.value += timedelta(hours=24, seconds=1)
    store.fail_at = store.calls + 2

    with pytest.raises(DomainError) as failed:
        await storage.collect()
    assert error_code(failed) == "media_unavailable"
    assert not blob.exists()
    deleting = engine.snapshot()["media"][reserved["id"]]
    assert deleting["status"] == "deleting" and deleting["revision"] == 3

    store.fail_at = None
    await storage.collect()
    deleted = engine.snapshot()["media"][reserved["id"]]
    assert deleted["status"] == "deleted" and deleted["revision"] == 4
    assert "blob_key" not in deleted and "sha256" not in deleted


@pytest.mark.asyncio
async def test_collect_skips_busy_upload_then_expires_it_after_cleanup(media_env):
    engine, _, clock, root = media_env
    reserved = await reserve(engine, clock)
    entered, release = asyncio.Event(), asyncio.Event()

    async def paused(path):
        entered.set()
        await release.wait()
        return metadata(path.read_bytes())

    storage = MediaStorage(engine, root, clock, decoder=paused)
    upload = asyncio.create_task(
        storage.put("synthetic-child", reserved["id"], 1, chunks(b"image"), guard=allowed)
    )
    await entered.wait()
    clock.value += timedelta(hours=1, seconds=1)
    await storage.collect()
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "reserved"
    assert reserved["id"] in storage._busy

    release.set()
    with pytest.raises(DomainError) as expired_upload:
        await upload
    assert error_code(expired_upload) == "forbidden"
    assert storage._busy == set()
    await storage.collect()
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "deleted"
    assert not root.exists() or list(root.iterdir()) == []


@pytest.mark.asyncio
async def test_collect_after_stop_is_a_noop(media_env):
    engine, store, clock, root = media_env
    reserved = await reserve(engine, clock)
    clock.value += timedelta(hours=1, seconds=1)
    storage = MediaStorage(engine, root, clock, decoder=decode)
    await storage.stop()
    calls = store.calls
    await storage.collect()
    assert store.calls == calls
    assert engine.snapshot()["media"][reserved["id"]]["status"] == "reserved"
    assert not root.exists()
