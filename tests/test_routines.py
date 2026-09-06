"""Tests for domain routines execution, persistence, and state machine transitions."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def enabled_engine(engine, store):
    snapshot = engine.snapshot()
    if "routines" not in snapshot["settings"]["modules"]:
        snapshot["settings"]["modules"].append("routines")
    rebuilt = Engine(snapshot, store.save)
    return rebuilt


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


@pytest.mark.asyncio
async def test_ordered_manual_steps_and_fresh_nonce_transitions(enabled_engine, now):
    """Cover ordered steps, fresh nonce check, wrong actor, and future step denial."""
    # Create template with 2 ordered manual steps
    t_payload = {
        "title": "Morning Prep",
        "assignees": ["child"],
        "steps": [
            {"title": "Brush teeth", "confirmation": "manual", "offset_minutes": 0},
            {"title": "Pack backpack", "confirmation": "manual", "offset_minutes": 5},
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-t1", now)
    t_id = t_res["id"]

    # Start routine for child
    start_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_id, "revision": t_res["revision"], "member": "child"},
        "start-1",
        now,
    )
    run_id = start_res["id"]
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    step0 = run["steps"][0]
    assert step0["status"] == "active"
    nonce0 = step0["nonce"]
    assert nonce0

    # Step 1 should still be pending because offset_minutes = 5
    assert run["steps"][1]["status"] == "pending"

    # Future step denial: attempting to confirm step 1 fails
    with pytest.raises(DomainError):
        await enabled_engine.execute(
            "child",
            "routines.confirm",
            {"id": run_id, "revision": run["revision"], "step": 1, "nonce": "invalid"},
            "confirm-future",
            now,
        )

    # Wrong actor: parent cannot confirm child's manual step
    with pytest.raises(DomainError):
        await enabled_engine.execute(
            "parent",
            "routines.confirm",
            {"id": run_id, "revision": run["revision"], "step": 0, "nonce": nonce0},
            "confirm-wrong-actor",
            now,
        )

    # Sibling cannot confirm child's step
    with pytest.raises(DomainError):
        await enabled_engine.execute(
            "sibling",
            "routines.confirm",
            {"id": run_id, "revision": run["revision"], "step": 0, "nonce": nonce0},
            "confirm-sibling",
            now,
        )

    # Wrong nonce check: DomainError raised
    with pytest.raises(DomainError):
        await enabled_engine.execute(
            "child",
            "routines.confirm",
            {"id": run_id, "revision": run["revision"], "step": 0, "nonce": "wrong-nonce"},
            "confirm-wrong-nonce",
            now,
        )

    # Correct nonce confirms step 0
    confirm0 = await enabled_engine.execute(
        "child",
        "routines.confirm",
        {"id": run_id, "revision": run["revision"], "step": 0, "nonce": nonce0},
        "confirm-step-0",
        now,
    )
    assert confirm0["steps"][0]["status"] == "completed"
    assert confirm0["steps"][1]["status"] == "pending"

    # Tick before offset (e.g. +3 min) does not activate step 1
    await enabled_engine.tick(now + timedelta(minutes=3))
    run_mid = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run_mid["steps"][1]["status"] == "pending"

    # Tick at +5 min activates step 1 with a new fresh nonce
    await enabled_engine.tick(now + timedelta(minutes=5))
    run_ready = enabled_engine.snapshot()["routine_runs"][run_id]
    step1 = run_ready["steps"][1]
    assert step1["status"] == "active"
    nonce1 = step1["nonce"]
    assert nonce1 and nonce1 != nonce0

    # Old nonce0 cannot confirm step 1
    with pytest.raises(DomainError):
        await enabled_engine.execute(
            "child",
            "routines.confirm",
            {"id": run_id, "revision": run_ready["revision"], "step": 1, "nonce": nonce0},
            "confirm-stale-nonce",
            now + timedelta(minutes=5),
        )

    # Confirm step 1 with nonce1 completes routine
    final_res = await enabled_engine.execute(
        "child",
        "routines.confirm",
        {"id": run_id, "revision": run_ready["revision"], "step": 1, "nonce": nonce1},
        "confirm-step-1",
        now + timedelta(minutes=5),
    )
    assert final_res["status"] == "completed"
    assert final_res["steps"][1]["status"] == "completed"


@pytest.mark.asyncio
async def test_stable_operation_replay_and_idempotency(enabled_engine, now):
    """Verify replay returns identical deepcopy results without re-executing."""
    t_payload = {
        "title": "Evening routine",
        "assignees": ["child"],
        "steps": [{"title": "Read book", "confirmation": "none", "offset_minutes": 0}],
    }
    res1 = await enabled_engine.execute("parent", "routines.save", t_payload, "op-idemp-1", now)
    res2 = await enabled_engine.execute("parent", "routines.save", t_payload, "op-idemp-1", now)
    assert res1 == res2

    # Attempting different payload with same operation_id raises idempotency_conflict
    diff_payload = {**t_payload, "title": "Different"}
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await enabled_engine.execute("parent", "routines.save", diff_payload, "op-idemp-1", now)


@pytest.mark.asyncio
async def test_one_active_run_per_template_and_member(enabled_engine, now):
    """Multiple starts for the same active routine return the existing active run."""
    t_payload = {
        "title": "Daily Chore",
        "assignees": ["child", "sibling"],
        "steps": [{"title": "Make bed", "confirmation": "manual", "offset_minutes": 0}],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-chore", now)
    t_id = t_res["id"]

    start_child_1 = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_id, "revision": t_res["revision"], "member": "child"},
        "start-child-1",
        now,
    )
    start_child_2 = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_id, "revision": t_res["revision"], "member": "child"},
        "start-child-2",
        now + timedelta(minutes=1),
    )
    assert start_child_1["id"] == start_child_2["id"]

    # Different member gets their own run
    start_sibling = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_id, "revision": t_res["revision"], "member": "sibling"},
        "start-sibling-1",
        now,
    )
    assert start_sibling["id"] != start_child_1["id"]


@pytest.mark.asyncio
async def test_offset_minutes_wait_advancement(enabled_engine, now):
    """Steps wait for planned_at + offset_minutes before activating."""
    t_payload = {
        "title": "Timed Steps",
        "assignees": ["child"],
        "steps": [
            {"title": "Step 0", "confirmation": "none", "offset_minutes": 0},
            {"title": "Step 1", "confirmation": "none", "offset_minutes": 10},
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-timed", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-timed",
        now,
    )
    run_id = run_res["id"]

    # Step 0 completes immediately because confirmation is none
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["steps"][0]["status"] == "completed"
    assert run["steps"][1]["status"] == "pending"
    assert run["status"] == "active"

    # Tick at +9 min: step 1 still pending
    assert not await enabled_engine.tick(now + timedelta(minutes=9))
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["steps"][1]["status"] == "pending"

    # Tick at +10 min: step 1 completes and routine finishes
    assert await enabled_engine.tick(now + timedelta(minutes=10))
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["steps"][1]["status"] == "completed"
    assert run["status"] == "completed"


@pytest.mark.asyncio
async def test_entity_observation_states_stale_unknown_and_approved_fresh(enabled_engine, now):
    """Entity observations: unknown, unavailable, stale, or negated unknown do not complete."""
    # Allowlist switch.test_device
    await enabled_engine.execute(
        "owner",
        "routines.configure",
        {"entity_allowlist": ["switch.test_device"], "revision": 0},
        "allow-dev",
        now,
    )

    t_payload = {
        "title": "Device Monitor",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Wait for device on",
                "confirmation": "entity_state",
                "completion_condition": {
                    "kind": "entity_state",
                    "entity_id": "switch.test_device",
                    "state": "on",
                    "max_age_seconds": 60,
                },
                "offset_minutes": 0,
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-obs", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-obs",
        now,
    )
    run_id = run_res["id"]

    # 1. State 'unknown' does not complete step
    obs_unknown = {"switch.test_device": {"state": "unknown", "observed_at": _iso(now)}}
    await enabled_engine.tick(now, routine_observations=obs_unknown)
    assert enabled_engine.snapshot()["routine_runs"][run_id]["steps"][0]["status"] == "active"

    # 2. State 'unavailable' does not complete step
    obs_unavail = {"switch.test_device": {"state": "unavailable", "observed_at": _iso(now)}}
    await enabled_engine.tick(now, routine_observations=obs_unavail)
    assert enabled_engine.snapshot()["routine_runs"][run_id]["steps"][0]["status"] == "active"

    # 3. Stale observation (> 60s max_age) does not complete step
    stale_time = now - timedelta(seconds=120)
    obs_stale = {"switch.test_device": {"state": "on", "observed_at": _iso(stale_time)}}
    await enabled_engine.tick(now, routine_observations=obs_stale)
    assert enabled_engine.snapshot()["routine_runs"][run_id]["steps"][0]["status"] == "active"

    # 4. Negated unknown step test
    t_neg = {
        "title": "Negated Monitor",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Wait not off",
                "confirmation": "entity_state",
                "completion_condition": {
                    "kind": "entity_state",
                    "entity_id": "switch.test_device",
                    "state": "off",
                    "negate": True,
                    "max_age_seconds": 60,
                },
                "offset_minutes": 0,
            }
        ],
    }
    t_neg_res = await enabled_engine.execute("parent", "routines.save", t_neg, "save-neg", now)
    run_neg_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_neg_res["id"], "revision": t_neg_res["revision"], "member": "child"},
        "start-neg",
        now,
    )
    neg_id = run_neg_res["id"]

    # Even with negate=True, unknown state yields None, not True
    await enabled_engine.tick(now, routine_observations=obs_unknown)
    assert enabled_engine.snapshot()["routine_runs"][neg_id]["steps"][0]["status"] == "active"

    # 5. Fresh matching observation completes step and routine
    obs_fresh = {"switch.test_device": {"state": "on", "observed_at": _iso(now)}}
    await enabled_engine.tick(now, routine_observations=obs_fresh)
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["steps"][0]["status"] == "completed"
    assert run["status"] == "completed"


@pytest.mark.asyncio
async def test_allowlist_owner_only_and_revocation_blocks_stale_cached_obs(enabled_engine, now):
    """Only owner can configure allowlist; revoking allowlist blocks cached observations."""
    # Parent attempts configure: forbidden
    with pytest.raises(DomainError, match="forbidden"):
        await enabled_engine.execute(
            "parent",
            "routines.configure",
            {"entity_allowlist": ["binary_sensor.door"], "revision": 0},
            "parent-cfg",
            now,
        )

    # Owner configures allowlist
    cfg1 = await enabled_engine.execute(
        "owner",
        "routines.configure",
        {"entity_allowlist": ["binary_sensor.door"], "revision": 0},
        "owner-cfg",
        now,
    )

    t_payload = {
        "title": "Door Watch",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Door opened",
                "confirmation": "entity_state",
                "completion_condition": {
                    "kind": "entity_state",
                    "entity_id": "binary_sensor.door",
                    "state": "on",
                },
                "offset_minutes": 0,
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-door", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-door",
        now,
    )
    run_id = run_res["id"]

    # Revoke binary_sensor.door from allowlist
    await enabled_engine.execute(
        "owner",
        "routines.configure",
        {"entity_allowlist": [], "revision": cfg1["revision"]},
        "revoke-cfg",
        now,
    )

    # Safe observation filter removes unallowed entity, preventing evaluation
    obs_fresh = {"binary_sensor.door": {"state": "on", "observed_at": _iso(now)}}
    await enabled_engine.tick(now, routine_observations=obs_fresh)
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["steps"][0]["status"] == "active"


@pytest.mark.asyncio
async def test_parent_override_and_cancel_with_reason(enabled_engine, now):
    """Parent can override step with outcome ('completed' or 'skipped') and cancel run."""
    t_payload = {
        "title": "Manual Tasks",
        "assignees": ["child"],
        "steps": [
            {"title": "Step 1", "confirmation": "manual", "offset_minutes": 0},
            {"title": "Step 2", "confirmation": "manual", "offset_minutes": 0},
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-ovr", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-ovr",
        now,
    )
    run_id = run_res["id"]

    # Child cannot override
    with pytest.raises(DomainError, match="forbidden"):
        await enabled_engine.execute(
            "child",
            "routines.override",
            {
                "id": run_id,
                "revision": run_res["revision"],
                "step": 0,
                "outcome": "skipped",
                "reason": "excused",
            },
            "child-ovr",
            now,
        )

    # Parent overrides step 0 to skipped
    ovr_res = await enabled_engine.execute(
        "parent",
        "routines.override",
        {
            "id": run_id,
            "revision": run_res["revision"],
            "step": 0,
            "outcome": "skipped",
            "reason": "parent excused",
        },
        "parent-ovr",
        now,
    )
    assert ovr_res["steps"][0]["status"] == "skipped"
    # Step 1 immediately activated
    assert ovr_res["steps"][1]["status"] == "active"

    # Parent cancels the entire run
    cancel_res = await enabled_engine.execute(
        "parent",
        "routines.cancel",
        {"id": run_id, "revision": ovr_res["revision"], "reason": "plans changed"},
        "cancel-run",
        now,
    )
    assert cancel_res["status"] == "cancelled"
    history = cancel_res["history"]
    assert any(h["action"] == "cancelled" and h["reason"] == "plans changed" for h in history)


@pytest.mark.asyncio
async def test_parent_modes_skip_when_holidays(enabled_engine, now):
    """Setting mode to holidays skips template condition when configured."""
    # Set mode to holidays
    await enabled_engine.execute(
        "parent",
        "routines.modes",
        {"modes": ["holidays"], "revision": 0},
        "mode-holidays",
        now,
    )

    t_payload = {
        "title": "School Routine",
        "assignees": ["child"],
        "skip_when": {"kind": "mode", "mode": "holidays"},
        "steps": [{"title": "Wake up early", "confirmation": "none", "offset_minutes": 0}],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-school", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-school",
        now,
    )
    assert run_res["status"] == "skipped"
    assert run_res["steps"][0]["status"] == "skipped"


@pytest.mark.asyncio
async def test_recurring_recurrence_dedup_survives_mode_changes_and_restarts(
    enabled_engine, store, now
):
    """Recurring recurrence triggers once per date; skipped start persists after mode normal."""
    # Set initial mode to holidays
    await enabled_engine.execute(
        "parent",
        "routines.modes",
        {"modes": ["holidays"], "revision": 0},
        "init-holiday-mode",
        now,
    )

    t_payload = {
        "title": "Daily Recurrence",
        "assignees": ["child"],
        "skip_when": {"kind": "mode", "mode": "holidays"},
        "rule": {
            "frequency": "daily",
            "start_date": now.date().isoformat(),
            "time": now.strftime("%H:%M"),
            "timezone": "UTC",
        },
        "steps": [{"title": "Brush teeth", "confirmation": "none", "offset_minutes": 0}],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-recur", now)
    t_id = t_res["id"]

    # First tick triggers recurrence during holiday mode: run starts and immediately skips
    assert await enabled_engine.tick(now)
    snapshot = enabled_engine.snapshot()
    template = snapshot["routines"][t_id]
    today = now.date().isoformat()
    assert today in template["occurrences"]
    runs = [r for r in snapshot["routine_runs"].values() if r["template_id"] == t_id]
    assert len(runs) == 1
    assert runs[0]["status"] == "skipped"

    # Restart engine from persistent store
    restarted = Engine(deepcopy(store.value), store.save)

    # Change modes back to normal on restarted engine
    await restarted.execute(
        "parent",
        "routines.modes",
        {"modes": ["normal"], "revision": 1},
        "mode-back-normal",
        now + timedelta(minutes=30),
    )

    # Tick again on the same day: occurrence dedup ensures skipped run remains and no restart
    await restarted.tick(now + timedelta(hours=2))
    snapshot2 = restarted.snapshot()
    runs2 = [r for r in snapshot2["routine_runs"].values() if r["template_id"] == t_id]
    assert len(runs2) == 1
    assert runs2[0]["status"] == "skipped"


@pytest.mark.asyncio
async def test_template_edits_preserve_existing_runs_history_and_steps(enabled_engine, now):
    """Editing template preserves existing run steps, status, and history."""
    t_payload = {
        "title": "Version 1",
        "assignees": ["child"],
        "steps": [{"title": "Old Step", "confirmation": "manual", "offset_minutes": 0}],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-v1", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-v1",
        now,
    )
    run_id = run_res["id"]

    # Edit template to Version 2 with completely different step
    t_v2 = {
        "id": t_res["id"],
        "revision": t_res["revision"],
        "title": "Version 2",
        "assignees": ["child"],
        "steps": [{"title": "New Step", "confirmation": "none", "offset_minutes": 0}],
    }
    await enabled_engine.execute(
        "parent", "routines.save", t_v2, "save-v2", now + timedelta(minutes=1)
    )

    # Existing run is unaffected: title, steps, and history remain intact
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["title"] == "Version 1"
    assert run["steps"][0]["title"] == "Old Step"
    assert run["steps"][0]["status"] == "active"


@pytest.mark.asyncio
async def test_overdue_step_escalation_revision_and_incident_lifecycle(enabled_engine, now):
    """Overdue steps preserve the button revision and close announced alerts."""
    t_payload = {
        "title": "Homework",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Maths",
                "confirmation": "manual",
                "offset_minutes": 0,
                "escalate_minutes": 15,
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-hw", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-hw",
        now,
    )
    run_id = run_res["id"]
    initial_run_rev = run_res["revision"]
    step0 = enabled_engine.snapshot()["routine_runs"][run_id]["steps"][0]
    nonce = step0["nonce"]

    # Tick at +14 min: not yet overdue
    await enabled_engine.tick(now + timedelta(minutes=14))
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert "escalated_at" not in run["steps"][0]
    assert run["revision"] == initial_run_rev

    # Tick at +15 min: overdue triggers incident in outbox, run revision stays intact
    await enabled_engine.tick(now + timedelta(minutes=15))
    snapshot = enabled_engine.snapshot()
    run = snapshot["routine_runs"][run_id]
    assert run["steps"][0].get("escalated_at") is not None
    assert run["revision"] == initial_run_rev

    # Check incident opened
    incidents = snapshot["incidents"]
    incident_id = f"routine:{run_id}:0"
    assert incident_id in incidents
    assert incidents[incident_id]["state"] == "open"
    event_id = incidents[incident_id]["event_id"]
    assert event_id in snapshot["outbox"]
    assert snapshot["outbox"][event_id]["recipient"] == "parents"

    # Announced incident: deliveries marked sent -> completion produces paired closure
    await enabled_engine.system_update(
        "mock_delivery",
        now + timedelta(minutes=16),
        lambda ctx: ctx.state["outbox"][event_id].update(
            state="sent", deliveries={"deliv1": {"state": "sent"}}
        ),
    )

    # Confirm step with original revision and nonce
    await enabled_engine.execute(
        "child",
        "routines.confirm",
        {"id": run_id, "revision": initial_run_rev, "step": 0, "nonce": nonce},
        "confirm-hw",
        now + timedelta(minutes=17),
    )

    closed_snapshot = enabled_engine.snapshot()
    assert closed_snapshot["incidents"][incident_id]["state"] == "closed"
    closure_event_id = closed_snapshot["incidents"][incident_id].get("closure_event_id")
    assert closure_event_id is not None
    assert closure_event_id in closed_snapshot["outbox"]
    assert closed_snapshot["outbox"][closure_event_id]["key"] == "routine_closed"


@pytest.mark.asyncio
async def test_unsent_alert_supersession_on_cancellation(enabled_engine, now):
    """Unsent routine_step alerts and unannounced incidents are superseded upon cancellation."""
    t_payload = {
        "title": "Clean room",
        "assignees": ["child"],
        "steps": [{"title": "Tidy desk", "confirmation": "manual", "offset_minutes": 0}],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-clean", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-clean",
        now,
    )
    run_id = run_res["id"]

    # Step activation produced a routine_step outbox event in pending state
    outbox = enabled_engine.snapshot()["outbox"]
    step_events = [
        e
        for e in outbox.values()
        if e["key"] == "routine_step" and e["data"].get("run_id") == run_id
    ]
    assert len(step_events) == 1
    assert step_events[0]["state"] == "pending"

    # Cancel the run
    await enabled_engine.execute(
        "parent",
        "routines.cancel",
        {"id": run_id, "revision": run_res["revision"], "reason": "not needed"},
        "cancel-clean",
        now,
    )

    outbox_after = enabled_engine.snapshot()["outbox"]
    cancelled_step_event = outbox_after[step_events[0]["id"]]
    assert cancelled_step_event["state"] == "superseded"


@pytest.mark.asyncio
async def test_disabled_module_and_member_revocation_cancels_active_runs(enabled_engine, now):
    """Disabling module or deactivating member/creator cancels active runs immediately."""
    t_payload = {
        "title": "Routine 1",
        "assignees": ["child", "sibling"],
        "steps": [{"title": "Step", "confirmation": "manual", "offset_minutes": 0}],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-mod-dis", now)
    run_res = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-mod-dis",
        now,
    )
    run_id = run_res["id"]

    # Deactivate child member via members.save
    await enabled_engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": enabled_engine.snapshot()["members"]["child"]["revision"],
            "name": "Child",
            "role": "child",
            "active": False,
        },
        "deact-child",
        now,
    )

    # Tick triggers cancel_disabled
    await enabled_engine.tick(now + timedelta(seconds=1))
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["status"] == "cancelled"
    assert any(
        h["action"] == "cancelled" and h["reason"] == "authorization_removed"
        for h in run["history"]
    )

    # Test immediate cancellation when disabling routines module via settings.save
    run_sibling = await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "sibling"},
        "start-sib-dis",
        now + timedelta(seconds=2),
    )
    sib_run_id = run_sibling["id"]
    assert enabled_engine.snapshot()["routine_runs"][sib_run_id]["status"] == "active"

    # Disable routines module via settings.save
    current_settings = enabled_engine.snapshot()["settings"]
    new_modules = [m for m in current_settings["modules"] if m != "routines"]
    await enabled_engine.execute(
        "owner",
        "settings.save",
        {
            "name": current_settings["name"],
            "language": current_settings["language"],
            "modules": new_modules,
        },
        "disable-routines-module",
        now + timedelta(seconds=3),
    )

    # Engine execute automatically runs cancel_disabled on every transaction
    run2 = enabled_engine.snapshot()["routine_runs"][sib_run_id]
    assert run2["status"] == "cancelled"
    assert any(
        h["action"] == "cancelled" and h["reason"] == "authorization_removed"
        for h in run2["history"]
    )


@pytest.mark.asyncio
async def test_store_failure_atomicity_and_concurrent_duplicate_handling(
    enabled_engine, store, now
):
    """Store failure leaves state unchanged; concurrent duplicates are serialized safely."""
    t_payload = {
        "title": "Atomic Test",
        "assignees": ["child"],
        "steps": [{"title": "Step", "confirmation": "none", "offset_minutes": 0}],
    }
    before = enabled_engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await enabled_engine.execute("parent", "routines.save", t_payload, "fail-op", now)
    assert enabled_engine.snapshot() == before

    store.fail = False
    # Concurrent calls with identical operation_id
    results = await asyncio.gather(
        *[
            enabled_engine.execute("parent", "routines.save", t_payload, "concurrent-op", now)
            for _ in range(10)
        ]
    )
    assert all(r["id"] == results[0]["id"] for r in results)
    assert len(enabled_engine.snapshot()["routines"]) == 1


@pytest.mark.asyncio
async def test_privacy_boundaries_sibling_and_guest(enabled_engine, now):
    """Guests are rejected; siblings only see their assigned templates and runs."""
    # Allowlist switch
    await enabled_engine.execute(
        "owner",
        "routines.configure",
        {"entity_allowlist": ["switch.door"], "revision": 0},
        "cfg-privacy",
        now,
    )

    t_payload = {
        "title": "Sibling Task",
        "assignees": ["sibling"],
        "steps": [
            {
                "title": "Step",
                "confirmation": "entity_state",
                "completion_condition": {
                    "kind": "entity_state",
                    "entity_id": "switch.door",
                    "state": "on",
                },
                "offset_minutes": 0,
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-priv", now)
    await enabled_engine.execute(
        "parent",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "sibling"},
        "start-priv",
        now,
    )

    # Guest cannot view routines projection
    guest_view = enabled_engine.view("guest")
    assert "routines" not in guest_view

    # Guest cannot execute any routine command
    with pytest.raises(DomainError, match="forbidden"):
        await enabled_engine.execute(
            "guest",
            "routines.start",
            {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
            "guest-cmd",
            now,
        )

    # Child (not assignee) cannot see sibling's template or run
    child_view = enabled_engine.view("child")
    assert len(child_view["routines"]["templates"]) == 0
    assert len(child_view["routines"]["runs"]) == 0
    assert "entity_allowlist" not in child_view["routines"]["config"]

    # Sibling sees their assigned template and run, but conditions and allowlist are redacted
    sibling_view = enabled_engine.view("sibling")
    assert len(sibling_view["routines"]["templates"]) == 1
    assert "entity_allowlist" not in sibling_view["routines"]["config"]
    run_proj = sibling_view["routines"]["runs"][0]
    assert "completion_condition" not in run_proj["steps"][0]

    # Parent view retains full conditions and entity_allowlist
    parent_view = enabled_engine.view("parent")
    assert "entity_allowlist" in parent_view["routines"]["config"]
    assert "completion_condition" in parent_view["routines"]["runs"][0]["steps"][0]
