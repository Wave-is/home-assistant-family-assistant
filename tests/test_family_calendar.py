"""Family calendar domain tests: save, approve, cancel, archive, and configure."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.family_calendar import published
from custom_components.family_assistant.domain.validation import DomainError


async def enable_calendar(engine, now):
    """Enable calendar module via settings.save with complete current allowed settings keys."""
    settings_payload = {
        "name": "Example household",
        "language": "en",
        "modules": ["shopping", "tasks", "alarms", "court", "calendar"],
        "automatic_penalties": False,
        "daily_penalty_cap": 1,
        "timezone": "UTC",
    }
    return await engine.execute("owner", "settings.save", settings_payload, "enable-calendar", now)


@pytest.fixture
async def calendar_engine(engine, now):
    await enable_calendar(engine, now)
    return engine


@pytest.mark.asyncio
async def test_child_tentative_parent_approval_edits_require_new_approval(calendar_engine, now):
    child_event = await calendar_engine.execute(
        "child",
        "calendar.save",
        {
            "title": "Child Tentative Event",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
        },
        "save-child",
        now,
    )
    assert child_event["status"] == "tentative"
    assert child_event["approved_by"] is None
    assert child_event["creator"] == "child"
    assert child_event["revision"] == 1

    # Child cannot approve
    with pytest.raises(DomainError, match="forbidden"):
        await calendar_engine.execute(
            "child",
            "calendar.approve",
            {
                "id": child_event["id"],
                "revision": child_event["revision"],
                "reason": "Self approve",
            },
            "child-approve",
            now,
        )

    # Parent approves
    approved = await calendar_engine.execute(
        "parent",
        "calendar.approve",
        {"id": child_event["id"], "revision": child_event["revision"], "reason": "Parent approved"},
        "parent-approve",
        now,
    )
    assert approved["status"] == "confirmed"
    assert approved["approved_by"] == "parent"
    assert approved["revision"] == 2

    # Cannot approve already confirmed
    with pytest.raises(DomainError, match="invalid_transition"):
        await calendar_engine.execute(
            "parent",
            "calendar.approve",
            {"id": approved["id"], "revision": approved["revision"], "reason": "Re-approve"},
            "parent-re-approve",
            now,
        )

    # Child edits event -> status returns to tentative, approved_by cleared, revision increments
    edited = await calendar_engine.execute(
        "child",
        "calendar.save",
        {
            "id": approved["id"],
            "revision": approved["revision"],
            "title": "Child Tentative Event (Updated)",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:30:00Z",
        },
        "child-edit",
        now,
    )
    assert edited["status"] == "tentative"
    assert edited["approved_by"] is None
    assert edited["title"] == "Child Tentative Event (Updated)"
    assert edited["revision"] == 3

    # Parent approves again
    reapproved = await calendar_engine.execute(
        "owner",
        "calendar.approve",
        {"id": edited["id"], "revision": edited["revision"], "reason": "Owner approved"},
        "owner-approve",
        now,
    )
    assert reapproved["status"] == "confirmed"
    assert reapproved["approved_by"] == "owner"
    assert reapproved["revision"] == 4


@pytest.mark.asyncio
async def test_parent_participants_vs_adult_own_only_and_guest_denial(calendar_engine, now):
    # Adult can only specify themselves as participant
    adult_event = await calendar_engine.execute(
        "adult",
        "calendar.save",
        {
            "title": "Adult Solo Event",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "participants": ["adult"],
        },
        "adult-solo",
        now,
    )
    assert adult_event["status"] == "confirmed"
    assert adult_event["participants"] == ["adult"]

    # Adult cannot specify other participants
    with pytest.raises(DomainError, match="forbidden"):
        await calendar_engine.execute(
            "adult",
            "calendar.save",
            {
                "title": "Adult Multi Event",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
                "participants": ["adult", "child"],
            },
            "adult-multi",
            now,
        )

    # Parent can specify multiple participants and escort
    parent_event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Family Trip",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T11:00:00Z",
            "participants": ["child", "sibling"],
            "escort": "adult",
        },
        "parent-multi",
        now,
    )
    assert parent_event["status"] == "confirmed"
    assert parent_event["participants"] == ["child", "sibling"]
    assert parent_event["escort"] == "adult"

    # Guest cannot perform calendar actions
    with pytest.raises(DomainError, match="forbidden"):
        await calendar_engine.execute(
            "guest",
            "calendar.save",
            {
                "title": "Guest Event",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "guest-save",
            now,
        )

    # Guest is excluded from view
    assert "calendar" not in calendar_engine.view("guest")

    # Guest cannot be participant
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "title": "Guest Participant",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
                "participants": ["guest"],
            },
            "parent-guest-part",
            now,
        )


@pytest.mark.asyncio
async def test_private_event_projections_no_sibling_leak(calendar_engine, now):
    # Child creates a private event with visibility='participants'
    private_child_event = await calendar_engine.execute(
        "child",
        "calendar.save",
        {
            "title": "Child Secret Event",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "visibility": "participants",
        },
        "child-secret",
        now,
    )

    # Child sees it
    child_view = calendar_engine.view("child", now=now)
    assert any(e["id"] == private_child_event["id"] for e in child_view["calendar"]["events"])
    assert any(
        o["event_id"] == private_child_event["id"] for o in child_view["calendar"]["occurrences"]
    )

    # Sibling does not see it (no sibling leak)
    sibling_view = calendar_engine.view("sibling", now=now)
    assert not any(e["id"] == private_child_event["id"] for e in sibling_view["calendar"]["events"])
    assert not any(
        o["event_id"] == private_child_event["id"] for o in sibling_view["calendar"]["occurrences"]
    )

    # Parent (privileged) can see it
    parent_view = calendar_engine.view("parent", now=now)
    assert any(e["id"] == private_child_event["id"] for e in parent_view["calendar"]["events"])

    # Adult (non-privileged) does not see it
    adult_view = calendar_engine.view("adult", now=now)
    assert not any(e["id"] == private_child_event["id"] for e in adult_view["calendar"]["events"])


@pytest.mark.asyncio
async def test_ha_export_default_no_publish_and_explicit_owner_confirmation(calendar_engine, now):
    # Create confirmed family event
    fam_event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Family Confirmed",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "visibility": "family",
        },
        "fam-event",
        now,
    )

    # Create private event
    await calendar_engine.execute(
        "child",
        "calendar.save",
        {
            "title": "Child Private Tentative",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "visibility": "participants",
        },
        "priv-event",
        now,
    )

    query_start = now
    query_end = now + timedelta(days=7)

    # Default: publish_to_ha is False, so published returns []
    snap = calendar_engine.snapshot()
    assert not snap["settings"].get("calendar", {}).get("publish_to_ha", False)
    assert published(snap, query_start, query_end) == []

    # Non-owner cannot configure
    with pytest.raises(DomainError, match="forbidden"):
        await calendar_engine.execute(
            "parent",
            "calendar.configure",
            {"revision": 0, "publish_to_ha": True, "confirm_public_visibility": True},
            "cfg-forbidden",
            now,
        )

    # Owner enabling publish_to_ha without confirm_public_visibility raises confirmation_required
    with pytest.raises(DomainError, match="confirmation_required"):
        await calendar_engine.execute(
            "owner",
            "calendar.configure",
            {"revision": 0, "publish_to_ha": True},
            "cfg-no-confirm",
            now,
        )

    # Stale revision fails
    with pytest.raises(DomainError, match="conflict"):
        await calendar_engine.execute(
            "owner",
            "calendar.configure",
            {"revision": 5, "publish_to_ha": True, "confirm_public_visibility": True},
            "cfg-stale",
            now,
        )

    # Owner explicitly confirms public visibility
    cfg = await calendar_engine.execute(
        "owner",
        "calendar.configure",
        {"revision": 0, "publish_to_ha": True, "confirm_public_visibility": True},
        "cfg-success",
        now,
    )
    assert cfg["publish_to_ha"] is True
    assert cfg["revision"] == 1

    # Now published only exports family confirmed events
    pub = published(calendar_engine.snapshot(), query_start, query_end)
    assert len(pub) == 1
    assert pub[0]["event_id"] == fam_event["id"]
    assert pub[0]["title"] == "Family Confirmed"


@pytest.mark.asyncio
async def test_child_approval_and_member_deactivate(calendar_engine, now):
    child_event = await calendar_engine.execute(
        "child",
        "calendar.save",
        {
            "title": "School Trip",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "reminder_minutes": [15],
        },
        "child-trip",
        now,
    )
    # Child cannot approve
    with pytest.raises(DomainError, match="forbidden"):
        await calendar_engine.execute(
            "child",
            "calendar.approve",
            {"id": child_event["id"], "revision": 1, "reason": "Approve"},
            "child-appr",
            now,
        )

    # Parent approves
    await calendar_engine.execute(
        "parent",
        "calendar.approve",
        {"id": child_event["id"], "revision": 1, "reason": "Parent approves"},
        "parent-appr",
        now,
    )

    # Owner deactivates child
    await calendar_engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "name": "Child",
            "role": "child",
            "active": False,
        },
        "deact-child",
        now,
    )

    # Deactivated child cannot act
    with pytest.raises(DomainError, match="forbidden"):
        await calendar_engine.execute(
            "child",
            "calendar.save",
            {
                "title": "Another trip",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "child-after-deact",
            now,
        )

    # Deactivated child reminders are not dispatched in tick
    tick_time = datetime(2026, 9, 6, 8, 45, tzinfo=UTC)
    await calendar_engine.tick(tick_time)
    outbox = calendar_engine.snapshot()["outbox"]
    assert not any(n["recipient"] == "child" for n in outbox.values())


@pytest.mark.asyncio
async def test_strict_revisions_bool_missing_stale(calendar_engine, now):
    event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Revision Event",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
        },
        "rev-create",
        now,
    )
    assert event["revision"] == 1

    # Missing revision when id is provided
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "id": event["id"],
                "title": "No revision",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "rev-missing",
            now,
        )

    # Providing revision when creating new event (no id)
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "revision": 1,
                "title": "Revision without id",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "rev-without-id",
            now,
        )

    # Boolean revision instead of int
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "id": event["id"],
                "revision": True,
                "title": "Bool revision",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "rev-bool",
            now,
        )

    # Stale revision on save
    with pytest.raises(DomainError, match="conflict"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "id": event["id"],
                "revision": 99,
                "title": "Stale revision",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "rev-stale",
            now,
        )

    # Stale revision on cancel
    with pytest.raises(DomainError, match="conflict"):
        await calendar_engine.execute(
            "parent",
            "calendar.cancel",
            {"id": event["id"], "revision": 99, "reason": "Cancel stale"},
            "cancel-stale",
            now,
        )


@pytest.mark.asyncio
async def test_cancel_archive_history_no_resurrection(calendar_engine, now):
    event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Event to cancel",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
        },
        "event-create",
        now,
    )
    assert [h["action"] for h in event["history"]] == ["created"]

    # Cancel event
    cancelled = await calendar_engine.execute(
        "parent",
        "calendar.cancel",
        {"id": event["id"], "revision": event["revision"], "reason": "Rain forecasted"},
        "cancel-1",
        now,
    )
    assert cancelled["status"] == "cancelled"
    assert [h["action"] for h in cancelled["history"]] == ["created", "cancel"]
    assert cancelled["history"][-1]["reason"] == "Rain forecasted"

    # Cannot cancel already cancelled
    with pytest.raises(DomainError, match="invalid_transition"):
        await calendar_engine.execute(
            "parent",
            "calendar.cancel",
            {"id": cancelled["id"], "revision": cancelled["revision"], "reason": "Cancel again"},
            "cancel-again",
            now,
        )

    # Cannot edit cancelled event (no resurrection)
    with pytest.raises(DomainError, match="invalid_transition"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "id": cancelled["id"],
                "revision": cancelled["revision"],
                "title": "Resurrect attempt",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "resurrect-save",
            now,
        )

    # Archive cancelled event
    archived = await calendar_engine.execute(
        "parent",
        "calendar.archive",
        {"id": cancelled["id"], "revision": cancelled["revision"], "reason": "Archiving cancelled"},
        "archive-1",
        now,
    )
    assert archived["archived"] is True
    assert [h["action"] for h in archived["history"]] == ["created", "cancel", "archive"]

    # Cannot edit archived event
    with pytest.raises(DomainError, match="invalid_transition"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "id": archived["id"],
                "revision": archived["revision"],
                "title": "Edit archived",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "resurrect-archived",
            now,
        )


@pytest.mark.asyncio
async def test_malformed_fields_and_optional_preservation(calendar_engine, now):
    # Missing required title
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {"start": "2026-09-06T09:00:00Z", "end": "2026-09-06T10:00:00Z"},
            "bad-missing-title",
            now,
        )

    # Malformed start datetime
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {"title": "Bad Start", "start": "not-a-date", "end": "2026-09-06T10:00:00Z"},
            "bad-start",
            now,
        )

    # End before start
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {"title": "Inverted", "start": "2026-09-06T10:00:00Z", "end": "2026-09-06T09:00:00Z"},
            "bad-end",
            now,
        )

    # All day valid
    allday_event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "All Day Event",
            "all_day": True,
            "start": "2026-09-06",
            "end": "2026-09-07",
        },
        "good-allday",
        now,
    )
    assert allday_event["all_day"] is True

    # Malformed reminder_minutes (duplicates or > 10080)
    with pytest.raises(DomainError, match="invalid_field"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "title": "Bad Reminders",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
                "reminder_minutes": [15, 15],
            },
            "bad-rem-dup",
            now,
        )

    # Create task for child
    task = await calendar_engine.execute(
        "parent",
        "tasks.create",
        {"title": "Child Task", "assignee": "child"},
        "create-task",
        now,
    )

    # Valid task link and preservation of optional fields across edits
    full_event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Complete Event",
            "description": "Full detailed description",
            "location": "Room 42",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "participants": ["child"],
            "task_ids": [task["id"]],
            "preparation": ["Pack backpack", "Bring water"],
            "reminder_minutes": [15, 30],
        },
        "full-event-save",
        now,
    )
    assert full_event["description"] == "Full detailed description"
    assert full_event["location"] == "Room 42"
    assert full_event["preparation"] == ["Pack backpack", "Bring water"]
    assert full_event["reminder_minutes"] == [30, 15]

    # Edit without specifying description/location/preparation -> preserved from previous
    edited = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "id": full_event["id"],
            "revision": full_event["revision"],
            "title": "Updated Complete Event",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
        },
        "partial-edit",
        now,
    )
    assert edited["description"] == "Full detailed description"
    assert edited["location"] == "Room 42"
    assert edited["preparation"] == ["Pack backpack", "Bring water"]
    assert edited["task_ids"] == [task["id"]]


@pytest.mark.asyncio
async def test_exact_replay_concurrent_edits_and_store_failure(calendar_engine, store, now):
    payload = {
        "title": "Replay Event",
        "start": "2026-09-06T09:00:00Z",
        "end": "2026-09-06T10:00:00Z",
    }
    first = await calendar_engine.execute("parent", "calendar.save", payload, "op-replay", now)
    second = await calendar_engine.execute("parent", "calendar.save", payload, "op-replay", now)
    assert first == second

    # Storage failure aborts without mutating state
    before = calendar_engine.snapshot()
    store.fail = True
    with pytest.raises(OSError, match="synthetic disk error"):
        await calendar_engine.execute(
            "parent",
            "calendar.save",
            {
                "title": "Disk Fail Event",
                "start": "2026-09-06T09:00:00Z",
                "end": "2026-09-06T10:00:00Z",
            },
            "op-fail",
            now,
        )
    assert calendar_engine.snapshot() == before
    store.fail = False

    # Reload from store matches
    reloaded = Engine(store.value, store.save)
    assert reloaded.snapshot()["calendar"] == calendar_engine.snapshot()["calendar"]

    # Concurrent edits on the same revision: exactly one succeeds, one gets conflict
    edit_payload_1 = {
        "id": first["id"],
        "revision": first["revision"],
        "title": "Concurrent 1",
        "start": "2026-09-06T09:00:00Z",
        "end": "2026-09-06T10:00:00Z",
    }
    edit_payload_2 = {
        "id": first["id"],
        "revision": first["revision"],
        "title": "Concurrent 2",
        "start": "2026-09-06T09:00:00Z",
        "end": "2026-09-06T10:00:00Z",
    }
    results = await asyncio.gather(
        calendar_engine.execute("parent", "calendar.save", edit_payload_1, "race-1", now),
        calendar_engine.execute("parent", "calendar.save", edit_payload_2, "race-2", now),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert any(isinstance(r, DomainError) and r.code == "conflict" for r in results)


@pytest.mark.asyncio
async def test_reminders_15min_dedup_restart_and_recipients(calendar_engine, store, now):
    event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Doctor Appointment",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "participants": ["child"],
            "escort": "adult",
            "preparation": ["Health card"],
            "reminder_minutes": [15],
        },
        "doc-event",
        now,
    )

    # At 08:40 (20min before start): 15min reminder is NOT due yet
    t_early = datetime(2026, 9, 6, 8, 40, tzinfo=UTC)
    assert await calendar_engine.tick(t_early) is False
    assert len(calendar_engine.snapshot()["outbox"]) == 0

    # At 08:45 (exactly 15min before start): reminder is due
    t_due = datetime(2026, 9, 6, 8, 45, tzinfo=UTC)
    assert await calendar_engine.tick(t_due) is True
    outbox = calendar_engine.snapshot()["outbox"]
    recipients = {msg["recipient"] for msg in outbox.values()}
    # Only participants and escort receive the reminder (child and adult)
    assert recipients == {"child", "adult"}
    msg = next(m for m in outbox.values() if m["recipient"] == "child")
    assert msg["key"] == "calendar_reminder"
    assert msg["data"]["title"] == "Doctor Appointment"
    assert msg["data"]["preparation"] == ["Health card"]
    assert msg["data"]["event_id"] == event["id"]

    # Dedup: ticking again at 08:46 produces no new reminder
    t_next = datetime(2026, 9, 6, 8, 46, tzinfo=UTC)
    assert await calendar_engine.tick(t_next) is False

    # Engine restart with same persisted state does not re-send
    restarted = Engine(store.value, store.save)
    assert await restarted.tick(t_next) is False


@pytest.mark.asyncio
async def test_5min_catchup_skips_older_reminders(calendar_engine, now):
    await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Missed Event",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "participants": ["child"],
            "reminder_minutes": [15],
        },
        "missed-event",
        now,
    )

    # Offline until 08:52 (7 min past 08:45 due time). Window [08:47, 08:52] skips 08:45.
    t_late = datetime(2026, 9, 6, 8, 52, tzinfo=UTC)
    assert await calendar_engine.tick(t_late) is False
    assert len(calendar_engine.snapshot()["outbox"]) == 0


@pytest.mark.asyncio
async def test_module_disable_supersedes_unsent_reminders(calendar_engine, now):
    await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Meeting",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "participants": ["child"],
            "reminder_minutes": [15],
        },
        "meeting-event",
        now,
    )

    # Tick at 08:45 sends reminder to outbox
    t_due = datetime(2026, 9, 6, 8, 45, tzinfo=UTC)
    await calendar_engine.tick(t_due)
    outbox = calendar_engine.snapshot()["outbox"]
    assert any(m["key"] == "calendar_reminder" and m["state"] == "pending" for m in outbox.values())

    # Disable calendar module
    await calendar_engine.execute(
        "owner",
        "settings.save",
        {
            "name": "Example household",
            "language": "en",
            "modules": ["shopping", "tasks", "alarms", "court"],
        },
        "disable-calendar",
        now,
    )

    # Tick with calendar module disabled supersedes unsent reminders
    await calendar_engine.tick(datetime(2026, 9, 6, 8, 46, tzinfo=UTC))
    outbox_after = calendar_engine.snapshot()["outbox"]
    calendar_reminders = [m for m in outbox_after.values() if m["key"] == "calendar_reminder"]
    assert len(calendar_reminders) > 0
    assert all(m["state"] == "superseded" for m in calendar_reminders)


@pytest.mark.asyncio
async def test_cancel_or_edit_supersedes_pending_reminders(calendar_engine, now):
    event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Lesson",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "participants": ["child"],
            "reminder_minutes": [15],
        },
        "lesson-save",
        now,
    )

    # Fire reminder
    await calendar_engine.tick(datetime(2026, 9, 6, 8, 45, tzinfo=UTC))
    outbox = calendar_engine.snapshot()["outbox"]
    assert any(m["state"] == "pending" for m in outbox.values())

    # Cancel event supersedes pending reminders
    await calendar_engine.execute(
        "parent",
        "calendar.cancel",
        {"id": event["id"], "revision": event["revision"], "reason": "Tutor ill"},
        "lesson-cancel",
        now,
    )
    outbox_after = calendar_engine.snapshot()["outbox"]
    assert all(
        m["state"] == "superseded" for m in outbox_after.values() if m["key"] == "calendar_reminder"
    )


@pytest.mark.asyncio
async def test_recurrence_expansion_and_reminders(calendar_engine, now):
    rule = {
        "frequency": "daily",
        "interval": 1,
        "start_date": "2026-09-06",
        "time": "09:00",
        "timezone": "UTC",
    }
    rec_event = await calendar_engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Daily Morning Standup",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T09:30:00Z",
            "rule": rule,
            "participants": ["child"],
            "reminder_minutes": [15],
        },
        "rec-save",
        now,
    )

    # View occurrences for 7 days
    child_view = calendar_engine.view("child", now=now)
    occurrences = [
        o for o in child_view["calendar"]["occurrences"] if o["event_id"] == rec_event["id"]
    ]
    assert len(occurrences) >= 7

    # Tick for first day's 15min reminder (08:45)
    t_day1 = datetime(2026, 9, 6, 8, 45, tzinfo=UTC)
    await calendar_engine.tick(t_day1)
    outbox1 = calendar_engine.snapshot()["outbox"]
    assert any(
        m["key"] == "calendar_reminder" and m["data"]["start"] == "2026-09-06T09:00:00Z"
        for m in outbox1.values()
    )

    # Tick for second day's 15min reminder (2026-09-07 08:45)
    t_day2 = datetime(2026, 9, 7, 8, 45, tzinfo=UTC)
    await calendar_engine.tick(t_day2)
    outbox2 = calendar_engine.snapshot()["outbox"]
    assert any(
        m["key"] == "calendar_reminder" and m["data"]["start"] == "2026-09-07T09:00:00Z"
        for m in outbox2.values()
    )
