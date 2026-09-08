"""Authenticated optional purchase totals through actual HA WebSocket commands."""


async def verify_shopping_price(entry, owner, child, request):
    item = await request(
        owner,
        "shopping.add",
        {"name": "Synthetic priced oats", "quantity": 3, "unit": "kg", "store": "Synthetic market"},
    )
    payload = {
        "id": item["id"],
        "revision": item["revision"],
        "quantity": 0.5,
        "price": {"total": "1.2340", "currency": "EUR"},
    }
    bought = await request(owner, "shopping.purchase", payload, "ha-price-once")
    assert bought["history"][-1]["detail"]["price"] == {"total": "1.234", "currency": "EUR"}
    assert bought["history"][-1]["detail"]["amount"] == 0.5
    before = entry.runtime_data.engine.snapshot()
    assert await request(owner, "shopping.purchase", payload, "ha-price-once") == bought
    assert entry.runtime_data.engine.snapshot() == before
    await request(
        owner,
        "shopping.purchase",
        {
            "id": item["id"],
            "revision": bought["revision"],
            "price": {"total": 1.5, "currency": "EUR"},
        },
        error="invalid_field",
    )
    assert entry.runtime_data.engine.snapshot() == before
    observed = next(
        row for row in (await request(child, "view", {}))["shopping"] if row["id"] == item["id"]
    )
    assert observed["history"] == bought["history"]
    free = await request(
        child,
        "shopping.purchase",
        {
            "id": item["id"],
            "revision": bought["revision"],
            "quantity": 0.25,
            "price": {"total": "0", "currency": "USD"},
        },
    )
    assert free["history"][-2]["detail"]["price"]["currency"] == "EUR"
    assert free["history"][-1]["detail"]["price"] == {"total": "0", "currency": "USD"}
    finished = await request(
        owner, "shopping.purchase", {"id": item["id"], "revision": free["revision"]}
    )
    assert "price" not in finished["history"][-1]["detail"]
    print(
        "PASS: actual HA exact optional purchase totals, shared history, "
        "invalid-input rollback and replay"
    )
