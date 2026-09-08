"""Explicit owner-matched historical images; opaque legacy notes are not files.

This internal preparation API receives already selected bytes, never URLs, local
paths or Telegram credentials. It decodes in the existing bounded child process.
It does not authenticate HTTP users, fetch files, write a Store or activate data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..domain.media import IMAGE_MIME_TYPES, MAX_FILE_BYTES, MAX_VERIFIED_BYTES
from ..domain.validation import DomainError, timestamp
from ..media_storage import _settle, decode_file
from .preflight import _bounded_json
from .review import LegacyReview

MAX_ATTACHMENTS = 512
_KEY = re.compile(r"[a-zA-Z0-9_-]{1,80}")


class PhotoEvidenceError(ValueError):
    """Code only; never a filename, reference, decoder message or source title."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def submission_inventory(review: LegacyReview, *, members) -> list[dict]:
    """Owner-private references for an explicit matching screen, not diagnostics."""
    if type(review) is not LegacyReview or not review.matches_members(members):
        raise PhotoEvidenceError("review_changed")
    assistant, _, mapping = review.private_data()
    # LegacyReview's factory already rejects missing event IDs/timestamps and
    # invalid member revisions. It is not a raw-JSON input or an HTTP capability.
    ledger = assistant.get("ledger", assistant)
    rows = ledger["tasks"]
    submissions = []
    seen = set()
    for event in ledger["history"]:
        row = rows.get(event.get("task_id"), {})
        if not (
            row.get("kind") == "task"
            and row.get("requires_report") is True
            and row.get("report_type") == "photo"
            and event.get("type") == "submitted"
        ):
            continue
        details = event.get("details")
        note = details.get("report") if type(details) is dict else None
        sequence = event.get("sequence")
        binding = mapping.get(event.get("actor"), {})
        key = (event["task_id"], sequence)
        if (
            type(note) is not str
            or not note.strip()
            or len(note) > 2000
            or type(sequence) is not int
            or not 1 <= sequence <= 2**53 - 1
            or key in seen
            or binding.get("archive_only")
            or not binding.get("member_id")
        ):
            raise PhotoEvidenceError("photo_source_review_required")
        seen.add(key)
        submissions.append(
            {
                "task_id": event["task_id"],
                "event_sequence": sequence,
                "report_reference": note,
                "report_sha256": _digest(note.encode()),
                "submitted_at": event["at"],
                "assignee": binding["member_id"],
                "assignee_revision": binding["member_revision"],
            }
        )
        if len(submissions) > MAX_ATTACHMENTS:
            raise PhotoEvidenceError("photo_evidence_limit")
    return submissions


@dataclass(frozen=True, repr=False)
class PhotoEvidence:
    _review_fingerprint: str = field(repr=False)
    _private: bytes = field(repr=False)
    _blobs: tuple[tuple[str, bytes], ...] = field(repr=False)

    def __repr__(self):
        return "PhotoEvidence(private=True, activation_available=False)"

    def private_data(self):
        return json.loads(self._private)

    def private_blobs(self):
        return dict(self._blobs)

    def summary(self):
        return {
            "mode": "owner_matched_photos",
            "fingerprint": _digest(self._private),
            "images_count": len(self._blobs),
            "bytes_count": sum(len(content) for _, content in self._blobs),
            "image_identity_automatically_verified": False,
            "activation_available": False,
        }

    def require_matches(self, review, members):
        if (
            type(review) is not LegacyReview
            or not review.matches_members(members)
            or review.summary()["fingerprint"] != self._review_fingerprint
        ):
            raise PhotoEvidenceError("review_changed")


async def _verify_bytes(content):
    """Settle each file writer/decoder before destroying its private directory."""
    creating = asyncio.create_task(
        asyncio.to_thread(tempfile.TemporaryDirectory, prefix="fa-migration-photo-")
    )
    directory = None
    try:
        try:
            directory = await asyncio.shield(creating)
        except asyncio.CancelledError:
            directory = await _settle(creating)
            raise
        path = Path(directory.name) / "image"
        writing = asyncio.create_task(asyncio.to_thread(path.write_bytes, content))
        try:
            await asyncio.shield(writing)
        except asyncio.CancelledError:
            await _settle(writing)
            raise
        # decode_file itself kills and settles its child before propagating
        # cancellation, including repeated cancellation during process reaping.
        return await decode_file(path)
    finally:
        if directory is not None:
            cleaning = asyncio.create_task(asyncio.to_thread(directory.cleanup))
            try:
                await asyncio.shield(cleaning)
            except asyncio.CancelledError:
                await _settle(cleaning)
                raise


async def async_prepare_photo_evidence(
    review: LegacyReview,
    *,
    members,
    source_review_fingerprint: str,
    confirmed_by: str,
    prepared_at: datetime,
    confirmations: list[dict],
    attachments: dict[str, bytes],
) -> PhotoEvidence:
    """Require complete explicit event→image matches and verify every supplied image.

    The future authenticated caller must derive confirmed_by from a fresh owner
    identity and show the exact matching choices first. Digests prove byte identity,
    not that a photograph actually depicts the historical task.
    """
    inventory = submission_inventory(review, members=members)
    fingerprint = review.summary()["fingerprint"]
    owner = members.get(confirmed_by) if type(confirmed_by) is str else None
    if (
        not isinstance(owner, dict)
        or owner.get("role") != "owner"
        or owner.get("active") is not True
    ):
        raise PhotoEvidenceError("photo_owner_required")
    if source_review_fingerprint != fingerprint:
        raise PhotoEvidenceError("review_changed")
    try:
        prepared = timestamp(prepared_at, "prepared_at").isoformat()
    except DomainError:
        raise PhotoEvidenceError("photo_time_invalid") from None
    if (
        type(confirmations) is not list
        or type(attachments) is not dict
        or len(confirmations) != len(inventory)
        or len(attachments) != len(inventory)
        or any(type(key) is not str or not _KEY.fullmatch(key) for key in attachments)
        or any(
            type(value) is not bytes or not 0 < len(value) <= MAX_FILE_BYTES
            for value in attachments.values()
        )
        or sum(len(value) for value in attachments.values()) > MAX_VERIFIED_BYTES
    ):
        raise PhotoEvidenceError("photo_evidence_set_invalid")
    expected = {(row["task_id"], row["event_sequence"]): row for row in inventory}
    selected, used = [], set()
    for item in confirmations:
        if (
            type(item) is not dict
            or set(item) != {"task_id", "event_sequence", "report_sha256", "attachment_key"}
            or type(item["task_id"]) is not str
            or type(item["event_sequence"]) is not int
            or type(item["attachment_key"]) is not str
        ):
            raise PhotoEvidenceError("photo_evidence_set_invalid")
        row = expected.pop((item["task_id"], item["event_sequence"]), None)
        key = item["attachment_key"]
        if (
            row is None
            or item["report_sha256"] != row["report_sha256"]
            or key not in attachments
            or key in used
        ):
            raise PhotoEvidenceError("photo_evidence_set_invalid")
        used.add(key)
        # Freeze all caller-owned choices and bytes before the first await.
        selected.append((row, attachments[key]))
    if expected:
        raise PhotoEvidenceError("photo_evidence_set_invalid")
    records, blobs = [], []
    for row, content in sorted(
        selected, key=lambda item: (item[0]["task_id"], item[0]["event_sequence"])
    ):
        try:
            metadata = await _verify_bytes(content)
        except DomainError as error:
            raise PhotoEvidenceError(error.code) from None
        except (OSError, ValueError):
            raise PhotoEvidenceError("photo_image_invalid") from None
        digest = _digest(content)
        if (
            type(metadata) is not dict
            or type(metadata.get("mime_type")) is not str
            or metadata.get("mime_type") not in IMAGE_MIME_TYPES
            or type(metadata.get("size_bytes")) is not int
            or metadata["size_bytes"] != len(content)
            or metadata.get("sha256") != digest
        ):
            raise PhotoEvidenceError("photo_image_invalid")
        if not review.matches_members(members):
            raise PhotoEvidenceError("review_changed")
        token = _digest(
            _encode(["legacy-photo-v1", fingerprint, row["task_id"], row["event_sequence"], digest])
        )
        records.append(
            {
                **{key: value for key, value in row.items() if key != "report_reference"},
                "media_id": "M" + token[:32],
                "blob_key": token,
                "sha256": digest,
                "mime_type": metadata["mime_type"],
                "size_bytes": len(content),
            }
        )
        blobs.append((token, content))
    if not review.matches_members(members):
        raise PhotoEvidenceError("review_changed")
    payload = _encode(
        {
            "version": 1,
            "source_review_fingerprint": fingerprint,
            "confirmed_by": confirmed_by,
            "owner_revision": owner["revision"],
            "prepared_at": prepared,
            "records": records,
        }
    )
    return PhotoEvidence(fingerprint, payload, tuple(blobs))


async def async_restore_photo_evidence(review, *, members, archive, blobs) -> PhotoEvidence:
    """Reverify every archived byte and exact mapping; JSON metadata grants nothing.

    This is an internal private archive decoder, not fresh user confirmation or an
    import endpoint. Authentication and explicit acceptance remain caller duties.
    """
    try:
        if (
            type(archive) is not dict
            or not _bounded_json(archive)
            or set(archive)
            != {
                "version",
                "source_review_fingerprint",
                "confirmed_by",
                "owner_revision",
                "prepared_at",
                "records",
            }
            or type(archive["version"]) is not int
            or archive["version"] != 1
            or type(archive["records"]) is not list
            or len(archive["records"]) > MAX_ATTACHMENTS
            or type(blobs) is not dict
        ):
            raise PhotoEvidenceError("photo_evidence_archive_invalid")
        expected = _encode(archive)
        frozen = json.loads(expected)
        choices = [
            {
                "task_id": row["task_id"],
                "event_sequence": row["event_sequence"],
                "report_sha256": row["report_sha256"],
                "attachment_key": row["blob_key"],
            }
            for row in frozen["records"]
        ]
        prepared = timestamp(frozen["prepared_at"], "prepared_at")
    except (KeyError, TypeError, DomainError):
        raise PhotoEvidenceError("photo_evidence_archive_invalid") from None
    result = await async_prepare_photo_evidence(
        review,
        members=members,
        source_review_fingerprint=frozen["source_review_fingerprint"],
        confirmed_by=frozen["confirmed_by"],
        prepared_at=prepared,
        confirmations=choices,
        attachments=blobs,
    )
    if result._private != expected:
        raise PhotoEvidenceError("photo_evidence_archive_changed")
    return result
