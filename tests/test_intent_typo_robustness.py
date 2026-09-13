"""Explicit assignment grammar resolves configured identities, never fuzzy guesses."""

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram import intents
from custom_components.family_assistant.telegram.router import route


async def names(engine, now):
    def update(ctx):
        ctx.state["members"]["child"].update(name="Артём", aliases=["Тёма"])
        ctx.state["members"]["sibling"].update(name="Child One", aliases=["Study Helper"])

    await engine.system_update("synthetic-names", now, update)


@pytest.mark.parametrize(
    "phrase,member,title",
    [
        ("поставь задачу Артёму - купить хлеб", "child", "купить хлеб"),
        ("ПОСТАВЬТЕ ЗАДАЧУ АРТЕМУ — купить хлеб", "child", "купить хлеб"),
        ("поставить задачу Тёме – купить хлеб", "child", "купить хлеб"),
        ("поставь Артему задачу - купить хлеб", "child", "купить хлеб"),
        ("поставь задачу для Артёма: купить хлеб", "child", "купить хлеб"),
        ("поставь задачу Артёму:купить хлеб", "child", "купить хлеб"),
        ("назначь задачу Артёму — купить хлеб", "child", "купить хлеб"),
        ("поставь задачу Артёму—купить хлеб", "child", "купить хлеб"),
        ("поставь\tзадачу\tАртёму\t-\tкупить хлеб", "child", "купить хлеб"),
        ("поставь задачу Артёму купить хлеб", "child", "купить хлеб"),
        ("create task Child One - Read the e-book", "sibling", "Read the e-book"),
        ("assign task Child One - Read the e-book", "sibling", "Read the e-book"),
        ("створи завдання Study Helper — купити хліб", "sibling", "купити хліб"),
        ("постав завдання Study Helper — купити хліб", "sibling", "купити хліб"),
        ("поставте завдання Study Helper — купити хліб", "sibling", "купити хліб"),
        ("assign Child One task - Read the e-book", "sibling", "Read the e-book"),
        ("Child One task — Read the e-book", "sibling", "Read the e-book"),
        ("create task Child One Read the e-book", "sibling", "Read the e-book"),
    ],
)
async def test_explicit_assignment_preserves_configured_target_and_title(
    engine, now, phrase, member, title
):
    await names(engine, now)

    async def no_model(*_args):
        pytest.fail("A recognized configured recipient must not need a model")

    first = await route(engine, "parent", phrase, "assignment", now, fallback=no_model)
    assert await route(engine, "parent", phrase, "assignment", now, fallback=no_model) == first
    tasks = list(engine.snapshot()["tasks"].values())
    assert len(tasks) == 1
    assert tasks[0]["assignee"] == member
    assert tasks[0]["title"] == title


@pytest.mark.parametrize(
    "phrase",
    [
        "поставь задачу Аптему - купить хлеб",
        "create task Child Unknown - Read chapter",
        "create task Child Unknown: Read chapter",
        "create task Child Unknown:Read chapter",
    ],
)
async def test_unknown_full_recipient_is_not_reduced_to_known_first_token(engine, now, phrase):
    await names(engine, now)
    with pytest.raises(DomainError, match="unknown_member"):
        intents.parse(engine.snapshot(), engine.view("parent"), phrase, now)
    assert not engine.snapshot()["tasks"]


async def test_equal_configured_aliases_are_ambiguous_and_inactive_names_do_not_bind(engine, now):
    await names(engine, now)
    state = engine.snapshot()
    state["members"]["sibling"]["aliases"] = ["Артему"]
    # Explicit exact alias already wins over morphology in find_member; do not change that policy.
    state["members"]["child"]["aliases"] = ["Артему"]
    with pytest.raises(DomainError, match="ambiguous_member"):
        intents.parse(state, engine.view("parent"), "поставь задачу Артему - купить хлеб", now)
    state["members"]["child"]["active"] = False
    state["members"]["sibling"]["aliases"] = []
    with pytest.raises(DomainError, match="unknown_member"):
        intents.parse(state, engine.view("parent"), "поставь задачу Артему - купить хлеб", now)


@pytest.mark.parametrize("separator", ["-", "—", "–", ":"])
async def test_empty_assignment_title_never_creates_a_separator_task(engine, now, separator):
    await names(engine, now)
    with pytest.raises(DomainError):
        intents.parse(
            engine.snapshot(), engine.view("parent"), f"поставь задачу Артему {separator}", now
        )


async def test_hyphenated_configured_alias_is_not_split_and_due_stays_in_title_slot(engine, now):
    await engine.system_update(
        "name", now, lambda ctx: ctx.state["members"]["child"].update(aliases=["Study-Helper"])
    )
    result = intents.parse(
        engine.snapshot(),
        engine.view("parent"),
        "create task Study-Helper - Read the e-book tomorrow at 18:00",
        now,
    )
    assert result.payload == {
        "assignee": "child",
        "title": "Read the e-book",
        "due_at": "2026-09-07T18:00:00+00:00",
    }


@pytest.mark.parametrize("actor", ["child", "guest"])
async def test_new_spelling_does_not_bypass_engine_authority(engine, now, actor):
    await names(engine, now)
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, actor, "поставь задачу Child One - Read chapter", "denied", now)
    assert not engine.snapshot()["tasks"]


@pytest.mark.parametrize(
    "content,recipient",
    [
        ("  поставь задачу Аптему - купить хлеб  ", "Аптему"),
        ("поставьте задачу для Child Unknown — read chapter", "Child Unknown"),
        ("назначь Child Unknown задачу - Read chapter", "Child Unknown"),
        ("Child Unknown task Read chapter", "Child Unknown"),
        ("створи завдання Study Helper: купити хліб", "Study Helper"),
        ("поставь задачу Артему—купить хлеб", "Артему"),
        ("assign task Alxe - Buy bread", "Alxe"),
        ("assign task Alxe:Buy bread", "Alxe"),
        ("постав завдання Ропану — Buy bread", "Ропану"),
    ],
)
def test_recipient_helper_returns_only_original_full_slot(content, recipient):
    start, end = intents.assignment_recipient(content)
    assert content[start:end] == recipient
    replaced = content[:start] + "Synthetic Replacement" + content[end:]
    assert replaced.replace("Synthetic Replacement", recipient) == content


@pytest.mark.parametrize(
    "content",
    [
        "How was your day?",
        "create task Child Unknown read chapter",
        "поставь задачу Аптему купить хлеб",
        "не поставь задачу Артему - купить хлеб",
        "поставь задачу Артему -",
        "task Child in - 2 days at 17:30",
        "/task Child | Read chapter",
    ],
)
def test_recipient_helper_declines_ambiguous_or_nonassignment_text(content):
    assert intents.assignment_recipient(content) is None
