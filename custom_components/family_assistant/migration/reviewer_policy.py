"""Compare explicitly supplied legacy reviewer sets; never grant or import rights.

The source adapter/operator must supply the complete effective per-task policy.
Names and historical review events are not evidence of current reviewer authority.
This comparison cannot verify source capture or the truth of supplied policy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from hmac import compare_digest

from .preflight import _bounded_json, _integer, _text
from .review import LegacyReview


class ReviewerPolicyError(ValueError):
    """Fixed codes only, never identifiers, names or source values."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, repr=False)
class ReviewerPolicyReview:
    _summary: bytes = field(repr=False)
    _private: bytes = field(repr=False)

    def __repr__(self):
        return "ReviewerPolicyReview(private=True, import_available=False)"

    def summary(self):
        return json.loads(self._summary)

    def private_data(self):
        return json.loads(self._private)

    def matches(self, review, policy, *, members=None):
        """Recompute every pin, not an import capability or lock."""
        try:
            candidate = build_reviewer_policy_review(review, policy, members=members)
            return compare_digest(self._private, candidate._private) and compare_digest(
                self._summary, candidate._summary
            )
        except (ReviewerPolicyError, TypeError, ValueError):
            return False


def build_reviewer_policy_review(review: LegacyReview, policy, *, members=None):
    """Compare each declared complete old set with current household parents."""
    if type(review) is not LegacyReview or not review.matches_members(members):
        raise ReviewerPolicyError("review_changed")
    if (
        type(policy) is not dict
        or not _bounded_json(policy)
        or set(policy) != {"schema", "revision", "source_review_fingerprint", "reviewers"}
        or type(policy["schema"]) is not int
        or policy["schema"] != 1
        or not _integer(policy["revision"], 1)
        or type(policy["source_review_fingerprint"]) is not str
        or policy["source_review_fingerprint"] != review.summary()["fingerprint"]
        or type(policy["reviewers"]) is not dict
    ):
        raise ReviewerPolicyError("reviewer_policy_invalid")
    assistant, _, mapping = review.private_data()
    ledger = assistant["ledger"] if "ledger" in assistant else assistant
    rows = {
        key: row
        for key, row in ledger["tasks"].items()
        if row.get("kind") == "task" and row.get("requires_report") is True
    }
    if set(policy["reviewers"]) != set(rows):
        raise ReviewerPolicyError("reviewer_policy_coverage_required")
    modern = {
        key
        for key, member in members.items()
        if member["active"] and member["role"] in {"parent", "owner"}
    }

    def bindings(keys):
        return [
            {"member_id": key, "member_revision": members[key]["revision"]} for key in sorted(keys)
        ]

    comparisons = []
    for key, row in sorted(rows.items()):
        declared = policy["reviewers"][key]
        if (
            type(declared) is not list
            or not 1 <= len(declared) <= 512
            or not all(_text(actor, 128) for actor in declared)
            or len(set(declared)) != len(declared)
            or row.get("reviewer") not in declared
        ):
            raise ReviewerPolicyError("reviewer_policy_set_invalid")
        old = set()
        for actor in declared:
            binding = mapping.get(actor)
            if (
                type(binding) is not dict
                or binding.get("archive_only")
                or binding.get("member_id") not in members
            ):
                raise ReviewerPolicyError("reviewer_policy_mapping_required")
            old.add(binding["member_id"])
        added, removed = modern - old, old - modern
        comparisons.append(
            {
                "source_task": key,
                "declared_old_reviewers": sorted(declared),
                "mapped_old_reviewers": bindings(old),
                "target_reviewers": bindings(modern),
                "added": bindings(added),
                "removed": bindings(removed),
                "decision_required": bool(added or removed),
            }
        )
    private = _encode(
        {
            "source_review_fingerprint": review.summary()["fingerprint"],
            "policy": policy,
            "target_policy": "household_parents",
            "comparisons": comparisons,
        }
    )
    return ReviewerPolicyReview(
        _encode(
            {
                "mode": "reviewer_set_review",
                "fingerprint": hashlib.sha256(private).hexdigest(),
                "tasks_count": len(comparisons),
                "changed_tasks_count": sum(item["decision_required"] for item in comparisons),
                "additional_reviewer_bindings_count": sum(
                    len(item["added"]) for item in comparisons
                ),
                "removed_reviewer_bindings_count": sum(
                    len(item["removed"]) for item in comparisons
                ),
                "source_policy_verified": False,
                "coherence_verified": False,
                "import_available": False,
            }
        ),
        private,
    )
