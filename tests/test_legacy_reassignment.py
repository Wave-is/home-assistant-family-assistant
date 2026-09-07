"""Verified source assignment chains preserve each person's own report rounds."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_legacy_task_plan import plan_for
from test_legacy_text_report_history import BASE, project, source

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.migration.task_reports import ReportHistoryError


def reassigned(*, new_report=False, return_assignment=False):
    args = source(rounds=1, terminal="needs_changes")
    ledger, _, mapping, state = args
    mapping["old-sibling"] = {"member_id": "sibling", "member_revision": 1}
    state["members"]["sibling"] = {
        "id": "sibling",
        "revision": 1,
        "active": True,
        "role": "child",
        "name": "Fictional sibling",
        "language": "en",
    }
    row = ledger["tasks"]["T000001"]

    def add(kind, actor, destination, details):
        stamp = (BASE + timedelta(minutes=len(ledger["history"]))).isoformat()
        ledger["history"].append(
            {
                "task_id": row["task_id"],
                "sequence": ledger["next_event_sequence"],
                "type": kind,
                "actor": actor,
                "at": stamp,
                "from_state": row["state"],
                "to_state": destination,
                "details": details,
            }
        )
        ledger["next_event_sequence"] += 1
        row["state"] = destination
        return stamp

    def assign(key):
        add(
            "revised",
            "old-parent",
            "assigned",
            {
                "previous": {"assignee": row["assignee"]},
                "current": {"assignee": key},
            },
        )
        row.update(assignee=key, accepted_at=None, started_at=None, submitted_at=None)
        # The old ledger deliberately keeps last_note even after reassignment.

    assign("old-sibling")
    if new_report or return_assignment:
        row["submitted_at"] = add(
            "submitted", "old-sibling", "submitted", {"report": "Sibling report"}
        )
        row["last_note"] = "Sibling report"
    if return_assignment:
        add("changes_requested", "old-parent", "needs_changes", {"note": "Sibling review"})
        row["last_note"] = "Sibling review"
        assign("old-child")
    return args


def imported(args):
    _, plan = plan_for(*args)
    private = plan.private_data()
    assert private["blocked"] == []
    state = deepcopy(args[3])
    state["tasks"]["T000777"] = {
        "id": "T000777",
        "revision": 1,
        **private["proposals"][0]["record"],
    }
    assert private["archive"]["history"] == args[0]["history"]
    return state


@pytest.mark.asyncio
async def test_new_assignee_does_not_inherit_old_report_but_parent_keeps_history():
    args = reassigned()
    before = deepcopy(args)
    saved = []

    async def save(value):
        saved.append(deepcopy(value))

    engine = Engine(imported(args), save)
    parent = engine.view("owner")["tasks"][0]
    child = engine.view("sibling")["tasks"][0]
    assert parent["report"] is None and "review_note" not in parent
    assert "submitted_at" not in parent
    old = parent["previous_reports"][0]
    assert old["assignee"] == "child" and old["assignee_revision"] == 1
    assert old["report"] == "First report" and old["review_note"] == "Review 0"
    assert old["submitted_at"] == args[0]["history"][1]["at"]
    assert old["reassigned_at"] == args[0]["history"][3]["at"]
    assert "previous_reports" not in child and child["report"] is None
    assert engine.view("child")["tasks"] == []
    await engine.execute(
        "sibling",
        "tasks.submit",
        {
            "id": "T000777",
            "revision": 1,
            "report": "Native sibling report",
        },
        "native-new-report",
        BASE + timedelta(hours=1),
    )
    retained = Engine(saved[-1], save).view("owner")["tasks"][0]
    assert retained["report"] == "Native sibling report"
    assert retained["previous_reports"] == [old]
    assert args == before


def test_later_source_submission_is_attributed_to_new_assignee():
    result = imported(reassigned(new_report=True))["tasks"]["T000777"]
    assert result["assignee"] == "sibling" and result["report"] == "Sibling report"
    assert result["previous_reports"][0]["assignee"] == "child"
    assert "review_note" not in result


def test_returning_assignment_does_not_restore_previous_report():
    result = imported(reassigned(return_assignment=True))["tasks"]["T000777"]
    assert result["assignee"] == "child" and result["report"] is None
    assert "submitted_at" not in result and "review_note" not in result
    assert [x["assignee"] for x in result["previous_reports"]] == ["child", "sibling"]
    assert [x["report"] for x in result["previous_reports"]] == ["First report", "Sibling report"]


@pytest.mark.parametrize(
    "mutation, code",
    [
        (
            lambda a: a[0]["history"][3]["details"]["previous"].update(assignee="old-sibling"),
            "task_report_reassignment_review_required",
        ),
        (
            lambda a: a[0]["tasks"]["T000001"].update(assignee="old-child"),
            "task_report_reassignment_review_required",
        ),
        (
            lambda a: a[0]["history"][3].update(actor="old-child"),
            "task_reviewer_role_review_required",
        ),
        (
            lambda a: a[3]["members"]["child"].update(active=False),
            "task_report_identity_review_required",
        ),
        (
            lambda a: a[3]["members"]["sibling"].update(revision=2),
            "task_report_identity_review_required",
        ),
        (
            lambda a: a[2].update({"old-child": {"archive_only": True}}),
            "task_report_identity_review_required",
        ),
        (
            lambda a: a[0]["history"][3]["details"]["current"].update(assignee="unmapped"),
            "task_report_identity_review_required",
        ),
    ],
)
def test_tampered_assignment_chain_or_stale_identity_is_not_importable(mutation, code):
    args = reassigned()
    mutation(args)
    with pytest.raises(ReportHistoryError, match=f"^{code}$"):
        project(args)


@pytest.mark.parametrize(
    "kind, destination", [("accepted", "accepted"), ("started", "in_progress")]
)
def test_progress_events_cannot_be_attributed_to_former_assignee(kind, destination):
    args = reassigned()
    ledger = args[0]
    ledger["history"].append(
        {
            "task_id": "T000001",
            "sequence": ledger["next_event_sequence"],
            "type": kind,
            "actor": "old-child",
            "at": (BASE + timedelta(hours=1)).isoformat(),
            "from_state": "assigned",
            "to_state": destination,
            "details": {},
        }
    )
    ledger["next_event_sequence"] += 1
    ledger["tasks"]["T000001"]["state"] = destination
    with pytest.raises(ReportHistoryError, match="^task_report_identity_review_required$"):
        project(args)
