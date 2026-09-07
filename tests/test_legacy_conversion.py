"""A joined review never loses blocked rows or upgrades a checksum to permission."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
from ha_legacy_archive_smoke import synthetic_source

from custom_components.family_assistant.migration.archive import decode_private_review
from custom_components.family_assistant.migration.conversion import (
    ConversionError,
    build_conversion_review,
)
from custom_components.family_assistant.migration.review import read_store_pair


def fixture():
    assistant, court, mapping, members = synthetic_source()
    return read_store_pair(assistant, court).review(mapping, members, mapping_revision=1), members


def test_all_buckets_joined_with_blocked_personal_record_and_single_archive():
    review, members = fixture()
    result = build_conversion_review(review, "Europe/Paris", members=members)
    summary, private = result.summary(), result.private_data()
    assert set(summary["modules"]) == {"alarms", "tasks", "shopping", "court"}
    assert summary["blocked_records_count"] == 1
    assert (
        summary["source_counts"]["tasks"]
        == summary["source_counts"]["reminders"]
        == summary["source_counts"]["shopping"]
        == 1
    )
    assert summary["coherence_verified"] is summary["import_available"] is False
    assert private["plans"]["tasks"]["blocked"] == [
        {"source_task": "T000003", "code": "task_personal_scope_unsupported"}
    ]
    assert all("archive" not in plan for plan in private["plans"].values())
    assert private["plans"]["alarms"]["proposals"][0]["payload"]["enabled"] is False
    restored = decode_private_review(result.private_archive_bytes(), members=members)
    assert restored._source == review._source
    assert restored.summary() == review.summary()
    repeated = build_conversion_review(restored, "Europe/Paris", members=members)
    assert repeated.summary() == summary
    assert repeated.private_data() == private


def test_summary_privacy_immutable_copies_and_timezone_fingerprint():
    review, members = fixture()
    result = build_conversion_review(review, "UTC", members=members)
    public = json.dumps(result.summary()) + repr(result)
    for value in (
        "old-parent",
        "old-child",
        "T000001",
        "Яблоки",
        "synthetic-note",
        "source-period",
        "private-original",
    ):
        assert value not in public
    assert repr(result) == "ConversionReview(private=True, import_available=False)"
    private = result.private_data()
    private["plans"].clear()
    private["archive"].clear()
    result.summary()["source_counts"].clear()
    assert result.private_data()["plans"] and result.private_data()["archive"]
    assert result.summary()["source_counts"]
    with pytest.raises(FrozenInstanceError):
        result._summary = b"{}"
    other = build_conversion_review(review, "Europe/Paris", members=members)
    assert other.summary()["fingerprint"] != result.summary()["fingerprint"]


def test_invalid_review_timezone_and_current_binding_have_fixed_errors():
    review, members = fixture()
    with pytest.raises(ConversionError, match="^review_changed$"):
        build_conversion_review(None, "UTC", members=members)
    with pytest.raises(ConversionError, match="^review_changed$"):
        build_conversion_review(review, "UTC")
    changed = deepcopy(members)
    changed["owner"]["ha_user_id"] = "another-owner"
    with pytest.raises(ConversionError, match="^review_changed$"):
        build_conversion_review(review, "UTC", members=changed)
    with pytest.raises(ConversionError, match="^invalid_timezone$"):
        build_conversion_review(review, "Not/AZone", members=members)
