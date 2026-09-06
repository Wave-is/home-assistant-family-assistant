"""Remembered corrections stay local, exact, actor-bound and freshly authorized."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.router import route


async def enable(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "enable-learning",
        now,
    )


@pytest.mark.asyncio
async def test_explicit_phrase_read_is_personal_and_does_not_override_builtin(engine, now):
    await enable(engine, now)
    await engine.execute(
        "parent",
        "court.award",
        {"member": "child", "points": -1, "reason": "Synthetic reason"},
        "points",
        now,
    )
    learned = await route(engine, "parent", "/learn почему такой счёт | /stats", "learn1", now)
    assert "L000001" in learned
    assert "Synthetic reason" in await route(engine, "parent", "Почему такой счёт?", "use1", now)
    assert "haven't understood" in await route(engine, "child", "почему такой счёт", "child1", now)
    assert engine.view("child")["learned_phrases"] == []
    with pytest.raises(DomainError, match="learning_template_required"):
        await route(engine, "parent", "/learn за что минусы | /tasks", "shadow", now)
    with pytest.raises(DomainError, match="invalid_field"):
        await route(engine, "parent", "/learn /ping | /stats", "shadow-ping", now)


@pytest.mark.asyncio
async def test_reusable_assignment_recalculates_date_and_rechecks_role(engine, store, now):
    await enable(engine, now)
    await route(
        engine,
        "parent",
        "/learn растения | Child task Water plants, deadline tomorrow",
        "learn2",
        now,
    )
    assert not engine.snapshot()["tasks"]  # Learning validates but does not execute.
    restarted = Engine(engine.snapshot(), store.save)
    await route(restarted, "parent", "растения", "plants1", now)
    await route(restarted, "parent", "растения", "plants2", now + timedelta(days=1))
    tasks = list(restarted.snapshot()["tasks"].values())
    assert tasks[0]["due_at"][:10] == "2026-09-07"
    assert tasks[1]["due_at"][:10] == "2026-09-08"
    assert len(tasks) == 2
    await route(restarted, "parent", "растения", "plants2", now + timedelta(days=1))
    assert len(restarted.snapshot()["tasks"]) == 2
    await restarted.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": restarted.snapshot()["members"]["parent"]["revision"],
            "name": "Parent",
            "role": "child",
            "language": "en",
        },
        "revoke",
        now,
    )
    with pytest.raises(DomainError, match="forbidden"):
        await route(restarted, "parent", "растения", "plants3", now)


@pytest.mark.asyncio
async def test_reply_template_uses_current_receipt_and_negation_never_matches(engine, now):
    await enable(engine, now)
    await route(engine, "parent", "/learn на денёк позже | установи срок завтра", "learn3", now)
    task = await engine.execute(
        "parent", "tasks.create", {"title": "Synthetic", "assignee": "child"}, "create3", now
    )
    assert "haven't understood" in await route(
        engine, "parent", "не на денёк позже", "negative3", now
    )
    with pytest.raises(DomainError, match="context_required"):
        await route(engine, "parent", "на денёк позже", "missing3", now)
    await route(engine, "parent", "на денёк позже", "use3", now, (task["id"],))
    assert engine.snapshot()["tasks"][task["id"]]["due_at"][:10] == "2026-09-07"


@pytest.mark.asyncio
async def test_no_fixed_record_target_unauthorized_teaching_or_cross_actor_forget(engine, now):
    await enable(engine, now)
    for canonical in (
        "set deadline for T000001 tomorrow",
        "Child task Work, deadline 2026-10-01",
        "Run a shell command",
    ):
        with pytest.raises(DomainError, match="learning_template_required"):
            await route(
                engine, "parent", "/learn phrase | " + canonical, "invalid-" + canonical, now
            )
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/learn duty | Parent task Work", "unauthorized4", now)
    await route(engine, "parent", "/learn my situation | /tasks", "learn4", now)
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/forget L000001", "forget-other4", now)
    await route(engine, "parent", "/forget L000001", "forget4", now)
    assert engine.view("parent")["learned_phrases"][0]["active"] is False
    assert "haven't understood" in await route(engine, "parent", "my situation", "after4", now)
