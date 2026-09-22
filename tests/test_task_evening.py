"""Daily evening task check: one reminder per member per local day."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import task_events
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.task_delivery import (
    current_evening_reminder,
)
from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram import messages

SYSTEM = {"id": "system", "role": "system"}
KYIV = "Europe/Kyiv"
# 2026-09-06 17:00 UTC == 20:00 Europe/Kyiv (UTC+3)
EVENING = datetime(2026, 9, 6, 17, 0, tzinfo=UTC)


def evening_state(engine):
    state = engine.snapshot()
    state["settings"]["modules"] = ["tasks"]
    state["settings"]["timezone"] = KYIV
    return state


def add_task(state, member, *, index, due_at=None, status="assigned", personal=False):
    task_id = f"T{index:06d}"
    state["tasks"][task_id] = {
        "id": task_id,
        "title": f"Task {index}",
        "assignee": member,
        "assignee_revision": 1,
        "creator": member if personal else "parent",
        "due_at": due_at,
        "created_at": "2026-09-01T08:00:00+00:00",
        "status": status,
        "report_type": "none" if personal else "text",
        "report": None,
        "deadline_policy": {"reminder_minutes": 0, "grace_minutes": 0, "penalty": 0},
        "checklist": [],
        "revision": 1,
        "updated_at": "2026-09-01T08:00:00+00:00",
        **({"delivery_scope": "personal"} if personal else {}),
    }
    return task_id


def run_tick(state, now):
    task_events.tick(Context(state, SYSTEM, now, f"evening-test:{now.isoformat()}"))


def evening_events(state):
    return [
        event
        for event in state["outbox"].values()
        if event["key"] == "task_evening_reminder"
    ]


def make_event(state, task_ids, *, expires_at="2026-09-06T23:59:59+03:00"):
    event = {
        "id": "evening-test-event",
        "recipient": "child",
        "key": "task_evening_reminder",
        "data": {"date": "2026-09-06", "tasks": task_ids, "expires_at": expires_at},
        "created_at": EVENING.isoformat(),
        "state": "pending",
        "attempts": 0,
    }
    state["outbox"][event["id"]] = event
    return event


def test_evening_reminder_fires_once_per_member_per_day(engine):
    state = evening_state(engine)
    add_task(state, "child", index=2, due_at=None)
    add_task(state, "child", index=1, due_at="2026-09-08T17:00:00+00:00")
    add_task(state, "sibling", index=3, due_at=None)

    run_tick(state, EVENING + timedelta(minutes=5))

    events = evening_events(state)
    assert len(events) == 2
    child = next(event for event in events if event["recipient"] == "child")
    sibling = next(event for event in events if event["recipient"] == "sibling")
    # Tasks with a due date come first; undated tasks are still listed.
    assert child["data"]["tasks"] == ["T000001", "T000002"]
    assert sibling["data"]["tasks"] == ["T000003"]
    assert child["data"]["date"] == "2026-09-06"
    assert child["data"]["expires_at"] == "2026-09-06T23:59:59+03:00"
    markers = state["task_evening_reminders"]
    assert markers["2026-09-06:child"]["event_id"] == child["id"]
    assert markers["2026-09-06:sibling"]["event_id"] == sibling["id"]

    run_tick(state, EVENING + timedelta(minutes=25))
    assert len(evening_events(state)) == 2


def test_evening_check_time_gate(engine):
    state = evening_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, EVENING - timedelta(minutes=1))
    assert evening_events(state) == []
    assert state["task_evening_reminders"] == {}

    run_tick(state, EVENING)
    assert len(evening_events(state)) == 1


def test_evening_check_excludes_closed_personal_guest_and_inactive(engine):
    state = evening_state(engine)
    add_task(state, "child", index=1, status="submitted")
    add_task(state, "child", index=2, personal=True)
    add_task(state, "guest", index=3)
    add_task(state, "sibling", index=4)
    state["members"]["sibling"]["active"] = False
    add_task(state, "child", index=5, status="in_progress")

    run_tick(state, EVENING + timedelta(minutes=5))

    events = evening_events(state)
    assert len(events) == 1
    assert events[0]["recipient"] == "child"
    assert events[0]["data"]["tasks"] == ["T000005"]
    assert "2026-09-06:sibling" not in state["task_evening_reminders"]


def test_evening_check_late_start_same_day(engine):
    state = evening_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, datetime(2026, 9, 6, 20, 30, tzinfo=UTC))  # 23:30 Kyiv

    assert len(evening_events(state)) == 1


def test_evening_check_next_day_fires_again(engine):
    state = evening_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, EVENING + timedelta(minutes=5))
    run_tick(state, EVENING + timedelta(days=1, minutes=5))

    events = evening_events(state)
    assert len(events) == 2
    assert "2026-09-07:child" in state["task_evening_reminders"]
    assert events[-1]["data"]["date"] == "2026-09-07"


def test_evening_check_prunes_stale_markers(engine):
    state = evening_state(engine)
    state["task_evening_reminders"] = {
        "2026-08-20:child": {"at": "2026-08-20T17:05:00+00:00", "event_id": "old"},
        "broken:child": {"at": "2026-08-20T17:05:00+00:00", "event_id": "old"},
        "2026-09-01:child": "malformed-marker",
    }
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, EVENING + timedelta(minutes=5))

    markers = state["task_evening_reminders"]
    assert "2026-08-20:child" not in markers
    assert "broken:child" not in markers
    assert "2026-09-01:child" not in markers
    assert "2026-09-06:child" in markers


def test_evening_check_module_disabled(engine):
    state = evening_state(engine)
    state["settings"]["modules"] = []
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, EVENING + timedelta(minutes=5))

    assert evening_events(state) == []


def test_evening_render_lists_current_open_tasks(engine):
    state = evening_state(engine)
    state["members"]["child"]["telegram_id"] = 101
    state["members"]["child"]["language"] = "ru"
    add_task(state, "child", index=1, due_at="2026-09-08T17:00:00+00:00")
    add_task(state, "child", index=2, due_at=None)
    add_task(state, "child", index=3, status="completed")
    event = make_event(state, ["T000001", "T000002", "T000003"])

    targets = messages.targets(event, state)
    assert targets == [{"channel": "telegram", "id": 101, "language": "ru"}]
    envelope = messages.render(event, targets[0], state, now=EVENING + timedelta(minutes=5))
    assert envelope["chat_id"] == 101
    assert envelope["text"] == (
        "🌙 Вечерняя проверка задач:\n"
        "• Task 1 — срок 08.09.2026 20:00\n"
        "• Task 2"
    )


def test_evening_render_marks_overdue(engine):
    state = evening_state(engine)
    state["members"]["child"]["telegram_id"] = 101
    add_task(state, "child", index=1, due_at="2026-09-05T17:00:00+00:00")
    event = make_event(state, ["T000001"])

    targets = messages.targets(event, state)
    envelope = messages.render(event, targets[0], state, now=EVENING + timedelta(minutes=5))

    assert "• Task 1 — overdue" in envelope["text"]


def test_evening_render_revoked_when_every_task_closed(engine):
    state = evening_state(engine)
    state["members"]["child"]["telegram_id"] = 101
    add_task(state, "child", index=1, status="completed")
    event = make_event(state, ["T000001"])

    # The member target still resolves; render revalidates the task list.
    targets = messages.targets(event, state)
    assert targets
    with pytest.raises(DeliveryError) as err:
        messages.render(event, targets[0], state, now=EVENING + timedelta(minutes=5))
    assert err.value.code == "delivery_revoked"


def test_current_evening_reminder(engine):
    state = evening_state(engine)
    add_task(state, "child", index=1, due_at=None)
    event = make_event(state, ["T000001"])
    assert current_evening_reminder(state, event, EVENING + timedelta(minutes=5)) is True

    state["tasks"]["T000001"]["status"] = "completed"
    assert current_evening_reminder(state, event, EVENING + timedelta(minutes=5)) is False

    state["tasks"]["T000001"]["status"] = "assigned"
    state["tasks"]["T000001"]["assignee"] = "sibling"
    assert current_evening_reminder(state, event, EVENING + timedelta(minutes=5)) is False

    # Past local end of day the list is stale even if a task is still open.
    state["tasks"]["T000001"]["assignee"] = "child"
    assert (
        current_evening_reminder(state, event, datetime(2026, 9, 6, 21, 0, tzinfo=UTC))
        is False
    )
