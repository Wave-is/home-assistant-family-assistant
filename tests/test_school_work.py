"""School homework reuses private tasks without duplicating their lifecycle."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain import (
    school,
    school_work,
    task_access,
    task_events,
    tasks,
)
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError, timestamp

BAD_REVISIONS = (None, True, False, 1.0, "1", 0, -1, 2**53)


def enabled_state(engine):
    state = engine.snapshot()
    state["settings"]["modules"].append("school")
    return state


def context(state, actor, now, operation="school-work"):
    return Context(state, state["members"][actor], now, operation)


def timetable(state, now, *, member="child", exceptions=None):
    payload = {
        "member": member,
        "member_revision": state["members"][member]["revision"],
        "title": "Autumn timetable",
        "valid_from": "2026-09-07",
        "valid_until": "2026-12-18",
        "lessons": [
            {
                "weekday": 0,
                "start": "09:00",
                "end": "09:45",
                "subject": "Mathematics",
                "room": "12",
                "materials": ["Workbook"],
            },
            {
                "weekday": 2,
                "start": "10:00",
                "end": "10:45",
                "subject": "History",
                "room": "",
                "materials": [],
            },
        ],
        "backpack_routine": None,
        "exceptions": ["2026-09-14"] if exceptions is None else exceptions,
    }
    return school.handle(context(state, "parent", now, "school-table"), "timetable_save", payload)


def lesson_link(record, **changes):
    return {
        "timetable_id": record["id"],
        "timetable_revision": record["revision"],
        "date": "2026-09-07",
        "lesson_index": 0,
        **changes,
    }


def create_payload(state, lesson=None, *, member="child", **changes):
    return {
        "member": member,
        "member_revision": state["members"][member]["revision"],
        "title": "Finish algebra exercises",
        "due_at": "2026-09-08T17:00:00+00:00",
        "checklist": ["Exercises 1-4", "Pack workbook"],
        "reminder_minutes": 30,
        "grace_minutes": 15,
        "lesson": lesson,
        **changes,
    }


def revise_payload(state, task, **changes):
    return {
        "id": task["id"],
        "revision": task["revision"],
        "member_revision": state["members"][task["assignee"]]["revision"],
        "title": "Revised algebra exercises",
        "due_at": "2026-09-09T17:00:00+00:00",
        "reminder_minutes": 45,
        "grace_minutes": 20,
        **changes,
    }


def reject_unchanged(state, call, code="invalid_field", field=None):
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code
    if field is not None:
        assert caught.value.field == field
    assert state == before


def create(state, now, *, actor="child", operation="homework-create", **changes):
    return school_work.handle(
        context(state, actor, now, operation),
        "homework_create",
        create_payload(state, **changes),
    )


def test_child_create_is_opaque_private_and_uses_real_task_contract(engine, now):
    state = enabled_state(engine)
    table = timetable(state, now)
    unrelated = {
        key: deepcopy(state[key])
        for key in ("routine_runs", "court", "calendar", "shopping", "pantry")
    }

    receipt = create(state, now, lesson=lesson_link(table))

    assert receipt == {"id": "T000001", "revision": 1, "status": "assigned"}
    assert set(receipt) == {"id", "revision", "status"}
    task = state["tasks"][receipt["id"]]
    assert task["creator"] == "child" and task["assignee"] == "child"
    assert task["assignee_revision"] == 1
    assert task["delivery_scope"] == "private"
    assert task["deadline_policy"] == {
        "reminder_minutes": 30,
        "grace_minutes": 15,
        "penalty": 0,
    }
    assert task["source"] == {
        "kind": "school_homework",
        "member": "child",
        "member_revision": 1,
        "lesson": lesson_link(table),
    }
    assert school_work.is_homework_task(task)
    assert school_work.current_homework(state, task)
    assert not task_access.may_view(state, state["members"]["sibling"], task)
    assert "source" not in task_access.public_task(task, parent=False)
    notification = next(
        event
        for event in state["outbox"].values()
        if event["key"] == "task_assigned" and event["data"]["id"] == task["id"]
    )
    assert notification["recipient"] == "child"
    assert notification["data"] == {
        "id": task["id"],
        "member": "child",
        "member_revision": 1,
    }
    assert all(state[key] == value for key, value in unrelated.items())

    async def save(_state):
        return None

    projection = plans.projection(Engine(state, save).view("child", now=now))
    assert task["title"] not in str(projection)


def test_create_may_omit_optional_lesson(engine, now):
    state = enabled_state(engine)
    payload = create_payload(state)
    payload.pop("lesson")

    receipt = school_work.handle(context(state, "child", now), "homework_create", payload)

    assert state["tasks"][receipt["id"]]["source"]["lesson"] is None
    school_work.authorize_replay(context(state, "child", now), "homework_create", payload)


def test_parent_and_self_child_create_but_other_roles_cannot_assign_child(engine, now):
    state = enabled_state(engine)
    parent = school_work.handle(
        context(state, "parent", now, "parent-homework"),
        "homework_create",
        create_payload(state),
    )
    assert state["tasks"][parent["id"]]["creator"] == "parent"

    sibling = school_work.handle(
        context(state, "sibling", now, "sibling-homework"),
        "homework_create",
        create_payload(state, member="sibling"),
    )
    assert state["tasks"][sibling["id"]]["assignee"] == "sibling"

    for actor in ("sibling", "adult", "guest"):
        reject_unchanged(
            state,
            lambda actor=actor: school_work.handle(
                context(state, actor, now),
                "homework_create",
                create_payload(state),
            ),
            "forbidden",
        )
    state["members"]["child"]["active"] = False
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "parent", now),
            "homework_create",
            create_payload(state),
        ),
        "unknown_member",
    )


@pytest.mark.parametrize("revision", BAD_REVISIONS)
def test_create_requires_strict_current_child_epoch(engine, now, revision):
    state = enabled_state(engine)
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "child", now),
            "homework_create",
            create_payload(state, member_revision=revision),
        ),
        "invalid_field",
        "member_revision",
    )


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"due_at": "2026-09-08T17:00:00"}, "due_at"),
        ({"checklist": [""]}, "checklist"),
        ({"checklist": "not-a-list"}, "checklist"),
        ({"reminder_minutes": True}, "reminder_minutes"),
        ({"grace_minutes": 1441}, "grace_minutes"),
        ({"unexpected": "field"}, "unexpected"),
    ],
)
def test_create_validation_is_atomic(engine, now, changes, field):
    state = enabled_state(engine)
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "child", now),
            "homework_create",
            create_payload(state, **changes),
        ),
        field=field,
    )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"timetable_revision": 2}, "conflict"),
        ({"date": "2026-09-14"}, "invalid_field"),
        ({"date": "2026-09-08"}, "invalid_field"),
        ({"date": "2027-01-04"}, "invalid_field"),
        ({"lesson_index": 2}, "invalid_field"),
        ({"lesson_index": True}, "invalid_field"),
        ({"extra": "no"}, "invalid_field"),
    ],
)
def test_lesson_link_must_be_an_exact_current_occurrence(engine, now, change, code):
    state = enabled_state(engine)
    table = timetable(state, now)
    reject_unchanged(
        state,
        lambda: create(state, now, lesson=lesson_link(table, **change)),
        code,
    )


def test_lesson_link_rejects_wrong_child_stale_epoch_and_archived_table(engine, now):
    state = enabled_state(engine)
    table = timetable(state, now)
    record = state["school"]["timetables"][table["id"]]
    record["member"] = "sibling"
    reject_unchanged(
        state,
        lambda: create(state, now, lesson=lesson_link(table)),
        "not_found",
    )
    record["member"] = "child"
    state["members"]["child"]["revision"] = 2
    reject_unchanged(
        state,
        lambda: create(
            state,
            now,
            member_revision=2,
            lesson=lesson_link(table),
        ),
        "conflict",
    )
    record["member_revision"] = 2
    record["status"] = "archived"
    reject_unchanged(
        state,
        lambda: create(
            state,
            now,
            member_revision=2,
            lesson=lesson_link(table),
        ),
        "invalid_transition",
    )


@pytest.mark.parametrize(
    "exists,revision,status",
    [
        (False, 1, "active"),
        (True, 1, "active"),
        (True, 2, "active"),
        (True, 1, "archived"),
        (True, 2, "archived"),
    ],
)
def test_child_cannot_probe_sibling_timetable_versions(engine, now, exists, revision, status):
    state = enabled_state(engine)
    table = timetable(state, now)
    record = state["school"]["timetables"][table["id"]]
    record.update(member="sibling", revision=revision, status=status)
    if not exists:
        del state["school"]["timetables"][table["id"]]
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "child", now),
            "homework_create",
            create_payload(state, lesson=lesson_link(table)),
        ),
        "not_found",
    )


def test_parent_revise_resets_progress_and_rebinds_current_epoch(engine, now):
    state = enabled_state(engine)
    table = timetable(state, now)
    created = create(state, now, lesson=lesson_link(table))
    original = state["tasks"][created["id"]]
    original["checklist"][0]["done"] = True
    old_notice = next(
        event for event in state["outbox"].values() if event["key"] == "task_assigned"
    )
    state["members"]["child"]["revision"] = 2
    assert not school_work.current_homework(state, original)

    revised = school_work.handle(
        context(state, "parent", now, "homework-revise"),
        "homework_revise",
        revise_payload(state, original),
    )

    assert revised == {"id": original["id"], "revision": 2, "status": "assigned"}
    task = state["tasks"][created["id"]]
    assert task["title"] == "Revised algebra exercises"
    assert task["due_at"] == "2026-09-09T17:00:00+00:00"
    assert task["checklist"] == [
        {"text": "Exercises 1-4", "done": False},
        {"text": "Pack workbook", "done": False},
    ]
    assert task["source"]["lesson"] == lesson_link(table)
    assert task["assignee_revision"] == 2
    assert task["source"]["member_revision"] == 2
    assert school_work.current_homework(state, task)
    assert old_notice["state"] == "superseded"
    notices = [
        event
        for event in state["outbox"].values()
        if event["key"] == "task_assigned" and event["data"]["id"] == task["id"]
    ]
    assert len(notices) == 2
    assert notices[-1]["data"]["member_revision"] == 2


def _move_to_needs_changes(state, now, task):
    tasks.handle(
        context(state, "child", now, "homework-check"),
        "check",
        {"id": task["id"], "revision": task["revision"], "checklist_index": 0, "done": True},
    )
    tasks.handle(
        context(state, "child", now, "homework-start"),
        "start",
        {"id": task["id"], "revision": task["revision"]},
    )
    tasks.handle(
        context(state, "child", now, "homework-submit"),
        "submit",
        {"id": task["id"], "revision": task["revision"], "report": "PRIVATE OLD REPORT"},
    )
    tasks.handle(
        context(state, "parent", now, "homework-review"),
        "request_changes",
        {"id": task["id"], "revision": task["revision"], "note": "PRIVATE REVIEW NOTE"},
    )


def test_epoch_refresh_archives_parent_only_report_and_resets_current_state(engine, now):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    _move_to_needs_changes(state, now, task)
    old_review = next(
        event
        for event in state["outbox"].values()
        if event["key"] == "task_review" and event["data"]["id"] == task["id"]
    )

    state["members"]["child"]["revision"] = 2
    school_work.handle(
        context(state, "parent", now + timedelta(minutes=1), "epoch-refresh"),
        "homework_revise",
        revise_payload(state, task, due_at=task["due_at"]),
    )

    assert task["status"] == "assigned"
    assert task["report"] is None
    assert "review_note" not in task
    assert all(entry["done"] is False for entry in task["checklist"])
    assert task["previous_reports"] == [
        {
            "assignee": "child",
            "report": "PRIVATE OLD REPORT",
            "review_note": "PRIVATE REVIEW NOTE",
            "reassigned_at": (now + timedelta(minutes=1)).isoformat(),
        }
    ]
    assert "previous_reports" not in task_access.public_task(task, parent=False)
    assert old_review["state"] == "superseded"


def test_epoch_refresh_reissues_reminder_for_unchanged_due_date(engine, now):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    reminder_at = timestamp(task["due_at"], "due_at") - timedelta(minutes=15)
    system = {"id": "system", "role": "system"}
    task_events.tick(Context(state, system, reminder_at, "old-epoch-reminder"))
    old_reminder = next(
        event
        for event in state["outbox"].values()
        if event["key"] == "task_reminder" and event["data"]["id"] == task["id"]
    )
    assert task["deadline_events"][task["due_at"]]["reminded"] == reminder_at.isoformat()

    state["members"]["child"]["revision"] = 2
    school_work.handle(
        context(state, "parent", reminder_at, "epoch-refresh"),
        "homework_revise",
        revise_payload(state, task, due_at=task["due_at"], reminder_minutes=30),
    )
    assert "deadline_events" not in task
    assert old_reminder["state"] == "superseded"

    task_events.tick(Context(state, system, reminder_at, "new-epoch-reminder"))
    reminders = [
        event
        for event in state["outbox"].values()
        if event["key"] == "task_reminder" and event["data"]["id"] == task["id"]
    ]
    assert len(reminders) == 2
    assert reminders[-1]["state"] == "pending"
    assert reminders[-1]["data"]["member_revision"] == 2


def test_same_epoch_revise_preserves_report_review_progress_and_deadline_state(engine, now):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    _move_to_needs_changes(state, now, task)
    task["deadline_events"] = {task["due_at"]: {"reminded": now.isoformat()}}

    school_work.handle(
        context(state, "parent", now, "same-epoch-revise"),
        "homework_revise",
        revise_payload(state, task, due_at=task["due_at"]),
    )

    assert task["status"] == "needs_changes"
    assert task["report"] == "PRIVATE OLD REPORT"
    assert task["review_note"] == "PRIVATE REVIEW NOTE"
    assert task["checklist"][0]["done"] is True
    assert task["deadline_events"] == {task["due_at"]: {"reminded": now.isoformat()}}


@pytest.mark.parametrize("actor", ["child", "sibling", "adult", "guest"])
def test_only_parent_can_revise_homework(engine, now, actor):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, actor, now),
            "homework_revise",
            revise_payload(state, task),
        ),
        "forbidden",
    )


@pytest.mark.parametrize("revision", BAD_REVISIONS)
def test_revise_requires_strict_task_revision(engine, now, revision):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "parent", now),
            "homework_revise",
            revise_payload(state, task, revision=revision),
        ),
        "invalid_field",
    )


def test_revise_conflicts_are_atomic_and_nonhomework_is_not_claimed(engine, now):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "parent", now),
            "homework_revise",
            revise_payload(state, task, revision=task["revision"] + 1),
        ),
        "conflict",
    )
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "parent", now),
            "homework_revise",
            revise_payload(state, task, due_at="not-a-date", title="Would partially write"),
        ),
        field="due_at",
    )
    ordinary = tasks.handle(
        context(state, "parent", now, "ordinary"),
        "create",
        {"title": "Ordinary", "assignee": "child"},
    )
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "parent", now),
            "homework_revise",
            revise_payload(state, ordinary),
        ),
        "not_found",
    )


@pytest.mark.parametrize("status", ["submitted", "completed", "cancelled", "archived"])
def test_revise_rejects_nonrevisable_status_without_side_effects(engine, now, status):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    task["status"] = status
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "parent", now),
            "homework_revise",
            revise_payload(state, task),
        ),
        "invalid_transition",
    )


def test_materialized_homework_survives_timetable_archive_and_school_disable(engine, now):
    state = enabled_state(engine)
    table = timetable(state, now)
    created = create(state, now, lesson=lesson_link(table))
    task = state["tasks"][created["id"]]
    state["school"]["timetables"][table["id"]]["status"] = "archived"
    revised = school_work.handle(
        context(state, "parent", now),
        "homework_revise",
        revise_payload(state, task),
    )
    state["settings"]["modules"].remove("school")
    reject_unchanged(
        state,
        lambda: school_work.handle(
            context(state, "parent", now),
            "homework_revise",
            revise_payload(state, state["tasks"][created["id"]]),
        ),
        "module_disabled",
    )
    started = tasks.handle(
        context(state, "child", now, "homework-start"),
        "start",
        {"id": created["id"], "revision": revised["revision"]},
    )
    assert started["status"] == "in_progress"
    assert state["tasks"][created["id"]]["source"]["lesson"] == lesson_link(table)


def test_replay_rechecks_modules_actor_target_epoch_but_not_old_timetable(engine, now):
    state = enabled_state(engine)
    table = timetable(state, now)
    payload = create_payload(state, lesson_link(table))
    school_work.authorize_replay(context(state, "child", now), "homework_create", payload)
    state["school"]["timetables"].pop(table["id"])
    school_work.authorize_replay(context(state, "child", now), "homework_create", payload)
    state["members"]["child"]["revision"] = 2
    reject_unchanged(
        state,
        lambda: school_work.authorize_replay(
            context(state, "child", now), "homework_create", payload
        ),
        "conflict",
    )
    state["members"]["child"]["revision"] = 1
    state["settings"]["modules"].remove("tasks")
    reject_unchanged(
        state,
        lambda: school_work.authorize_replay(
            context(state, "child", now), "homework_create", payload
        ),
        "module_disabled",
    )


def test_revise_replay_uses_current_task_and_member_not_historical_revision(engine, now):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    payload = revise_payload(state, task)
    school_work.handle(context(state, "parent", now, "revise"), "homework_revise", payload)
    school_work.authorize_replay(context(state, "parent", now), "homework_revise", payload)
    state["tasks"][created["id"]]["status"] = "completed"
    school_work.authorize_replay(context(state, "parent", now), "homework_revise", payload)
    state["members"]["child"]["revision"] = 2
    reject_unchanged(
        state,
        lambda: school_work.authorize_replay(
            context(state, "parent", now), "homework_revise", payload
        ),
        "conflict",
    )


def test_malformed_source_and_unknown_actions_fail_closed(engine, now):
    state = enabled_state(engine)
    created = create(state, now)
    task = state["tasks"][created["id"]]
    task["source"]["extra"] = "untrusted"
    assert school_work.is_homework_task(task)
    assert not school_work.current_homework(state, task)
    reject_unchanged(
        state,
        lambda: school_work.handle(context(state, "parent", now), "unknown", {}),
        "unknown_action",
    )
    reject_unchanged(
        state,
        lambda: school_work.handle(context(state, "parent", now), "homework_create", None),
        field="payload",
    )
