"""Clock/state-machine tests, using synthetic schedules and no physical siren."""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.alarms import scheduled_time
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def schedule(engine, now, **overrides):
    data = {
        "member": "child",
        "time": "08:00",
        "days": list(range(7)),
        "timezone": "UTC",
        "profile": "strict",
        **overrides,
    }
    return await engine.execute("owner", "alarms.save", data, f"schedule:{overrides}", now)


def current(engine):
    return engine.view("child")["alarm_runs"][-1]


def solution(run):
    return sum(int(n) for n in run["challenge"]["question"].split(" + "))


async def answer(engine, run, now, operation="answer", actor="child", value=None):
    return await engine.execute(
        actor,
        "alarms.answer",
        {
            "id": run["id"],
            "nonce": run["challenge"]["nonce"],
            "answer": solution(run) if value is None else value,
        },
        operation,
        now,
    )


@pytest.mark.asyncio
async def test_two_stages_survive_restart_and_no_early_reply(engine, store, now):
    await schedule(engine, now)
    assert await engine.tick(now)
    first = current(engine)
    assert first["stage"] == "first" and first["siren_desired"]
    assert "challenge_secret" not in first
    assert not await engine.tick(now)
    result = await answer(engine, first, now + timedelta(seconds=30))
    assert result["accepted"]
    engine = Engine(deepcopy(store.value), store.save)
    waiting = current(engine)
    assert waiting["stage"] == "waiting_second" and not waiting["siren_desired"]
    second_at = datetime.fromisoformat(waiting["second_at"])
    assert (
        timedelta(minutes=12) <= second_at - (now + timedelta(seconds=30)) <= timedelta(minutes=18)
    )
    with pytest.raises(DomainError, match="challenge_expired"):
        await answer(engine, first, now + timedelta(minutes=1), "early")
    await engine.tick(second_at)
    second = current(engine)
    assert second["stage"] == "second" and not second["siren_desired"]
    assert second["challenge"]["nonce"] != first["challenge"]["nonce"]
    await engine.tick(second_at + timedelta(seconds=60))
    assert current(engine)["siren_desired"]
    await answer(engine, second, second_at + timedelta(seconds=61), "second")
    assert current(engine)["stage"] == "complete"
    assert not current(engine)["siren_desired"]
    await engine.tick(now + timedelta(hours=2))
    assert not engine.snapshot()["court"]


@pytest.mark.asyncio
async def test_cannot_replay_other_child_or_parent_confirm(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    run = current(engine)
    for actor in ("parent", "sibling", "owner", "guest"):
        with pytest.raises(DomainError, match="forbidden"):
            await answer(engine, run, now, actor, actor)
    assert engine.view("sibling")["alarm_runs"] == []
    result = await answer(engine, run, now)
    assert await answer(engine, run, now + timedelta(seconds=1)) == result
    with pytest.raises(DomainError, match="challenge_expired"):
        await answer(engine, run, now, "different-id")


@pytest.mark.asyncio
async def test_guess_limit_refreshes_and_old_challenge_is_superseded(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    run = current(engine)
    for attempt in range(3):
        result = await answer(engine, run, now, f"wrong:{attempt}", value=-99)
        assert not result["accepted"]
    assert current(engine)["challenge"]["nonce"] != run["challenge"]["nonce"]
    notifications = list(engine.snapshot()["outbox"].values())
    assert [e["state"] for e in notifications].count("pending") == 1
    assert [e["state"] for e in notifications].count("superseded") == 1
    with pytest.raises(DomainError, match="challenge_expired"):
        await answer(engine, run, now, "stale")


@pytest.mark.asyncio
async def test_expired_answer_never_silences_siren(engine, now):
    await schedule(engine, now)
    await engine.tick(now)
    run = current(engine)
    with pytest.raises(DomainError, match="challenge_expired"):
        await answer(engine, run, now + timedelta(minutes=5))
    await engine.tick(now + timedelta(minutes=5))
    assert current(engine)["siren_desired"]
    assert current(engine)["challenge"]["nonce"] != run["challenge"]["nonce"]


@pytest.mark.asyncio
async def test_no_default_penalties_test_runs_and_single_escalation(engine, store, now):
    alarm = await schedule(engine, now, penalty=-1)
    await engine.tick(now)
    await engine.tick(now + timedelta(minutes=30))
    assert not engine.snapshot()["court"]
    missed = [e for e in engine.snapshot()["outbox"].values() if e["key"] == "alarm_missed"]
    assert len(missed) == 1
    run = current(engine)
    await engine.execute(
        "parent",
        "alarms.cancel",
        {"id": run["id"], "reason": "Parent checked"},
        "cancel",
        now + timedelta(minutes=31),
    )
    closed = [e for e in engine.snapshot()["outbox"].values() if e["key"] == "alarm_closed"]
    assert len(closed) == 1
    state = engine.snapshot()
    state["settings"]["automatic_penalties"] = True
    engine = Engine(state, store.save)
    await engine.execute("parent", "alarms.test", {"id": alarm["id"]}, "test", now)
    await engine.tick(now + timedelta(minutes=31))
    assert not engine.snapshot()["court"]
    assert len([e for e in engine.snapshot()["outbox"].values() if e["key"] == "alarm_missed"]) == 1


@pytest.mark.asyncio
async def test_penalty_once_after_restart_keeps_ringing(engine, store, now):
    state = engine.snapshot()
    state["settings"]["automatic_penalties"] = True
    engine = Engine(state, store.save)
    await schedule(engine, now, penalty=-1)
    await engine.tick(now)
    await engine.tick(now + timedelta(minutes=30))
    engine = Engine(deepcopy(store.value), store.save)
    for minute in range(31, 36):
        await engine.tick(now + timedelta(minutes=minute))
    assert len(engine.snapshot()["court"]) == 1
    assert current(engine)["siren_desired"]


@pytest.mark.asyncio
async def test_store_failure_does_not_publish_ringing_or_queue(engine, store, now):
    await schedule(engine, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(now)
    assert engine.snapshot() == before
    store.fail = False
    await engine.tick(now)
    assert len(engine.snapshot()["alarm_runs"]) == 1


@pytest.mark.asyncio
async def test_disable_schedule_module_or_member_cancels_active(engine, now):
    alarm = await schedule(engine, now)
    await engine.tick(now)
    await engine.execute(
        "parent", "alarms.enable", {"id": alarm["id"], "enabled": False}, "disable", now
    )
    assert current(engine)["stage"] == "cancelled"
    assert not current(engine)["siren_desired"]
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child", "alarms.enable", {"id": alarm["id"], "enabled": True}, "child-enable", now
        )


@pytest.mark.asyncio
async def test_exceptions_catchup_and_overlaps(engine, now):
    await schedule(engine, now, exceptions=[now.date().isoformat()])
    assert not await engine.tick(now)
    with pytest.raises(DomainError, match="schedule_overlap"):
        await schedule(engine, now, name="Duplicate")


@pytest.mark.asyncio
async def test_no_alarm_for_stale_downtime(engine, now):
    await schedule(engine, now)
    assert not await engine.tick(now + timedelta(minutes=31))
    assert not engine.snapshot()["alarm_runs"]


def test_dst_skip_nonexistent_and_only_one_fall_back_occurrence():
    schedule = {"timezone": "Europe/Berlin", "time": "02:30"}
    assert scheduled_time(schedule, date(2026, 3, 29)) is None
    assert scheduled_time(schedule, date(2026, 10, 25)) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"time": "25:00"},
        {"days": [True]},
        {"timezone": "bad/zone"},
        {"days": []},
        {"second_min": 19},
        {"penalty": 1},
        {"exceptions": ["tomorrow"]},
        {"enabled": "true"},
    ],
)
async def test_invalid_schedules_are_atomic(engine, now, override):
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await schedule(engine, now, **override)
    assert engine.snapshot() == before
