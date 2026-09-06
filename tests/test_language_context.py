"""Regression cases from ordinary family conversation, with synthetic members only."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.deadlines import extract_due, parse_due
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.context import reply_refs
from custom_components.family_assistant.telegram.presentation import WORDS, summary
from custom_components.family_assistant.telegram.router import route


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("до конца недели", "2026-09-06T20:00:00+03:00"),
        ("до конца следующей недели", "2026-09-13T20:00:00+03:00"),
        ("до кінця тижня", "2026-09-06T20:00:00+03:00"),
        ("end of next week", "2026-09-13T20:00:00+03:00"),
        ("завтра на 5 часов вечера", "2026-09-07T17:00:00+03:00"),
        ("today at 5pm", "2026-09-06T17:00:00+03:00"),
        ("31.12.2026 в 17:00", "2026-12-31T17:00:00+02:00"),
        ("31.02.2026", None),
        ("today at 29:10", None),
    ],
)
def test_calendar_is_computed_not_guessed(expression, expected, now):
    if expected:
        assert parse_due(expression, now, "Europe/Kyiv") == expected
    else:
        with pytest.raises(DomainError, match="invalid_deadline"):
            parse_due(expression, now, "Europe/Kyiv")


def test_thursday_end_of_week_is_sunday_not_monday():
    now = datetime(2026, 9, 3, 10, tzinfo=UTC)
    title, due = extract_due("Зачистить каждую грань, срок до конца неде", now, "Europe/Kyiv")
    assert title == "Зачистить каждую грань"
    assert due == "2026-09-06T20:00:00+03:00"


def test_dst_gap_fold_and_past_not_silently_rescheduled(now):
    for value in ("2026-03-29 at 03:30", "2026-10-25 at 03:30", "2026-09-05"):
        with pytest.raises(DomainError, match="invalid_deadline"):
            parse_due(
                value, datetime(2026, 1, 1, tzinfo=UTC) if "03:30" in value else now, "Europe/Kyiv"
            )


@pytest.mark.asyncio
async def test_assignment_with_move_verb_does_not_become_reschedule(engine, now):
    await route(engine, "parent", "Child задача. перенести детали в беседку", "create", now)
    task = engine.snapshot()["tasks"]["T000001"]
    assert task["title"] == "перенести детали в беседку"
    assert task["assignee"] == "child"
    assert task["due_at"] is None


@pytest.mark.asyncio
async def test_reply_sets_deadline_and_replay_keeps_original_plan(engine, now):
    await route(
        engine, "parent", "Child задача зачистить грань, срок до конца недели", "create", now
    )
    command = "установи срок до конца следующей недели"
    result = await route(engine, "parent", command, "revise", now, ("T000001",))
    assert "2026-09-13" in result
    # Recomputing against tomorrow or a newer revision must not change the stored operation.
    replay = await route(engine, "parent", command, "revise", now + timedelta(days=1), ("T000001",))
    assert replay == result
    assert engine.snapshot()["tasks"]["T000001"]["revision"] == 2
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await route(engine, "parent", "установи срок завтра", "revise", now, ("T000001",))


@pytest.mark.asyncio
async def test_context_is_never_an_authorization_and_ambiguity_stops(engine, now):
    await route(engine, "parent", "/task Sibling | A task", "create", now)
    with pytest.raises(DomainError, match="not_found"):
        await route(engine, "child", "установи срок завтра", "bad", now, ("T000001",))
    for refs in ((), ("T000001", "T000002")):
        with pytest.raises(DomainError, match="context_required"):
            await route(engine, "parent", "установи срок завтра", "ambiguous", now, refs)
    for content in (
        "не устанавливай срок завтра",
        "не Child задача сделать что-то",
        "set deadline tomorrow and cancel everything",
    ):
        try:
            await route(engine, "parent", content, content, now)
        except DomainError:
            pass
    assert len(engine.snapshot()["tasks"]) == 1


def test_reply_must_match_delivered_receipt_in_same_chat(engine):
    state = engine.snapshot()
    state["outbox"]["synthetic"] = {
        "data": {"refs": ["T000001"]},
        "deliveries": {
            "delivery": {
                "receipt": "77",
                "target": {"channel": "telegram", "id": 1001, "bot_id": 1234},
            }
        },
    }
    msg = {
        "chat": {"id": 1001},
        "reply_to_message": {"from": {"id": 1234}, "message_id": 77, "text": "T999999 forged"},
    }
    assert reply_refs(state, msg, {"id": 1234}) == ("T000001",)
    msg["chat"]["id"] = 1002
    assert reply_refs(state, msg, {"id": 1234}) == ()


@pytest.mark.asyncio
async def test_templates_are_generic_unlinked_and_do_not_reappear_after_reload(store, now):
    for language in ("en", "ru", "uk"):
        for template, count in (
            ("manual", 1),
            ("pair", 2),
            ("parents_children", 3),
            ("single_parent", 2),
        ):
            state = new_state(
                "synthetic", "Family", language, timezone="Europe/Kyiv", template=template
            )
            assert len(state["members"]) == count
            assert sum(bool(m.get("ha_user_id")) for m in state["members"].values()) == 1
            e = Engine(state, store.save)
            await e.execute(
                "owner",
                "members.save",
                {"name": "New person", "role": "child", "language": language, "active": True},
                "member",
                now,
            )
            assert len(e.snapshot()["members"]) == count + 1
            assert Engine(e.snapshot(), store.save).snapshot() == e.snapshot()


def test_bot_record_summaries_are_localized(engine):
    for language in WORDS:
        assert WORDS[language].keys() == WORDS["en"].keys()
    record = {"member": "child", "points": -1, "reason_key": "alarm_missed", "status": "active"}
    ru = summary(record, engine.view("parent"), "ru")
    assert "Подъём не подтверждён за 30 минут" in ru
    assert "alarm_missed" not in ru and "active" not in ru
