"""Weekly menu domain tests with synthetic household state only."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import meal_plans
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

SLOTS = ("breakfast", "lunch", "dinner", "snack")
BAD_REVISIONS = (None, True, 1.0, "1", 0, 2**53)


def context(state, actor_id, now, operation="meal-test"):
    return Context(state, state["members"][actor_id], now, operation)


def enabled_state(engine):
    state = engine.snapshot()
    if "pantry" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("pantry")
    return state


def ingredient(name="Rice", unit="g", quantity=250):
    return {"name": name, "unit": unit, "quantity": quantity}


def entry(day="2026-09-07", slot="dinner", **changes):
    return {
        "date": day,
        "slot": slot,
        "title": "Rice bowl",
        "servings": 4,
        "ingredients": [ingredient()],
        **changes,
    }


def plan_payload(week="2026-09-07", **changes):
    return {
        "week_start": week,
        "title": "Week menu",
        "entries": [entry(week)],
        "note": "Parent planning note",
        **changes,
    }


def save(state, now, *, actor="parent", week="2026-09-07", **changes):
    return meal_plans.handle(context(state, actor, now), "meal_save", plan_payload(week, **changes))


def assert_rejected_without_mutation(state, call, code="invalid_field"):
    before = deepcopy(state)
    with pytest.raises(DomainError, match=code) as caught:
        call()
    assert caught.value.code == code
    assert state == before


def test_create_is_lazy_parent_only_and_has_immutable_audit_history(engine, now):
    state = enabled_state(engine)
    assert state["pantry"] == {}
    assert_rejected_without_mutation(
        state,
        lambda: meal_plans.handle(context(state, "child", now), "meal_save", plan_payload()),
        "forbidden",
    )
    assert_rejected_without_mutation(
        state,
        lambda: meal_plans.handle(
            context(state, "parent", now),
            "meal_save",
            {**plan_payload(), "revision": 1},
        ),
    )

    shopping = deepcopy(state["shopping"])
    outbox = deepcopy(state["outbox"])
    item = save(state, now)
    assert item["id"] == "MP000001"
    assert item["status"] == "draft" and item["revision"] == 1
    assert item["created_by"] == "parent"
    assert item["created_at"] == now.isoformat() and item["updated_at"] == now.isoformat()
    assert item["history"] == [
        {
            "actor": "parent",
            "at": now.isoformat(),
            "action": "created",
            "changes": {
                "week_start": "2026-09-07",
                "title": "Week menu",
                "entries": [entry()],
                "note": "Parent planning note",
            },
        }
    ]
    assert state["shopping"] == shopping and state["outbox"] == outbox
    assert set(state["pantry"]) == {"meal_plans"}


def test_current_state_role_is_rechecked_for_every_write(engine, now):
    state = enabled_state(engine)
    item = save(state, now, actor="owner")
    state["members"]["parent"]["active"] = False
    forged = Context(state, {"id": "parent", "role": "owner"}, now, "forged-role")
    for action, payload in (
        ("meal_save", {"id": item["id"], "revision": item["revision"], "title": "No"}),
        ("meal_publish", {"id": item["id"], "revision": item["revision"]}),
        (
            "meal_archive",
            {"id": item["id"], "revision": item["revision"], "reason": "No"},
        ),
    ):
        assert_rejected_without_mutation(
            state,
            lambda action=action, payload=payload: meal_plans.handle(forged, action, payload),
            "forbidden",
        )


def test_dates_entry_shapes_and_servings_are_strict(engine, now):
    state = enabled_state(engine)
    invalid = []
    invalid.append({**plan_payload(), "week_start": "2026-09-06"})
    invalid.append({**plan_payload(), "week_start": "2026-9-7"})
    invalid.append(plan_payload(week="9999-12-27"))
    invalid.append(plan_payload(entries=[]))
    invalid.append(plan_payload(entries=[entry()] * 29))
    invalid.append(plan_payload(entries=[entry("2026-09-14")]))
    invalid.append(plan_payload(entries=[entry(), entry()]))
    invalid.append(plan_payload(entries=[entry(slot="brunch")]))
    invalid.append(plan_payload(entries=[{**entry(), "extra": "field"}]))
    invalid.append(plan_payload(entries=[entry(title="")]))
    invalid.append(plan_payload(title="x" * 121))
    invalid.append(plan_payload(note="x" * 501))
    invalid.append(plan_payload(entries=[entry(title="x" * 121)]))
    for servings in (True, 1.0, 0, 51):
        invalid.append(plan_payload(entries=[entry(servings=servings)]))

    for index, payload in enumerate(invalid):
        assert_rejected_without_mutation(
            state,
            lambda payload=payload, index=index: meal_plans.handle(
                context(state, "parent", now, f"invalid-entry:{index}"), "meal_save", payload
            ),
        )
    assert state["pantry"] == {}


def test_ingredient_shapes_quantities_and_total_budget_are_strict(engine, now):
    state = enabled_state(engine)
    invalid_ingredients = (
        [ingredient(), {**ingredient(name="Extra"), "extra": "field"}],
        [{"name": "Rice", "unit": "g"}],
        [ingredient(name="")],
        [ingredient(name="n" * 121)],
        [ingredient(unit="u" * 25)],
        [ingredient(quantity=True)],
        [ingredient(quantity=0)],
        [ingredient(quantity=0.0001)],
        [ingredient(quantity=float("inf"))],
        [ingredient(quantity=1000000.001)],
        [ingredient(name=str(index)) for index in range(21)],
    )
    for index, ingredients in enumerate(invalid_ingredients):
        assert_rejected_without_mutation(
            state,
            lambda ingredients=ingredients, index=index: meal_plans.handle(
                context(state, "parent", now, f"invalid-ingredient:{index}"),
                "meal_save",
                plan_payload(entries=[entry(ingredients=ingredients)]),
            ),
        )

    entries = []
    first = now.date() + timedelta(days=1)
    for index in range(6):
        entries.append(
            entry(
                (first + timedelta(days=index // 4)).isoformat(),
                SLOTS[index % 4],
                ingredients=[ingredient(name=str(item)) for item in range(20)],
            )
        )
    assert_rejected_without_mutation(
        state,
        lambda: meal_plans.handle(
            context(state, "parent", now, "ingredient-budget"),
            "meal_save",
            plan_payload(entries=entries),
        ),
    )
    assert state["pantry"] == {}

    boundary = save(
        state,
        now,
        entries=[
            entry(
                ingredients=[
                    ingredient(name=f"Ingredient {index}", quantity=1000000 if index == 0 else 1)
                    for index in range(20)
                ]
            ),
            entry("2026-09-08", "snack", title="No ingredients", ingredients=[]),
        ],
    )
    assert len(boundary["entries"][0]["ingredients"]) == 20
    assert boundary["entries"][0]["ingredients"][0]["quantity"] == 1000000
    assert boundary["entries"][1]["ingredients"] == []


def test_partial_edit_preserves_week_entries_and_published_edit_returns_to_draft(engine, now):
    state = enabled_state(engine)
    item = save(state, now)
    original_entries = deepcopy(item["entries"])
    first_history = deepcopy(item["history"][0])
    edited = meal_plans.handle(
        context(state, "parent", now, "edit-title"),
        "meal_save",
        {"id": item["id"], "revision": item["revision"], "title": "Changed week"},
    )
    assert edited["week_start"] == "2026-09-07" and edited["entries"] == original_entries
    assert edited["note"] == "Parent planning note"
    assert edited["history"][0] == first_history and edited["history"][-1]["action"] == "edited"

    published = meal_plans.handle(
        context(state, "owner", now, "publish"),
        "meal_publish",
        {"id": edited["id"], "revision": edited["revision"]},
    )
    assert published["status"] == "published" and published["published_at"] == now.isoformat()
    redrafted = meal_plans.handle(
        context(state, "parent", now, "redraft"),
        "meal_save",
        {"id": published["id"], "revision": published["revision"], "note": ""},
    )
    assert redrafted["status"] == "draft" and "published_at" not in redrafted
    assert redrafted["entries"] == original_entries and redrafted["note"] == ""
    assert redrafted["history"][-1]["changes"]["status"] == "draft"


def test_revision_contract_is_strict_for_edit_publish_and_archive(engine, now):
    state = enabled_state(engine)
    item = save(state, now)
    commands = (
        ("meal_save", {"id": item["id"], "title": "Changed"}),
        ("meal_publish", {"id": item["id"]}),
        ("meal_archive", {"id": item["id"], "reason": "Retired"}),
    )
    for action, base in commands:
        assert_rejected_without_mutation(
            state,
            lambda action=action, base=base: meal_plans.handle(
                context(state, "parent", now), action, base
            ),
        )
        for bad in BAD_REVISIONS:
            assert_rejected_without_mutation(
                state,
                lambda action=action, base=base, bad=bad: meal_plans.handle(
                    context(state, "parent", now), action, {**base, "revision": bad}
                ),
            )

    stale = item["revision"]
    changed = meal_plans.handle(
        context(state, "parent", now),
        "meal_save",
        {"id": item["id"], "revision": stale, "title": "Current"},
    )
    for action, payload in (
        ("meal_save", {"id": item["id"], "revision": stale, "title": "Stale"}),
        ("meal_publish", {"id": item["id"], "revision": stale}),
        (
            "meal_archive",
            {"id": item["id"], "revision": stale, "reason": "Stale"},
        ),
    ):
        assert_rejected_without_mutation(
            state,
            lambda action=action, payload=payload: meal_plans.handle(
                context(state, "parent", now), action, payload
            ),
            "conflict",
        )
    assert changed["revision"] == 2


def test_publish_conflicts_by_week_and_archived_plans_are_immutable(engine, now):
    state = enabled_state(engine)
    first = save(state, now, title="First")
    second = save(state, now, actor="owner", title="Second")
    meal_plans.handle(
        context(state, "parent", now),
        "meal_publish",
        {"id": first["id"], "revision": first["revision"]},
    )
    assert_rejected_without_mutation(
        state,
        lambda: meal_plans.handle(
            context(state, "owner", now),
            "meal_publish",
            {"id": second["id"], "revision": second["revision"]},
        ),
        "conflict",
    )
    archived = meal_plans.handle(
        context(state, "owner", now),
        "meal_archive",
        {"id": first["id"], "revision": first["revision"], "reason": "Plan changed"},
    )
    assert archived["status"] == "archived"
    assert archived["history"][-1]["reason"] == "Plan changed"
    for action, payload in (
        (
            "meal_save",
            {"id": first["id"], "revision": archived["revision"], "title": "No edit"},
        ),
        ("meal_publish", {"id": first["id"], "revision": archived["revision"]}),
        (
            "meal_archive",
            {"id": first["id"], "revision": archived["revision"], "reason": "Again"},
        ),
    ):
        assert_rejected_without_mutation(
            state,
            lambda action=action, payload=payload: meal_plans.handle(
                context(state, "parent", now), action, payload
            ),
            "invalid_transition",
        )


def test_view_is_pure_and_redacts_parent_internals_from_shared_published_menu(engine, now):
    state = enabled_state(engine)
    draft = save(state, now, title="Draft")
    published = save(state, now, week="2026-09-14", title="Shared")
    published = meal_plans.handle(
        context(state, "owner", now),
        "meal_publish",
        {"id": published["id"], "revision": published["revision"]},
    )
    archived = save(state, now, week="2026-09-21", title="Archived")
    meal_plans.handle(
        context(state, "parent", now),
        "meal_archive",
        {"id": archived["id"], "revision": archived["revision"], "reason": "Old"},
    )
    before = deepcopy(state)

    parent = meal_plans.view(state, state["members"]["parent"])
    assert {item["id"] for item in parent} == {draft["id"], published["id"], archived["id"]}
    for actor_id in ("adult", "child", "sibling"):
        shared = meal_plans.view(state, state["members"][actor_id])
        assert len(shared) == 1 and shared[0]["id"] == published["id"]
        assert not meal_plans.PARENT_ONLY_FIELDS & shared[0].keys()
        assert shared[0]["entries"][0]["ingredients"][0]["quantity"] == 250
        shared[0]["entries"][0]["title"] = "Local mutation"
    assert meal_plans.view(state, state["members"]["guest"]) == []
    state["members"]["child"]["active"] = False
    assert meal_plans.view(state, {"id": "child", "role": "parent"}) == []
    state["members"]["child"]["active"] = True
    assert state == before


def test_invalid_bucket_shapes_are_rejected_without_repair(engine, now):
    state = enabled_state(engine)
    state["pantry"]["meal_plans"] = []
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_field"):
        meal_plans.view(state, state["members"]["parent"])
    with pytest.raises(DomainError, match="invalid_field"):
        meal_plans.handle(context(state, "parent", now), "meal_save", plan_payload())
    assert state == before
