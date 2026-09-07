"""Process-local Engine write lease used while an external backup reads files."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)


class RecordingStore:
    def __init__(self):
        self.calls = 0
        self.values = []

    async def save(self, state):
        self.calls += 1
        self.values.append(deepcopy(state))


class GatedStore(RecordingStore):
    def __init__(self, *, fail=False):
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.fail = fail

    async def save(self, state):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise OSError("synthetic persist failure")
        self.values.append(deepcopy(state))


def engine_with(store):
    return Engine(new_state("synthetic-owner", "Backup household"), store.save)


async def add(engine, operation="add"):
    return await engine.execute(
        "owner",
        "shopping.add",
        {"name": f"Item {operation}"},
        operation,
        NOW,
    )


async def domain_error(awaitable, code):
    with pytest.raises(DomainError) as caught:
        await awaitable
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_active_backup_rejects_every_mutation_before_validation_without_writes():
    store = RecordingStore()
    engine = engine_with(store)
    before = engine.snapshot()
    token = await engine.async_begin_backup()
    callback_called = False

    # The fixed gate wins even over otherwise malformed mutation inputs.
    await domain_error(
        engine.execute("missing", "invalid", None, "", datetime.min),
        "backup_in_progress",
    )
    await domain_error(engine.tick(NOW), "backup_in_progress")

    def change(ctx):
        nonlocal callback_called
        callback_called = True
        ctx.state["network"]["forbidden_write"] = True

    await domain_error(
        engine.system_update("synthetic", NOW, change),
        "backup_in_progress",
    )
    assert callback_called is False
    assert store.calls == 0
    assert engine.snapshot() == before
    assert engine.view("owner")["revision"] == before["revision"]
    assert not any(key.startswith("backup") or key.startswith("_backup") for key in before)

    await engine.async_end_backup(token)
    receipt = await add(engine)
    assert receipt["status"] == "approved"
    assert store.calls == 1


@pytest.mark.asyncio
async def test_begin_drains_an_inflight_persist_and_rejects_a_mutation_queued_behind_it():
    store = GatedStore()
    engine = engine_with(store)
    first = asyncio.create_task(add(engine, "first"))
    await asyncio.wait_for(store.entered.wait(), 1)

    begin = asyncio.create_task(engine.async_begin_backup())
    await asyncio.sleep(0)
    queued = asyncio.create_task(add(engine, "queued"))
    await asyncio.sleep(0)
    assert not begin.done()
    assert not queued.done()

    store.release.set()
    first_receipt = await asyncio.wait_for(first, 1)
    token = await asyncio.wait_for(begin, 1)
    await domain_error(queued, "backup_in_progress")

    assert first_receipt["status"] == "approved"
    assert store.calls == 1
    snapshot = engine.snapshot()
    assert [row["name"] for row in snapshot["shopping"].values()] == ["Item first"]
    assert [row["id"] for row in snapshot["audit"]] == ["first"]
    await engine.async_end_backup(token)


@pytest.mark.asyncio
async def test_mutation_already_queued_before_begin_is_part_of_the_successful_drain():
    store = GatedStore()
    engine = engine_with(store)
    active = asyncio.create_task(add(engine, "active"))
    await asyncio.wait_for(store.entered.wait(), 1)
    queued_first = asyncio.create_task(add(engine, "queued-first"))
    await asyncio.sleep(0)
    begin = asyncio.create_task(engine.async_begin_backup())
    await asyncio.sleep(0)

    store.release.set()
    await asyncio.wait_for(active, 1)
    await asyncio.wait_for(queued_first, 1)
    token = await asyncio.wait_for(begin, 1)
    assert store.calls == 2
    assert [row["name"] for row in engine.snapshot()["shopping"].values()] == [
        "Item active",
        "Item queued-first",
    ]
    await engine.async_end_backup(token)


@pytest.mark.asyncio
async def test_failed_inflight_persist_drains_to_the_unchanged_state_before_freeze():
    store = GatedStore(fail=True)
    engine = engine_with(store)
    before = engine.snapshot()
    mutation = asyncio.create_task(add(engine, "fails"))
    await asyncio.wait_for(store.entered.wait(), 1)
    begin = asyncio.create_task(engine.async_begin_backup())
    await asyncio.sleep(0)
    store.release.set()

    with pytest.raises(OSError, match="synthetic persist failure"):
        await mutation
    token = await asyncio.wait_for(begin, 1)
    assert engine.snapshot() == before
    assert store.calls == 1
    await domain_error(add(engine, "blocked"), "backup_in_progress")
    assert store.calls == 1
    await engine.async_end_backup(token)


@pytest.mark.asyncio
async def test_cancelling_begin_while_it_waits_never_strands_a_backup_gate():
    store = GatedStore()
    engine = engine_with(store)
    mutation = asyncio.create_task(add(engine, "drain"))
    await asyncio.wait_for(store.entered.wait(), 1)
    begin = asyncio.create_task(engine.async_begin_backup())
    await asyncio.sleep(0)
    begin.cancel()
    with pytest.raises(asyncio.CancelledError):
        await begin

    store.release.set()
    await asyncio.wait_for(mutation, 1)
    token = await asyncio.wait_for(engine.async_begin_backup(), 1)
    await domain_error(add(engine, "frozen"), "backup_in_progress")
    await engine.async_end_backup(token)
    await add(engine, "after-cancel")
    assert store.calls == 2


@pytest.mark.asyncio
async def test_concurrent_leases_wrong_tokens_and_old_tokens_cannot_unfreeze():
    store = RecordingStore()
    engine = engine_with(store)
    first, second = await asyncio.gather(
        engine.async_begin_backup(),
        engine.async_begin_backup(),
        return_exceptions=True,
    )
    values = [value for value in (first, second) if not isinstance(value, Exception)]
    errors = [value for value in (first, second) if isinstance(value, Exception)]
    assert len(values) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], DomainError) and errors[0].code == "conflict"
    token = values[0]

    await domain_error(engine.async_begin_backup(), "conflict")
    await domain_error(engine.async_end_backup(object()), "conflict")
    await domain_error(add(engine, "still-frozen"), "backup_in_progress")
    await engine.async_end_backup(token)
    await engine.async_end_backup(token)  # The matching release is idempotent.

    next_token = await engine.async_begin_backup()
    await domain_error(engine.async_end_backup(token), "conflict")
    await domain_error(add(engine, "old-token-did-not-clear"), "backup_in_progress")
    await engine.async_end_backup(next_token)


@pytest.mark.asyncio
async def test_backup_lease_is_not_persisted_and_old_token_is_invalid_after_restart():
    first_store = RecordingStore()
    original = engine_with(first_store)
    token = await original.async_begin_backup()
    snapshot = original.snapshot()

    restarted_store = RecordingStore()
    restarted = Engine(snapshot, restarted_store.save)
    await domain_error(restarted.async_end_backup(token), "conflict")
    await add(restarted, "after-restart")
    assert restarted_store.calls == 1
    await domain_error(add(original, "original-frozen"), "backup_in_progress")
    await original.async_end_backup(token)
