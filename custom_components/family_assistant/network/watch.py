"""Explicit self-only parent discovery subscriptions; local evidence, no router writes."""

import re
from datetime import timedelta

from ..domain.validation import DomainError, fields, revision, timestamp
from .admission_inventory import classify, observation_token

ACTION = "admission_watch_set"
KEY = "network_unreviewed_devices"
INCIDENT_KEY = "network_watch_cleared"  # sent when all pending devices reviewed
MAX_SEEN = 10_000
MAX_PENDING = 1000
EVENT_LIFETIME = timedelta(hours=1)


def _records(state):
    records = state["network"].get("admission_watches", {})
    if not isinstance(records, dict) or len(records) > 100:
        raise DomainError("network_response")
    return records


def _parent(state, member_id):
    member = state["members"].get(member_id)
    if (
        not member
        or member.get("active") is not True
        or member.get("role") not in {"owner", "parent"}
    ):
        raise DomainError("forbidden")
    revision(member.get("revision"))
    return member


def _record(state, member_id):
    record = _records(state).get(member_id)
    if record is None:
        return None
    if not isinstance(record, dict):
        raise DomainError("network_response")
    fields(
        record,
        {
            "revision",
            "actor_revision",
            "telegram_id",
            "backend",
            "enabled",
            "min_interval_minutes",
            "baseline_at",
            "updated_at",
            "seen",
            "pending",
            "last_enqueued_at",
            "delivery_gate",
            "capacity_blocked",
            "source_revoked",
        },
        {
            "revision",
            "actor_revision",
            "telegram_id",
            "backend",
            "enabled",
            "min_interval_minutes",
            "baseline_at",
            "updated_at",
            "seen",
            "pending",
            "last_enqueued_at",
            "delivery_gate",
            "capacity_blocked",
            "source_revoked",
        },
    )
    revision(record["revision"])
    revision(record["actor_revision"])
    if record["enabled"] and (
        not isinstance(record["backend"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", record["backend"])
        or type(record["telegram_id"]) is not int
        or record["telegram_id"] <= 0
        or record["baseline_at"] is None
    ):
        raise DomainError("network_response")
    if any(
        type(record[key]) is not bool for key in ("enabled", "capacity_blocked", "source_revoked")
    ):
        raise DomainError("network_response")
    interval = record["min_interval_minutes"]
    if type(interval) is not int or not 5 <= interval <= 1440:
        raise DomainError("network_response")
    for field, maximum in (("seen", MAX_SEEN), ("pending", MAX_PENDING)):
        rows = record[field]
        if not isinstance(rows, list) or len(rows) > maximum:
            raise DomainError("network_response")
        from .inventory import mac

        if any(not isinstance(value, str) or mac(value) != value for value in rows):
            raise DomainError("network_response")
        if len(set(rows)) != len(rows):
            raise DomainError("network_response")
    if not set(record["pending"]) <= set(record["seen"]):
        raise DomainError("network_response")
    for field in ("baseline_at", "updated_at", "last_enqueued_at"):
        if record[field] is not None:
            timestamp(record[field], field)
    gate = record["delivery_gate"]
    if gate is not None:
        fields(gate, {"event_id", "until"}, {"event_id", "until"})
        if not isinstance(gate["event_id"], str) or not 1 <= len(gate["event_id"]) <= 300:
            raise DomainError("network_response")
        timestamp(gate["until"], "until")
    return record


def _private_chat_ready(state, member):
    chat = member.get("telegram_id")
    return bool(
        type(chat) is int
        and chat > 0
        and chat != state["telegram"].get("group_id")
        and sum(
            m.get("active") is True and m.get("telegram_id") == chat
            for m in state["members"].values()
        )
        == 1
    )


def _effective(state, member, record):
    return bool(
        record
        and record["enabled"]
        and not record["capacity_blocked"]
        and not record["source_revoked"]
        and "mikrotik" in state["settings"]["modules"]
        and record["actor_revision"] == member["revision"]
        and record["backend"] == state["network"].get("backend")
        and type(record["telegram_id"]) is int
        and record["telegram_id"] > 0
        and record["telegram_id"] == member.get("telegram_id")
        and _private_chat_ready(state, member)
    )


def public(state, member_id):
    member = _parent(state, member_id)
    record = _record(state, member_id)
    return {
        "actor_revision": member["revision"],
        "watch_revision": record["revision"] if record else None,
        "enabled": record["enabled"] if record else False,
        "effective": _effective(state, member, record),
        "min_interval_minutes": record["min_interval_minutes"] if record else 30,
        "baseline_at": record["baseline_at"] if record else None,
        "seen_count": len(record["seen"]) if record else 0,
        "pending_count": len(record["pending"]) if record else 0,
        "capacity_blocked": record["capacity_blocked"] if record else False,
        "private_chat_ready": _private_chat_ready(state, member),
    }


def handle(ctx, payload):
    if "mikrotik" not in ctx.state["settings"]["modules"]:
        raise DomainError("module_disabled")
    member = _parent(ctx.state, ctx.actor_id)
    fields(
        payload,
        {
            "actor_revision",
            "watch_revision",
            "enabled",
            "min_interval_minutes",
            "observation_token",
        },
        {"actor_revision", "watch_revision", "enabled", "min_interval_minutes"},
    )
    if revision(payload["actor_revision"]) != member["revision"]:
        raise DomainError("conflict")
    old = _record(ctx.state, ctx.actor_id)
    expected = payload["watch_revision"]
    if expected is not None:
        revision(expected)
    if expected != (old["revision"] if old else None):
        raise DomainError("conflict")
    if type(payload["enabled"]) is not bool:
        raise DomainError("invalid_field", "enabled")
    interval = payload["min_interval_minutes"]
    if type(interval) is not int or not 5 <= interval <= 1440:
        raise DomainError("invalid_field", "min_interval_minutes")
    if expected == 2**53 - 1:
        raise DomainError("capacity_reached")
    if payload["enabled"]:
        if payload.get("observation_token") != observation_token(ctx.state["network"], ctx.now):
            raise DomainError("network_conflict")
        chat = member.get("telegram_id")
        if not _private_chat_ready(ctx.state, member):
            raise DomainError("forbidden")
        seen = sorted(row["mac"] for row in classify(ctx.state["network"], ctx.now)["devices"])
        baseline = ctx.now.isoformat()
    else:
        if "observation_token" in payload:
            raise DomainError("invalid_field", "observation_token")
        chat = member.get("telegram_id")
        seen, baseline = [], None
    records = ctx.state["network"].setdefault("admission_watches", {})
    if ctx.actor_id not in records and len(records) >= 100:
        raise DomainError("capacity_reached")
    records[ctx.actor_id] = {
        "revision": (expected or 0) + 1,
        "actor_revision": member["revision"],
        "telegram_id": chat,
        "backend": ctx.state["network"].get("backend"),
        "enabled": payload["enabled"],
        "min_interval_minutes": interval,
        "baseline_at": baseline,
        "updated_at": ctx.now.isoformat(),
        "seen": seen,
        "pending": [],
        "last_enqueued_at": None,
        "delivery_gate": None,
        "capacity_blocked": False,
        "source_revoked": False,
    }
    return {"watch_revision": (expected or 0) + 1, "enabled": payload["enabled"]}


def authorize_replay(ctx, payload, result):
    if "mikrotik" not in ctx.state["settings"]["modules"]:
        raise DomainError("module_disabled")
    member = _parent(ctx.state, ctx.actor_id)
    record = _record(ctx.state, ctx.actor_id)
    if not isinstance(result, dict) or type(result.get("enabled")) is not bool:
        raise DomainError("conflict")
    revision(result.get("watch_revision"))
    if (
        not record
        or revision(payload.get("actor_revision")) != member["revision"]
        or record["actor_revision"] != member["revision"]
        or result != {"watch_revision": record["revision"], "enabled": record["enabled"]}
        or (record["enabled"] and not _effective(ctx.state, member, record))
    ):
        raise DomainError("conflict")


def tick(ctx):
    if "mikrotik" not in ctx.state["settings"]["modules"]:
        return
    try:
        member_ids = list(_records(ctx.state))
    except DomainError:
        return
    if not member_ids:
        return
    inventory = classify(ctx.state["network"], ctx.now)
    if inventory["status"] != "fresh":
        return
    observe_backend(ctx.state, inventory["backend"])
    observed = {row["mac"] for row in inventory["devices"]}
    unreviewed = {row["mac"] for row in inventory["devices"] if row["status"] == "unreviewed"}
    for member_id in member_ids:
        try:
            member, record = _parent(ctx.state, member_id), _record(ctx.state, member_id)
            if not _effective(ctx.state, member, record):
                continue
        except (DomainError, TypeError, ValueError):
            continue
        new = observed - set(record["seen"])
        pending = (set(record["pending"]) | new) & unreviewed
        if len(set(record["seen"]) | new) > MAX_SEEN or len(pending) > MAX_PENDING:
            record["capacity_blocked"] = True
            continue
        record["seen"] = sorted(set(record["seen"]) | new)
        record["pending"] = sorted(pending)

        # Incident lifecycle: track open state in incidents dict.
        # An incident opens when new unreviewed devices are detected, and stays open
        # while any tracked devices remain unreviewed. A closure notification
        # (network_watch_cleared) is sent when all tracked devices have been reviewed
        # if a discovery alert was previously announced.
        incident_id = f"network_watch:{member_id}"
        incident = ctx.state["incidents"].get(incident_id)
        if pending:
            if not incident or incident.get("state") != "open":
                ctx.state["incidents"][incident_id] = {
                    "id": incident_id,
                    "generation": (incident["generation"] + 1 if incident else 1),
                    "state": "open",
                    "opened_at": ctx.now.isoformat(),
                    # Discovery alert below announces; no separate event here.
                    "event_id": None,
                    "recipient": member_id,
                    "macs": sorted(pending),
                }
            else:
                incident["macs"] = sorted(set(incident.get("macs", [])) | set(pending))
        elif incident and incident.get("state") == "open":
            remaining = set(incident.get("macs", [])) & unreviewed
            if remaining:
                incident["macs"] = sorted(remaining)
            else:
                incident["state"] = "closed"
                incident["closed_at"] = ctx.now.isoformat()
                incident["macs"] = []
                if record.get("last_enqueued_at"):
                    ctx.notify(
                        member_id,
                        INCIDENT_KEY,
                        {
                            "actor_revision": member["revision"],
                            "watch_revision": record["revision"],
                            "backend": record["backend"],
                            "telegram_id": record["telegram_id"],
                        },
                    )
                    record["last_enqueued_at"] = None

        from ..notifications import quiet_until

        if quiet_until(ctx.now, ctx.state["settings"].get("notifications", {})):
            continue  # Keep markers, not expiring outbox intents, through quiet hours.
        last = record["last_enqueued_at"]
        if not pending or (
            last
            and ctx.now
            < timestamp(last, "last_enqueued_at")
            + timedelta(minutes=record["min_interval_minutes"])
        ):
            continue
        ctx.notify(
            member_id,
            KEY,
            {
                "actor_revision": member["revision"],
                "watch_revision": record["revision"],
                "backend": record["backend"],
                "telegram_id": record["telegram_id"],
                "macs": sorted(pending),
                "expires_at": (ctx.now + EVENT_LIFETIME).isoformat(),
            },
        )
        record["pending"] = []
        record["last_enqueued_at"] = ctx.now.isoformat()


def current(state, event, now=None):
    try:
        if event.get("key") != KEY:
            return False
        member = _parent(state, event.get("recipient"))
        record = _record(state, member["id"])
        data = event["data"]
        fields(
            data,
            {"actor_revision", "watch_revision", "backend", "telegram_id", "macs", "expires_at"},
            {"actor_revision", "watch_revision", "backend", "telegram_id", "macs", "expires_at"},
        )
        rows = data["macs"]
        from .inventory import mac

        if type(data["telegram_id"]) is not int:
            return False
        if (
            not isinstance(rows, list)
            or not 1 <= len(rows) <= MAX_PENDING
            or len(set(rows)) != len(rows)
        ):
            return False
        if any(not isinstance(value, str) or mac(value) != value for value in rows):
            return False
        authorized = bool(
            _effective(state, member, record)
            and revision(data["actor_revision"]) == member["revision"]
            and revision(data["watch_revision"]) == record["revision"]
            and data["backend"] == record["backend"]
            and data["telegram_id"] == record["telegram_id"]
            and set(rows) <= set(record["seen"])
        )
        if not authorized or now is None:
            return authorized
        inventory = classify(state["network"], now)
        return bool(
            timestamp(event["created_at"], "created_at")
            <= timestamp(now, "now")
            < timestamp(data["expires_at"], "expires_at")
            <= timestamp(event["created_at"], "created_at") + EVENT_LIFETIME
            and inventory["status"] == "fresh"
            and any(
                row["mac"] in rows and row["status"] == "unreviewed" for row in inventory["devices"]
            )
        )
    except (DomainError, KeyError, TypeError, ValueError, AttributeError):
        return False


def dispatch_ready(state, event, now):
    """A quiet-hours backlog must not release several discovery batches at once."""
    if not current(state, event, now):
        return False
    record = _record(state, event["recipient"])
    gate = record["delivery_gate"]
    return not gate or gate["event_id"] == event["id"] or now >= timestamp(gate["until"], "until")


def reserve_dispatch(ctx, event):
    record = _record(ctx.state, event["recipient"])
    gate = record["delivery_gate"]
    if not gate or gate["event_id"] != event["id"]:
        record["delivery_gate"] = {
            "event_id": event["id"],
            "until": (ctx.now + timedelta(minutes=record["min_interval_minutes"])).isoformat(),
        }


def release_undispatched(ctx, event):
    """Only use after a confirmed pre-transport abort, never after uncertain I/O."""
    try:
        record = _record(ctx.state, event["recipient"])
        if (
            record
            and record["revision"] == event["data"].get("watch_revision")
            and record["delivery_gate"]
            and record["delivery_gate"]["event_id"] == event["id"]
        ):
            record["delivery_gate"] = None
    except (DomainError, KeyError, TypeError, ValueError):
        return


def observe_backend(state, backend):
    """Remember a witnessed source replacement; switching back cannot revive consent."""
    try:
        keys = list(_records(state))
    except DomainError:
        return
    for member_id in keys:
        try:
            record = _record(state, member_id)
            if record and record["enabled"] and record["backend"] != backend:
                record["source_revoked"] = True
        except (DomainError, TypeError, ValueError, KeyError):
            continue
