"""Task delivery is reauthorized from current task state before transport."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.task_delivery import current_task_event

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def state():
    return {
        "settings": {"modules": ["tasks", "maintenance"]},
        "members": {
            "owner": {"id": "owner", "role": "owner", "active": True, "revision": 1},
            "child": {"id": "child", "role": "child", "active": True, "revision": 4},
        },
        "tasks": {
            "T1": {
                "id": "T1",
                "revision": 9,
                "title": "Reviewed maintenance task",
                "assignee": "child",
                "creator": "owner",
                "status": "assigned",
                "due_at": "2026-09-08T12:00:00+00:00",
                "maintenance_asset_id": "MA1",
            }
        },
        "incidents": {},
        "outbox": {},
        "notification_rates": {},
    }


def event(current, key, recipient, data, operation="test"):
    ctx = Context(current, current["members"]["owner"], NOW, operation)
    event_id = ctx.notify(recipient, key, data)
    return current["outbox"][event_id]


def stamped(**extra):
    return {"id": "T1", "member": "child", "member_revision": 4, **extra}


@pytest.mark.parametrize(
    ("key", "recipient", "data", "status"),
    [
        ("task_assigned", "child", stamped(), "assigned"),
        (
            "task_reminder",
            "child",
            stamped(due_at="2026-09-08T12:00:00+00:00"),
            "in_progress",
        ),
        ("task_review", "parents", stamped(), "submitted"),
    ],
)
def test_current_direct_task_events(key, recipient, data, status):
    current = state()
    current["tasks"]["T1"]["status"] = status
    notification = event(current, key, recipient, data)

    assert current_task_event(current, notification)
    # Checklist/status-neutral task revisions do not invalidate the audience.
    current["tasks"]["T1"]["revision"] += 1
    assert current_task_event(current, notification)


@pytest.mark.parametrize(
    "source_kind", ["maintenance_fault", "maintenance_service", "school_homework"]
)
def test_private_task_epoch_is_required_even_with_current_event_stamp(source_kind):
    current = state()
    task = current["tasks"]["T1"]
    task.update(source={"kind": source_kind}, delivery_scope="private", assignee_revision=4)
    notice = event(current, "task_assigned", "child", stamped())
    assert current_task_event(current, notice)
    task["assignee_revision"] = 3
    assert not current_task_event(current, notice)
    task["assignee_revision"] = 4
    del notice["data"]["member_revision"]
    assert current_task_event(current, notice)
    current["members"]["child"]["revision"] = 5
    assert not current_task_event(current, notice)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value, notice: value["settings"].update(modules=["maintenance"]),
        lambda value, notice: value["tasks"].pop("T1"),
        lambda value, notice: value["tasks"]["T1"].update(assignee="owner"),
        lambda value, notice: value["members"]["child"].update(active=False),
        lambda value, notice: value["members"]["child"].update(role="guest"),
        lambda value, notice: value["members"]["child"].update(revision=5),
        lambda value, notice: value["tasks"]["T1"].update(status="completed"),
        lambda value, notice: notice.update(recipient="owner"),
        lambda value, notice: notice["data"].update(member="owner"),
        lambda value, notice: notice["data"].update(member_revision=None),
    ],
)
def test_assigned_fails_closed_after_scope_change(mutate):
    current = state()
    notification = event(current, "task_assigned", "child", stamped())

    mutate(current, notification)

    assert not current_task_event(current, notification)


def test_reminder_requires_current_due_date_and_nonfinal_status():
    current = state()
    notification = event(
        current,
        "task_reminder",
        "child",
        stamped(due_at=current["tasks"]["T1"]["due_at"]),
    )
    assert current_task_event(current, notification)

    current["tasks"]["T1"]["due_at"] = "2026-09-09T12:00:00+00:00"
    assert not current_task_event(current, notification)


def test_review_requires_submitted_task_and_current_parent():
    current = state()
    current["tasks"]["T1"]["status"] = "submitted"
    notification = event(current, "task_review", "parents", stamped())
    assert current_task_event(current, notification)

    current["members"]["owner"]["role"] = "adult"
    assert not current_task_event(current, notification)
    current["members"]["owner"]["role"] = "owner"
    current["tasks"]["T1"]["status"] = "needs_changes"
    assert not current_task_event(current, notification)


def open_overdue(current, *, stamped_event=True):
    data = stamped(due_at=current["tasks"]["T1"]["due_at"])
    if not stamped_event:
        data = {"id": "T1", "member": "child"}
    notice = event(current, "task_overdue", "family", data, "incident:task:T1:1")
    current["incidents"]["task:T1"] = {
        "id": "task:T1",
        "generation": 1,
        "state": "open",
        "event_id": notice["id"],
        "recipient": "family",
    }
    return notice


def test_overdue_requires_open_matching_incident_and_current_task():
    current = state()
    notification = open_overdue(current)
    assert current_task_event(current, notification)

    changed = deepcopy(current)
    changed["incidents"]["task:T1"]["event_id"] = "different"
    assert not current_task_event(changed, notification)
    changed = deepcopy(current)
    changed["incidents"]["task:T1"]["state"] = "closed"
    assert not current_task_event(changed, notification)
    changed = deepcopy(current)
    changed["tasks"]["T1"]["due_at"] = "2026-09-09T12:00:00+00:00"
    assert not current_task_event(changed, notification)

    changed = deepcopy(current)
    changed["tasks"]["T1"]["due_at"] = None
    assert not current_task_event(changed, notification)


def close_announced(current, overdue):
    overdue["deliveries"] = {"telegram": {"state": "sent"}}
    overdue["state"] = "sent"
    current["incidents"]["task:T1"]["state"] = "closed"
    closure = event(
        current,
        "task_incident_closed",
        "family",
        stamped(original_event_id=overdue["id"], incident_generation=1),
        "incident:task:T1:1:close",
    )
    current["incidents"]["task:T1"]["closure_event_id"] = closure["id"]
    return closure


def test_announced_closure_survives_expected_revocations():
    current = state()
    overdue = open_overdue(current)
    closure = close_announced(current, overdue)
    current["settings"]["modules"] = []
    current["members"]["child"].update(active=False, revision=5)
    current["tasks"]["T1"].update(status="completed", assignee="owner")

    assert current_task_event(current, closure)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value, overdue, closure: overdue.pop("deliveries"),
        lambda value, overdue, closure: overdue.update(deliveries={"x": {"state": "pending"}}),
        lambda value, overdue, closure: closure["data"].update(
            original_event_id="incident:task:T1:1:missing"
        ),
        lambda value, overdue, closure: closure["data"].update(incident_generation=2),
        lambda value, overdue, closure: value["outbox"].pop(overdue["id"]),
        lambda value, overdue, closure: overdue["data"].update(member="owner"),
        lambda value, overdue, closure: overdue["data"].update(member_revision=False),
        lambda value, overdue, closure: closure.update(recipient="parents"),
    ],
)
def test_closure_requires_exact_announced_pair(mutate):
    current = state()
    overdue = open_overdue(current)
    closure = close_announced(current, overdue)

    mutate(current, overdue, closure)

    assert not current_task_event(current, closure)


@pytest.mark.parametrize(
    ("key", "recipient", "data", "status"),
    [
        ("task_assigned", "child", {"id": "T1"}, "assigned"),
        (
            "task_reminder",
            "child",
            {"id": "T1", "due_at": "2026-09-08T12:00:00+00:00"},
            "assigned",
        ),
    ],
)
def test_legacy_unstamped_assignee_events_use_current_relationship(key, recipient, data, status):
    current = state()
    current["tasks"]["T1"]["status"] = status
    notification = event(current, key, recipient, data)

    assert current_task_event(current, notification)

    current["tasks"]["T1"]["assignee"] = "owner"
    assert not current_task_event(current, notification)


def test_legacy_unstamped_review_uses_current_submitted_relationship():
    current = state()
    current["tasks"]["T1"]["status"] = "submitted"
    notification = event(current, "task_review", "parents", {"id": "T1"})

    assert current_task_event(current, notification)

    # Legacy review payloads did not record the subject epoch. Submitted tasks
    # cannot be reassigned through the domain, so status and current authority
    # are the strongest backward-compatible checks.
    current["tasks"]["T1"]["status"] = "needs_changes"
    assert not current_task_event(current, notification)


def test_legacy_overdue_and_closure_remain_compatible():
    current = state()
    overdue = open_overdue(current, stamped_event=False)
    assert current_task_event(current, overdue)
    closure = close_announced(current, overdue)
    closure["data"] = {"id": "T1", "member": "child"}
    assert current_task_event(current, closure)


def test_stamped_closure_survives_later_incident_generation():
    current = state()
    overdue = open_overdue(current)
    closure = close_announced(current, overdue)
    current["tasks"]["T1"]["due_at"] = "2026-09-09T12:00:00+00:00"
    later = event(
        current,
        "task_overdue",
        "family",
        stamped(due_at="2026-09-09T12:00:00+00:00"),
        "incident:task:T1:2",
    )
    current["incidents"]["task:T1"] = {
        "id": "task:T1",
        "generation": 2,
        "state": "open",
        "event_id": later["id"],
        "recipient": "family",
    }

    assert current_task_event(current, closure)


def test_closure_rejects_malformed_epoch_but_not_changed_current_epoch():
    current = state()
    overdue = open_overdue(current)
    closure = close_announced(current, overdue)

    current["members"]["child"]["revision"] = 5
    assert current_task_event(current, closure)

    closure["data"]["member_revision"] = None
    assert not current_task_event(current, closure)


def test_maintenance_state_does_not_revoke_materialized_ordinary_task():
    current = state()
    notification = event(current, "task_assigned", "child", stamped())
    current["settings"]["modules"].remove("maintenance")
    current["maintenance"] = {"assets": {"MA1": {"status": "retired"}}}

    assert current_task_event(current, notification)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"key": "task_assigned"},
        {"id": "x", "key": "unknown", "recipient": "child", "data": {"id": "T1"}},
        {"id": "x", "key": "task_assigned", "recipient": "child", "data": None},
        {"id": "x", "key": "task_assigned", "recipient": "child", "data": {"id": []}},
    ],
)
def test_malformed_events_fail_closed_without_crashing(bad):
    assert current_task_event(state(), bad) is False


def test_malformed_current_state_fails_closed():
    current = state()
    notification = event(current, "task_assigned", "child", stamped())

    current["tasks"]["T1"]["status"] = "invented"
    assert not current_task_event(current, notification)

    current = state()
    notification = event(current, "task_assigned", "child", {"id": "T1"})
    current["members"]["child"].pop("revision")
    assert not current_task_event(current, notification)
