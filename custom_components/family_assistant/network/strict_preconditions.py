"""Strict-mode precondition gate for network enforcement.

Strict blocking (quarantine / allowlist enforcement) requires explicit
topology evidence that no bypass path exists, IPv4 and IPv6 restrictions
work in this topology, FastTrack and hardware offload are accounted for,
management hosts are excluded, and local recovery after restart works.

None of these checks modify the router.  When any precondition is missing,
the gate returns a non-empty list of reason codes so the card can display
an actionable explanation instead of silently refusing to activate.

Topology evidence is supplied by ``tests/routeros/`` probes and stored as
``network.strict_evidence`` by the owner.  Evidence records are bound to a
specific backend identity and expire after 30 days so that topology changes
require re-verification.
"""

from __future__ import annotations

from datetime import timedelta

from ..domain.validation import DomainError, fields, revision, timestamp

# Public reason codes; translated in strings.json under network.strict.*
REASON_MODULE_DISABLED = "module_disabled"
REASON_NO_EVIDENCE = "no_topology_evidence"
REASON_EVIDENCE_EXPIRED = "evidence_expired"
REASON_EVIDENCE_WRONG_BACKEND = "evidence_wrong_backend"
REASON_IPV4_MISSING = "ipv4_restriction_unverified"
REASON_IPV6_MISSING = "ipv6_restriction_unverified"
REASON_FASTTRACK_UNACCOUNTED = "fasttrack_bypass_unaccounted"
REASON_MANAGEMENT_NOT_EXCLUDED = "management_hosts_not_excluded"
REASON_RESTART_UNVERIFIED = "restart_recovery_unverified"

EVIDENCE_MAX_AGE = timedelta(days=30)
EVIDENCE_FIELDS = frozenset(
    {
        "backend",
        "revision",
        "recorded_at",
        "ipv4_verified",
        "ipv6_verified",
        "fasttrack_accounted",
        "management_excluded",
        "restart_verified",
        "notes",
    }
)
EVIDENCE_REQUIRED = frozenset(
    {
        "backend",
        "revision",
        "recorded_at",
        "ipv4_verified",
        "ipv6_verified",
        "fasttrack_accounted",
        "management_excluded",
        "restart_verified",
    }
)


def _validate_evidence(record: object) -> dict:
    """Parse and validate a single strict-mode evidence record."""
    if not isinstance(record, dict):
        raise DomainError("network_response")
    fields(record, EVIDENCE_FIELDS, EVIDENCE_REQUIRED)
    if not isinstance(record["backend"], str) or len(record["backend"]) != 64:
        raise DomainError("network_response")
    revision(record["revision"])
    timestamp(record["recorded_at"], "recorded_at")
    for key in (
        "ipv4_verified",
        "ipv6_verified",
        "fasttrack_accounted",
        "management_excluded",
        "restart_verified",
    ):
        if type(record[key]) is not bool:
            raise DomainError("network_response")
    notes = record.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 500):
        raise DomainError("network_response")
    return record


def check(state: dict, now) -> list[str]:
    """Return a list of unmet precondition reason codes (empty = all met).

    ``state`` is the full Family Assistant engine state snapshot.
    ``now`` is a timezone-aware datetime.
    """
    if "mikrotik" not in state.get("settings", {}).get("modules", set()):
        return [REASON_MODULE_DISABLED]

    network = state.get("network", {})
    backend = network.get("backend")
    evidence_store = network.get("strict_evidence")

    if not evidence_store or not isinstance(evidence_store, dict):
        return [REASON_NO_EVIDENCE]

    # Pick the evidence record matching the current backend.
    raw = evidence_store.get(backend) if isinstance(backend, str) else None
    if raw is None:
        return [REASON_EVIDENCE_WRONG_BACKEND]

    try:
        record = _validate_evidence(raw)
    except (DomainError, KeyError, TypeError, ValueError):
        return [REASON_NO_EVIDENCE]

    try:
        now_dt = timestamp(now, "now")
        recorded_dt = timestamp(record["recorded_at"], "recorded_at")
    except (DomainError, TypeError, ValueError):
        return [REASON_NO_EVIDENCE]

    reasons: list[str] = []

    if now_dt - recorded_dt > EVIDENCE_MAX_AGE:
        reasons.append(REASON_EVIDENCE_EXPIRED)

    if not record["ipv4_verified"]:
        reasons.append(REASON_IPV4_MISSING)
    if not record["ipv6_verified"]:
        reasons.append(REASON_IPV6_MISSING)
    if not record["fasttrack_accounted"]:
        reasons.append(REASON_FASTTRACK_UNACCOUNTED)
    if not record["management_excluded"]:
        reasons.append(REASON_MANAGEMENT_NOT_EXCLUDED)
    if not record["restart_verified"]:
        reasons.append(REASON_RESTART_UNVERIFIED)

    return reasons


def record_evidence(ctx, payload: dict) -> dict:
    """Owner action: store topology evidence for the current backend.

    Payload fields:
      actor_revision       – current owner revision
      ipv4_verified        – bool: IPv4 restriction probe passed
      ipv6_verified        – bool: IPv6 restriction probe passed
      fasttrack_accounted  – bool: FastTrack/offload bypass measured
      management_excluded  – bool: HA and management hosts explicitly excluded
      restart_verified     – bool: local restart / exception recovery confirmed
      notes                – optional string (≤500 chars) for test evidence links

    Each call replaces any existing evidence for the current backend.
    Evidence is automatically invalid when the backend identity changes.
    """
    if "mikrotik" not in ctx.state["settings"]["modules"]:
        raise DomainError("module_disabled")
    actor = ctx.state["members"].get(ctx.actor_id)
    if not actor or actor.get("active") is not True or actor.get("role") != "owner":
        raise DomainError("forbidden")
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    if revision(payload.get("actor_revision")) != revision(actor.get("revision")):
        raise DomainError("conflict")

    allowed = {
        "actor_revision",
        "ipv4_verified",
        "ipv6_verified",
        "fasttrack_accounted",
        "management_excluded",
        "restart_verified",
        "notes",
    }
    required = allowed - {"notes"}
    fields(payload, allowed, required)

    for key in (
        "ipv4_verified",
        "ipv6_verified",
        "fasttrack_accounted",
        "management_excluded",
        "restart_verified",
    ):
        if type(payload[key]) is not bool:
            raise DomainError("invalid_field", key)

    notes = payload.get("notes")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 500):
        raise DomainError("invalid_field", "notes")

    network = ctx.state["network"]
    backend = network.get("backend")
    if not isinstance(backend, str) or len(backend) != 64:
        raise DomainError("network_response")

    new_record = {
        "backend": backend,
        "revision": (
            (network.get("strict_evidence", {}).get(backend, {}).get("revision") or 0) + 1
        ),
        "recorded_at": ctx.now.isoformat(),
        "ipv4_verified": payload["ipv4_verified"],
        "ipv6_verified": payload["ipv6_verified"],
        "fasttrack_accounted": payload["fasttrack_accounted"],
        "management_excluded": payload["management_excluded"],
        "restart_verified": payload["restart_verified"],
        "notes": notes,
    }
    _validate_evidence(new_record)  # internal consistency check

    evidence_store = network.setdefault("strict_evidence", {})
    # Keep at most 5 historical backend records to bound storage.
    if backend not in evidence_store and len(evidence_store) >= 5:
        # Remove the oldest by recorded_at
        oldest = min(
            evidence_store,
            key=lambda k: evidence_store[k].get("recorded_at", ""),
        )
        del evidence_store[oldest]
    evidence_store[backend] = new_record

    unmet = check(ctx.state, ctx.now)
    return {
        "revision": new_record["revision"],
        "unmet_preconditions": unmet,
        "strict_available": len(unmet) == 0,
    }


def public_status(state: dict, now) -> dict:
    """Return a card-safe strict-mode status (no secrets, no full evidence)."""
    if "mikrotik" not in state.get("settings", {}).get("modules", set()):
        return {"strict_available": False, "unmet_preconditions": [REASON_MODULE_DISABLED]}
    unmet = check(state, now)
    return {
        "strict_available": len(unmet) == 0,
        "unmet_preconditions": unmet,
    }
