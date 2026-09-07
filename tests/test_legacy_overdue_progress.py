"""Late acceptance/start are not rewound to the old pre-overdue phase."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_legacy_task_plan import plan_for
from test_legacy_text_report_history import BASE, source


def overdue_source(*, report_type="text", refresh=True, started=True):
    args = source(rounds=0)
    ledger, _, mapping, _ = args
    row = ledger["tasks"]["T000001"]
    required = report_type is not None
    reviewer = "old-parent" if required else None
    row.update(requires_report=required, report_type=report_type, reviewer=reviewer)
    ledger["history"][0]["details"].update(
        requires_report=required, report_type=report_type, reviewer=reviewer
    )
    mapping["system"] = {"archive_only": True}
    row["metadata"] = {}
    sequence = ["overdue", "accepted"] if refresh else ["accepted"]
    if started:
        sequence.append("started")
    for index, kind in enumerate(sequence, 1):
        stamp = (BASE + timedelta(hours=index)).isoformat()
        ledger["history"].append(
            {
                "sequence": index + 1,
                "task_id": row["task_id"],
                "type": kind,
                "from_state": row["state"],
                "to_state": "overdue",
                "at": stamp,
                "actor": "system" if kind == "overdue" else "old-child",
                "details": {"late": True},
            }
        )
        if kind == "overdue":
            row["metadata"]["overdue_from_state"] = row["state"]
        else:
            row[f"{kind}_at"] = stamp
        row["state"] = "overdue"
    ledger["next_event_sequence"] = len(ledger["history"]) + 1
    return args


@pytest.mark.parametrize("report_type", [None, "text", "photo"])
@pytest.mark.parametrize("refresh", [False, True])
@pytest.mark.parametrize("started", [False, True])
def test_actual_activity_is_preserved_with_or_without_prior_deadline_refresh(
    report_type, refresh, started
):
    args = overdue_source(report_type=report_type, refresh=refresh, started=started)
    before = deepcopy(args)
    _, plan = plan_for(*args)
    assert not plan.private_data()["blocked"]
    record = plan.private_data()["proposals"][0]["record"]
    assert record["status"] == ("in_progress" if started else "accepted")
    assert record["accepted_at"] == args[0]["tasks"]["T000001"]["accepted_at"]
    if started:
        assert record["started_at"] == args[0]["tasks"]["T000001"]["started_at"]
    assert record["due_at"] == args[0]["tasks"]["T000001"]["due_at"]
    assert args == before and plan.private_data()["archive"]["tasks"] == args[0]["tasks"]
    assert not plan.summary()["import_available"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a[0]["tasks"]["T000001"].update(accepted_at=BASE.isoformat()),
        lambda a: a[0]["tasks"]["T000001"].update(started_at=BASE.isoformat()),
        lambda a: a[0]["tasks"]["T000001"].update(accepted_at=None),
        lambda a: a[0]["history"].pop(2),
        lambda a: a[0]["history"][-1].update(actor="old-parent"),
    ],
)
def test_unproven_progress_is_never_inferred_from_a_timestamp_alone(mutation):
    args = overdue_source()
    mutation(args)
    _, plan = plan_for(*args)
    assert not plan.private_data()["proposals"] and plan.summary()["blocked_items_count"] == 1


def test_equivalent_iso_offset_preserves_the_exact_original_activity_timestamp():
    args = overdue_source()
    args[0]["tasks"]["T000001"]["started_at"] = "2026-09-07T13:00:00+02:00"
    _, plan = plan_for(*args)
    record = plan.private_data()["proposals"][0]["record"]
    assert record["started_at"] == "2026-09-07T13:00:00+02:00"


def test_stale_phase_restored_by_a_later_source_revision_is_not_silently_rewound():
    args = overdue_source()
    ledger = args[0]
    for sequence, kind, before, after, details in [
        (
            5,
            "revised",
            "overdue",
            "assigned",
            {"previous": {"assignee": "old-child"}, "current": {"assignee": "old-child"}},
        ),
        (6, "overdue", "assigned", "overdue", {}),
    ]:
        ledger["history"].append(
            {
                "sequence": sequence,
                "task_id": "T000001",
                "type": kind,
                "at": (BASE + timedelta(hours=sequence)).isoformat(),
                "actor": "old-parent" if kind == "revised" else "system",
                "from_state": before,
                "to_state": after,
                "details": details,
            }
        )
    ledger["next_event_sequence"] = 7
    _, plan = plan_for(*args)
    assert plan.summary()["issues"] == [
        {"code": "task_overdue_progress_review_required", "count": 1}
    ]


def test_fabricated_needs_changes_phase_without_any_report_is_blocked():
    args = overdue_source(started=False)
    ledger = args[0]
    for sequence, kind, before, after, details in [
        (
            4,
            "revised",
            "overdue",
            "needs_changes",
            {"previous": {"assignee": "old-child"}, "current": {"assignee": "old-child"}},
        ),
        (5, "overdue", "needs_changes", "overdue", {}),
    ]:
        ledger["history"].append(
            {
                "sequence": sequence,
                "task_id": "T000001",
                "type": kind,
                "at": (BASE + timedelta(hours=sequence)).isoformat(),
                "actor": "old-parent" if kind == "revised" else "system",
                "from_state": before,
                "to_state": after,
                "details": details,
            }
        )
    ledger["next_event_sequence"] = 6
    ledger["tasks"]["T000001"]["metadata"]["overdue_from_state"] = "needs_changes"
    _, plan = plan_for(*args)
    assert not plan.private_data()["proposals"]
    assert plan.summary()["blocked_items_count"] == 1
