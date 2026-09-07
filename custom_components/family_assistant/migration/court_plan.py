"""Reconcile the legacy open-week score without resurrecting earlier penalties."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field

from .preflight import _text
from .review import LegacyReview


class CourtPlanError(ValueError):
    """Fixed code only; original reasons, names and transport fields stay private."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, repr=False)
class CourtPlan:
    """A private proposal; not a live award, a command receipt or import authority."""

    _summary: bytes = field(repr=False)
    _private_payload: bytes = field(repr=False)

    def __repr__(self):
        return "CourtPlan(private=True, import_available=False)"

    def summary(self):
        return json.loads(self._summary)

    def private_data(self):
        return json.loads(self._private_payload)


def build_court_plan(review: LegacyReview, *, members=None) -> CourtPlan:
    if type(review) is not LegacyReview:
        raise CourtPlanError("invalid_review")
    if not review.matches_members(members):
        raise CourtPlanError("review_changed")
    _, court, mapping = review.private_data()
    proposals, blocked = [], []
    issues = Counter()
    current_count = cancelled_count = previous_count = 0
    for row in court["history"]:
        # Preflight balances ignore non-current weeks, so an absent/corrupt week
        # must not be silently accepted here as known historical data.
        if not _text(row.get("week_id"), 128):
            code = "court_period_unknown"
        elif row["week_id"] != court["week_id"]:
            previous_count += 1
            continue
        else:
            current_count += 1
            if row["cancelled"]:
                cancelled_count += 1
                continue
            if not _text(row.get("reason"), 500):
                code = "court_reason_unsupported"
            else:
                binding = mapping[row["child"]]
                proposals.append(
                    {
                        "source_event": row["event_id"],
                        "target_binding": binding,
                        "record": {
                            "member": binding["member_id"],
                            "points": row["delta"],
                            "reason": row["reason"],
                            "created_at": row["timestamp"],
                            "status": "active",
                            "source": "legacy",
                            # A legacy Telegram parent ID/name is not a current
                            # authenticated actor. Attribution remains in the archive.
                            "actor": None,
                        },
                    }
                )
                continue
        issues[code] += 1
        blocked.append({"source_event": row["event_id"], "code": code})
    balances = [
        {
            "source_member": member,
            "target_binding": mapping[member],
            "pluses": values["pluses"],
            "minuses": values["minuses"],
            "balance": values["pluses"] - values["minuses"],
        }
        for member, values in sorted(court["children"].items())
    ]
    # Keep the whole decoded Court Store: cancellations, earlier weeks, reasons,
    # report messages, unknown fields and old transport receipts are archive only.
    private = _encode(
        {
            "proposals": proposals,
            "blocked": blocked,
            "balances": balances,
            "source_week": court["week_id"],
            "archive": court,
        }
    )
    stamp = {
        "version": 1,
        "review": review.summary()["fingerprint"],
        "payload": hashlib.sha256(private).hexdigest(),
    }
    summary = {
        "mode": "court_plan_proposal",
        "fingerprint": hashlib.sha256(_encode(stamp)).hexdigest(),
        "review_fingerprint": stamp["review"],
        "source_events_count": len(court["history"]),
        "current_events_count": current_count,
        "cancelled_current_count": cancelled_count,
        "previous_events_count": previous_count,
        "record_proposals_count": len(proposals),
        "blocked_events_count": len(blocked),
        "source_members_count": len(balances),
        "archived_weeks_count": len(court["archived_weeks"]),
        "issues": [{"code": code, "count": count} for code, count in sorted(issues.items())],
        "coherence_verified": False,
        "import_available": False,
    }
    return CourtPlan(_encode(summary), private)
