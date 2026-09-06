"""Tests for shopping.merge command, roles, strict revisions, validation, and history."""

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.mark.asyncio
async def test_merge_happy_path_quantity_conservation_and_history(engine, now):
    target = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Milk 3.2%",
            "quantity": 2.5,
            "unit": "l",
            "category": "Dairy",
            "store": "Supermarket",
            "note": "Whole milk",
            "buyer": "adult",
        },
        "add-target",
        now,
    )
    source = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "  milk 3.2%  ",
            "quantity": 1.5,
            "unit": "l",
            "category": "Dairy",
            "store": "Supermarket",
            "note": "Whole milk",
            "buyer": "adult",
        },
        "add-source",
        now,
    )

    source_partial = await engine.execute(
        "adult",
        "shopping.purchase",
        {"id": source["id"], "quantity": 0.5, "revision": source["revision"]},
        "buy-source-partial",
        now,
    )
    assert source_partial["purchased"] == 0.5

    merged_target = await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": target["id"],
            "revision": target["revision"],
            "sources": [{"id": source["id"], "revision": source_partial["revision"]}],
        },
        "merge-1",
        now,
    )

    assert merged_target["id"] == target["id"]
    assert merged_target["status"] == "approved"
    assert merged_target["quantity"] == 4.0
    assert merged_target["purchased"] == 0.5
    assert merged_target["merged_from"] == [source["id"]]
    assert merged_target["revision"] == target["revision"] + 1

    assert "history" in merged_target
    target_merge_events = [e for e in merged_target["history"] if e["action"] == "merge"]
    assert len(target_merge_events) == 1
    assert target_merge_events[0]["actor"] == "parent"
    assert target_merge_events[0]["detail"]["sources"] == [source["id"]]
    assert target_merge_events[0]["detail"]["quantity"] == 4.0
    assert target_merge_events[0]["detail"]["purchased"] == 0.5

    snapshot = engine.snapshot()
    source_record = snapshot["shopping"][source["id"]]
    assert source_record["status"] == "merged"
    assert source_record["merged_into"] == target["id"]
    assert source_record["quantity"] == 1.5
    assert source_record["purchased"] == 0.5
    assert source_record["name"] == source["name"]
    assert source_record["creator"] == "parent"
    assert source_record["revision"] == source_partial["revision"] + 1

    source_merge_events = [e for e in source_record["history"] if e["action"] == "merge"]
    assert len(source_merge_events) == 1
    assert source_merge_events[0]["actor"] == "parent"
    assert source_merge_events[0]["detail"]["merged_into"] == target["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["child", "guest", "adult"])
async def test_merge_role_forbidden_for_non_parents(engine, now, actor):
    target = await engine.execute(
        "parent", "shopping.add", {"name": "Bread", "quantity": 1}, "add-target", now
    )
    source = await engine.execute(
        "parent", "shopping.add", {"name": "Bread", "quantity": 2}, "add-source", now
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            actor,
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": source["id"], "revision": source["revision"]}],
            },
            "merge-forbidden",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_target_rev",
    [None, True, False, "1", 1.0, 0, -1],
)
async def test_merge_strict_revision_rejected_on_target(engine, now, bad_target_rev):
    target = await engine.execute(
        "parent", "shopping.add", {"name": "Apples", "quantity": 1}, "add-target", now
    )
    source = await engine.execute(
        "parent", "shopping.add", {"name": "Apples", "quantity": 2}, "add-source", now
    )
    payload = {
        "id": target["id"],
        "sources": [{"id": source["id"], "revision": source["revision"]}],
    }
    if bad_target_rev is not None:
        payload["revision"] = bad_target_rev
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute("parent", "shopping.merge", payload, "merge-bad-rev", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_source_rev",
    [None, True, False, "1", 1.0, 0, -1],
)
async def test_merge_strict_revision_rejected_on_source(engine, now, bad_source_rev):
    target = await engine.execute(
        "parent", "shopping.add", {"name": "Bananas", "quantity": 1}, "add-target", now
    )
    source = await engine.execute(
        "parent", "shopping.add", {"name": "Bananas", "quantity": 2}, "add-source", now
    )
    src_entry = {"id": source["id"]}
    if bad_source_rev is not None:
        src_entry["revision"] = bad_source_rev
    payload = {
        "id": target["id"],
        "revision": target["revision"],
        "sources": [src_entry],
    }
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute("parent", "shopping.merge", payload, "merge-bad-src-rev", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_merge_revision_conflict_on_mismatched_revision(engine, now):
    target = await engine.execute(
        "parent", "shopping.add", {"name": "Oranges", "quantity": 1}, "add-target", now
    )
    source = await engine.execute(
        "parent", "shopping.add", {"name": "Oranges", "quantity": 2}, "add-source", now
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"] + 99,
                "sources": [{"id": source["id"], "revision": source["revision"]}],
            },
            "conflict-target",
            now,
        )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": source["id"], "revision": source["revision"] + 99}],
            },
            "conflict-source",
            now,
        )


@pytest.mark.asyncio
async def test_merge_pending_bypass_rejection(engine, now):
    child_target = await engine.execute(
        "child", "shopping.add", {"name": "Cookies", "quantity": 1}, "add-c-target", now
    )
    assert child_target["status"] == "pending"

    child_source = await engine.execute(
        "child", "shopping.add", {"name": "Cookies", "quantity": 2}, "add-c-source", now
    )
    assert child_source["status"] == "pending"

    approved_item = await engine.execute(
        "parent", "shopping.add", {"name": "Cookies", "quantity": 1}, "add-p-approved", now
    )
    assert approved_item["status"] == "approved"

    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": child_target["id"],
                "revision": child_target["revision"],
                "sources": [{"id": approved_item["id"], "revision": approved_item["revision"]}],
            },
            "merge-pending-target",
            now,
        )

    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": approved_item["id"],
                "revision": approved_item["revision"],
                "sources": [{"id": child_source["id"], "revision": child_source["revision"]}],
            },
            "merge-pending-source",
            now,
        )


@pytest.mark.asyncio
async def test_merge_rejected_for_terminal_and_zero_remaining_statuses(engine, now):
    target = await engine.execute(
        "parent", "shopping.add", {"name": "Tea", "quantity": 2}, "add-target", now
    )
    source = await engine.execute(
        "parent", "shopping.add", {"name": "Tea", "quantity": 1}, "add-source", now
    )

    bought_source = await engine.execute(
        "adult",
        "shopping.purchase",
        {"id": source["id"], "quantity": 1, "revision": source["revision"]},
        "buy-source",
        now,
    )
    assert bought_source["status"] == "purchased"

    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": bought_source["id"], "revision": bought_source["revision"]}],
            },
            "merge-purchased-source",
            now,
        )

    archive_cand = await engine.execute(
        "child", "shopping.add", {"name": "Tea", "quantity": 1}, "add-arch", now
    )
    archived = await engine.execute(
        "parent",
        "shopping.archive",
        {"id": archive_cand["id"], "revision": archive_cand["revision"]},
        "archive-item",
        now,
    )
    assert archived["status"] == "archived"
    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": archived["id"], "revision": archived["revision"]}],
            },
            "merge-archived-source",
            now,
        )


@pytest.mark.asyncio
async def test_merge_source_boundaries_and_uniqueness(engine, now):
    target = await engine.execute(
        "parent", "shopping.add", {"name": "Juice", "quantity": 1}, "add-target", now
    )
    source = await engine.execute(
        "parent", "shopping.add", {"name": "Juice", "quantity": 1}, "add-source", now
    )

    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {"id": target["id"], "revision": target["revision"], "sources": []},
            "merge-0-sources",
            now,
        )

    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [
                    {"id": source["id"], "revision": source["revision"]},
                    {"id": source["id"], "revision": source["revision"]},
                ],
            },
            "merge-dup-sources",
            now,
        )

    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": target["id"], "revision": target["revision"]}],
            },
            "merge-target-as-source",
            now,
        )

    items = []
    for i in range(20):
        it = await engine.execute(
            "parent", "shopping.add", {"name": "Juice", "quantity": 1}, f"add-juice-{i}", now
        )
        items.append(it)
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": it["id"], "revision": it["revision"]} for it in items],
            },
            "merge-20-sources",
            now,
        )


@pytest.mark.asyncio
async def test_merge_attribute_mismatches(engine, now):
    target = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Coffee",
            "quantity": 1,
            "unit": "kg",
            "category": "Groceries",
            "store": "Store A",
            "note": "Arabica",
            "buyer": "adult",
        },
        "target",
        now,
    )

    diff_name = await engine.execute(
        "parent", "shopping.add", {"name": "Tea", "unit": "kg"}, "diff-name", now
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": diff_name["id"], "revision": diff_name["revision"]}],
            },
            "mismatch-name",
            now,
        )

    diff_unit = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Coffee",
            "unit": "g",
            "category": "Groceries",
            "store": "Store A",
            "note": "Arabica",
            "buyer": "adult",
        },
        "diff-unit",
        now,
    )
    with pytest.raises(DomainError, match="unit_mismatch"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": diff_unit["id"], "revision": diff_unit["revision"]}],
            },
            "mismatch-unit",
            now,
        )

    diff_cat = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Coffee",
            "unit": "kg",
            "category": "Beverages",
            "store": "Store A",
            "note": "Arabica",
            "buyer": "adult",
        },
        "diff-cat",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": diff_cat["id"], "revision": diff_cat["revision"]}],
            },
            "mismatch-cat",
            now,
        )

    diff_store = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Coffee",
            "unit": "kg",
            "category": "Groceries",
            "store": "Store B",
            "note": "Arabica",
            "buyer": "adult",
        },
        "diff-store",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": diff_store["id"], "revision": diff_store["revision"]}],
            },
            "mismatch-store",
            now,
        )

    diff_note = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Coffee",
            "unit": "kg",
            "category": "Groceries",
            "store": "Store A",
            "note": "Robusta",
            "buyer": "adult",
        },
        "diff-note",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": diff_note["id"], "revision": diff_note["revision"]}],
            },
            "mismatch-note",
            now,
        )

    diff_buyer = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Coffee",
            "unit": "kg",
            "category": "Groceries",
            "store": "Store A",
            "note": "Arabica",
            "buyer": None,
        },
        "diff-buyer",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": target["id"],
                "revision": target["revision"],
                "sources": [{"id": diff_buyer["id"], "revision": diff_buyer["revision"]}],
            },
            "mismatch-buyer",
            now,
        )


@pytest.mark.asyncio
async def test_merge_chains_preserves_merged_from_provenance(engine, now):
    a = await engine.execute(
        "parent", "shopping.add", {"name": "Sugar", "quantity": 1}, "add-a", now
    )
    b = await engine.execute(
        "parent", "shopping.add", {"name": "Sugar", "quantity": 2}, "add-b", now
    )
    c = await engine.execute(
        "parent", "shopping.add", {"name": "Sugar", "quantity": 3}, "add-c", now
    )

    merged_a1 = await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": a["id"],
            "revision": a["revision"],
            "sources": [{"id": b["id"], "revision": b["revision"]}],
        },
        "merge-b-into-a",
        now,
    )
    assert merged_a1["quantity"] == 3
    assert merged_a1["merged_from"] == [b["id"]]

    merged_c = await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": c["id"],
            "revision": c["revision"],
            "sources": [{"id": merged_a1["id"], "revision": merged_a1["revision"]}],
        },
        "merge-a-into-c",
        now,
    )
    assert merged_c["quantity"] == 6
    assert merged_c["merged_from"] == [merged_a1["id"]]

    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": c["id"],
                "revision": merged_c["revision"],
                "sources": [{"id": b["id"], "revision": b["revision"] + 1}],
            },
            "merge-b-again",
            now,
        )


@pytest.mark.asyncio
async def test_merge_idempotent_replay(engine, now):
    t = await engine.execute(
        "parent", "shopping.add", {"name": "Salt", "quantity": 1}, "add-t", now
    )
    s = await engine.execute(
        "parent", "shopping.add", {"name": "Salt", "quantity": 2}, "add-s", now
    )

    p = {
        "id": t["id"],
        "revision": t["revision"],
        "sources": [{"id": s["id"], "revision": s["revision"]}],
    }

    res1 = await engine.execute("parent", "shopping.merge", p, "merge-op-id", now)
    res2 = await engine.execute("parent", "shopping.merge", p, "merge-op-id", now)
    assert res1 == res2
    assert res2["quantity"] == 3


@pytest.mark.asyncio
async def test_merge_storage_failure_atomicity(engine, store, now):
    t = await engine.execute(
        "parent", "shopping.add", {"name": "Pepper", "quantity": 1}, "add-t", now
    )
    s = await engine.execute(
        "parent", "shopping.add", {"name": "Pepper", "quantity": 2}, "add-s", now
    )

    before = engine.snapshot()
    store.fail = True

    p = {
        "id": t["id"],
        "revision": t["revision"],
        "sources": [{"id": s["id"], "revision": s["revision"]}],
    }
    with pytest.raises(OSError):
        await engine.execute("parent", "shopping.merge", p, "fail-op", now)

    assert engine.snapshot() == before
    store.fail = False


@pytest.mark.asyncio
async def test_merge_json_finite_errors(engine, now):
    t = await engine.execute(
        "parent", "shopping.add", {"name": "Rice", "quantity": 1}, "add-t", now
    )
    s = await engine.execute(
        "parent", "shopping.add", {"name": "Rice", "quantity": 2}, "add-s", now
    )

    nan_payload = {
        "id": t["id"],
        "revision": float("nan"),
        "sources": [{"id": s["id"], "revision": s["revision"]}],
    }
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute("parent", "shopping.merge", nan_payload, "nan-op", now)


@pytest.mark.asyncio
async def test_merge_quantity_bounded_1e6(engine, now):
    t = await engine.execute(
        "parent", "shopping.add", {"name": "Flour", "quantity": 999999}, "add-t", now
    )
    s = await engine.execute(
        "parent", "shopping.add", {"name": "Flour", "quantity": 10}, "add-s", now
    )
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "shopping.merge",
            {
                "id": t["id"],
                "revision": t["revision"],
                "sources": [{"id": s["id"], "revision": s["revision"]}],
            },
            "exceed-1e6",
            now,
        )


@pytest.mark.asyncio
async def test_merge_old_records_lacking_history(engine, store, now):
    state = engine.snapshot()
    state["shopping"]["S000091"] = {
        "id": "S000091",
        "name": "Butter",
        "quantity": 2.0,
        "purchased": 0.0,
        "unit": "pack",
        "category": "Dairy",
        "store": "",
        "note": "",
        "buyer": None,
        "creator": "parent",
        "created_at": now.isoformat(),
        "status": "approved",
        "revision": 1,
    }
    state["shopping"]["S000092"] = {
        "id": "S000092",
        "name": "Butter",
        "quantity": 1.0,
        "purchased": 0.0,
        "unit": "pack",
        "category": "Dairy",
        "store": "",
        "note": "",
        "buyer": None,
        "creator": "parent",
        "created_at": now.isoformat(),
        "status": "approved",
        "revision": 1,
    }
    legacy_engine = Engine(state, store.save)

    purchased = await legacy_engine.execute(
        "adult",
        "shopping.purchase",
        {"id": "S000092", "quantity": 0.5, "revision": 1},
        "legacy-buy",
        now,
    )
    assert purchased["purchased"] == 0.5
    assert len(purchased["history"]) == 1
    assert purchased["history"][0]["action"] == "purchase"

    merged = await legacy_engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": "S000091",
            "revision": 1,
            "sources": [{"id": "S000092", "revision": purchased["revision"]}],
        },
        "legacy-merge",
        now,
    )
    assert merged["quantity"] == 3.0
    assert merged["purchased"] == 0.5
    assert merged["merged_from"] == ["S000092"]
    assert len(merged["history"]) == 1
    assert merged["history"][0]["action"] == "merge"


@pytest.mark.asyncio
async def test_shopping_add_with_empty_or_omitted_unit(engine, now):
    item1 = await engine.execute(
        "parent", "shopping.add", {"name": "Toothpaste"}, "add-no-unit", now
    )
    assert item1["unit"] == ""
    assert item1["history"][0]["detail"]["unit"] == ""

    item2 = await engine.execute(
        "parent", "shopping.add", {"name": "Soap", "unit": ""}, "add-empty-unit", now
    )
    assert item2["unit"] == ""
    assert item2["history"][0]["detail"]["unit"] == ""


@pytest.mark.asyncio
async def test_all_history_lifecycle_actions_and_schema(engine, now):
    child_item = await engine.execute(
        "child", "shopping.add", {"name": "Cereal", "quantity": 3}, "add-cereal", now
    )
    assert child_item["status"] == "pending"
    assert len(child_item["history"]) == 1
    e_add = child_item["history"][0]
    assert set(e_add.keys()) == {"at", "actor", "action", "detail"}
    assert e_add["action"] == "add"
    assert e_add["actor"] == "child"

    rejected = await engine.execute(
        "parent",
        "shopping.reject",
        {"id": child_item["id"], "revision": child_item["revision"]},
        "reject-cereal",
        now,
    )
    assert rejected["status"] == "rejected"
    assert len(rejected["history"]) == 2
    assert rejected["history"][1]["action"] == "reject"
    assert rejected["history"][1]["actor"] == "parent"
    assert rejected["history"][1]["detail"]["status"] == "rejected"

    second_child_item = await engine.execute(
        "child", "shopping.add", {"name": "Yogurt", "quantity": 2}, "add-yogurt", now
    )
    approved = await engine.execute(
        "parent",
        "shopping.approve",
        {"id": second_child_item["id"], "revision": second_child_item["revision"]},
        "approve-yogurt",
        now,
    )
    assert approved["status"] == "approved"
    assert len(approved["history"]) == 2
    assert approved["history"][1]["action"] == "approve"

    purchased = await engine.execute(
        "adult",
        "shopping.purchase",
        {"id": approved["id"], "quantity": 1, "revision": approved["revision"]},
        "buy-yogurt",
        now,
    )
    assert purchased["purchased"] == 1
    assert len(purchased["history"]) == 3
    assert purchased["history"][2]["action"] == "purchase"
    assert purchased["history"][2]["detail"]["amount"] == 1
    assert purchased["history"][2]["detail"]["purchased"] == 1
    assert purchased["history"][2]["detail"]["remaining"] == 1

    archived = await engine.execute(
        "parent",
        "shopping.archive",
        {"id": purchased["id"], "revision": purchased["revision"]},
        "archive-yogurt",
        now,
    )
    assert archived["status"] == "archived"
    assert len(archived["history"]) == 4
    assert archived["history"][3]["action"] == "archive"
    assert archived["history"][3]["detail"]["status"] == "archived"

    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.archive",
            {"id": archived["id"], "revision": archived["revision"]},
            "archive-again",
            now,
        )


@pytest.mark.asyncio
async def test_merged_source_archive_denial(engine, now):
    target = await engine.execute(
        "parent", "shopping.add", {"name": "Garlic", "quantity": 2}, "add-g1", now
    )
    source = await engine.execute(
        "parent", "shopping.add", {"name": "Garlic", "quantity": 3}, "add-g2", now
    )

    merged = await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": target["id"],
            "revision": target["revision"],
            "sources": [{"id": source["id"], "revision": source["revision"]}],
        },
        "merge-garlic",
        now,
    )
    assert merged["quantity"] == 5

    snapshot = engine.snapshot()
    merged_source = snapshot["shopping"][source["id"]]
    assert merged_source["status"] == "merged"

    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "parent",
            "shopping.archive",
            {"id": source["id"], "revision": merged_source["revision"]},
            "archive-merged-source",
            now,
        )


@pytest.mark.asyncio
async def test_history_corruption_preserves_state(engine, store, now):
    state = engine.snapshot()
    state["shopping"]["S000099"] = {
        "id": "S000099",
        "name": "CorruptItem",
        "quantity": 1.0,
        "purchased": 0.0,
        "unit": "pack",
        "category": "",
        "store": "",
        "note": "",
        "buyer": None,
        "creator": "parent",
        "created_at": now.isoformat(),
        "status": "approved",
        "revision": 1,
        "history": "not a list",
    }
    corrupt_engine = Engine(state, store.save)
    before = corrupt_engine.snapshot()

    with pytest.raises(DomainError, match="invalid_field"):
        await corrupt_engine.execute(
            "adult",
            "shopping.purchase",
            {"id": "S000099", "quantity": 1, "revision": 1},
            "buy-corrupt",
            now,
        )

    assert corrupt_engine.snapshot() == before


@pytest.mark.asyncio
async def test_merge_aggregate_precision(engine, now):
    t = await engine.execute(
        "parent", "shopping.add", {"name": "Spices", "quantity": 0.100001}, "add-s1", now
    )
    s1 = await engine.execute(
        "parent", "shopping.add", {"name": "Spices", "quantity": 0.200002}, "add-s2", now
    )
    s2 = await engine.execute(
        "parent", "shopping.add", {"name": "Spices", "quantity": 0.300003}, "add-s3", now
    )

    merged = await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": t["id"],
            "revision": t["revision"],
            "sources": [
                {"id": s1["id"], "revision": s1["revision"]},
                {"id": s2["id"], "revision": s2["revision"]},
            ],
        },
        "merge-spices",
        now,
    )

    assert merged["quantity"] == 0.600006
    assert merged["purchased"] == 0.0
