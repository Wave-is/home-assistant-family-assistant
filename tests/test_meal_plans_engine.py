"""Weekly meal plans through the real Engine transaction and privacy boundaries."""

import asyncio
from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def meal_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"].append("pantry")
    return Engine(state, store.save)


def entry(
    *,
    date="2026-09-07",
    slot="dinner",
    title="Synthetic soup",
    servings=4,
    ingredients=None,
):
    return {
        "date": date,
        "slot": slot,
        "title": title,
        "servings": servings,
        "ingredients": (
            [{"name": "Synthetic beans", "unit": "g", "quantity": 250}]
            if ingredients is None
            else ingredients
        ),
    }


def meal_payload(**changes):
    payload = {
        "week_start": "2026-09-07",
        "title": "Synthetic weekly menu",
        "note": "Private preparation note",
        "entries": [entry()],
    }
    payload.update(changes)
    return payload


async def save_meal(engine, now, operation="meal-save", **changes):
    return await engine.execute(
        "parent", "pantry.meal_save", meal_payload(**changes), operation, now
    )


def meal_state(engine):
    return engine.snapshot()["pantry"]["meal_plans"]


def assert_no_write(engine, store, before, writes):
    assert engine.snapshot() == before
    assert store.calls == writes


@pytest.mark.asyncio
async def test_create_publish_role_projection_and_no_inventory_side_effects(
    meal_engine, store, now
):
    before = meal_engine.snapshot()
    created = await save_meal(meal_engine, now)
    assert created["id"] == "MP000001"
    assert created["status"] == "draft"
    assert created["created_by"] == "parent"
    assert created["revision"] == 1
    assert meal_engine.view("parent", now=now)["pantry"]["meal_plans"] == [created]
    assert meal_engine.view("owner", now=now)["pantry"]["meal_plans"] == [created]
    assert meal_engine.view("adult", now=now)["pantry"]["meal_plans"] == []
    assert meal_engine.view("child", now=now)["pantry"]["meal_plans"] == []
    assert "pantry" not in meal_engine.view("guest", now=now)

    published = await meal_engine.execute(
        "parent",
        "pantry.meal_publish",
        {"id": created["id"], "revision": created["revision"]},
        "meal-publish",
        now,
    )
    assert published["status"] == "published" and published["revision"] == 2
    for actor in ("adult", "child"):
        visible = meal_engine.view(actor, now=now)["pantry"]["meal_plans"]
        assert len(visible) == 1
        assert visible[0]["id"] == created["id"]
        assert "note" not in visible[0]
        assert "history" not in visible[0]
        assert "created_by" not in visible[0]

    after = meal_engine.snapshot()
    for bucket in ("items", "suggestions"):
        assert after["pantry"].get(bucket, {}) == before["pantry"].get(bucket, {})
    assert after["shopping"] == before["shopping"]
    assert after["outbox"] == before["outbox"]
    assert store.calls == 2


@pytest.mark.asyncio
async def test_partial_edit_preserves_fields_and_published_edit_becomes_private_draft(
    meal_engine, now
):
    created = await save_meal(meal_engine, now)
    published = await meal_engine.execute(
        "parent",
        "pantry.meal_publish",
        {"id": created["id"], "revision": created["revision"]},
        "publish",
        now,
    )
    edited = await meal_engine.execute(
        "parent",
        "pantry.meal_save",
        {"id": published["id"], "revision": published["revision"], "title": "New title"},
        "edit",
        now,
    )
    assert edited["revision"] == published["revision"] + 1
    assert edited["status"] == "draft"
    assert edited["title"] == "New title"
    for field in ("week_start", "entries", "note", "created_by"):
        assert edited[field] == published[field]
    assert meal_engine.view("adult", now=now)["pantry"]["meal_plans"] == []
    assert meal_engine.view("child", now=now)["pantry"]["meal_plans"] == []


@pytest.mark.asyncio
async def test_only_one_published_plan_per_week_until_first_returns_to_draft(
    meal_engine, store, now
):
    first = await save_meal(meal_engine, now, operation="first", title="First")
    second = await save_meal(meal_engine, now, operation="second", title="Second")
    first = await meal_engine.execute(
        "parent",
        "pantry.meal_publish",
        {"id": first["id"], "revision": first["revision"]},
        "publish-first",
        now,
    )
    before = meal_engine.snapshot()
    writes = store.calls
    with pytest.raises(DomainError, match="conflict"):
        await meal_engine.execute(
            "parent",
            "pantry.meal_publish",
            {"id": second["id"], "revision": second["revision"]},
            "publish-second-conflict",
            now,
        )
    assert meal_engine.snapshot() == before
    assert store.calls == writes

    first = await meal_engine.execute(
        "parent",
        "pantry.meal_save",
        {"id": first["id"], "revision": first["revision"], "note": "Revising"},
        "revise-first",
        now,
    )
    assert first["status"] == "draft"
    second = await meal_engine.execute(
        "parent",
        "pantry.meal_publish",
        {"id": second["id"], "revision": second["revision"]},
        "publish-second",
        now,
    )
    assert second["status"] == "published"


@pytest.mark.asyncio
async def test_archive_requires_reason_is_immutable_and_survives_restart(meal_engine, store, now):
    created = await save_meal(meal_engine, now)
    with pytest.raises(DomainError, match="invalid_field"):
        await meal_engine.execute(
            "parent",
            "pantry.meal_archive",
            {"id": created["id"], "revision": created["revision"]},
            "archive-no-reason",
            now,
        )
    archived = await meal_engine.execute(
        "parent",
        "pantry.meal_archive",
        {"id": created["id"], "revision": created["revision"], "reason": "Plans changed"},
        "archive",
        now,
    )
    assert archived["status"] == "archived"
    restarted = Engine(deepcopy(store.value), store.save)
    assert meal_state(restarted)[created["id"]] == archived
    for action, payload in (
        (
            "pantry.meal_save",
            {"id": archived["id"], "revision": archived["revision"], "title": "Resurrect"},
        ),
        (
            "pantry.meal_publish",
            {"id": archived["id"], "revision": archived["revision"]},
        ),
        (
            "pantry.meal_archive",
            {"id": archived["id"], "revision": archived["revision"], "reason": "Again"},
        ),
    ):
        before = restarted.snapshot()
        with pytest.raises(DomainError):
            await restarted.execute("parent", action, payload, f"immutable-{action}", now)
        assert restarted.snapshot() == before


@pytest.mark.asyncio
async def test_concurrent_duplicate_operation_frozen_receipt_and_restart_replay(
    meal_engine, store, now
):
    payload = meal_payload()
    results = await asyncio.gather(
        *[
            meal_engine.execute("parent", "pantry.meal_save", payload, "same-meal", now)
            for _ in range(12)
        ]
    )
    assert all(result == results[0] for result in results)
    assert len(meal_state(meal_engine)) == 1
    assert store.calls == 1

    receipt = results[0]
    receipt["title"] = "Tampered result"
    meal_engine.snapshot()["pantry"]["meal_plans"][results[0]["id"]]["title"] = "Tampered copy"
    restarted = Engine(deepcopy(store.value), store.save)
    writes = store.calls
    replay = await restarted.execute("parent", "pantry.meal_save", payload, "same-meal", now)
    assert replay["title"] == "Synthetic weekly menu"
    assert store.calls == writes
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await restarted.execute(
            "parent",
            "pantry.meal_save",
            meal_payload(title="Different"),
            "same-meal",
            now,
        )


@pytest.mark.asyncio
async def test_atomic_batch_rolls_back_meal_plan_creation(meal_engine, store, now):
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError):
        await meal_engine.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "pantry.meal_save", "payload": meal_payload(title="Valid")},
                    {
                        "action": "pantry.meal_save",
                        "payload": meal_payload(week_start="2026-09-08"),
                    },
                ]
            },
            "meal-batch",
            now,
        )
    assert_no_write(meal_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["adult", "child", "guest"])
async def test_non_parent_cannot_mutate_meal_plans(meal_engine, store, now, actor):
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="forbidden"):
        await meal_engine.execute(
            actor, "pantry.meal_save", meal_payload(), f"forbidden-{actor}", now
        )
    assert_no_write(meal_engine, store, before, writes)


@pytest.mark.asyncio
async def test_active_owner_can_create_meal_plan(meal_engine, now):
    created = await meal_engine.execute(
        "owner", "pantry.meal_save", meal_payload(title="Owner menu"), "owner-meal", now
    )
    assert created["created_by"] == "owner"
    assert created["title"] == "Owner menu"


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["module", "role", "inactive"])
async def test_exact_receipt_replay_rechecks_current_authority(meal_engine, store, now, revocation):
    payload = meal_payload()
    result = await meal_engine.execute(
        "parent", "pantry.meal_save", payload, f"saved-{revocation}", now
    )
    assert result["status"] == "draft"
    if revocation == "module":
        settings = meal_engine.snapshot()["settings"]
        await meal_engine.execute(
            "owner",
            "settings.save",
            {
                "name": settings["name"],
                "language": settings["language"],
                "modules": [m for m in settings["modules"] if m != "pantry"],
            },
            "disable-pantry",
            now,
        )
        expected = "module_disabled"
    else:
        member = meal_engine.snapshot()["members"]["parent"]
        await meal_engine.execute(
            "owner",
            "members.save",
            {
                "id": "parent",
                "revision": member["revision"],
                "name": member["name"],
                "role": "adult" if revocation == "role" else "parent",
                "active": revocation != "inactive",
            },
            f"revoke-{revocation}",
            now,
        )
        expected = "forbidden"
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match=expected):
        await meal_engine.execute("parent", "pantry.meal_save", payload, f"saved-{revocation}", now)
    assert_no_write(meal_engine, store, before, writes)


INVALID_REVISIONS = [None, True, False, 1.0, "1", 0, -1, 2**53]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["meal_save", "meal_publish", "meal_archive"])
@pytest.mark.parametrize("bad_revision", ["missing", *INVALID_REVISIONS])
async def test_existing_actions_reject_missing_or_invalid_revision_without_write(
    meal_engine, store, now, action, bad_revision
):
    created = await save_meal(meal_engine, now)
    payload = {"id": created["id"]}
    if action == "meal_save":
        payload["title"] = "Edit"
    if action == "meal_archive":
        payload["reason"] = "No longer needed"
    if bad_revision != "missing":
        payload["revision"] = bad_revision
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await meal_engine.execute(
            "parent", f"pantry.{action}", payload, f"bad-{action}-{bad_revision!r}", now
        )
    assert_no_write(meal_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["meal_save", "meal_publish", "meal_archive"])
async def test_stale_positive_revision_conflicts_without_write(meal_engine, store, now, action):
    created = await save_meal(meal_engine, now)
    current = await meal_engine.execute(
        "parent",
        "pantry.meal_save",
        {"id": created["id"], "revision": created["revision"], "note": "Changed"},
        "advance",
        now,
    )
    payload = {"id": current["id"], "revision": created["revision"]}
    if action == "meal_save":
        payload["title"] = "Stale edit"
    if action == "meal_archive":
        payload["reason"] = "Stale archive"
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="conflict"):
        await meal_engine.execute("parent", f"pantry.{action}", payload, f"stale-{action}", now)
    assert_no_write(meal_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"week_start": "2026-09-08"},
        {"week_start": "2026-02-30"},
        {"week_start": "2026-9-7"},
        {"week_start": None},
        {"title": ""},
        {"title": "x" * 121},
        {"note": "x" * 501},
        {"entries": []},
        {"entries": [entry()] * 29},
        {"entries": [entry(date="2026-09-06")]},
        {"entries": [entry(date="2026-09-14")]},
        {"entries": [entry(date="2026-02-30")]},
        {"entries": [entry(slot="brunch")]},
        {"entries": [entry(title="")]},
        {"entries": [entry(title="x" * 121)]},
        {"entries": [entry(servings=True)]},
        {"entries": [entry(servings=4.0)]},
        {"entries": [entry(servings="4")]},
        {"entries": [entry(servings=0)]},
        {"entries": [entry(servings=51)]},
        {"entries": [entry(ingredients=[{"name": "x", "unit": "g", "quantity": 1}] * 21)]},
        {"entries": [entry(), entry(title="Duplicate")]},
        {"entries": [{key: value for key, value in entry().items() if key != "title"}]},
        {"entries": [{**entry(), "extra": True}]},
        {"extra": True},
    ],
)
async def test_plan_and_entry_limits_reject_atomically(meal_engine, store, now, changes):
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await save_meal(meal_engine, now, operation=f"invalid-{writes}", **changes)
    assert_no_write(meal_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ingredient",
    [
        {},
        {"name": "x", "unit": "g"},
        {"name": "x", "unit": "g", "quantity": 1, "extra": True},
        {"name": "", "unit": "g", "quantity": 1},
        {"name": "x" * 121, "unit": "g", "quantity": 1},
        {"name": "x", "unit": "", "quantity": 1},
        {"name": "x", "unit": "u" * 25, "quantity": 1},
        {"name": "x", "unit": "g", "quantity": True},
        {"name": "x", "unit": "g", "quantity": "1"},
        {"name": "x", "unit": "g", "quantity": 0},
        {"name": "x", "unit": "g", "quantity": -1},
        {"name": "x", "unit": "g", "quantity": 1_000_000.001},
        {"name": "x", "unit": "g", "quantity": 1.0001},
        {"name": "x", "unit": "g", "quantity": float("inf")},
        {"name": "x", "unit": "g", "quantity": float("nan")},
    ],
)
async def test_ingredient_shape_and_number_limits_reject_atomically(
    meal_engine, store, now, ingredient
):
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await save_meal(
            meal_engine,
            now,
            operation=f"invalid-ingredient-{writes}",
            entries=[entry(ingredients=[ingredient])],
        )
    assert_no_write(meal_engine, store, before, writes)


@pytest.mark.asyncio
async def test_all_slots_week_edges_decimal_boundary_and_total_ingredient_limit(meal_engine, now):
    slots = ("breakfast", "lunch", "dinner", "snack")
    dates = [f"2026-09-{day:02}" for day in range(7, 14)]
    entries = [
        entry(
            date=date,
            slot=slot,
            title=f"Meal {date} {slot}",
            servings=50,
            ingredients=[
                {"name": f"Ingredient {index}", "unit": "unit", "quantity": 1_000_000}
                for index in range(4 if position < 16 else 3)
            ],
        )
        for position, (date, slot) in enumerate(
            date_slot for date in dates for date_slot in [(date, slot) for slot in slots]
        )
    ]
    assert sum(len(item["ingredients"]) for item in entries) == 100
    result = await save_meal(meal_engine, now, entries=entries)
    assert len(result["entries"]) == 28


@pytest.mark.asyncio
async def test_more_than_one_hundred_total_ingredients_is_rejected(meal_engine, store, now):
    slots = ("breakfast", "lunch", "dinner", "snack")
    entries = []
    for index in range(21):
        entries.append(
            entry(
                date=f"2026-09-{7 + index // 4:02}",
                slot=slots[index % 4],
                title=f"Meal {index}",
                ingredients=[
                    {"name": f"Ingredient {part}", "unit": "g", "quantity": 1} for part in range(5)
                ],
            )
        )
    before, writes = meal_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await save_meal(meal_engine, now, entries=entries)
    assert_no_write(meal_engine, store, before, writes)


@pytest.mark.asyncio
async def test_creation_rejects_id_or_revision_and_valid_quantity_three_decimals(
    meal_engine, store, now
):
    for extra in ({"id": "MP999999"}, {"revision": 1}):
        before, writes = meal_engine.snapshot(), store.calls
        with pytest.raises(DomainError, match="invalid_field"):
            await save_meal(meal_engine, now, operation=f"bad-new-{tuple(extra)}", **extra)
        assert_no_write(meal_engine, store, before, writes)
    result = await save_meal(
        meal_engine,
        now,
        operation="decimal-boundary",
        entries=[
            entry(ingredients=[{"name": "Synthetic spice", "unit": "g", "quantity": 0.001}]),
            entry(date="2026-09-08", ingredients=[]),
        ],
    )
    assert result["entries"][0]["ingredients"][0]["quantity"] == 0.001
    assert result["entries"][1]["ingredients"] == []
