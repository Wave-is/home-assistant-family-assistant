"""Explicit source policy comparison is private and never permission to import."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
from test_legacy_conversion import fixture

from custom_components.family_assistant.migration.conversion import (
    ConversionError,
    build_conversion_review,
)
from custom_components.family_assistant.migration.reviewer_policy import (
    ReviewerPolicyError,
    build_reviewer_policy_review,
)


def inputs(extra_parent=False):
    review, members = fixture()
    if extra_parent:
        members["second-parent"] = {
            "id": "second-parent",
            "name": "Private reviewer name",
            "role": "parent",
            "active": True,
            "revision": 1,
        }
        review = review._source.review(review.private_data()[2], members, mapping_revision=1)
    assistant, _, _ = review.private_data()
    policy = {
        "schema": 1,
        "revision": 1,
        "source_review_fingerprint": review.summary()["fingerprint"],
        "reviewers": {
            key: [row["reviewer"]]
            for key, row in assistant["ledger"]["tasks"].items()
            if row.get("kind") == "task" and row.get("requires_report") is True
        },
    }
    return review, members, policy


def test_equivalent_policy_has_no_rights_changes_or_side_effects():
    review, members, policy = inputs()
    before = deepcopy((members, policy, review.private_data()))
    result = build_reviewer_policy_review(review, policy, members=members)
    assert result.summary()["changed_tasks_count"] == 0
    assert result.summary()["tasks_count"] == 1
    assert result.matches(review, policy, members=members)
    assert (members, policy, review.private_data()) == before
    assert result.summary()["import_available"] is False
    assert result.summary()["source_policy_verified"] is False


def test_new_parent_does_not_silently_gain_legacy_reviewer_authority():
    review, members, policy = inputs(extra_parent=True)
    result = build_reviewer_policy_review(review, policy, members=members)
    assert result.summary()["changed_tasks_count"] == 1
    assert result.summary()["additional_reviewer_bindings_count"] == 1
    assert result.private_data()["comparisons"][0]["added"] == [
        {"member_id": "second-parent", "member_revision": 1}
    ]
    public = json.dumps(result.summary()) + repr(result)
    for text in ("second-parent", "Private reviewer name", "T000004", "old-parent"):
        assert text not in public


def test_declared_nonparent_old_authority_is_reported_not_promoted():
    review, members, policy = inputs()
    policy["reviewers"][next(iter(policy["reviewers"]))].append("old-child")
    result = build_reviewer_policy_review(review, policy, members=members)
    assert result.summary()["removed_reviewer_bindings_count"] == 1
    assert members["child"]["role"] == "child"


@pytest.mark.parametrize(
    "drift", ["member_revision", "binding", "role", "policy_revision", "source"]
)
def test_retained_review_detects_every_input_drift(drift):
    review, members, policy = inputs()
    result = build_reviewer_policy_review(review, policy, members=members)
    if drift == "member_revision":
        members["owner"]["revision"] += 1
    elif drift == "binding":
        members["owner"]["ha_user_id"] = "synthetic-changed"
    elif drift == "role":
        members["child"]["role"] = "parent"
    elif drift == "policy_revision":
        policy["revision"] += 1
    else:
        policy["source_review_fingerprint"] = "0" * 64
    assert not result.matches(review, policy, members=members)


@pytest.mark.parametrize(
    "bad", ["missing", "extra", "duplicate", "unknown", "empty", "no-designated", "bool-revision"]
)
def test_incomplete_or_ambiguous_policy_fails_without_source_content(bad):
    review, members, policy = inputs()
    key = next(iter(policy["reviewers"]))
    if bad == "missing":
        policy["reviewers"].clear()
    elif bad == "extra":
        policy["reviewers"]["private-wrong-task"] = ["old-parent"]
    elif bad == "duplicate":
        policy["reviewers"][key] *= 2
    elif bad == "unknown":
        policy["reviewers"][key].append("private-unknown-actor")
    elif bad == "empty":
        policy["reviewers"][key] = []
    elif bad == "no-designated":
        policy["reviewers"][key] = ["old-child"]
    else:
        policy["revision"] = True
    with pytest.raises(ReviewerPolicyError) as error:
        build_reviewer_policy_review(review, policy, members=members)
    assert "private" not in str(error.value) and key not in str(error.value)


def test_private_copies_and_frozen_review_cannot_change_receipt():
    review, members, policy = inputs()
    result = build_reviewer_policy_review(review, policy, members=members)
    result.private_data()["comparisons"].clear()
    result.summary()["tasks_count"] = 0
    assert result.matches(review, policy, members=members)
    with pytest.raises(FrozenInstanceError):
        result._private = b"{}"


def test_joined_conversion_pins_authority_review_but_does_not_grant_import():
    review, members, policy = inputs(extra_parent=True)
    result = build_conversion_review(review, "UTC", members=members, reviewer_policy=policy)
    assert result.summary()["reviewer_authority"]["changed_tasks_count"] == 1
    assert result.summary()["import_available"] is False
    assert result.private_data()["reviewer_authority"]["policy"] == policy
    repeated = build_conversion_review(review, "UTC", members=members, reviewer_policy=policy)
    assert repeated.private_data() == result.private_data()
    policy["revision"] += 1
    changed = build_conversion_review(review, "UTC", members=members, reviewer_policy=policy)
    assert changed.summary()["fingerprint"] != result.summary()["fingerprint"]
    policy["reviewers"].clear()
    with pytest.raises(ConversionError, match="reviewer_policy_coverage_required"):
        build_conversion_review(review, "UTC", members=members, reviewer_policy=policy)


def test_missing_authority_is_explicit_not_inferred_from_completed_events():
    review, members, _ = inputs()
    result = build_conversion_review(review, "UTC", members=members)
    assert result.summary()["reviewer_authority"] == {"mode": "not_supplied"}
    assert result.private_data()["reviewer_authority"] is None
