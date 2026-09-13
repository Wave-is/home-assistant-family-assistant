"""Dated opt-in settlement through actual Engine transactions; fictional chores."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import task_settlements as settlements
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.task_delivery import current_task_event
from custom_components.family_assistant.domain.validation import DomainError


def policy(**changes):
    return {**settlements.DEFAULTS, "daily_rollover": True, **changes}


async def setup(engine, now, **settings):
    state = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            "name": state["name"],
            "language": "en",
            "modules": state["modules"],
            "automatic_penalties": True,
            "daily_penalty_cap": 10,
            **settings,
        },
        "opt-in",
        now,
    )


async def create(engine, now, *, missed=None, actor="parent", **changes):
    return await engine.execute(
        actor,
        "tasks.create",
        {
            "title": "Synthetic daily chore",
            "assignee": "child",
            "due_at": now.replace(hour=19).isoformat(),
            "penalty": -1,
            "missed_policy": policy(**(missed or {})),
            "missed_actor_revision": engine.snapshot()["members"][actor]["revision"],
            **changes,
        },
        "new-chore",
        now,
    )


def current(engine, task):
    return engine.snapshot()["tasks"][task["id"]]


async def action(engine, task, now, action="complete", actor="parent", operation=None, **payload):
    return await engine.execute(
        actor,
        "tasks." + action,
        {"id": task["id"], "revision": current(engine, task)["revision"], **payload},
        operation or action,
        now,
    )


def notices(engine):
    return [
        event for event in engine.snapshot()["outbox"].values() if event["key"] == "task_rollover"
    ]


async def test_cutoff_atomic_receipt_rollover_score_and_restart(engine, now, store):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True})
    assert "missed_scope" not in task and "missed_generation" not in task
    await engine.tick(now.replace(hour=19, minute=59))
    assert not engine.snapshot()["court"]
    await engine.tick(now.replace(hour=20))
    row = current(engine, task)
    receipt = row["missed_receipt"]
    assert row["due_at"] == (now + timedelta(days=1)).replace(hour=19).isoformat()
    assert row["missed_original_due_at"] == task["due_at"]
    assert row["status"] == "assigned" and row["report"] is None
    assert receipt["outcome"] == "applied" and receipt["points"] == -1
    assert receipt["ledger_id"] == f"task:{task['id']}:missed:2026-09-06"
    assert current_task_event(engine.snapshot(), notices(engine)[0])
    restored = Engine(store.value, store.save)
    await restored.tick(now.replace(hour=21))
    assert len(notices(restored)) == 1 and len(restored.snapshot()["court"]) == 1
    await restored.tick((now + timedelta(days=1)).replace(hour=20))
    assert len(restored.snapshot()["court"]) == 2
    assert current(restored, task)["missed_receipt"]["due_local_date"] == "2026-09-07"
    assert not current_task_event(restored.snapshot(), notices(restored)[0])


@pytest.mark.parametrize(
    "extra,outcome", [({}, "skipped_duplicate"), ({"repeat_penalty": True}, "applied")]
)
async def test_repeat_penalty_requires_separate_consent(engine, now, extra, outcome):
    await setup(engine, now)
    task = await create(engine, now, missed=extra)
    for days in (0, 1):
        await engine.tick((now + timedelta(days=days)).replace(hour=20))
    assert current(engine, task)["missed_receipt"]["outcome"] == outcome
    assert len(engine.snapshot()["court"]) == (2 if extra else 1)


@pytest.mark.parametrize(
    "change,outcome",
    [
        ({"automatic_penalties": False}, "skipped_disabled"),
        ({"daily_penalty_cap": 0}, "skipped_cap"),
        ({"modules": ["tasks"]}, "skipped_disabled"),
    ],
)
async def test_skipped_scores_are_terminal_not_backfilled(engine, now, change, outcome):
    await setup(engine, now, **change)
    task = await create(engine, now)
    await engine.tick(now.replace(hour=20))
    assert current(engine, task)["missed_receipt"]["outcome"] == outcome
    assert not engine.snapshot()["court"]
    await engine.tick(now.replace(hour=22))
    assert not engine.snapshot()["court"] and len(notices(engine)) == 1


async def test_outage_skips_old_days_in_one_bounded_transition(engine, now, store):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True})
    late = (now + timedelta(days=40)).replace(hour=22)
    await engine.tick(late)
    row = current(engine, task)
    assert row["missed_receipt"]["outcome"] == "skipped_outage"
    assert row["due_at"] == (late + timedelta(days=1)).replace(hour=19).isoformat()
    restored = Engine(store.value, store.save)
    for seconds in range(4):
        await restored.tick(late + timedelta(seconds=seconds))
    assert not restored.snapshot()["court"] and len(notices(restored)) == 1


async def test_same_day_parent_completion_reverses_only_original_score_atomically(
    engine, now, store
):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True, "same_day_correction": True})
    await engine.tick(now.replace(hour=20))
    receipt = deepcopy(current(engine, task)["missed_receipt"])
    other = await engine.execute(
        "parent",
        "court.award",
        {"member": "child", "points": -2, "reason": "Unrelated synthetic score"},
        "manual",
        now,
    )
    result = await action(engine, task, now.replace(hour=21))
    assert result["status"] == "completed" and result["correction_status"] == "reversed"
    assert current(engine, task)["missed_receipt"] == receipt
    assert engine.snapshot()["court"][receipt["ledger_id"]]["status"] == "reversed"
    assert engine.snapshot()["court"][other["id"]]["status"] == "active"
    assert not current_task_event(engine.snapshot(), notices(engine)[0])
    restored = Engine(store.value, store.save)
    assert (
        await restored.execute(
            "parent",
            "tasks.complete",
            {"id": task["id"], "revision": result["revision"] - 1},
            "complete",
            now + timedelta(days=1),
        )
        == result
    )


@pytest.mark.parametrize("completion", ["next_day", "cancel", "archive", "submitted"])
async def test_non_correction_transitions_keep_original_score(engine, now, completion):
    await setup(engine, now)
    task = await create(engine, now, missed={"same_day_correction": True})
    await engine.tick(now.replace(hour=20))
    if completion == "next_day":
        await action(engine, task, now + timedelta(days=1))
    elif completion == "submitted":
        await action(engine, task, now.replace(hour=21), "submit", actor="child", report="Finished")
    else:
        await action(engine, task, now.replace(hour=21), completion)
    assert next(iter(engine.snapshot()["court"].values()))["status"] == "active"


async def test_submitted_work_is_never_rolled_or_penalized(engine, now):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True})
    await action(engine, task, now, "submit", actor="child", report="Done")
    before = current(engine, task)
    await engine.tick(now + timedelta(days=50))
    assert current(engine, task) == before
    assert not engine.snapshot()["court"] and not notices(engine)


@pytest.mark.parametrize("when", ["tick", "completion"])
async def test_store_failure_commits_no_partial_score_date_or_correction(engine, now, store, when):
    await setup(engine, now)
    task = await create(engine, now, missed={"same_day_correction": True})
    if when == "completion":
        await engine.tick(now.replace(hour=20))
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        if when == "tick":
            await engine.tick(now.replace(hour=20))
        else:
            await action(engine, task, now.replace(hour=21))
    assert engine.snapshot() == before


@pytest.mark.parametrize("changed", ["child", "actor", "role", "timezone", "source", "series"])
async def test_revoked_identity_or_source_cannot_settle(engine, now, store, changed):
    await setup(engine, now)
    task = await create(engine, now)
    state = engine.snapshot()
    if changed in {"child", "actor"}:
        state["members"]["child" if changed == "child" else "parent"]["revision"] += 1
    elif changed == "role":
        state["members"]["child"]["role"] = "adult"
    elif changed == "timezone":
        state["settings"]["timezone"] = "Europe/Kyiv"
    else:
        state["tasks"][task["id"]]["source" if changed == "source" else "series_id"] = (
            {"kind": "school_homework"} if changed == "source" else "TS000001"
        )
    restored = Engine(state, store.save)
    await restored.tick(now.replace(hour=20))
    assert not restored.snapshot()["court"] and not notices(restored)
    assert current(restored, task)["missed_scope"]["state"] == "revoked"


@pytest.mark.parametrize(
    "changes",
    [
        {"assignee": "parent"},
        {"due_at": None},
        {"missed_actor_revision": 2},
        {"missed_actor_revision": True},
        {"missed_policy": policy(repeat_penalty=1)},
        {"missed_policy": policy(settle_time="25:00")},
        {"missed_policy": policy(daily_rollover=False, repeat_penalty=True)},
    ],
)
async def test_invalid_or_stale_configuration_is_atomic(engine, now, changes):
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await create(engine, now, **changes)
    assert engine.snapshot() == before


@pytest.mark.parametrize("actor", ["child", "adult", "guest"])
async def test_only_parent_can_enable_policy(engine, now, actor):
    with pytest.raises(DomainError):
        await create(engine, now, actor=actor, penalty=0)


async def test_independent_appeal_requires_review_without_blocking_completion(engine, now):
    await setup(engine, now)
    await engine.execute(
        "owner", "court.configure", {"revision": 0, "second_adult_review": True}, "independent", now
    )
    task = await create(engine, now, missed={"same_day_correction": True})
    await engine.tick(now.replace(hour=20))
    receipt = current(engine, task)["missed_receipt"]
    await engine.execute(
        "parent",
        "court.appeal",
        {"id": receipt["ledger_id"], "revision": 1, "reason": "Please review"},
        "appeal",
        now.replace(hour=20),
    )
    result = await action(engine, task, now.replace(hour=21))
    assert result["status"] == "completed" and result["correction_status"] == "needs_review"
    payload = settlements.correction_payload(
        engine.snapshot(), current(engine, task), engine.snapshot()["members"]["parent"]
    )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "parent",
            "tasks.correct_miss",
            {**payload, "reason": "Verified same-day completion"},
            "self-review",
            now.replace(hour=21),
        )
    payload["actor_revision"] = engine.snapshot()["members"]["owner"]["revision"]
    result = await engine.execute(
        "owner",
        "tasks.correct_miss",
        {**payload, "reason": "Independent review"},
        "review",
        now.replace(hour=21),
    )
    assert result["correction_status"] == "reversed"


async def test_receipts_are_immutable_across_dates_correction_and_restart(engine, now, store):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True, "same_day_correction": True})
    await engine.tick(now.replace(hour=20))
    first = deepcopy(current(engine, task)["missed_receipt"])
    await engine.tick((now + timedelta(days=1)).replace(hour=20))
    history = deepcopy(current(engine, task)["missed_receipts"])
    assert len(history) == 2 and history[first["id"]] == first
    await action(engine, task, (now + timedelta(days=1)).replace(hour=21))
    restored = Engine(store.value, store.save)
    assert current(restored, task)["missed_receipts"] == history
    for actor in ("parent", "child"):
        exported = next(row for row in restored.view(actor)["tasks"] if row["id"] == task["id"])
        assert "missed_receipts" not in exported and "missed_scope" not in exported
        if actor == "child":
            assert "last_settlement" not in exported


async def test_same_date_reauthorization_gets_distinct_receipt_not_another_score(engine, now):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True})
    await engine.tick(now.replace(hour=20))
    first = deepcopy(current(engine, task)["missed_receipt"])
    await action(
        engine,
        task,
        now.replace(hour=20, minute=5),
        "revise",
        due_at=now.replace(hour=21).isoformat(),
        missed_policy=policy(repeat_penalty=True),
        missed_actor_revision=1,
    )
    await engine.tick(now.replace(hour=22))
    row = current(engine, task)
    second = row["missed_receipt"]
    assert first["id"] != second["id"]
    assert first["due_local_date"] == second["due_local_date"]
    assert row["missed_receipts"][first["id"]] == first
    assert second["outcome"] == "skipped_duplicate" and second["points"] == 0
    assert len(engine.snapshot()["court"]) == 1


async def test_capacity_pauses_one_task_without_eviction_or_repeated_updates(engine, now, store):
    await setup(engine, now)
    task = await create(engine, now)
    state = engine.snapshot()
    history = {
        f"synthetic-{index}": {"id": f"synthetic-{index}"}
        for index in range(settlements.MAX_SETTLEMENT_RECEIPTS)
    }
    state["tasks"][task["id"]]["missed_receipts"] = deepcopy(history)
    restored = Engine(state, store.save)
    # Ordinary work still executes in the same scheduler transaction.
    other = await restored.execute(
        "parent",
        "tasks.create",
        {
            "title": "Unaffected ordinary chore",
            "assignee": "sibling",
            "due_at": now.replace(hour=19).isoformat(),
            "penalty": -1,
        },
        "other",
        now,
    )
    await restored.tick(now.replace(hour=20))
    row = current(restored, task)
    assert row["missed_receipts"] == history and row["due_at"] == task["due_at"]
    assert row["missed_scope"]["state"] == "needs_review"
    assert row["missed_scope"]["reason"] == "settlement_capacity"
    assert set(restored.snapshot()["court"]) == {"task:" + other["id"]}
    assert not notices(restored)
    for days in (1, 2):
        await restored.tick(now + timedelta(days=days))
        assert current(restored, task) == row
    assert (
        next(row for row in restored.view("parent")["tasks"] if row["id"] == task["id"])[
            "missed_policy_reason"
        ]
        == "settlement_capacity"
    )
    with pytest.raises(DomainError, match="invalid_transition"):
        await action(
            restored,
            task,
            now + timedelta(days=2),
            "revise",
            missed_policy=policy(),
            missed_actor_revision=1,
        )


async def test_later_explicit_due_and_grace_crossing_midnight_are_preserved(engine, now):
    await setup(engine, now)
    task = await create(
        engine,
        now,
        due_at=now.replace(hour=23, minute=45).isoformat(),
        grace_minutes=30,
        missed={"same_day_correction": True},
    )
    await engine.tick(now.replace(hour=23, minute=59))
    assert not engine.snapshot()["court"]
    settled = (now + timedelta(days=1)).replace(hour=0, minute=15)
    await engine.tick(settled)
    receipt = current(engine, task)["missed_receipt"]
    assert receipt["due_local_date"] == "2026-09-06"
    assert receipt["settled_local_date"] == "2026-09-07"
    assert receipt["outcome"] == "applied"
    await action(engine, task, settled + timedelta(minutes=1))
    assert engine.snapshot()["court"][receipt["ledger_id"]]["status"] == "reversed"


async def test_missing_spring_cutoff_does_not_roll_before_later_deadline(engine, store):
    now = datetime(2026, 3, 29, 0, 0, tzinfo=UTC)
    await setup(engine, now, timezone="Europe/Berlin")
    task = await create(
        engine,
        now,
        due_at="2026-03-29T19:00:00+02:00",
        missed={"settle_time": "02:30", "repeat_penalty": True},
    )
    before = current(engine, task)
    await engine.tick(now.replace(hour=8))
    assert current(engine, task) == before
    await engine.tick(now.replace(hour=18))
    receipt = current(engine, task)["missed_receipt"]
    assert receipt["outcome"] == "skipped_outage"
    assert receipt["due_at"] == "2026-03-30T19:00:00+02:00"
    assert not engine.snapshot()["court"]
    restored = Engine(store.value, store.save)
    await restored.tick(now.replace(hour=19))
    assert current(restored, task)["missed_receipt"] == receipt


async def test_default_absence_preserves_ordinary_one_off_shape(engine, now):
    await setup(engine, now)
    task = await engine.execute(
        "parent",
        "tasks.create",
        {
            "title": "Legacy one-off",
            "assignee": "child",
            "due_at": now.replace(hour=19).isoformat(),
            "penalty": -1,
        },
        "legacy",
        now,
    )
    await engine.tick(now.replace(hour=20))
    await engine.tick(now + timedelta(days=5))
    row = current(engine, task)
    assert row["due_at"] == task["due_at"]
    assert not any(key.startswith("missed_") for key in row)
    assert set(engine.snapshot()["court"]) == {f"task:{task['id']}"}


@pytest.mark.parametrize(
    "change", ["parent_epoch", "child_epoch", "parent_role", "deadline", "module"]
)
async def test_queued_notice_is_revalidated_against_current_scope(engine, now, change):
    await setup(engine, now)
    task = await create(engine, now)
    await engine.tick(now.replace(hour=20))
    state = engine.snapshot()
    event = notices(engine)[0]
    assert current_task_event(state, event)
    if change == "parent_epoch":
        state["members"]["owner"]["revision"] += 1
    elif change == "child_epoch":
        state["members"]["child"]["revision"] += 1
    elif change == "parent_role":
        state["members"]["owner"]["role"] = "adult"
    elif change == "deadline":
        state["tasks"][task["id"]]["due_at"] = now.replace(hour=23).isoformat()
    else:
        state["settings"]["modules"].remove("tasks")
    assert not current_task_event(state, event)


async def test_capacity_store_failure_does_not_partially_pause(engine, now, store):
    task = await create(engine, now)
    state = engine.snapshot()
    state["tasks"][task["id"]]["missed_receipts"] = {
        str(index): {"id": str(index)} for index in range(settlements.MAX_SETTLEMENT_RECEIPTS)
    }
    restored = Engine(state, store.save)
    before = restored.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await restored.tick(now.replace(hour=20))
    assert restored.snapshot() == before


async def test_returning_to_ordinary_policy_cannot_assess_settled_task_again(engine, now):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True})
    await engine.tick(now.replace(hour=20))
    history = current(engine, task)["missed_receipts"]
    await action(
        engine,
        task,
        now.replace(hour=21),
        "revise",
        missed_policy=policy(daily_rollover=False),
        missed_actor_revision=1,
    )
    await engine.tick((now + timedelta(days=1)).replace(hour=21))
    assert len(engine.snapshot()["court"]) == 1
    assert current(engine, task)["missed_receipts"] == history


async def test_global_switch_revokes_until_fresh_parent_review(engine, now):
    await setup(engine, now)
    task = await create(engine, now, missed={"repeat_penalty": True})
    await engine.tick(now.replace(hour=20))
    settings = engine.snapshot()["settings"]
    for enabled in (False, True):
        await engine.execute(
            "owner",
            "settings.save",
            {
                "name": settings["name"],
                "language": "en",
                "modules": settings["modules"],
                "automatic_penalties": enabled,
            },
            f"switch-{enabled}",
            now.replace(hour=21),
        )
    await engine.tick((now + timedelta(days=1)).replace(hour=20))
    assert len(engine.snapshot()["court"]) == 1
    assert current(engine, task)["missed_scope"]["state"] == "revoked"
    later = now + timedelta(days=2)
    await action(
        engine,
        task,
        later,
        "revise",
        due_at=later.replace(hour=19).isoformat(),
        missed_policy=policy(repeat_penalty=True),
        missed_actor_revision=1,
    )
    await engine.tick(later.replace(hour=20))
    assert len(engine.snapshot()["court"]) == 2
