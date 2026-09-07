"""Synthetic byte/parser/mapping boundaries; no source export or live Store I/O."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from custom_components.family_assistant.migration.review import (
    ASSISTANT_KEY,
    COURT_KEY,
    LegacyReviewError,
    read_store_pair,
)

STAMP = "2026-09-07T08:00:00+00:00"


def encoded(value):
    return json.dumps(value, ensure_ascii=True).encode()


def wrapped(data, key):
    return encoded({"key": key, "version": 1, "minor_version": 1, "data": data})


@pytest.fixture
def source_pair():
    ledger = {
        "schema_version": 1,
        "next_task_sequence": 2,
        "next_event_sequence": 2,
        "tasks": {
            "T000001": {
                "task_id": "T000001",
                "kind": "task",
                "state": "assigned",
                "title": "Synthetic private title",
                "creator": "old-parent",
                "assignee": "old-child",
                "reviewer": None,
                "created_at": STAMP,
                "due_at": STAMP,
                "metadata": {"private-transport": "synthetic-only-value"},
            }
        },
        "history": [{"sequence": 1, "task_id": "T000001", "actor": "old-system", "at": STAMP}],
        "processed_commands": {},
    }
    assistant = {"ledger": ledger, "alarms": {"schedules": {}, "runs": {}}}
    court = {
        "schema_version": 1,
        "week_id": "source-period",
        "opened_at": STAMP,
        "children": {"old-child": {"pluses": 0, "minuses": 0}},
        "history": [],
        "archived_weeks": [],
        "processed_messages": {},
    }
    members = {
        "owner": {
            "id": "owner",
            "revision": 3,
            "active": True,
            "role": "owner",
            "name": "Synthetic owner",
            "ha_user_id": "synthetic-local-binding",
        },
        "child": {
            "id": "child",
            "revision": 4,
            "active": True,
            "role": "child",
            "name": "Synthetic child",
        },
    }
    mapping = {
        "old-parent": {"member_id": "owner", "member_revision": 3},
        "old-child": {"member_id": "child", "member_revision": 4},
        "old-system": {"archive_only": True},
    }
    return wrapped(assistant, ASSISTANT_KEY), wrapped(court, COURT_KEY), mapping, members


def reviewed(source_pair):
    assistant, court, mapping, members = source_pair
    return read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)


def test_exact_read_only_review_is_private_immutable_and_not_import(source_pair):
    before = deepcopy(source_pair)
    source = read_store_pair(*source_pair[:2])
    review = reviewed(source_pair)
    summary = review.summary()
    assert summary["mode"] == "source_mapping_review"
    assert summary["counts"]["tasks"] == 1
    assert summary["coherence_verified"] is False
    assert summary["import_available"] is False
    assert len(summary["fingerprint"]) == 64
    assert source.inspect(set(source_pair[2]))["issues"] == []
    assert review.matches(*source_pair, mapping_revision=1)
    public = json.dumps(summary) + repr(source) + repr(review)
    for private in (
        "Synthetic",
        "old-child",
        "old-parent",
        "old-system",
        "local-binding",
        "T000001",
        "source-period",
        "private-transport",
    ):
        assert private not in public
    assert source_pair == before
    with pytest.raises(FrozenInstanceError):
        review._mapping_revision = 9
    summary["counts"]["tasks"] = 999
    assert review.summary()["counts"]["tasks"] == 1


def test_private_data_are_copies_never_live_target_state(source_pair):
    review = reviewed(source_pair)
    private = review.private_data()
    private[0]["ledger"]["tasks"].clear()
    private[1]["children"].clear()
    private[2]["old-child"]["member_id"] = "owner"
    again = review.private_data()
    assert len(again[0]["ledger"]["tasks"]) == 1
    assert again[1]["children"]
    assert again[2]["old-child"]["member_id"] == "child"
    assert "ha_user_id" not in json.dumps(again)


@pytest.mark.parametrize(
    "replacement",
    [
        None,
        "{}",
        bytearray(b"{}"),
        b"",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"{",
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"[" * 1500 + b"]" * 1500,
        b'{"private":1,"private":2}',
        b'{"x": {"private":1,"private":2}}',
        b"9" * 5000,
    ],
)
def test_bad_json_never_surfaces_source_text(source_pair, replacement):
    with pytest.raises(LegacyReviewError) as caught:
        read_store_pair(replacement, source_pair[1])
    assert str(caught.value) in {
        "source_bytes_limit",
        "source_invalid_json",
        "source_duplicate_key",
        "source_json_limits",
    }
    assert "private" not in repr(caught.value)
    assert not reviewed(source_pair).matches(replacement, *source_pair[1:], mapping_revision=1)


@pytest.mark.parametrize(
    "change",
    [
        {"version": True},
        {"version": 2},
        {"version": 1.0},
        {"minor_version": True},
        {"minor_version": 2},
        {"minor_version": 1.0},
        {"key": COURT_KEY},
        {"extra": "synthetic-private"},
        {"data": []},
        {"data": None},
    ],
)
def test_store_wrappers_are_exact_and_not_guessed(source_pair, change):
    wrapper = json.loads(source_pair[0])
    wrapper.update(change)
    with pytest.raises(LegacyReviewError, match="^source_store_wrapper$"):
        read_store_pair(encoded(wrapper), source_pair[1])


def test_explicit_store_wrapper_is_required_and_optional_minor_one_is_supported(source_pair):
    wrapper = json.loads(source_pair[0])
    with pytest.raises(LegacyReviewError, match="source_store_wrapper"):
        read_store_pair(encoded(wrapper["data"]), source_pair[1])
    wrapper.pop("minor_version")
    assert (
        read_store_pair(encoded(wrapper), source_pair[1]).inspect(set(source_pair[2]))["issues"]
        == []
    )
    wrapper.pop("version")
    with pytest.raises(LegacyReviewError, match="source_store_wrapper"):
        read_store_pair(encoded(wrapper), source_pair[1])


@pytest.mark.parametrize("value", ["\ud800", 2**53, [None] * 100_001])
def test_bounded_domain_payloads_precede_reviews(source_pair, value):
    wrapper = json.loads(source_pair[0])
    wrapper["data"]["private"] = value
    with pytest.raises(LegacyReviewError, match="source_json_limits"):
        read_store_pair(encoded(wrapper), source_pair[1])


def test_byte_and_depth_limits_are_independent(source_pair, monkeypatch):
    from custom_components.family_assistant.migration import review as module

    monkeypatch.setattr(module, "MAX_BYTES", len(source_pair[0]) - 1)
    with pytest.raises(LegacyReviewError, match="source_bytes_limit"):
        read_store_pair(*source_pair[:2])
    monkeypatch.undo()
    nested = {}
    for _ in range(40):
        nested = {"nested": nested}
    with pytest.raises(LegacyReviewError, match="source_json_limits"):
        read_store_pair(wrapped(nested, ASSISTANT_KEY), source_pair[1])


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"old-child": []},
        {"old-child": {"archive_only": 1}},
        {"old-child": {"member_id": "child", "member_revision": True}},
        {"old-child": {"member_id": [], "member_revision": 4}},
        {"old-child": {"member_id": "child", "member_revision": 4, "role": "owner"}},
    ],
)
def test_mapping_is_explicit_and_cannot_create_authority(source_pair, value):
    source = read_store_pair(*source_pair[:2])
    with pytest.raises(LegacyReviewError, match="invalid_member_mapping"):
        source.review(value, source_pair[3], mapping_revision=1)


@pytest.mark.parametrize("revision", [True, 0, -1, 1.0, "1", None, 2**53])
def test_mapping_revision_is_strict(source_pair, revision):
    with pytest.raises(LegacyReviewError, match="invalid_mapping_revision"):
        read_store_pair(*source_pair[:2]).review(*source_pair[2:], mapping_revision=revision)


def test_history_actor_can_be_archived_but_not_collapsed_or_given_recipient_rights(source_pair):
    assistant, court, mapping, members = source_pair
    source = read_store_pair(assistant, court)
    mapping["old-system"] = {"member_id": "owner", "member_revision": 3}
    with pytest.raises(LegacyReviewError, match="collapsed_member_mapping"):
        source.review(mapping, members, mapping_revision=1)
    mapping["old-system"] = {"archive_only": True}
    mapping["old-child"] = {"archive_only": True}
    with pytest.raises(LegacyReviewError, match="subject_requires_member"):
        source.review(mapping, members, mapping_revision=1)


def test_preflight_blockers_prevent_review_without_invented_mapping(source_pair):
    assistant, court, mapping, members = source_pair
    mapping.pop("old-system")
    source = read_store_pair(assistant, court)
    assert source.inspect(set(mapping))["issues"] == [{"code": "unmapped_members", "count": 1}]
    with pytest.raises(LegacyReviewError, match="source_preflight_failed"):
        source.review(mapping, members, mapping_revision=1)


@pytest.mark.parametrize("change", [{"revision": 5}, {"active": False}, {"role": "guest"}])
def test_target_must_still_be_the_reviewed_active_nonguest(source_pair, change):
    assistant, court, mapping, members = source_pair
    old = reviewed(source_pair)
    members["child"].update(change)
    assert not old.matches(*source_pair, mapping_revision=1)
    with pytest.raises(LegacyReviewError, match="target_member_changed"):
        read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ha_user_id", "synthetic-new-user"),
        ("telegram_user_id", 123),
        ("name", "New display"),
        ("role", "parent"),
        ("aliases", ["New alias"]),
    ],
)
def test_all_current_member_fields_are_pinned_even_without_revision_bump(source_pair, field, value):
    old = reviewed(source_pair)
    source_pair[3]["child"][field] = value
    assert not old.matches(*source_pair, mapping_revision=1)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"owner": None},
        {"owner": {"id": "owner", "role": [], "active": True, "revision": 1}},
    ],
)
def test_invalid_target_inventory_has_fixed_errors(source_pair, value):
    with pytest.raises(LegacyReviewError, match="invalid_target_members"):
        read_store_pair(*source_pair[:2]).review(source_pair[2], value, mapping_revision=1)


def test_fingerprint_binds_both_raw_sources_mapping_version_and_member_inventory(source_pair):
    assistant, court, mapping, members = source_pair
    review = reviewed(source_pair)
    assert not review.matches(assistant + b" ", court, mapping, members, mapping_revision=1)
    assert not review.matches(assistant, court + b" ", mapping, members, mapping_revision=1)
    assert not review.matches(*source_pair, mapping_revision=2)
    reordered = dict(reversed(list(mapping.items())))
    assert review.matches(assistant, court, reordered, members, mapping_revision=1)
    mapping["additional-historical-actor"] = {"archive_only": True}
    assert not review.matches(*source_pair, mapping_revision=1)
    assert "additional-historical-actor" not in review.private_data()[2]


def test_stored_data_are_kept_exactly_without_running_legacy_receipts(source_pair):
    wrapper = json.loads(source_pair[0])
    wrapper["data"]["processed_home_updates"] = ["synthetic-transport-receipt"]
    wrapper["data"]["memories"] = {"private": "synthetic-stale-plan"}
    assistant = wrapped(wrapper["data"], ASSISTANT_KEY)
    review = read_store_pair(assistant, source_pair[1]).review(*source_pair[2:], mapping_revision=1)
    assert review.private_data()[0] == wrapper["data"]
    assert review.summary()["import_available"] is False
