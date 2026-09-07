"""Short-lived private Telegram review intents for family poll commands."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, timedelta

from ..const import PRIVILEGED
from . import polls
from .context import Context
from .validation import DomainError, enum, text, timestamp
from .validation import revision as strict_revision

TTL = timedelta(minutes=5)
MAX_REVIEWS = 200
MAX_PER_ACTOR = 10
KINDS = frozenset({"vote", "close", "archive"})
STATUSES = frozenset({"pending", "claimed", "completed", "cancelled"})


def _version(value, field: str) -> int:
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", field) from None


def _module(state: dict) -> None:
    modules = state.get("settings", {}).get("modules", [])
    if not isinstance(modules, list) or "polls" not in modules:
        raise DomainError("module_disabled")


def _actor(state: dict, actor_id) -> dict:
    actor_id = text(actor_id, "actor", 80)
    actor = state.get("members", {}).get(actor_id)
    if (
        not isinstance(actor, dict)
        or actor.get("id") != actor_id
        or actor.get("active") is not True
        or actor.get("role") == "guest"
    ):
        raise DomainError("forbidden")
    _version(actor.get("revision"), "actor_revision")
    return actor


def _bucket(state: dict) -> dict:
    bucket = state.get("poll_reviews", {})
    if not isinstance(bucket, dict):
        raise DomainError("invalid_field", "poll_reviews")
    return bucket


def _mutable_bucket(ctx: Context) -> dict:
    bucket = ctx.state.get("poll_reviews")
    if bucket is None:
        bucket = {}
        ctx.state["poll_reviews"] = bucket
    if not isinstance(bucket, dict):
        raise DomainError("invalid_field", "poll_reviews")
    return bucket


def _record(state: dict, actor: dict, review_id) -> dict:
    review_id = text(review_id, "review_id", 80)
    record = _bucket(state).get(review_id)
    if (
        not isinstance(record, dict)
        or record.get("id") != review_id
        or record.get("actor") != actor.get("id")
        or record.get("actor_revision") != actor.get("revision")
    ):
        raise DomainError("forbidden")
    _version(record.get("revision"), "review_revision")
    enum(record.get("kind"), KINDS, "kind")
    enum(record.get("status"), STATUSES, "status")
    timestamp(record.get("created_at"), "created_at")
    timestamp(record.get("expires_at"), "expires_at")
    return record


def _expired(record: dict, now) -> bool:
    return timestamp(now, "now").astimezone(UTC) >= timestamp(
        record.get("expires_at"), "expires_at"
    ).astimezone(UTC)


def _projection(state: dict, actor: dict, now) -> dict:
    _module(state)
    return polls.view(state, actor, now)


def _find(rows: list, poll_id: str) -> dict | None:
    return next((row for row in rows if row.get("id") == poll_id), None)


def _source(state: dict, actor: dict, kind: str, poll_id, option_id, now) -> dict:
    poll_id = text(poll_id, "poll_id", 80)
    projection = _projection(state, actor, now)
    if kind == "vote":
        option_id = text(option_id, "option_id", 16)
        row = _find(projection["open"], poll_id)
        if not row or row.get("can_vote") is not True:
            raise DomainError("forbidden")
        if option_id not in {
            option.get("id") for option in row.get("options", []) if isinstance(option, dict)
        }:
            raise DomainError("invalid_field", "option_id")
        ballot = row.get("own_ballot")
        ballot_revision = (
            None if ballot is None else _version(ballot.get("revision"), "ballot_revision")
        )
        return {
            "poll_id": poll_id,
            "definition_revision": _version(row.get("definition_revision"), "definition_revision"),
            "ballot_revision": ballot_revision,
            "option_id": option_id,
        }
    if option_id is not None:
        raise DomainError("invalid_field", "option_id")
    if actor.get("role") not in PRIVILEGED:
        raise DomainError("forbidden")
    bucket = "open" if kind == "close" else "closed"
    capability = "can_close" if kind == "close" else "can_archive"
    row = _find(projection[bucket], poll_id)
    if not row or row.get(capability) is not True:
        raise DomainError("forbidden")
    return {"poll_id": poll_id, "poll_revision": _version(row.get("revision"), "revision")}


def _fingerprint(actor: dict, kind: str, source: dict) -> str:
    value = [actor["id"], actor["revision"], kind, source]
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _new_id(bucket: dict) -> str:
    for _attempt in range(10):
        review_id = "PR" + secrets.token_urlsafe(12)
        if review_id not in bucket:
            return review_id
    raise DomainError("conflict")


def prune(ctx: Context) -> int:
    """Remove only expired review intents; ballots and poll definitions are untouched."""
    bucket = _bucket(ctx.state)
    expired = [review_id for review_id, record in bucket.items() if _expired(record, ctx.now)]
    if not expired:
        return 0
    mutable = _mutable_bucket(ctx)
    for review_id in expired:
        mutable.pop(review_id, None)
    return len(expired)


def begin(
    ctx: Context,
    actor_id: str,
    kind: str,
    poll_id: str,
    option_id: str | None,
    source_operation_id: str,
) -> dict:
    """Freeze one currently authorized choice behind an opaque short-lived ID."""
    _module(ctx.state)
    actor = _actor(ctx.state, actor_id)
    kind = enum(kind, KINDS, "kind")
    source_operation_id = text(source_operation_id, "operation_id", 180)
    bucket = _bucket(ctx.state)
    for record in bucket.values():
        if not isinstance(record, dict) or record.get("source_operation_id") != source_operation_id:
            continue
        if record.get("actor") != actor["id"]:
            raise DomainError("idempotency_conflict")
        record = _record(ctx.state, actor, record.get("id"))
        if _expired(record, ctx.now):
            raise DomainError("invalid_transition")
        source = record.get("source")
        if (
            record.get("kind") != kind
            or not isinstance(source, dict)
            or source.get("poll_id") != poll_id
            or source.get("option_id") != option_id
            or record.get("fingerprint") != _fingerprint(actor, kind, source)
        ):
            raise DomainError("idempotency_conflict")
        return {"review_id": record["id"]}

    prune(ctx)
    bucket = _bucket(ctx.state)
    if len(bucket) >= MAX_REVIEWS:
        raise DomainError("command_too_large")
    if sum(record.get("actor") == actor["id"] for record in bucket.values()) >= MAX_PER_ACTOR:
        raise DomainError("invalid_transition")
    source = _source(ctx.state, actor, kind, poll_id, option_id, ctx.now)
    review_id = _new_id(bucket)
    created = timestamp(ctx.now, "now").astimezone(UTC)
    record = {
        "id": review_id,
        "revision": 1,
        "status": "pending",
        "kind": kind,
        "actor": actor["id"],
        "actor_revision": actor["revision"],
        "source": source,
        "source_operation_id": source_operation_id,
        "fingerprint": _fingerprint(actor, kind, source),
        "created_at": created.isoformat(),
        "expires_at": (created + TTL).isoformat(),
    }
    _mutable_bucket(ctx)[review_id] = record
    return {"review_id": review_id}


def _resolved_payload(state: dict, actor: dict, record: dict, now) -> tuple[str, dict]:
    source = _source(
        state,
        actor,
        record["kind"],
        record["source"]["poll_id"],
        record["source"].get("option_id"),
        now,
    )
    if source != record.get("source"):
        raise DomainError("conflict")
    if record["kind"] == "vote":
        return "polls.vote", {
            "id": source["poll_id"],
            "definition_revision": source["definition_revision"],
            "voter_revision": actor["revision"],
            "option_id": source["option_id"],
            "ballot_revision": source["ballot_revision"],
        }
    return f"polls.{record['kind']}", {
        "id": source["poll_id"],
        "revision": source["poll_revision"],
        "actor_revision": actor["revision"],
    }


def get_current(state: dict, actor_id: str, review_id: str, now) -> dict:
    """Return only the IDs needed for authorized send-time review rendering."""
    _module(state)
    actor = _actor(state, actor_id)
    record = _record(state, actor, review_id)
    if record.get("status") != "pending" or _expired(record, now):
        raise DomainError("invalid_transition")
    _resolved_payload(state, actor, record, now)
    return {
        "review_id": record["id"],
        "kind": record["kind"],
        "poll_id": record["source"]["poll_id"],
        **({"option_id": record["source"]["option_id"]} if record["kind"] == "vote" else {}),
    }


def claim(ctx: Context, actor_id: str, review_id: str, operation_id: str) -> tuple[str, dict, str]:
    """Bind a review to one Telegram update and return its frozen Engine command."""
    _module(ctx.state)
    actor = _actor(ctx.state, actor_id)
    operation_id = text(operation_id, "operation_id", 180)
    record = _record(ctx.state, actor, review_id)
    if _expired(record, ctx.now):
        raise DomainError("invalid_transition")
    if record.get("status") in {"claimed", "completed"}:
        source = record["source"]
        try:
            action, payload = _resolved_payload(ctx.state, actor, record, ctx.now)
            return action, payload, record["confirm_operation_id"]
        except DomainError:
            pass
        projection = _projection(ctx.state, actor, ctx.now)
        if record["kind"] == "vote":
            row = _find(projection["open"] + projection["closed"], source["poll_id"])
            ballot = row.get("own_ballot") if row else None
            expected_revision = (source["ballot_revision"] or 0) + 1
            if not row or ballot != {
                "option_id": source["option_id"],
                "revision": expected_revision,
            }:
                raise DomainError("conflict")
            action, payload = (
                "polls.vote",
                {
                    "id": source["poll_id"],
                    "definition_revision": source["definition_revision"],
                    "voter_revision": actor["revision"],
                    "option_id": source["option_id"],
                    "ballot_revision": source["ballot_revision"],
                },
            )
        else:
            expected_status = "closed" if record["kind"] == "close" else "archived"
            row = _find(projection[expected_status], source["poll_id"])
            if not row or row.get("revision") != source["poll_revision"] + 1:
                raise DomainError("conflict")
            action, payload = (
                f"polls.{record['kind']}",
                {
                    "id": source["poll_id"],
                    "revision": source["poll_revision"],
                    "actor_revision": actor["revision"],
                },
            )
        return action, payload, record["confirm_operation_id"]
    if record.get("status") != "pending":
        raise DomainError("invalid_transition")
    action, payload = _resolved_payload(ctx.state, actor, record, ctx.now)
    record.update(
        status="claimed",
        revision=record["revision"] + 1,
        confirm_operation_id=operation_id,
        claimed_at=timestamp(ctx.now, "now").astimezone(UTC).isoformat(),
    )
    return action, payload, operation_id


def complete(ctx: Context, actor_id: str, review_id: str, operation_id: str) -> None:
    actor = _actor(ctx.state, actor_id)
    record = _record(ctx.state, actor, review_id)
    if record.get("confirm_operation_id") != operation_id:
        raise DomainError("forbidden")
    if record.get("status") == "completed":
        return
    if record.get("status") != "claimed":
        raise DomainError("invalid_transition")
    record.update(
        status="completed",
        revision=record["revision"] + 1,
        completed_at=timestamp(ctx.now, "now").astimezone(UTC).isoformat(),
    )


def cancel(ctx: Context, actor_id: str, review_id: str, operation_id: str) -> None:
    actor = _actor(ctx.state, actor_id)
    operation_id = text(operation_id, "operation_id", 180)
    record = _record(ctx.state, actor, review_id)
    if _expired(record, ctx.now):
        raise DomainError("invalid_transition")
    if record.get("status") == "cancelled":
        if record.get("cancel_operation_id") != operation_id:
            raise DomainError("invalid_transition")
        return
    if record.get("status") != "pending":
        raise DomainError("invalid_transition")
    record.update(
        status="cancelled",
        revision=record["revision"] + 1,
        cancel_operation_id=operation_id,
        cancelled_at=timestamp(ctx.now, "now").astimezone(UTC).isoformat(),
    )
