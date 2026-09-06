"""Real authenticated menu-to-shopping preview and acceptance boundaries."""

from copy import deepcopy


async def verify_meal_shopping(hass, entry, owner, child, request):
    state = entry.runtime_data.engine.snapshot()
    plan = next(iter(state["pantry"]["meal_plans"].values()))
    stock = deepcopy(state["pantry"]["items"])
    existing = await request(
        owner, "shopping.add", {"name": "Carrot", "unit": "kg", "quantity": 0.2}
    )
    source = {"id": plan["id"], "revision": plan["revision"]}
    await request(child, "pantry.meal_shop_prepare", source, error="forbidden")
    preview = await request(owner, "pantry.meal_shop_prepare", source, "ha-meal-preview")
    assert preview["status"] == "open"
    assert preview["lines"][0]["quantity"] == 0.3
    assert preview["lines"][0]["open_shopping"] == 0.2
    assert (
        "input_fingerprint" not in (await request(owner, "view", {}))["pantry"]["meal_shopping"][0]
    )
    assert (await request(child, "view", {}))["pantry"]["meal_shopping"] == []
    await request(
        owner,
        "shopping.purchase",
        {"id": existing["id"], "revision": existing["revision"], "quantity": 0.1},
    )
    old = {"id": preview["id"], "revision": preview["revision"]}
    await request(owner, "pantry.meal_shop_accept", old, error="conflict")
    fresh = await request(owner, "pantry.meal_shop_prepare", source, "ha-meal-recalculate")
    assert fresh["id"] != preview["id"] and fresh["lines"][0]["quantity"] == 0.4
    accept = {"id": fresh["id"], "revision": fresh["revision"]}
    await request(child, "pantry.meal_shop_accept", accept, error="forbidden")
    result = await request(owner, "pantry.meal_shop_accept", accept, "ha-meal-shopping-accept")
    assert result["status"] == "accepted" and result["transfer_count"] == 1
    assert (
        await request(owner, "pantry.meal_shop_accept", accept, "ha-meal-shopping-accept") == result
    )
    sealed = await request(owner, "pantry.meal_shop_prepare", source, "ha-meal-sealed")
    assert sealed["id"] == result["id"] and sealed["status"] == "accepted"
    current = entry.runtime_data.engine.snapshot()
    assert current["pantry"]["items"] == stock
    created = current["shopping"][result["lines"][0]["shopping_id"]]
    assert created["quantity"] == 0.4 and created["purchased"] == 0
    assert created["status"] == "approved" and created["note"] == ""
    assert created["meal_plan_id"] == plan["id"]
    assert created["meal_shopping_id"] == result["id"]
    assert "Synthetic parent-private meal note" not in str(await request(child, "view", {}))
    print(
        "PASS: actual HA meal shopping review, changed coverage conflict, "
        "accepted receipt and privacy"
    )
