"""Tests for recurring shopping series."""

from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain import shopping, shopping_series
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import new_state
from custom_components.family_assistant.domain.validation import DomainError


def _make_state(creator_role="parent", buyer_role="adult", creator_active=True, buyer_active=True):
    state = new_state("synthetic-owner", "Example household")
    state["members"]["p1"] = {
        "id": "p1",
        "name": "Parent 1",
        "role": creator_role,
        "language": "en",
        "ha_user_id": "syn-p1",
        "aliases": [],
        "active": creator_active,
        "revision": 1,
    }
    state["members"]["b1"] = {
        "id": "b1",
        "name": "Buyer 1",
        "role": buyer_role,
        "language": "en",
        "ha_user_id": "syn-b1",
        "aliases": [],
        "active": buyer_active,
        "revision": 1,
    }
    state["members"]["child1"] = {
        "id": "child1",
        "name": "Child 1",
        "role": "child",
        "language": "en",
        "ha_user_id": "syn-c1",
        "aliases": [],
        "active": True,
        "revision": 1,
    }
    return state


def _make_ctx(state, actor_id="p1", now=None, op_id="test-op"):
    now = now or datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
    actor = state["members"].get(actor_id, {"id": actor_id, "role": "system"})
    return Context(state, actor, now, op_id)


def test_parent_permission_required():
    state = _make_state()
    rule = {
        "frequency": "daily",
        "start_date": "2026-09-01",
        "time": "09:00",
        "timezone": "UTC",
    }
    child_ctx = _make_ctx(state, "child1")
    with pytest.raises(DomainError, match="forbidden"):
        shopping_series.handle(child_ctx, "series_save", {"name": "Milk", "rule": rule})

    parent_ctx = _make_ctx(state, "p1")
    series = shopping_series.handle(parent_ctx, "series_save", {"name": "Milk", "rule": rule})
    assert series["id"].startswith("B")
    assert series["name"] == "Milk"

    with pytest.raises(DomainError, match="forbidden"):
        shopping_series.handle(
            child_ctx,
            "series_enable",
            {"id": series["id"], "enabled": False, "revision": series["revision"]},
        )


def test_malformed_payload_and_field_validations():
    state = _make_state()
    ctx = _make_ctx(state, "p1")
    rule = {
        "frequency": "daily",
        "start_date": "2026-09-01",
        "time": "09:00",
        "timezone": "UTC",
    }

    # Missing required name
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(ctx, "series_save", {"rule": rule})
    assert exc.value.code == "invalid_field"

    # Missing required rule
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(ctx, "series_save", {"name": "Bread"})
    assert exc.value.code == "invalid_field"

    # Unknown action
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(ctx, "other_action", {"name": "Bread", "rule": rule})
    assert exc.value.code == "unknown_action"

    # Unknown field
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(
            ctx, "series_save", {"name": "Bread", "rule": rule, "extra_field": 123}
        )
    assert exc.value.code == "invalid_field"

    # Name text > 200
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(ctx, "series_save", {"name": "A" * 201, "rule": rule})
    assert exc.value.code == "invalid_field"

    # Blank name
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(ctx, "series_save", {"name": "   ", "rule": rule})
    assert exc.value.code == "invalid_field"

    # Quantity < 0.001
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(
            ctx, "series_save", {"name": "Bread", "rule": rule, "quantity": 0.0005}
        )
    assert exc.value.code == "invalid_field"

    # Quantity boolean
    with pytest.raises(DomainError) as exc:
        shopping_series.handle(
            ctx, "series_save", {"name": "Bread", "rule": rule, "quantity": True}
        )
    assert exc.value.code == "invalid_field"

    # String field non-string or length overflow
    for field, max_len in (("unit", 32), ("category", 80), ("store", 80), ("note", 500)):
        with pytest.raises(DomainError) as exc:
            shopping_series.handle(ctx, "series_save", {"name": "Bread", "rule": rule, field: 123})
        assert exc.value.code == "invalid_field"

        with pytest.raises(DomainError) as exc:
            shopping_series.handle(
                ctx, "series_save", {"name": "Bread", "rule": rule, field: "x" * (max_len + 1)}
            )
        assert exc.value.code == "invalid_field"

    # Non-existent or inactive buyer
    with pytest.raises(DomainError, match="unknown_member"):
        shopping_series.handle(
            ctx, "series_save", {"name": "Bread", "rule": rule, "buyer": "nonexistent"}
        )

    state["members"]["inactive_member"] = {
        "id": "inactive_member",
        "name": "Inactive",
        "role": "adult",
        "language": "en",
        "ha_user_id": "syn-in",
        "aliases": [],
        "active": False,
        "revision": 1,
    }
    with pytest.raises(DomainError, match="unknown_member"):
        shopping_series.handle(
            ctx, "series_save", {"name": "Bread", "rule": rule, "buyer": "inactive_member"}
        )

    # Malformed enabled
    with pytest.raises(DomainError):
        shopping_series.handle(
            ctx, "series_save", {"name": "Bread", "rule": rule, "enabled": "yes"}
        )


def test_revision_conflicts_and_preservation():
    state = _make_state()
    ctx = _make_ctx(state, "p1")
    rule = {
        "frequency": "daily",
        "start_date": "2026-09-01",
        "time": "09:00",
        "timezone": "UTC",
    }
    saved = shopping_series.handle(
        ctx,
        "series_save",
        {
            "name": "Apples",
            "quantity": 2.5,
            "unit": "kg",
            "category": "Groceries",
            "store": "Supermarket",
            "note": "Crisp ones",
            "buyer": "b1",
            "rule": rule,
        },
    )
    series_id = saved["id"]
    rev = saved["revision"]
    assert saved["creator"] == "p1"
    assert saved["occurrences"] == {}

    # Update without revision must fail
    with pytest.raises(DomainError, match="invalid_field"):
        shopping_series.handle(
            ctx,
            "series_save",
            {"id": series_id, "name": "Green Apples", "rule": rule},
        )

    # Update with wrong revision must fail (conflict)
    with pytest.raises(DomainError, match="conflict"):
        shopping_series.handle(
            ctx,
            "series_save",
            {"id": series_id, "revision": rev + 5, "name": "Green Apples", "rule": rule},
        )

    # Enable with wrong revision or missing revision
    with pytest.raises(DomainError):
        shopping_series.handle(
            ctx,
            "series_enable",
            {"id": series_id, "enabled": False},
        )
    with pytest.raises(DomainError, match="conflict"):
        shopping_series.handle(
            ctx,
            "series_enable",
            {"id": series_id, "revision": rev + 5, "enabled": False},
        )

    # Updating preserves creator and occurrences
    saved["occurrences"]["2026-09-05"] = {"state": "created", "item_id": "S000001"}
    updated = shopping_series.handle(
        ctx,
        "series_save",
        {"id": series_id, "revision": rev, "name": "Green Apples", "rule": rule},
    )
    assert updated["name"] == "Green Apples"
    assert updated["creator"] == "p1"
    assert "2026-09-05" in updated["occurrences"]
    assert updated["revision"] == rev + 1

    # Disable series
    disabled = shopping_series.handle(
        ctx,
        "series_enable",
        {"id": series_id, "revision": updated["revision"], "enabled": False},
    )
    assert disabled["enabled"] is False


def test_tick_module_disabled_or_series_disabled():
    state = _make_state()
    rule = {
        "frequency": "daily",
        "start_date": "2026-09-06",
        "time": "08:00",
        "timezone": "UTC",
    }
    save_ctx = _make_ctx(state, "p1", now=datetime(2026, 9, 6, 7, 0, tzinfo=UTC))
    series = shopping_series.handle(save_ctx, "series_save", {"name": "Milk", "rule": rule})

    # Disable module
    state["settings"]["modules"] = ["tasks"]
    tick_ctx = _make_ctx(state, now=datetime(2026, 9, 6, 9, 0, tzinfo=UTC))
    shopping_series.tick(tick_ctx)
    assert len(series["occurrences"]) == 0
    assert len(state.get("shopping", {})) == 0

    # Re-enable module, but series disabled
    state["settings"]["modules"] = ["shopping"]
    series["enabled"] = False
    shopping_series.tick(tick_ctx)
    assert len(series["occurrences"]) == 0


def test_tick_creator_revoked_or_buyer_inactive():
    state = _make_state()
    rule = {
        "frequency": "daily",
        "start_date": "2026-09-06",
        "time": "08:00",
        "timezone": "UTC",
    }
    save_ctx = _make_ctx(state, "p1", now=datetime(2026, 9, 6, 7, 0, tzinfo=UTC))
    series = shopping_series.handle(
        save_ctx, "series_save", {"name": "Milk", "rule": rule, "buyer": "b1"}
    )

    # Creator role demoted to child
    state["members"]["p1"]["role"] = "child"
    tick_ctx = _make_ctx(state, now=datetime(2026, 9, 6, 9, 0, tzinfo=UTC))
    shopping_series.tick(tick_ctx)
    assert len(series["occurrences"]) == 0

    # Creator restored to parent, but inactive
    state["members"]["p1"]["role"] = "parent"
    state["members"]["p1"]["active"] = False
    shopping_series.tick(tick_ctx)
    assert len(series["occurrences"]) == 0

    # Creator active, but buyer inactive
    state["members"]["p1"]["active"] = True
    state["members"]["b1"]["active"] = False
    shopping_series.tick(tick_ctx)
    assert len(series["occurrences"]) == 0

    # Buyer active again -> generates item
    state["members"]["b1"]["active"] = True
    shopping_series.tick(tick_ctx)
    assert len(series["occurrences"]) == 1
    assert series["occurrences"]["2026-09-06"]["state"] == "created"


def test_creation_partial_suppression_and_fully_purchased():
    state = _make_state()
    rule = {
        "frequency": "daily",
        "start_date": "2026-09-04",
        "time": "08:00",
        "timezone": "UTC",
        "catchup_hours": 48,
    }
    save_ctx = _make_ctx(state, "p1", now=datetime(2026, 9, 4, 7, 0, tzinfo=UTC))
    series = shopping_series.handle(
        save_ctx,
        "series_save",
        {
            "name": "Apples",
            "quantity": 5.0,
            "unit": "kg",
            "category": "Fruit",
            "store": "Farmer Market",
            "buyer": "b1",
            "rule": rule,
        },
    )

    # Day 1 tick: 2026-09-04 09:00 UTC
    t1 = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t1))
    assert "2026-09-04" in series["occurrences"]
    occ1 = series["occurrences"]["2026-09-04"]
    assert occ1["state"] == "created"
    item1_id = occ1["item_id"]
    item1 = state["shopping"][item1_id]
    assert item1["status"] == "approved"
    assert item1["creator"] == "p1"
    assert item1["name"] == "Apples"
    assert item1["quantity"] == 5.0
    assert item1["buyer"] == "b1"
    assert item1["series_id"] == series["id"]
    assert item1["occurrence_id"] == "2026-09-04"

    # Day 2 tick: item1 still open (not purchased) -> should record skipped_open
    t2 = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t2))
    assert "2026-09-05" in series["occurrences"]
    assert series["occurrences"]["2026-09-05"]["state"] == "skipped_open"
    assert series["occurrences"]["2026-09-05"]["item_id"] is None
    # No new shopping item created
    assert len(state["shopping"]) == 1

    # Partially purchase item1 (2 of 5 kg)
    shop_ctx = _make_ctx(state, "b1", now=datetime(2026, 9, 5, 12, 0, tzinfo=UTC))
    shopping.handle(shop_ctx, "purchase", {"id": item1_id, "quantity": 2.0})
    assert item1["purchased"] == 2.0
    assert item1["status"] == "approved"

    # Day 3 tick: item1 is still open (partially purchased) -> skipped_open again
    t3 = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t3))
    assert "2026-09-06" in series["occurrences"]
    assert series["occurrences"]["2026-09-06"]["state"] == "skipped_open"
    assert len(state["shopping"]) == 1

    # Fully purchase remaining (3 kg)
    shopping.handle(shop_ctx, "purchase", {"id": item1_id})
    assert item1["status"] == "purchased"

    # Add an unrelated shopping item with the SAME name manually
    unrelated_item = shopping.handle(
        _make_ctx(state, "p1", now=datetime(2026, 9, 6, 14, 0, tzinfo=UTC)),
        "add",
        {"name": "Apples", "quantity": 10},
    )
    assert unrelated_item["status"] == "approved"
    assert "series_id" not in unrelated_item

    # No open item belongs to this series now: create its next occurrence.
    t4 = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t4))
    assert "2026-09-07" in series["occurrences"]
    assert series["occurrences"]["2026-09-07"]["state"] == "created"
    item2_id = series["occurrences"]["2026-09-07"]["item_id"]
    assert item2_id != item1_id
    assert state["shopping"][item2_id]["series_id"] == series["id"]


def test_enable_no_old_backfill():
    state = _make_state()
    # Rule started days ago
    rule = {
        "frequency": "daily",
        "start_date": "2026-09-01",
        "time": "08:00",
        "timezone": "UTC",
        "catchup_hours": 48,
    }
    # Initially created disabled on Sept 1
    t0 = datetime(2026, 9, 1, 7, 0, tzinfo=UTC)
    series = shopping_series.handle(
        _make_ctx(state, "p1", now=t0),
        "series_save",
        {"name": "Juice", "rule": rule, "enabled": False},
    )

    # Now on Sept 6 10:00 UTC, series is enabled
    t_enable = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
    shopping_series.handle(
        _make_ctx(state, "p1", now=t_enable),
        "series_enable",
        {"id": series["id"], "revision": series["revision"], "enabled": True},
    )
    assert series["effective_at"] == t_enable.isoformat()

    # Tick at 11:00 UTC on Sept 6
    t_tick = datetime(2026, 9, 6, 11, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t_tick))

    # Nothing before the effective time (10:00 UTC) may be backfilled.
    assert len(series["occurrences"]) == 0
    assert len(state.get("shopping", {})) == 0

    # Tick next day on Sept 7 at 09:00 UTC
    t_next = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t_next))
    assert "2026-09-07" in series["occurrences"]
    assert series["occurrences"]["2026-09-07"]["state"] == "created"


def test_no_duplicate_on_retry_and_dst():
    state = _make_state()
    # Weekly on Sundays at 09:00 Kyiv time (Europe/Kiev)
    # 2026-09-06 is Sunday
    rule = {
        "frequency": "weekly",
        "start_date": "2026-09-06",
        "time": "09:00",
        "timezone": "Europe/Kiev",
        "weekdays": [6],
    }
    t_save = datetime(2026, 9, 6, 5, 0, tzinfo=UTC)
    series = shopping_series.handle(
        _make_ctx(state, "p1", now=t_save), "series_save", {"name": "Eggs", "rule": rule}
    )

    # Kyiv is UTC+3 in September, so 09:00 Kyiv = 06:00 UTC
    t_due = datetime(2026, 9, 6, 7, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t_due))
    assert "2026-09-06" in series["occurrences"]
    assert len(state["shopping"]) == 1

    # Retry tick immediately
    shopping_series.tick(_make_ctx(state, now=t_due))
    assert len(series["occurrences"]) == 1
    assert len(state["shopping"]) == 1

    # Later same day
    t_later = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
    shopping_series.tick(_make_ctx(state, now=t_later))
    assert len(series["occurrences"]) == 1
    assert len(state["shopping"]) == 1
