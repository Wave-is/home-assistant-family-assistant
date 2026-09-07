"""Recipient-scoped digest content uses only explicit bounded projections."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.const import MODULES
from custom_components.family_assistant.domain import (
    family_calendar,
    polls,
    school,
    tasks,
)
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.digest_content import has_content, snapshot
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 7, 7, tzinfo=UTC)
START = "2026-09-07"
END = "2026-09-08"
EXCLUDED = "PRIVATE-EXCLUDED-CANARY-91b7"


async def _discard(_state):
    return None


def base_state():
    state = new_state("ha-owner", "Digest household", modules=list(MODULES))
    state["settings"]["modules"].append("digests")
    for member_id, role in (
        ("parent", "parent"),
        ("adult", "adult"),
        ("child", "child"),
        ("sibling", "child"),
        ("guest", "guest"),
    ):
        state["members"][member_id] = {
            "id": member_id,
            "name": member_id.title(),
            "role": role,
            "language": "en",
            "ha_user_id": f"ha-{member_id}",
            "aliases": [],
            "active": True,
            "revision": 1,
        }
    return Engine(state, _discard).snapshot()


def ctx(state, actor="owner", now=NOW, operation="digest-fixture"):
    return Context(state, state["members"][actor], now, operation)


def section(result, key):
    return next(item for item in result["sections"] if item["key"] == key)


def take(state, actor="child", kind="morning", start=START, end=END, now=NOW):
    return snapshot(state, state["members"][actor], kind, start, end, now)


def add_task(state, assignee, title, due, *, report=None):
    item = tasks.handle(
        ctx(state),
        "create",
        {"title": title, "assignee": assignee, "due_at": due, "report_type": "text"},
    )
    stored = state["tasks"][item["id"]]
    if report is not None:
        stored["report"] = report
        stored["review_note"] = EXCLUDED
        stored["previous_reports"] = [{"report": EXCLUDED}]
    return stored


def add_event(state, title, participants, *, visibility="participants", hour=9):
    return family_calendar.handle(
        ctx(state),
        "save",
        {
            "title": title,
            "start": f"2026-09-07T{hour:02}:00:00+00:00",
            "end": f"2026-09-07T{hour:02}:30:00+00:00",
            "participants": participants,
            "visibility": visibility,
            "description": EXCLUDED,
            "location": EXCLUDED,
        },
    )


def test_empty_envelope_argument_bounds_actor_scope_and_immutability():
    state = base_state()
    before = deepcopy(state)
    result = take(state)
    assert result == {
        "schema": 1,
        "kind": "morning",
        "window_start": START,
        "window_end": END,
        "sections": [],
    }
    assert has_content(result) is False
    assert state == before

    state["settings"]["modules"].remove("digests")
    assert take(state)["sections"] == []
    state["settings"]["modules"].append("digests")
    assert take(state, "guest")["sections"] == []
    stale = deepcopy(state["members"]["child"])
    stale["revision"] += 1
    assert snapshot(state, stale, "morning", START, END, NOW)["sections"] == []
    # Daily delivery never reads yesterday; weekly's 24-hour TTL may cross a
    # local-date boundary and therefore permits exactly one prior start day.
    with pytest.raises(DomainError):
        snapshot(
            state,
            state["members"]["child"],
            "morning",
            "2026-09-06",
            "2026-09-07",
            NOW,
        )
    prior_week = snapshot(
        state,
        state["members"]["child"],
        "weekly",
        "2026-09-06",
        "2026-09-13",
        NOW,
    )
    assert prior_week["sections"] == []

    for args in (
        ("daily", START, END, NOW),
        ("morning", "20260907", END, NOW),
        ("morning", START, "2026-09-09", NOW),
        ("weekly", START, END, NOW),
        ("morning", "2026-08-01", "2026-08-02", NOW),
    ):
        with pytest.raises(DomainError):
            snapshot(state, state["members"]["child"], *args)
    assert has_content({"sections": [{"key": "forged"}]}) is False
    forged = {
        **result,
        "sections": [{"key": "shopping", "rows": [EXCLUDED], "count": 1, "overflow": 0}],
    }
    assert has_content(forged) is False
    forged["sections"] = [{"key": "shopping", "rows": [], "count": True, "overflow": 0}]
    assert has_content(forged) is False
    forged["sections"] = [
        {
            "key": "tasks",
            "rows": [
                {
                    "title": "Task",
                    "status": "assigned",
                    "due_at": END,
                    "id": EXCLUDED,
                }
            ],
            "count": 1,
            "overflow": 0,
        }
    ]
    assert has_content(forged) is False


def test_tasks_are_personal_details_parent_counts_and_cap_without_reports():
    state = base_state()
    for index in range(12):
        add_task(
            state,
            "child",
            f"Child task {index:02}",
            f"2026-09-07T{8 + index // 4:02}:{(index % 4) * 10:02}:00+00:00",
            report=EXCLUDED if index == 0 else None,
        )
    add_task(state, "sibling", "Sibling title canary", "2026-09-07T10:59:00+00:00")
    add_task(state, "child", "Tomorrow", "2026-09-08T09:00:00+00:00")

    child = take(state)
    own = section(child, "tasks")
    assert (own["count"], len(own["rows"]), own["overflow"]) == (12, 10, 2)
    assert own["rows"][0] == {
        "title": "Child task 00",
        "status": "assigned",
        "due_at": "2026-09-07T08:00:00+00:00",
    }
    encoded = json.dumps(child)
    assert "Sibling title canary" not in encoded
    assert EXCLUDED not in encoded

    parent = take(state, "parent")
    counts = section(parent, "tasks")
    assert counts == {"key": "tasks", "rows": [], "count": 13, "overflow": 0}


def test_calendar_details_require_relationship_while_other_visible_is_counted():
    state = base_state()
    add_event(state, "Own occurrence", ["child"])
    add_event(state, "Family-only title", ["sibling"], visibility="family", hour=10)
    add_event(state, "Tentative excluded", ["child"], hour=11)["status"] = "tentative"

    result = take(state)
    calendar = section(result, "calendar")
    assert calendar == {
        "key": "calendar",
        "rows": [
            {
                "title": "Own occurrence",
                "start": "2026-09-07T09:00:00Z",
                "all_day": False,
            }
        ],
        "count": 2,
        "overflow": 0,
    }
    encoded = json.dumps(result)
    assert "Family-only title" not in encoded
    assert "Tentative excluded" not in encoded
    assert EXCLUDED not in encoded


def test_current_routine_step_is_detailed_but_other_shared_run_is_count_only():
    state = base_state()
    state["routine_runs"] = {
        "R2": {
            "id": "R2",
            "template_id": "RT2",
            "title": "Sibling routine canary",
            "member": "sibling",
            "planned_at": "2026-09-07T07:00:00+00:00",
            "status": "active",
            "steps": [{"title": "Sibling step", "status": "active", "member": "sibling"}],
        },
        "R1": {
            "id": "R1",
            "template_id": "RT1",
            "title": "Own routine",
            "member": "child",
            "planned_at": "2026-09-07T06:00:00+00:00",
            "status": "active",
            "steps": [
                {
                    "title": "Own current step",
                    "status": "active",
                    "member": "child",
                    "completion_condition": {"entity": EXCLUDED},
                    "nonce": EXCLUDED,
                }
            ],
        },
    }
    child = take(state)
    assert section(child, "routines") == {
        "key": "routines",
        "rows": [{"routine_title": "Own routine", "step_title": "Own current step"}],
        "count": 1,
        "overflow": 0,
    }
    parent = take(state, "parent")
    parent_section = section(parent, "routines")
    assert parent_section["count"] == 2 and parent_section["rows"] == []
    assert EXCLUDED not in json.dumps(child)
    assert "Sibling routine canary" not in json.dumps(parent)


def test_school_child_details_parent_count_and_material_bound():
    state = base_state()
    school.handle(
        ctx(state),
        "timetable_save",
        {
            "member": "child",
            "member_revision": 1,
            "title": "Private timetable canary",
            "valid_from": "2026-09-01",
            "valid_until": "2026-12-31",
            "exceptions": [],
            "backpack_routine": None,
            "lessons": [
                {
                    "weekday": 0,
                    "start": "09:00",
                    "end": "09:45",
                    "subject": "Mathematics",
                    "room": EXCLUDED,
                    "materials": [f"Material {index}" for index in range(12)],
                }
            ],
        },
    )
    child = section(take(state), "school")
    assert child["count"] == 1 and child["overflow"] == 0
    assert child["rows"][0] == {
        "date": "2026-09-07",
        "subject": "Mathematics",
        "start": "09:00",
        "materials": [f"Material {index}" for index in range(10)],
    }
    parent = section(take(state, "parent"), "school")
    assert parent == {"key": "school", "rows": [], "count": 1, "overflow": 0}
    assert EXCLUDED not in json.dumps(take(state))
    assert "Private timetable canary" not in json.dumps(take(state, "parent"))


def test_counts_only_sources_never_emit_names_notes_quantities_or_ballots():
    state = base_state()
    state["dietary_profiles"] = {"child": {"allergy_note": EXCLUDED}}
    state["presence"]["observations"] = {"child": {"state": EXCLUDED}}
    state["media"] = {"M1": {"sha256": EXCLUDED}}
    state["audit"] = [{"payload": EXCLUDED}]
    state["court"] = {"C1": {"reason": EXCLUDED}}
    state["shopping"]["S1"] = {
        "id": "S1",
        "name": EXCLUDED,
        "quantity": 2.0,
        "purchased": 0.5,
        "status": "approved",
        "note": EXCLUDED,
    }
    state["pantry"] = {
        "items": {
            "P1": {
                "id": "P1",
                "status": "active",
                "name": EXCLUDED,
                "quantity": 1.0,
                "minimum_quantity": 2.0,
                "unit": "item",
                "expires_on": START,
                "note": EXCLUDED,
            }
        },
        "suggestions": {},
    }
    fault_task = add_task(state, "child", EXCLUDED, "2026-09-08T09:00:00+00:00", report=EXCLUDED)
    state["maintenance"] = {
        "assets": {},
        "faults": {
            "MF1": {
                "id": "MF1",
                "summary": EXCLUDED,
                "details": EXCLUDED,
                "task_id": fault_task["id"],
                "reporter": "child",
                "reporter_member_revision": 1,
            }
        },
        "service_logs": {},
    }
    polls.handle(
        ctx(state),
        "create",
        {
            "actor_revision": 1,
            "question": EXCLUDED,
            "options": [EXCLUDED, "Other"],
            "eligible": [{"member": "child", "revision": 1}],
            "closes_at": (NOW + timedelta(hours=1)).isoformat(),
            "confirm_private_ballot_limits": True,
        },
    )
    closed = polls.handle(
        ctx(state, operation="second-poll"),
        "create",
        {
            "actor_revision": 1,
            "question": EXCLUDED,
            "options": ["Yes", "No"],
            "eligible": [{"member": "child", "revision": 1}],
            "closes_at": (NOW + timedelta(hours=2)).isoformat(),
            "confirm_private_ballot_limits": True,
        },
    )
    polls.handle(
        ctx(state, operation="close-poll"),
        "close",
        {"id": closed["id"], "revision": closed["revision"], "actor_revision": 1},
    )

    result = take(state)
    assert section(result, "shopping")["count"] == 1
    assert section(result, "pantry_low_stock")["count"] == 1
    assert section(result, "pantry_expiring")["count"] == 1
    assert section(result, "maintenance_faults")["count"] == 1
    assert section(result, "polls_open")["count"] == 1
    assert section(result, "polls_results")["count"] == 1
    assert all(not item["rows"] for item in result["sections"])
    assert EXCLUDED not in json.dumps(result)


def test_each_source_module_gate_removes_only_its_sections():
    state = base_state()
    add_task(state, "child", "Task", "2026-09-07T09:00:00+00:00")
    add_event(state, "Event", ["child"])
    full = take(state)
    assert {item["key"] for item in full["sections"]} == {"tasks", "calendar"}

    state["settings"]["modules"].remove("calendar")
    gated = take(state)
    assert {item["key"] for item in gated["sections"]} == {"tasks"}
    state["settings"]["modules"].remove("tasks")
    assert take(state)["sections"] == []


def test_weekly_window_is_bounded_and_deterministic():
    state = base_state()
    add_task(state, "child", "First", "2026-09-08T08:00:00+00:00")
    add_task(state, "child", "Last", "2026-09-14T20:00:00+00:00")
    add_task(state, "child", "Outside", "2026-09-15T00:00:00+00:00")
    before = deepcopy(state)
    first = take(state, kind="weekly", start="2026-09-08", end="2026-09-15")
    second = take(state, kind="weekly", start="2026-09-08", end="2026-09-15")
    assert first == second
    assert [row["title"] for row in section(first, "tasks")["rows"]] == ["First", "Last"]
    assert state == before
    assert has_content(first) is True
