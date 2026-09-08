"""Private feedback capture and projection for rejected model proposals."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from .context import Context
from .validation import DomainError, enum, fields, text, timestamp
from .validation import revision as strict_revision

MAX_ACTIVE_RECORDS = 64
MAX_EXPECTED_LENGTH = 400
MAX_SOURCE_LENGTH = 4096
MAX_PREVIEW_LENGTH = 2200
MAX_ID_LENGTH = 80

ALLOWED_CATEGORIES = frozenset(
    {
        "wrong_action",
        "wrong_target",
        "wrong_time",
        "other",
    }
)

VALID_ACTOR_ROLES = frozenset(
    {
        "owner",
        "parent",
        "adult",
        "child",
    }
)

REQUIRED_RECORD_KEYS = frozenset(
    {
        "id",
        "actor",
        "actor_revision",
        "role",
        "proposal_id",
        "category",
        "expected",
        "source",
        "source_available",
        "preview",
        "created_at",
    }
)

ALLOWED_RECORD_KEYS = REQUIRED_RECORD_KEYS | {"revision", "updated_at"}


def _is_valid_record(record: Any) -> bool:
    """Validate that a stored record has the strict shape, types, and bounds."""
    if not isinstance(record, dict):
        return False
    try:
        keys = set(record.keys())
    except Exception:
        return False
    if not all(isinstance(k, str) for k in keys):
        return False
    if not REQUIRED_RECORD_KEYS.issubset(keys) or not keys.issubset(ALLOWED_RECORD_KEYS):
        return False

    rec_id = record["id"]
    if (
        not isinstance(rec_id, str)
        or not rec_id.strip()
        or len(rec_id) > MAX_ID_LENGTH
        or rec_id != rec_id.strip()
    ):
        return False

    actor = record["actor"]
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or len(actor) > MAX_ID_LENGTH
        or actor != actor.strip()
    ):
        return False

    try:
        strict_revision(record["actor_revision"])
    except DomainError:
        return False

    role = record.get("role")
    if not isinstance(role, str) or role not in VALID_ACTOR_ROLES:
        return False

    proposal_id = record["proposal_id"]
    if (
        not isinstance(proposal_id, str)
        or not proposal_id.strip()
        or len(proposal_id) > MAX_ID_LENGTH
        or proposal_id != proposal_id.strip()
    ):
        return False

    category = record.get("category")
    if not isinstance(category, str) or category not in ALLOWED_CATEGORIES:
        return False

    expected = record["expected"]
    if not isinstance(expected, str) or not expected.strip() or len(expected) > MAX_EXPECTED_LENGTH:
        return False

    if type(record["source_available"]) is not bool:
        return False

    src = record["source"]
    if not isinstance(src, str) or len(src) > MAX_SOURCE_LENGTH:
        return False
    if record["source_available"]:
        if not src.strip():
            return False
    else:
        if src != "":
            return False

    preview = record["preview"]
    if not isinstance(preview, str) or len(preview) > MAX_PREVIEW_LENGTH:
        return False

    created_at = record["created_at"]
    if not isinstance(created_at, str):
        return False
    try:
        dt = timestamp(created_at, "created_at")
        if not dt:
            return False
    except Exception:
        return False

    if "revision" in record:
        try:
            strict_revision(record["revision"])
        except DomainError:
            return False

    if "updated_at" in record:
        updated_at = record["updated_at"]
        if not isinstance(updated_at, str):
            return False
        try:
            dt = timestamp(updated_at, "updated_at")
            if not dt:
                return False
        except Exception:
            return False

    return True


def _check_store_health(memory: dict) -> dict:
    """Validate that the semantic_feedback store in memory is well-formed."""
    if "semantic_feedback" not in memory:
        store: dict[str, dict] = {}
        memory["semantic_feedback"] = store
        return store

    store = memory["semantic_feedback"]
    if not isinstance(store, dict):
        raise DomainError("invalid_field", "semantic_feedback")

    if len(store) > MAX_ACTIVE_RECORDS:
        raise DomainError("invalid_field", "semantic_feedback")

    seen_proposals: set[str] = set()
    for rec_id, rec in store.items():
        if (
            not isinstance(rec_id, str)
            or len(rec_id) > MAX_ID_LENGTH
            or not _is_valid_record(rec)
            or rec["id"] != rec_id
        ):
            raise DomainError("invalid_field", "semantic_feedback")
        prop_id = rec["proposal_id"]
        if prop_id in seen_proposals:
            raise DomainError("invalid_field", "semantic_feedback")
        seen_proposals.add(prop_id)

    return store


def capture(ctx: Context, proposal: dict, payload: dict) -> dict:
    """Capture private feedback for a rejected model proposal."""
    # Reject inactive or guest actor
    if (
        not isinstance(ctx.actor, dict)
        or ctx.actor.get("active") is not True
        or not isinstance(ctx.actor.get("role"), str)
        or ctx.actor.get("role") not in VALID_ACTOR_ROLES
        or not isinstance(ctx.actor.get("id"), str)
        or not ctx.actor_id.strip()
        or len(ctx.actor_id) > MAX_ID_LENGTH
        or ctx.actor_id != ctx.actor_id.strip()
    ):
        raise DomainError("forbidden")

    try:
        act_rev = strict_revision(ctx.actor.get("revision"))
    except DomainError:
        raise DomainError("conflict") from None

    if not isinstance(ctx.state, dict):
        raise DomainError("invalid_field", "semantic_feedback")

    # Validate proposal
    if not isinstance(proposal, dict):
        raise DomainError("invalid_field", "proposal")

    proposal_id = proposal.get("id")
    if (
        not isinstance(proposal_id, str)
        or not proposal_id.strip()
        or len(proposal_id) > MAX_ID_LENGTH
        or proposal_id != proposal_id.strip()
    ):
        raise DomainError("invalid_field", "proposal")

    if (
        proposal.get("actor") != ctx.actor_id
        or proposal.get("role") != ctx.actor.get("role")
        or proposal.get("role") not in VALID_ACTOR_ROLES
    ):
        raise DomainError("forbidden")

    try:
        prop_rev = strict_revision(proposal.get("actor_revision"))
        if prop_rev != act_rev:
            raise DomainError("conflict")
    except DomainError:
        raise DomainError("conflict") from None

    if proposal.get("status") != "pending":
        raise DomainError("proposal_expired")

    if "expires_at" not in proposal or not isinstance(proposal["expires_at"], str):
        raise DomainError("invalid_field", "expires_at")
    expires_dt = timestamp(proposal["expires_at"], "expires_at")
    if ctx.now >= expires_dt:
        raise DomainError("proposal_expired")

    source_hash = proposal.get("source_hash")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise DomainError("invalid_field", "source_hash")
    try:
        int(source_hash, 16)
    except ValueError:
        raise DomainError("invalid_field", "source_hash") from None

    preview = proposal.get("preview")
    if not isinstance(preview, str):
        raise DomainError("invalid_field", "preview")
    bounded_preview = preview[:MAX_PREVIEW_LENGTH]

    # Validate payload
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")

    fields(payload, {"category", "expected", "source"}, {"category", "expected"})
    category = enum(payload["category"], ALLOWED_CATEGORIES, "category")
    expected = text(payload["expected"], "expected", MAX_EXPECTED_LENGTH)

    if "source" in payload:
        source_val = payload["source"]
        if (
            not isinstance(source_val, str)
            or not source_val.strip()
            or len(source_val) > MAX_SOURCE_LENGTH
        ):
            raise DomainError("invalid_field", "source")
        hasher = hashlib.sha256(source_val.encode("utf-8")).hexdigest()
        if hasher.lower() != source_hash.lower():
            raise DomainError("invalid_field", "source")
        stored_source = source_val
        source_available = True
    else:
        stored_source = ""
        source_available = False

    # Validate state memory bucket and existing records
    if "memory" in ctx.state and not isinstance(ctx.state["memory"], dict):
        raise DomainError("invalid_field", "semantic_feedback")
    if "memory" not in ctx.state:
        ctx.state["memory"] = {}

    store = _check_store_health(ctx.state["memory"])

    # Check for existing feedback on this proposal
    existing = next(
        (r for r in store.values() if r["proposal_id"] == proposal_id),
        None,
    )
    if existing is not None:
        # Duplicate capture of same proposal must require same actor epoch
        # before returning any previous result
        if existing["actor"] != ctx.actor_id:
            raise DomainError("forbidden")
        if existing["actor_revision"] != act_rev or existing["role"] != ctx.actor["role"]:
            raise DomainError("conflict")

        if (
            existing["category"] == category
            and existing["expected"] == expected
            and existing["source_available"] == source_available
            and existing["source"] == stored_source
        ):
            return {
                "id": existing["id"],
                "status": "recorded",
                "actor_revision": existing["actor_revision"],
                "role": existing["role"],
            }
        raise DomainError("conflict")

    if len(store) >= MAX_ACTIVE_RECORDS:
        raise DomainError("capacity_reached")

    sequence = ctx.state.get("sequences")
    if not isinstance(sequence, dict):
        raise DomainError("invalid_field", "semantic_feedback")
    previous = sequence.get("F", 0)
    if type(previous) is not int or not 0 <= previous < 2**53 - 1:
        raise DomainError("invalid_field", "semantic_feedback")
    if f"F{previous + 1:06}" in store:
        raise DomainError("conflict")
    record_id = ctx.identifier("F")
    if (
        not isinstance(record_id, str)
        or not record_id.strip()
        or len(record_id) > MAX_ID_LENGTH
        or record_id in store
    ):
        raise DomainError("conflict")

    record = {
        "id": record_id,
        "actor": ctx.actor_id,
        "actor_revision": act_rev,
        "role": ctx.actor["role"],
        "proposal_id": proposal_id,
        "category": category,
        "expected": expected,
        "source": stored_source,
        "source_available": source_available,
        "preview": bounded_preview,
        "created_at": ctx.now.isoformat(),
    }
    ctx.touch(record)
    store[record_id] = record

    return {
        "id": record_id,
        "status": "recorded",
        "actor_revision": act_rev,
        "role": ctx.actor["role"],
    }


def project(state: dict, actor: dict) -> dict:
    """Project private feedback records matching the actor's exact identity epoch."""
    if not isinstance(actor, dict):
        return {"available": False, "records": []}

    actor_id = actor.get("id")
    actor_role = actor.get("role")
    actor_rev = actor.get("revision")
    actor_active = actor.get("active")

    if (
        not isinstance(actor_id, str)
        or not actor_id.strip()
        or len(actor_id) > MAX_ID_LENGTH
        or actor_id != actor_id.strip()
    ):
        return {"available": False, "records": []}

    if not isinstance(actor_role, str) or actor_role not in VALID_ACTOR_ROLES:
        return {"available": False, "records": []}

    if actor_active is not True:
        return {"available": False, "records": []}

    try:
        strict_actor_rev = strict_revision(actor_rev)
    except DomainError:
        return {"available": False, "records": []}

    if not isinstance(state, dict):
        return {"available": False, "records": []}

    if "memory" not in state:
        return {"available": True, "records": []}

    memory = state["memory"]
    if not isinstance(memory, dict):
        return {"available": False, "records": []}

    if "semantic_feedback" not in memory:
        return {"available": True, "records": []}

    store = memory["semantic_feedback"]
    if not isinstance(store, dict):
        return {"available": False, "records": []}

    if len(store) > MAX_ACTIVE_RECORDS:
        return {"available": False, "records": []}

    seen_proposals: set[str] = set()
    records = []
    for rec_id, rec in store.items():
        if (
            not isinstance(rec_id, str)
            or len(rec_id) > MAX_ID_LENGTH
            or not _is_valid_record(rec)
            or rec["id"] != rec_id
        ):
            return {"available": False, "records": []}
        prop_id = rec["proposal_id"]
        if prop_id in seen_proposals:
            return {"available": False, "records": []}
        seen_proposals.add(prop_id)

        if (
            rec["actor"] == actor_id
            and rec["actor_revision"] == strict_actor_rev
            and rec["role"] == actor_role
        ):
            records.append(deepcopy(rec))

    return {"available": True, "records": records}


def purge(ctx: Context, payload: dict) -> dict:
    """Purge a single private feedback record belonging to the current actor epoch."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")

    fields(payload, {"id", "confirmed"}, {"id", "confirmed"})
    record_id = text(payload["id"], "id", MAX_ID_LENGTH)
    if payload["confirmed"] is not True:
        raise DomainError("invalid_field", "confirmed")

    # Reject inactive or guest actor
    if (
        not isinstance(ctx.actor, dict)
        or ctx.actor.get("active") is not True
        or not isinstance(ctx.actor.get("role"), str)
        or ctx.actor.get("role") not in VALID_ACTOR_ROLES
        or not isinstance(ctx.actor.get("id"), str)
        or not ctx.actor_id.strip()
        or len(ctx.actor_id) > MAX_ID_LENGTH
        or ctx.actor_id != ctx.actor_id.strip()
    ):
        raise DomainError("forbidden")

    try:
        act_rev = strict_revision(ctx.actor.get("revision"))
    except DomainError:
        raise DomainError("conflict") from None

    if not isinstance(ctx.state, dict):
        raise DomainError("invalid_field", "semantic_feedback")
    if "memory" not in ctx.state:
        raise DomainError("not_found")
    if not isinstance(ctx.state["memory"], dict):
        raise DomainError("invalid_field", "semantic_feedback")
    if "semantic_feedback" not in ctx.state["memory"]:
        raise DomainError("not_found")
    if not isinstance(ctx.state["memory"]["semantic_feedback"], dict):
        raise DomainError("invalid_field", "semantic_feedback")

    store = ctx.state["memory"]["semantic_feedback"]
    if len(store) > MAX_ACTIVE_RECORDS:
        raise DomainError("invalid_field", "semantic_feedback")

    seen_proposals: set[str] = set()
    for k, rec in store.items():
        if (
            not isinstance(k, str)
            or len(k) > MAX_ID_LENGTH
            or not _is_valid_record(rec)
            or rec["id"] != k
        ):
            raise DomainError("invalid_field", "semantic_feedback")
        prop_id = rec["proposal_id"]
        if prop_id in seen_proposals:
            raise DomainError("invalid_field", "semantic_feedback")
        seen_proposals.add(prop_id)

    record = store.get(record_id)
    if record is None:
        raise DomainError("not_found")

    if record["actor"] != ctx.actor_id or record["role"] != ctx.actor.get("role"):
        raise DomainError("forbidden")

    try:
        rec_rev = strict_revision(record["actor_revision"])
        if rec_rev != act_rev:
            raise DomainError("conflict")
    except DomainError:
        raise DomainError("conflict") from None

    del store[record_id]

    return {
        "id": record_id,
        "status": "purged",
        "actor_revision": act_rev,
        "role": ctx.actor["role"],
    }
