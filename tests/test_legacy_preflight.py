"""Synthetic, non-mutating legacy preflight; never a live migration fixture."""

from __future__ import annotations

import copy
import json

import pytest

from custom_components.family_assistant.migration import preflight

NOW = "2026-09-07T08:00:00+00:00"
KNOWN = {"parent", "child"}


def source():
    ledger = {
        "schema_version": 1,
        "next_task_sequence": 2,
        "next_event_sequence": 2,
        "tasks": {
            "T000001": {
                "task_id": "T000001",
                "kind": "task",
                "state": "assigned",
                "title": "Synthetic task",
                "creator": "parent",
                "assignee": "child",
                "reviewer": None,
                "created_at": NOW,
                "due_at": NOW,
                "metadata": {},
            },
        },
        "history": [{"sequence": 1, "task_id": "T000001", "actor": "parent", "at": NOW}],
        "processed_commands": {},
    }
    assistant = {
        "ledger": ledger,
        "alarms": {
            "schedules": {"child": {"weekday": {"enabled": False, "time": "07:00"}}},
            "runs": {},
        },
        "memories": {},
        "processed_home_updates": [],
        "sent_task_reminders": [],
    }
    court = {
        "schema_version": 1,
        "week_id": "synthetic-week",
        "opened_at": NOW,
        "children": {"child": {"pluses": 0, "minuses": 1}},
        "history": [
            {
                "event_id": "synthetic-event",
                "child": "child",
                "timestamp": NOW,
                "week_id": "synthetic-week",
                "type": "minus",
                "delta": -1,
                "cancelled": False,
            }
        ],
        "archived_weeks": [],
        "processed_messages": {},
    }
    return assistant, court


def codes(report):
    return {value["code"]: value["count"] for value in report["issues"]}


@pytest.mark.parametrize("envelope", [True, False])
def test_valid_data_is_read_only_counts_not_conversion(envelope):
    assistant, court = source()
    if not envelope:
        assistant = assistant["ledger"]
    before = copy.deepcopy((assistant, court, KNOWN))
    report = preflight.inspect_legacy(assistant, court, KNOWN)
    assert report["mode"] == "preflight_only"
    assert report["conversion_available"] is False
    assert report["issues"] == []
    assert report["counts"]["tasks"] == 1
    assert report["counts"]["court_events"] == 1
    assert report["counts"]["alarm_schedules"] == (1 if envelope else 0)
    assert (assistant, court, KNOWN) == before


def test_source_identities_text_and_transport_secrets_never_appear_in_report():
    assistant, court = source()
    row = assistant["ledger"]["tasks"]["T000001"]
    row.update(title="synthetic-secret-title", creator="unmapped-secret-person")
    row["metadata"]["opaque-private-source"] = "synthetic-secret-token"
    court["history"][0]["original_text"] = "synthetic-secret-message"
    report = preflight.inspect_legacy(assistant, court, KNOWN)
    assert codes(report)["unmapped_members"] == 1
    encoded = json.dumps(report)
    for secret in (
        "synthetic-secret",
        "T000001",
        "unmapped-secret-person",
        "synthetic-event",
        "child",
        "parent",
    ):
        assert secret not in encoded


@pytest.mark.parametrize("schema", [True, 1.0, "1", 2, None, [], {}])
def test_unsupported_schema_is_not_normalized(schema):
    assistant, court = source()
    assistant["ledger"]["schema_version"] = schema
    court["schema_version"] = schema
    found = codes(preflight.inspect_legacy(assistant, court, KNOWN))
    assert found["unsupported_task_schema"] == 1
    assert found["unsupported_court_schema"] == 1


def test_task_status_reference_private_owner_and_naive_time_block():
    assistant, court = source()
    row = assistant["ledger"]["tasks"]["T000001"]
    row.update(state="not-supported", kind="reminder", created_at="2026-09-07T08:00:00")
    assistant["ledger"]["history"][0]["task_id"] = "missing"
    found = codes(preflight.inspect_legacy(assistant, court, KNOWN))
    assert found["unsupported_task_status"] == 1
    assert found["broken_task_reference"] == 1
    assert found["private_reminder_owner_mismatch"] == 1
    assert found["naive_timestamp"] == 1


@pytest.mark.parametrize("sequence", [True, 1.5, "1", 0, -1, []])
def test_invalid_history_sequences_are_not_coerced(sequence):
    assistant, court = source()
    assistant["ledger"]["history"][0]["sequence"] = sequence
    assert "invalid_history_sequence" in codes(preflight.inspect_legacy(assistant, court, KNOWN))


def test_unknown_shopping_quantity_remains_unknown_and_partial_quantity_valid():
    assistant, court = source()
    row = assistant["ledger"]["tasks"]["T000001"]
    row.update(kind="shopping", assignee=None)
    row["metadata"] = {
        "shopping_quantity": None,
        "shopping_remaining_quantity": None,
        "shopping_unit": None,
        "shopping_approval": "pending",
    }
    assert not preflight.inspect_legacy(assistant, court, KNOWN)["issues"]
    row["metadata"].update(shopping_quantity=3, shopping_remaining_quantity=1.5, shopping_unit="kg")
    assert not preflight.inspect_legacy(assistant, court, KNOWN)["issues"]
    assert row["metadata"]["shopping_remaining_quantity"] == 1.5


@pytest.mark.parametrize(
    "quantity,remaining",
    [(True, 1), (0, 0), (-1, 0), (2, 3), (None, 1), (2, -1), (2, True), ({}, 1), (1, [])],
)
def test_invalid_shopping_quantities_block(quantity, remaining):
    assistant, court = source()
    row = assistant["ledger"]["tasks"]["T000001"]
    row.update(kind="shopping", assignee=None)
    row["metadata"] = {
        "shopping_quantity": quantity,
        "shopping_remaining_quantity": remaining,
        "shopping_unit": None,
        "shopping_approval": "approved",
    }
    assert "invalid_shopping_quantity" in codes(preflight.inspect_legacy(assistant, court, KNOWN))


def test_cancelled_and_previous_week_events_are_not_current_penalties():
    assistant, court = source()
    base = court["history"][0]
    court["history"].extend(
        [
            {**base, "event_id": "cancelled-event", "cancelled": True},
            {**base, "event_id": "previous-event", "week_id": "previous-week"},
        ]
    )
    court["archived_weeks"] = [{"week_id": "previous-week"}]
    report = preflight.inspect_legacy(assistant, court, KNOWN)
    assert not report["issues"]
    assert report["counts"]["court_events"] == 3
    assert report["counts"]["court_archived_weeks"] == 1
    court["children"]["child"]["minuses"] = 3
    assert codes(preflight.inspect_legacy(assistant, court, KNOWN))["court_balance_mismatch"] == 1


@pytest.mark.parametrize("value", [True, 1.5, "1", -1, None, []])
def test_court_counters_require_exact_nonnegative_integers(value):
    assistant, court = source()
    court["children"]["child"]["minuses"] = value
    assert "invalid_court_counter" in codes(preflight.inspect_legacy(assistant, court, KNOWN))


def test_alarm_enabled_and_active_run_are_not_activated_by_preflight():
    assistant, court = source()
    alarms = assistant["alarms"]
    alarms["schedules"]["child"]["weekday"]["enabled"] = True
    alarms["runs"]["private-run"] = {
        "child": "child",
        "scheduled_at": NOW,
        "challenge_answer": "synthetic-secret-answer",
        "confirmed_at": None,
        "cancelled_at": None,
    }
    before = copy.deepcopy(assistant)
    report = preflight.inspect_legacy(assistant, court, KNOWN)
    assert codes(report)["active_alarm_runs"] == 1
    assert report["counts"]["enabled_alarm_schedules"] == 1
    assert "synthetic-secret-answer" not in json.dumps(report)
    assert before == assistant
    alarms["schedules"]["child"]["weekday"].update(enabled=1, time="29:99")
    assert "invalid_alarm_schedule" in codes(preflight.inspect_legacy(assistant, court, KNOWN))


@pytest.mark.parametrize(
    "bad", [float("nan"), float("inf"), {1: "bad"}, object(), (1, 2), "\ud800", 2**80]
)
def test_non_json_source_is_refused_before_inspection(bad):
    assistant, court = source()
    assistant["opaque"] = bad
    assert codes(preflight.inspect_legacy(assistant, court, KNOWN)) == {"source_json_limits": 1}


def test_depth_cycle_node_and_text_limits(monkeypatch):
    assistant, court = source()
    assistant["cycle"] = assistant
    assert "source_json_limits" in codes(preflight.inspect_legacy(assistant, court, KNOWN))
    del assistant["cycle"]
    nested = {}
    for _ in range(preflight.MAX_DEPTH + 1):
        nested = {"nested": nested}
    assistant["nested"] = nested
    assert "source_json_limits" in codes(preflight.inspect_legacy(assistant, court, KNOWN))
    del assistant["nested"]
    assistant["large"] = "x" * (preflight.MAX_TEXT + 1)
    assert "source_json_limits" in codes(preflight.inspect_legacy(assistant, court, KNOWN))
    del assistant["large"]
    monkeypatch.setattr(preflight, "MAX_NODES", 10)
    assert "source_json_limits" in codes(preflight.inspect_legacy(assistant, court, KNOWN))


@pytest.mark.parametrize("value", [None, [], {}, True, 3, "untrusted", {"x": []}])
def test_malformed_records_cannot_raise_or_echo_input(value):
    assistant, court = source()
    for bucket, key in ((assistant["ledger"]["tasks"], "T000001"), (court["children"], "child")):
        bucket[key] = value
    assistant["ledger"]["history"][0] = value
    court["history"][0] = value
    report = preflight.inspect_legacy(assistant, court, KNOWN)
    assert report["issues"]
    assert "untrusted" not in json.dumps(report)


def test_nested_json_shape_mutations_are_total_and_counts_only():
    paths = (
        [
            (0, "ledger", "tasks", "T000001", key)
            for key in ("task_id", "kind", "state", "creator", "assignee", "metadata", "created_at")
        ]
        + [
            (1, "history", 0, key)
            for key in ("event_id", "child", "type", "delta", "cancelled", "week_id", "timestamp")
        ]
        + [(0, "alarms", "schedules", "child", "weekday", key) for key in ("enabled", "time")]
    )
    values = [None, True, 0, 1.5, "unknown", [], {}, ["x"], {"x": []}]
    for path in paths:
        for value in values:
            pair = source()
            target = pair[path[0]]
            for key in path[1:-1]:
                target = target[key]
            target[path[-1]] = value
            before = copy.deepcopy(pair)
            report = preflight.inspect_legacy(*pair, KNOWN)
            assert pair == before
            assert set(report) == {"mode", "conversion_available", "counts", "issues"}
            assert all(type(count) is int for count in report["counts"].values())
            assert all(set(issue) == {"code", "count"} for issue in report["issues"])
