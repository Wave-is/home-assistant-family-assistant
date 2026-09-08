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
    await verify_barcode(entry, owner, child, request)


async def verify_barcode(entry, owner, child, request):
    """Structural GTINs cross the real authenticated transport and Store boundary."""
    code = "00036000291452"
    payload = {"name": "Synthetic barcode cereal", "quantity": 2, "barcode": "036000291452"}
    item = await request(owner, "shopping.add", payload, "ha-gtin-add")
    assert item["barcode"] == code
    assert await request(owner, "shopping.add", payload, "ha-gtin-add") == item
    before = entry.runtime_data.engine.snapshot()
    await request(
        owner, "shopping.add", {**payload, "barcode": "036000291451"}, error="invalid_field"
    )
    assert entry.runtime_data.engine.snapshot() == before
    buy = {"id": item["id"], "revision": item["revision"], "quantity": 1}
    purchased = await request(child, "shopping.purchase", buy)
    assert purchased["history"][-1]["detail"]["barcode"] == code
    edit = {
        "id": item["id"],
        "revision": purchased["revision"],
        "name": item["name"],
        "category": "",
        "store": "",
        "note": "",
        "buyer": None,
        "barcode": "4006381333931",
    }
    changed = await request(owner, "shopping.edit", edit, "ha-gtin-edit")
    assert changed["barcode"] == "04006381333931" and changed["purchased"] == 1
    observed = next(
        row for row in (await request(child, "view", {}))["shopping"] if row["id"] == item["id"]
    )
    assert observed["barcode"] == changed["barcode"]
    assert observed["history"][-2]["detail"]["barcode"] == code
    assert await request(owner, "shopping.edit", edit, "ha-gtin-edit") == changed
    # The suite's normal entry reload later compares every shopping record.
    print(
        "PASS: actual HA barcode add/edit/read, purchase history, invalid rollback and exact replay"
    )
