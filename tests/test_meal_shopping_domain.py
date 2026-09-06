"""Meal-plan shopping proposal tests with synthetic in-memory state only."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain import meal_plans, meal_shopping, pantry, shopping
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

BAD_REVISIONS = (None, True, 1.0, "1", 0, 2**53)


def context(state, actor_id, now, operation="meal-shopping-test"):
    return Context(state, state["members"][actor_id], now, operation)


def enabled_state(engine):
    state = engine.snapshot()
    for module in ("pantry", "shopping"):
        if module not in state["settings"]["modules"]:
            state["settings"]["modules"].append(module)
    return state


def ingredient(name="Rice", unit="kg", quantity=1):
    return {"name": name, "unit": unit, "quantity": quantity}


def published_plan(state, now, ingredients=None, *, title="School week"):
    created = meal_plans.handle(
        context(state, "parent", now, "create-plan"),
        "meal_save",
        {
            "week_start": "2026-09-07",
            "title": title,
            "entries": [
                {
                    "date": "2026-09-07",
                    "slot": "dinner",
                    "title": "Rice bowl",
                    "servings": 4,
                    "ingredients": ingredients if ingredients is not None else [ingredient()],
                }
            ],
            "note": "Private parent meal note",
        },
    )
    return meal_plans.handle(
        context(state, "parent", now, "publish-plan"),
        "meal_publish",
        {"id": created["id"], "revision": created["revision"]},
    )


def pantry_item(state, now, *, name="Rice", unit="kg", quantity=0.25, category="Food"):
    return pantry.handle(
        context(state, "parent", now, f"pantry:{name}:{unit}"),
        "item_save",
        {
            "name": name,
            "unit": unit,
            "quantity": quantity,
            "minimum_quantity": 0,
            "category": category,
        },
    )


def shopping_item(state, now, *, name="Rice", unit="kg", quantity=0.25):
    return shopping.handle(
        context(state, "parent", now, f"shopping:{name}:{unit}:{quantity}"),
        "add",
        {"name": name, "unit": unit, "quantity": quantity},
    )


def prepare(state, now, plan, operation="prepare"):
    return meal_shopping.handle(
        context(state, "parent", now, operation),
        "meal_shop_prepare",
        {"id": plan["id"], "revision": plan["revision"]},
    )


def accept(state, now, proposal, operation="accept"):
    return meal_shopping.handle(
        context(state, "parent", now, operation),
        "meal_shop_accept",
        {"id": proposal["id"], "revision": proposal["revision"]},
    )


def rejected_without_mutation(state, call, code):
    before = deepcopy(state)
    with pytest.raises(DomainError, match=code) as caught:
        call()
    assert caught.value.code == code
    assert state == before


def test_prepare_aggregates_normalized_names_exact_units_and_existing_coverage(engine, now):
    state = enabled_state(engine)
    plan = published_plan(
        state,
        now,
        [
            ingredient("Rice", "kg", 1),
            ingredient("  RICE ", "kg", 0.5),
            ingredient("Rice", "g", 500),
            ingredient("Oil", "l", 2),
        ],
    )
    pantry_item(state, now, name="rice", unit="kg", quantity=0.4)
    pantry_item(state, now, name="Rice", unit="g", quantity=500)
    open_item = shopping_item(state, now, name="RICE", unit="kg", quantity=0.25)
    shopping.handle(
        context(state, "parent", now, "partial-purchase"),
        "purchase",
        {"id": open_item["id"], "revision": open_item["revision"], "quantity": 0.05},
    )
    pantry_before = deepcopy(state["pantry"]["items"])
    shopping_before = deepcopy(state["shopping"])
    outbox_before = deepcopy(state["outbox"])

    proposal = prepare(state, now, plan)

    assert proposal["id"] == "MS000001"
    assert proposal["source_plan_id"] == plan["id"]
    assert proposal["source_revision"] == plan["revision"]
    assert proposal["plan_title"] == "School week"
    assert proposal["week_start"] == "2026-09-07"
    assert proposal["status"] == "open" and proposal["revision"] == 1
    assert proposal["created_by"] == "parent" and proposal["created_at"] == now.isoformat()
    assert proposal["history"] == [{"actor": "parent", "at": now.isoformat(), "action": "prepared"}]
    lines = {(line["name"].casefold(), line["unit"]): line for line in proposal["lines"]}
    assert lines[("rice", "kg")] == {
        "name": "Rice",
        "unit": "kg",
        "required": 1.5,
        "stock": 0.4,
        "open_shopping": 0.2,
        "deficit": 0.9,
        "quantity": 0.9,
    }
    assert lines[("rice", "g")]["quantity"] == 0
    assert lines[("rice", "g")]["deficit"] == 0
    assert lines[("oil", "l")]["quantity"] == 2
    assert len(proposal["input_fingerprint"]) == 64
    assert "Private parent meal note" not in proposal["input_fingerprint"]
    assert state["pantry"]["items"] == pantry_before
    assert state["shopping"] == shopping_before
    assert state["outbox"] == outbox_before


def test_prepare_is_lazy_reuses_same_snapshot_and_supersedes_changed_snapshot(engine, now):
    state = enabled_state(engine)
    plan = published_plan(state, now)
    assert "meal_shopping" not in state["pantry"]

    first = prepare(state, now, plan, "prepare:first")
    after_first = deepcopy(state)
    same = prepare(state, now, plan, "prepare:same")
    assert same["id"] == first["id"] and same["revision"] == first["revision"]
    assert state == after_first

    pantry_item(state, now, quantity=0.25)
    fresh = prepare(state, now, plan, "prepare:changed")
    assert fresh["id"] == "MS000002"
    assert first["status"] == "superseded" and first["revision"] == 2
    assert first["history"][-1]["action"] == "superseded"
    assert fresh["input_fingerprint"] != first["input_fingerprint"]


def test_accept_creates_only_positive_approved_lines_with_provenance(engine, now):
    state = enabled_state(engine)
    plan = published_plan(
        state,
        now,
        [ingredient("Rice", "kg", 1), ingredient("Oil", "l", 2)],
    )
    pantry_item(state, now, name="Oil", unit="l", quantity=2)
    proposal = prepare(state, now, plan)
    stock_before = deepcopy(state["pantry"]["items"])
    original_shopping = shopping_item(state, now, name="Soap", unit="pcs", quantity=2)
    # The unrelated item was added after preparation and therefore must not stale it.

    receipt = accept(state, now, proposal)

    assert receipt["status"] == "accepted"
    assert receipt["revision"] == 2 and receipt["transfer_count"] == 1
    assert [event["action"] for event in receipt["history"]] == ["prepared", "accepted"]
    rice = next(line for line in receipt["lines"] if line["name"] == "Rice")
    oil = next(line for line in receipt["lines"] if line["name"] == "Oil")
    assert rice["shopping_id"].startswith("S")
    assert "shopping_id" not in oil and oil["quantity"] == 0
    created = state["shopping"][rice["shopping_id"]]
    assert created["status"] == "approved" and created["purchased"] == 0
    assert created["note"] == ""
    assert created["meal_plan_id"] == plan["id"]
    assert created["meal_shopping_id"] == receipt["id"]
    assert created["quantity"] == 1 and created["unit"] == "kg"
    assert state["shopping"][original_shopping["id"]]["name"] == "Soap"
    assert state["pantry"]["items"] == stock_before
    assert state["outbox"] == {}


def test_sub_milli_deficit_is_disclosed_and_rounded_up_for_shopping(engine, now):
    state = enabled_state(engine)
    plan = published_plan(state, now, [ingredient(quantity=1)])
    shopping_item(state, now, quantity=0.999999)
    proposal = prepare(state, now, plan)
    assert proposal["lines"] == [
        {
            "name": "Rice",
            "unit": "kg",
            "required": 1,
            "stock": 0,
            "open_shopping": 0.999999,
            "deficit": 0.000001,
            "quantity": 0.001,
        }
    ]
    receipt = accept(state, now, proposal)
    created = state["shopping"][receipt["lines"][0]["shopping_id"]]
    assert created["quantity"] == 0.001


def test_fully_covered_accept_is_terminal_without_creating_shopping(engine, now):
    state = enabled_state(engine)
    plan = published_plan(state, now)
    pantry_item(state, now, quantity=1)
    proposal = prepare(state, now, plan)
    shopping_before = deepcopy(state["shopping"])
    receipt = accept(state, now, proposal)
    assert receipt["status"] == "covered"
    assert receipt["transfer_count"] == 0
    assert receipt["lines"][0]["quantity"] == 0
    assert state["shopping"] == shopping_before


def test_relevant_changes_conflict_but_unrelated_changes_do_not(engine, now):
    state = enabled_state(engine)
    plan = published_plan(state, now)
    matching = pantry_item(state, now, quantity=0.25)
    proposal = prepare(state, now, plan)
    pantry.handle(
        context(state, "parent", now, "matching-metadata-edit"),
        "item_save",
        {
            "id": matching["id"],
            "revision": matching["revision"],
            "category": "Dry goods",
        },
    )
    rejected_without_mutation(state, lambda: accept(state, now, proposal), "conflict")

    state = enabled_state(engine)
    plan = published_plan(state, now)
    proposal = prepare(state, now, plan)
    pantry_item(state, now, name="Beans", unit="tin", quantity=3)
    shopping_item(state, now, name="Soap", unit="pcs", quantity=2)
    assert accept(state, now, proposal)["status"] == "accepted"


def test_new_matching_shopping_and_source_plan_changes_conflict(engine, now):
    state = enabled_state(engine)
    plan = published_plan(state, now)
    proposal = prepare(state, now, plan)
    shopping_item(state, now, quantity=0.25)
    rejected_without_mutation(state, lambda: accept(state, now, proposal), "conflict")

    state = enabled_state(engine)
    plan = published_plan(state, now)
    proposal = prepare(state, now, plan)
    meal_plans.handle(
        context(state, "parent", now, "edit-source"),
        "meal_save",
        {"id": plan["id"], "revision": plan["revision"], "title": "Changed plan"},
    )
    rejected_without_mutation(state, lambda: accept(state, now, proposal), "conflict")


def test_one_terminal_transfer_per_plan_lifetime(engine, now):
    state = enabled_state(engine)
    plan = published_plan(state, now)
    proposal = prepare(state, now, plan)
    receipt = accept(state, now, proposal)
    shopping_count = len(state["shopping"])
    rejected_without_mutation(
        state,
        lambda: meal_shopping.handle(
            context(state, "parent", now, "second-accept"),
            "meal_shop_accept",
            {"id": receipt["id"], "revision": receipt["revision"]},
        ),
        "invalid_transition",
    )

    edited = meal_plans.handle(
        context(state, "parent", now, "edit-after-transfer"),
        "meal_save",
        {"id": plan["id"], "revision": plan["revision"], "title": "Revised title"},
    )
    republished = meal_plans.handle(
        context(state, "parent", now, "republish-after-transfer"),
        "meal_publish",
        {"id": edited["id"], "revision": edited["revision"]},
    )
    terminal = prepare(state, now, republished, "prepare-after-transfer")
    assert terminal["id"] == receipt["id"] and terminal["status"] == "accepted"
    assert len(state["shopping"]) == shopping_count


@pytest.mark.parametrize("bad_revision", BAD_REVISIONS)
def test_prepare_and_accept_require_strict_revisions(engine, now, bad_revision):
    state = enabled_state(engine)
    plan = published_plan(state, now)
    rejected_without_mutation(
        state,
        lambda: meal_shopping.handle(
            context(state, "parent", now),
            "meal_shop_prepare",
            {"id": plan["id"], "revision": bad_revision},
        ),
        "invalid_field",
    )
    proposal = prepare(state, now, plan)
    rejected_without_mutation(
        state,
        lambda: meal_shopping.handle(
            context(state, "parent", now),
            "meal_shop_accept",
            {"id": proposal["id"], "revision": bad_revision},
        ),
        "invalid_field",
    )


def test_roles_modules_fields_and_large_totals_are_rejected_without_mutation(engine, now):
    state = enabled_state(engine)
    plan = published_plan(state, now)
    for actor in ("adult", "child", "guest"):
        rejected_without_mutation(
            state,
            lambda actor=actor: meal_shopping.handle(
                context(state, actor, now),
                "meal_shop_prepare",
                {"id": plan["id"], "revision": plan["revision"]},
            ),
            "forbidden",
        )
    state["members"]["parent"]["active"] = False
    forged = Context(state, {"id": "parent", "role": "owner"}, now, "forged")
    rejected_without_mutation(
        state,
        lambda: meal_shopping.handle(
            forged, "meal_shop_prepare", {"id": plan["id"], "revision": plan["revision"]}
        ),
        "forbidden",
    )

    state = enabled_state(engine)
    plan = published_plan(state, now)
    mismatched = Context(state, {"id": "parent", "role": "child"}, now, "mismatch")
    rejected_without_mutation(
        state,
        lambda: meal_shopping.handle(
            mismatched,
            "meal_shop_prepare",
            {"id": plan["id"], "revision": plan["revision"]},
        ),
        "forbidden",
    )

    state = enabled_state(engine)
    plan = published_plan(state, now)
    for missing in ("pantry", "shopping"):
        state["settings"]["modules"].remove(missing)
        rejected_without_mutation(
            state,
            lambda: prepare(state, now, plan),
            "module_disabled",
        )
        state["settings"]["modules"].append(missing)
    rejected_without_mutation(
        state,
        lambda: meal_shopping.handle(
            context(state, "parent", now),
            "meal_shop_prepare",
            {"id": plan["id"], "revision": plan["revision"], "extra": True},
        ),
        "invalid_field",
    )

    state = enabled_state(engine)
    oversized = published_plan(
        state,
        now,
        [ingredient(quantity=600000), ingredient(name=" rice ", quantity=600000)],
    )
    rejected_without_mutation(state, lambda: prepare(state, now, oversized), "invalid_field")
    assert "meal_shopping" not in state["pantry"]


def test_view_is_parent_only_pure_and_redacts_internal_fingerprint(engine, now):
    state = enabled_state(engine)
    proposal = prepare(state, now, published_plan(state, now))
    before = deepcopy(state)
    owner_view = meal_shopping.view(state, state["members"]["owner"])
    parent_view = meal_shopping.view(state, state["members"]["parent"])
    assert owner_view == parent_view
    assert owner_view[0]["id"] == proposal["id"]
    assert "input_fingerprint" not in owner_view[0]
    for actor in ("adult", "child", "guest"):
        assert meal_shopping.view(state, state["members"][actor]) == []
    assert state == before
