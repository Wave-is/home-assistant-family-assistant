"""No repeated penalties, false missed reports, or unpaired family alerts."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.telegram.messages import MESSAGES, render


async def setup_task(engine, now, **extra):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": "en",
            "modules": settings["modules"],
            "automatic_penalties": True,
            "daily_penalty_cap": 1,
        },
        "auto-opt-in",
        now,
    )
    return await engine.execute(
        "parent",
        "tasks.create",
        {
            "title": "Synthetic chore",
            "assignee": "child",
            "due_at": (now + timedelta(hours=1)).isoformat(),
            "penalty": -1,
            **extra,
        },
        "new-chore",
        now,
    )


def events(engine, key):
    return [e for e in engine.snapshot()["outbox"].values() if e["key"] == key]


@pytest.mark.asyncio
async def test_reminder_escalation_and_penalty_once_even_after_restart(engine, store, now):
    task = await setup_task(engine, now)
    await engine.tick(now)
    await engine.tick(now + timedelta(seconds=10))
    assert len(events(engine, "task_reminder")) == 1
    await engine.tick(now + timedelta(minutes=89))
    assert not events(engine, "task_overdue")
    await engine.tick(now + timedelta(minutes=90))
    restarted = Engine(engine.snapshot(), store.save)
    await restarted.tick(now + timedelta(days=1))
    assert len(events(restarted, "task_overdue")) == 1
    scores = restarted.snapshot()["court"]
    assert len(scores) == 1 and scores[f"task:{task['id']}"]["points"] == -1


@pytest.mark.asyncio
async def test_parent_review_delay_does_not_punish_child(engine, now):
    task = await setup_task(engine, now)
    await engine.execute(
        "child", "tasks.submit", {"id": task["id"], "report": "Finished"}, "report", now
    )
    await engine.tick(now + timedelta(days=1))
    assert not engine.snapshot()["court"] and not events(engine, "task_overdue")


@pytest.mark.asyncio
async def test_completed_task_does_not_deliver_stale_reminder(engine, now):
    task = await setup_task(engine, now)
    await engine.tick(now)
    await engine.execute("parent", "tasks.complete", {"id": task["id"]}, "done", now)
    assert events(engine, "task_reminder")[0]["state"] == "superseded"
    assert events(engine, "task_assigned")[0]["state"] == "superseded"


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery_state", ["sent", "sending", "uncertain", "pending"])
async def test_close_pairs_announced_problem_but_cancels_unsent_alert(engine, now, delivery_state):
    task = await setup_task(engine, now)
    await engine.tick(now + timedelta(hours=2))
    alert = events(engine, "task_overdue")[0]

    def delivery(ctx):
        event = ctx.state["outbox"][alert["id"]]
        event["state"] = delivery_state
        event["deliveries"] = {"synthetic": {"state": delivery_state}}

    await engine.system_update("synthetic_delivery", now, delivery)
    await engine.execute(
        "parent", "tasks.complete", {"id": task["id"]}, "complete", now + timedelta(hours=2)
    )
    assert len(events(engine, "task_incident_closed")) == (0 if delivery_state == "pending" else 1)
    if delivery_state == "pending":
        assert events(engine, "task_overdue")[0]["state"] == "superseded"
    await engine.tick(now + timedelta(days=1))
    assert len(engine.snapshot()["court"]) == 1  # Completion does not hide or erase the ledger.


@pytest.mark.asyncio
async def test_reschedule_does_not_repeat_same_task_penalty(engine, now):
    task = await setup_task(engine, now)
    await engine.tick(now + timedelta(hours=2))
    await engine.execute(
        "parent",
        "tasks.revise",
        {"id": task["id"], "due_at": (now + timedelta(days=1)).isoformat()},
        "later",
        now + timedelta(hours=2),
    )
    await engine.tick(now + timedelta(days=2))
    assert len(engine.snapshot()["court"]) == 1


@pytest.mark.asyncio
async def test_failed_persistence_applies_no_penalty_or_alert(engine, store, now):
    await setup_task(engine, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(now + timedelta(hours=2))
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_past_import_and_default_opt_out_have_no_automatic_penalty(engine, now):
    await engine.execute(
        "parent",
        "tasks.create",
        {
            "title": "Past record",
            "assignee": "child",
            "due_at": (now - timedelta(days=1)).isoformat(),
            "penalty": -1,
        },
        "past",
        now,
    )
    await engine.tick(now)
    assert not engine.snapshot()["court"] and not events(engine, "task_overdue")


def test_all_task_notifications_render_in_three_languages(engine):
    for language in MESSAGES:
        assert MESSAGES[language].keys() == MESSAGES["en"].keys()
        for key in ("task_reminder", "task_overdue", "task_incident_closed"):
            message = render(
                {
                    "key": key,
                    "data": {"id": "T000001", "member": "child", "due_at": "2026-09-06T20:00:00Z"},
                },
                {"id": 1001, "language": language},
                engine.snapshot(),
            )
            assert "T000001" in message["text"]
