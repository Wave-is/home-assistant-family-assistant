"""Bounded legacy day/week deadlines; no guessed task, old due date or LLM calendar."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.deadlines import extract_due, parse_due
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.router import route


@pytest.mark.parametrize(
    "expression,days",
    [
        ("на неделю", 7),
        ("на одну неделю", 7),
        ("на 2 недели", 14),
        ("срок выполнения три дня", 3),
        ("срок на выполнение 4 дня", 4),
        ("на выполнение две недели", 14),
        ("в течение одного дня", None),
        ("в течение дня", 1),
        ("через четыре дня", 4),
        ("термін виконання два дні", 2),
        ("протягом двох днів", None),
        ("через три тижні", 21),
        ("на тиждень", 7),
        ("in a week", 7),
        ("within four days", 4),
        ("for two weeks", 14),
        ("365 days", 365),
        ("52 weeks", 364),
        ("53 weeks", None),
        ("0 дней", None),
        ("-1 день", None),
        ("1.5 дня", None),
        ("1000 дней", None),
        ("две недели завтра", None),
        ("in two days and cancel everything", None),
    ],
)
def test_bounded_relative_date_slot(expression, days, now):
    if days is None:
        with pytest.raises(DomainError, match="invalid_deadline"):
            parse_due(expression, now, "Europe/Kyiv")
    else:
        day = (now + timedelta(days=days)).date().isoformat()
        expected = parse_due(day, now, "Europe/Kyiv")
        assert parse_due(expression, now, "Europe/Kyiv") == expected


@pytest.mark.parametrize(
    "marker",
    [
        "срок неделя",
        "срок выполнения неделя",
        "срок на выполнение неделя",
        "на выполнение неделя",
        "в течение недели",
        "через неделю",
        "термін виконання тиждень",
        "протягом тижня",
        "in a week",
        "within one week",
    ],
)
def test_creation_keeps_deadline_marker_out_of_title(marker, now):
    title, due = extract_due(f"Prepare materials, {marker}", now, "Europe/Kyiv")
    assert title == "Prepare materials"
    assert due == "2026-09-13T20:00:00+03:00"


def test_relative_date_local_midnight_clock_and_dst():
    now = datetime(2026, 9, 6, 22, 30, tzinfo=UTC)
    assert parse_due("через день в 17:30", now, "Europe/Kyiv") == "2026-09-08T17:30:00+03:00"
    for instant in (datetime(2026, 3, 28, tzinfo=UTC), datetime(2026, 10, 24, tzinfo=UTC)):
        with pytest.raises(DomainError, match="invalid_deadline"):
            parse_due("через день в 03:30", instant, "Europe/Kyiv")
    assert extract_due("Купить корм на неделю", now, "Europe/Kyiv") == (
        "Купить корм на неделю",
        None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "продли T000001 на неделю",
        "продлите задачу T000001 на 1 неделю",
        "продовжи завдання T000001 на тиждень",
        "подовжіть T000001 на тиждень",
        "extend task T000001 for one week",
        "/edit T000001 deadline in a week",
    ],
)
async def test_relative_task_edit_is_received_day_based_and_replayed(engine, now, command):
    await route(engine, "parent", "Child задача Work, срок завтра", "create", now)
    result = await route(engine, "parent", command, "extend", now)
    task = engine.snapshot()["tasks"]["T000001"]
    assert task["due_at"] == "2026-09-13T20:00:00+00:00"  # Household fixture uses UTC.
    assert task["title"] == "Work" and task["revision"] == 2
    assert await route(engine, "parent", command, "extend", now + timedelta(days=2)) == result
    assert engine.snapshot()["tasks"]["T000001"]["revision"] == 2


@pytest.mark.asyncio
async def test_relative_reply_is_not_authority_and_needs_unique_target(engine, now):
    await route(engine, "parent", "/task Sibling | Work", "create", now)
    for refs in ((), ("T000001", "T000002")):
        with pytest.raises(DomainError, match="context_required"):
            await route(engine, "parent", "продли на неделю", "bad", now, refs)
    with pytest.raises(DomainError, match="not_found"):
        await route(engine, "child", "продли на неделю", "bad", now, ("T000001",))
    await route(engine, "parent", "продли на неделю", "good", now, ("T000001",))
    assert engine.snapshot()["tasks"]["T000001"]["due_at"] == "2026-09-13T20:00:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "не продли T000001 на неделю",
        "do not extend T000001 for a week",
        "продли T000001 на неделю и удали остальные",
        "продли T000001 на 366 дней",
        "/продлить T000001 на неделю",
    ],
)
async def test_negation_unsupported_slash_and_trailing_actions_never_mutate(engine, now, command):
    await route(engine, "parent", "/task Child | Work", "create", now)
    before = engine.snapshot()["tasks"]
    try:
        await route(engine, "parent", command, "unsupported", now)
    except DomainError:
        pass
    assert engine.snapshot()["tasks"] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["task Child", "remind me to"])
@pytest.mark.parametrize(
    "slot",
    [
        "not within a week",
        "срок не через неделю",
        "deadline in 1000 days at 17:30",
        "in 1.5 days at 17:30",
        "in 1,5 days at 17:30",
        "in -2 days at 17:30",
        "in twenty one days at 17:30",
        "in 1/2 days at 17:30",
        "in - 2 days at 17:30",
        "in one hundred and one days at 17:30",
        "через 999 дней в 17:30",
        "deadline tomorrow and cancel everything",
        "not tomorrow",
        "не через неделю",
        "deadline tomorrow, within a week",
    ],
)
async def test_invalid_or_negated_duration_cannot_fall_back_to_later_clock(
    engine, now, prefix, slot
):
    before = engine.snapshot()["tasks"]
    with pytest.raises(DomainError, match="invalid_deadline"):
        await route(engine, "parent", f"{prefix} Work, {slot}", "bad-slot", now)
    assert engine.snapshot()["tasks"] == before


@pytest.mark.parametrize(
    "title", ["Work in a shop", "Пройти через дорогу", "Купить корм на неделю"]
)
def test_non_deadline_prepositions_remain_title(title, now):
    assert extract_due(title, now, "Europe/Kyiv") == (title, None)


@pytest.mark.parametrize("separator", [", ", ". ", ": ", "; "])
@pytest.mark.parametrize("due", ["deadline in a week", "within a week", "deadline tomorrow"])
def test_ordinary_title_preposition_does_not_steal_a_later_deadline(now, separator, due):
    title, resolved = extract_due(f"Work in a shop{separator}{due}", now, "Europe/Kyiv")
    assert title == "Work in a shop"
    assert resolved == parse_due(due.removeprefix("deadline "), now, "Europe/Kyiv")
