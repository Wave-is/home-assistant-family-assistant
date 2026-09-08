"""Private, nonurgent outbox deferral; presence observations are never retained.

Only an explicitly reviewed independent delivery policy can invoke an observer.
Ordinary replies, group messages, alarms and incident closures never enter this lane.
"""

from __future__ import annotations

from datetime import timedelta

from . import presence_delivery
from .context import Context
from .validation import DomainError, revision, timestamp

GATED_KEYS = frozenset(
    {
        "family_digest",
        "task_assigned",
        "task_reminder",
        "task_personal_due",
        "pantry_expiry",
        "school_preparation_reminder",
    }
)
POLL_SECONDS = 60
RESUME_SECONDS = 120


def recipient(state: dict, event: dict, target: dict) -> dict | None:
    """Never apply one person's presence to a shared or ambiguous destination."""
    if (
        event.get("key") not in GATED_KEYS
        or event.get("recipient") == "family"
        or target.get("channel") != "telegram"
        or type(target.get("id")) is not int
        or target["id"] <= 0
        or target["id"] == state.get("telegram", {}).get("group_id")
    ):
        return None
    matches = [
        member
        for member in state.get("members", {}).values()
        if isinstance(member, dict)
        and member.get("active") is True
        and member.get("role") in {"owner", "parent", "adult", "child"}
        and type(member.get("telegram_id")) is int
        and member["telegram_id"] == target["id"]
    ]
    if len(matches) != 1:
        return None
    member = matches[0]
    try:
        revision(member.get("revision"))
    except DomainError:
        return None
    return member


def _identity(member: dict, target: dict) -> dict:
    return {
        "member": member["id"],
        "member_revision": member["revision"],
        "telegram_id": target["id"],
        "bot_id": target.get("bot_id"),
    }


def _same_recipient(stamp, member, target) -> bool:
    try:
        return (
            member is not None
            and isinstance(stamp, dict)
            and set(stamp) == {"member", "member_revision", "telegram_id", "bot_id"}
            and revision(stamp["member_revision"]) == member["revision"]
            and type(stamp["telegram_id"]) is int
            and stamp == _identity(member, target)
        )
    except DomainError:
        return False


def _supersede(delivery: dict, code: str) -> str:
    delivery["state"] = "superseded"
    delivery["error"] = code
    delivery.pop("lease_until", None)
    return "superseded"


def evaluate(ctx: Context, event: dict, delivery: dict, observer=None, *, dispatch=False) -> str:
    """Return allow/defer/superseded inside the Engine transaction.

    An observer is a short-lived synchronous adapter. It must recheck HA authority,
    the exact policy/source binding, current options and fresh reported state, and
    return the literal True only for reported home. None/error/unknown means defer.
    """
    target = delivery.get("target", {})
    member = recipient(ctx.state, event, target)
    stamp = delivery.get("presence_recipient")
    if stamp is not None:
        if not _same_recipient(stamp, member, target):
            return _supersede(delivery, "delivery_revoked")
    if member is None:
        return "allow"
    policy = presence_delivery.effective_policy(ctx.state, member["id"])
    now = timestamp(ctx.now, "now")
    started = delivery.get("presence_started_at")
    if started is not None:
        try:
            started = timestamp(started, "presence_started_at")
            deadline = timestamp(delivery.get("presence_deadline"), "presence_deadline")
            if policy is not None:
                deadline = min(deadline, started + timedelta(minutes=policy["max_wait_minutes"]))
        except (DomainError, OverflowError):
            return _supersede(delivery, "presence_wait_invalid")
        if now < started or now >= deadline:
            return _supersede(delivery, "presence_wait_expired")
        delivery["presence_deadline"] = deadline.isoformat()
    if policy is None:
        # Withdrawal stops observation and restores ordinary delivery, but cannot
        # revive an expired hold or change the pinned recipient of a held item.
        for key in ("presence_next_at", "presence_deadline", "presence_started_at"):
            delivery.pop(key, None)
        return "allow"
    delivery["presence_recipient"] = _identity(member, target)
    if not dispatch and delivery.get("presence_next_at"):
        try:
            if now < timestamp(delivery["presence_next_at"], "presence_next_at"):
                return "defer"
        except DomainError:
            return _supersede(delivery, "presence_wait_invalid")
    try:
        home = observer(ctx.state, member, policy, now) is True if observer else False
    except (DomainError, AttributeError, KeyError, TypeError, ValueError, OSError):
        home = False
    if not home:
        if started is None:
            try:
                deadline = now + timedelta(minutes=policy["max_wait_minutes"])
            except OverflowError:
                return _supersede(delivery, "presence_wait_invalid")
            delivery["presence_started_at"] = now.isoformat()
            delivery["presence_deadline"] = deadline.isoformat()
        delivery["presence_next_at"] = (now + timedelta(seconds=POLL_SECONDS)).isoformat()
        return "defer"
    delivery.pop("presence_next_at", None)
    if started is not None:
        # Drain held notifications slowly. This is separate from the ordinary
        # transport rate limiter, so it cannot delay alarms or closure messages.
        bucket = ctx.state.setdefault("presence", {})
        rates = bucket.setdefault("delivery_rates", {})
        if not isinstance(rates, dict):
            return _supersede(delivery, "presence_wait_invalid")
        for key, value in list(rates.items()):
            try:
                if not isinstance(value, dict) or timestamp(value.get("until"), "until") <= now:
                    rates.pop(key, None)
            except DomainError:
                rates.pop(key, None)
        current = rates.get(member["id"])
        if current and current.get("event") != event["id"]:
            delivery["presence_next_at"] = current["until"]
            return "defer"
        if dispatch and current is None:
            rates[member["id"]] = {
                "event": event["id"],
                "until": (now + timedelta(seconds=RESUME_SECONDS)).isoformat(),
            }
    return "allow"
