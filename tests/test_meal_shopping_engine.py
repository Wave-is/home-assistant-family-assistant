"""Meal-plan shopping proposals through the real Engine transaction boundary."""

import asyncio
from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.shopping import normalized_name
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def transfer_engine(engine, store):
    state = engine.snapshot()
    for module in ("pantry", "shopping"):
        if module not in state["settings"]["modules"]:
            state["settings"]["modules"].append(module)
    return Engine(state, store.save)


def ingredient(name="Synthetic milk", unit="l", quantity=2):
    return {"name": name, "unit": unit, "quantity": quantity}


def meal_entry(
    *,
    date="2026-09-07",
    slot="dinner",
    title="Synthetic meal",
    ingredients=None,
):
    return {
        "date": date,
        "slot": slot,
        "title": title,
        "servings": 4,
        "ingredients": [ingredient()] if ingredients is None else ingredients,
    }


async def published_plan(engine, now, *, entries=None, operation="source"):
    created = await engine.execute(
        "parent",
        "pantry.meal_save",
        {
            "week_start": "2026-09-07",
            "title": "Synthetic source menu",
            "entries": [meal_entry()] if entries is None else entries,
        },
        f"{operation}-save",
        now,
    )
    return await engine.execute(
        "parent",
        "pantry.meal_publish",
        {"id": created["id"], "revision": created["revision"]},
        f"{operation}-publish",
        now,
    )


async def prepare(engine, now, plan, operation="prepare"):
    return await engine.execute(
        "parent",
        "pantry.meal_shop_prepare",
        {"id": plan["id"], "revision": plan["revision"]},
        operation,
        now,
    )


async def accept(engine, now, proposal, operation="accept"):
    return await engine.execute(
        "parent",
        "pantry.meal_shop_accept",
        {"id": proposal["id"], "revision": proposal["revision"]},
        operation,
        now,
    )


async def add_stock(
    engine,
    now,
    *,
    name="Synthetic milk",
    unit="l",
    quantity=1,
    expires_on=None,
    operation="stock",
):
    return await engine.execute(
        "parent",
        "pantry.item_save",
        {
            "name": name,
            "unit": unit,
            "quantity": quantity,
            "minimum_quantity": 0,
            "expires_on": expires_on,
        },
        operation,
        now,
    )


async def add_shopping(
    engine,
    now,
    *,
    actor="parent",
    name="Synthetic milk",
    unit="l",
    quantity=1,
    operation="shopping",
):
    return await engine.execute(
        actor,
        "shopping.add",
        {"name": name, "unit": unit, "quantity": quantity},
        operation,
        now,
    )


def proposals(engine):
    return engine.snapshot()["pantry"]["meal_shopping"]


def line_for(proposal, *, unit, name="synthetic milk"):
    return next(
        line
        for line in proposal["lines"]
        if normalized_name(line["name"]) == normalized_name(name) and line["unit"] == unit
    )


def assert_no_write(engine, store, before, writes):
    assert engine.snapshot() == before
    assert store.calls == writes


@pytest.mark.asyncio
async def test_prepare_groups_normalized_names_exact_units_and_subtracts_only_open_remaining(
    transfer_engine, now
):
    plan = await published_plan(
        transfer_engine,
        now,
        entries=[
            meal_entry(ingredients=[ingredient(" Synthetic   Milk ", "l", 2)]),
            meal_entry(
                date="2026-09-08",
                slot="breakfast",
                ingredients=[ingredient("synthetic milk", "l", 3)],
            ),
            meal_entry(
                date="2026-09-09",
                slot="lunch",
                ingredients=[ingredient("SYNTHETIC MILK", "ml", 1000)],
            ),
            meal_entry(
                date="2026-09-10",
                slot="snack",
                ingredients=[ingredient("Cafe\u0301", "pcs", 1)],
            ),
            meal_entry(
                date="2026-09-11",
                slot="dinner",
                ingredients=[ingredient("Café", "pcs", 2)],
            ),
        ],
    )
    await add_stock(
        transfer_engine,
        now,
        quantity=1.25,
        expires_on="2020-01-01",
        operation="active-expired-stock",
    )
    await add_stock(
        transfer_engine,
        now,
        unit="ml",
        quantity=100,
        operation="different-unit-stock",
    )
    archived = await add_stock(transfer_engine, now, quantity=999, operation="archived-stock")
    await transfer_engine.execute(
        "parent",
        "pantry.item_archive",
        {"id": archived["id"], "revision": archived["revision"], "reason": "Synthetic"},
        "archive-stock",
        now,
    )
    partial = await add_shopping(transfer_engine, now, quantity=2, operation="approved-partial")
    await transfer_engine.execute(
        "parent",
        "shopping.purchase",
        {"id": partial["id"], "revision": partial["revision"], "quantity": 0.5},
        "partial-purchase",
        now,
    )
    await add_shopping(
        transfer_engine,
        now,
        actor="child",
        quantity=0.5,
        operation="pending-open",
    )
    purchased = await add_shopping(transfer_engine, now, quantity=7, operation="fully-purchased")
    await transfer_engine.execute(
        "parent",
        "shopping.purchase",
        {"id": purchased["id"], "revision": purchased["revision"]},
        "complete-purchase",
        now,
    )
    before = transfer_engine.snapshot()
    proposal = await prepare(transfer_engine, now, plan)

    assert proposal["id"] == "MS000001"
    assert proposal["status"] == "open"
    assert len(proposal["lines"]) == 3
    litres = line_for(proposal, unit="l")
    assert litres == {
        **litres,
        "required": 5,
        "stock": 1.25,
        "open_shopping": 2,
        "quantity": 1.75,
    }
    millilitres = line_for(proposal, unit="ml")
    assert millilitres["required"] == 1000
    assert millilitres["stock"] == 100
    assert millilitres["open_shopping"] == 0
    assert millilitres["quantity"] == 900
    cafe = line_for(proposal, unit="pcs", name="café")
    assert cafe["required"] == 3 and cafe["quantity"] == 3
    after = transfer_engine.snapshot()
    assert after["shopping"] == before["shopping"]
    assert after["pantry"]["items"] == before["pantry"]["items"]
    assert after["outbox"] == before["outbox"]


@pytest.mark.asyncio
async def test_accept_creates_only_positive_approved_lines_with_fixed_lineage(transfer_engine, now):
    plan = await published_plan(
        transfer_engine,
        now,
        entries=[
            meal_entry(ingredients=[ingredient(quantity=2)]),
            meal_entry(
                date="2026-09-08",
                slot="lunch",
                ingredients=[ingredient("Covered beans", "g", 500)],
            ),
        ],
    )
    await add_stock(
        transfer_engine,
        now,
        name="Covered beans",
        unit="g",
        quantity=500,
        operation="cover-beans",
    )
    proposal = await prepare(transfer_engine, now, plan)
    assert line_for(proposal, unit="g", name="covered beans")["quantity"] == 0
    before_ids = set(transfer_engine.snapshot()["shopping"])
    accepted = await accept(transfer_engine, now, proposal)
    created_ids = set(transfer_engine.snapshot()["shopping"]) - before_ids
    assert accepted["status"] == "accepted"
    assert accepted["transfer_count"] == 1
    assert len(created_ids) == 1
    created = transfer_engine.snapshot()["shopping"][created_ids.pop()]
    assert created["status"] == "approved"
    assert created["quantity"] == 2 and created["unit"] == "l"
    assert created["note"] == ""
    assert created["meal_plan_id"] == plan["id"]
    assert created["meal_shopping_id"] == proposal["id"]
    positive = line_for(accepted, unit="l")
    assert positive["shopping_id"] == created["id"]
    assert line_for(accepted, unit="g", name="covered beans")["quantity"] == 0


@pytest.mark.asyncio
async def test_all_zero_lines_are_retained_and_accept_marks_covered(transfer_engine, now):
    plan = await published_plan(transfer_engine, now)
    await add_stock(transfer_engine, now, quantity=2)
    proposal = await prepare(transfer_engine, now, plan)
    assert proposal["lines"][0]["quantity"] == 0
    before = transfer_engine.snapshot()["shopping"]
    covered = await accept(transfer_engine, now, proposal)
    assert covered["status"] == "covered"
    assert covered["transfer_count"] == 0
    assert covered["lines"][0]["quantity"] == 0
    assert transfer_engine.snapshot()["shopping"] == before


@pytest.mark.asyncio
async def test_proposals_are_parent_only_and_both_modules_are_required(transfer_engine, store, now):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    for actor in ("parent", "owner"):
        visible = transfer_engine.view(actor, now=now)["pantry"]["meal_shopping"]
        assert len(visible) == 1 and visible[0]["id"] == proposal["id"]
        assert visible[0]["lines"] == proposal["lines"]
        assert "input_fingerprint" not in visible[0]
    for actor in ("adult", "child"):
        assert transfer_engine.view(actor, now=now)["pantry"]["meal_shopping"] == []
    assert "pantry" not in transfer_engine.view("guest", now=now)

    settings = transfer_engine.snapshot()["settings"]
    await transfer_engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": [module for module in settings["modules"] if module != "shopping"],
        },
        "disable-shopping",
        now,
    )
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="module_disabled"):
        await accept(transfer_engine, now, proposal, "accept-without-shopping")
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["adult", "child", "guest"])
@pytest.mark.parametrize("action", ["prepare", "accept"])
async def test_unprivileged_roles_cannot_prepare_or_accept(
    transfer_engine, store, now, actor, action
):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    command, payload = (
        ("meal_shop_prepare", {"id": plan["id"], "revision": plan["revision"]})
        if action == "prepare"
        else ("meal_shop_accept", {"id": proposal["id"], "revision": proposal["revision"]})
    )
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="forbidden"):
        await transfer_engine.execute(
            actor, f"pantry.{command}", payload, f"forbidden-{actor}-{action}", now
        )
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
async def test_concurrent_different_operation_prepares_and_accepts_do_not_duplicate(
    transfer_engine, now
):
    plan = await published_plan(transfer_engine, now)
    payload = {"id": plan["id"], "revision": plan["revision"]}
    prepared = await asyncio.gather(
        *[
            transfer_engine.execute(
                "parent", "pantry.meal_shop_prepare", payload, f"concurrent-prepare-{index}", now
            )
            for index in range(12)
        ]
    )
    assert {item["id"] for item in prepared} == {"MS000001"}
    assert len(proposals(transfer_engine)) == 1
    proposal = prepared[0]
    accept_payload = {"id": proposal["id"], "revision": proposal["revision"]}
    accepted = await asyncio.gather(
        *[
            transfer_engine.execute(
                "parent",
                "pantry.meal_shop_accept",
                accept_payload,
                f"concurrent-accept-{index}",
                now,
            )
            for index in range(12)
        ],
        return_exceptions=True,
    )
    successes = [item for item in accepted if isinstance(item, dict)]
    conflicts = [item for item in accepted if isinstance(item, DomainError)]
    assert len(successes) == 1 and successes[0]["status"] == "accepted"
    assert len(conflicts) == 11 and {error.code for error in conflicts} == {"conflict"}
    linked = [
        item
        for item in transfer_engine.snapshot()["shopping"].values()
        if item.get("meal_plan_id") == plan["id"]
    ]
    assert len(linked) == 1


@pytest.mark.asyncio
async def test_same_inputs_reuse_open_but_relevant_change_supersedes_it(transfer_engine, now):
    plan = await published_plan(transfer_engine, now)
    first = await prepare(transfer_engine, now, plan, "prepare-first")
    reused = await prepare(transfer_engine, now, plan, "prepare-reuse")
    assert reused["id"] == first["id"] and len(proposals(transfer_engine)) == 1
    await add_stock(transfer_engine, now, quantity=0.5, operation="relevant-stock")
    replacement = await prepare(transfer_engine, now, plan, "prepare-changed")
    assert replacement["id"] != first["id"]
    assert proposals(transfer_engine)[first["id"]]["status"] == "superseded"
    assert replacement["lines"][0]["quantity"] == 1.5


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["stock", "shopping"])
async def test_relevant_inventory_or_open_shopping_change_invalidates_accept(
    transfer_engine, store, now, change
):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    if change == "stock":
        await add_stock(transfer_engine, now, quantity=0.5, operation="new-matching-stock")
    else:
        await add_shopping(transfer_engine, now, quantity=0.5, operation="new-matching-shopping")
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="conflict"):
        await accept(transfer_engine, now, proposal)
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
async def test_unrelated_records_do_not_invalidate_accept(transfer_engine, now):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    await add_stock(
        transfer_engine,
        now,
        name="Unrelated salt",
        unit="g",
        quantity=10,
        operation="unrelated-stock",
    )
    await add_shopping(
        transfer_engine,
        now,
        name="Unrelated soap",
        unit="pcs",
        quantity=1,
        operation="unrelated-shopping",
    )
    result = await accept(transfer_engine, now, proposal)
    assert result["status"] == "accepted"


@pytest.mark.asyncio
@pytest.mark.parametrize("source_change", ["edit", "archive"])
async def test_source_plan_edit_or_archive_invalidates_accept(
    transfer_engine, store, now, source_change
):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    if source_change == "edit":
        await transfer_engine.execute(
            "parent",
            "pantry.meal_save",
            {"id": plan["id"], "revision": plan["revision"], "title": "Changed source"},
            "edit-source",
            now,
        )
    else:
        await transfer_engine.execute(
            "parent",
            "pantry.meal_archive",
            {"id": plan["id"], "revision": plan["revision"], "reason": "Changed plans"},
            "archive-source",
            now,
        )
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="conflict"):
        await accept(transfer_engine, now, proposal)
    assert_no_write(transfer_engine, store, before, writes)


INVALID_REVISIONS = [None, True, False, 1.0, "1", 0, -1, 2**53]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["prepare", "accept"])
@pytest.mark.parametrize("bad_revision", ["missing", *INVALID_REVISIONS])
async def test_missing_or_invalid_revisions_make_no_write(
    transfer_engine, store, now, action, bad_revision
):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    source = plan if action == "prepare" else proposal
    payload = {"id": source["id"]}
    if bad_revision != "missing":
        payload["revision"] = bad_revision
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await transfer_engine.execute(
            "parent",
            f"pantry.meal_shop_{action}",
            payload,
            f"invalid-{action}-{bad_revision!r}",
            now,
        )
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["prepare", "accept"])
async def test_stale_positive_revisions_conflict_without_write(transfer_engine, store, now, action):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    if action == "prepare":
        current = await transfer_engine.execute(
            "parent",
            "pantry.meal_save",
            {"id": plan["id"], "revision": plan["revision"], "title": "New source revision"},
            "advance-source",
            now,
        )
        payload = {"id": current["id"], "revision": plan["revision"]}
    else:
        await add_stock(transfer_engine, now, quantity=0.5, operation="advance-input")
        await prepare(transfer_engine, now, plan, "superseding-prepare")
        current = proposals(transfer_engine)[proposal["id"]]
        payload = {"id": current["id"], "revision": proposal["revision"]}
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="conflict"):
        await transfer_engine.execute(
            "parent", f"pantry.meal_shop_{action}", payload, f"stale-{action}", now
        )
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
async def test_prepare_store_failure_is_atomic_and_retryable(transfer_engine, store, now):
    plan = await published_plan(transfer_engine, now)
    before, persisted = transfer_engine.snapshot(), deepcopy(store.value)
    store.fail = True
    with pytest.raises(OSError):
        await prepare(transfer_engine, now, plan, "prepare-failure")
    assert transfer_engine.snapshot() == before and store.value == persisted
    store.fail = False
    result = await prepare(transfer_engine, now, plan, "prepare-failure")
    assert result["status"] == "open" and len(proposals(transfer_engine)) == 1


@pytest.mark.asyncio
async def test_accept_store_failure_retry_restart_and_exact_replay(transfer_engine, store, now):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    before, persisted = transfer_engine.snapshot(), deepcopy(store.value)
    store.fail = True
    with pytest.raises(OSError):
        await accept(transfer_engine, now, proposal, "accept-failure")
    assert transfer_engine.snapshot() == before and store.value == persisted
    store.fail = False
    result = await accept(transfer_engine, now, proposal, "accept-failure")
    restarted = Engine(deepcopy(store.value), store.save)
    writes = store.calls
    assert await accept(restarted, now, proposal, "accept-failure") == result
    assert store.calls == writes
    assert (
        len(
            [
                item
                for item in restarted.snapshot()["shopping"].values()
                if item.get("meal_shopping_id") == proposal["id"]
            ]
        )
        == 1
    )


@pytest.mark.asyncio
async def test_batch_accept_rolls_back_created_shopping_item(transfer_engine, store, now):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError):
        await transfer_engine.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {
                        "action": "pantry.meal_shop_accept",
                        "payload": {"id": proposal["id"], "revision": proposal["revision"]},
                    },
                    {
                        "action": "pantry.meal_shop_accept",
                        "payload": {"id": proposal["id"]},
                    },
                ]
            },
            "accept-batch-failure",
            now,
        )
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["pantry", "shopping", "role", "inactive"])
@pytest.mark.parametrize("receipt_action", ["prepare", "accept"])
async def test_exact_replay_rechecks_modules_role_and_active_identity(
    transfer_engine, store, now, revocation, receipt_action
):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(
        transfer_engine, now, plan, f"proposal-for-{receipt_action}-{revocation}"
    )
    operation = f"replay-{receipt_action}-{revocation}"

    async def replay():
        if receipt_action == "prepare":
            return await prepare(transfer_engine, now, plan, operation)
        return await accept(transfer_engine, now, proposal, operation)

    if receipt_action == "prepare":
        await replay()
    else:
        await accept(transfer_engine, now, proposal, operation)
    if revocation in {"pantry", "shopping"}:
        settings = transfer_engine.snapshot()["settings"]
        await transfer_engine.execute(
            "owner",
            "settings.save",
            {
                "name": settings["name"],
                "language": settings["language"],
                "modules": [module for module in settings["modules"] if module != revocation],
            },
            f"disable-{revocation}",
            now,
        )
        expected = "module_disabled"
    else:
        member = transfer_engine.snapshot()["members"]["parent"]
        await transfer_engine.execute(
            "owner",
            "members.save",
            {
                "id": member["id"],
                "revision": member["revision"],
                "name": member["name"],
                "role": "adult" if revocation == "role" else "parent",
                "active": revocation != "inactive",
            },
            f"revoke-{revocation}",
            now,
        )
        expected = "forbidden"
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match=expected):
        await replay()
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
async def test_required_group_over_one_million_is_rejected_without_write(
    transfer_engine, store, now
):
    plan = await published_plan(
        transfer_engine,
        now,
        entries=[
            meal_entry(ingredients=[ingredient(quantity=600_000)]),
            meal_entry(
                date="2026-09-08",
                slot="breakfast",
                ingredients=[ingredient(name=" synthetic  MILK ", quantity=600_000)],
            ),
        ],
    )
    before, writes = transfer_engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await prepare(transfer_engine, now, plan)
    assert_no_write(transfer_engine, store, before, writes)


@pytest.mark.asyncio
async def test_large_totals_in_different_units_remain_independent(transfer_engine, now):
    plan = await published_plan(
        transfer_engine,
        now,
        entries=[
            meal_entry(ingredients=[ingredient(quantity=600_000)]),
            meal_entry(
                date="2026-09-08",
                slot="breakfast",
                ingredients=[ingredient(unit="ml", quantity=600_000)],
            ),
        ],
    )
    proposal = await prepare(transfer_engine, now, plan)
    assert {(line["unit"], line["required"]) for line in proposal["lines"]} == {
        ("l", 600_000),
        ("ml", 600_000),
    }


@pytest.mark.asyncio
async def test_six_decimal_residual_is_ceiled_to_smallest_shopping_quantity(transfer_engine, now):
    plan = await published_plan(
        transfer_engine,
        now,
        entries=[meal_entry(ingredients=[ingredient(quantity=1)])],
    )
    await add_shopping(transfer_engine, now, quantity=0.999999)
    proposal = await prepare(transfer_engine, now, plan)
    line = proposal["lines"][0]
    assert line["required"] == 1
    assert line["open_shopping"] == 0.999999
    assert line["quantity"] == 0.001
    accepted = await accept(transfer_engine, now, proposal)
    created = transfer_engine.snapshot()["shopping"][accepted["lines"][0]["shopping_id"]]
    assert created["quantity"] == 0.001
    assert accepted["transfer_count"] == 1


@pytest.mark.asyncio
async def test_terminal_transfer_is_reused_after_purchase_and_republished_plan_edit(
    transfer_engine, now
):
    plan = await published_plan(transfer_engine, now)
    proposal = await prepare(transfer_engine, now, plan)
    terminal = await accept(transfer_engine, now, proposal)
    shopping_id = terminal["lines"][0]["shopping_id"]
    shopping_item = transfer_engine.snapshot()["shopping"][shopping_id]
    await transfer_engine.execute(
        "parent",
        "shopping.purchase",
        {"id": shopping_id, "revision": shopping_item["revision"]},
        "buy-generated-item",
        now,
    )
    edited = await transfer_engine.execute(
        "parent",
        "pantry.meal_save",
        {
            "id": plan["id"],
            "revision": plan["revision"],
            "title": "Republished changed menu",
            "entries": [meal_entry(ingredients=[ingredient(quantity=5)])],
        },
        "edit-after-transfer",
        now,
    )
    republished = await transfer_engine.execute(
        "parent",
        "pantry.meal_publish",
        {"id": edited["id"], "revision": edited["revision"]},
        "republish-after-transfer",
        now,
    )
    later = await prepare(transfer_engine, now, republished, "prepare-after-transfer")
    assert later["id"] == terminal["id"]
    assert later["status"] == terminal["status"] == "accepted"
    assert later["lines"] == terminal["lines"]
    assert (
        len(
            [
                item
                for item in transfer_engine.snapshot()["shopping"].values()
                if item.get("meal_plan_id") == plan["id"]
            ]
        )
        == 1
    )
