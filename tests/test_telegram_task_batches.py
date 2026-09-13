"""Numbered Telegram creation through real parsers, Engine, Store and manager."""

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.context import result_refs
from custom_components.family_assistant.telegram.errors import ERRORS
from custom_components.family_assistant.telegram.router import COPY, route
from custom_components.family_assistant.telegram.task_batches import parsed
from tests.test_telegram_command_scope import NOW, fixture, update
from tests.test_telegram_command_scope import manager_module as manager_module  # noqa: F401


@pytest.mark.parametrize("count", [2, 3, 4, 5])
@pytest.mark.parametrize(
    "header",
    [
        "create {count} tasks for Child",
        "создай {count} задачи для Child",
        "створи {count} завдання для Child",
    ],
)
async def test_declared_counts_create_one_ordered_atomic_batch(engine, store, now, count, header):
    message = (
        header.format(count=count)
        + ":\n"
        + "\n".join(f"{index}. Chore {index}, preserve THIS title" for index in range(1, count + 1))
    )
    before = engine.snapshot()
    payload = parsed(before, engine.view("parent"), message, now)
    assert len(payload["commands"]) == count
    reply = await route(engine, "parent", message, "numbered", now)
    state = engine.snapshot()
    tasks = list(state["tasks"].values())
    assert [task["title"] for task in tasks] == [
        f"Chore {index}, preserve THIS title" for index in range(1, count + 1)
    ]
    assert all(task["assignee"] == "child" and task["assignee_revision"] == 1 for task in tasks)
    assert len(state["audit"]) == len(before["audit"]) + 1
    assert len(state["outbox"]) == count
    assert state["sequences"]["T"] == count
    assert store.calls == 2  # One interpretation checkpoint, one whole Engine transaction.
    assert all(task["id"] in reply for task in tasks)
    assert state["telegram"]["plans"]["numbered"]["action"] == "batch"
    assert state["telegram"]["plans"]["numbered"]["payload"] == payload
    assert result_refs(state["processed"]["numbered"]["result"]) == [task["id"] for task in tasks]


@pytest.mark.parametrize(
    "header,first,second",
    [
        (
            "создай 2 задачи Child на завтра с фотоотчетом",
            "Убрать Стол",
            "задача Sibling Собрать Рюкзак через неделю без отчета",
        ),
        (
            "створи 2 завдання Child на завтра з фотозвітом",
            "Прибрати Стіл",
            "завдання Sibling Зібрати Рюкзак через тиждень без звіту",
        ),
        (
            "create 2 tasks for Child for tomorrow with a photo report",
            "Clear Desk",
            "task Sibling Pack Bag in a week without a report",
        ),
    ],
)
async def test_shared_defaults_and_per_item_overrides(engine, now, header, first, second):
    await route(engine, "parent", f"{header}:\n1) {first}\n2) {second}", "defaults", now)
    one, two = engine.snapshot()["tasks"].values()
    assert one["title"] == first and one["assignee"] == "child"
    assert one["report_type"] == "photo" and one["due_at"] == "2026-09-07T20:00:00+00:00"
    assert two["assignee"] == "sibling" and two["report_type"] == "none"
    assert two["due_at"] == "2026-09-13T20:00:00+00:00"
    assert not any(word in two["title"] for word in ("через", "without", "без"))


async def test_header_without_shared_member_requires_explicit_items(engine, now):
    message = (
        "2 tasks tomorrow with a text report:\n"
        "1. for Child: Keep HDMI-2, version 1.2; label: FRONT\n"
        "2. для Sibling: Read Chapter 3 завтра в 18:30 с фотоотчетом"
    )
    await route(engine, "parent", message, "members", now)
    one, two = engine.snapshot()["tasks"].values()
    assert one["title"] == "Keep HDMI-2, version 1.2; label: FRONT"
    assert one["report_type"] == "text" and one["due_at"].startswith("2026-09-07T20:00")
    assert two["title"] == "Read Chapter 3" and two["report_type"] == "photo"
    assert two["assignee"] == "sibling" and two["due_at"].startswith("2026-09-07T18:30")


async def test_shared_multiword_member_is_resolved_whole_and_preserves_declared_duplicates(
    engine, now
):
    await engine.system_update(
        "names",
        now,
        lambda ctx: ctx.state["members"]["sibling"].update(name="Child One"),
    )
    await route(engine, "parent", "2 tasks for Child One:\n1. Work\n2. Work", "twice", now)
    tasks = list(engine.snapshot()["tasks"].values())
    assert len(tasks) == 2 and all(task["assignee"] == "sibling" for task in tasks)


INVALID = [
    "create 2 tasks for Child:\n1. Work",
    "create 2 tasks for Child:\n1. Work\n2. More\n3. Extra",
    "create 1 tasks for Child:\n1. Work",
    "create 6 tasks for Child:\n1. Work\n2. More",
    "create 0 tasks for Child:\n1. Work\n2. More",
    "create -2 tasks for Child:\n1. Work\n2. More",
    "create 2.5 tasks for Child:\n1. Work\n2. More",
    "create 02 tasks for Child:\n1. Work\n2. More",
    "create two tasks for Child:\n1. Work\n2. More",
    "create 2 tasks for Child\n1. Work\n2. More",
    "create 2 tasks for Child: 1. Work 2. More",
    "create 2 tasks for Child:\n2. Work\n1. More",
    "create 2 tasks for Child:\n1. Work\n1. More",
    "create 2 tasks for Child:\n1. Work\n3. More",
    "create 2 tasks for Child:\n01. Work\n2. More",
    "create 2 tasks for Child:\n1. Work\n2)",
    "create 2 tasks for Child:\n1. Work\n2) More",
    "create 2 tasks for Child:\n1. Work\n2.More",
    "create 2 tasks for Child:\n1. Work\n2. ",
    "create 2 tasks for Child:\n1. Work\n2. More\nAnd cancel everything",
    "create 2 tasks for Child:\n1. Work\nContinuation\n2. More",
    "create 2 tasks for Child:\n1. Work\n2. More\ntomorrow",
    "create tasks for Child:\n1. Work\n2. More",
    "task Child Work:\n1. First\n2. Second",
    "не создай 2 задачи Child:\n1. Work\n2. More",
    "do not create 2 tasks for Child:\n1. Work\n2. More",
    "2 tasks for Child:\n1. Work\n2. do not create task Sibling More",
    "2 tasks for Child:\n1. Work\n2. не задача Sibling More",
    "2 tasks for Missing Person:\n1. Work\n2. More",
    "2 tasks:\n1. task Child Work\n2. More",
    "2 tasks for Child:\n1. Work\n2. for Missing Person: More",
    "2 tasks for Child:\n1. Work\n2. task Missing Person: More",
    "2 tasks for Child with a photo report without a report:\n1. Work\n2. More",
    "2 tasks for Child:\n1. Work\n2. More tomorrow with photo without a report",
    "2 tasks for Child deadline in 1000 days at 18:00:\n1. Work\n2. More",
    "2 tasks for Child:\n1. Work\n2. More deadline tomorrow and cancel everything",
    "2 tasks for Child:\n1. Work\n2. More not within a week",
    "2 tasks for Child:\n1. Work\n2. tomorrow with a report",
    "2 tasks:\n1. task Child Work\n2. /award Child | -1 | No reason",
    "2 tasks:\n1. task Child Work\n2. 2 tasks for Sibling: Work, More",
    "2 tasks for Child:\n1. Work\n2. /award Child | -1 | No reason",
    "2 tasks for Child:\n1. Work\n2. 2 tasks for Sibling: Work, More",
]


@pytest.mark.parametrize("message", INVALID)
async def test_invalid_batch_cannot_fall_through_to_partial_parser_or_model(
    engine, store, now, message
):
    async def forbidden_fallback(*_args):
        pytest.fail("A claimed invalid numbered batch reached model fallback")

    before = engine.snapshot()
    with pytest.raises(DomainError):
        await route(engine, "parent", message, "invalid", now, fallback=forbidden_fallback)
    assert engine.snapshot() == before
    assert store.calls == 0


@pytest.mark.parametrize("actor", ["child", "adult", "guest"])
async def test_one_unauthorized_recipient_rejects_whole_batch_before_plan(
    engine, store, now, actor
):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await route(
            engine, actor, f"2 tasks:\n1. task {actor} Work\n2. task Sibling More", "roles", now
        )
    assert engine.snapshot() == before and store.calls == 0


@pytest.mark.parametrize("actor", ["child", "adult"])
async def test_nonparent_may_create_only_self_tasks(engine, now, actor):
    await route(engine, actor, f"2 tasks for {actor}:\n1. Work\n2. More", "self", now)
    assert all(task["assignee"] == actor for task in engine.snapshot()["tasks"].values())


@pytest.mark.parametrize("kind", ["inactive", "ambiguous", "guest"])
async def test_invalid_last_member_preserves_all_state(engine, store, now, kind):
    state = engine.snapshot()
    target = "Sibling"
    if kind == "inactive":
        state["members"]["sibling"]["active"] = False
    elif kind == "ambiguous":
        for member in ("child", "sibling"):
            state["members"][member]["aliases"] = ["Shared Alias"]
        target = "Shared Alias"
    else:
        target = "Guest"
    engine = Engine(state, store.save)
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await route(
            engine, "parent", f"2 tasks:\n1. task Child Work\n2. for {target}: More", "bad", now
        )
    assert engine.snapshot() == before and store.calls == 0


async def test_plan_survives_failed_atomic_store_and_retry_keeps_dates(engine, store, now):
    fail = True

    async def persist(state):
        if fail and state["tasks"]:
            raise OSError("Synthetic task checkpoint failure")
        await store.save(state)

    engine = Engine(engine.snapshot(), persist)
    content = "2 tasks for Child tomorrow with a photo report:\n1. Work\n2. More"
    with pytest.raises(OSError):
        await route(engine, "parent", content, "durable", now)
    failed = engine.snapshot()
    assert not failed["tasks"] and not failed["outbox"] and not failed["processed"]
    assert failed["sequences"].get("T", 0) == 0 and not failed["audit"]
    assert store.value == failed and "durable" in failed["telegram"]["plans"]
    fail = False
    engine = Engine(store.value, persist)
    response = await route(engine, "parent", content, "durable", now + timedelta(days=2))
    assert "T000001" in response and "T000002" in response
    assert all(
        task["due_at"].startswith("2026-09-07") for task in engine.snapshot()["tasks"].values()
    )
    saved = engine.snapshot()
    restarted = Engine(store.value, store.save)
    assert await route(restarted, "parent", content, "durable", now + timedelta(days=3)) == response
    assert restarted.snapshot() == saved
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await route(restarted, "parent", content.replace("More", "Different"), "durable", now)


async def test_pending_plan_rechecks_recipient_revision_after_restart(engine, store, now):
    async def persist(state):
        if state["tasks"]:
            raise OSError("Synthetic failure")
        await store.save(state)

    engine = Engine(engine.snapshot(), persist)
    content = "2 tasks:\n1. task Child Work\n2. task Sibling More"
    with pytest.raises(OSError):
        await route(engine, "parent", content, "pending", now)
    restarted = Engine(store.value, store.save)
    await restarted.execute(
        "owner",
        "members.save",
        {"id": "sibling", "revision": 1, "name": "New Sibling", "role": "child"},
        "rebind",
        now,
    )
    before = restarted.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await route(restarted, "parent", content, "pending", now)
    assert restarted.snapshot() == before and not restarted.snapshot()["tasks"]


async def test_member_write_between_plan_and_execution_rolls_back_entire_batch(engine, store, now):
    entered, release = asyncio.Event(), asyncio.Event()

    async def persist(state):
        if state["telegram"].get("plans") and not entered.is_set():
            entered.set()
            await release.wait()
        await store.save(state)

    engine = Engine(engine.snapshot(), persist)
    content = "2 tasks:\n1. task Child Work\n2. task Sibling More"
    creation = asyncio.create_task(route(engine, "parent", content, "race", now))
    await asyncio.wait_for(entered.wait(), 2)
    changed = asyncio.create_task(
        engine.execute(
            "owner",
            "members.save",
            {"id": "sibling", "revision": 1, "name": "Renamed Sibling", "role": "child"},
            "member-change",
            now,
        )
    )
    try:
        await asyncio.sleep(
            0
        )  # Queue the competing writer while interpretation holds the real lock.
        release.set()
        await changed
        with pytest.raises(DomainError, match="conflict"):
            await creation
        assert not engine.snapshot()["tasks"]
        assert engine.snapshot()["sequences"].get("T", 0) == 0
        assert not any(
            event["key"] == "task_assigned" for event in engine.snapshot()["outbox"].values()
        )
    finally:
        release.set()
        await asyncio.gather(creation, changed, return_exceptions=True)


@pytest.mark.parametrize("revocation", ["role", "module", "inactive"])
async def test_successful_replay_rechecks_current_authority(engine, now, revocation):
    content = "2 tasks for Child:\n1. Work\n2. More"
    await route(engine, "parent", content, "replay", now)

    def revoke(ctx):
        if revocation == "role":
            ctx.state["members"]["parent"]["role"] = "adult"
        elif revocation == "inactive":
            ctx.state["members"]["parent"]["active"] = False
        else:
            ctx.state["settings"]["modules"].remove("tasks")

    await engine.system_update("revoke", now, revoke)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden|module_disabled"):
        await route(engine, "parent", content, "replay", now)
    assert engine.snapshot() == before


async def test_multi_task_receipt_needs_explicit_id_for_done(engine, now):
    content = "2 tasks for Child:\n1. Work\n2. More"
    await route(engine, "parent", content, "create", now)
    refs = result_refs(engine.snapshot()["processed"]["create"]["result"])
    with pytest.raises(DomainError, match="context_required"):
        await route(engine, "child", "done", "unclear", now, refs)
    await route(engine, "child", "/done T000001 | Finished", "done", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "submitted"
    assert engine.snapshot()["tasks"]["T000002"]["status"] == "assigned"


@pytest.mark.parametrize("language", ["ru", "uk", "en"])
async def test_manager_invalid_count_is_localized_without_model_job(manager_module, language):
    engine, _store, _entry, runtime, manager, client = fixture(manager_module)
    await engine.system_update(
        "language", NOW, lambda ctx: ctx.state["members"]["owner"].update(language=language)
    )
    runtime.assistant = object()
    await manager.process(update(text="create 3 tasks for owner:\n1. Work\n2. More"))
    state = engine.snapshot()
    replies = [event for event in state["outbox"].values() if event["key"] == "telegram_reply"]
    assert len(replies) == 1
    assert replies[0]["data"]["text"] == COPY[language]["error"].format(
        error=ERRORS[language]["invalid_field"]
    )
    assert not state["tasks"] and not state["telegram"].get("plans") and not state["assistant_jobs"]
    assert client.calls == []


async def test_manager_addressing_duplicate_delivery_and_task_references(manager_module):
    engine, _store, _entry, _runtime, manager, client = fixture(manager_module)
    content = "create 2 tasks for owner:\n1. Work\n2. More"
    await manager.process(update(10, group=True, text=content))
    assert not engine.snapshot()["tasks"]
    request = update(11, group=True, text="@synthetic_family_bot " + content)
    await manager.process(request)
    await manager.process(deepcopy(request))
    state = engine.snapshot()
    assert len(state["tasks"]) == 2
    replies = [event for event in state["outbox"].values() if event["key"] == "telegram_reply"]
    assert len(replies) == 1
    assert replies[0]["data"]["refs"] == ["T000001", "T000002"]
    assert all(task in replies[0]["data"]["text"] for task in ("T000001", "T000002"))
    assert client.calls == []


@pytest.mark.parametrize("size,error", [(501, "invalid_field"), (4096, "command_too_large")])
async def test_oversized_last_item_or_message_does_not_persist_plan(
    engine, store, now, size, error
):
    before = engine.snapshot()
    with pytest.raises(DomainError, match=error):
        await route(engine, "parent", "2 tasks for Child:\n1. Work\n2. " + "X" * size, "large", now)
    assert engine.snapshot() == before and store.calls == 0


async def test_failure_to_save_plan_never_starts_task_transaction(engine, store, now):
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await route(engine, "parent", "2 tasks for Child:\n1. Work\n2. More", "no-plan", now)
    assert engine.snapshot() == before and store.value is None


async def test_shared_deadline_uses_received_local_calendar_day(engine, now):
    await engine.system_update(
        "zone",
        now,
        lambda ctx: ctx.state["settings"].update(timezone="Europe/Kyiv"),
    )
    content = "2 tasks for Child tomorrow at 18:00:\n1. Work\n2. More"
    await route(engine, "parent", content, "local", now.replace(hour=22))
    assert all(
        task["due_at"] == "2026-09-08T18:00:00+03:00"
        for task in engine.snapshot()["tasks"].values()
    )


async def test_batch_claim_does_not_change_literal_slash_or_single_assignment(engine, now):
    title = "Work with a numbered checklist:\n1. Step one\n2. Step two"
    await route(engine, "parent", "/task Child | " + title, "slash", now)
    assert engine.snapshot()["tasks"]["T000001"]["title"] == title
    for index, message in enumerate(
        ("Child task Read", "assign Child task Read", "признач Child завдання Читати")
    ):
        await route(engine, "parent", message, f"single-{index}", now)
    assert len(engine.snapshot()["tasks"]) == 4


async def test_problem_book_shopping_is_not_a_task_batch(engine, now):
    message = "добавь 2 задачника в покупки"
    assert parsed(engine.snapshot(), engine.view("parent"), message, now) is None
    await route(engine, "parent", message, "books", now)
    item = engine.snapshot()["shopping"]["S000001"]
    assert item["name"] == "задачника" and item["quantity"] == 2
    assert not engine.snapshot()["tasks"]


async def test_negative_chore_title_and_indented_list_keep_literal_meaning(engine, now):
    message = (
        "  2 задачи для Child:\n\n  1. Не забыть купить хлеб\n\n  2. Не выбрасывать упаковку\n"
    )
    await route(engine, "parent", message, "negative-titles", now)
    assert [task["title"] for task in engine.snapshot()["tasks"].values()] == [
        "Не забыть купить хлеб",
        "Не выбрасывать упаковку",
    ]
