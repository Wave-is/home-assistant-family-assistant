"""Private, immutable source/mapping reviews; no filesystem or import authority.

Only fixed-code errors and counts-only summaries are safe to display. Raw Store
bytes and legacy payloads stay in these local objects and are never model input.
Fingerprint equality proves unchanged inputs, NOT a coherent source snapshot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from hmac import compare_digest

from .preflight import MAX_BYTES, _bounded_json, _integer, _text, inspect_legacy

ASSISTANT_KEY = "family_assistant.tasks"
COURT_KEY = "family_court.ledger"
STORE_FIELDS = frozenset({"version", "minor_version", "key", "data"})
ROLES = frozenset({"owner", "parent", "adult", "child", "guest"})


class LegacyReviewError(ValueError):
    """Fixed code only; never interpolate a source field, JSON error or identity."""


def _encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LegacyReviewError("source_duplicate_key")
        result[key] = value
    return result


def _constant(_value):
    raise LegacyReviewError("source_invalid_json")


def _store(content, expected_key):
    if type(content) is not bytes or not 0 < len(content) <= MAX_BYTES:
        raise LegacyReviewError("source_bytes_limit")
    try:
        wrapper = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant
        )
    except LegacyReviewError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise LegacyReviewError("source_invalid_json") from None
    if not _bounded_json(wrapper):
        raise LegacyReviewError("source_json_limits")
    if (
        type(wrapper) is not dict
        or wrapper.keys() - STORE_FIELDS
        or wrapper.get("key") != expected_key
        or type(wrapper.get("version")) is not int
        or wrapper["version"] != 1
        or type(wrapper.get("minor_version", 1)) is not int
        or wrapper.get("minor_version", 1) != 1
        or type(wrapper.get("data")) is not dict
    ):
        raise LegacyReviewError("source_store_wrapper")
    return wrapper["data"]


def _member_mapping(mapping, members, mapping_revision):
    if not _integer(mapping_revision, 1):
        raise LegacyReviewError("invalid_mapping_revision")
    if (
        type(mapping) is not dict
        or not 1 <= len(mapping) <= 512
        or not _bounded_json(mapping)
        or not all(_text(key, 128) for key in mapping)
    ):
        raise LegacyReviewError("invalid_member_mapping")
    if type(members) is not dict or not 1 <= len(members) <= 512 or not _bounded_json(members):
        raise LegacyReviewError("invalid_target_members")
    for key, member in members.items():
        if (
            not _text(key, 80)
            or type(member) is not dict
            or member.get("id") != key
            or type(member.get("role")) is not str
            or member["role"] not in ROLES
            or type(member.get("active")) is not bool
            or not _integer(member.get("revision"), 1)
        ):
            raise LegacyReviewError("invalid_target_members")
    targets = set()
    for binding in mapping.values():
        if type(binding) is not dict:
            raise LegacyReviewError("invalid_member_mapping")
        if set(binding) == {"archive_only"} and binding["archive_only"] is True:
            continue
        if (
            set(binding) != {"member_id", "member_revision"}
            or not _text(binding["member_id"], 80)
            or not _integer(binding["member_revision"], 1)
        ):
            raise LegacyReviewError("invalid_member_mapping")
        target = members.get(binding["member_id"])
        if (
            target is None
            or not target["active"]
            or target["role"] == "guest"
            or target["revision"] != binding["member_revision"]
        ):
            raise LegacyReviewError("target_member_changed")
        if target["id"] in targets:
            raise LegacyReviewError("collapsed_member_mapping")
        targets.add(target["id"])


def _required_subjects(assistant, court):
    """History-only actors may be archived, but never a task owner or recipient."""
    envelope = "ledger" in assistant
    ledger = assistant["ledger"] if envelope else assistant
    subjects = set(court["children"])
    for row in ledger["tasks"].values():
        subjects.update(row[key] for key in ("creator", "assignee", "reviewer") if row.get(key))
    if envelope:
        alarm_data = assistant.get("alarms", {})
        subjects.update(alarm_data.get("schedules", {}))
        subjects.update(row["child"] for row in alarm_data.get("runs", {}).values())
    return subjects


@dataclass(frozen=True, repr=False)
class LegacySource:
    """Construct with read_store_pair, not by reading a live Store from this module."""

    _assistant: bytes = field(repr=False)
    _court: bytes = field(repr=False)

    def __repr__(self):
        return "LegacySource(private=True)"

    def private_data(self) -> tuple[dict, dict]:
        """Fresh copies for the future local converter; never an API response."""
        return _store(self._assistant, ASSISTANT_KEY), _store(self._court, COURT_KEY)

    def inspect(self, known_members: set[str]) -> dict:
        return inspect_legacy(*self.private_data(), known_members)

    def review(self, mapping: dict, members: dict, *, mapping_revision: int):
        _member_mapping(mapping, members, mapping_revision)
        assistant, court = self.private_data()
        report = inspect_legacy(assistant, court, set(mapping))
        if report["issues"]:
            raise LegacyReviewError("source_preflight_failed")
        if any(
            mapping[subject].get("archive_only") for subject in _required_subjects(assistant, court)
        ):
            raise LegacyReviewError("subject_requires_member")
        # Freeze caller-owned dictionaries before hashing or retaining anything.
        frozen_mapping = _encode(mapping)
        member_hash = _digest(_encode(members))
        stamp = {
            "version": 1,
            "assistant": _digest(self._assistant),
            "court": _digest(self._court),
            "mapping": _digest(frozen_mapping),
            "members": member_hash,
            "mapping_revision": mapping_revision,
        }
        return LegacyReview(
            self,
            frozen_mapping,
            mapping_revision,
            _digest(_encode(stamp)),
            _encode(report["counts"]),
        )


@dataclass(frozen=True, repr=False)
class LegacyReview:
    """A review is not a capability: no method imports or writes domain state."""

    _source: LegacySource = field(repr=False)
    _mapping: bytes = field(repr=False)
    _mapping_revision: int
    _fingerprint: str = field(repr=False)
    _counts: bytes = field(repr=False)

    def __repr__(self):
        return "LegacyReview(private=True, import_available=False)"

    def summary(self) -> dict:
        return {
            "mode": "source_mapping_review",
            "fingerprint": self._fingerprint,
            "mapping_revision": self._mapping_revision,
            "counts": json.loads(self._counts),
            "coherence_verified": False,
            "import_available": False,
        }

    def private_data(self) -> tuple[dict, dict, dict]:
        return (*self._source.private_data(), json.loads(self._mapping))

    def matches(self, assistant, court, mapping, members, *, mapping_revision) -> bool:
        """Fail closed on every changed source byte or current member/binding field."""
        try:
            current = read_store_pair(assistant, court).review(
                mapping, members, mapping_revision=mapping_revision
            )
        except LegacyReviewError:
            return False
        return compare_digest(self._fingerprint, current._fingerprint)


def read_store_pair(assistant: bytes, court: bytes) -> LegacySource:
    """Decode exact schema-1 wrappers from an already obtained private export."""
    _store(assistant, ASSISTANT_KEY)
    _store(court, COURT_KEY)
    return LegacySource(assistant, court)
