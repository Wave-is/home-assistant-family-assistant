"""Synthetic private identity inventory; no inference, file I/O or authority."""

import json
from copy import deepcopy

import pytest
from ha_legacy_archive_smoke import synthetic_source

from custom_components.family_assistant.migration.copy_inventory import (
    CopyInventoryError,
    source_inventory,
)
from custom_components.family_assistant.migration.review import read_store_pair


def source(change=None):
    assistant, court, _, _ = synthetic_source()
    data = json.loads(assistant)
    if change:
        change(data["data"])
    return read_store_pair(json.dumps(data).encode(), court)


def test_exact_inventory_without_auto_matching_and_legacy_event_type_optional():
    selected = source()
    before = selected.private_data()
    result = source_inventory(selected, additional_members=["old-observer"])
    assert result["members"] == [
        {"source_id": "old-child", "archive_allowed": False},
        {"source_id": "old-observer", "archive_allowed": True},
        {"source_id": "old-parent", "archive_allowed": False},
    ]
    assert result["reviewers"][0]["task_id"] == "T000004"
    assert result["coherence_verified"] is False
    assert selected.private_data() == before


def test_source_and_additional_ids_deduplicate_but_not_guess_names():
    result = source_inventory(source(), additional_members=["old-parent", "Old-Parent"])
    assert len(result["members"]) == 3
    assert result["members"][0] == {"source_id": "Old-Parent", "archive_allowed": True}


@pytest.mark.parametrize(
    "extra", [None, {}, "x", [""], ["x", "x"], [False], ["x" * 129], list(map(str, range(513)))]
)
def test_invalid_extra_id_metadata_is_fixed_code(extra):
    with pytest.raises(CopyInventoryError, match="^migration_prepare_source_invalid$"):
        source_inventory(source(), additional_members=extra)


def test_unsettled_active_alarm_blocks_preparation_instead_of_hiding_it():
    def change(data):
        data["alarms"]["runs"]["private-canary"] = {
            "child": "old-child",
            "scheduled_at": "2026-09-07T08:00:00+00:00",
        }

    with pytest.raises(CopyInventoryError, match="^migration_prepare_source_invalid$"):
        source_inventory(source(change), additional_members=[])


@pytest.mark.parametrize(
    "kind", ["submitted", "changes_requested", "completed", "cancelled", "archived"]
)
@pytest.mark.parametrize("report_type", ["text", "photo"])
def test_historical_report_and_terminal_actor_cannot_be_archived(kind, report_type):
    def change(data):
        task = data["ledger"]["tasks"]["T000004"]
        task["report_type"] = report_type
        event = data["ledger"]["history"][-1]
        event.update(type=kind, actor="old-former-child")

    result = source_inventory(source(change), additional_members=[])
    assert {"source_id": "old-former-child", "archive_allowed": False} in result["members"]


def test_created_and_revised_old_assignees_are_visible_without_privilege_guessing():
    def change(data):
        rows = data["ledger"]["history"]
        rows[0].update(type="created", details={"assignee": "old-first"})
        rows[1].update(
            type="revised",
            details={"previous": {"assignee": "old-second"}, "current": {"assignee": "old-third"}},
        )

    result = source_inventory(source(change), additional_members=[])
    assert {row["source_id"] for row in result["members"]} >= {
        "old-first",
        "old-second",
        "old-third",
    }
    assert all(
        not row["archive_allowed"]
        for row in result["members"]
        if row["source_id"] in {"old-first", "old-second", "old-third"}
    )
    original = deepcopy(result)
    result["members"].clear()
    assert source_inventory(source(change), additional_members=[]) == original
