"""Pantry transactions, receipts and projections through the actual shared engine."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def stocked(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"].append("pantry")
    return Engine(state, store.save)


async def add(engine, now):
    return await engine.execute(
        "parent",
        "pantry.item_save",
        {
            "name": "Synthetic milk",
            "unit": "l",
            "quantity": 0.5,
            "minimum_quantity": 2,
            "note": "Synthetic private parent note",
            "expires_on": "2026-09-07",
        },
        "pantry-item",
        now,
    )


@pytest.mark.asyncio
async def test_tick_acceptance_disk_failure_restart_and_exact_replay(stocked, store, now):
    item = await add(stocked, now)
    assert await stocked.tick(now)
    proposal = stocked.view("parent", now=now)["pantry"]["suggestions"][0]
    assert proposal["quantity"] == 1.5
    assert not await stocked.tick(now)
    assert stocked.snapshot()["shopping"] == {} and stocked.snapshot()["outbox"] == {}
    payload = {"id": proposal["id"], "revision": proposal["revision"]}
    before = stocked.snapshot()
    persisted = deepcopy(store.value)
    store.fail = True
    with pytest.raises(OSError):
        await stocked.execute("parent", "pantry.suggestion_accept", payload, "accept", now)
    assert stocked.snapshot() == before and store.value == persisted
    store.fail = False
    result = await stocked.execute("parent", "pantry.suggestion_accept", payload, "accept", now)
    restarted = Engine(deepcopy(store.value), store.save)
    writes = store.calls
    assert (
        await restarted.execute("parent", "pantry.suggestion_accept", payload, "accept", now)
        == result
    )
    assert store.calls == writes
    shopping = restarted.snapshot()["shopping"]
    assert len(shopping) == 1
    purchase = shopping[result["shopping_id"]]
    assert purchase["pantry_id"] == item["id"] and purchase["quantity"] == 1.5
    assert purchase["status"] == "approved" and purchase["purchased"] == 0
    assert purchase["note"] == ""
    assert "Synthetic private parent note" not in str(restarted.view("child", now=now))
    assert restarted.snapshot()["pantry"]["items"][item["id"]]["quantity"] == 0.5


@pytest.mark.asyncio
async def test_atomic_batch_rolls_back_stock_and_proposals(stocked, store, now):
    item = await add(stocked, now)
    await stocked.tick(now)
    before, writes = stocked.snapshot(), store.calls
    with pytest.raises(DomainError):
        await stocked.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {
                        "action": "pantry.stock_set",
                        "payload": {
                            "id": item["id"],
                            "revision": item["revision"],
                            "quantity": 1,
                            "reason": "Counted",
                        },
                    },
                    {
                        "action": "pantry.item_save",
                        "payload": {
                            "name": "Invalid",
                            "unit": "pcs",
                            "quantity": True,
                            "minimum_quantity": 1,
                        },
                    },
                ]
            },
            "batch",
            now,
        )
    assert stocked.snapshot() == before and store.calls == writes


@pytest.mark.asyncio
async def test_role_change_denies_parent_receipt_and_adult_stock_is_private(stocked, now):
    item = await add(stocked, now)
    receipt = await stocked.execute(
        "adult",
        "pantry.stock_set",
        {
            "id": item["id"],
            "revision": item["revision"],
            "quantity": 1,
            "reason": "Counted",
        },
        "adult-stock",
        now,
    )
    assert "note" not in receipt and "history" not in receipt
    await stocked.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": stocked.snapshot()["members"]["parent"]["revision"],
            "name": "Former parent",
            "role": "adult",
            "active": True,
        },
        "demote",
        now,
    )
    with pytest.raises(DomainError, match="forbidden"):
        await add(stocked, now)
    view = stocked.view("parent", now=now)["pantry"]
    assert "note" not in view["items"][0] and view["suggestions"] == []


@pytest.mark.asyncio
async def test_disabled_module_is_not_projected_or_replayed(stocked, now):
    await add(stocked, now)
    settings = stocked.snapshot()["settings"]
    await stocked.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": [m for m in settings["modules"] if m != "pantry"],
        },
        "disable",
        now,
    )
    assert "pantry" not in stocked.view("parent", now=now)
    before = stocked.snapshot()
    assert not await stocked.tick(now)
    assert stocked.snapshot() == before
    with pytest.raises(DomainError, match="module_disabled"):
        await add(stocked, now)
