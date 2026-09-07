"""Synthetic task conversion tests, without reading or applying live household data."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.migration.review import (
    ASSISTANT_KEY,
    COURT_KEY,
    read_store_pair,
)
from custom_components.family_assistant.migration.task_plan import (
    TaskPlanError,
    build_task_plan,
)

STAMP = "2026-09-07T08:00:00+00:00"


def wrapped(data, key):
    return json.dumps({"key": key, "version": 1, "data": data}).encode()


def fixture():
    state = new_state("fictional-ha-user", "Fictional household")
    state["members"]["child"] = {
        "id": "child",
        "revision": 1,
        "active": True,
        "role": "child",
        "name": "Nika",
        "language": "en",
    }
    row = {
        "task_id": "T000001",
        "kind": "task",
        "state": "accepted",
        "title": "Clean bedroom",
        "creator": "old-parent",
        "assignee": "old-child",
        "reviewer": None,
        "created_at": STAMP,
        "due_at": STAMP,
        "requires_report": False,
        "report_type": None,
        "last_note": None,
        "submitted_at": None,
        "metadata": {
            "arbitrary_secret": "opaque-task-secret",
        },
    }
    ledger = {
        "schema_version": 1,
        "tasks": {row["task_id"]: row},
        "history": [
            {
                "task_id": row["task_id"],
                "sequence": 1,
                "actor": "old-parent",
                "type": "assigned",
                "at": STAMP,
                "details": None,
                "from_state": None,
                "to_state": "assigned",
                "opaque": "fictional-event-secret",
            }
        ],
        "processed_commands": {"old-receipt": {"anything": "not-new-authority"}},
        "next_task_sequence": 2,
        "next_event_sequence": 2,
    }
    court = {
        "schema_version": 1,
        "week_id": "old-period",
        "opened_at": STAMP,
        "children": {},
        "history": [],
        "archived_weeks": [],
        "processed_messages": {},
    }
    mapping = {
        "old-parent": {"member_id": "owner", "member_revision": 1},
        "old-child": {"member_id": "child", "member_revision": 1},
    }
    return ledger, court, mapping, state


def plan_for(ledger, court, mapping, state, *, envelope=True):
    assistant = {"ledger": ledger} if envelope else ledger
    review = read_store_pair(wrapped(assistant, ASSISTANT_KEY), wrapped(court, COURT_KEY)).review(
        mapping, state["members"], mapping_revision=1
    )
    return review, build_task_plan(review, members=state["members"])


@pytest.mark.parametrize("envelope", [True, False])
def test_partial_records_and_exact_private_archive(envelope):
    args = fixture()
    before = deepcopy(args)
    review, plan = plan_for(*args, envelope=envelope)
    private = plan.private_data()
    assert args == before
    assert private["blocked"] == []
    assert private["archive"] == {"tasks": args[0]["tasks"], "history": args[0]["history"]}
    proposal = private["proposals"][0]
    assert proposal["source_task"] == "T000001"
    assert proposal["target_bindings"] == {
        "creator": args[2]["old-parent"],
        "assignee": args[2]["old-child"],
    }
    assert proposal["record"] == {
        "title": "Clean bedroom",
        "creator": "owner",
        "assignee": "child",
        "assignee_revision": 1,
        "created_at": STAMP,
        "due_at": STAMP,
        "status": "accepted",
        "report_type": "none",
        "report": None,
        "deadline_policy": {
            "reminder_minutes": 0,
            "grace_minutes": 0,
            "penalty": 0,
        },
        "checklist": [],
    }
    summary = plan.summary()
    assert summary["mode"] == "task_plan_proposal"
    assert summary["source_items_count"] == 1
    assert summary["record_proposals_count"] == 1
    assert summary["blocked_items_count"] == 0
    assert summary["archived_history_count"] == 1
    assert summary["review_fingerprint"] == review.summary()["fingerprint"]
    assert summary["import_available"] is False
    assert summary["coherence_verified"] is False
    assert "processed_commands" not in private["archive"]
    assert repr(plan) == "TaskPlan(private=True, import_available=False)"


def test_privacy_and_immutability():
    args = fixture()
    review, plan = plan_for(*args)
    summary_str = json.dumps(plan.summary())
    repr_str = repr(plan)
    for sensitive in (
        "Clean bedroom",
        "T000001",
        "old-parent",
        "old-child",
        "opaque-task-secret",
        "fictional-event-secret",
        STAMP,
    ):
        assert sensitive not in summary_str
        assert sensitive not in repr_str

    private = plan.private_data()
    private["proposals"].clear()
    private["archive"]["tasks"].clear()
    plan.summary()["issues"].append("external-mutation")
    assert len(plan.private_data()["proposals"]) == 1
    assert len(plan.private_data()["archive"]["tasks"]) == 1
    assert plan.summary()["issues"] == []

    with pytest.raises(FrozenInstanceError):
        plan._summary = b"{}"


def test_empty_source_and_shopping_exclusion():
    args = fixture()
    args[0]["tasks"] = {}
    args[0]["history"] = []
    _, plan = plan_for(*args)
    assert plan.private_data() == {
        "proposals": [],
        "blocked": [],
        "archive": {"tasks": {}, "history": []},
    }
    assert plan.summary()["source_items_count"] == 0
    assert plan.summary()["record_proposals_count"] == 0
    assert plan.summary()["blocked_items_count"] == 0

    # A shopping kind task in ledger is ignored by task_plan
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row["kind"] = "shopping"
    row["metadata"].update(
        shopping_quantity=1,
        shopping_remaining_quantity=1,
        shopping_approval="pending",
    )
    _, plan = plan_for(*args)
    assert plan.summary()["source_items_count"] == 0
    assert plan.private_data()["proposals"] == []
    assert plan.private_data()["archive"]["tasks"] == {}


@pytest.mark.parametrize(
    "source_state,expected_status",
    [
        ("assigned", "assigned"),
        ("accepted", "accepted"),
        ("in_progress", "in_progress"),
        ("completed", "completed"),
        ("cancelled", "cancelled"),
        ("archived", "archived"),
    ],
)
def test_supported_statuses(source_state, expected_status):
    args = fixture()
    args[0]["tasks"]["T000001"]["state"] = source_state
    _, plan = plan_for(*args)
    assert plan.summary()["blocked_items_count"] == 0
    record = plan.private_data()["proposals"][0]["record"]
    assert record["status"] == expected_status


@pytest.mark.parametrize(
    "from_state,expected_status",
    [
        ("assigned", "assigned"),
        ("accepted", "accepted"),
        ("in_progress", "in_progress"),
    ],
)
def test_overdue_with_valid_metadata(from_state, expected_status):
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row["state"] = "overdue"
    row["metadata"]["overdue_from_state"] = from_state
    _, plan = plan_for(*args)
    assert plan.summary()["blocked_items_count"] == 0
    record = plan.private_data()["proposals"][0]["record"]
    assert record["status"] == expected_status


@pytest.mark.parametrize(
    "invalid_metadata",
    [
        {},
        {"overdue_from_state": None},
        {"overdue_from_state": "completed"},
        {"overdue_from_state": "archived"},
        {"overdue_from_state": "cancelled"},
        {"overdue_from_state": "submitted"},
        {"overdue_from_state": "unknown_state"},
    ],
)
def test_overdue_requires_valid_overdue_from_state_never_guesses_accepted(invalid_metadata):
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row["state"] = "overdue"
    row["metadata"] = invalid_metadata
    _, plan = plan_for(*args)
    assert plan.summary()["record_proposals_count"] == 0
    assert plan.summary()["blocked_items_count"] == 1
    assert plan.summary()["issues"] == [{"code": "task_overdue_state_unsupported", "count": 1}]
    assert plan.private_data()["blocked"] == [
        {"source_task": "T000001", "code": "task_overdue_state_unsupported"}
    ]


@pytest.mark.parametrize("status", ["pending_approval", "submitted", "needs_changes"])
def test_unsupported_statuses_blocked_never_silently_reopened(status):
    args = fixture()
    args[0]["tasks"]["T000001"]["state"] = status
    _, plan = plan_for(*args)
    assert plan.summary()["record_proposals_count"] == 0
    assert plan.summary()["blocked_items_count"] == 1
    assert plan.summary()["issues"] == [{"code": "task_state_unsupported", "count": 1}]
    assert plan.private_data()["blocked"] == [
        {"source_task": "T000001", "code": "task_state_unsupported"}
    ]


def test_reminders_preserve_personal_scope():
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row["kind"] = "reminder"
    row["assignee"] = "old-parent"  # preflight requires creator == assignee for reminders
    _, plan = plan_for(*args)
    assert plan.summary()["record_proposals_count"] == 1
    assert plan.summary()["blocked_items_count"] == 0
    assert plan.summary()["issues"] == []
    record = plan.private_data()["proposals"][0]["record"]
    assert record["delivery_scope"] == "personal"
    assert record["creator"] == record["assignee"] == "owner"
    # Raw reminder is still preserved in private archive.
    assert "T000001" in plan.private_data()["archive"]["tasks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_owner,actor", [("old-parent", "owner"), ("old-child", "child")])
async def test_proposed_personal_reminder_keeps_real_target_privacy_and_lifecycle(
    source_owner, actor
):
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row.update(kind="reminder", creator=source_owner, assignee=source_owner)
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    assert record["creator"] == record["assignee"] == actor
    args[3]["tasks"]["T000001"] = {"id": "T000001", "revision": 1, **record}
    saved = []

    async def persist(value):
        saved.append(deepcopy(value))

    engine = Engine(args[3], persist)
    for current in ["owner", "child"]:
        assert len(engine.view(current)["tasks"]) == (1 if current == actor else 0)
    task = await engine.execute(
        actor,
        "tasks.complete",
        {"id": "T000001", "revision": 1},
        "finish",
        datetime.fromisoformat(STAMP),
    )
    assert task["status"] == "completed" and task["delivery_scope"] == "personal"
    restored = Engine(saved[-1], persist)
    assert restored.view(actor)["tasks"] == engine.view(actor)["tasks"]


@pytest.mark.parametrize("report_type", ["photo", "text"])
def test_report_required_task_blocked_with_task_report_review_required(report_type):
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row["requires_report"] = True
    row["report_type"] = report_type
    _, plan = plan_for(*args)
    assert plan.summary()["record_proposals_count"] == 0
    assert plan.summary()["blocked_items_count"] == 1
    assert plan.summary()["issues"] == [{"code": "task_report_review_required", "count": 1}]
    assert plan.private_data()["blocked"] == [
        {"source_task": "T000001", "code": "task_report_review_required"}
    ]


def test_task_with_reviewer_blocked_with_task_report_review_required():
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row["reviewer"] = "old-parent"
    _, plan = plan_for(*args)
    assert plan.summary()["record_proposals_count"] == 0
    assert plan.summary()["blocked_items_count"] == 1
    assert plan.summary()["issues"] == [{"code": "task_report_review_required", "count": 1}]


@pytest.mark.parametrize(
    "changes",
    [
        {"requires_report": None},
        {"requires_report": "true"},
        {"requires_report": True, "report_type": None},
        {"requires_report": True, "report_type": "invalid"},
        {"requires_report": False, "report_type": "photo"},
        {"requires_report": False, "report_type": "text"},
        {"requires_report": False, "submitted_at": STAMP},
        {"requires_report": False, "last_note": "some note"},
    ],
)
def test_invalid_report_combinations_blocked(changes):
    args = fixture()
    args[0]["tasks"]["T000001"].update(changes)
    _, plan = plan_for(*args)
    assert plan.summary()["record_proposals_count"] == 0
    assert plan.summary()["blocked_items_count"] == 1
    assert plan.summary()["issues"] == [{"code": "task_report_settings_unsupported", "count": 1}]
    assert plan.private_data()["blocked"] == [
        {"source_task": "T000001", "code": "task_report_settings_unsupported"}
    ]


@pytest.mark.parametrize("title", ["", "   ", "x" * 501])
def test_title_validation(title):
    args = fixture()
    args[0]["tasks"]["T000001"]["title"] = title
    if not title.strip() or len(title) > 500:
        # If title fails preflight, test by inspecting planner directly
        from custom_components.family_assistant.migration.task_plan import _record

        with pytest.raises(TaskPlanError, match="^task_title_unsupported$"):
            _record(args[0]["tasks"]["T000001"], args[2])


def test_lossless_archive_preserves_every_task_reminder_and_history():
    args = fixture()
    reminder_row = {
        "task_id": "T000002",
        "kind": "reminder",
        "state": "assigned",
        "title": "Drink water",
        "creator": "old-parent",
        "assignee": "old-parent",
        "reviewer": None,
        "created_at": STAMP,
        "due_at": STAMP,
        "requires_report": False,
        "report_type": None,
        "last_note": None,
        "submitted_at": None,
        "metadata": {},
    }
    args[0]["tasks"]["T000002"] = reminder_row
    args[0]["history"].append(
        {
            "task_id": "T000002",
            "sequence": 2,
            "actor": "old-parent",
            "type": "created",
            "at": STAMP,
            "details": "Drink water note",
            "from_state": None,
            "to_state": "assigned",
        }
    )
    args[0]["next_task_sequence"] = 3
    args[0]["next_event_sequence"] = 3
    _, plan = plan_for(*args)
    assert plan.summary()["source_items_count"] == 2
    assert plan.summary()["record_proposals_count"] == 2
    assert plan.summary()["blocked_items_count"] == 0
    assert plan.summary()["archived_history_count"] == 2
    assert plan.private_data()["archive"]["tasks"]["T000001"] == args[0]["tasks"]["T000001"]
    assert plan.private_data()["archive"]["tasks"]["T000002"] == reminder_row
    assert len(plan.private_data()["archive"]["history"]) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 2),
        ("active", False),
        ("role", "parent"),
        ("telegram_id", 9911),
        ("ha_user_id", "new-binding"),
    ],
)
def test_member_change_revokes_proposal(field, value):
    args = fixture()
    review, _ = plan_for(*args)
    args[3]["members"]["child"][field] = value
    with pytest.raises(TaskPlanError, match="^review_changed$"):
        build_task_plan(review, members=args[3]["members"])


def test_invalid_or_forged_review_rejected():
    args = fixture()
    review, _ = plan_for(*args)
    with pytest.raises(TaskPlanError, match="^invalid_review$"):
        build_task_plan(None)
    with pytest.raises(TaskPlanError, match="^review_changed$"):
        build_task_plan(review)
    with pytest.raises(TaskPlanError, match="^review_changed$"):
        build_task_plan(replace(review, _fingerprint="x" * 64), members=args[3]["members"])


def test_deterministic_fingerprint_pins_every_source_change():
    args = fixture()
    _, first = plan_for(*args)
    _, repeated = plan_for(*args)
    assert first.summary() == repeated.summary()
    args[0]["processed_commands"]["unrelated-source-change"] = {}
    _, changed = plan_for(*args)
    assert first.summary()["fingerprint"] != changed.summary()["fingerprint"]


@pytest.mark.asyncio
async def test_real_modern_engine_field_and_lifecycle_compatibility():
    args = fixture()
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    saved = []

    async def persist(value):
        saved.append(deepcopy(value))

    engine = Engine(args[3], persist)
    now = datetime.fromisoformat(STAMP).astimezone(UTC)

    # 1. Compatibility with modern task creation command
    created = await engine.execute(
        "owner",
        "tasks.create",
        {
            "title": record["title"],
            "assignee": record["assignee"],
            "due_at": record["due_at"],
            "report_type": record["report_type"],
            "reminder_minutes": record["deadline_policy"]["reminder_minutes"],
            "grace_minutes": record["deadline_policy"]["grace_minutes"],
            "penalty": record["deadline_policy"]["penalty"],
        },
        "fictional-task-create",
        now,
    )
    assert created["title"] == record["title"]
    assert created["assignee"] == record["assignee"]
    assert created["assignee_revision"] == record["assignee_revision"]
    assert created["creator"] == record["creator"]
    assert created["due_at"] == record["due_at"]
    assert created["report_type"] == record["report_type"]
    assert created["report"] == record["report"]
    assert created["deadline_policy"] == record["deadline_policy"]
    assert created["checklist"] == record["checklist"]

    # 2. Lifecycle operations on synthetic state seeded with proposed record
    synthetic_id = "T000001"
    args[3]["tasks"][synthetic_id] = {
        "id": synthetic_id,
        "revision": 1,
        **record,
    }
    engine = Engine(args[3], persist)
    assert engine.snapshot()["tasks"][synthetic_id]["status"] == "accepted"
    # Initial status is "accepted"
    started = await engine.execute(
        "child",
        "tasks.start",
        {"id": synthetic_id, "revision": 1},
        "start-task",
        now,
    )
    assert started["status"] == "in_progress"

    completed = await engine.execute(
        "owner",
        "tasks.complete",
        {"id": synthetic_id, "revision": started["revision"]},
        "complete-task",
        now,
    )
    assert completed["status"] == "completed"

    # A completed record is inert. Zero policy alone does NOT suppress overdue
    # incidents for an open past-due task; a future shadow must keep modules off.
    await engine.tick(now)
    assert not any(e.get("key") == "task_overdue" for e in engine.snapshot()["outbox"].values())


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"requires_report": True, "report_type": []}, "task_report_settings_unsupported"),
        ({"requires_report": True, "report_type": {}}, "task_report_settings_unsupported"),
        ({"report_type": "none"}, "task_report_settings_unsupported"),
        (
            {"state": "overdue", "metadata": {"overdue_from_state": []}},
            "task_overdue_state_unsupported",
        ),
        (
            {"state": "overdue", "metadata": {"overdue_from_state": {}}},
            "task_overdue_state_unsupported",
        ),
        (
            {
                "state": "overdue",
                "metadata": {"overdue_from_state": "assigned"},
                "accepted_at": STAMP,
            },
            "task_overdue_progress_review_required",
        ),
        (
            {
                "state": "overdue",
                "metadata": {"overdue_from_state": "accepted"},
                "started_at": STAMP,
            },
            "task_overdue_progress_review_required",
        ),
        ({"started_at": "2026-09-07T08:00:00"}, "task_lifecycle_timestamp_unsupported"),
        ({"completed_at": {}}, "task_lifecycle_timestamp_unsupported"),
        ({"state": "archived", "archived_from_state": "overdue"}, "task_archive_state_unsupported"),
    ],
)
def test_malformed_fields_or_later_overdue_progress_are_not_guessed(changes, code):
    args = fixture()
    args[0]["tasks"]["T000001"].update(changes)
    _, plan = plan_for(*args)
    assert plan.summary()["issues"] == [{"code": code, "count": 1}]
    assert plan.private_data()["archive"]["tasks"] == args[0]["tasks"]


def test_known_lifecycle_dates_and_archived_state_are_preserved_without_invention():
    args = fixture()
    row = args[0]["tasks"]["T000001"]
    row.update(state="completed", accepted_at=STAMP, started_at=STAMP, completed_at=STAMP)
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    assert record["closed_at"] == record["accepted_at"] == record["started_at"] == STAMP
    row.update(state="archived", archived_from_state="completed", archived_at=STAMP)
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    assert record["previous_status"] == "completed" and record["archived_at"] == STAMP


def test_unknown_state_rejected_by_source_preflight():
    from custom_components.family_assistant.migration.review import LegacyReviewError

    args = fixture()
    args[0]["tasks"]["T000001"]["state"] = "unknown"
    with pytest.raises(LegacyReviewError, match="^source_preflight_failed$"):
        plan_for(*args)
