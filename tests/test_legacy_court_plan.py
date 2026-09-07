"""Only the source open week seeds a future balance; old events stay archived."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.court_periods import summarize
from custom_components.family_assistant.domain.reward_wallet import balance
from custom_components.family_assistant.migration.court_plan import CourtPlanError, build_court_plan
from custom_components.family_assistant.migration.review import (
    ASSISTANT_KEY,
    COURT_KEY,
    read_store_pair,
)

STAMP = "2026-09-07T08:00:00+00:00"


def fixture():
    assistant = {
        "schema_version": 1,
        "tasks": {},
        "history": [],
        "processed_commands": {},
        "next_task_sequence": 1,
        "next_event_sequence": 1,
    }

    def event(identifier, points, *, cancelled=False, week="open-period"):
        return {
            "event_id": identifier,
            "timestamp": STAMP,
            "week_id": week,
            "child": "old-child",
            "type": "plus" if points == 1 else "minus",
            "delta": points,
            "reason": "Fictional reason " + identifier,
            "cancelled": cancelled,
            "parent_user_id": 989899,
            "parent_name": "Old actor",
            "original_text": "private-original-message",
            "telegram_message_id": 9494,
        }

    court = {
        "schema_version": 1,
        "week_id": "open-period",
        "opened_at": STAMP,
        "children": {"old-child": {"pluses": 1, "minuses": 1}},
        "history": [
            event("positive", 1),
            event("negative", -1),
            event("cancelled", -1, cancelled=True),
            event("previous", -1, week="old-period"),
        ],
        "archived_weeks": [
            {
                "week_id": "old-period",
                "children": {"old-child": {"pluses": 0, "minuses": 1}},
                "report_message": "old-private-report",
            }
        ],
        "processed_messages": {"old-receipt": {"token": "fictional-old-token"}},
        "unknown-field": {"metadata": "preserved"},
    }
    members = {"child": {"id": "child", "revision": 1, "active": True, "role": "child"}}
    mapping = {"old-child": {"member_id": "child", "member_revision": 1}}
    return assistant, court, mapping, members


def reviewed(assistant, court, mapping, members):
    def wrapped(data, key):
        return json.dumps({"key": key, "version": 1, "data": data}).encode()

    return read_store_pair(wrapped(assistant, ASSISTANT_KEY), wrapped(court, COURT_KEY)).review(
        mapping, members, mapping_revision=1
    )


def test_current_reasons_and_balances_without_prior_or_cancelled_penalties():
    args = fixture()
    before = deepcopy(args)
    review = reviewed(*args)
    plan = build_court_plan(review, members=args[3])
    assert args == before
    private = plan.private_data()
    assert private["archive"] == args[1]
    assert private["source_week"] == "open-period"
    assert private["blocked"] == []
    assert private["balances"] == [
        {
            "source_member": "old-child",
            "target_binding": args[2]["old-child"],
            "pluses": 1,
            "minuses": 1,
            "balance": 0,
        }
    ]
    assert [p["source_event"] for p in private["proposals"]] == ["positive", "negative"]
    for proposal, source in zip(private["proposals"], args[1]["history"], strict=False):
        assert proposal["target_binding"] == args[2]["old-child"]
        assert proposal["record"] == {
            "member": "child",
            "points": source["delta"],
            "reason": source["reason"],
            "created_at": STAMP,
            "status": "active",
            "source": "legacy",
            "actor": None,
        }
    summary = plan.summary()
    assert summary["source_events_count"] == 4
    assert summary["current_events_count"] == 3
    assert summary["cancelled_current_count"] == 1
    assert summary["previous_events_count"] == 1
    assert summary["record_proposals_count"] == 2
    assert summary["source_members_count"] == 1
    assert summary["archived_weeks_count"] == 1
    assert summary["issues"] == []
    assert summary["import_available"] is summary["coherence_verified"] is False
    assert summary["review_fingerprint"] == review.summary()["fingerprint"]


def test_generated_fields_work_with_real_week_summary_and_wallet():
    args = fixture()
    plan = build_court_plan(reviewed(*args), members=args[3])
    # IDs are assigned by a future importer; old receipt IDs are never new rights.
    records = [
        {"id": f"C{index}", "revision": 1, **p["record"]}
        for index, p in enumerate(plan.private_data()["proposals"], 1)
    ]
    now = datetime.fromisoformat(STAMP).astimezone(UTC)
    summary = summarize(records, now - timedelta(days=1), now + timedelta(days=1))
    assert summary["rows"] == [
        {
            "member": "child",
            "active_positives": 1,
            "active_negatives": -1,
            "total": 0,
            "active_count": 2,
            "reversed_count": 0,
        }
    ]
    wallet = balance(records, [], "child")
    assert wallet["earned"] == wallet["net"] == 0


def test_privacy_and_immutable_copies():
    args = fixture()
    plan = build_court_plan(reviewed(*args), members=args[3])
    assert repr(plan) == "CourtPlan(private=True, import_available=False)"
    public = json.dumps(plan.summary()) + repr(plan)
    for value in (
        "Fictional",
        "Old actor",
        "old-child",
        "private-original",
        "989899",
        "9494",
        "open-period",
        STAMP,
    ):
        assert value not in public
    private = plan.private_data()
    private["archive"]["history"].clear()
    private["proposals"][0]["record"]["points"] = 90
    private["balances"][0]["balance"] = 90
    assert len(plan.private_data()["archive"]["history"]) == 4
    assert plan.private_data()["proposals"][0]["record"]["points"] == 1
    assert plan.private_data()["balances"][0]["balance"] == 0
    with pytest.raises(FrozenInstanceError):
        plan._summary = b"{}"


@pytest.mark.parametrize("reason", [None, "", " ", "x" * 501, {}, 42])
def test_current_missing_or_unrepresentable_reason_is_not_invented(reason):
    args = fixture()
    args[1]["history"][0]["reason"] = reason
    plan = build_court_plan(reviewed(*args), members=args[3])
    assert plan.summary()["issues"] == [{"code": "court_reason_unsupported", "count": 1}]
    assert plan.summary()["blocked_events_count"] == 1
    assert plan.summary()["record_proposals_count"] == 1
    assert plan.private_data()["blocked"] == [
        {"source_event": "positive", "code": "court_reason_unsupported"}
    ]
    assert plan.private_data()["archive"]["history"][0]["reason"] == reason


@pytest.mark.parametrize("week", [None, "", " ", 42, [], {}, "x" * 129])
def test_unknown_period_cannot_be_silently_classified_as_old(week):
    args = fixture()
    args[1]["history"][3]["week_id"] = week
    plan = build_court_plan(reviewed(*args), members=args[3])
    assert plan.summary()["issues"] == [{"code": "court_period_unknown", "count": 1}]
    assert plan.summary()["previous_events_count"] == 0
    assert plan.private_data()["archive"]["history"][3]["week_id"] == week


def test_cancelled_and_old_reason_and_delivery_data_never_become_active_records():
    args = fixture()
    args[1]["history"][2]["reason"] = None
    args[1]["history"][3]["reason"] = {"unknown-old-field": "kept"}
    plan = build_court_plan(reviewed(*args), members=args[3])
    assert plan.summary()["issues"] == []
    assert len(plan.private_data()["proposals"]) == 2
    assert plan.private_data()["archive"] == args[1]
    assert "telegram" not in json.dumps(plan.private_data()["proposals"])
    assert "old-receipt" not in json.dumps(plan.private_data()["proposals"])


def test_empty_court_has_no_synthetic_zero_awards():
    args = fixture()
    args[1].update(
        history=[], archived_weeks=[], children={"old-child": {"pluses": 0, "minuses": 0}}
    )
    plan = build_court_plan(reviewed(*args), members=args[3])
    assert plan.private_data()["proposals"] == []
    assert plan.private_data()["balances"][0]["balance"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("active", False),
        ("revision", 2),
        ("role", "adult"),
        ("telegram_id", 2929),
        ("ha_user_id", "other"),
    ],
)
def test_changed_target_identity_revokes_review(field, value):
    args = fixture()
    review = reviewed(*args)
    args[3]["child"][field] = value
    with pytest.raises(CourtPlanError, match="^review_changed$"):
        build_court_plan(review, members=args[3])


def test_forged_or_missing_review_rejected_and_fingerprint_binds_whole_archive():
    args = fixture()
    review = reviewed(*args)
    first = build_court_plan(review, members=args[3])
    assert build_court_plan(reviewed(*args), members=args[3]).summary() == first.summary()
    args[1]["unknown-field"]["metadata"] = "changed"
    assert (
        build_court_plan(reviewed(*args), members=args[3]).summary()["fingerprint"]
        != first.summary()["fingerprint"]
    )
    with pytest.raises(CourtPlanError, match="^invalid_review$"):
        build_court_plan(None)
    with pytest.raises(CourtPlanError, match="^review_changed$"):
        build_court_plan(review)
    with pytest.raises(CourtPlanError, match="^review_changed$"):
        build_court_plan(replace(review, _counts=b"{}"), members=args[3])


def test_bad_counter_cannot_enter_a_plan_even_with_forged_source():
    args = fixture()
    review = reviewed(*args)
    assistant, court = review._source.private_data()
    court["children"]["old-child"]["minuses"] = 50
    forged_source = read_store_pair(
        json.dumps({"key": ASSISTANT_KEY, "version": 1, "data": assistant}).encode(),
        json.dumps({"key": COURT_KEY, "version": 1, "data": court}).encode(),
    )
    with pytest.raises(CourtPlanError, match="^review_changed$"):
        build_court_plan(replace(review, _source=forged_source), members=args[3])
