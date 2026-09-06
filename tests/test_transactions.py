"""Persistence failures, retries, concurrency and authorization boundaries."""

import asyncio
import json
from copy import deepcopy
from datetime import datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def test_success_only_after_persist_and_retry_after_restart(engine, store, now):
    payload = {"name": "Milk", "quantity": 2, "unit": "l"}
    result = await engine.execute("parent", "shopping.add", payload, "update-1", now)
    restored = Engine(json.loads(json.dumps(store.value)), store.save)
    repeated = await restored.execute("parent", "shopping.add", payload, "update-1", now)
    assert result == repeated
    assert len(restored.snapshot()["shopping"]) == 1
    assert store.calls == 1


async def test_storage_failure_is_atomic_and_retry_works(engine, store, now):
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("child", "shopping.add", {"name": "Pear"}, "fail", now)
    assert engine.snapshot() == before  # includes sequence, outbox, audit and dedup keys
    store.fail = False
    result = await engine.execute("child", "shopping.add", {"name": "Pear"}, "fail", now)
    assert result["id"] == "S000001"
    assert len(engine.snapshot()["outbox"]) == 1


async def test_concurrent_redelivery_does_not_duplicate(engine, store, now):
    results = await asyncio.gather(
        *[
            engine.execute("child", "shopping.add", {"name": "Bread"}, "same", now)
            for _ in range(25)
        ]
    )
    assert all(result == results[0] for result in results)
    assert store.calls == 1
    assert len(engine.snapshot()["audit"]) == 1


async def test_key_collision_not_treated_as_success(engine, now):
    await engine.execute("parent", "shopping.add", {"name": "Bread"}, "collision", now)
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await engine.execute("parent", "shopping.add", {"name": "Milk"}, "collision", now)


async def test_return_values_and_journal_cannot_mutate_store(engine, now):
    item = await engine.execute("parent", "shopping.add", {"name": "Bread"}, "add", now)
    item["name"] = "tampered"
    snapshot = engine.snapshot()
    snapshot["shopping"][item["id"]]["name"] = "also tampered"
    await engine.execute(
        "parent", "shopping.purchase", {"id": item["id"], "revision": item["revision"]}, "buy", now
    )
    persisted = engine.snapshot()
    assert persisted["shopping"][item["id"]]["name"] == "Bread"
    assert persisted["audit"][0]["result"]["status"] == "approved"


async def test_failed_batch_creates_nothing(engine, store, now):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="unknown_member"):
        await engine.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "tasks.create", "payload": {"title": "Sweep", "assignee": "child"}},
                    {
                        "action": "tasks.create",
                        "payload": {"title": "Water", "assignee": "missing"},
                    },
                ]
            },
            "batch",
            now,
        )
    assert engine.snapshot() == before
    assert store.calls == 0


async def test_optimistic_revision_prevents_lost_changes(engine, now):
    item = await engine.execute("parent", "shopping.add", {"name": "Bread"}, "a", now)
    await engine.execute("parent", "shopping.purchase", {"id": item["id"], "revision": 1}, "b", now)
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent", "shopping.archive", {"id": item["id"], "revision": 1}, "c", now
        )


@pytest.mark.parametrize("actor", ["unknown", "_system", ""])
async def test_unknown_actor_cannot_claim_parent_role(engine, actor, now):
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            actor, "court.award", {"member": "child", "points": 1, "reason": "test"}, "a", now
        )


async def test_role_payload_cannot_elevate_child(engine, now):
    with pytest.raises(DomainError):
        await engine.execute("child", "shopping.add", {"name": "Book", "role": "parent"}, "a", now)
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child",
            "members.save",
            {
                "name": "Child",
                "role": "owner",
                "id": "child",
                "revision": engine.snapshot()["members"]["child"]["revision"],
            },
            "b",
            now,
        )


async def test_revoked_identity_cannot_retry_old_success(engine, store, now):
    await engine.execute("parent", "shopping.add", {"name": "Bread"}, "a", now)
    state = deepcopy(store.value)
    state["members"]["parent"]["active"] = False
    restored = Engine(state, store.save)
    with pytest.raises(DomainError, match="forbidden"):
        await restored.execute("parent", "shopping.add", {"name": "Bread"}, "a", now)


async def test_naive_clock_and_nonfinite_payload_rejected(engine, now):
    with pytest.raises(DomainError):
        await engine.execute("parent", "shopping.add", {"name": "A"}, "a", datetime(2026, 1, 1))
    with pytest.raises(DomainError):
        await engine.execute(
            "parent", "shopping.add", {"name": "A", "quantity": float("nan")}, "a", now
        )


async def test_different_households_do_not_share_data(engine, store, now):
    second = Engine(engine.snapshot(), store.save)
    await engine.execute("parent", "shopping.add", {"name": "Private item"}, "a", now)
    assert second.view("parent")["shopping"] == []
