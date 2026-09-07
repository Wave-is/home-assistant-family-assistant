"""One private, frozen review of every supported source bucket; never apply it."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .alarm_plan import AlarmPlanError, build_alarm_plan
from .archive import encode_private_review
from .court_plan import build_court_plan
from .review import LegacyReview
from .shopping_plan import build_shopping_plan
from .task_plan import build_task_plan


class ConversionError(ValueError):
    """Fixed error code, never source content or identity data."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, repr=False)
class ConversionReview:
    """Immutable local-only review and archive; checksums are not capabilities."""

    _summary: bytes = field(repr=False)
    _private_payload: bytes = field(repr=False)

    def __repr__(self):
        return "ConversionReview(private=True, import_available=False)"

    def summary(self):
        return json.loads(self._summary)

    def private_data(self):
        return json.loads(self._private_payload)

    def private_archive_bytes(self):
        """Only for owner-private local storage, never diagnostics or model input."""
        return _encode(json.loads(self._private_payload)["archive"])


def build_conversion_review(
    review: LegacyReview, timezone: str, *, members=None
) -> ConversionReview:
    if type(review) is not LegacyReview or not review.matches_members(members):
        raise ConversionError("review_changed")
    try:
        alarm_plan = build_alarm_plan(review, timezone, members=members)
    except AlarmPlanError:
        raise ConversionError("invalid_timezone") from None
    plans = {
        "alarms": alarm_plan,
        "tasks": build_task_plan(review, members=members),
        "shopping": build_shopping_plan(review, members=members),
        "court": build_court_plan(review, members=members),
    }
    # Keep raw sources exactly once, not multiple overlapping per-module archives.
    private = _encode(
        {
            "timezone": timezone,
            "archive": json.loads(encode_private_review(review, members=members)),
            "plans": {
                name: {key: value for key, value in plan.private_data().items() if key != "archive"}
                for name, plan in plans.items()
            },
        }
    )
    summary = {
        "mode": "conversion_review",
        "fingerprint": hashlib.sha256(private).hexdigest(),
        "review_fingerprint": review.summary()["fingerprint"],
        "source_counts": review.summary()["counts"],
        "modules": {name: plan.summary() for name, plan in plans.items()},
        "blocked_records_count": sum(
            len(plan.private_data().get("blocked", [])) for plan in plans.values()
        ),
        "coherence_verified": False,
        "import_available": False,
    }
    return ConversionReview(_encode(summary), private)
