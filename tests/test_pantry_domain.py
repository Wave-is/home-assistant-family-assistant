"""Pantry inventory and reviewable shopping suggestions domain tests."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain import pantry, shopping
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def context(state, actor_id, now, operation="pantry-test"):
    return Context(state, state["members"][actor_id], now, operation)


def enable(state):
    if "pantry" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("pantry")
    return state


def create_item(state, now, **changes):
    payload = {
        "name": "Milk",
        "unit": "l",
        "quantity": 1,
        "minimum_quantity": 3,
        "category": "Food",
        "location": "Fridge",
        "note": "Synthetic note",
        "expires_on": "2026-09-10",
        **changes,
    }
    return pantry.handle(context(state, "parent", now), "item_save", payload)


def open_suggestion(state):
    return next(
        item for item in state["pantry"]["suggestions"].values() if item["status"] == "open"
    )


def test_item_validation_roles_partial_edits_and_immutable_history(engine, now):
    state = enable(engine.snapshot())
    required = {
        "name": "Milk",
        "unit": "l",
        "quantity": 1,
        "minimum_quantity": 2,
    }
    with pytest.raises(DomainError, match="forbidden"):
        pantry.handle(context(state, "child", now), "item_save", required)
    for patch in (
        {"quantity": True},
        {"quantity": 0.0000000001},
        {"quantity": 1.0001},
        {"minimum_quantity": float("inf")},
        {"expires_on": "2026-9-7"},
        {"unit": ""},
    ):
        with pytest.raises(DomainError, match="invalid_field"):
            pantry.handle(context(state, "parent", now), "item_save", {**required, **patch})
    with pytest.raises(DomainError, match="invalid_field"):
        pantry.handle(
            context(state, "parent", now),
            "item_save",
            {key: value for key, value in required.items() if key != "unit"},
        )

    item = create_item(state, now)
    assert item["id"].startswith("I") and item["revision"] == 1
    first_history = deepcopy(item["history"][0])
    edited = pantry.handle(
        context(state, "parent", now),
        "item_save",
        {"id": item["id"], "revision": item["revision"], "location": "Pantry shelf"},
    )
    assert edited["location"] == "Pantry shelf"
    assert edited["category"] == "Food" and edited["note"] == "Synthetic note"
    assert edited["quantity"] == 1 and edited["expires_on"] == "2026-09-10"
    assert edited["history"][0] == first_history
    with pytest.raises(DomainError, match="conflict"):
        pantry.handle(
            context(state, "parent", now),
            "item_save",
            {"id": item["id"], "revision": 1, "location": "Stale"},
        )
    with pytest.raises(DomainError) as caught:
        pantry.handle(
            context(state, "parent", now),
            "item_save",
            {"id": item["id"], "revision": edited["revision"], "quantity": 2},
        )
    assert caught.value.field == "reason"
    with pytest.raises(DomainError) as caught:
        pantry.handle(
            context(state, "parent", now),
            "item_save",
            {"id": item["id"], "revision": edited["revision"], "unit": "ml"},
        )
    assert caught.value.field == "reason"


@pytest.mark.parametrize("revision", [None, True, 1.0, "1", 0, -1, 2**53])
@pytest.mark.parametrize(
    "action,changes",
    [
        ("item_save", {"location": "New shelf"}),
        ("stock_set", {"quantity": 2, "reason": "Counted"}),
        ("item_archive", {"reason": "Removed"}),
        ("suggestion_accept", {}),
        ("suggestion_dismiss", {"reason": "Not needed"}),
    ],
)
def test_every_edit_requires_strict_revision(engine, now, revision, action, changes):
    state = enable(engine.snapshot())
    item = create_item(state, now)
    pantry.tick(context(state, "parent", now))
    target = open_suggestion(state) if action.startswith("suggestion_") else item
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_field") as caught:
        pantry.handle(
            context(state, "parent", now),
            action,
            {"id": target["id"], "revision": revision, **changes},
        )
    assert caught.value.field == "revision"
    assert state == before


def test_stock_set_requires_current_active_adult_and_reason(engine, now):
    state = enable(engine.snapshot())
    item = create_item(state, now)
    with pytest.raises(DomainError, match="forbidden"):
        pantry.handle(
            context(state, "child", now),
            "stock_set",
            {"id": item["id"], "revision": item["revision"], "quantity": 2, "reason": "Count"},
        )
    with pytest.raises(DomainError, match="invalid_field"):
        pantry.handle(
            context(state, "adult", now),
            "stock_set",
            {"id": item["id"], "revision": item["revision"], "quantity": 2},
        )
    changed = pantry.handle(
        context(state, "adult", now),
        "stock_set",
        {"id": item["id"], "revision": item["revision"], "quantity": 2, "reason": "Counted"},
    )
    assert changed["quantity"] == 2
    assert "history" not in changed and "note" not in changed
    assert item["history"][-1]["reason"] == "Counted"
    with pytest.raises(DomainError, match="invalid_transition"):
        pantry.handle(
            context(state, "adult", now),
            "stock_set",
            {
                "id": item["id"],
                "revision": changed["revision"],
                "quantity": 2,
                "reason": "Same count",
            },
        )
    state["members"]["adult"]["active"] = False
    with pytest.raises(DomainError, match="forbidden"):
        pantry.handle(
            context(state, "adult", now),
            "stock_set",
            {
                "id": item["id"],
                "revision": changed["revision"],
                "quantity": 0,
                "reason": "Stale identity",
            },
        )


def test_tick_is_lazy_deduplicated_and_dismissal_suppresses_unchanged_stock(engine, now):
    disabled = engine.snapshot()
    before = deepcopy(disabled)
    pantry.tick(context(disabled, "owner", now))
    assert disabled == before

    state = enable(engine.snapshot())
    empty = deepcopy(state)
    pantry.tick(context(state, "owner", now))
    assert state == empty and state["pantry"] == {}

    item = create_item(state, now)
    shopping_before = deepcopy(state["shopping"])
    pantry.tick(context(state, "owner", now, "tick-one"))
    proposal = open_suggestion(state)
    assert proposal["id"].startswith("G")
    assert proposal["quantity"] == 2 and proposal["source_revision"] == item["revision"]
    assert state["shopping"] == shopping_before
    pantry.tick(context(state, "owner", now, "tick-two"))
    assert len(state["pantry"]["suggestions"]) == 1

    dismissed = pantry.handle(
        context(state, "parent", now),
        "suggestion_dismiss",
        {"id": proposal["id"], "revision": proposal["revision"], "reason": "Already stocked"},
    )
    assert dismissed["status"] == "dismissed"
    pantry.tick(context(state, "owner", now, "tick-three"))
    assert len(state["pantry"]["suggestions"]) == 1

    pantry.handle(
        context(state, "adult", now),
        "stock_set",
        {"id": item["id"], "revision": item["revision"], "quantity": 0, "reason": "Recount"},
    )
    pantry.tick(context(state, "owner", now, "tick-four"))
    assert len(state["pantry"]["suggestions"]) == 2
    assert open_suggestion(state)["source_revision"] == item["revision"]


def test_stock_and_metadata_changes_or_archive_supersede_open_proposals(engine, now):
    state = enable(engine.snapshot())
    item = create_item(state, now)
    pantry.tick(context(state, "owner", now))
    first = open_suggestion(state)
    pantry.handle(
        context(state, "parent", now),
        "item_save",
        {"id": item["id"], "revision": item["revision"], "minimum_quantity": 4},
    )
    assert first["status"] == "superseded"

    pantry.tick(context(state, "owner", now))
    second = open_suggestion(state)
    archived = pantry.handle(
        context(state, "parent", now),
        "item_archive",
        {"id": item["id"], "revision": item["revision"], "reason": "Removed"},
    )
    assert archived["status"] == "archived" and second["status"] == "superseded"


def test_matching_open_shopping_uses_normalized_name_and_exact_unit(engine, now):
    state = enable(engine.snapshot())
    item = create_item(state, now, name="  MILK  ", unit="l")
    shopping.handle(
        context(state, "parent", now),
        "add",
        {"name": "milk", "quantity": 1, "unit": "L"},
    )
    pantry.tick(context(state, "owner", now))
    proposal = open_suggestion(state)

    matching = shopping.handle(
        context(state, "parent", now),
        "add",
        {"name": "Milk", "quantity": 1, "unit": "l"},
    )
    pantry.tick(context(state, "owner", now))
    assert proposal["status"] == "covered"
    assert proposal["shopping_id"] == matching["id"]
    assert item["quantity"] == 1


def test_accept_is_atomic_reviewed_creation_and_rechecks_fresh_coverage(engine, now):
    state = enable(engine.snapshot())
    item = create_item(state, now)
    pantry.tick(context(state, "owner", now))
    proposal = open_suggestion(state)
    outbox_before = deepcopy(state["outbox"])
    accepted = pantry.handle(
        context(state, "parent", now),
        "suggestion_accept",
        {"id": proposal["id"], "revision": proposal["revision"]},
    )
    created = state["shopping"][accepted["shopping_id"]]
    assert accepted["status"] == "accepted"
    assert created["status"] == "approved" and created["purchased"] == 0
    assert created["quantity"] == 2 and created["pantry_id"] == item["id"]
    assert created["pantry_suggestion_id"] == proposal["id"]
    assert created["note"] == ""
    child_view = Engine(state, lambda _state: None).view("child")
    visible = next(value for value in child_view["shopping"] if value["id"] == created["id"])
    assert "Synthetic note" not in visible.values()
    assert item["quantity"] == 1 and state["outbox"] == outbox_before
    pantry.tick(context(state, "owner", now))
    assert len(state["shopping"]) == 1 and len(state["pantry"]["suggestions"]) == 1

    second = create_item(state, now, name="Bread", unit="loaf", note="")
    pantry.tick(context(state, "owner", now))
    second_proposal = next(
        value
        for value in state["pantry"]["suggestions"].values()
        if value["pantry_id"] == second["id"] and value["status"] == "open"
    )
    existing = shopping.handle(
        context(state, "parent", now),
        "add",
        {"name": "bread", "quantity": 1, "unit": "loaf"},
    )
    covered = pantry.handle(
        context(state, "parent", now),
        "suggestion_accept",
        {"id": second_proposal["id"], "revision": second_proposal["revision"]},
    )
    assert covered["status"] == "covered" and covered["shopping_id"] == existing["id"]
    assert len(state["shopping"]) == 2


def test_accept_rejects_stale_source_and_disabled_shopping(engine, now):
    state = enable(engine.snapshot())
    item = create_item(state, now)
    pantry.tick(context(state, "owner", now))
    proposal = open_suggestion(state)
    pantry.handle(
        context(state, "adult", now),
        "stock_set",
        {"id": item["id"], "revision": item["revision"], "quantity": 2, "reason": "Fresh count"},
    )
    with pytest.raises(DomainError, match="invalid_transition"):
        pantry.handle(
            context(state, "parent", now),
            "suggestion_accept",
            {"id": proposal["id"], "revision": proposal["revision"]},
        )

    pantry.tick(context(state, "owner", now))
    current = open_suggestion(state)
    state["settings"]["modules"].remove("shopping")
    with pytest.raises(DomainError, match="module_disabled"):
        pantry.handle(
            context(state, "parent", now),
            "suggestion_accept",
            {"id": current["id"], "revision": current["revision"]},
        )
    assert not state["shopping"]


def test_view_is_pure_private_and_uses_household_local_date(engine, now):
    state = enable(engine.snapshot())
    state["settings"]["timezone"] = "Europe/Kyiv"
    item = create_item(state, now, expires_on="2026-09-07")
    pantry.tick(context(state, "owner", now))
    before = deepcopy(state)

    unknown = pantry.view(state, state["members"]["child"])
    assert unknown["items"][0]["expiry_status"] == "unknown"
    local_today = pantry.view(
        state, state["members"]["child"], datetime(2026, 9, 6, 22, 30, tzinfo=UTC)
    )
    child_item = local_today["items"][0]
    assert child_item["expiry_status"] == "today" and child_item["expires_in_days"] == 0
    assert child_item["low_stock"] is True
    assert "history" not in child_item and "note" not in child_item
    assert local_today["suggestions"] == []

    after_expiry = datetime(2026, 9, 8, 8, tzinfo=UTC)
    pantry.tick(context(state, "owner", after_expiry, "post-expiry"))
    expired = pantry.view(state, state["members"]["child"], after_expiry)
    assert expired["items"][0]["expiry_status"] == "expired"
    assert item["quantity"] == 1

    parent = pantry.view(state, state["members"]["parent"], now)
    assert parent["items"][0]["note"] == "Synthetic note"
    assert parent["items"][0]["history"] and parent["suggestions"]
    assert pantry.view(state, state["members"]["guest"], now) == {
        "items": [],
        "archived": [],
        "suggestions": [],
    }
    assert state == before and item["quantity"] == 1
