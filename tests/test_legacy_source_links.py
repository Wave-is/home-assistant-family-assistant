"""Synthetic cross-Store saga histories; no source writes or device operations."""

import json
from copy import deepcopy

import pytest
from ha_legacy_archive_smoke import synthetic_source

from custom_components.family_assistant.migration.review import read_store_pair
from custom_components.family_assistant.migration.source_links import (
    SourceLinkError,
    inspect_source_links,
)

STAMP = "2026-09-07T20:00:00+00:00"
TASK = "T000002"
KEY = f"task:{TASK}:missed:2026-09-07"


@pytest.fixture
def data():
    assistant, court, mapping, members = synthetic_source()
    assistant, court = json.loads(assistant), json.loads(court)
    mapping["system"] = {"archive_only": True}
    ledger = assistant["data"]["ledger"]
    ledger["history"][1].update(type="created", details={"assignee": "old-child"})
    court["data"]["history"] = []
    return assistant, court, mapping, members


def event(data, kind, details):
    ledger = data[0]["data"]["ledger"]
    ledger["history"].append(
        {
            "sequence": ledger["next_event_sequence"],
            "task_id": TASK,
            "type": kind,
            "actor": "system",
            "at": STAMP,
            "details": details,
        }
    )
    ledger["next_event_sequence"] += 1
    return ledger["history"][-1]


def rollover(data):
    return event(
        data,
        "missed_and_rolled_over",
        {"missed_date": "2026-09-07", "court_source_key": KEY, "court_delta": -1},
    )


def assessment(data, key=KEY, **values):
    court = data[1]["data"]
    row = {
        "event_id": f"synthetic-{len(court['history'])}",
        "child": "old-child",
        "week_id": court["week_id"],
        "timestamp": STAMP,
        "type": "minus",
        "delta": -1,
        "cancelled": False,
        "reason": "Private synthetic reason",
        "parent_user_id": 0,
        "telegram_message_id": f"system:{key}",
        "original_text": f"automatic task control: {key}",
        **values,
    }
    court["history"].append(row)
    return row


def review(data):
    assistant, court, mapping, members = data
    for key, values in court["data"]["children"].items():
        current = [
            row
            for row in court["data"]["history"]
            if row["child"] == key
            and row["week_id"] == court["data"]["week_id"]
            and not row["cancelled"]
        ]
        values.update(
            pluses=sum(row["delta"] == 1 for row in current),
            minuses=sum(row["delta"] == -1 for row in current),
        )
    return read_store_pair(json.dumps(assistant).encode(), json.dumps(court).encode()).review(
        mapping, members, mapping_revision=1
    )


def result(data):
    return inspect_source_links(review(data), members=data[3])


def codes(data):
    return {item["code"] for item in result(data)["issues"]}


def test_two_sided_task_link_uses_historical_owner_not_current_assignee(data):
    rollover(data)
    assessment(data)
    event(
        data,
        "revised",
        {"previous": {"assignee": "old-child"}, "current": {"assignee": "old-parent"}},
    )
    data[0]["data"]["ledger"]["tasks"][TASK]["assignee"] = "old-parent"
    before = deepcopy(data)
    summary = result(data)
    # Counter normalization is test preparation, not part of the inspector.
    before[1]["data"]["children"]["old-child"]["minuses"] = 1
    assert data == before
    assert not summary["issues"] and summary["task_penalties_matched"] == 1
    assert summary["coherence_verified"] is False
    assert "Private" not in json.dumps(summary) and TASK not in json.dumps(summary)


@pytest.mark.parametrize(
    "missing,expected",
    [("task", "court_penalty_without_task"), ("court", "task_penalty_without_court")],
)
def test_store_matching_does_not_hide_one_sided_commit(data, missing, expected):
    if missing != "task":
        rollover(data)
    if missing != "court":
        assessment(data)
    assert expected in codes(data)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("duplicate_court", "automatic_source_duplicate"),
        ("duplicate_rollover", "task_penalty_link_duplicate"),
        ("wrong_member", "task_penalty_member_mismatch"),
        ("missing_assignment", "task_penalty_link_invalid"),
        ("wrong_source", "task_penalty_link_invalid"),
        ("boolean_delta", "task_penalty_link_invalid"),
        ("message_id", "automatic_source_invalid"),
        ("parent_bool", "automatic_source_invalid"),
        ("unknown_system", "automatic_source_unknown"),
    ],
)
def test_exact_keys_members_and_strict_receipts(data, mutation, expected):
    rolled, score = rollover(data), assessment(data)
    if mutation == "duplicate_court":
        assessment(data)
    elif mutation == "duplicate_rollover":
        rollover(data)
    elif mutation == "wrong_member":
        data[1]["data"]["children"]["old-parent"] = {"pluses": 0, "minuses": 0}
        score["child"] = "old-parent"
    elif mutation == "missing_assignment":
        data[0]["data"]["ledger"]["history"][1].pop("details")
    elif mutation == "wrong_source":
        rolled["details"]["court_source_key"] = "private-wrong-key"
    elif mutation == "boolean_delta":
        rolled["details"]["court_delta"] = True
    elif mutation == "message_id":
        score["telegram_message_id"] = "private-wrong-id"
    elif mutation == "parent_bool":
        score["parent_user_id"] = False
    else:
        score["original_text"] = "private-unsupported-system"
    assert expected in codes(data)


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("pending", "task_correction_pending"),
        ("ack_without_reversal", "task_correction_without_reversal"),
        ("ack_without_request", "task_correction_ack_invalid"),
        ("valid", None),
    ],
)
def test_correction_is_a_two_store_saga(data, phase, expected):
    rollover(data)
    score = assessment(data)
    if phase != "ack_without_request":
        event(data, "court_correction_requested", {"source_key": KEY})
    if phase != "pending":
        event(data, "court_correction_applied", {"source_key": KEY, "court_delta_reversed": 1})
    if phase == "valid":
        score["cancelled"] = True
    found = codes(data)
    assert expected in found if expected else not found


def alarm(data):
    row = {
        "child": "old-child",
        "date": "2026-09-07",
        "scheduled_at": "2026-09-07T07:00:00+00:00",
        "confirmed_at": STAMP,
        "penalty_applied_at": STAMP,
    }
    data[0]["data"]["alarms"]["runs"]["old-child:2026-09-07"] = row
    return row


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("valid", None),
        ("no_run", "court_penalty_without_alarm"),
        ("no_court", "alarm_penalty_without_court"),
        ("no_ack", "alarm_penalty_not_acknowledged"),
        ("bad_date", "alarm_penalty_link_invalid"),
    ],
)
def test_alarm_penalty_needs_matching_run_acknowledgement(data, phase, expected):
    if phase != "no_run":
        run = alarm(data)
        if phase == "no_ack":
            run["penalty_applied_at"] = None
        elif phase == "bad_date":
            run["date"] = "private-invalid-date"
    if phase != "no_court":
        assessment(data, "alarm:old-child:2026-09-07:missed")
    found = codes(data)
    assert expected in found if expected else not found


def test_pruned_old_alarm_is_explicitly_archive_only_not_verified(data):
    assessment(data, "alarm:old-child:2026-06-01:missed", week_id="older-period")
    report = result(data)
    assert not report["issues"] and report["pruned_alarm_events_archive_only"] == 1
    assert report["alarm_penalties_matched"] == 0 and report["coherence_verified"] is False


def test_manual_court_reversal_does_not_require_a_task_ack(data):
    rollover(data)
    assessment(data, cancelled=True)
    assert not codes(data)


def test_changed_member_graph_is_rejected(data):
    selected = review(data)
    data[3]["child"]["revision"] += 1
    with pytest.raises(SourceLinkError, match="^source_link_review_changed$"):
        inspect_source_links(selected, members=data[3])


@pytest.mark.parametrize(
    "field,value",
    [
        ("penalty_applied_at", True),
        ("penalty_applied_at", ""),
        ("penalty_applied_at", "2026-09-07T06:00:00+00:00"),
        ("date", "2026-09-08"),
    ],
)
def test_malformed_alarm_ack_time_cannot_be_a_verified_link(data, field, value):
    run = alarm(data)
    assessment(data, "alarm:old-child:2026-09-07:missed")
    run[field] = value
    assert "alarm_penalty_link_invalid" in codes(data)


def test_non_system_rollover_actor_is_not_a_system_receipt(data):
    row = rollover(data)
    assessment(data)
    row["actor"] = "old-child"
    assert "task_penalty_link_invalid" in codes(data)


def test_unsettled_effect_blocks_whole_shadow_before_any_conversion(data):
    from test_legacy_shadow import NOW, inputs

    from custom_components.family_assistant.migration.shadow import (
        ShadowError,
        build_shadow_candidate,
    )

    _, target, _ = inputs()
    assessment(data)
    # Normalize counters through the existing fixture before binding full target.
    review(data)
    selected = read_store_pair(json.dumps(data[0]).encode(), json.dumps(data[1]).encode()).review(
        data[2], target["members"], mapping_revision=1
    )
    untouched = deepcopy(target)
    with pytest.raises(ShadowError, match="^shadow_source_effects_unsettled$"):
        build_shadow_candidate(selected, target, reviewer_policy={}, prepared_at=NOW)
    assert target == untouched


def test_consistent_alpha25_fixture_keeps_its_exact_whole_store_seal():
    from test_legacy_shadow import NOW, inputs

    from custom_components.family_assistant.migration.shadow import build_shadow_candidate

    # Generated by published alpha25, not this candidate:
    # 41546e28d85d16e898701c8c7ca53eba9aa524e7. Preserve the consistent copy.
    selected, target, policy = inputs()
    candidate = build_shadow_candidate(selected, target, reviewer_policy=policy, prepared_at=NOW)
    assert (
        candidate.summary()["fingerprint"]
        == "a6cfe61922d4786dea5420fdf1514d4295ad13101e05e1a05ef84bb4e222c1dd"
    )
