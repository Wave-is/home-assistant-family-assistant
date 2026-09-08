"""Exact opt-in purchase totals share the existing purchase transaction boundary."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.shopping_price import price
from custom_components.family_assistant.domain.validation import DomainError


@pytest.mark.parametrize(
    "total,expected",
    [
        ("0", "0"),
        ("0.0000", "0"),
        ("12.5000", "12.5"),
        ("0.0001", "0.0001"),
        ("999999999.0000", "999999999"),
    ],
)
def test_exact_bounded_decimal_canonicalization(total, expected):
    assert price({"total": total, "currency": "UAH"}) == {"total": expected, "currency": "UAH"}


@pytest.mark.parametrize(
    "total",
    [
        None,
        True,
        0,
        1.2,
        "",
        "NaN",
        "Infinity",
        "1e2",
        "01",
        "+1",
        "-0",
        "1.",
        ".1",
        "1,2",
        " 1",
        "1\n",
        "١",
        "１",
        "0.00001",
        "999999999.0001",
        "1000000000",
    ],
)
def test_invalid_decimal_never_coerced(total):
    with pytest.raises(DomainError):
        price({"total": total, "currency": "UAH"})


@pytest.mark.parametrize("currency", [None, True, "", "usd", "US", "USDD", "UАH", "USD\n", "<b>"])
def test_currency_is_three_ascii_uppercase_letters_not_an_iso_claim(currency):
    with pytest.raises(DomainError):
        price({"total": "1", "currency": currency})
    assert price({"total": "1", "currency": "ZZZ"})["currency"] == "ZZZ"


@pytest.mark.asyncio
async def test_partial_price_exact_replay_snapshot_and_unpriced_remainder(engine, now):
    item = await engine.execute(
        "parent",
        "shopping.add",
        {"name": "Rice", "quantity": 3, "unit": "kg", "store": "Market"},
        "add-price",
        now,
    )
    payload = {
        "id": item["id"],
        "revision": item["revision"],
        "quantity": 0.5,
        "price": {"total": "12.5000", "currency": "UAH"},
    }
    bought = await engine.execute("adult", "shopping.purchase", payload, "paid-once", now)
    expected = {
        "amount": 0.5,
        "purchased": 0.5,
        "remaining": 2.5,
        "price": {"total": "12.5", "currency": "UAH"},
        "name": "Rice",
        "unit": "kg",
        "store": "Market",
    }
    assert bought["history"][-1]["detail"] == expected
    before = engine.snapshot()
    assert await engine.execute("adult", "shopping.purchase", payload, "paid-once", now) == bought
    assert engine.snapshot() == before
    finished = await engine.execute(
        "parent",
        "shopping.purchase",
        {"id": item["id"], "revision": bought["revision"]},
        "remainder",
        now,
    )
    assert finished["status"] == "purchased"
    assert finished["history"][-2]["detail"] == expected
    assert "price" not in finished["history"][-1]["detail"]
    assert "price" not in finished, "A historical total must not become a reusable item/unit price"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "paid",
    [
        None,
        {},
        {"total": "1", "currency": "UAH", "card_number": "forbidden"},
        {"total": 1.2, "currency": "UAH"},
    ],
)
async def test_invalid_price_leaves_entire_state_unchanged(engine, now, paid):
    item = await engine.execute("parent", "shopping.add", {"name": "Rice"}, "add-bad", now)
    before = deepcopy(engine.snapshot())
    with pytest.raises(DomainError):
        await engine.execute(
            "parent",
            "shopping.purchase",
            {"id": item["id"], "revision": item["revision"], "price": paid},
            "bad",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_price_cannot_be_sneaked_into_approval_or_guest_purchase(engine, now):
    item = await engine.execute("child", "shopping.add", {"name": "Fruit"}, "child-price", now)
    payload = {
        "id": item["id"],
        "revision": item["revision"],
        "price": {"total": "0", "currency": "EUR"},
    }
    before = engine.snapshot()
    for actor, action in (("parent", "shopping.approve"), ("guest", "shopping.purchase")):
        with pytest.raises(DomainError):
            await engine.execute(actor, action, payload, "deny-" + actor, now)
        assert engine.snapshot() == before
