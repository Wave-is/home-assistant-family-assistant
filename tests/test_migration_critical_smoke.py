"""Migration smoke tests across the 7 critical modules in isolated shadow mode.

Verifies that legacy exports convert cleanly and run under strict shadow isolation
for all 7 critical areas: Tasks, Shopping, Alarms, Court, Routines/Calendar,
Network/Kid Control, and Dashboard.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.migration.review import read_store_pair
from custom_components.family_assistant.migration.shadow import build_shadow_candidate
from custom_components.family_assistant.network import kid_plans
from tests.ha_legacy_archive_smoke import synthetic_source

PREPARED_AT = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)


def _build_shadow_state():
    """Construct a full shadow candidate state from synthetic legacy sources."""
    assistant, court, mapping, members = synthetic_source(lifecycle=True)
    target = new_state("synthetic-owner-ha-id", "Synthetic migration shadow", modules=[])
    for member in members.values():
        member.update(
            language="en",
            aliases=[],
            ha_user_id="synthetic-owner-ha-id"
            if member["role"] == "owner"
            else "synthetic-child-ha-id",
        )
    target["members"] = members
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    policy = {
        "schema": 1,
        "revision": 1,
        "source_review_fingerprint": review.summary()["fingerprint"],
        "reviewers": {
            key: [row["reviewer"]]
            for key, row in review.private_data()[0]["ledger"]["tasks"].items()
            if row.get("requires_report") is True
        },
    }
    candidate = build_shadow_candidate(
        review, target, reviewer_policy=policy, prepared_at=PREPARED_AT
    )
    return candidate.private_state(), target


async def _never_persist(_state):
    pytest.fail("Shadow engine attempted to persist state")


# ---------------------------------------------------------------------------
# 1. Tasks (Задачи)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_smoke_tasks():
    state, _ = _build_shadow_state()
    engine = Engine(state, _never_persist)
    assert engine.shadow_mode

    # Tasks retain their original IDs and contents
    tasks = state["tasks"]
    assert "T000002" in tasks  # Fictional chore
    assert "T000003" in tasks  # Fictional private reminder
    assert "T000004" in tasks  # Fictional reviewed text task

    chore = tasks["T000002"]
    assert chore["title"] == "Fictional chore"
    assert chore["status"] == "in_progress"
    assert chore["assignee"] == "child"

    reminder = tasks["T000003"]
    assert reminder["title"] == "Fictional private reminder"
    assert reminder["delivery_scope"] == "personal"
    assert reminder["assignee"] == "owner"

    text_task = tasks["T000004"]
    assert text_task["title"] == "Fictional reviewed text task"
    assert text_task["report_type"] == "text"
    assert text_task["status"] == "submitted"
    assert text_task["report"] == "Report after reassignment"

    # All mutations must be blocked
    for action in ("tasks.create", "tasks.revise", "tasks.submit", "tasks.archive"):
        with pytest.raises(DomainError, match="migration_shadow_read_only"):
            await engine.execute("owner", action, {"title": "Attempt"}, "op-task", PREPARED_AT)


# ---------------------------------------------------------------------------
# 2. Shopping (Покупки)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_smoke_shopping():
    state, _ = _build_shadow_state()
    engine = Engine(state, _never_persist)

    # Legacy shopping task T000001 is converted into the separate shopping namespace S000001
    shopping = state["shopping"]
    assert len(shopping) == 1
    item = shopping["S000001"]
    assert item["name"] == "\u042f\u0431\u043b\u043e\u043a\u0438"
    assert item["quantity"] == 3.0
    assert item["purchased"] == 1.5
    assert item["unit"] == "kg"
    assert item["status"] == "approved"

    # All shopping mutations must be blocked
    for action, payload in [
        ("shopping.add", {"name": "Bread"}),
        ("shopping.buy", {"id": "S000001", "quantity": 1.0}),
        ("shopping.cancel", {"id": "S000001"}),
    ]:
        with pytest.raises(DomainError, match="migration_shadow_read_only"):
            await engine.execute("owner", action, payload, "op-shop", PREPARED_AT)


# ---------------------------------------------------------------------------
# 3. Alarms (Будильники)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_smoke_alarms():
    state, _ = _build_shadow_state()
    engine = Engine(state, _never_persist)

    # Converted alarms must be disabled, gentle, zero penalty
    alarms = state["alarms"]
    assert len(alarms) >= 1
    for _alarm_id, alarm in alarms.items():
        assert alarm["enabled"] is False
        assert alarm["penalty"] == 0
        assert alarm["profile"] == "gentle"
        assert alarm["member"] == "child"

    # Active runs must be empty
    assert state["alarm_runs"] == {}
    assert state["alarm_outputs"] == {}

    # Tick must be rejected, no alarm can fire
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await engine.tick(PREPARED_AT)

    # Alarm actions must reject
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await engine.execute(
            "owner", "alarms.save", {"member": "child", "time": "08:00"}, "op-alarm", PREPARED_AT
        )


# ---------------------------------------------------------------------------
# 4. Court (Суд)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_smoke_court():
    state, _ = _build_shadow_state()
    engine = Engine(state, _never_persist)

    # Court events from open week converted into C000001...
    court = state["court"]
    assert len(court) == 1
    event = court["C000001"]
    assert event["member"] == "child"
    assert event["status"] == "active"
    assert isinstance(event["points"], int)

    # Balance check: matches synthetic court event score exactly (-1 point)
    total_points = sum(r["points"] for r in court.values() if r["member"] == "child")
    assert total_points == -1

    # Court actions must reject
    for action, payload in [
        ("court.award", {"member": "child", "points": 5, "reason": "Chore"}),
        ("court.deduct", {"member": "child", "points": 2, "reason": "Late"}),
    ]:
        with pytest.raises(DomainError, match="migration_shadow_read_only"):
            await engine.execute("owner", action, payload, "op-court", PREPARED_AT)


# ---------------------------------------------------------------------------
# 5. Routines / Calendar (Расписание / Календарь)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_smoke_routines_and_calendar():
    state, _ = _build_shadow_state()
    engine = Engine(state, _never_persist)

    # Routines and Calendar must be clean and unconfigured in shadow state
    assert state["routines"] == {}
    assert state["routine_runs"] == {}
    assert state["calendar"] == {}
    assert "routines" not in state["settings"]["modules"]
    assert "calendar" not in state["settings"]["modules"]

    # No routine action can execute
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await engine.execute(
            "owner", "routines.start", {"routine_id": "r1"}, "op-routine", PREPARED_AT
        )

    # Clock tick cannot advance or start any routine
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await engine.tick(PREPARED_AT)


# ---------------------------------------------------------------------------
# 6. Network / Kid Control (Сеть / Kid Control)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_migration_smoke_network_and_kid_control():
    state, _ = _build_shadow_state()
    engine = Engine(state, _never_persist)

    # Network state is empty and unconfigured
    assert state["network"] == {}
    assert "mikrotik" not in state["settings"]["modules"]

    # Kid Control view projection handles empty network cleanly without error
    kc_view = kid_plans.view(state, "owner", PREPARED_AT)
    assert kc_view["profiles"] == []
    assert kc_view["plans"] == []
    assert kc_view["can_manage"] is True

    # Strict preconditions cannot be activated because module is absent
    from custom_components.family_assistant.network.strict_preconditions import check

    unmet = check(state, PREPARED_AT)
    assert "module_disabled" in unmet

    # Network actions must reject
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await engine.execute(
            "owner",
            "mikrotik.kid_pause",
            {"member": "child", "duration_minutes": 30},
            "op-net",
            PREPARED_AT,
        )


# ---------------------------------------------------------------------------
# 7. Dashboard / View Projections (Дашборд)
# ---------------------------------------------------------------------------
def test_migration_smoke_dashboard():
    state, _ = _build_shadow_state()
    engine = Engine(state, _never_persist)

    # 1. Owner view has explicit read-only marker
    view = engine.view("owner", now=PREPARED_AT)
    assert view["read_only"] == "migration_shadow_read_only"
    assert view["role"] == "owner"
    assert view["actor"] == "owner"

    # 2. Populated buckets match shadow candidate contents
    assert len(view["tasks"]) == 3
    assert len(view["shopping"]) == 1
    assert len(view["court"]) == 1
    assert len(view["alarms"]) >= 1

    # 3. Sensitive migration internal archive is NEVER leaked into view
    assert "migration_archive" not in view
    assert "migration_shadow" not in view
    assert "migration_archive" in state  # Exists in Store state, but hidden from view

    # 4. Non-owners (child, parent) are strictly forbidden from viewing shadow copy
    with pytest.raises(DomainError, match="forbidden"):
        engine.view("child", now=PREPARED_AT)

    with pytest.raises(DomainError, match="forbidden"):
        engine.actor_for_ha("synthetic-child-ha-id")
