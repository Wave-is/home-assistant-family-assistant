"""Unit tests for the price_watch domain module (no I/O, no HA)."""

from __future__ import annotations

import pytest

from custom_components.family_assistant.domain.price_watch import (
    _parse_price_float,
    _price_dropped,
)
from custom_components.family_assistant.domain.validation import DomainError

# ── add ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_watcher_creates_record(engine, now):
    result = await engine.execute(
        "parent",
        "price_watch.add",
        {"url": "https://example.com/product/1"},
        "pw-add",
        now,
    )
    assert result["url"] == "https://example.com/product/1"
    assert result["availability"] == "unknown"
    assert result["price_text"] == ""
    assert result["history"] == []
    assert result["id"].startswith("PW")
    snap = engine.snapshot()
    assert result["id"] in snap["price_watches"]


@pytest.mark.asyncio
async def test_add_watcher_with_all_fields(engine, now):
    result = await engine.execute(
        "parent",
        "price_watch.add",
        {
            "url": "https://rozetka.com.ua/12345",
            "name": "Samsung TV 55",
            "currency": "UAH",
            "notify_drop": True,
            "notify_available": False,
        },
        "pw-add-full",
        now,
    )
    assert result["name"] == "Samsung TV 55"
    assert result["currency"] == "UAH"
    assert result["notify_drop"] is True
    assert result["notify_available"] is False


@pytest.mark.asyncio
async def test_add_duplicate_url_rejected(engine, now):
    url = "https://example.com/product/1"
    await engine.execute("parent", "price_watch.add", {"url": url}, "pw-add-1", now)
    before = engine.snapshot()
    with pytest.raises(DomainError) as exc_info:
        await engine.execute("parent", "price_watch.add", {"url": url}, "pw-add-2", now)
    assert exc_info.value.code == "conflict"
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_add_invalid_url_rejected(engine, now):
    for bad_url in ("not-a-url", "ftp://example.com", "", "javascript:void(0)"):
        before = engine.snapshot()
        with pytest.raises(DomainError):
            await engine.execute("parent", "price_watch.add", {"url": bad_url}, "pw-bad", now)
        assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_child_cannot_add_watcher(engine, now):
    before = engine.snapshot()
    with pytest.raises(DomainError) as exc_info:
        await engine.execute(
            "child",
            "price_watch.add",
            {"url": "https://example.com/product/1"},
            "pw-child",
            now,
        )
    assert exc_info.value.code == "forbidden"
    assert engine.snapshot() == before


# ── edit ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_watcher_name_and_currency(engine, now):
    watcher = await engine.execute(
        "parent",
        "price_watch.add",
        {"url": "https://example.com/p/1"},
        "pw-add",
        now,
    )
    edited = await engine.execute(
        "parent",
        "price_watch.edit",
        {
            "id": watcher["id"],
            "revision": watcher["revision"],
            "name": "New Name",
            "currency": "USD",
        },
        "pw-edit",
        now,
    )
    assert edited["name"] == "New Name"
    assert edited["currency"] == "USD"


@pytest.mark.asyncio
async def test_edit_stale_revision_rejected(engine, now):
    watcher = await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/p/stale"}, "pw-add", now
    )
    before = engine.snapshot()
    with pytest.raises(DomainError) as exc_info:
        await engine.execute(
            "parent",
            "price_watch.edit",
            {"id": watcher["id"], "revision": 999, "name": "X"},
            "pw-edit-stale",
            now,
        )
    assert exc_info.value.code == "conflict"
    assert engine.snapshot() == before


# ── remove ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_watcher_deletes_record(engine, now):
    watcher = await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/p/del"}, "pw-add", now
    )
    await engine.execute(
        "parent",
        "price_watch.remove",
        {"id": watcher["id"], "revision": watcher["revision"]},
        "pw-remove",
        now,
    )
    assert watcher["id"] not in engine.snapshot()["price_watches"]


@pytest.mark.asyncio
async def test_remove_nonexistent_rejected(engine, now):
    with pytest.raises(DomainError) as exc_info:
        await engine.execute(
            "parent",
            "price_watch.remove",
            {"id": "PW999999", "revision": 1},
            "pw-remove-bad",
            now,
        )
    assert exc_info.value.code == "not_found"


# ── record ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_stores_price_and_availability(engine, now):
    watcher = await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/p/rec"}, "pw-add", now
    )
    result = await engine.execute(
        "parent",
        "price_watch.record",
        {
            "id": watcher["id"],
            "price_text": "1 299,00",
            "currency": "UAH",
            "availability": "in_stock",
        },
        "pw-rec",
        now,
    )
    assert result["price_text"] == "1 299,00"
    assert result["currency"] == "UAH"
    assert result["availability"] == "in_stock"
    assert len(result["history"]) == 1
    assert result["last_error"] is None


@pytest.mark.asyncio
async def test_record_error_stored_without_clearing_price(engine, now):
    watcher = await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/p/err"}, "pw-add", now
    )
    # First record a price
    await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "price_text": "500", "currency": "UAH", "availability": "in_stock"},
        "pw-rec-ok",
        now,
    )
    # Then record an error
    updated = await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "error": "timeout"},
        "pw-rec-err",
        now,
    )
    assert updated["last_error"] == "timeout"
    # Price should still be there from previous successful fetch
    assert updated["price_text"] == "500"


@pytest.mark.asyncio
async def test_record_price_drop_emits_notification(engine, now):
    watcher = await engine.execute(
        "parent",
        "price_watch.add",
        {"url": "https://example.com/p/drop", "notify_drop": True},
        "pw-add",
        now,
    )
    await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "price_text": "2000", "currency": "UAH", "availability": "in_stock"},
        "pw-rec-1",
        now,
    )
    snap_before_outbox = len(engine.snapshot()["outbox"])
    await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "price_text": "1500", "currency": "UAH", "availability": "in_stock"},
        "pw-rec-2",
        now,
    )
    outbox = engine.snapshot()["outbox"]
    assert len(outbox) > snap_before_outbox
    keys = [v["key"] for v in outbox.values()]
    assert "price_watch_drop" in keys


@pytest.mark.asyncio
async def test_record_no_notification_when_price_rises(engine, now):
    watcher = await engine.execute(
        "parent",
        "price_watch.add",
        {"url": "https://example.com/p/rise", "notify_drop": True},
        "pw-add",
        now,
    )
    await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "price_text": "1000", "currency": "UAH", "availability": "in_stock"},
        "pw-rec-1",
        now,
    )
    outbox_before = dict(engine.snapshot()["outbox"])
    await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "price_text": "1200", "currency": "UAH", "availability": "in_stock"},
        "pw-rec-2",
        now,
    )
    # No new outbox entries for price_watch_drop
    new_entries = {
        k: v
        for k, v in engine.snapshot()["outbox"].items()
        if k not in outbox_before and v.get("key") == "price_watch_drop"
    }
    assert not new_entries


@pytest.mark.asyncio
async def test_record_available_notification_when_back_in_stock(engine, now):
    watcher = await engine.execute(
        "parent",
        "price_watch.add",
        {"url": "https://example.com/p/avail", "notify_available": True},
        "pw-add",
        now,
    )
    await engine.execute(
        "parent",
        "price_watch.record",
        {
            "id": watcher["id"],
            "price_text": "500",
            "currency": "UAH",
            "availability": "out_of_stock",
        },
        "pw-rec-1",
        now,
    )
    await engine.execute(
        "parent",
        "price_watch.record",
        {
            "id": watcher["id"],
            "price_text": "500",
            "currency": "UAH",
            "availability": "in_stock",
        },
        "pw-rec-2",
        now,
    )
    keys = [v["key"] for v in engine.snapshot()["outbox"].values()]
    assert "price_watch_available" in keys


@pytest.mark.asyncio
async def test_history_capped_at_30(engine, now):
    watcher = await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/p/hist"}, "pw-add", now
    )
    for i in range(35):
        await engine.execute(
            "parent",
            "price_watch.record",
            {
                "id": watcher["id"],
                "price_text": str(i * 10),
                "currency": "UAH",
                "availability": "in_stock",
            },
            f"pw-rec-{i}",
            now,
        )
    snap = engine.snapshot()["price_watches"][watcher["id"]]
    assert len(snap["history"]) == 30


# ── price parsing helpers ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text_val,expected",
    [
        ("1234.56", 1234.56),
        ("1 234,56", 1234.56),
        ("1.234,56", 1234.56),
        ("500", 500.0),
        ("0", 0.0),
        ("", None),
        ("abc", None),
    ],
)
def test_parse_price_float(text_val, expected):

    result = _parse_price_float(text_val)
    if expected is None:
        assert result is None
    else:
        assert abs(result - expected) < 0.01


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("1000", "900", True),
        ("1000", "1000", False),
        ("1000", "1100", False),
        ("", "900", False),
        ("1000", "", False),
        ("abc", "900", False),
    ],
)
def test_price_dropped(old, new, expected):
    assert _price_dropped(old, new) == expected


# ── idempotency ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_operation_id_is_idempotent(engine, now):
    """Replaying the same operation_id must not double-apply the command."""
    await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/p/idem"}, "pw-add-idem", now
    )
    snap1 = engine.snapshot()
    # Replaying the exact same operation with same id → idempotent
    await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/p/idem"}, "pw-add-idem", now
    )
    assert engine.snapshot() == snap1


# ── telegram commands & view projection ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_price_watch_view_projection(engine, now):
    watcher = await engine.execute(
        "parent", "price_watch.add", {"url": "https://example.com/proj", "name": "Projected"}, "pw-proj", now
    )
    view = engine.view("parent", now=now)
    assert "price_watches" in view
    assert any(w["id"] == watcher["id"] and w["name"] == "Projected" for w in view["price_watches"])


@pytest.mark.asyncio
async def test_telegram_watch_and_watchlist(engine, now):
    from custom_components.family_assistant.telegram.router import route

    # Test adding via /watch URL | Name
    resp = await route(engine, "parent", "/watch https://example.com/watch1 | My Watch 1", "op-w1", now)
    assert "PW" in resp
    assert "My Watch 1" in resp

    # Test /watchlist listing
    list_resp = await route(engine, "parent", "/watchlist", "op-list", now)
    assert "My Watch 1" in list_resp
    assert "https://example.com/watch1" in list_resp

    # Test /prices alias
    prices_resp = await route(engine, "parent", "/prices", "op-prices", now)
    assert list_resp == prices_resp

    # Test direct URL input
    direct_resp = await route(engine, "parent", "https://example.com/watch2 | My Watch 2", "op-w2", now)
    assert "PW" in direct_resp
    assert "My Watch 2" in direct_resp

    # Extract ID and test /unwatch
    snap = engine.snapshot()["price_watches"]
    w1_id = next(k for k, v in snap.items() if v["url"] == "https://example.com/watch1")
    unwatch_resp = await route(engine, "parent", f"/unwatch {w1_id}", "op-unw", now)
    assert "🗑" in unwatch_resp
    assert w1_id in unwatch_resp

    # Confirm deleted from watchlist
    after_list = await route(engine, "parent", "/watchlist", "op-list2", now)
    assert "My Watch 1" not in after_list
    assert "My Watch 2" in after_list
