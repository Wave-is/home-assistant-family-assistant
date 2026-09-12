"""Saved score rules and source correction use the canonical Engine transaction."""

import json
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.court import ParsedMessage, calculate_court_stats
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.court_router import route_court


def rule(**overrides):
    return {
        "id": "example-rule",
        "label": "Example family review",
        "direction": "at_most",
        "points": -3,
        "members": ["child"],
        **overrides,
    }


async def configure(engine, now, **changes):
    revision = engine.view("owner", now=now)["court_config"]["revision"]
    return await engine.execute(
        "owner", "court.configure", {"revision": revision, **changes}, f"config-{revision}", now
    )


async def award(engine, now, *, member="child", points=-2, operation="award"):
    return await engine.execute(
        "parent",
        "court.award",
        {
            "member": member,
            "points": points,
            "reason": "Synthetic score reason",
        },
        operation,
        now,
    )


async def automatic(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": settings["modules"],
            "automatic_penalties": True,
        },
        "opt-in",
        now,
    )
    task = await engine.execute(
        "parent",
        "tasks.create",
        {
            "title": "Synthetic chore",
            "assignee": "child",
            "penalty": -1,
            "due_at": (now + timedelta(hours=1)).isoformat(),
        },
        "task",
        now,
    )
    await engine.tick(now + timedelta(hours=2))
    return task, engine.snapshot()["court"][f"task:{task['id']}"]


def correction(task, record, **changes):
    return {
        "source": "task",
        "source_id": task["id"],
        "member": "child",
        "revision": record["revision"],
        "reason": "Parent verified the automatic score was mistaken",
        **changes,
    }


async def test_no_default_threshold_and_configured_numeric_progress(engine, now):
    assert engine.view("owner", now=now)["court_config"]["thresholds"] == []
    rules = [rule(), rule(id="positive", label="Example goal", direction="at_least", points=4)]
    await configure(engine, now, thresholds=rules)
    await award(engine, now)
    rows = engine.view("child", now=now)["court_summary"]["thresholds"]
    assert [(r["rule_id"], r["reached"], r["remaining"]) for r in rows] == [
        ("example-rule", False, 1),
        ("positive", False, 6),
    ]
    await award(engine, now, points=-1, operation="second")
    rows = engine.view("child", now=now)["court_summary"]["thresholds"]
    assert rows[0]["reached"] and rows[0]["remaining"] == 0
    assert len(engine.snapshot()["court"]) == 2
    assert engine.snapshot()["outbox"] == {}  # A threshold is not an effect or notification.


async def test_rule_labels_are_projected_only_to_authorized_member(engine, now):
    await configure(
        engine,
        now,
        thresholds=[
            rule(),
            rule(id="private", members=["sibling"], label="Private sibling-only rule"),
        ],
    )
    await award(engine, now)
    await award(engine, now, member="sibling", operation="sibling")
    child = engine.view("child", now=now)
    assert "Private sibling-only rule" not in json.dumps(child)
    assert {r["member"] for r in child["court_summary"]["thresholds"]} == {"child"}
    assert "Private sibling-only rule" in json.dumps(engine.view("parent", now=now))
    assert "Private sibling-only rule" not in json.dumps(engine.view("guest", now=now))


async def test_disabled_member_rule_can_be_preserved_on_metadata_edit(engine, store, now):
    await configure(engine, now, thresholds=[rule()])
    state = engine.snapshot()
    state["members"]["child"]["active"] = False
    restored = Engine(state, store.save)
    changed = await configure(restored, now, time="22:00", weekday=4)
    assert changed["thresholds"] == [rule()]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        [rule(points=True)],
        [rule(points=1.5)],
        [rule(points=10001)],
        [rule(direction="device_action")],
        [rule(members=["guest"])],
        [rule(members=["missing"])],
        [rule(members=["child", "child"])],
        [rule(), rule()],
        [rule(label="")],
        [rule(extra="unknown")],
        [rule()] * 21,
    ],
)
async def test_invalid_rule_rejected_without_state_change(engine, now, bad):
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await configure(engine, now, thresholds=bad)
    assert engine.snapshot() == before


@pytest.mark.parametrize("actor", ["parent", "adult", "child", "guest"])
async def test_only_owner_configures_thresholds(engine, now, actor):
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            actor,
            "court.configure",
            {
                "revision": 0,
                "thresholds": [rule()],
            },
            "denied-config",
            now,
        )


async def test_reports_keep_rule_and_balance_snapshot_after_rule_change(engine, store, now):
    await configure(engine, now, thresholds=[rule()], weekly_enabled=True)
    await award(engine, now, points=-4)
    await engine.tick(now + timedelta(days=1))
    report = deepcopy(next(iter(engine.snapshot()["court_reports"].values())))
    assert report["thresholds"][0]["reached"]
    await configure(
        engine, now + timedelta(days=1), thresholds=[rule(label="Changed label", points=-8)]
    )
    restored = Engine(store.value, store.save)
    assert next(iter(restored.snapshot()["court_reports"].values())) == report
    assert sum(r["points"] for r in restored.snapshot()["court"].values()) == -4


async def test_rule_store_failure_keeps_previous_configuration(engine, store, now):
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await configure(engine, now, thresholds=[rule()])
    assert engine.snapshot() == before


async def test_zero_score_threshold_projection_is_explicit_and_effect_free(engine, now):
    rules = [rule(direction="at_least", points=4)]
    view = engine.view("child", now=now)
    summary = calculate_court_stats(
        [],
        now=now,
        members=[m for m in view["members"] if m["id"] == "child"],
        thresholds=rules,
    )
    assert summary.stats["child"]["thresholds"][0]["remaining"] == 4
    assert engine.snapshot()["court"] == {}


async def test_exact_source_reversal_preserves_other_scores_and_survives_restart(
    engine, store, now
):
    task, record = await automatic(engine, now)
    manual = await award(engine, now + timedelta(hours=2), operation="manual")
    original_task = deepcopy(engine.snapshot()["tasks"][task["id"]])
    payload = correction(task, record)
    result = await engine.execute("parent", "court.reverse_source", payload, "correct", now)
    assert result["status"] == "reversed"
    assert result["reason_data"] == record["reason_data"]
    assert result["reversal"]["source_reference"] == {"source": "task", "source_id": task["id"]}
    restored = Engine(store.value, store.save)
    assert (
        await restored.execute("parent", "court.reverse_source", payload, "correct", now) == result
    )
    await restored.tick(now + timedelta(days=1))
    assert len(restored.snapshot()["court"]) == 2
    assert restored.snapshot()["court"][manual["id"]]["status"] == "active"
    assert restored.snapshot()["tasks"][task["id"]] == original_task


@pytest.mark.parametrize(
    "changes",
    [
        {"member": "sibling"},
        {"source_id": "missing"},
        {"source": "manual"},
        {"revision": 2},
        {"revision": True},
        {"reason": ""},
    ],
)
async def test_source_reversal_rejects_wrong_target_and_revision(engine, now, changes):
    task, record = await automatic(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute(
            "parent",
            "court.reverse_source",
            correction(task, record, **changes),
            "bad-correction",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.parametrize("actor", ["child", "adult", "guest"])
async def test_source_reversal_requires_parent(engine, now, actor):
    task, record = await automatic(engine, now)
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(actor, "court.reverse_source", correction(task, record), "denied", now)


async def test_source_reversal_honors_independent_appeal_review(engine, now):
    await configure(engine, now, second_adult_review=True)
    task, record = await automatic(engine, now)
    appealed = await engine.execute(
        "owner",
        "court.appeal",
        {
            "id": record["id"],
            "revision": record["revision"],
            "reason": "Please review source",
        },
        "appeal-source",
        now,
    )
    payload = correction(task, appealed)
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("owner", "court.reverse_source", payload, "self-review", now)
    result = await engine.execute("parent", "court.reverse_source", payload, "independent", now)
    assert result["appeal"]["status"] == "resolved"
    assert result["appeal"]["decision"] == "reverse"


async def test_source_reversal_disk_failure_is_atomic(engine, store, now):
    task, record = await automatic(engine, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute(
            "parent", "court.reverse_source", correction(task, record), "disk", now
        )
    assert engine.snapshot() == before


async def test_automatic_history_has_localized_reason_and_exact_task_reference(engine, now):
    task, _ = await automatic(engine, now)
    answer = await route_court(
        engine,
        "child",
        "/history",
        "history",
        now + timedelta(hours=2),
        ParsedMessage("history"),
        engine.view("child", now=now),
        "en",
    )
    assert "Task deadline was missed" in answer and task["id"] in answer


async def test_exact_alarm_source_can_be_reversed_without_changing_alarm_run(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": settings["modules"],
            "automatic_penalties": True,
        },
        "opt-in",
        now,
    )
    await engine.execute(
        "owner",
        "alarms.save",
        {
            "member": "child",
            "time": "08:00",
            "days": list(range(7)),
            "timezone": "UTC",
            "profile": "gentle",
            "penalty": -1,
        },
        "alarm",
        now,
    )
    await engine.tick(now)
    await engine.tick(now + timedelta(minutes=40))
    state = engine.snapshot()
    record = next(iter(state["court"].values()))
    result = await engine.execute(
        "parent",
        "court.reverse_source",
        {
            "source": "alarm",
            "source_id": record["reason_data"]["run_id"],
            "member": "child",
            "revision": record["revision"],
            "reason": "Synthetic parent correction",
        },
        "alarm-correction",
        now + timedelta(minutes=41),
    )
    assert result["status"] == "reversed"
    assert engine.snapshot()["alarm_runs"] == state["alarm_runs"]
