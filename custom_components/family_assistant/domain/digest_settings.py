"""Strict, reviewable digest scheduling policy without unrelated setting writes."""

from __future__ import annotations

import hashlib
import json

from .household import timezone
from .recurrence import clock
from .validation import DomainError, fields, revision

DEFAULTS = {
    "digest_morning_enabled": False,
    "digest_morning_time": "07:00",
    "digest_evening_enabled": False,
    "digest_evening_time": "19:00",
    "digest_weekly_enabled": False,
    "digest_weekly_weekday": 6,
    "digest_weekly_time": "18:00",
}


def validate(values: dict) -> dict:
    """Validate supplied policy fields; omission preserves the current value."""
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise DomainError("invalid_field", "digest_policy")
    result = {}
    for key, value in values.items():
        if key.endswith("_enabled"):
            if type(value) is not bool:
                raise DomainError("invalid_field", key)
        elif key.endswith("_weekday"):
            if type(value) is not int or not 0 <= value <= 6:
                raise DomainError("invalid_field", key)
        else:
            try:
                value = clock(value)
            except (DomainError, TypeError, ValueError):
                raise DomainError("invalid_field", key) from None
        result[key] = value
    return result


def values(state: dict) -> dict:
    settings = state.get("settings", {})
    return validate({key: settings.get(key, default) for key, default in DEFAULTS.items()})


def fingerprint(state: dict) -> str:
    policy = {
        "revision": revision(state.get("settings", {}).get("digest_policy_revision", 1)),
        "enabled": "digests" in state.get("settings", {}).get("modules", []),
        "timezone": timezone(state.get("settings", {}).get("timezone", "UTC")),
        **values(state),
    }
    return hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def advance(state: dict, before: str) -> None:
    """Policy A -> B -> A cannot revive an old queued digest."""
    if fingerprint(state) == before:
        return
    current = revision(state["settings"].get("digest_policy_revision", 1))
    if current == 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    state["settings"]["digest_policy_revision"] = current + 1


def handle(ctx, payload: dict) -> dict:
    """Owner policy change pins actor and policy epochs, not all household state."""
    if ctx.actor.get("role") != "owner":
        raise DomainError("forbidden")
    required = {"actor_revision", "policy_fingerprint", *DEFAULTS}
    fields(payload, required, required)
    if revision(payload["actor_revision"]) != ctx.actor.get("revision"):
        raise DomainError("conflict")
    before = fingerprint(ctx.state)
    if payload["policy_fingerprint"] != before:
        raise DomainError("conflict")
    supplied = validate({key: payload[key] for key in DEFAULTS})
    if supplied == values(ctx.state):
        raise DomainError("invalid_transition")
    ctx.state["settings"].update(supplied)
    advance(ctx.state, before)
    return {"policy_fingerprint": fingerprint(ctx.state)}


def authorize_replay(ctx, payload: dict, result: dict) -> None:
    if ctx.actor.get("role") != "owner":
        raise DomainError("forbidden")
    if revision(payload.get("actor_revision")) != ctx.actor.get("revision"):
        raise DomainError("conflict")
    if result != {"policy_fingerprint": fingerprint(ctx.state)}:
        raise DomainError("conflict")
