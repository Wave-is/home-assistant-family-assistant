"""A future photo requirement is not the same as unresolved historical evidence."""

from copy import deepcopy

import pytest
from test_legacy_task_plan import plan_for
from test_legacy_text_report_history import BASE, source

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def photo_source(*, rounds=0, terminal=None):
    args = source(rounds=rounds, terminal=terminal)
    args[0]["tasks"]["T000001"]["report_type"] = "photo"
    args[0]["history"][0]["details"]["report_type"] = "photo"
    return args


@pytest.mark.parametrize("terminal", [None, "completed", "cancelled", "archived"])
def test_photo_requirement_without_submission_preserves_source_outcome(terminal):
    args = photo_source(terminal=terminal)
    before = deepcopy(args)
    _, plan = plan_for(*args)
    assert not plan.private_data()["blocked"]
    proposal = plan.private_data()["proposals"][0]
    record = proposal["record"]
    assert record["report_type"] == "photo" and record["report"] is None
    assert record["status"] == (terminal or "assigned")
    assert "report_media" not in record and "submitted_at" not in record
    assert "previous_reports" not in record
    assert proposal["review_policy"] == "household_parents"
    assert proposal["target_bindings"]["reviewer"] == args[2]["old-parent"]
    assert args == before and plan.private_data()["archive"]["history"] == args[0]["history"]
    assert not plan.summary()["import_available"]


@pytest.mark.asyncio
async def test_imported_future_photo_task_still_requires_verified_photo_in_actual_engine():
    args = photo_source()
    _, plan = plan_for(*args)
    state = deepcopy(args[3])
    state["tasks"]["T000777"] = {
        "id": "T000777",
        "revision": 1,
        **plan.private_data()["proposals"][0]["record"],
    }
    saved = []

    async def save(value):
        saved.append(deepcopy(value))

    engine = Engine(state, save)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="photo_required"):
        await engine.execute(
            "child",
            "tasks.submit",
            {"id": "T000777", "revision": 1, "report": "An unverified caption"},
            "no-photo",
            BASE,
        )
    assert engine.snapshot() == before and not saved
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "child", "tasks.complete", {"id": "T000777", "revision": 1}, "no-parent", BASE
        )
    assert engine.snapshot() == before and not saved


@pytest.mark.parametrize("terminal", [None, "needs_changes", "completed", "cancelled", "archived"])
def test_any_historical_photo_submission_blocks_even_if_now_terminal(terminal):
    args = photo_source(rounds=1, terminal=terminal)
    _, plan = plan_for(*args)
    assert plan.summary()["issues"] == [{"code": "task_photo_evidence_review_required", "count": 1}]
    assert not plan.private_data()["proposals"]
    assert plan.private_data()["archive"]["history"] == args[0]["history"]


def test_direct_completion_without_photo_requires_explicit_source_parent_confirmation():
    args = photo_source(terminal="completed")
    args[0]["history"][-1]["details"].pop("direct_parent_confirmation")
    _, plan = plan_for(*args)
    assert not plan.private_data()["proposals"]
    assert plan.summary()["issues"] == [{"code": "task_report_history_review_required", "count": 1}]
