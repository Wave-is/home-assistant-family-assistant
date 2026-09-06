"""Recurring purchases use the same atomic store and authenticated action path."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def payload(now, **extra):
    return {
        "name": "Milk",
        "quantity": 2,
        "unit": "l",
        "buyer": "adult",
        "rule": {
            "frequency": "daily",
            "start_date": now.date().isoformat(),
            "time": "08:00",
            "timezone": "UTC",
        },
        **extra,
    }


@pytest.mark.asyncio
async def test_series_dispatch_store_fault_reload_and_replay(engine, store, now):
    p = payload(now)
    saved = await engine.execute("parent", "shopping.series_save", p, "series", now)
    assert await engine.execute("parent", "shopping.series_save", p, "series", now) == saved
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(now)
    assert engine.snapshot() == before
    store.fail = False
    assert await engine.tick(now)
    state = engine.snapshot()
    assert not state["tasks"] and not state["court"]
    assert len(state["shopping"]) == 1
    item = next(iter(state["shopping"].values()))
    assert item["series_id"] == saved["id"] and item["status"] == "approved"
    assert item["creator"] == "parent" and item["buyer"] == "adult"
    restarted = Engine(state, store.save)
    assert not await restarted.tick(now + timedelta(seconds=10))
    await restarted.execute(
        "adult",
        "shopping.purchase",
        {"id": item["id"], "revision": item["revision"], "quantity": 1},
        "partial",
        now,
    )
    assert await restarted.tick(now + timedelta(days=1))
    assert len(restarted.snapshot()["shopping"]) == 1
    await restarted.execute(
        "adult",
        "shopping.purchase",
        {"id": item["id"], "revision": restarted.snapshot()["shopping"][item["id"]]["revision"]},
        "finish",
        now,
    )
    assert await restarted.tick(now + timedelta(days=2))
    assert len(restarted.snapshot()["shopping"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["child", "guest", "adult"])
async def test_only_parents_can_automate_approved_purchases(engine, now, actor):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(actor, "shopping.series_save", payload(now), "denied", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_revision", [None, True, False, "1", 1.0, 0, -1])
async def test_revision_type_cannot_bypass_edit_or_enable(engine, now, bad_revision):
    item = await engine.execute("parent", "shopping.series_save", payload(now), "series", now)
    for action, change in (
        ("series_enable", {"enabled": False}),
        ("series_save", payload(now, name="Changed")),
    ):
        before = engine.snapshot()
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute(
                "parent",
                f"shopping.{action}",
                {**change, "id": item["id"], "revision": bad_revision},
                "bad-" + action,
                now,
            )
        assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_edit_preserves_optional_data_and_hides_internal_occurrences(engine, now):
    item = await engine.execute("parent", "shopping.series_save", payload(now), "series", now)
    changed = await engine.execute(
        "owner",
        "shopping.series_save",
        {
            "id": item["id"],
            "revision": item["revision"],
            "name": "Fresh milk",
            "rule": item["rule"],
        },
        "edit",
        now,
    )
    assert (changed["creator"], changed["quantity"], changed["unit"], changed["buyer"]) == (
        "parent",
        2,
        "l",
        "adult",
    )
    assert not engine.view("guest")["shopping_series"]
    assert "creator" not in engine.view("child")["shopping_series"][0]
    assert "occurrences" not in engine.view("child")["shopping_series"][0]
    assert engine.view("parent")["shopping_series"][0]["revision"] == changed["revision"]


@pytest.mark.asyncio
async def test_missing_old_bucket_is_initialized_without_overwriting_items(engine, store, now):
    await engine.execute("parent", "shopping.add", {"name": "Bread"}, "manual", now)
    state = engine.snapshot()
    del state["shopping_series"]
    saved = deepcopy(state)
    restarted = Engine(state, store.save)
    assert restarted.snapshot()["shopping"] == saved["shopping"]
    assert restarted.view("parent")["shopping_series"] == []
    assert "shopping_series" not in state


@pytest.mark.asyncio
async def test_guest_buyer_cannot_be_assigned_or_receive_new_occurrences(engine, now):
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent", "shopping.series_save", payload(now, buyer="guest"), "bad", now
        )
    await engine.execute("parent", "shopping.series_save", payload(now), "good", now)
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "adult",
            "revision": engine.snapshot()["members"]["adult"]["revision"],
            "name": "Visitor",
            "role": "guest",
        },
        "role",
        now,
    )
    await engine.tick(now)
    assert not engine.snapshot()["shopping"]


@pytest.mark.asyncio
@pytest.mark.parametrize("day,expected", [("2026-03-29", 0), ("2026-10-25", 1)])
async def test_purchase_series_handles_actual_dst_gap_and_fold(engine, store, day, expected):
    morning = datetime.fromisoformat(day + "T00:00:00+00:00")
    p = payload(morning)
    p["rule"].update(time="03:30", timezone="Europe/Kyiv", catchup_hours=6)
    await engine.execute("parent", "shopping.series_save", p, "dst", morning)
    await engine.tick(morning + timedelta(hours=4))
    assert len(engine.snapshot()["shopping"]) == expected
    restarted = Engine(engine.snapshot(), store.save)
    await restarted.tick(morning + timedelta(hours=5))
    assert len(restarted.snapshot()["shopping"]) == expected
