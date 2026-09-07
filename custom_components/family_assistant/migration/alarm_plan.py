"""Pure disabled-alarm conversion proposals; no live import, transport or HA I/O."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .preflight import _text
from .review import LegacyReview

PERIOD_DAYS = {"weekday": (0, 1, 2, 3, 4), "weekend": (5, 6)}


class AlarmPlanError(ValueError):
    """Fixed code only; never interpolate source fields or underlying errors."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, repr=False)
class AlarmPlan:
    """A private immutable draft, not a capability to apply domain commands."""

    _summary: bytes = field(repr=False)
    _private_payload: bytes = field(repr=False)

    def __repr__(self):
        return "AlarmPlan(private=True, import_available=False)"

    def summary(self):
        return json.loads(self._summary)

    def private_data(self):
        """Fresh local-only copies, never a family view or diagnostics response."""
        return json.loads(self._private_payload)


def build_alarm_plan(review: LegacyReview, timezone: str, *, members=None) -> AlarmPlan:
    if type(review) is not LegacyReview:
        raise AlarmPlanError("invalid_review")
    if not _text(timezone, 80):
        raise AlarmPlanError("invalid_timezone")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise AlarmPlanError("invalid_timezone") from None
    # Re-run preflight and all mapping/current-member checks. A manually forged
    # dataclass, changed binding, inactive child or stale revision is not a review.
    if not review.matches_members(members):
        raise AlarmPlanError("review_changed")
    assistant, _, mapping = review.private_data()
    alarms = assistant.get("alarms", {}) if "ledger" in assistant else {}
    proposals = []
    for old_member, periods in sorted(alarms.get("schedules", {}).items()):
        binding = mapping[old_member]
        for period, days in PERIOD_DAYS.items():
            if period not in periods:
                continue
            proposals.append(
                {
                    "source_member": old_member,
                    "period": period,
                    "target_member_revision": binding["member_revision"],
                    "payload": {
                        "member": binding["member_id"],
                        "time": periods[period]["time"],
                        "days": list(days),
                        "timezone": timezone,
                        "enabled": False,
                        "profile": "gentle",
                        "penalty": 0,
                    },
                }
            )
    # Preserve the exact decoded alarm object, including every unknown field.
    # Raw Store bytes remain in LegacyReview; no challenge is copied into a payload.
    private = _encode({"proposals": proposals, "archive": alarms})
    stamp = {
        "version": 1,
        "review": review.summary()["fingerprint"],
        "timezone": timezone,
        "payload": hashlib.sha256(private).hexdigest(),
    }
    summary = {
        "mode": "alarm_plan_proposal",
        "fingerprint": hashlib.sha256(_encode(stamp)).hexdigest(),
        "review_fingerprint": stamp["review"],
        "schedule_proposals_count": len(proposals),
        "archived_schedules_count": len(proposals),
        "archived_runs_count": len(alarms.get("runs", {})),
        "previously_enabled_count": review.summary()["counts"]["enabled_alarm_schedules"],
        "coherence_verified": False,
        "import_available": False,
    }
    return AlarmPlan(_encode(summary), private)
