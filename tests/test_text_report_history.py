"""Repeated textual reports retain history under the real transactional Engine."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def prepare(engine, now):
    task = await engine.execute(
        "parent",
        "tasks.create",
        {"title": "Synthetic report rounds", "assignee": "child", "report_type": "text"},
        "create-report-rounds",
        now,
    )
    task = await engine.execute(
        "child",
        "tasks.submit",
        {"id": task["id"], "revision": task["revision"], "report": "First report"},
        "first-report",
        now,
    )
    return await engine.execute(
        "parent",
        "tasks.request_changes",
        {"id": task["id"], "revision": task["revision"], "note": "First review"},
        "first-review",
        now + timedelta(minutes=1),
    )


@pytest.mark.asyncio
async def test_text_resubmission_is_archived_once_and_rehydrates(engine, store, now):
    task = await prepare(engine, now)
    later = now + timedelta(minutes=2)
    payload = {"id": task["id"], "revision": task["revision"], "report": "Corrected report"}
    child_result = await engine.execute("child", "tasks.submit", payload, "resubmit", later)
    assert child_result["report"] == "Corrected report"
    assert child_result["submitted_at"] == later.isoformat()
    assert "review_note" not in child_result and "previous_reports" not in child_result
    expected_history = [
        {
            "assignee": "child",
            "assignee_revision": 1,
            "report": "First report",
            "review_note": "First review",
            "submitted_at": now.isoformat(),
            "resubmitted_at": later.isoformat(),
        }
    ]
    parent_row = engine.view("parent")["tasks"][0]
    assert parent_row["previous_reports"] == expected_history
    fresh = Engine(deepcopy(store.value), store.save)
    assert await fresh.execute("child", "tasks.submit", payload, "resubmit", later) == child_result
    assert fresh.view("parent")["tasks"][0]["previous_reports"] == expected_history
    assert not fresh.view("sibling")["tasks"]
    assert not fresh.view("guest")["tasks"]
    assert "previous_reports" not in fresh.view("child")["tasks"][0]


@pytest.mark.asyncio
async def test_failed_resubmission_does_not_erase_prior_report_or_note(engine, store, now):
    task = await prepare(engine, now)
    before = engine.snapshot()
    payload = {"id": task["id"], "revision": task["revision"], "report": "Second report"}
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("child", "tasks.submit", payload, "resubmit", now)
    assert engine.snapshot() == before
    store.fail = False
    await engine.execute("child", "tasks.submit", payload, "resubmit", now)
    assert len(engine.snapshot()["tasks"][task["id"]]["previous_reports"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("report", [None, "", " ", 2, {}, "x" * 2001])
async def test_invalid_resubmission_leaves_history_intact(engine, now, report):
    task = await prepare(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "child",
            "tasks.submit",
            {"id": task["id"], "revision": task["revision"], "report": report},
            "invalid-resubmit",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_old_text_report_without_new_timestamp_is_preserved(engine, store, now):
    task = await prepare(engine, now)
    old_state = engine.snapshot()
    old_state["tasks"][task["id"]].pop("submitted_at")
    old_state["tasks"][task["id"]].pop("assignee_revision")
    fresh = Engine(old_state, store.save)
    await fresh.execute(
        "child",
        "tasks.submit",
        {"id": task["id"], "revision": task["revision"], "report": "New report"},
        "legacy-resubmit",
        now,
    )
    archived = fresh.snapshot()["tasks"][task["id"]]["previous_reports"][0]
    assert archived["report"] == "First report" and archived["review_note"] == "First review"
    assert "submitted_at" not in archived and "assignee_revision" not in archived
