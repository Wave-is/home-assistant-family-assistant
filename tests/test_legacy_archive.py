"""Archive codec preserves original private bytes but never grants import authority."""

import base64
import json
from copy import deepcopy

import pytest
from ha_legacy_archive_smoke import proposals, synthetic_source

from custom_components.family_assistant.migration import archive
from custom_components.family_assistant.migration.review import read_store_pair


def fixture():
    assistant, court, mapping, members = synthetic_source()
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    return review, members, archive.encode_private_review(review, members=members)


def test_exact_original_source_bytes_and_all_proposals_survive_roundtrip():
    review, members, content = fixture()
    restored = archive.decode_private_review(content, members=members)
    assert restored.summary() == review.summary()
    assert restored._source == review._source
    assert restored._source._assistant.endswith(b"\n")
    assert b"  " in restored._source._assistant
    assert restored.private_data() == review.private_data()
    assert archive.encode_private_review(restored, members=members) == content
    assert proposals(restored, members) == proposals(review, members)
    assert (
        restored.summary()["coherence_verified"] is restored.summary()["import_available"] is False
    )


@pytest.mark.parametrize(
    "content",
    [
        b"",
        None,
        "{}",
        b"\xff",
        b"{",
        b"[]",
        b"{}",
        b"null",
        b'{"version":1,"version":1}',
        b'{"foo":NaN}',
    ],
)
def test_invalid_archive_has_fixed_error_without_content(content):
    _, members, _ = fixture()
    with pytest.raises(archive.ArchiveError) as error:
        archive.decode_private_review(content, members=members)
    assert str(error.value) in {"archive_invalid", "archive_bytes_limit"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 2),
        ("version", 1.0),
        ("version", "1"),
        ("assistant", ""),
        ("assistant", 123),
        ("assistant", "not base64"),
        ("assistant", "☃"),
        ("assistant", "e30="),
        ("court", "===="),
        ("court", None),
        ("mapping", []),
        ("mapping_revision", True),
        ("mapping_revision", 0),
        ("fingerprint", "x" * 64),
        ("fingerprint", "é" * 64),
        ("fingerprint", None),
    ],
)
def test_corrupt_envelope_or_source_rejected(field, value):
    _, members, content = fixture()
    value_dict = json.loads(content)
    value_dict[field] = value
    with pytest.raises(archive.ArchiveError, match="^archive_invalid$"):
        archive.decode_private_review(json.dumps(value_dict).encode(), members=members)


def test_unknown_fields_and_noncanonical_base64_are_not_ignored():
    _, members, content = fixture()
    value = json.loads(content)
    value["unknown"] = "do-not-accept"
    with pytest.raises(archive.ArchiveError, match="^archive_invalid$"):
        archive.decode_private_review(json.dumps(value).encode(), members=members)
    value.pop("unknown")
    value["assistant"] += "===="
    with pytest.raises(archive.ArchiveError, match="^archive_invalid$"):
        archive.decode_private_review(json.dumps(value).encode(), members=members)


def test_changed_source_bytes_or_mapping_revision_change_review_fingerprint():
    _, members, content = fixture()
    for field in ("assistant", "mapping_revision"):
        value = json.loads(content)
        if field == "assistant":
            raw = base64.b64decode(value[field]) + b" "
            value[field] = base64.b64encode(raw).decode()
        else:
            value[field] += 1
        with pytest.raises(archive.ArchiveError, match="^review_changed$"):
            archive.decode_private_review(json.dumps(value).encode(), members=members)


@pytest.mark.parametrize(
    "field,value", [("telegram_id", 9292), ("name", "Changed"), ("role", "parent")]
)
def test_current_member_values_checked_again_after_restart(field, value):
    review, members, content = fixture()
    changed = deepcopy(members)
    changed["child"][field] = value
    with pytest.raises(archive.ArchiveError, match="^review_changed$"):
        archive.decode_private_review(content, members=changed)
    with pytest.raises(archive.ArchiveError, match="^review_changed$"):
        archive.encode_private_review(review, members=changed)
    assert archive.decode_private_review(content, members=members).summary() == review.summary()


def test_missing_current_members_and_invalid_review_fail_closed():
    review, _, content = fixture()
    with pytest.raises(archive.ArchiveError, match="^archive_invalid$"):
        archive.decode_private_review(content)
    for value in (review, None, {}):
        with pytest.raises(archive.ArchiveError, match="^review_changed$"):
            archive.encode_private_review(value)


def test_archive_and_source_limits_precede_decoding(monkeypatch):
    review, members, content = fixture()
    monkeypatch.setattr(archive, "MAX_ARCHIVE_BYTES", len(content) - 1)
    with pytest.raises(archive.ArchiveError, match="^archive_bytes_limit$"):
        archive.decode_private_review(content, members=members)
    with pytest.raises(archive.ArchiveError, match="^archive_bytes_limit$"):
        archive.encode_private_review(review, members=members)
    monkeypatch.setattr(archive, "MAX_ARCHIVE_BYTES", len(content))
    monkeypatch.setattr(archive, "MAX_BASE64_BYTES", 4)
    with pytest.raises(archive.ArchiveError, match="^archive_invalid$"):
        archive.decode_private_review(content, members=members)
