"""Shared buyer metadata through actual parser, Engine, replay and assistant."""

import pytest

from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.intents import parse
from custom_components.family_assistant.telegram.router import route
from tests.test_assistant import Provider, enable


@pytest.mark.parametrize(
    "content",
    [
        "поручи Child купить 2 кг яблок",
        "попроси Child купить 2 кг яблок",
        "доручи Child купити 2 кг яблок",
        "попроси Child купити 2 кг яблок",
        "ask Child to buy 2 кг яблок",
        "assign Child to buy 2 кг яблок",
    ],
)
async def test_assigned_creation_and_helper_purchase(engine, store, now, content):
    reply = await route(engine, "parent", content, "assignment", now)
    row = engine.snapshot()["shopping"]["S000001"]
    assert (row["buyer"], row["name"], row["quantity"], row["unit"]) == ("child", "яблок", 2, "кг")
    assert row["status"] == "approved" and "buyer_revision" not in row
    assert "Child" in reply and not engine.snapshot()["tasks"]
    assert engine.view("sibling")["shopping"][0]["id"] == row["id"]
    restarted = Engine(store.value, store.save)
    assert await route(restarted, "parent", content, "assignment", now) == reply
    assert len(restarted.snapshot()["shopping"]) == 1
    await route(restarted, "sibling", "/bought S000001 | 1", "help", now)
    changed = restarted.snapshot()["shopping"][row["id"]]
    assert changed["buyer"] == "child" and changed["purchased"] == 1
    assert changed["history"][-1]["actor"] == "sibling"


@pytest.mark.parametrize(
    "content",
    [
        "назначь Child задачу купить хлеб",
        "/task Child | купить хлеб",
        "признач Child завдання купити хліб",
        "assign Child task buy bread",
        "assign task Child to buy bread",
        "assign Child task to buy bread",
    ],
)
async def test_explicit_task_stays_task(engine, now, content):
    await route(engine, "parent", content, "task", now)
    assert len(engine.snapshot()["tasks"]) == 1 and not engine.snapshot()["shopping"]


@pytest.mark.parametrize(
    "content,name",
    [
        ("купи чай для похудения", "чай для похудения"),
        ("buy food for birds", "food for birds"),
    ],
)
async def test_product_purpose_is_not_buyer(engine, now, content, name):
    await route(engine, "parent", content, "plain", now)
    item = engine.snapshot()["shopping"]["S000001"]
    assert item["name"] == name and item["buyer"] is None


@pytest.mark.parametrize(
    "assign,clear",
    [
        ("/assignbuy S000001 | Child", "/unassignbuy S000001"),
        ("назначь покупателя S000001 Child", "сними покупателя S000001"),
        ("зміни покупця S000001 Child", "прибери покупця S000001"),
        ("change buyer S000001 to Child", "unassign buyer S000001"),
    ],
)
async def test_reassign_clear_preserve_record_and_exact_retry(engine, store, now, assign, clear):
    row = await engine.execute(
        "parent",
        "shopping.add",
        {
            "name": "Bread",
            "quantity": 3,
            "unit": "pcs",
            "buyer": "adult",
            "category": "Bakery",
            "store": "Market",
            "note": "Shared",
            "barcode": "96385074",
        },
        "add",
        now,
    )
    await engine.execute(
        "adult", "shopping.purchase", {"id": row["id"], "revision": 1, "quantity": 1}, "help", now
    )
    before = engine.snapshot()["shopping"][row["id"]]
    response = await route(engine, "parent", assign, "assign", now)
    edited = engine.snapshot()["shopping"][row["id"]]
    assert edited["buyer"] == "child" and len(engine.snapshot()["shopping"]) == 1
    for field in (
        "name",
        "quantity",
        "unit",
        "purchased",
        "status",
        "creator",
        "category",
        "store",
        "note",
        "barcode",
    ):
        assert edited[field] == before[field]
    assert edited["history"][-1]["detail"] == {"fields": ["buyer"]}
    await route(engine, "parent", clear, "clear", now)
    restarted = Engine(store.value, store.save)
    assert await route(restarted, "parent", assign, "assign", now) == response
    assert restarted.snapshot()["shopping"][row["id"]]["buyer"] is None
    assert len(restarted.snapshot()["shopping"][row["id"]]["history"]) == 4


@pytest.mark.parametrize("query", ["/shopping mine", "мои покупки", "мої покупки", "my shopping"])
async def test_self_filter_is_not_a_visibility_rule(engine, now, query):
    for name, buyer in (
        ("Own assigned", "child"),
        ("Other assigned", "sibling"),
        ("Unassigned", None),
    ):
        await engine.execute("parent", "shopping.add", {"name": name, "buyer": buyer}, name, now)
    answer = await route(engine, "child", query, "read", now)
    assert (
        "Own assigned" in answer and "Other assigned" not in answer and "Unassigned" not in answer
    )
    shared = await route(engine, "child", "/shopping", "family", now)
    assert all(name in shared for name in ("Own assigned", "Other assigned", "Unassigned"))
    parent = await route(engine, "parent", "/shopping Sibling", "buyer-read", now)
    assert "Other assigned" in parent and "Own assigned" not in parent


@pytest.mark.parametrize(
    "query", ["shopping list", "покупки", "список покупок", "/shopping", "show shopping"]
)
async def test_existing_family_list_grammar(engine, now, query):
    await engine.execute("parent", "shopping.add", {"name": "Canary"}, "add", now)
    assert "Canary" in await route(engine, "parent", query, "read", now)


@pytest.mark.parametrize(
    "recipient,error",
    [
        ("Missing", "unknown_member"),
        ("Guest", "invalid_field"),
        ("Child Sibling", "unknown_member"),
    ],
)
async def test_unresolved_recipient_has_no_side_effects(engine, now, recipient, error):
    before = engine.snapshot()
    with pytest.raises(DomainError, match=error):
        await route(engine, "parent", f"ask {recipient} to buy bread", "no", now)
    assert engine.snapshot() == before


@pytest.mark.parametrize(
    "content",
    ["не поручи Child купить хлеб", "do not ask Child to buy bread", '"ask Child to buy bread"'],
)
def test_negated_or_quoted_assignment_is_not_a_command(engine, now, content):
    assert parse(engine.snapshot(), engine.view("parent"), content, now) is None


async def test_member_pin_checks_inside_transaction_and_is_not_stored(engine, store, now):
    intent = parse(engine.snapshot(), engine.view("parent"), "ask Child to buy bread", now)
    state = engine.snapshot()
    state["members"]["child"]["revision"] += 1
    changed = Engine(state, store.save)
    with pytest.raises(DomainError, match="conflict"):
        await changed.execute("parent", intent.action, intent.payload, "stale", now)
    assert changed.snapshot() == state


@pytest.mark.parametrize("pin", [True, False, None, 1.0, "1", 0, -1, 2**53])
async def test_strict_buyer_pin(engine, now, pin):
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute(
            "parent",
            "shopping.add",
            {"name": "Bread", "buyer": "child", "buyer_revision": pin},
            "bad",
            now,
        )
    assert engine.snapshot() == before


async def test_edit_and_purchase_race_preserves_partial_purchase(engine, now):
    await route(engine, "parent", "ask Adult to buy 3 bread", "add", now)
    intent = parse(engine.snapshot(), engine.view("parent"), "change buyer S000001 to Child", now)
    await route(engine, "sibling", "/bought S000001 | 1", "help", now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute("parent", intent.action, intent.payload, "stale-edit", now)
    assert engine.snapshot() == before


def shopping_model(**changes):
    return Provider(
        {
            "kind": "commands",
            "operations": [
                {
                    "action": "shopping.add",
                    "payload": {
                        "name": "bread",
                        "quantity": 1,
                        "unit": "",
                        "buyer": "child",
                        **changes,
                    },
                }
            ],
        }
    )


async def test_proven_name_repair_and_offline_reuse_bind_shopping_module(engine, store, now):
    await enable(engine, now)
    state = engine.snapshot()
    state["members"]["child"]["name"] = "Alexander"
    state["settings"]["modules"].remove("tasks")
    engine = Engine(state, store.save)
    provider = shopping_model()
    assistant = Assistant(engine, Cascade([provider], {}))
    content = "ask Alexandr to buy bread"
    first = await route(engine, "parent", content, "repair", now, fallback=assistant.respond)
    assert "L000001" in first and len(provider.calls) == 1
    assert len(engine.snapshot()["shopping"]) == 1 and not engine.snapshot()["tasks"]
    assert not engine.snapshot()["proposals"]
    restarted = Engine(store.value, store.save)
    assert "L000001" in await route(restarted, "parent", "ask Alexandr to buy milk", "offline", now)
    assert len(restarted.snapshot()["shopping"]) == 2
    assert await route(restarted, "parent", content, "repair", now) == first
    disabled = restarted.snapshot()
    disabled["settings"]["modules"].remove("shopping")
    stopped = Engine(disabled, store.save)
    with pytest.raises(DomainError, match="module_disabled"):
        await route(stopped, "parent", content, "repair", now)


@pytest.mark.parametrize(
    "change", [{"name": "different"}, {"quantity": 2}, {"buyer": "sibling"}, {"note": "extra"}]
)
async def test_model_payload_drift_is_reviewed_not_autoexecuted(engine, store, now, change):
    await enable(engine, now)
    state = engine.snapshot()
    state["members"]["child"]["name"] = "Alexander"
    engine = Engine(state, store.save)
    assistant = Assistant(engine, Cascade([shopping_model(**change)], {}))
    reply = await route(
        engine, "parent", "ask Alexandr to buy bread", "drift", now, fallback=assistant.respond
    )
    assert "/confirm" in reply
    assert not engine.snapshot()["shopping"] and not engine.snapshot()["memory"].get("phrases")


async def test_purchase_wording_cannot_be_reinterpreted_as_task(engine, now):
    await enable(engine, now)
    provider = Provider(
        {
            "kind": "commands",
            "operations": [
                {"action": "tasks.create", "payload": {"title": "bread", "assignee": "child"}}
            ],
        }
    )
    assistant = Assistant(engine, Cascade([provider], {}))
    with pytest.raises(DomainError, match="ambiguous_command"):
        await route(
            engine,
            "parent",
            "ask Missing to buy bread",
            "wrong-kind",
            now,
            fallback=assistant.respond,
        )
    assert not engine.snapshot()["shopping"] and not engine.snapshot()["tasks"]


@pytest.mark.parametrize(
    "content",
    [
        "ask Child to buy bread and ask Sibling to buy milk",
        "поручи Child купить хлеб и поручи Sibling купить молоко",
    ],
)
async def test_multiple_assignments_do_not_become_one_product(engine, now, content):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="ambiguous_command"):
        await route(engine, "parent", content, "multi", now)
    assert engine.snapshot() == before


async def test_unknown_buyer_edit_clarifies_without_model_reinterpretation(engine, now):
    await route(engine, "parent", "buy bread", "add", now)

    async def unexpected(*args):
        pytest.fail("An exact S-ID edit must not be reinterpreted as creation")

    before = engine.snapshot()
    with pytest.raises(DomainError, match="unknown_member"):
        await route(
            engine, "parent", "change buyer S000001 to Missing", "edit", now, fallback=unexpected
        )
    assert engine.snapshot() == before


@pytest.mark.parametrize(
    "actor,buyer,allowed",
    [
        ("child", "Child", True),
        ("child", "Sibling", False),
        ("adult", "Child", True),
        ("guest", "Child", False),
    ],
)
async def test_existing_assignment_roles_preserved(engine, now, actor, buyer, allowed):
    if not allowed:
        with pytest.raises(DomainError, match="forbidden"):
            await route(engine, actor, f"ask {buyer} to buy bread", "role", now)
        assert not engine.snapshot()["shopping"]
    else:
        await route(engine, actor, f"ask {buyer} to buy bread", "role", now)
        row = engine.snapshot()["shopping"]["S000001"]
        assert row["status"] == ("pending" if actor == "child" else "approved")


async def test_failed_store_does_not_commit_assignment_or_name_rule(engine, store, now):
    await enable(engine, now)
    state = engine.snapshot()
    state["members"]["child"]["name"] = "Alexander"
    engine = Engine(state, store.save)
    payload = {
        "source": "ask Alexandr to buy bread",
        "actor_revision": 1,
        "member_revision": 1,
        "commands": [
            {
                "action": "shopping.add",
                "payload": {
                    "name": "bread",
                    "quantity": 1,
                    "unit": "",
                    "buyer": "child",
                    "buyer_revision": 1,
                },
            }
        ],
    }
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("parent", "conversation.apply_name_repair", payload, "failed", now)
    assert engine.snapshot() == before
    store.fail = False
    result = await engine.execute(
        "parent", "conversation.apply_name_repair", payload, "failed", now
    )
    assert result["status"] == "repaired" and len(engine.snapshot()["shopping"]) == 1
    assert (
        await engine.execute("parent", "conversation.apply_name_repair", payload, "failed", now)
        == result
    )


@pytest.mark.parametrize(
    "name,content",
    [("Роман", "поручи Ропану купить bread"), ("Роман", "доручи Ропану купити bread")],
)
async def test_cyrillic_purchase_repair_preserves_exact_shape(engine, store, now, name, content):
    await enable(engine, now)
    state = engine.snapshot()
    state["members"]["child"]["name"] = name
    engine = Engine(state, store.save)
    assistant = Assistant(engine, Cascade([shopping_model()], {}))
    reply = await route(engine, "parent", content, "cyrillic", now, fallback=assistant.respond)
    assert "L000001" in reply and not engine.snapshot()["proposals"]
    assert engine.snapshot()["shopping"]["S000001"]["buyer"] == "child"


async def test_ambiguous_typo_requires_review_and_does_not_learn(engine, store, now):
    await enable(engine, now)
    state = engine.snapshot()
    state["members"]["child"]["name"] = "Alexander"
    state["members"]["sibling"]["name"] = "Alexandra"
    engine = Engine(state, store.save)
    assistant = Assistant(engine, Cascade([shopping_model()], {}))
    reply = await route(
        engine, "parent", "ask Alexandr to buy bread", "ambiguous", now, fallback=assistant.respond
    )
    assert "/confirm" in reply and not engine.snapshot()["shopping"]
    assert not engine.snapshot()["memory"].get("phrases")
