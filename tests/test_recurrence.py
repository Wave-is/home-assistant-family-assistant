"""Duties are generated once by local calendar, not repeatedly by a timer."""

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.recurrence import due, matches, validate
from custom_components.family_assistant.domain.validation import DomainError


def rule(**extra):
    return {
        "frequency": "daily",
        "start_date": "2026-09-01",
        "time": "07:00",
        "timezone": "UTC",
        **extra,
    }


async def series(engine, now, **extra):
    return await engine.execute(
        "parent",
        "tasks.series_save",
        {
            "title": "Take out recycling",
            "assignees": ["child", "sibling"],
            "rule": rule(),
            "due_time": "20:00",
            **extra,
        },
        "series",
        now - timedelta(hours=2),
    )


def test_weekly_interval_and_monthly_missing_days():
    weekly = validate(rule(frequency="weekly", interval=2, weekdays=[0, 4]))
    assert matches(weekly, date(2026, 9, 4))
    assert not matches(weekly, date(2026, 9, 11))
    assert matches(weekly, date(2026, 9, 14))
    monthly = validate(rule(frequency="monthly", start_date="2026-01-01", month_day=31))
    assert matches(monthly, date(2026, 1, 31))
    assert not matches(monthly, date(2026, 2, 28))
    assert matches(monthly, date(2026, 3, 31))


def test_dst_gap_skipped_fold_once_and_quick_normal_tick():
    spring = validate(rule(start_date="2026-01-01", timezone="Europe/Kyiv", time="03:30"))
    moments = list(due(spring, datetime(2026, 3, 29, 10, tzinfo=UTC)))
    assert not any(m.date() == date(2026, 3, 29) for m in moments)
    moments = list(due(spring, datetime(2026, 10, 25, 10, tzinfo=UTC)))
    today = [m for m in moments if m.date() == date(2026, 10, 25)]
    assert len(today) == 1 and today[0].fold == 0
    quick = validate(rule(catchup_hours=0))
    assert len(list(due(quick, datetime(2026, 9, 6, 7, 0, 5, tzinfo=UTC)))) == 1
    assert not list(due(quick, datetime(2026, 9, 6, 7, 2, tzinfo=UTC)))


@pytest.mark.asyncio
async def test_multiple_assignees_receive_independent_tasks_once(engine, store, now):
    duty = await series(engine, now)
    assert await engine.tick(now)
    state = engine.snapshot()
    assert len(state["tasks"]) == 2 and len(state["outbox"]) == 2
    assert {t["assignee"] for t in state["tasks"].values()} == {"child", "sibling"}
    assert all(t["series_id"] == duty["id"] for t in state["tasks"].values())
    restarted = Engine(state, store.save)
    assert not await restarted.tick(now + timedelta(seconds=10))
    assert len(restarted.snapshot()["tasks"]) == 2


@pytest.mark.asyncio
async def test_rotation_survives_restart_and_skips_inactive_member(engine, store, now):
    await series(engine, now, rotation=True)
    await engine.tick(now)
    assert next(iter(engine.snapshot()["tasks"].values()))["assignee"] == "child"
    engine = Engine(engine.snapshot(), store.save)
    await engine.tick(now + timedelta(days=1))
    assert engine.snapshot()["tasks"]["T000002"]["assignee"] == "sibling"
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": engine.snapshot()["members"]["child"]["revision"],
            "name": "Child",
            "role": "child",
            "active": False,
        },
        "inactive",
        now,
    )
    await engine.tick(now + timedelta(days=2))
    assert engine.snapshot()["tasks"]["T000003"]["assignee"] == "sibling"


@pytest.mark.asyncio
async def test_late_restart_creates_no_backlog_or_immediate_punishment(engine, now):
    duty = await series(engine, now)
    await engine.tick(now + timedelta(days=30, hours=13))
    state = engine.snapshot()
    assert not state["tasks"] and not state["court"]
    assert (
        list(state["task_series"][duty["id"]]["occurrences"].values())[0]["state"]
        == "skipped_deadline"
    )


@pytest.mark.asyncio
async def test_storage_fault_and_parent_revocation_cannot_generate_tasks(engine, store, now):
    await series(engine, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(now)
    assert engine.snapshot() == before
    store.fail = False
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": engine.snapshot()["members"]["parent"]["revision"],
            "name": "Parent",
            "role": "adult",
        },
        "revoke",
        now,
    )
    assert not await engine.tick(now)
    assert not engine.snapshot()["tasks"]


@pytest.mark.asyncio
async def test_disabled_series_and_exception_date_stay_quiet(engine, now):
    duty = await series(engine, now, rule=rule(exceptions=["2026-09-06"]))
    assert not await engine.tick(now)
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child", "tasks.series_enable", {"id": duty["id"], "enabled": True}, "bad", now
        )
    await engine.execute(
        "parent",
        "tasks.series_enable",
        {"id": duty["id"], "revision": duty["revision"], "enabled": False},
        "off",
        now,
    )
    assert not await engine.tick(now + timedelta(days=1))


@pytest.mark.asyncio
async def test_malformed_series_never_partial_saves(engine, now):
    for assignees in ([{}], ["child", "child"], [], [False]):
        with pytest.raises(DomainError, match="invalid_field"):
            await series(engine, now, assignees=assignees)
    assert not engine.snapshot()["task_series"]
