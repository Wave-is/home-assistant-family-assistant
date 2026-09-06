"""Shopping projection, recurring provenance and Telegram use the real engine."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.shopping_series import _open_descendant
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.router import route


@pytest.mark.asyncio
async def test_partial_purchase_from_telegram_and_finished_item_leaves_active_list(engine, now):
    first = await engine.execute(
        "parent", "shopping.add", {"name": "Apples", "quantity": 3, "unit": "kg"}, "add", now
    )
    command = f"/bought {first['id']} | 1,5"
    await route(engine, "adult", command, "partial", now)
    await route(engine, "adult", command, "partial", now)
    assert engine.snapshot()["shopping"][first["id"]]["purchased"] == 1.5
    listing = await route(engine, "child", "/shopping", "list-open", now)
    assert "Apples" in listing and "1.5 kg" in listing
    for invalid in ("nan", "inf", "-1", "0", "2", "not-a-number"):
        before = engine.snapshot()
        with pytest.raises(DomainError):
            await route(engine, "adult", f"/bought {first['id']} | {invalid}", invalid, now)
        after = engine.snapshot()
        # Semantic failures may retain an interpretation receipt, never effects.
        for bucket in ("shopping", "processed", "audit"):
            assert after[bucket] == before[bucket]
        if invalid in {"nan", "inf", "not-a-number"}:
            assert after == before
    await route(engine, "adult", f"/bought {first['id']}", "finish", now)
    assert "Apples" not in await route(engine, "child", "/shopping", "list-done", now)


@pytest.mark.asyncio
async def test_recurring_source_follows_merge_chain_without_duplicate_accumulation(engine, now):
    series = await engine.execute(
        "parent",
        "shopping.series_save",
        {
            "name": "Milk",
            "unit": "l",
            "quantity": 2,
            "rule": {
                "frequency": "daily",
                "start_date": now.date().isoformat(),
                "time": "08:00",
                "timezone": "UTC",
            },
        },
        "series",
        now,
    )
    await engine.tick(now)
    original = next(iter(engine.snapshot()["shopping"].values()))
    target = await engine.execute(
        "parent",
        "shopping.add",
        {"name": "Milk", "unit": "l"},
        "manual",
        now,
    )
    merged = await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": target["id"],
            "revision": target["revision"],
            "sources": [{"id": original["id"], "revision": original["revision"]}],
        },
        "merge",
        now,
    )
    last = await engine.execute(
        "parent",
        "shopping.add",
        {"name": "Milk", "unit": "l"},
        "next-manual",
        now,
    )
    await engine.execute(
        "parent",
        "shopping.merge",
        {
            "id": last["id"],
            "revision": last["revision"],
            "sources": [{"id": merged["id"], "revision": merged["revision"]}],
        },
        "next-merge",
        now,
    )
    assert await engine.tick(now + timedelta(days=1))
    state = engine.snapshot()
    assert len(state["shopping"]) == 3
    assert (
        state["shopping_series"][series["id"]]["occurrences"][
            (now + timedelta(days=1)).date().isoformat()
        ]["state"]
        == "skipped_open"
    )
    assert (await route(engine, "child", "/shopping", "list", now)).count("Milk") == 1
    await engine.execute(
        "adult",
        "shopping.purchase",
        {"id": last["id"], "revision": engine.snapshot()["shopping"][last["id"]]["revision"]},
        "done",
        now,
    )
    assert await engine.tick(now + timedelta(days=2))
    assert len(engine.snapshot()["shopping"]) == 4


def test_corrupt_merged_provenance_does_not_create_a_new_purchase():
    for items in (
        {"a": {"status": "merged", "merged_into": "missing"}},
        {"a": {"status": "merged", "merged_into": "a"}},
        {"a": {"status": "merged", "merged_into": []}},
        {
            "a": {"status": "merged", "merged_into": "b"},
            "b": {"status": "merged", "merged_into": "a"},
        },
    ):
        assert _open_descendant(items, items["a"])


@pytest.mark.asyncio
async def test_six_decimal_quantities_finish_without_a_stuck_fraction(engine, store, now):
    item = await engine.execute(
        "parent", "shopping.add", {"name": "Spice", "quantity": 1.0000004}, "spice", now
    )
    assert item["quantity"] == 1
    bought = await engine.execute(
        "adult",
        "shopping.purchase",
        {"id": item["id"], "revision": item["revision"], "quantity": 0.1234561},
        "partial",
        now,
    )
    assert bought["purchased"] == 0.123456
    assert bought["history"][-1]["detail"]["amount"] == 0.123456
    # An old stored item may have higher precision; finish at supported precision.
    state = engine.snapshot()
    state["shopping"][item["id"]]["quantity"] = 1.0000004
    restored = Engine(state, store.save)
    result = await restored.execute(
        "adult",
        "shopping.purchase",
        {"id": item["id"], "revision": restored.snapshot()["shopping"][item["id"]]["revision"]},
        "done",
        now,
    )
    assert result["status"] == "purchased" and result["purchased"] == 1


@pytest.mark.asyncio
async def test_unicode_candidate_projection_uses_the_same_matching_as_merge(engine, now):
    items = [
        await engine.execute("parent", "shopping.add", {"name": name}, name, now)
        for name in ("Straße", " STRASSE ")
    ]
    visible = engine.view("child")["shopping"]
    assert visible[0]["merge_name"] == visible[1]["merge_name"] == "strasse"
    assert "merge_name" not in engine.snapshot()["shopping"][items[0]["id"]]
    merged = await engine.execute(
        "parent",
        "shopping.merge",
        {"id": items[0]["id"], "revision": 1, "sources": [{"id": items[1]["id"], "revision": 1}]},
        "merge",
        now,
    )
    assert merged["quantity"] == 2
