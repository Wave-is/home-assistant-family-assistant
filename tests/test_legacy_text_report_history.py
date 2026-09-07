"""Synthetic explicit history, immutable proposals and actual Engine contracts."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_legacy_task_plan import fixture, plan_for

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.migration.task_reports import (
    ReportHistoryError,
    project_text_history,
)

BASE = datetime(2026, 9, 7, 8, tzinfo=UTC)


def source(rounds=2, report="First report", terminal=None):
    ledger, court, mapping, state = fixture()
    row = ledger["tasks"]["T000001"]
    row.update(state="assigned", requires_report=True, report_type="text", reviewer="old-parent")
    events = []

    def add(kind, actor, destination, details):
        stamp = (BASE + timedelta(minutes=len(events))).isoformat()
        events.append(
            {
                "task_id": row["task_id"],
                "sequence": len(events) + 1,
                "type": kind,
                "actor": actor,
                "at": stamp,
                "from_state": row["state"] if events else None,
                "to_state": destination,
                "details": details,
            }
        )
        row["state"] = destination
        return stamp

    add(
        "created",
        "old-parent",
        "assigned",
        {
            "assignee": "old-child",
            "reviewer": "old-parent",
            "requires_report": True,
            "report_type": "text",
        },
    )
    for index in range(rounds):
        body = report if index == 0 else f"Corrected {index}"
        row["submitted_at"] = add("submitted", "old-child", "submitted", {"report": body})
        row["last_note"] = body or None
        if index < rounds - 1 or terminal == "needs_changes":
            add("changes_requested", "old-parent", "needs_changes", {"note": f"Review {index}"})
            row["last_note"] = f"Review {index}"
    if terminal in {"completed", "cancelled", "archived"}:
        prior = row["state"]
        stamp = add(
            terminal,
            "old-parent",
            terminal,
            {"note": "Distinct terminal note", "direct_parent_confirmation": rounds == 0},
        )
        row["last_note"] = "Distinct terminal note"
        row[
            {"completed": "completed_at", "cancelled": "cancelled_at", "archived": "archived_at"}[
                terminal
            ]
        ] = stamp
        if terminal == "archived":
            row["archived_from_state"] = prior
    ledger["history"] = events
    ledger["next_event_sequence"] = len(events) + 1
    return ledger, court, mapping, state


def project(args):
    ledger, _, mapping, state = args
    return project_text_history(
        ledger["tasks"]["T000001"], ledger["history"], mapping, state["members"]
    )


@pytest.mark.parametrize("rounds", [0, 1, 2, 3])
@pytest.mark.parametrize("terminal", [None, "completed", "cancelled", "archived"])
def test_supported_text_history_preserves_all_rounds_and_terminal_notes(rounds, terminal):
    args = source(rounds=rounds, terminal=terminal)
    before = deepcopy(args)
    _, plan = plan_for(*args)
    assert not plan.private_data()["blocked"]
    proposal = plan.private_data()["proposals"][0]
    record = proposal["record"]
    assert proposal["target_bindings"]["reviewer"] == args[2]["old-parent"]
    assert proposal["review_policy"] == "household_parents"
    assert record["report"] == (
        None if not rounds else "First report" if rounds == 1 else f"Corrected {rounds - 1}"
    )
    assert len(record.get("previous_reports", [])) == max(0, rounds - 1)
    if rounds > 1:
        assert record["previous_reports"][0]["report"] == "First report"
        assert record["previous_reports"][0]["review_note"] == "Review 0"
        assert record["previous_reports"][0]["assignee_revision"] == 1
    if terminal:
        key = {
            "completed": "completion_note",
            "cancelled": "cancellation_note",
            "archived": "archive_note",
        }[terminal]
        assert record[key] == "Distinct terminal note"
    assert args == before and plan.private_data()["archive"]["history"] == args[0]["history"]
    assert not plan.summary()["import_available"] and not plan.summary()["coherence_verified"]


@pytest.mark.parametrize("report", ["", "x" * 2000])
def test_exact_legacy_empty_or_maximum_text_is_not_fabricated(report):
    result = project(source(rounds=1, report=report))
    assert result["fields"]["report"] == report


def test_returned_report_and_note_remain_distinct():
    result = project(source(rounds=1, terminal="needs_changes"))["fields"]
    assert result["report"] == "First report" and result["review_note"] == "Review 0"


def test_equivalent_current_timestamp_preserves_source_row_offset():
    args = source(rounds=1)
    args[0]["tasks"]["T000001"]["submitted_at"] = "2026-09-07T10:01:00+02:00"
    assert project(args)["fields"]["submitted_at"] == "2026-09-07T10:01:00+02:00"


@pytest.mark.parametrize(
    "previous, stamp_key", [("completed", "completed_at"), ("cancelled", "cancelled_at")]
)
def test_archived_record_retains_its_original_close_time(previous, stamp_key):
    args = source(rounds=1, terminal=previous)
    ledger = args[0]
    row = ledger["tasks"]["T000001"]
    row.update(
        state="archived", archived_from_state=previous, archived_at="2026-09-08T09:00:00+00:00"
    )
    ledger["history"].append(
        {
            "task_id": row["task_id"],
            "sequence": ledger["next_event_sequence"],
            "type": "archived",
            "actor": "old-parent",
            "at": row["archived_at"],
            "from_state": previous,
            "to_state": "archived",
            "details": {"note": ""},
        }
    )
    ledger["next_event_sequence"] += 1
    _, plan = plan_for(*args)
    assert plan.private_data()["proposals"][0]["record"]["closed_at"] == row[stamp_key]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda args: args[0]["tasks"]["T000001"].update(last_note="guessed report"),
        lambda args: args[0]["tasks"]["T000001"].update(submitted_at=BASE.isoformat()),
        lambda args: args[0]["tasks"]["T000001"].update(state="completed"),
        lambda args: args[0]["history"][-1].update(at="not-time"),
        lambda args: args[0]["history"][-1].update(at=BASE.isoformat()),
        lambda args: args[0]["history"][-1].update(type="unknown_future_event"),
        lambda args: args[0]["history"][-1].update(details={"report": {"wrong": "shape"}}),
        lambda args: args[0]["history"][-1].update(actor="old-parent"),
        lambda args: args[0]["history"][2].update(from_state="assigned"),
        lambda args: args[0]["history"][0]["details"].update(assignee="other-child"),
        lambda args: args[3]["members"]["owner"].update(role="adult"),
        lambda args: args[3]["members"]["child"].update(revision=2),
        lambda args: args[2].update({"old-parent": {"archive_only": True}}),
    ],
)
def test_ambiguous_history_and_rebound_authority_are_fixed_blockers(mutation):
    args = source()
    mutation(args)
    with pytest.raises(ReportHistoryError) as caught:
        project(args)
    assert str(caught.value) in {
        "task_report_history_review_required",
        "task_report_identity_review_required",
        "task_report_reassignment_review_required",
        "task_reviewer_role_review_required",
    }


@pytest.mark.asyncio
async def test_proposed_submitted_report_continues_in_real_engine_without_recreating_it():
    args = source()
    _, plan = plan_for(*args)
    state = deepcopy(args[3])
    record = plan.private_data()["proposals"][0]["record"]
    state["tasks"]["T000777"] = {"id": "T000777", "revision": 1, **record}
    saved = []

    async def save(value):
        saved.append(deepcopy(value))

    engine = Engine(state, save)
    assert "previous_reports" not in engine.view("child")["tasks"][0]
    assert engine.view("owner")["tasks"][0]["previous_reports"][0]["report"] == "First report"
    reviewed = await engine.execute(
        "owner",
        "tasks.request_changes",
        {"id": "T000777", "revision": 1, "note": "Another review"},
        "review-import",
        BASE,
    )
    await engine.execute(
        "child",
        "tasks.submit",
        {"id": "T000777", "revision": reviewed["revision"], "report": "New native report"},
        "report-import",
        BASE,
    )
    retained = Engine(saved[-1], save).view("owner")["tasks"][0]
    assert len(retained["previous_reports"]) == 2 and retained["report"] == "New native report"
    assert "review_note" not in retained
    from custom_components.family_assistant.assistant.plans import projection

    projected = projection(Engine(saved[-1], save).view("owner"))
    assert "First report" not in repr(projected) and "New native report" not in repr(projected)
