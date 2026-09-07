"""Synthetic shopping conversion, without reading or applying any household data."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.migration.review import (
    ASSISTANT_KEY,
    COURT_KEY,
    read_store_pair,
)
from custom_components.family_assistant.migration.shopping_plan import (
    ShoppingPlanError,
    build_shopping_plan,
)

STAMP = "2026-09-07T08:00:00+00:00"


def wrapped(data, key):
    return json.dumps({"key": key, "version": 1, "data": data}).encode()


def fixture():
    state = new_state("fictional-ha-user", "Fictional household")
    state["members"]["child"] = {
        "id": "child",
        "revision": 1,
        "active": True,
        "role": "child",
        "name": "Nika",
        "language": "en",
    }
    row = {
        "task_id": "T000001",
        "kind": "shopping",
        "state": "accepted",
        "title": "Apples",
        "creator": "old-parent",
        "assignee": "old-child",
        "reviewer": None,
        "created_at": STAMP,
        "due_at": STAMP,
        "metadata": {
            "shopping_quantity": 3,
            "shopping_remaining_quantity": 1.5,
            "shopping_unit": "kg",
            "shopping_approval": "approved",
            "opaque": "fictional-secret",
        },
    }
    ledger = {
        "schema_version": 1,
        "tasks": {row["task_id"]: row},
        "history": [
            {
                "task_id": row["task_id"],
                "sequence": 1,
                "actor": "old-parent",
                "at": STAMP,
                "opaque": "fictional-event-secret",
            }
        ],
        "processed_commands": {"old-receipt": {"anything": "not-new-authority"}},
        "next_task_sequence": 2,
        "next_event_sequence": 2,
    }
    court = {
        "schema_version": 1,
        "week_id": "old-period",
        "opened_at": STAMP,
        "children": {},
        "history": [],
        "archived_weeks": [],
        "processed_messages": {},
    }
    mapping = {
        "old-parent": {"member_id": "owner", "member_revision": 1},
        "old-child": {"member_id": "child", "member_revision": 1},
    }
    return ledger, court, mapping, state


def plan_for(ledger, court, mapping, state, *, envelope=True):
    assistant = {"ledger": ledger} if envelope else ledger
    review = read_store_pair(wrapped(assistant, ASSISTANT_KEY), wrapped(court, COURT_KEY)).review(
        mapping, state["members"], mapping_revision=1
    )
    return review, build_shopping_plan(review, members=state["members"])


@pytest.mark.parametrize("envelope", [True, False])
def test_partial_records_and_exact_private_archive(envelope):
    args = fixture()
    before = deepcopy(args)
    review, plan = plan_for(*args, envelope=envelope)
    private = plan.private_data()
    assert args == before
    assert private["blocked"] == []
    assert private["archive"] == {"tasks": args[0]["tasks"], "history": args[0]["history"]}
    row = private["proposals"][0]
    assert row["source_task"] == "T000001"
    assert row["target_bindings"] == {
        "creator": args[2]["old-parent"],
        "buyer": args[2]["old-child"],
    }
    assert row["record"] == {
        "name": "Apples",
        "quantity": 3.0,
        "purchased": 1.5,
        "unit": "kg",
        "creator": "owner",
        "buyer": "child",
        "created_at": STAMP,
        "status": "approved",
        "category": "",
        "store": "",
        "note": "",
        "history": [],
    }
    assert plan.summary()["record_proposals_count"] == 1
    assert plan.summary()["archived_history_count"] == 1
    assert plan.summary()["review_fingerprint"] == review.summary()["fingerprint"]
    for value in ("Apples", "T000001", "old-parent", "old-child", "fictional-secret", STAMP):
        assert value not in json.dumps(plan.summary())
        assert value not in repr(plan)
    assert plan.summary()["import_available"] is False
    assert plan.summary()["coherence_verified"] is False
    assert "processed_commands" not in private["archive"]
    assert repr(plan) == "ShoppingPlan(private=True, import_available=False)"
    private["proposals"].clear()
    private["archive"]["tasks"].clear()
    plan.summary()["issues"].append("external-mutation")
    assert len(plan.private_data()["proposals"]) == 1
    assert len(plan.private_data()["archive"]["tasks"]) == 1
    assert plan.summary()["issues"] == []
    with pytest.raises(FrozenInstanceError):
        plan._summary = b"{}"


@pytest.mark.parametrize(
    "status,approval,remaining,target",
    [
        ("pending_approval", "pending", 3, "pending"),
        ("assigned", "approved", 3, "approved"),
        ("accepted", "approved", 2, "approved"),
        ("completed", "approved", 0, "purchased"),
        ("cancelled", "rejected", 3, "rejected"),
        ("cancelled", "pending", 3, "archived"),
        ("cancelled", "approved", 2, "archived"),
        ("archived", "approved", 0, "archived"),
        ("archived", "pending", 3, "archived"),
    ],
)
def test_exact_status_and_approval_mapping(status, approval, remaining, target):
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row["state"] = status
    row["metadata"].update(shopping_approval=approval, shopping_remaining_quantity=remaining)
    _, plan = plan_for(*args)
    assert plan.summary()["blocked_items_count"] == 0
    record = plan.private_data()["proposals"][0]["record"]
    assert record["status"] == target
    assert record["quantity"] - record["purchased"] == remaining


@pytest.mark.parametrize(
    "changes,code",
    [
        (
            {"shopping_quantity": None, "shopping_remaining_quantity": None},
            "shopping_quantity_unknown",
        ),
        ({"shopping_remaining_quantity": None}, "shopping_quantity_unknown"),
        (
            {"shopping_quantity": 0.0001, "shopping_remaining_quantity": 0.0001},
            "shopping_precision_unsupported",
        ),
        (
            {"shopping_quantity": 1.0000001, "shopping_remaining_quantity": 1},
            "shopping_precision_unsupported",
        ),
        ({"shopping_remaining_quantity": 0.9999999999999999}, "shopping_precision_unsupported"),
        (
            {"shopping_quantity": 1e-200, "shopping_remaining_quantity": 0},
            "shopping_precision_unsupported",
        ),
        ({"shopping_approval": "pending"}, "shopping_state_conflict"),
        ({"shopping_remaining_quantity": 0}, "shopping_state_conflict"),
    ],
)
def test_unrepresentable_values_remain_visible_blockers(changes, code):
    args = fixture()
    args[0]["tasks"]["T000001"]["metadata"].update(changes)
    _, plan = plan_for(*args)
    assert plan.summary()["issues"] == [{"code": code, "count": 1}]
    assert plan.summary()["source_items_count"] == plan.summary()["blocked_items_count"] == 1
    assert plan.summary()["record_proposals_count"] == 0
    assert plan.private_data()["blocked"] == [{"source_task": "T000001", "code": code}]
    assert plan.private_data()["archive"]["tasks"] == args[0]["tasks"]


@pytest.mark.parametrize("status", ["in_progress", "submitted", "needs_changes", "overdue"])
def test_unsupported_state_is_not_silently_reopened(status):
    args = fixture()
    args[0]["tasks"]["T000001"]["state"] = status
    _, plan = plan_for(*args)
    assert plan.summary()["issues"] == [{"code": "shopping_state_unsupported", "count": 1}]


def test_long_name_is_not_truncated_and_null_unit_is_absent():
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row.update(title="x" * 201, assignee=None)
    row["metadata"]["shopping_unit"] = None
    _, blocked = plan_for(*args)
    assert blocked.summary()["issues"][0]["code"] == "shopping_name_unsupported"
    row["title"] = "x" * 200
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    assert record["name"] == row["title"]
    assert record["unit"] == ""
    assert record["buyer"] is None


def test_empty_bucket_does_not_collect_private_reminder_history():
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row.update(kind="reminder", assignee="old-parent")
    _, plan = plan_for(*args)
    assert plan.private_data() == {
        "proposals": [],
        "blocked": [],
        "archive": {"tasks": {}, "history": []},
    }
    assert plan.summary()["source_items_count"] == 0


def test_deterministic_fingerprint_pins_every_source_change():
    args = fixture()
    _, first = plan_for(*args)
    _, repeated = plan_for(*args)
    assert first.summary() == repeated.summary()
    args[0]["processed_commands"]["unrelated-source-change"] = {}
    _, changed = plan_for(*args)
    assert first.summary()["fingerprint"] != changed.summary()["fingerprint"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 2),
        ("active", False),
        ("role", "parent"),
        ("telegram_id", 9911),
        ("ha_user_id", "new-binding"),
    ],
)
def test_member_change_revokes_proposal(field, value):
    args = fixture()
    review, _ = plan_for(*args)
    args[3]["members"]["child"][field] = value
    with pytest.raises(ShoppingPlanError, match="^review_changed$"):
        build_shopping_plan(review, members=args[3]["members"])


def test_invalid_or_forged_review_has_fixed_error():
    args = fixture()
    review, _ = plan_for(*args)
    with pytest.raises(ShoppingPlanError, match="^invalid_review$"):
        build_shopping_plan(None)
    with pytest.raises(ShoppingPlanError, match="^review_changed$"):
        build_shopping_plan(review)
    with pytest.raises(ShoppingPlanError, match="^review_changed$"):
        build_shopping_plan(replace(review, _fingerprint="x" * 64), members=args[3]["members"])


@pytest.mark.parametrize("quantity,remaining", [(1000001, 1), (3, -1), (3, 4)])
def test_preflight_revalidation_blocks_invalid_numeric_bounds(quantity, remaining):
    args = fixture()
    review, _ = plan_for(*args)
    args[0]["tasks"]["T000001"]["metadata"].update(
        shopping_quantity=quantity, shopping_remaining_quantity=remaining
    )
    source = read_store_pair(wrapped(args[0], ASSISTANT_KEY), wrapped(args[1], COURT_KEY))
    with pytest.raises(ShoppingPlanError, match="^review_changed$"):
        build_shopping_plan(replace(review, _source=source), members=args[3]["members"])


def test_source_duck_type_cannot_run_code_or_bypass_revalidation():
    class FakeSource:
        def review(self, *args, **kwargs):
            raise AssertionError("Must not call a duck-typed source")

    args = fixture()
    review, _ = plan_for(*args)
    with pytest.raises(ShoppingPlanError, match="^review_changed$"):
        build_shopping_plan(replace(review, _source=FakeSource()), members=args[3]["members"])


def test_six_decimal_projection_uses_domain_rounding_for_remaining():
    args = fixture()
    args[0]["tasks"]["T000001"]["metadata"].update(
        shopping_quantity=1.1, shopping_remaining_quantity=0.1
    )
    _, plan = plan_for(*args)
    item = plan.private_data()["proposals"][0]["record"]
    assert item["quantity"] == 1.1
    assert item["purchased"] == 1.0
    assert round(item["quantity"] - item["purchased"], 6) == 0.1


@pytest.mark.asyncio
async def test_proposed_record_matches_real_modern_creation_and_partial_purchase():
    args = fixture()
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    saved = []

    async def persist(value):
        saved.append(deepcopy(value))

    engine = Engine(args[3], persist)
    now = datetime.fromisoformat(STAMP).astimezone(UTC)
    item = await engine.execute(
        "owner",
        "shopping.add",
        {
            key: record[key]
            for key in ("name", "quantity", "unit", "category", "store", "note", "buyer")
        },
        "fictional-add",
        now,
    )
    item = await engine.execute(
        "owner",
        "shopping.purchase",
        {"id": item["id"], "revision": item["revision"], "quantity": record["purchased"]},
        "fictional-purchase",
        now,
    )
    assert {key: item[key] for key in record if key != "history"} == {
        key: value for key, value in record.items() if key != "history"
    }
    # New domain history is verified through commands; none is fabricated by the planner.
    assert item["history"] and record["history"] == []
    assert len(saved) == 2
