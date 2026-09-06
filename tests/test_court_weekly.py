"""Opt-in weekly reporting and independent appeal decisions use atomic local state."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.messages import render
from custom_components.family_assistant.telegram.router import route


async def configure(engine, now, **extra):
    return await engine.execute(
        "owner", "court.configure", {"revision": 0, **extra}, "configure", now
    )


async def award(engine, now, actor="parent", operation="award", **extra):
    return await engine.execute(
        actor,
        "court.award",
        {"member": "child", "points": -1, "reason": "Synthetic reason", **extra},
        operation,
        now,
    )


@pytest.mark.asyncio
async def test_default_is_quiet_and_current_summary_is_authorized(engine, now):
    await award(engine, now)
    await engine.tick(now + timedelta(days=1))
    assert not engine.snapshot()["court_reports"]
    assert not engine.view("sibling", now=now)["court_summary"]["rows"]
    assert "court_summary" not in engine.view("guest", now=now)
    assert engine.view("child", now=now)["court_summary"]["rows"][0]["total"] == -1
    assert "court_reports" not in engine.view("child", now=now)


@pytest.mark.asyncio
async def test_guest_cannot_receive_scores_and_auto_reason_keeps_task_reference(engine, now):
    with pytest.raises(DomainError, match="invalid_field"):
        await award(engine, now, member="guest")
    from custom_components.family_assistant.telegram.presentation import court_stats

    view = engine.view("child", now=now)
    view["tasks"] = [{"id": "T000001", "title": "Synthetic overdue task"}]
    view["court"] = [
        {
            "id": "task:T000001",
            "member": "child",
            "points": -1,
            "status": "active",
            "source": "task",
            "created_at": now.isoformat(),
            "reason_key": "task_missed",
            "reason_data": {"task_id": "T000001"},
        }
    ]
    for language in ("en", "ru", "uk"):
        answer = court_stats(view, language)
        assert "T000001" in answer and "Synthetic overdue task" in answer


@pytest.mark.asyncio
async def test_telegram_totals_reasons_and_appeal_resolution_replay(engine, now):
    await route(engine, "parent", "/award Child | -2 | Synthetic score reason", "award-chat", now)
    stats = await route(engine, "child", "/stats", "stats-chat", now)
    assert "Child: +0 / -2 = -2" in stats and "Synthetic score reason" in stats
    assert "C000001" in stats
    assert "C000001" not in await route(engine, "sibling", "/stats", "other-stats", now)
    assert "Current week" in await route(engine, "child", "/week", "week-chat", now)
    await route(engine, "child", "/appeal C000001 | Please review", "appeal-chat", now)
    first = await route(
        engine, "owner", "/courtresolve C000001 | reverse | Checked again", "resolve-chat", now
    )
    assert "reversed" in first
    assert first == await route(
        engine, "owner", "/courtresolve C000001 | reverse | Checked again", "resolve-chat", now
    )
    stats = await route(engine, "child", "/stats", "stats-after", now)
    assert "Child: +0 / 0 = +0" in stats and "Synthetic score reason" in stats
    with pytest.raises(DomainError, match="forbidden"):
        await route(
            engine, "child", "/award Sibling | 5 | Invalid parent operation", "deny-award", now
        )


@pytest.mark.asyncio
async def test_second_reviewer_requires_another_active_parent(engine, now):
    await engine.execute(
        "owner",
        "members.save",
        {"id": "parent", "name": "Parent", "role": "adult"},
        "downgrade",
        now,
    )
    with pytest.raises(DomainError, match="invalid_field"):
        await configure(engine, now, second_adult_review=True)


@pytest.mark.asyncio
async def test_pending_appeal_needs_explicit_decision_and_guest_cannot_appeal(engine, now):
    item = await award(engine, now)
    for actor in ("guest", "sibling"):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(
                actor, "court.appeal", {"id": item["id"], "reason": "Invalid actor"}, "deny", now
            )
    await engine.execute(
        "child", "court.appeal", {"id": item["id"], "reason": "Review"}, "appeal", now
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner",
            "court.resolve_appeal",
            {"id": item["id"], "reason": "Missing decision"},
            "missing",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_weekly_report_once_after_boundary_restart_and_reversal_are_preserved(
    engine, store, now
):
    await configure(engine, now, weekly_enabled=True)
    item = await award(engine, now)
    await engine.tick(now)
    assert not engine.snapshot()["court_reports"]
    boundary = now.replace(hour=0) + timedelta(days=1)
    await engine.tick(boundary)
    before = engine.snapshot()
    assert len(before["court_reports"]) == 1
    report = next(iter(before["court_reports"].values()))
    assert report["rows"][0]["total"] == -1
    assert report["events"] == [item["id"]]
    restarted = Engine(store.value, store.save)
    assert not await restarted.tick(boundary + timedelta(minutes=1))
    await restarted.execute(
        "owner",
        "court.reverse",
        {"id": item["id"], "revision": item["revision"], "reason": "Correction"},
        "reverse",
        boundary,
    )
    assert next(iter(restarted.snapshot()["court_reports"].values())) == report
    assert (
        len([e for e in restarted.snapshot()["outbox"].values() if e["key"] == "court_weekly"]) == 1
    )
    event = next(e for e in before["outbox"].values() if e["key"] == "court_weekly")
    for language in ("en", "ru", "uk"):
        rendered = render(event, {"id": -999, "language": language}, before)
        assert "Child: +0 / -1 = -1" in rendered["text"]
        assert "parse_mode" not in rendered
        assert len(rendered["text"]) < 4000


@pytest.mark.asyncio
async def test_weekly_tick_store_failure_and_bounded_catchup(engine, store, now):
    await configure(engine, now, weekly_enabled=True)
    await award(engine, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(now + timedelta(days=60))
    assert engine.snapshot() == before
    store.fail = False
    await engine.tick(now + timedelta(days=60))
    assert len(engine.snapshot()["court_reports"]) == 1
    assert len(engine.snapshot()["outbox"]) == 1


@pytest.mark.asyncio
async def test_court_config_permissions_revisions_and_disable_supersedes_pending(engine, now):
    for actor in ("parent", "adult", "child", "guest"):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(actor, "court.configure", {"revision": 0}, "deny", now)
    config = await configure(engine, now, weekly_enabled=True)
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute("owner", "court.configure", {"revision": 0}, "stale", now)
    await engine.tick(now + timedelta(days=1))
    await engine.execute(
        "owner",
        "court.configure",
        {"revision": config["revision"], "weekly_enabled": False},
        "disable",
        now + timedelta(days=1),
    )
    await engine.tick(now + timedelta(days=1, minutes=1))
    assert all(e["state"] == "superseded" for e in engine.snapshot()["outbox"].values())
    before = engine.snapshot()
    for bad in (None, True, "1", -1, 1.0):
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute("owner", "court.configure", {"revision": bad}, "bad", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_independent_appeal_reviewer_cannot_be_bypassed_by_direct_reverse(engine, now):
    await configure(engine, now, second_adult_review=True)
    item = await award(engine, now)
    appeal = await engine.execute(
        "child", "court.appeal", {"id": item["id"], "reason": "Please review"}, "appeal", now
    )
    for action, extra in (("court.resolve_appeal", {"decision": "reverse"}), ("court.reverse", {})):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(
                "parent",
                action,
                {"id": item["id"], "revision": appeal["revision"], "reason": "Same adult", **extra},
                "self-" + action,
                now,
            )
    with pytest.raises(DomainError, match="invalid_transition"):
        await engine.execute(
            "child", "court.appeal", {"id": item["id"], "reason": "Again"}, "repeat-appeal", now
        )
    payload = {
        "id": item["id"],
        "revision": appeal["revision"],
        "decision": "reverse",
        "reason": "Independent review",
    }
    resolved = await engine.execute("owner", "court.resolve_appeal", payload, "resolve", now)
    assert resolved["status"] == "reversed" and resolved["reason"] == item["reason"]
    assert resolved["appeal"]["resolution"]["actor"] == "owner"
    assert (
        await engine.execute("owner", "court.resolve_appeal", payload, "resolve", now) == resolved
    )
    events = engine.snapshot()["outbox"]
    assert len([e for e in events.values() if e["key"] == "court_appeal_resolved"]) == 1
    assert all(e["state"] == "superseded" for e in events.values() if e["key"] == "court_appeal")


@pytest.mark.asyncio
async def test_upheld_appeal_history_and_failed_resolution_do_not_lose_data(engine, store, now):
    item = await award(engine, now)
    appeal = await engine.execute(
        "child", "court.appeal", {"id": item["id"], "reason": "First reason"}, "appeal", now
    )
    payload = {
        "id": item["id"],
        "revision": appeal["revision"],
        "decision": "uphold",
        "reason": "Verified",
    }
    before = deepcopy(engine.snapshot())
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("owner", "court.resolve_appeal", payload, "resolve", now)
    assert engine.snapshot() == before
    store.fail = False
    resolved = await engine.execute("owner", "court.resolve_appeal", payload, "resolve", now)
    assert resolved["status"] == "active" and "reversal" not in resolved
    next_appeal = await engine.execute(
        "child",
        "court.appeal",
        {"id": item["id"], "revision": resolved["revision"], "reason": "New evidence"},
        "new",
        now,
    )
    assert next_appeal["previous_appeals"] == [resolved["appeal"]]
    assert next_appeal["appeal"]["reason"] == "New evidence"
