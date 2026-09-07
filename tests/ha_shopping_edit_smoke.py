"""Real authenticated shopping metadata/replay checks with synthetic data."""


async def verify_shopping_edit(hass, entry, owner, child, child_id, request):
    item = await request(
        owner,
        "shopping.add",
        {"name": "Synthetic metadata item", "quantity": 3, "unit": "kg"},
    )
    item = await request(
        owner, "shopping.purchase", {"id": item["id"], "revision": item["revision"], "quantity": 1}
    )
    payload = {
        "id": item["id"],
        "revision": item["revision"],
        "name": item["name"],
        "category": "Synthetic category",
        "store": "Synthetic store",
        "note": "Synthetic household-visible note",
        "buyer": child_id,
    }
    await request(child, "shopping.edit", payload, error="forbidden")
    result = await request(owner, "shopping.edit", payload, "ha-shopping-edit")
    assert (result["quantity"], result["purchased"], result["unit"]) == (3, 1, "kg")
    assert await request(owner, "shopping.edit", payload, "ha-shopping-edit") == result
    await request(owner, "shopping.edit", payload, error="conflict")
    view = await request(child, "view", {})
    observed = next(row for row in view["shopping"] if row["id"] == item["id"])
    assert observed["note"] == payload["note"] and observed["revision"] == result["revision"]
    assert observed["history"][-1]["action"] == "edit"
    assert set(observed["history"][-1]["detail"]) == {"fields"}
    proposal = await request(child, "shopping.add", {"name": "Synthetic child proposal"})
    child_payload = {
        "id": proposal["id"],
        "revision": proposal["revision"],
        "name": "Synthetic revised child proposal",
        "category": "",
        "store": "",
        "note": "",
        "buyer": child_id,
    }
    revised = await request(child, "shopping.edit", child_payload)
    assert revised["status"] == "pending" and revised["creator"] == child_id
    print(
        "PASS: actual HA authenticated shopping metadata, child proposal, "
        "strict revisions and exact replay"
    )
