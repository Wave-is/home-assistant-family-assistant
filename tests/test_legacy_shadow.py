"""Whole synthetic shadow construction; no partial copy or activation."""

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from ha_legacy_archive_smoke import synthetic_source

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.migration.archive import decode_private_review
from custom_components.family_assistant.migration.review import read_store_pair
from custom_components.family_assistant.migration.shadow import ShadowError, build_shadow_candidate

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def inputs():
    assistant, court, mapping, members = synthetic_source(lifecycle=True)
    target = new_state("synthetic-owner", "Synthetic shadow", modules=[])
    for member in members.values():
        member.update(
            language="en",
            aliases=[],
            ha_user_id="synthetic-owner" if member["role"] == "owner" else None,
        )
    target["members"] = members
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    policy = {
        "schema": 1,
        "revision": 1,
        "source_review_fingerprint": review.summary()["fingerprint"],
        "reviewers": {
            key: [row["reviewer"]]
            for key, row in review.private_data()[0]["ledger"]["tasks"].items()
            if row.get("requires_report") is True
        },
    }
    return review, target, policy


def test_whole_candidate_exact_replay_archive_counts_ids_and_source_unchanged():
    review, target, policy = inputs()
    original = deepcopy((target, policy, review.private_data()))
    candidate = build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)
    state = candidate.private_state()
    assert candidate.summary()["counts"] == {
        "members": 2,
        "tasks": 3,
        "shopping": 1,
        "court": 1,
        "alarms": 1,
    }
    assert state["tasks"]["T000004"]["report"] == "Report after reassignment"
    assert state["tasks"]["T000003"]["delivery_scope"] == "personal"
    assert state["shopping"]["S000001"]["purchased"] == 1.5
    assert state["migration_archive"]["id_map"]["shopping"] == {"T000001": "S000001"}
    assert state["alarms"]["A000001"]["enabled"] is False
    restored = decode_private_review(
        json.dumps(state["migration_archive"]["archive"]).encode(), members=target["members"]
    )
    assert restored._source == review._source
    assert (
        candidate.private_state()
        == build_shadow_candidate(
            restored, target, reviewer_policy=policy, prepared_at=NOW
        ).private_state()
    )
    assert (target, policy, review.private_data()) == original
    assert not candidate.summary()["activation_available"]
    assert not candidate.summary()["coherence_verified"]
    public = repr(candidate) + json.dumps(candidate.summary())
    for private in (
        "Report after reassignment",
        "synthetic-owner",
        "old-child",
        "T000001",
        "Яблоки",
    ):
        assert private not in public
    state["tasks"].clear()
    assert candidate.private_state()["tasks"]


@pytest.mark.asyncio
async def test_actual_engine_no_incidents_effects_or_updates_even_far_past_due():
    review, target, policy = inputs()
    state = build_shadow_candidate(
        review, target, reviewer_policy=policy, prepared_at=NOW
    ).private_state()

    async def save(_state):
        pytest.fail("Shadow persisted a change")

    engine = Engine(state, save)
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await engine.tick(datetime(2027, 1, 1, tzinfo=UTC))
    assert engine.snapshot() == state and not state["outbox"] and not state["incidents"]


@pytest.mark.parametrize(
    "mutation",
    [
        "task",
        "processed",
        "revision",
        "modules",
        "binding",
        "missing_policy",
        "parent",
        "malformed_member",
    ],
)
def test_nonempty_changed_or_unreviewed_target_is_not_overwritten(mutation):
    review, target, policy = inputs()
    if mutation == "task":
        target["tasks"]["existing"] = {"title": "Private existing task"}
    elif mutation == "processed":
        target["processed"]["existing"] = {"done": True}
    elif mutation == "revision":
        target["revision"] = 1
    elif mutation == "modules":
        target["settings"]["modules"] = ["tasks"]
    elif mutation == "binding":
        target["members"]["owner"]["ha_user_id"] = "changed"
    elif mutation == "missing_policy":
        policy = None
    elif mutation == "malformed_member":
        target["members"]["child"]["language"] = None
    else:
        target["members"]["new-parent"] = {
            **target["members"]["child"],
            "id": "new-parent",
            "role": "parent",
        }
        review = review._source.review(
            review.private_data()[2], target["members"], mapping_revision=1
        )
        policy["source_review_fingerprint"] = review.summary()["fingerprint"]
    before = deepcopy(target)
    with pytest.raises(ShadowError):
        build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)
    assert before == target


def test_one_blocked_record_rejects_all_modules_instead_of_partial_import():
    review, target, policy = inputs()
    raw = json.loads(review._source._assistant)
    raw["data"]["ledger"]["tasks"]["T000001"]["metadata"]["shopping_quantity"] = 3.0000001
    review = read_store_pair(json.dumps(raw).encode(), review._source._court).review(
        review.private_data()[2], target["members"], mapping_revision=1
    )
    policy["source_review_fingerprint"] = review.summary()["fingerprint"]
    with pytest.raises(ShadowError, match="shadow_complete_conversion_required"):
        build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)


def test_configured_member_sequence_is_reserved_without_changing_binding():
    review, target, policy = inputs()
    child = target["members"].pop("child")
    child["id"] = "M000125"
    target["members"][child["id"]] = child
    mapping = review.private_data()[2]
    mapping["old-child"]["member_id"] = child["id"]
    review = review._source.review(mapping, target["members"], mapping_revision=2)
    policy["source_review_fingerprint"] = review.summary()["fingerprint"]
    state = build_shadow_candidate(
        review, target, reviewer_policy=policy, prepared_at=NOW
    ).private_state()
    assert state["sequences"]["M"] == 125
    assert state["tasks"]["T000002"]["assignee"] == child["id"]
    assert state["members"] == target["members"]
