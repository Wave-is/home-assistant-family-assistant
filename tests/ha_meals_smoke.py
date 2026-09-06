"""Weekly meal plans through authenticated actual Home Assistant WebSockets."""

from copy import deepcopy


async def verify_meals_controls(hass, entry, owner, child, request):
    engine = entry.runtime_data.engine
    untouched = {key: deepcopy(engine.snapshot()[key]) for key in ("shopping", "tasks", "outbox")}
    stock = deepcopy(engine.snapshot()["pantry"]["items"])
    payload = {
        "week_start": "2026-09-07",
        "title": "Synthetic weekly menu",
        "note": "Synthetic parent-private meal note",
        "entries": [
            {
                "date": "2026-09-07",
                "slot": "dinner",
                "title": "Synthetic soup",
                "servings": 4,
                "ingredients": [{"name": "Carrot", "unit": "kg", "quantity": 0.5}],
            }
        ],
    }
    await request(child, "pantry.meal_save", payload, error="forbidden")
    plan = await request(owner, "pantry.meal_save", payload, "ha-meal-create")
    assert await request(owner, "pantry.meal_save", payload, "ha-meal-create") == plan
    assert plan["status"] == "draft"
    assert (await request(child, "view", {}))["pantry"]["meal_plans"] == []
    publish = {"id": plan["id"], "revision": plan["revision"]}
    await request(child, "pantry.meal_publish", publish, error="forbidden")
    published = await request(owner, "pantry.meal_publish", publish, "ha-meal-publish")
    assert published["status"] == "published"
    child_view = await request(child, "view", {})
    visible = child_view["pantry"]["meal_plans"]
    assert len(visible) == 1 and visible[0]["entries"] == payload["entries"]
    assert not {"note", "history", "created_by"} & visible[0].keys()
    assert payload["note"] not in str(child_view)
    await request(
        owner, "pantry.meal_save", {**publish, "title": "Stale overwrite"}, error="conflict"
    )
    edit = {"id": plan["id"], "revision": published["revision"], "title": "Revised menu"}
    revised = await request(owner, "pantry.meal_save", edit, "ha-meal-edit")
    assert revised["status"] == "draft" and revised["entries"] == payload["entries"]
    assert (await request(child, "view", {}))["pantry"]["meal_plans"] == []
    assert await request(owner, "pantry.meal_save", edit, "ha-meal-edit") == revised
    final = await request(
        owner,
        "pantry.meal_publish",
        {"id": plan["id"], "revision": revised["revision"]},
        "ha-meal-republish",
    )
    assert final["entries"][0]["ingredients"][0]["quantity"] == 0.5
    current = entry.runtime_data.engine.snapshot()
    assert current["pantry"]["items"] == stock
    assert all(current[key] == value for key, value in untouched.items())
    print("PASS: actual HA weekly menu publication, private drafts, stale edits and exact replay")
