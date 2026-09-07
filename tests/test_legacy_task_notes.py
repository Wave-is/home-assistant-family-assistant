"""Explicit terminal notes retain their meaning without creating report evidence."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_legacy_task_plan import plan_for
from test_legacy_text_report_history import BASE, source

from custom_components.family_assistant.domain.engine import Engine


def with_notes(
    *, personal=False, transitions=("completed", "archived"), archive_note="Archive reason"
):
    args = source(rounds=0)
    ledger, _, _, _ = args
    row = ledger["tasks"]["T000001"]
    row.update(
        kind="reminder" if personal else "task",
        requires_report=False,
        report_type=None,
        reviewer=None,
    )
    first = ledger["history"][0]
    first["details"].update(requires_report=False, report_type=None, reviewer=None)
    if personal:
        row.update(creator="old-child", state="accepted", accepted_at=BASE.isoformat())
        first.update(actor="old-child", to_state="accepted")
    else:
        transitions = ("accepted", *transitions)
    for index, destination in enumerate(transitions, 1):
        note = archive_note if destination == "archived" else f"{destination} reason"
        previous = row["state"]
        stamp = (BASE + timedelta(minutes=index)).isoformat()
        ledger["history"].append(
            {
                "task_id": row["task_id"],
                "sequence": index + 1,
                "actor": "old-child",
                "at": stamp,
                "type": destination,
                "from_state": previous,
                "to_state": destination,
                "details": {} if destination == "accepted" else {"note": note},
            }
        )
        row["state"] = destination
        row[
            {
                "accepted": "accepted_at",
                "completed": "completed_at",
                "cancelled": "cancelled_at",
                "archived": "archived_at",
            }[destination]
        ] = stamp
        if destination != "accepted" and note:
            row["last_note"] = note
        if destination == "archived":
            row["archived_from_state"] = previous
    ledger["next_event_sequence"] = len(ledger["history"]) + 1
    return args


@pytest.mark.parametrize("personal", [False, True])
@pytest.mark.parametrize(
    "transitions",
    [
        ("completed",),
        ("cancelled",),
        ("archived",),
        ("completed", "archived"),
        ("cancelled", "archived"),
    ],
)
def test_terminal_notes_survive_without_becoming_report_or_authority(personal, transitions):
    args = with_notes(personal=personal, transitions=transitions)
    before = deepcopy(args)
    _, plan = plan_for(*args)
    private = plan.private_data()
    assert not private["blocked"]
    proposal = private["proposals"][0]
    record = proposal["record"]
    assert record["report_type"] == "none" and record["report"] is None
    assert "submitted_at" not in record and "reviewer" not in proposal["target_bindings"]
    assert "review_policy" not in proposal and "previous_reports" not in record
    for terminal in transitions:
        key = {
            "completed": "completion_note",
            "cancelled": "cancellation_note",
            "archived": "archive_note",
        }[terminal]
        assert record[key] == ("Archive reason" if terminal == "archived" else f"{terminal} reason")
    if personal:
        assert record["delivery_scope"] == "personal"
        state = deepcopy(args[3])
        state["tasks"]["T000777"] = {"id": "T000777", "revision": 1, **record}
        engine = Engine(state, None)
        assert engine.view("owner")["tasks"] == []
        assert engine.view("child")["tasks"][0]["id"] == "T000777"
    assert private["archive"]["history"] == args[0]["history"] and args == before


def test_empty_archive_note_does_not_relabel_completion_note():
    args = with_notes(archive_note="")
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    assert record["completion_note"] == "completed reason" and "archive_note" not in record


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a[0]["tasks"]["T000001"].update(last_note="Guessed note"),
        lambda a: a[0]["history"][-1].update(details={}),
        lambda a: a[0]["history"][-1].update(at=BASE.isoformat()),
        lambda a: a[0]["history"][0]["details"].update(requires_report=True),
        lambda a: a[0]["history"][-1].update(type="submitted"),
        lambda a: a[0]["tasks"]["T000001"].update(submitted_at=BASE.isoformat()),
    ],
)
def test_ambiguous_no_report_notes_still_block(mutation):
    args = with_notes()
    mutation(args)
    _, plan = plan_for(*args)
    assert plan.summary()["blocked_items_count"] == 1
    assert not plan.private_data()["proposals"] and not plan.summary()["import_available"]


def test_parent_cannot_claim_personal_reminder_completion_in_source_history():
    args = with_notes(personal=True, transitions=("completed",))
    args[0]["history"][-1]["actor"] = "old-parent"
    _, plan = plan_for(*args)
    assert plan.summary()["issues"] == [
        {"code": "task_report_identity_review_required", "count": 1}
    ]
