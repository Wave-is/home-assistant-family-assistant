"""Engine lifecycle fences keep obsolete runtimes from writing current storage."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain import engine as engine_module
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


class RecordingStore:
    def __init__(self) -> None:
        self.calls = 0
        self.value = None

    async def save(self, state: dict) -> None:
        self.calls += 1
        self.value = deepcopy(state)


class GatedStore(RecordingStore):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.fail = fail

    async def save(self, state: dict) -> None:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise OSError("synthetic persist failure")
        self.value = deepcopy(state)


def make_engine(store: RecordingStore) -> Engine:
    return Engine(new_state("synthetic-owner", "Lifecycle household"), store.save)


async def add(engine: Engine, operation: str, *, guard=None) -> dict:
    return await engine.execute(
        "owner",
        "shopping.add",
        {"name": f"Item {operation}"},
        operation,
        NOW,
        guard=guard,
    )


async def assert_error(awaitable, code: str) -> None:
    with pytest.raises(DomainError) as caught:
        await awaitable
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_execute_guard_reads_latest_locked_state_before_dispatch_and_replay() -> None:
    store = GatedStore()
    engine = make_engine(store)
    first = asyncio.create_task(add(engine, "first"))
    await asyncio.wait_for(store.entered.wait(), 1)

    seen = []

    def reject_after_first(state: dict) -> None:
        seen.append((state["revision"], len(state["shopping"])))
        raise DomainError("conflict")

    queued = asyncio.create_task(add(engine, "queued", guard=reject_after_first))
    await asyncio.sleep(0)
    store.release.set()
    await asyncio.wait_for(first, 1)
    await assert_error(queued, "conflict")

    assert seen == [(1, 1)]
    assert store.calls == 1
    assert [row["id"] for row in engine.snapshot()["audit"]] == ["first"]

    # A cached receipt is authority checked only after the fresh caller guard.
    replay_guard_calls = []

    def reject_replay(state: dict) -> None:
        replay_guard_calls.append(state["revision"])
        raise DomainError("forbidden")

    await assert_error(add(engine, "first", guard=reject_replay), "forbidden")
    assert replay_guard_calls == [1]
    assert store.calls == 1


@pytest.mark.asyncio
async def test_system_guard_is_synchronous_isolated_and_runs_before_change() -> None:
    store = RecordingStore()
    engine = make_engine(store)
    before = engine.snapshot()
    changed = []

    def guard(state: dict) -> None:
        state["settings"]["name"] = "Guard cannot mutate live state"
        raise DomainError("forbidden")

    def change(ctx) -> None:
        changed.append(True)
        ctx.state["settings"]["name"] = "Must not run"

    await assert_error(engine.system_update("guarded", NOW, change, guard=guard), "forbidden")
    assert changed == []
    assert engine.snapshot() == before
    assert store.calls == 0

    async def invalid_async_guard(_state: dict) -> None:
        return None

    await assert_error(
        engine.system_update("async-guard", NOW, change, guard=invalid_async_guard),
        "invalid_field",
    )
    assert changed == []
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_close_drains_active_write_and_rejects_all_queued_and_new_writes() -> None:
    store = GatedStore()
    engine = make_engine(store)
    active = asyncio.create_task(add(engine, "active"))
    await asyncio.wait_for(store.entered.wait(), 1)

    queued_execute = asyncio.create_task(add(engine, "queued"))
    queued_tick = asyncio.create_task(engine.tick(NOW))
    queued_system = asyncio.create_task(
        engine.system_update("queued", NOW, lambda ctx: ctx.state["network"].update(x=1))
    )
    closer = asyncio.create_task(engine.async_close())
    await asyncio.sleep(0)
    assert not closer.done()

    store.release.set()
    receipt = await asyncio.wait_for(active, 1)
    assert receipt["status"] == "approved"
    await asyncio.wait_for(closer, 1)
    for task in (queued_execute, queued_tick, queued_system):
        await assert_error(task, "not_ready")

    committed = engine.snapshot()
    assert committed == store.value
    assert [row["id"] for row in committed["audit"]] == ["active"]
    assert store.calls == 1

    await assert_error(add(engine, "new"), "not_ready")
    await assert_error(engine.tick(datetime.min), "not_ready")
    await assert_error(engine.system_update("new", datetime.min, lambda _ctx: None), "not_ready")
    await assert_error(engine.async_begin_backup(), "not_ready")
    assert engine.view("owner")["revision"] == committed["revision"]


@pytest.mark.asyncio
async def test_close_wakes_backup_waiters_but_matching_token_cannot_reopen() -> None:
    store = RecordingStore()
    engine = make_engine(store)
    token = await engine.async_begin_backup()
    changed = []

    waiting = asyncio.create_task(engine.async_wait_writable())
    background = asyncio.create_task(
        engine.background_update("waiting", NOW, lambda _ctx: changed.append(True))
    )
    await asyncio.sleep(0)
    assert not waiting.done() and not background.done()

    await engine.async_close()
    await assert_error(waiting, "not_ready")
    await assert_error(background, "not_ready")
    assert changed == []
    assert store.calls == 0

    await engine.async_end_backup(token)
    await engine.async_end_backup(token)
    await assert_error(add(engine, "still-closed"), "not_ready")

    restarted_store = RecordingStore()
    restarted = Engine(engine.snapshot(), restarted_store.save)
    assert (await add(restarted, "restart"))["status"] == "approved"
    assert restarted_store.calls == 1


@pytest.mark.asyncio
async def test_cancelled_close_still_drains_and_leaves_engine_permanently_closed() -> None:
    store = GatedStore()
    engine = make_engine(store)
    active = asyncio.create_task(add(engine, "active-close-cancel"))
    await asyncio.wait_for(store.entered.wait(), 1)

    closer = asyncio.create_task(engine.async_close())
    await asyncio.sleep(0)
    closer.cancel()
    await asyncio.sleep(0)
    assert not closer.done()

    store.release.set()
    await asyncio.wait_for(active, 1)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(closer, 1)
    assert engine.snapshot() == store.value
    await assert_error(add(engine, "after-cancelled-close"), "not_ready")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["execute", "system_update", "tick"])
async def test_cancelled_persist_settles_then_publishes_exact_disk_state(
    kind: str, monkeypatch
) -> None:
    store = GatedStore()
    engine = make_engine(store)

    if kind == "execute":
        operation = add(engine, "cancelled-persist")
    elif kind == "system_update":
        operation = engine.system_update(
            "cancelled-persist",
            NOW,
            lambda ctx: ctx.state["network"].update(marker="system"),
        )
    else:
        monkeypatch.setattr(
            engine_module.poll_reviews,
            "prune",
            lambda ctx: ctx.state["network"].update(marker="tick"),
        )
        operation = engine.tick(NOW)

    task = asyncio.create_task(operation)
    await asyncio.wait_for(store.entered.wait(), 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    store.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)

    assert store.value is not None
    assert engine.snapshot() == store.value
    assert engine.snapshot()["revision"] == 1

    if kind == "execute":
        calls = store.calls
        receipt = await add(engine, "cancelled-persist")
        assert receipt["status"] == "approved"
        assert store.calls == calls


@pytest.mark.asyncio
async def test_cancelled_failed_persist_preserves_memory_and_cancellation() -> None:
    store = GatedStore(fail=True)
    engine = make_engine(store)
    before = engine.snapshot()
    task = asyncio.create_task(add(engine, "cancelled-failure"))
    await asyncio.wait_for(store.entered.wait(), 1)

    task.cancel()
    store.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)

    assert store.value is None
    assert engine.snapshot() == before
    assert store.calls == 1


@pytest.mark.asyncio
async def test_close_drains_a_failed_persist_without_publishing_it() -> None:
    store = GatedStore(fail=True)
    engine = make_engine(store)
    before = engine.snapshot()
    active = asyncio.create_task(add(engine, "failed-before-close"))
    await asyncio.wait_for(store.entered.wait(), 1)
    closer = asyncio.create_task(engine.async_close())
    await asyncio.sleep(0)

    store.release.set()
    with pytest.raises(OSError, match="synthetic persist failure"):
        await asyncio.wait_for(active, 1)
    await asyncio.wait_for(closer, 1)
    assert engine.snapshot() == before
    await assert_error(add(engine, "closed-after-failure"), "not_ready")
