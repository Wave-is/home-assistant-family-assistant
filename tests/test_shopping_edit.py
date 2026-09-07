"""Strict shopping metadata edits preserve quantities and provenance."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def edit_payload(item, **changes):
    payload = {
        "id": item["id"],
        "revision": item["revision"],
        "name": item["name"],
        "category": item.get("category", ""),
        "store": item.get("store", ""),
        "note": item.get("note", ""),
        "buyer": item.get("buyer"),
    }
    payload.update(changes)
    return payload


@pytest.mark.asyncio
async def test_parent_edit_preserves_partial_amount_and_all_server_provenance(engine, now):
    item = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Rice",
            "quantity": 3,
            "unit": "kg",
            "category": "Pantry",
            "store": "Old store",
            "note": "old-private-looking-canary",
            "buyer": "adult",
        },
        "add",
        now,
    )
    item = await engine.execute(
        "adult",
        "shopping.purchase",
        {"id": item["id"], "revision": item["revision"], "quantity": 0.75, "unit": "kg"},
        "partial",
        now,
    )

    def provenance(ctx):
        stored = ctx.state["shopping"][item["id"]]
        stored.update(
            series_id="B000004",
            occurrence_id="2026-09-07",
            meal_plan_id="MP000003",
            meal_shopping_id="MS000002",
            merged_from=["S000099"],
        )

    await engine.system_update("synthetic_provenance", now, provenance)
    current = engine.snapshot()["shopping"][item["id"]]
    before_server = {
        key: deepcopy(current[key])
        for key in (
            "quantity",
            "purchased",
            "unit",
            "status",
            "series_id",
            "occurrence_id",
            "meal_plan_id",
            "meal_shopping_id",
            "merged_from",
        )
    }
    result = await engine.execute(
        "parent",
        "shopping.edit",
        edit_payload(
            current,
            name="Brown rice",
            category="Staples",
            store="Market",
            note="household note",
            buyer=None,
        ),
        "edit",
        now,
    )
    assert {key: result[key] for key in before_server} == before_server
    assert result["revision"] == current["revision"] + 1
    assert result["history"][-1]["action"] == "edit"
    assert result["history"][-1]["detail"]["fields"] == [
        "name",
        "category",
        "store",
        "note",
        "buyer",
    ]
    assert "old-private-looking-canary" not in repr(result["history"][-1])
    assert "household note" not in repr(result["history"][-1])


@pytest.mark.asyncio
async def test_child_can_only_edit_own_pending_proposal_and_cannot_assign_others(engine, now):
    own = await engine.execute(
        "child", "shopping.add", {"name": "Pencils", "buyer": "child"}, "own", now
    )
    sibling = await engine.execute("sibling", "shopping.add", {"name": "Paper"}, "sibling", now)
    changed = await engine.execute(
        "child",
        "shopping.edit",
        edit_payload(own, note="Shared school note"),
        "own-edit",
        now,
    )
    assert changed["status"] == "pending" and changed["creator"] == "child"
    assert changed["buyer"] == "child"
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child",
            "shopping.edit",
            edit_payload(sibling, note="not allowed"),
            "other-edit",
            now,
        )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child",
            "shopping.edit",
            edit_payload(changed, buyer="adult"),
            "other-buyer",
            now,
        )


@pytest.mark.asyncio
async def test_adult_edits_approved_but_not_pending_and_parent_edits_both(engine, now):
    approved = await engine.execute("adult", "shopping.add", {"name": "Tea"}, "tea", now)
    pending = await engine.execute("child", "shopping.add", {"name": "Juice"}, "juice", now)
    approved = await engine.execute(
        "adult",
        "shopping.edit",
        edit_payload(approved, store="Market"),
        "adult-edit",
        now,
    )
    assert approved["store"] == "Market"
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "adult",
            "shopping.edit",
            edit_payload(pending, store="Market"),
            "adult-pending",
            now,
        )
    pending = await engine.execute(
        "owner",
        "shopping.edit",
        edit_payload(pending, category="School"),
        "parent-edit",
        now,
    )
    assert pending["category"] == "School" and pending["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["purchased", "rejected", "archived", "merged"])
async def test_terminal_records_are_immutable(engine, now, status):
    item = await engine.execute("parent", "shopping.add", {"name": "Milk"}, "milk", now)

    def terminal(ctx):
        stored = ctx.state["shopping"][item["id"]]
        stored["status"] = status
        stored["revision"] += 1

    await engine.system_update("synthetic_terminal", now, terminal)
    current = engine.snapshot()["shopping"][item["id"]]
    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.edit",
            edit_payload(current, note="new"),
            "terminal-edit-" + status,
            now,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", True),
        ("category", []),
        ("store", {}),
        ("note", 3),
        ("category", "x" * 81),
        ("store", "x" * 81),
        ("note", "x" * 501),
        ("unit", "x" * 33),
        ("buyer", False),
        ("buyer", "guest"),
        ("buyer", "missing"),
    ],
)
async def test_add_rejects_malformed_metadata_and_invalid_buyer(engine, now, field, value):
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute(
            "parent", "shopping.add", {"name": "Item", field: value}, f"bad-{field}", now
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_edit_is_full_strict_replacement_with_stale_and_noop_rejected(engine, now):
    item = await engine.execute("parent", "shopping.add", {"name": "Coffee"}, "coffee", now)
    for key in ("name", "category", "store", "note", "buyer"):
        malformed = edit_payload(item, note="changed")
        malformed.pop(key)
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute("parent", "shopping.edit", malformed, "missing-" + key, now)
    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute("parent", "shopping.edit", edit_payload(item), "same", now)
    changed = await engine.execute(
        "parent", "shopping.edit", edit_payload(item, note="changed"), "changed", now
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent", "shopping.edit", edit_payload(item, note="stale"), "stale", now
        )
    assert engine.snapshot()["shopping"][item["id"]] == changed


@pytest.mark.asyncio
async def test_store_failure_is_atomic_and_exact_retry_survives_restart(engine, store, now):
    item = await engine.execute("parent", "shopping.add", {"name": "Beans"}, "beans", now)
    payload = edit_payload(item, category="Pantry", note="Shared only")
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("parent", "shopping.edit", payload, "durable-edit", now)
    assert engine.snapshot() == before
    store.fail = False
    result = await engine.execute("parent", "shopping.edit", payload, "durable-edit", now)
    writes = store.calls
    assert await engine.execute("parent", "shopping.edit", payload, "durable-edit", now) == result
    assert store.calls == writes
    restarted_writes = 0

    async def persist(_state):
        nonlocal restarted_writes
        restarted_writes += 1

    restarted = Engine(deepcopy(store.value), persist)
    assert (
        await restarted.execute("parent", "shopping.edit", payload, "durable-edit", now) == result
    )
    assert restarted_writes == 0


@pytest.mark.asyncio
async def test_guest_and_changed_role_cannot_execute_or_replay_edit(engine, now):
    item = await engine.execute("parent", "shopping.add", {"name": "Oats"}, "oats", now)
    payload = edit_payload(item, note="Shared household note")
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("guest", "shopping.edit", payload, "guest-edit", now)
    await engine.execute("parent", "shopping.edit", payload, "parent-edit", now)
    parent = engine.snapshot()["members"]["parent"]
    await engine.execute(
        "owner",
        "members.save",
        {"id": "parent", "revision": parent["revision"], "name": parent["name"], "role": "guest"},
        "revoke-parent",
        now,
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("parent", "shopping.edit", payload, "parent-edit", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_replay_returns_historical_edit_receipt_without_reopening_purchased_item(engine, now):
    item = await engine.execute("parent", "shopping.add", {"name": "Oats"}, "oats", now)
    payload = edit_payload(item, note="Shared household note")
    result = await engine.execute("parent", "shopping.edit", payload, "edit-receipt", now)
    await engine.execute(
        "parent",
        "shopping.purchase",
        {"id": item["id"], "revision": result["revision"]},
        "buy",
        now,
    )
    before = engine.snapshot()
    assert await engine.execute("parent", "shopping.edit", payload, "edit-receipt", now) == result
    assert engine.snapshot() == before
    assert before["shopping"][item["id"]]["status"] == "purchased"
