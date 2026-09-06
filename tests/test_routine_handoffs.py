"""Tests for routine handoffs, per-step assignees, authority, and privacy."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def enabled_engine(engine, store):
    snapshot = engine.snapshot()
    if "routines" not in snapshot["settings"]["modules"]:
        snapshot["settings"]["modules"].append("routines")
    return Engine(snapshot, store.save)


@pytest.mark.asyncio
async def test_step_assignee_validation_via_engine_commands(enabled_engine, now):
    """Parent cannot save template with guest, inactive, unknown, or non-string step assignee."""
    base_steps = [{"title": "Brush teeth", "confirmation": "manual", "offset_minutes": 0}]

    # Unknown member in step assignee
    with pytest.raises(DomainError) as exc_info:
        await enabled_engine.execute(
            "parent",
            "routines.save",
            {
                "title": "Invalid Step Assignee",
                "assignees": ["child"],
                "steps": [{**base_steps[0], "assignee": "unknown_user"}],
            },
            "save-unknown-assignee",
            now,
        )
    assert exc_info.value.code in {"unknown_member", "invalid_field"}

    # Inactive member in step assignee
    await enabled_engine.execute(
        "owner",
        "members.save",
        {"id": "inactive_child", "name": "Inactive Child", "role": "child", "active": False},
        "add-inactive-child",
        now,
    )
    with pytest.raises(DomainError) as exc_info:
        await enabled_engine.execute(
            "parent",
            "routines.save",
            {
                "title": "Invalid Inactive Assignee",
                "assignees": ["child"],
                "steps": [{**base_steps[0], "assignee": "inactive_child"}],
            },
            "save-inactive-assignee",
            now,
        )
    assert exc_info.value.code in {"unknown_member", "invalid_field"}

    # Guest role in step assignee
    with pytest.raises(DomainError) as exc_info:
        await enabled_engine.execute(
            "parent",
            "routines.save",
            {
                "title": "Invalid Guest Assignee",
                "assignees": ["child"],
                "steps": [{**base_steps[0], "assignee": "guest"}],
            },
            "save-guest-assignee",
            now,
        )
    assert exc_info.value.code in {"unknown_member", "invalid_field"}

    # Non-string step assignee (e.g. integer or list)
    with pytest.raises(DomainError) as exc_info:
        await enabled_engine.execute(
            "parent",
            "routines.save",
            {
                "title": "Invalid Type Assignee",
                "assignees": ["child"],
                "steps": [{**base_steps[0], "assignee": 123}],
            },
            "save-int-assignee",
            now,
        )
    assert exc_info.value.code == "invalid_field"

    # Valid step assignee not in template.assignees is allowed
    # (e.g. parent assigns child run with parent step)
    saved = await enabled_engine.execute(
        "parent",
        "routines.save",
        {
            "title": "Child Run Parent Step",
            "assignees": ["child"],
            "steps": [
                {"title": "Child task", "confirmation": "manual", "offset_minutes": 0},
                {
                    "title": "Parent task",
                    "confirmation": "manual",
                    "offset_minutes": 5,
                    "assignee": "parent",
                },
            ],
        },
        "save-valid-handoff",
        now,
    )
    assert saved["steps"][0].get("assignee") is None
    assert saved["steps"][1].get("assignee") == "parent"


@pytest.mark.asyncio
async def test_run_steps_snapshot_effective_member_and_fallback(enabled_engine, now):
    """Run steps snapshot effective member per step; fallback to run member when None/missing."""
    t_payload = {
        "title": "Morning Prep with Parent Handoff",
        "assignees": ["child"],
        "steps": [
            {"title": "Brush teeth", "confirmation": "manual", "offset_minutes": 0},
            {
                "title": "Sign permission slip",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "parent",
            },
            {
                "title": "Tidy desk",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": None,
            },
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-t-snap", now)
    start_res = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-child-run",
        now,
    )
    run_id = start_res["id"]
    snapshot = enabled_engine.snapshot()
    run = snapshot["routine_runs"][run_id]

    assert run["steps"][0]["member"] == "child"
    assert run["steps"][1]["member"] == "parent"
    assert run["steps"][2]["member"] == "child"


@pytest.mark.asyncio
async def test_confirmation_authority_effective_actor_only_and_parent_override(enabled_engine, now):
    """Only the effective actor can confirm; parents must use a reasoned override."""
    t_payload = {
        "title": "Handoff Routine",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Parent Sign",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "parent",
            },
            {
                "title": "Child Pack",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "child",
            },
        ],
    }
    t_res = await enabled_engine.execute(
        "parent", "routines.save", t_payload, "save-t-authority", now
    )
    start_res = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-run-auth",
        now,
    )
    run_id = start_res["id"]
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    step0_nonce = run["steps"][0]["nonce"]
    step0_rev = run["revision"]

    # Child (run member) cannot confirm step 0 assigned to parent
    with pytest.raises(DomainError, match="forbidden"):
        await enabled_engine.execute(
            "child",
            "routines.confirm",
            {"id": run_id, "revision": step0_rev, "step": 0, "nonce": step0_nonce},
            "child-confirm-parent-step",
            now,
        )

    # Sibling cannot confirm step 0 assigned to parent
    with pytest.raises(DomainError, match="forbidden"):
        await enabled_engine.execute(
            "sibling",
            "routines.confirm",
            {"id": run_id, "revision": step0_rev, "step": 0, "nonce": step0_nonce},
            "sibling-confirm-parent-step",
            now,
        )

    # Adult (nonguest nonparent nonactor) cannot confirm step 0
    with pytest.raises(DomainError, match="forbidden"):
        await enabled_engine.execute(
            "adult",
            "routines.confirm",
            {"id": run_id, "revision": step0_rev, "step": 0, "nonce": step0_nonce},
            "adult-confirm-parent-step",
            now,
        )

    # Parent has reasoned override capability
    override_res = await enabled_engine.execute(
        "parent",
        "routines.override",
        {
            "id": run_id,
            "revision": step0_rev,
            "step": 0,
            "outcome": "completed",
            "reason": "Signed manually on paper",
        },
        "parent-override-step0",
        now,
    )
    assert override_res["steps"][0]["status"] == "completed"

    # Step 1 is now active for child
    run_after = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run_after["steps"][1]["status"] == "active"
    step1_nonce = run_after["steps"][1]["nonce"]
    step1_rev = run_after["revision"]

    # Parent cannot confirm child's manual step via routines.confirm (must use override)
    with pytest.raises(DomainError, match="forbidden"):
        await enabled_engine.execute(
            "parent",
            "routines.confirm",
            {"id": run_id, "revision": step1_rev, "step": 1, "nonce": step1_nonce},
            "parent-confirm-child-step",
            now,
        )

    # Child confirms their own step
    child_confirm = await enabled_engine.execute(
        "child",
        "routines.confirm",
        {"id": run_id, "revision": step1_rev, "step": 1, "nonce": step1_nonce},
        "child-confirm-step1",
        now,
    )
    assert child_confirm["steps"][1]["status"] == "completed"
    assert child_confirm["status"] == "completed"


@pytest.mark.asyncio
async def test_activation_notice_privately_sent_to_effective_actor(enabled_engine, now):
    """Send activation notice privately to the effective actor."""
    t_payload = {
        "title": "Handoff Notice Test",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Parent Step 0",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "parent",
            },
            {
                "title": "Child Step 1",
                "confirmation": "manual",
                "offset_minutes": 5,
                "assignee": "child",
            },
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-notice-t", now)
    start_res = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-notice-run",
        now,
    )
    run_id = start_res["id"]

    # The step event must be addressed to the effective actor.
    outbox = enabled_engine.snapshot()["outbox"]
    step0_events = [
        e
        for e in outbox.values()
        if e["key"] == "routine_step"
        and e["data"].get("run_id") == run_id
        and e["data"].get("step") == 0
    ]
    assert len(step0_events) == 1
    assert step0_events[0]["recipient"] == "parent"
    assert step0_events[0]["data"]["member"] == "parent"

    # Parent confirms step 0
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    await enabled_engine.execute(
        "parent",
        "routines.confirm",
        {
            "id": run_id,
            "revision": run["revision"],
            "step": 0,
            "nonce": run["steps"][0]["nonce"],
        },
        "parent-conf-s0",
        now,
    )

    # Advance time by 5 minutes for step 1
    await enabled_engine.tick(now + timedelta(minutes=5))

    outbox_after = enabled_engine.snapshot()["outbox"]
    step1_events = [
        e
        for e in outbox_after.values()
        if e["key"] == "routine_step"
        and e["data"].get("run_id") == run_id
        and e["data"].get("step") == 1
    ]
    assert len(step1_events) == 1
    assert step1_events[0]["recipient"] == "child"
    assert step1_events[0]["data"]["member"] == "child"


@pytest.mark.asyncio
async def test_completed_notification_only_to_original_run_member(enabled_engine, now):
    """Send completion only to the original run member after a handoff."""
    t_payload = {
        "title": "Handoff Completion",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Parent task",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "parent",
            }
        ],
    }
    t_res = await enabled_engine.execute(
        "parent", "routines.save", t_payload, "save-completion-t", now
    )
    start_res = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-completion-run",
        now,
    )
    run_id = start_res["id"]
    run = enabled_engine.snapshot()["routine_runs"][run_id]

    # Parent confirms the only step
    await enabled_engine.execute(
        "parent",
        "routines.confirm",
        {
            "id": run_id,
            "revision": run["revision"],
            "step": 0,
            "nonce": run["steps"][0]["nonce"],
        },
        "conf-completion-step",
        now,
    )

    outbox = enabled_engine.snapshot()["outbox"]
    comp_events = [
        e
        for e in outbox.values()
        if e["key"] == "routine_completed" and e["data"].get("run_id") == run_id
    ]
    assert len(comp_events) == 1
    # Addressed to the original run member (child), not parent
    assert comp_events[0]["recipient"] == "child"


@pytest.mark.asyncio
async def test_visibility_and_privacy_redactions(enabled_engine, now):
    """Runs visible to run member + explicit step actors + parents, not siblings.
    Non-parent view and routines.start return redacts other actors' nonce and conditions,
    while own current nonce is visible.
    """
    # Allowlist sensor for completion/skip condition
    await enabled_engine.execute(
        "owner",
        "routines.configure",
        {"entity_allowlist": ["binary_sensor.front_door"], "revision": 0},
        "cfg-allowlist",
        now,
    )

    t_payload = {
        "title": "Privacy Routine",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Child step",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "child",
                "skip_when": {
                    "kind": "entity_state",
                    "entity_id": "binary_sensor.front_door",
                    "state": "on",
                },
            },
            {
                "title": "Adult step",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "adult",
                "skip_when": {
                    "kind": "entity_state",
                    "entity_id": "binary_sensor.front_door",
                    "state": "off",
                },
            },
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-priv-t", now)

    # Start routine by child actor
    start_res = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-priv-run",
        now,
    )
    run_id = start_res["id"]

    # routines.start returns redacted public run for the calling child actor
    # Child's own step has nonce visible, but conditions are redacted
    assert "nonce" in start_res["steps"][0]
    assert "skip_when" not in start_res["steps"][0]
    # Adult's step (other actor) has nonce redacted and conditions redacted
    assert "nonce" not in start_res["steps"][1]
    assert "skip_when" not in start_res["steps"][1]

    # Child view
    child_view = enabled_engine.view("child")
    child_runs = [r for r in child_view["routines"]["runs"] if r["id"] == run_id]
    assert len(child_runs) == 1
    c_run = child_runs[0]
    assert "nonce" in c_run["steps"][0]
    assert "skip_when" not in c_run["steps"][0]
    assert "nonce" not in c_run["steps"][1]
    assert "skip_when" not in c_run["steps"][1]

    # Adult view (explicit step actor, not run member, not parent)
    adult_view = enabled_engine.view("adult")
    adult_runs = [r for r in adult_view["routines"]["runs"] if r["id"] == run_id]
    assert len(adult_runs) == 1
    a_run = adult_runs[0]
    assert "nonce" not in a_run["steps"][0]  # Child's nonce redacted for adult
    assert "skip_when" not in a_run["steps"][0]
    # The adult owns step 1, but it has no nonce until it becomes active.
    assert a_run["steps"][1]["status"] == "pending"
    assert "nonce" not in a_run["steps"][1]
    assert "skip_when" not in a_run["steps"][1]

    # Sibling view (not run member, not step actor, not parent)
    sibling_view = enabled_engine.view("sibling")
    sibling_runs = [r for r in sibling_view["routines"]["runs"] if r["id"] == run_id]
    assert len(sibling_runs) == 0  # Sibling cannot see this run!

    # Parent view retains conditions and every nonce that currently exists.
    parent_view = enabled_engine.view("parent")
    parent_runs = [r for r in parent_view["routines"]["runs"] if r["id"] == run_id]
    assert len(parent_runs) == 1
    p_run = parent_runs[0]
    assert "skip_when" in p_run["steps"][0]
    assert "skip_when" in p_run["steps"][1]
    assert "nonce" in p_run["steps"][0]
    assert "nonce" not in p_run["steps"][1]

    # Completing step 0 activates step 1 and creates its nonce at that point.
    await enabled_engine.execute(
        "child",
        "routines.confirm",
        {
            "id": run_id,
            "revision": c_run["revision"],
            "step": 0,
            "nonce": c_run["steps"][0]["nonce"],
        },
        "confirm-privacy-step-0",
        now,
    )
    child_after = enabled_engine.view("child")["routines"]["runs"][0]
    adult_after = enabled_engine.view("adult")["routines"]["runs"][0]
    parent_after = enabled_engine.view("parent")["routines"]["runs"][0]
    assert adult_after["steps"][1]["status"] == "active"
    assert "nonce" not in child_after["steps"][1]
    assert "nonce" in adult_after["steps"][1]
    assert "nonce" in parent_after["steps"][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "member_update",
    [
        {"role": "adult", "active": False},
        {"role": "guest", "active": True},
    ],
    ids=["inactive", "guest"],
)
async def test_revoking_step_participant_cancels_run_and_removes_nonces(
    enabled_engine, now, member_update
):
    """Deactivating or guest-demoting a step participant cancels the run."""
    t_payload = {
        "title": "Participant Revocation Test",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Adult task",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "adult",
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-rev-t", now)
    start_res = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-rev-run",
        now,
    )
    run_id = start_res["id"]
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["status"] == "active"
    assert "nonce" in run["steps"][0]

    # Revoke the step participant by deactivation or a role change to guest.
    await enabled_engine.execute(
        "owner",
        "members.save",
        {"id": "adult", "name": "Adult", **member_update},
        f"revoke-adult-{member_update['role']}-{member_update['active']}",
        now,
    )

    # Every transaction runs the authorization cancellation pass.
    run_after = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run_after["status"] == "cancelled"
    assert "nonce" not in run_after["steps"][0]
    assert any(
        h["action"] == "cancelled" and h["reason"] == "authorization_removed"
        for h in run_after["history"]
    )


@pytest.mark.asyncio
async def test_old_persisted_run_steps_without_member_inherit_run_member(
    enabled_engine, store, now
):
    """Keep pre-handoff persisted runs usable when steps lack a member field."""
    template = await enabled_engine.execute(
        "parent",
        "routines.save",
        {
            "title": "Legacy persisted run",
            "assignees": ["child"],
            "steps": [
                {
                    "title": "Legacy step",
                    "confirmation": "manual",
                    "offset_minutes": 0,
                }
            ],
        },
        "save-legacy-run-template",
        now,
    )
    started = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": template["id"], "revision": template["revision"], "member": "child"},
        "start-legacy-run",
        now,
    )

    persisted = enabled_engine.snapshot()
    persisted_step = persisted["routine_runs"][started["id"]]["steps"][0]
    persisted_step.pop("member")
    persisted_step.pop("assignee", None)
    legacy_engine = Engine(persisted, store.save)

    child_run = legacy_engine.view("child")["routines"]["runs"][0]
    assert child_run["steps"][0]["nonce"] == persisted_step["nonce"]
    assert legacy_engine.view("adult")["routines"]["runs"] == []

    confirmed = await legacy_engine.execute(
        "child",
        "routines.confirm",
        {
            "id": started["id"],
            "revision": child_run["revision"],
            "step": 0,
            "nonce": child_run["steps"][0]["nonce"],
        },
        "confirm-legacy-run",
        now,
    )
    assert confirmed["status"] == "completed"


@pytest.mark.asyncio
async def test_template_assignees_edit_does_not_rewrite_active_run(enabled_engine, now):
    """Edits to template assignees or steps do not rewrite already-active run."""
    t_payload = {
        "title": "Immutable Active Run",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Step 1",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "adult",
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-imm-t", now)
    run_res = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-imm-run",
        now,
    )
    run_id = run_res["id"]

    # Re-save template with different assignees and different step assignee
    await enabled_engine.execute(
        "parent",
        "routines.save",
        {
            "id": t_res["id"],
            "revision": t_res["revision"],
            "title": "Immutable Active Run Modified",
            "assignees": ["sibling"],
            "steps": [
                {
                    "title": "Step 1 Modified",
                    "confirmation": "manual",
                    "offset_minutes": 0,
                    "assignee": "parent",
                }
            ],
        },
        "save-imm-t-edit",
        now + timedelta(minutes=1),
    )

    # Active run retains original member, title, step assignee, and active status
    run = enabled_engine.snapshot()["routine_runs"][run_id]
    assert run["member"] == "child"
    assert run["title"] == "Immutable Active Run"
    assert run["steps"][0]["member"] == "adult"
    assert run["status"] == "active"


@pytest.mark.asyncio
async def test_scheduler_does_not_start_invalid_participant_templates(enabled_engine, now):
    """Scheduler does not start templates whose step participants are invalid/inactive/guests."""
    # Create template with adult as step assignee
    t_payload = {
        "title": "Scheduled Handoff Routine",
        "assignees": ["child"],
        "rule": {
            "frequency": "daily",
            "start_date": now.date().isoformat(),
            "time": now.strftime("%H:%M"),
            "timezone": "UTC",
        },
        "steps": [
            {
                "title": "Adult task",
                "confirmation": "none",
                "offset_minutes": 0,
                "assignee": "adult",
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-sched-t", now)
    t_id = t_res["id"]

    # Deactivate adult before scheduled trigger
    await enabled_engine.execute(
        "owner",
        "members.save",
        {"id": "adult", "name": "Adult", "role": "adult", "active": False},
        "deact-sched-adult",
        now,
    )

    # Tick at scheduled time: scheduler checks _steps_usable and skips starting
    await enabled_engine.tick(now)
    snapshot = enabled_engine.snapshot()
    today = now.date().isoformat()
    template = snapshot["routines"][t_id]
    # Occurrence should not have been created because template was not usable
    assert today not in template["occurrences"]
    runs = [r for r in snapshot["routine_runs"].values() if r["template_id"] == t_id]
    assert len(runs) == 0


@pytest.mark.asyncio
async def test_no_change_to_independent_alarm_state(enabled_engine, now):
    """Routine handoffs do not mutate a real active alarm challenge."""
    await enabled_engine.execute(
        "owner",
        "alarms.save",
        {
            "member": "child",
            "time": now.strftime("%H:%M"),
            "days": list(range(7)),
            "timezone": "UTC",
            "profile": "strict",
        },
        "save-independent-alarm",
        now,
    )
    await enabled_engine.tick(now)
    alarm_before = enabled_engine.snapshot()
    active_alarm = next(iter(alarm_before["alarm_runs"].values()))
    assert active_alarm["stage"] == "first"
    assert active_alarm["siren_desired"] is True
    assert active_alarm["challenge"]["nonce"]

    t_payload = {
        "title": "Handoff Independent Alarm",
        "assignees": ["child"],
        "steps": [
            {
                "title": "Parent task",
                "confirmation": "manual",
                "offset_minutes": 0,
                "assignee": "parent",
            }
        ],
    }
    t_res = await enabled_engine.execute("parent", "routines.save", t_payload, "save-alarm-t", now)
    started = await enabled_engine.execute(
        "child",
        "routines.start",
        {"id": t_res["id"], "revision": t_res["revision"], "member": "child"},
        "start-alarm-run",
        now,
    )
    routine = enabled_engine.snapshot()["routine_runs"][started["id"]]
    await enabled_engine.execute(
        "parent",
        "routines.confirm",
        {
            "id": routine["id"],
            "revision": routine["revision"],
            "step": 0,
            "nonce": routine["steps"][0]["nonce"],
        },
        "confirm-routine-with-active-alarm",
        now,
    )

    snapshot_after = enabled_engine.snapshot()
    assert snapshot_after["alarms"] == alarm_before["alarms"]
    assert snapshot_after["alarm_runs"] == alarm_before["alarm_runs"]
