"""Local-only review archive codec; no filesystem, import or authorization I/O.

The output contains private source bytes and must only enter owner-private local
storage/backup. Checksums detect changed input, not tampering by a trusted owner.
They are never proof of coherent source capture or permission to activate data.
"""

from __future__ import annotations

import base64
import binascii
import json
import re

from .preflight import MAX_BYTES
from .review import LegacyReview, LegacyReviewError, _constant, _object, read_store_pair

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_BASE64_BYTES = 4 * ((MAX_BYTES + 2) // 3)
FIELDS = {"version", "assistant", "court", "mapping", "mapping_revision", "fingerprint"}


class ArchiveError(ValueError):
    """Fixed code only; never echo the archive, source content or parser errors."""


def encode_private_review(review: LegacyReview, *, members=None) -> bytes:
    if type(review) is not LegacyReview or not review.matches_members(members):
        raise ArchiveError("review_changed")
    # Exact original Store-file bytes, not normalized/re-serialized domain JSON.
    value = {
        "version": 1,
        "assistant": base64.b64encode(review._source._assistant).decode("ascii"),
        "court": base64.b64encode(review._source._court).decode("ascii"),
        "mapping": json.loads(review._mapping),
        "mapping_revision": review._mapping_revision,
        "fingerprint": review.summary()["fingerprint"],
    }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > MAX_ARCHIVE_BYTES:
        raise ArchiveError("archive_bytes_limit")
    return encoded


def _decode_source(value):
    if type(value) is not str or not 0 < len(value) <= MAX_BASE64_BYTES:
        raise ArchiveError("archive_invalid")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, UnicodeError):
        raise ArchiveError("archive_invalid") from None
    if not 0 < len(decoded) <= MAX_BYTES or base64.b64encode(decoded).decode("ascii") != value:
        raise ArchiveError("archive_invalid")
    return decoded


def decode_private_review(content: bytes, *, members=None) -> LegacyReview:
    """Revalidate current identities after reloading an owner-private archive."""
    if type(content) is not bytes or not 0 < len(content) <= MAX_ARCHIVE_BYTES:
        raise ArchiveError("archive_bytes_limit")
    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant
        )
        if (
            type(value) is not dict
            or set(value) != FIELDS
            or type(value["version"]) is not int
            or value["version"] != 1
            or type(value["fingerprint"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", value["fingerprint"])
        ):
            raise ArchiveError("archive_invalid")
        source = read_store_pair(_decode_source(value["assistant"]), _decode_source(value["court"]))
        review = source.review(
            value["mapping"], members, mapping_revision=value["mapping_revision"]
        )
    except ArchiveError:
        raise
    except (LegacyReviewError, UnicodeError, ValueError, TypeError, RecursionError):
        raise ArchiveError("archive_invalid") from None
    if review.summary()["fingerprint"] != value["fingerprint"]:
        raise ArchiveError("review_changed")
    return review
