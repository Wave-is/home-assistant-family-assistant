"""Engine integration for the non-configurable private media namespace."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.const import SCHEMA_VERSION
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError


async def photo_task(engine, now, *, operation="create-photo"):
    return await engine.execute(
        "parent",
        "tasks.create",
        {
            "title": "Synthetic private photo report",
            "assignee": "child",
            "report_type": "photo",
        },
        operation,
        now,
    )


def reservation_payload(engine, task):
    child = engine.snapshot()["members"]["child"]
    return {
        "purpose": "task_report",
        "task_id": task["id"],
        "task_revision": task["revision"],
        "uploader_revision": child["revision"],
    }


@pytest.mark.asyncio
async def test_media_reserve_is_engine_routed_without_a_media_module_flag(engine, store, now):
    task = await photo_task(engine, now)
    payload = reservation_payload(engine, task)
    before = engine.snapshot()

    result = await engine.execute("child", "media.reserve", payload, "reserve-media", now)

    assert result == {"id": result["id"], "revision": 1, "status": "reserved"}
    after = engine.snapshot()
    assert "media" not in after["settings"]["modules"]
    assert list(after["media"]) == [result["id"]]
    assert after["revision"] == before["revision"] + 1
    assert after["audit"][-1]["result"] == result
    assert after["processed"]["reserve-media"]["result"] == result
    assert "blob_key" not in repr(result) and "sha256" not in repr(result)
    assert "media" not in engine.view("parent")


def test_new_and_loaded_state_prepare_media_additively_without_schema_migration(store):
    fresh = new_state("synthetic-owner", "Synthetic household")
    assert fresh["media"] == {}
    assert fresh["schema_version"] == SCHEMA_VERSION

    old = deepcopy(fresh)
    old.pop("media")
    old["future_public_extension"] = {"kept": [1, 2, 3]}
    original = deepcopy(old)
    engine = Engine(old, store.save)

    assert "media" not in old and old == original
    assert engine.snapshot()["media"] == {}
    assert engine.snapshot()["future_public_extension"] == {"kept": [1, 2, 3]}
    assert engine.snapshot()["schema_version"] == SCHEMA_VERSION
    assert store.calls == 0


def test_existing_media_and_unknown_keys_are_preserved_on_load(store):
    state = new_state("synthetic-owner", "Synthetic household")
    state["media"] = {"Msynthetic": {"opaque_future_record": True}}
    state["unknown_top_level"] = "preserved"
    engine = Engine(state, store.save)
    assert engine.snapshot()["media"] == state["media"]
    assert engine.snapshot()["unknown_top_level"] == "preserved"


@pytest.mark.asyncio
async def test_exact_reserve_replay_is_stable_and_does_not_write(engine, store, now):
    task = await photo_task(engine, now)
    payload = reservation_payload(engine, task)
    first = await engine.execute("child", "media.reserve", payload, "reserve-replay", now)
    snapshot = engine.snapshot()
    calls = store.calls

    replay = await engine.execute("child", "media.reserve", payload, "reserve-replay", now)

    assert replay == first
    assert engine.snapshot() == snapshot
    assert store.calls == calls
    assert len(engine.snapshot()["media"]) == 1


@pytest.mark.asyncio
async def test_batch_reserve_uses_same_replay_authority_and_opaque_receipt(engine, store, now):
    task = await photo_task(engine, now)
    command = {"action": "media.reserve", "payload": reservation_payload(engine, task)}
    payload = {"commands": [command]}
    first = await engine.execute("child", "batch", payload, "batch-reserve", now)
    snapshot = engine.snapshot()
    calls = store.calls

    assert set(first["items"][0]) == {"id", "revision", "status"}
    assert await engine.execute("child", "batch", payload, "batch-reserve", now) == first
    assert engine.snapshot() == snapshot
    assert store.calls == calls


@pytest.mark.asyncio
async def test_store_failure_rolls_back_reservation_and_retry_is_safe(engine, store, now):
    task = await photo_task(engine, now)
    payload = reservation_payload(engine, task)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("child", "media.reserve", payload, "failed-reserve", now)
    assert engine.snapshot() == before

    store.fail = False
    result = await engine.execute("child", "media.reserve", payload, "failed-reserve", now)
    assert result["status"] == "reserved"
    assert len(engine.snapshot()["media"]) == 1


@pytest.mark.asyncio
async def test_replay_rechecks_uploader_epoch_without_returning_cached_receipt(engine, now):
    task = await photo_task(engine, now)
    payload = reservation_payload(engine, task)
    await engine.execute("child", "media.reserve", payload, "epoch-reserve", now)
    member = engine.snapshot()["members"]["child"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": member["revision"],
            "name": "Rebound child",
            "role": "child",
            "language": member["language"],
            "aliases": member["aliases"],
            "ha_user_id": member.get("ha_user_id"),
            "active": True,
        },
        "change-child-epoch",
        now,
    )
    snapshot = engine.snapshot()

    with pytest.raises(DomainError, match="conflict"):
        await engine.execute("child", "media.reserve", payload, "epoch-reserve", now)
    assert engine.snapshot() == snapshot


@pytest.mark.asyncio
async def test_replay_rechecks_task_revision_and_tasks_module(engine, store, now):
    task = await photo_task(engine, now)
    payload = reservation_payload(engine, task)
    await engine.execute("child", "media.reserve", payload, "task-reserve", now)
    await engine.execute(
        "child",
        "tasks.start",
        {"id": task["id"], "revision": task["revision"]},
        "advance-task",
        now,
    )
    snapshot = engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute("child", "media.reserve", payload, "task-reserve", now)
    assert engine.snapshot() == snapshot

    disabled = engine.snapshot()
    disabled["settings"]["modules"] = [
        module for module in disabled["settings"]["modules"] if module != "tasks"
    ]
    restarted = Engine(disabled, store.save)
    with pytest.raises(DomainError, match="module_disabled"):
        await restarted.execute("child", "media.reserve", payload, "task-reserve", now)


@pytest.mark.asyncio
async def test_only_reserve_is_externally_routed_and_payload_is_exact(engine, now):
    task = await photo_task(engine, now)
    payload = reservation_payload(engine, task)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="unknown_action"):
        await engine.execute("child", "media.finalize", payload, "forged-finalize", now)
    assert engine.snapshot() == before
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "child",
            "media.reserve",
            {**payload, "blob_key": "chosen-by-client"},
            "forged-blob-key",
            now,
        )
    assert engine.snapshot() == before


def test_wrong_schema_is_still_rejected_instead_of_silently_prepared(store):
    state = new_state("synthetic-owner", "Synthetic household")
    state.pop("media")
    state["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(DomainError, match="unsupported_schema"):
        Engine(state, store.save)
