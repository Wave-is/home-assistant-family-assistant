"""Daily task checkpoints: 16:00 personal reminder + 20:00 family court session."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import task_events
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.task_delivery import (
    current_afternoon_reminder,
    current_evening_settlement,
)
from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram import messages

SYSTEM = {"id": "system", "role": "system"}
KYIV = "Europe/Kyiv"
# 2026-09-06 13:00 UTC == 16:00 Europe/Kyiv (UTC+3)
AFTERNOON = datetime(2026, 9, 6, 13, 0, tzinfo=UTC)
# 2026-09-06 17:00 UTC == 20:00 Europe/Kyiv
SETTLE = datetime(2026, 9, 6, 17, 0, tzinfo=UTC)
EXPIRES = "2026-09-06T23:59:59+03:00"


def afternoon_state(engine):
    state = engine.snapshot()
    state["settings"]["modules"] = ["tasks"]
    state["settings"]["timezone"] = KYIV
    return state


def settlement_state(engine):
    state = engine.snapshot()
    state["settings"]["modules"] = ["tasks", "court"]
    state["settings"]["timezone"] = KYIV
    state["settings"]["automatic_penalties"] = True
    state["settings"]["daily_penalty_cap"] = 10
    return state


def add_task(
    state,
    member,
    *,
    index,
    due_at=None,
    status="assigned",
    personal=False,
    penalty=0,
    created_at="2026-09-01T08:00:00+00:00",
):
    task_id = f"T{index:06d}"
    state["tasks"][task_id] = {
        "id": task_id,
        "title": f"Task {index}",
        "assignee": member,
        "assignee_revision": 1,
        "creator": member if personal else "parent",
        "due_at": due_at,
        "created_at": created_at,
        "status": status,
        "report_type": "none" if personal else "text",
        "report": None,
        "deadline_policy": {"reminder_minutes": 0, "grace_minutes": 0, "penalty": penalty},
        "checklist": [],
        "revision": 1,
        "updated_at": "2026-09-01T08:00:00+00:00",
        **({"delivery_scope": "personal"} if personal else {}),
    }
    return task_id


def run_tick(state, now):
    task_events.tick(Context(state, SYSTEM, now, f"check-test:{now.isoformat()}"))


def events(state, key):
    return [event for event in state["outbox"].values() if event["key"] == key]


def test_afternoon_reminder_fires_once_per_member_per_day(engine):
    state = afternoon_state(engine)
    add_task(state, "child", index=2, due_at=None)
    add_task(state, "child", index=1, due_at="2026-09-08T17:00:00+00:00")
    add_task(state, "sibling", index=3, due_at=None)

    run_tick(state, AFTERNOON + timedelta(minutes=5))

    found = events(state, "task_afternoon_reminder")
    assert len(found) == 2
    child = next(event for event in found if event["recipient"] == "child")
    sibling = next(event for event in found if event["recipient"] == "sibling")
    # Tasks with a due date come first; undated tasks are still listed.
    assert child["data"]["tasks"] == ["T000001", "T000002"]
    assert sibling["data"]["tasks"] == ["T000003"]
    assert child["data"]["date"] == "2026-09-06"
    assert child["data"]["expires_at"] == EXPIRES
    markers = state["task_afternoon_reminders"]
    assert markers["2026-09-06:child"]["event_id"] == child["id"]
    assert markers["2026-09-06:sibling"]["event_id"] == sibling["id"]

    run_tick(state, AFTERNOON + timedelta(minutes=25))
    assert len(events(state, "task_afternoon_reminder")) == 2


def test_afternoon_check_time_gate(engine):
    state = afternoon_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, AFTERNOON - timedelta(minutes=1))
    assert events(state, "task_afternoon_reminder") == []
    assert state["task_afternoon_reminders"] == {}

    run_tick(state, AFTERNOON)
    assert len(events(state, "task_afternoon_reminder")) == 1


def test_afternoon_check_excludes_closed_personal_guest_and_inactive(engine):
    state = afternoon_state(engine)
    add_task(state, "child", index=1, status="submitted")
    add_task(state, "child", index=2, personal=True)
    add_task(state, "guest", index=3)
    add_task(state, "sibling", index=4)
    state["members"]["sibling"]["active"] = False
    add_task(state, "child", index=5, status="in_progress")

    run_tick(state, AFTERNOON + timedelta(minutes=5))

    found = events(state, "task_afternoon_reminder")
    assert len(found) == 1
    assert found[0]["recipient"] == "child"
    assert found[0]["data"]["tasks"] == ["T000005"]
    assert "2026-09-06:sibling" not in state["task_afternoon_reminders"]


def test_afternoon_check_late_start_same_day(engine):
    state = afternoon_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, datetime(2026, 9, 6, 20, 30, tzinfo=UTC))  # 23:30 Kyiv

    assert len(events(state, "task_afternoon_reminder")) == 1


def test_afternoon_check_next_day_fires_again(engine):
    state = afternoon_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, AFTERNOON + timedelta(minutes=5))
    run_tick(state, AFTERNOON + timedelta(days=1, minutes=5))

    found = events(state, "task_afternoon_reminder")
    assert len(found) == 2
    assert "2026-09-07:child" in state["task_afternoon_reminders"]
    assert found[-1]["data"]["date"] == "2026-09-07"


def test_afternoon_check_prunes_stale_markers(engine):
    state = afternoon_state(engine)
    state["task_afternoon_reminders"] = {
        "2026-08-20:child": {"at": "2026-08-20T13:05:00+00:00", "event_id": "old"},
        "broken:child": {"at": "2026-08-20T13:05:00+00:00", "event_id": "old"},
        "2026-09-01:child": "malformed-marker",
    }
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, AFTERNOON + timedelta(minutes=5))

    markers = state["task_afternoon_reminders"]
    assert "2026-08-20:child" not in markers
    assert "broken:child" not in markers
    assert "2026-09-01:child" not in markers
    assert "2026-09-06:child" in markers


def test_afternoon_check_module_disabled(engine):
    state = afternoon_state(engine)
    state["settings"]["modules"] = []
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, AFTERNOON + timedelta(minutes=5))

    assert events(state, "task_afternoon_reminder") == []


def test_afternoon_render_lists_current_open_tasks(engine):
    state = afternoon_state(engine)
    state["members"]["child"]["telegram_id"] = 101
    state["members"]["child"]["language"] = "ru"
    add_task(state, "child", index=1, due_at="2026-09-08T17:00:00+00:00")
    add_task(state, "child", index=2, due_at=None)
    add_task(state, "child", index=3, status="completed")
    event = {
        "id": "afternoon-test-event",
        "recipient": "child",
        "key": "task_afternoon_reminder",
        "data": {"date": "2026-09-06", "tasks": ["T000001", "T000002", "T000003"], "expires_at": EXPIRES},
        "created_at": AFTERNOON.isoformat(),
        "state": "pending",
        "attempts": 0,
    }
    state["outbox"][event["id"]] = event

    targets = messages.targets(event, state)
    assert targets == [{"channel": "telegram", "id": 101, "language": "ru"}]
    envelope = messages.render(event, targets[0], state, now=AFTERNOON + timedelta(minutes=5))
    assert envelope["chat_id"] == 101
    assert envelope["text"] == (
        "🔔 Ненавязчивый цифровой тык: эти задачи всё ещё открыты 😅\n"
        "• Task 1 — срок 08.09.2026 20:00\n"
        "• Task 2"
    )


def test_afternoon_render_marks_overdue(engine):
    state = afternoon_state(engine)
    state["members"]["child"]["telegram_id"] = 101
    add_task(state, "child", index=1, due_at="2026-09-05T17:00:00+00:00")
    event = {
        "id": "afternoon-test-event",
        "recipient": "child",
        "key": "task_afternoon_reminder",
        "data": {"date": "2026-09-06", "tasks": ["T000001"], "expires_at": EXPIRES},
        "created_at": AFTERNOON.isoformat(),
        "state": "pending",
        "attempts": 0,
    }
    state["outbox"][event["id"]] = event

    targets = messages.targets(event, state)
    envelope = messages.render(event, targets[0], state, now=AFTERNOON + timedelta(minutes=5))

    assert "• Task 1 — overdue" in envelope["text"]


def test_afternoon_render_revoked_when_every_task_closed(engine):
    state = afternoon_state(engine)
    state["members"]["child"]["telegram_id"] = 101
    add_task(state, "child", index=1, status="completed")
    event = {
        "id": "afternoon-test-event",
        "recipient": "child",
        "key": "task_afternoon_reminder",
        "data": {"date": "2026-09-06", "tasks": ["T000001"], "expires_at": EXPIRES},
        "created_at": AFTERNOON.isoformat(),
        "state": "pending",
        "attempts": 0,
    }
    state["outbox"][event["id"]] = event

    # The member target still resolves; render revalidates the task list.
    targets = messages.targets(event, state)
    assert targets
    with pytest.raises(DeliveryError) as err:
        messages.render(event, targets[0], state, now=AFTERNOON + timedelta(minutes=5))
    assert err.value.code == "delivery_revoked"


def test_current_afternoon_reminder(engine):
    state = afternoon_state(engine)
    add_task(state, "child", index=1, due_at=None)
    event = {
        "id": "afternoon-test-event",
        "recipient": "child",
        "key": "task_afternoon_reminder",
        "data": {"date": "2026-09-06", "tasks": ["T000001"], "expires_at": EXPIRES},
        "created_at": AFTERNOON.isoformat(),
        "state": "pending",
        "attempts": 0,
    }
    state["outbox"][event["id"]] = event
    assert current_afternoon_reminder(state, event, AFTERNOON + timedelta(minutes=5)) is True

    state["tasks"]["T000001"]["status"] = "completed"
    assert current_afternoon_reminder(state, event, AFTERNOON + timedelta(minutes=5)) is False

    state["tasks"]["T000001"]["status"] = "assigned"
    state["tasks"]["T000001"]["assignee"] = "sibling"
    assert current_afternoon_reminder(state, event, AFTERNOON + timedelta(minutes=5)) is False

    # Past local end of day the list is stale even if a task is still open.
    state["tasks"]["T000001"]["assignee"] = "child"
    assert current_afternoon_reminder(state, event, datetime(2026, 9, 6, 21, 0, tzinfo=UTC)) is False


def settlement_event(state, awards, *, expires_at=EXPIRES):
    event = {
        "id": "settlement-test-event",
        "recipient": "family",
        "key": "task_evening_settlement",
        "data": {"date": "2026-09-06", "awards": awards, "expires_at": expires_at},
        "created_at": SETTLE.isoformat(),
        "state": "pending",
        "attempts": 0,
    }
    state["outbox"][event["id"]] = event
    return event


def test_settlement_time_gate(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, SETTLE - timedelta(minutes=1))
    assert events(state, "task_evening_settlement") == []
    assert state["court"] == {}
    assert state["task_evening_settlements"] == {}

    run_tick(state, SETTLE)
    assert len(events(state, "task_evening_settlement")) == 1
    assert "task:T000001:missed:2026-09-06" in state["court"]


def test_settlement_charges_each_open_child_task_once(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, due_at="2026-09-05T17:00:00+00:00")
    add_task(state, "child", index=2, due_at=None)

    run_tick(state, SETTLE + timedelta(minutes=5))

    court = state["court"]
    first = court["task:T000001:missed:2026-09-06"]
    second = court["task:T000002:missed:2026-09-06"]
    for record in (first, second):
        assert record["points"] == -1
        assert record["member"] == "child"
        assert record["source"] == "task"
        assert record["reason_key"] == "task_missed"
        assert record["status"] == "active"
    assert first["reason_data"]["task_id"] == "T000001"
    assert first["reason_data"]["settlement_date"] == "2026-09-06"
    assert second["reason_data"]["due_at"] is None

    found = events(state, "task_evening_settlement")
    assert len(found) == 1
    event = found[0]
    assert event["recipient"] == "family"
    assert [award["task_id"] for award in event["data"]["awards"]] == ["T000001", "T000002"]
    assert event["data"]["awards"][0]["member_name"] == "Child"
    assert "2026-09-06" in state["task_evening_settlements"]
    assert state["task_evening_settlements"]["2026-09-06"]["event_id"] == event["id"]

    # The next tick must not charge again or post a second message.
    run_tick(state, SETTLE + timedelta(minutes=25))
    assert len(state["court"]) == 2
    assert len(events(state, "task_evening_settlement")) == 1


def test_settlement_once_per_day_new_task_after_session_not_charged(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, SETTLE + timedelta(minutes=5))
    assert len(state["court"]) == 1

    add_task(state, "child", index=2, due_at=None)
    run_tick(state, SETTLE + timedelta(minutes=55))  # 21:00 Kyiv

    assert len(state["court"]) == 1
    assert len(events(state, "task_evening_settlement")) == 1


def test_settlement_excludes_personal_parent_managed_and_one_shot(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, personal=True)
    add_task(state, "parent", index=2)
    managed = add_task(state, "child", index=3)
    state["tasks"][managed]["missed_policy"] = {
        "daily_rollover": True,
        "settle_time": "20:00",
        "repeat_penalty": False,
        "same_day_correction": False,
    }
    one_shot = add_task(state, "child", index=4)
    state["court"][f"task:{one_shot}"] = {
        "id": f"task:{one_shot}",
        "member": "child",
        "points": -2,
        "reason_key": "task_missed",
        "reason_data": {"task_id": one_shot, "due_at": None},
        "actor": "system",
        "source": "task",
        "status": "active",
        "created_at": SETTLE.isoformat(),
        "revision": 1,
    }
    add_task(state, "child", index=5, due_at=None)

    run_tick(state, SETTLE + timedelta(minutes=5))

    assert [key for key in state["court"] if key.startswith("task:T00000")] == [
        f"task:{one_shot}",
        "task:T000005:missed:2026-09-06",
    ]
    found = events(state, "task_evening_settlement")
    assert len(found) == 1
    assert [award["task_id"] for award in found[0]["data"]["awards"]] == ["T000005"]


def test_settlement_respects_daily_cap(engine):
    state = settlement_state(engine)
    state["settings"]["daily_penalty_cap"] = 1
    add_task(state, "child", index=1, due_at="2026-09-05T17:00:00+00:00")
    add_task(state, "child", index=2, due_at=None)

    run_tick(state, SETTLE + timedelta(minutes=5))

    assert "task:T000001:missed:2026-09-06" in state["court"]
    assert "task:T000002:missed:2026-09-06" not in state["court"]
    found = events(state, "task_evening_settlement")
    assert [award["task_id"] for award in found[0]["data"]["awards"]] == ["T000001"]


def test_settlement_skips_existing_daily_record(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, due_at=None)
    state["court"]["task:T000001:missed:2026-09-06"] = {
        "id": "task:T000001:missed:2026-09-06",
        "member": "child",
        "points": -1,
        "reason_key": "task_missed",
        "reason_data": {"task_id": "T000001", "due_at": None, "settlement_date": "2026-09-06"},
        "actor": "system",
        "source": "task",
        "status": "active",
        "created_at": SETTLE.isoformat(),
        "revision": 1,
    }

    run_tick(state, SETTLE + timedelta(minutes=5))

    assert len(state["court"]) == 1
    assert events(state, "task_evening_settlement") == []
    # Nothing new was charged, so no marker is written and the tick stays inert.
    assert "2026-09-06" not in state["task_evening_settlements"]


def test_settlement_no_message_when_nothing_awarded(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, status="completed")

    run_tick(state, SETTLE + timedelta(minutes=5))

    assert state["court"] == {}
    assert events(state, "task_evening_settlement") == []
    assert "2026-09-06" not in state["task_evening_settlements"]


def test_settlement_skips_explicit_penalty_tasks(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, penalty=-1)

    run_tick(state, SETTLE + timedelta(minutes=5))

    # The one-shot deadline penalty flow owns this task; the session stays out.
    assert state["court"] == {}
    assert events(state, "task_evening_settlement") == []
    assert "2026-09-06" not in state["task_evening_settlements"]


def test_settlement_skips_settled_history(engine):
    state = settlement_state(engine)
    task_id = add_task(state, "child", index=1)
    state["tasks"][task_id]["missed_receipts"] = {
        f"{task_id}:missed:1:2026-09-05": {"id": f"{task_id}:missed:1:2026-09-05"}
    }

    run_tick(state, SETTLE + timedelta(minutes=5))

    assert state["court"] == {}
    assert events(state, "task_evening_settlement") == []
    assert "2026-09-06" not in state["task_evening_settlements"]


def test_settlement_skips_task_created_after_session_start(engine):
    state = settlement_state(engine)
    add_task(state, "child", index=1, created_at="2026-09-06T17:30:00+00:00")  # 20:30 Kyiv

    run_tick(state, SETTLE + timedelta(minutes=55))

    assert state["court"] == {}
    assert events(state, "task_evening_settlement") == []
    assert "2026-09-06" not in state["task_evening_settlements"]

    # The next day's session covers it.
    run_tick(state, SETTLE + timedelta(days=1, minutes=5))
    assert "task:T000001:missed:2026-09-07" in state["court"]


def test_settlement_requires_court_module(engine):
    state = settlement_state(engine)
    state["settings"]["modules"] = ["tasks"]
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, SETTLE + timedelta(minutes=5))

    assert state["court"] == {}
    assert events(state, "task_evening_settlement") == []
    assert state["task_evening_settlements"] == {}


def test_settlement_prunes_stale_markers(engine):
    state = settlement_state(engine)
    state["task_evening_settlements"] = {
        "2026-08-20": {"at": "2026-08-20T17:05:00+00:00", "event_id": "old"},
        "broken": {"at": "2026-08-20T17:05:00+00:00", "event_id": "old"},
    }
    add_task(state, "child", index=1, due_at=None)

    run_tick(state, SETTLE + timedelta(minutes=5))

    markers = state["task_evening_settlements"]
    assert "2026-08-20" not in markers
    assert "broken" not in markers
    assert "2026-09-06" in markers


def test_settlement_pipeline_tick_then_render_ru(engine):
    state = settlement_state(engine)
    state["settings"]["language"] = "ru"
    state["telegram"]["group_id"] = -509054614
    state["members"]["child"]["name"] = "Артём"
    add_task(state, "child", index=1, due_at="2026-09-05T17:00:00+00:00")
    add_task(state, "child", index=2, due_at=None)

    run_tick(state, SETTLE + timedelta(minutes=5))

    found = events(state, "task_evening_settlement")
    assert len(found) == 1
    targets = messages.targets(found[0], state)
    assert targets == [{"channel": "telegram", "id": -509054614, "language": "ru"}]
    envelope = messages.render(found[0], targets[0], state, now=SETTLE + timedelta(minutes=5))
    assert envelope["chat_id"] == -509054614
    assert envelope["text"] == (
        "⚖️ Вечернее заседание за 06.09 завершено:\n"
        "• Артём: −1 · T000001 · Task 1 · просрочена\n"
        "• Артём: −1 · T000002 · Task 2 · без срока\n"
        "Итого: Артём −2.\n"
        "Плюсы за полезную инициативу всё ещё могут выправить пятничный баланс."
    )


def test_settlement_render_labels_en_and_uk(engine):
    state = settlement_state(engine)
    state["telegram"]["group_id"] = -509054614
    awards = [
        {
            "member_id": "child",
            "member_name": "Child",
            "task_id": "T000001",
            "title": "Task 1",
            "due_at": "2026-09-08T17:00:00+00:00",
        }
    ]

    state["settings"]["language"] = "en"
    event = settlement_event(state, awards)
    envelope = messages.render(
        event,
        messages.targets(event, state)[0],
        state,
        now=SETTLE + timedelta(minutes=5),
    )
    assert envelope["text"] == (
        "⚖️ Evening session for 06.09 is over:\n"
        "• Child: −1 · T000001 · Task 1 · due 08.09.2026 20:00\n"
        "Total: Child −1.\n"
        "Plus points for useful initiative can still fix the Friday balance."
    )

    state["settings"]["language"] = "uk"
    event = settlement_event(state, awards)
    envelope = messages.render(
        event,
        messages.targets(event, state)[0],
        state,
        now=SETTLE + timedelta(minutes=5),
    )
    assert envelope["text"] == (
        "⚖️ Вечірнє засідання за 06.09 завершено:\n"
        "• Child: −1 · T000001 · Task 1 · термін 08.09.2026 20:00\n"
        "Разом: Child −1.\n"
        "Плюси за корисну ініціативу все ще можуть виправити п'ятничний баланс."
    )


def test_current_evening_settlement(engine):
    state = settlement_state(engine)
    awards = [
        {
            "member_id": "child",
            "member_name": "Child",
            "task_id": "T000001",
            "title": "Task 1",
            "due_at": None,
        }
    ]
    event = settlement_event(state, awards)
    # A truthful report of applied points: closing the task does not revoke it.
    state["tasks"]["T000001"] = {
        "id": "T000001",
        "title": "Task 1",
        "assignee": "child",
        "status": "completed",
        "created_at": "2026-09-01T08:00:00+00:00",
        "closed_at": SETTLE.isoformat(),
    }
    assert current_evening_settlement(state, event, SETTLE + timedelta(minutes=5)) is True
    # Past local end of day the stale session message is not delivered.
    assert current_evening_settlement(state, event, datetime(2026, 9, 6, 21, 0, tzinfo=UTC)) is False

    event = settlement_event(state, [])
    assert current_evening_settlement(state, event, SETTLE + timedelta(minutes=5)) is False
