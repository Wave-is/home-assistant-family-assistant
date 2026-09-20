"""Real parser/router/Engine and Telegram-manager regressions with fictional data."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.errors import ERRORS
from custom_components.family_assistant.telegram.intents import parse
from custom_components.family_assistant.telegram.router import COPY, route
from tests.test_telegram_command_scope import NOW, fixture, update
from tests.test_telegram_command_scope import manager_module as manager_module  # noqa: F401


@pytest.mark.parametrize(
    "command,title,policy",
    [
        ("задача Child убрать Стол на завтра с фотоотчетом", "убрать Стол", "photo"),
        ("задача Child убрать Стол с фотоотчётом на завтра", "убрать Стол", "photo"),
        ("назначь Child задачу убрать Стол завтра нужен фотоотчёт", "убрать Стол", "photo"),
        ("Child задача убрать Стол завтра с фото", "убрать Стол", "photo"),
        ("задача Child убрать Стол без отчёта завтра", "убрать Стол", "none"),
        ("задача Child убрать Стол завтра с текстовым отчетом", "убрать Стол", "text"),
        ("створи завдання Child прибрати Стіл на завтра з фотозвітом", "прибрати Стіл", "photo"),
        ("завдання Child прибрати Стіл потрібен фотозвіт завтра", "прибрати Стіл", "photo"),
        ("Child завдання прибрати Стіл завтра без звіту", "прибрати Стіл", "none"),
        ("завдання Child прибрати Стіл з текстовим звітом завтра", "прибрати Стіл", "text"),
        ("create task Child Clear Desk for tomorrow with a photo report", "Clear Desk", "photo"),
        ("assign Child task Clear Desk with a photo report tomorrow", "Clear Desk", "photo"),
        ("Child task Clear Desk tomorrow without a report", "Clear Desk", "none"),
        ("task Child Clear Desk with a text report tomorrow", "Clear Desk", "text"),
        ("task Child Clear Desk tomorrow photo report required", "Clear Desk", "photo"),
        ("task Child Clear Desk tomorrow report not required", "Clear Desk", "none"),
        ("task Child Clear Desk tomorrow no report required", "Clear Desk", "none"),
    ],
)
async def test_report_deadline_order_preserves_structured_payload(
    engine, now, command, title, policy
):
    intent = parse(engine.snapshot(), engine.view("parent"), command, now)
    assert intent.action == "tasks.create"
    assert intent.payload == {
        "assignee": "child",
        "title": title,
        "due_at": "2026-09-07T20:00:00+00:00",
        "report_type": policy,
    }
    await route(engine, "parent", command, "create", now)
    task = engine.snapshot()["tasks"]["T000001"]
    assert all(task[key] == value for key, value in intent.payload.items())


@pytest.mark.parametrize(
    "title",
    [
        "Check HDMI-2 cable",
        "Read “Tomorrow, and tomorrow”",
        "Work in a shop",
        "Купить корм на неделю",
        "Рассортировать фото гостей",
        "Create 3D Model",
    ],
)
async def test_unqualified_exact_titles_are_not_normalized(engine, now, title):
    await route(engine, "parent", "task Child " + title, "literal", now)
    task = engine.snapshot()["tasks"]["T000001"]
    assert task["title"] == title
    assert task["due_at"] is None and task["report_type"] == "text"


@pytest.mark.parametrize(
    "suffix,error",
    [
        ("завтра с фотоотчетом без отчета", "invalid_field"),
        ("с фотоотчетом завтра без отчета", "invalid_field"),
        ("завтра з фотозвітом без звіту", "invalid_field"),
        ("tomorrow with a text report with a photo report", "invalid_field"),
        ("without a report tomorrow with photo", "invalid_field"),
        ("tomorrow not with a photo report", "invalid_field"),
        ("завтра не с фотоотчетом", "invalid_field"),
        ("tomorrow without a photo report", "invalid_field"),
        ("tomorrow no photo report required", "invalid_field"),
        ("tomorrow without a text report required", "invalid_field"),
        ("завтра с фотоотчетом возможно", "invalid_field"),
        ("с фотоотчетом на вчера", "invalid_field"),
        ("на не завтра с фотоотчетом", "invalid_deadline"),
        ("not for tomorrow with a report", "invalid_deadline"),
        ("deadline in 1000 days at 18:00 with a photo report", "invalid_deadline"),
        ("in 1/2 days at 18:00 without a report", "invalid_deadline"),
        ("tomorrow with a report today", "invalid_deadline"),
        ("срок завтра и удали остальные с фотоотчетом", "invalid_deadline"),
    ],
)
async def test_malformed_contradictory_or_negated_slots_do_not_create(engine, now, suffix, error):
    with pytest.raises(DomainError, match=error):
        await route(engine, "parent", "task Child Work " + suffix, "invalid", now)
    assert not engine.snapshot()["tasks"]
    assert not engine.snapshot()["telegram"].get("plans")


async def test_missing_title_and_conflicting_report_qualifiers_need_no_model(engine, now):
    async def forbidden_fallback(*_args):
        pytest.fail("Invalid report policy must not be reinterpreted by a model")

    for text in ("task Child tomorrow with a photo report", "task Child Work with report maybe"):
        with pytest.raises(DomainError, match="invalid_field"):
            await route(engine, "parent", text, "invalid", now, fallback=forbidden_fallback)
    assert not engine.snapshot()["tasks"]


async def test_reported_task_replay_survives_restart_and_relative_date_change(engine, store, now):
    text = "задача Child убрать Стол через неделю с фотоотчетом"
    reply = await route(engine, "parent", text, "stable", now)
    restarted = Engine(store.value, store.save)
    assert await route(restarted, "parent", text, "stable", now + timedelta(days=2)) == reply
    tasks = list(restarted.snapshot()["tasks"].values())
    assert len(tasks) == 1
    assert tasks[0]["due_at"] == "2026-09-13T20:00:00+00:00"
    assert tasks[0]["report_type"] == "photo" and tasks[0]["title"] == "убрать Стол"


@pytest.mark.parametrize("actor", ["child", "adult", "guest"])
async def test_creation_qualifiers_do_not_confer_assignment_rights(engine, now, actor):
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, actor, "task Sibling Work tomorrow with a photo report", "forbid", now)
    assert not engine.snapshot()["tasks"]


async def test_child_self_assignment_retains_photo_submission_gate(engine, now):
    await route(engine, "child", "task Child Work tomorrow with a photo report", "own", now)
    with pytest.raises(DomainError, match="photo"):
        await route(engine, "child", "/done T000001 | Done", "submit", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "assigned"


@pytest.mark.parametrize(
    "text,name,quantity,unit",
    [
        ("добавь 2 кг яблок в покупки", "яблок", 2, "кг"),
        ("додай 1,5 л Молока у покупки", "Молока", 1.5, "л"),
        ("add 2 kg Apples to shopping", "Apples", 2, "kg"),
        ("add 0.5 liters Milk to the shopping list", "Milk", 0.5, "liters"),
        ("buy 2kg Apples", "Apples", 2, "kg"),
        ("купить 3 шт. Лимона", "Лимона", 3, "шт"),
        ("купити 2 яблука", "яблука", 2, ""),
        ("buy 2 Apples", "Apples", 2, ""),
        ("buy 7UP", "7UP", 1, ""),
        ("buy 3D puzzle", "3D puzzle", 1, ""),
        ("buy Tea | 1,5 | bags", "Tea", 1.5, "bags"),
    ],
)
async def test_natural_shopping_fields_are_saved_exactly(engine, now, text, name, quantity, unit):
    reply = await route(engine, "parent", text, "quantity", now)
    item = engine.snapshot()["shopping"]["S000001"]
    assert (item["name"], item["quantity"], item["unit"]) == (name, quantity, unit)
    assert await route(engine, "parent", text, "quantity", now + timedelta(days=1)) == reply
    assert len(engine.snapshot()["shopping"]) == 1


@pytest.mark.parametrize(
    "item",
    [
        "-2 kg Apples",
        "0 kg Apples",
        "1/2 kg Apples",
        "2..5 kg Apples",
        "2e3 kg Apples",
        "2 3 kg Apples",
        "2 kg",
        "2kg",
        "NaN kg Apples",
        "2",
        "Tea | inf | kg",
        "Tea | 1 | kg | extra",
    ],
)
async def test_malformed_quantities_do_not_become_item_names(engine, now, item):
    with pytest.raises(DomainError, match="invalid_field"):
        await route(engine, "parent", "buy " + item, "bad-quantity", now)
    assert not engine.snapshot()["shopping"]


async def test_natural_quantity_keeps_child_approval_and_guest_denial(engine, now):
    await route(engine, "child", "додай 2 кг яблук у покупки", "child", now)
    item = engine.snapshot()["shopping"]["S000001"]
    assert item["status"] == "pending" and item["quantity"] == 2 and item["unit"] == "кг"
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/approvebuy S000001", "approve", now)
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "guest", "buy 2 kg Apples", "guest", now)
    assert len(engine.snapshot()["shopping"]) == 1


@pytest.mark.parametrize(
    "text",
    [
        "не добавь 2 кг яблок в покупки",
        "не додай 2 кг яблук у покупки",
        "do not add 2 kg Apples to shopping",
        "не задача Child убрать стол с фотоотчетом",
        "do not create task Child Work with a photo report",
    ],
)
async def test_negated_creation_does_not_mutate(engine, now, text):
    try:
        await route(engine, "parent", text, "negative", now)
    except DomainError:
        pass
    assert not engine.snapshot()["tasks"] and not engine.snapshot()["shopping"]


async def test_literal_slash_titles_and_explicit_shopping_fields_stay_literal(engine, now):
    title = "Work tomorrow with a photo report"
    await route(engine, "parent", "/task Child | " + title, "literal", now)
    task = engine.snapshot()["tasks"]["T000001"]
    assert task["title"] == title and task["due_at"] is None and task["report_type"] == "text"
    await route(engine, "parent", "buy 7UP | 2 | bottles", "buy", now)
    item = engine.snapshot()["shopping"]["S000001"]
    assert (item["name"], item["quantity"], item["unit"]) == ("7UP", 2, "bottles")


@pytest.mark.parametrize(
    "text",
    [
        "покажи задачи Child",
        "покажи завдання Child",
        "show tasks for Child",
        "tasks for Child",
        "/tasks Child",
        "/задачи Child",
    ],
)
async def test_named_task_query_filters_authorized_records(engine, now, text):
    await route(engine, "parent", "/task Child | Child work", "child", now)
    await route(engine, "parent", "/task Sibling | Sibling work", "sibling", now)
    reply = await route(engine, "parent", text, "list", now, private=True)
    assert "Child work" in reply and "Sibling work" not in reply
    assert "Child work" in await route(engine, "child", text, "own-list", now, private=True)


@pytest.mark.parametrize("actor", ["child", "adult", "guest"])
async def test_named_query_is_not_cross_member_authority(engine, now, actor):
    await route(engine, "parent", "/task Sibling | Sibling secret", "sibling", now)
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, actor, "покажи задачи Sibling", "list", now, private=True)


@pytest.mark.parametrize("text", ["task Shared Name Work with photo", "покажи задачи Shared Name"])
async def test_creation_and_named_query_reject_equal_configured_aliases(engine, now, text):
    def aliases(ctx):
        for member in ("child", "sibling"):
            ctx.state["members"][member]["aliases"] = ["Shared Name"]

    await engine.system_update("aliases", now, aliases)
    with pytest.raises(DomainError, match="ambiguous_member"):
        await route(engine, "parent", text, "ambiguous", now)
    assert not engine.snapshot()["tasks"]


async def test_group_named_query_hides_private_and_personal_tasks(engine, now):
    await route(engine, "parent", "/task Child | Child public", "public", now)
    await route(engine, "parent", "/task Child | Child private", "private", now)
    await engine.system_update(
        "private",
        now,
        lambda ctx: ctx.state["tasks"]["T000002"].update(delivery_scope="private"),
    )
    await route(
        engine, "child", "remind me to Private reminder tomorrow", "personal", now, private=True
    )
    group = await route(engine, "parent", "show tasks Child", "group", now, private=False)
    assert (
        "Child public" in group and "Child private" not in group and "Private reminder" not in group
    )
    parent = await route(engine, "parent", "show tasks Child", "parent", now, private=True)
    assert "Child private" in parent and "Private reminder" not in parent
    child = await route(engine, "child", "show tasks Child", "child", now, private=True)
    assert "Child private" in child and "Private reminder" in child


@pytest.mark.parametrize("language", ["ru", "uk", "en"])
async def test_manager_reports_localized_invalid_qualifier_without_jobs(manager_module, language):
    engine, _store, _entry, runtime, manager, client = fixture(manager_module)
    await engine.system_update(
        "language",
        NOW,
        lambda ctx: ctx.state["members"]["owner"].update(language=language),
    )
    runtime.assistant = object()
    await manager.process(
        update(text="task owner Work tomorrow with a photo report without a report")
    )
    state = engine.snapshot()
    replies = [event for event in state["outbox"].values() if event["key"] == "telegram_reply"]
    assert len(replies) == 1
    assert replies[0]["data"]["text"] == COPY[language]["error"].format(
        error=ERRORS[language]["invalid_field"].rstrip(".!?")
    )
    assert not state["tasks"] and not state["assistant_jobs"]
    assert client.calls == []


async def test_manager_addressing_duplicate_delivery_and_quantity(manager_module):
    engine, _store, _entry, _runtime, manager, client = fixture(manager_module)
    await manager.process(update(10, group=True, text="add 2 kg Apples to shopping"))
    assert not engine.snapshot()["shopping"]
    request = update(11, group=True, text="@synthetic_family_bot add 2 kg Apples to shopping")
    await manager.process(request)
    await manager.process(request)
    items = list(engine.snapshot()["shopping"].values())
    assert len(items) == 1
    assert (items[0]["name"], items[0]["quantity"], items[0]["unit"]) == ("Apples", 2, "kg")
    assert client.calls == []
