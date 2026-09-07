"""Consent-bound, content-free intents for private family digests.

Rendered summaries are built by ``digest_content`` only from the recipient's
current authorized projection.  This module stores schedule/scope descriptors,
never summary text, counts, source identifiers, or excluded private domains.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import digest_settings, recurrence
from .context import Context
from .validation import DomainError, fields, timestamp
from .validation import revision as strict_revision

KEY = "family_digest"
ACTION = "access_set"
KINDS = ("morning", "evening", "weekly")
WINDOW = timedelta(minutes=5)
MAX_RECORDS = 10_000
DAILY_RETENTION = timedelta(days=35)
WEEKLY_RETENTION = timedelta(weeks=16)
FAILED_RETENTION = timedelta(days=90)
CURRENT_ROLES = frozenset({"owner", "parent", "adult", "child"})
UNSENT = frozenset({"pending", "awaiting_channel"})
TERMINAL = frozenset({"sent", "superseded", "resolved"})

PAYLOAD_FIELDS = frozenset(
    {"recipient_revision", "subscription_revision", "morning", "evening", "weekly"}
)
SUBSCRIPTION_FIELDS = frozenset(
    {
        "recipient",
        "recipient_revision",
        "morning",
        "evening",
        "weekly",
        "revision",
        "updated_at",
    }
)
EVENT_FIELDS = frozenset(
    {
        "schema",
        "kind",
        "period_key",
        "window_start",
        "window_end",
        "recipient_revision",
        "subscription_revision",
        "policy_fingerprint",
        "scheduled_at",
        "expires_at",
    }
)
MARKER_FIELDS = frozenset(
    {
        "event_id",
        "recipient_revision",
        "subscription_revision",
        "policy_fingerprint",
    }
)


def _module_enabled(state: dict) -> bool:
    settings = state.get("settings", {})
    modules = settings.get("modules", []) if isinstance(settings, dict) else []
    return isinstance(modules, list) and "digests" in modules


def policy(state: dict) -> dict:
    """Return strict current scheduling policy using additive public defaults."""
    settings = state.get("settings", {})
    if not isinstance(settings, dict):
        raise DomainError("invalid_field", "settings")
    values = digest_settings.values(state)
    zone_name = settings.get("timezone", "UTC")
    if not isinstance(zone_name, str):
        raise DomainError("invalid_field", "timezone")
    try:
        ZoneInfo(zone_name)
    except (ValueError, ZoneInfoNotFoundError):
        raise DomainError("invalid_field", "timezone") from None
    return {
        "timezone": zone_name,
        "morning": {
            "enabled": values["digest_morning_enabled"],
            "time": values["digest_morning_time"],
        },
        "evening": {
            "enabled": values["digest_evening_enabled"],
            "time": values["digest_evening_time"],
        },
        "weekly": {
            "enabled": values["digest_weekly_enabled"],
            "weekday": values["digest_weekly_weekday"],
            "time": values["digest_weekly_time"],
        },
    }


def _policy_fingerprint(state: dict) -> str:
    return digest_settings.fingerprint(state)


def _bucket(state: dict, name: str) -> dict:
    value = state.get(name, {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _mutable_bucket(ctx: Context, name: str) -> dict:
    value = ctx.state.get(name)
    if value is None:
        value = {}
        ctx.state[name] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _current_actor(state: dict, actor_id) -> dict:
    if not isinstance(actor_id, str):
        raise DomainError("forbidden")
    actor = state.get("members", {}).get(actor_id)
    if (
        not isinstance(actor, dict)
        or actor.get("id") != actor_id
        or actor.get("active") is not True
        or actor.get("role") not in CURRENT_ROLES
    ):
        raise DomainError("forbidden")
    strict_revision(actor.get("revision"))
    return actor


def _requested_revision(value) -> int | None:
    if value is None:
        return None
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", "subscription_revision") from None


def _subscription(state: dict, recipient: str) -> dict | None:
    record = _bucket(state, "digest_subscriptions").get(recipient)
    if record is None:
        return None
    if not isinstance(record, dict) or set(record) != SUBSCRIPTION_FIELDS:
        raise DomainError("invalid_field", "digest_subscriptions")
    if record.get("recipient") != recipient:
        raise DomainError("invalid_field", "digest_subscriptions")
    strict_revision(record.get("recipient_revision"))
    strict_revision(record.get("revision"))
    for kind in KINDS:
        if type(record.get(kind)) is not bool:
            raise DomainError("invalid_field", "digest_subscriptions")
    timestamp(record.get("updated_at"), "updated_at")
    return record


def _subscription_current(state: dict, actor: dict, record: dict | None, kind=None) -> bool:
    if record is None:
        return False
    try:
        current = _current_actor(state, actor.get("id"))
        valid = (
            record.get("recipient") == current["id"]
            and strict_revision(record.get("recipient_revision"))
            == strict_revision(current.get("revision"))
            and strict_revision(record.get("revision")) >= 1
        )
        if kind is not None:
            valid = valid and kind in KINDS and record.get(kind) is True
        return bool(valid)
    except (DomainError, AttributeError):
        return False


def _receipt(record: dict) -> dict:
    return {
        "revision": record["revision"],
        "status": "enabled" if any(record[kind] for kind in KINDS) else "disabled",
    }


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Set only the authenticated actor's own digest consent."""
    if action != ACTION:
        raise DomainError("unknown_action")
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    fields(payload, PAYLOAD_FIELDS, PAYLOAD_FIELDS)
    if not _module_enabled(ctx.state):
        raise DomainError("module_disabled")
    actor = _current_actor(ctx.state, ctx.actor_id)
    if strict_revision(payload["recipient_revision"]) != actor["revision"]:
        raise DomainError("conflict")
    for kind in KINDS:
        if type(payload[kind]) is not bool:
            raise DomainError("invalid_field", kind)
    requested = _requested_revision(payload["subscription_revision"])
    previous = _subscription(ctx.state, actor["id"])
    if previous is None:
        if requested is not None:
            raise DomainError("conflict")
        if not any(payload[kind] for kind in KINDS):
            raise DomainError("invalid_transition")
        revision = 1
    else:
        current_revision = strict_revision(previous["revision"])
        if requested is None or requested != current_revision:
            raise DomainError("conflict")
        if current_revision >= 2**53 - 1:
            raise DomainError("invalid_field", "subscription_revision")
        if previous["recipient_revision"] == actor["revision"] and all(
            previous[kind] is payload[kind] for kind in KINDS
        ):
            raise DomainError("invalid_transition")
        revision = current_revision + 1
    record = {
        "recipient": actor["id"],
        "recipient_revision": actor["revision"],
        **{kind: payload[kind] for kind in KINDS},
        "revision": revision,
        "updated_at": ctx.now.isoformat(),
    }
    _mutable_bucket(ctx, "digest_subscriptions")[actor["id"]] = record
    return _receipt(record)


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict) -> None:
    """Return a cached opaque receipt only for the exact current self-consent."""
    if action != ACTION or not isinstance(payload, dict):
        raise DomainError("forbidden")
    fields(payload, PAYLOAD_FIELDS, PAYLOAD_FIELDS)
    if not _module_enabled(ctx.state):
        raise DomainError("module_disabled")
    actor = _current_actor(ctx.state, ctx.actor_id)
    if strict_revision(payload["recipient_revision"]) != actor["revision"]:
        raise DomainError("conflict")
    for kind in KINDS:
        if type(payload[kind]) is not bool:
            raise DomainError("invalid_field", kind)
    requested = _requested_revision(payload["subscription_revision"])
    expected_revision = 1 if requested is None else requested + 1
    if expected_revision > 2**53 - 1:
        raise DomainError("invalid_field", "subscription_revision")
    record = _subscription(ctx.state, actor["id"])
    if (
        record is None
        or not _subscription_current(ctx.state, actor, record)
        or record["revision"] != expected_revision
        or any(record[kind] is not payload[kind] for kind in KINDS)
        or result != _receipt(record)
    ):
        raise DomainError("forbidden")


def _own_health(state: dict, recipient: str) -> str:
    try:
        outbox = _bucket(state, "outbox")
        markers = _bucket(state, "digest_markers")
    except DomainError:
        return "attention"
    troubled = any(
        isinstance(event, dict)
        and event.get("key") == KEY
        and event.get("recipient") == recipient
        and event.get("state") in {"failed", "uncertain", "awaiting_channel"}
        for event in outbox.values()
    )
    retained = sum(
        1 for event in outbox.values() if isinstance(event, dict) and event.get("key") == KEY
    )
    return (
        "attention" if troubled or len(markers) >= MAX_RECORDS or retained >= MAX_RECORDS else "ok"
    )


def view(state: dict, actor: dict) -> dict:
    """Project current policy and only the current actor's own controls."""
    empty = {"policy": None, "self": None}
    if not _module_enabled(state) or not isinstance(actor, dict):
        return empty
    try:
        current = _current_actor(state, actor.get("id"))
        current_policy = policy(state)
        record = _subscription(state, current["id"])
    except (DomainError, TypeError):
        return empty
    subscription_revision = record["revision"] if record is not None else None
    enabled = _subscription_current(state, current, record)
    return {
        "policy": current_policy,
        "self": {
            "recipient_revision": current["revision"],
            "subscription_revision": subscription_revision,
            **{kind: bool(enabled and record[kind]) for kind in KINDS},
            "can_edit": True,
            "health": _own_health(state, current["id"]),
        },
    }


def _period(kind: str, scheduled_day: date) -> tuple[str, date, date]:
    try:
        if kind == "morning":
            start, end = scheduled_day, scheduled_day + timedelta(days=1)
            key = f"{scheduled_day.isoformat()}/morning"
        elif kind == "evening":
            start, end = scheduled_day + timedelta(days=1), scheduled_day + timedelta(days=2)
            key = f"{scheduled_day.isoformat()}/evening"
        elif kind == "weekly":
            start, end = scheduled_day + timedelta(days=1), scheduled_day + timedelta(days=8)
            year, week, _weekday = scheduled_day.isocalendar()
            key = f"{year:04}-W{week:02}/weekly:{scheduled_day.isoformat()}"
        else:
            raise DomainError("invalid_field", "kind")
    except OverflowError:
        raise DomainError("invalid_field", "scheduled_at") from None
    return key, start, end


def _schedule(current: dict, kind: str, scheduled_day: date):
    if kind not in KINDS or not current[kind]["enabled"]:
        return None
    if kind == "weekly" and scheduled_day.weekday() != current[kind]["weekday"]:
        return None
    return recurrence.local_clock(scheduled_day, current[kind]["time"], current["timezone"])


def _marker_key(recipient: str, kind: str, period_key: str) -> str:
    return json.dumps([recipient, kind, period_key], ensure_ascii=False, separators=(",", ":"))


def _snapshot_has_content(
    state: dict,
    actor: dict,
    kind: str,
    window_start: str,
    window_end: str,
    now: datetime,
) -> bool:
    try:
        from . import digest_content

        result = digest_content.snapshot(state, actor, kind, window_start, window_end, now)
        return digest_content.has_content(result)
    except (DomainError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return False


def _event_data(
    state: dict,
    current_policy: dict,
    actor: dict,
    subscription: dict,
    kind: str,
    scheduled_day: date,
) -> dict | None:
    trigger = _schedule(current_policy, kind, scheduled_day)
    if trigger is None:
        return None
    period_key, start, end = _period(kind, scheduled_day)
    scheduled_at = trigger.astimezone(UTC)
    ttl = timedelta(hours=24 if kind == "weekly" else 6)
    expires_at = scheduled_at + ttl
    if kind == "morning":
        try:
            next_midnight = datetime.combine(
                scheduled_day + timedelta(days=1),
                time.min,
                ZoneInfo(current_policy["timezone"]),
            ).astimezone(UTC)
        except (OverflowError, ValueError, ZoneInfoNotFoundError):
            raise DomainError("invalid_field", "scheduled_at") from None
        expires_at = min(expires_at, next_midnight)
    if expires_at <= scheduled_at:
        return None
    return {
        "schema": 1,
        "kind": kind,
        "period_key": period_key,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "recipient_revision": actor["revision"],
        "subscription_revision": subscription["revision"],
        "policy_fingerprint": _policy_fingerprint(state),
        "scheduled_at": scheduled_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def _event_current(state: dict, event: dict, now: datetime, *, content: bool) -> bool:
    if (
        not isinstance(event, dict)
        or event.get("key") != KEY
        or not isinstance(event.get("recipient"), str)
        or not _module_enabled(state)
    ):
        return False
    data = event.get("data")
    if not isinstance(data, dict) or set(data) != EVENT_FIELDS:
        return False
    try:
        if type(data["schema"]) is not int or data["schema"] != 1:
            return False
        kind = data["kind"]
        if kind not in KINDS:
            return False
        current_now = timestamp(now, "now").astimezone(UTC)
        scheduled_at = timestamp(data["scheduled_at"], "scheduled_at").astimezone(UTC)
        expires_at = timestamp(data["expires_at"], "expires_at").astimezone(UTC)
        if current_now < scheduled_at or current_now >= expires_at:
            return False
        actor = _current_actor(state, event["recipient"])
        if strict_revision(data["recipient_revision"]) != actor["revision"]:
            return False
        subscription = _subscription(state, actor["id"])
        if (
            subscription is None
            or not _subscription_current(state, actor, subscription, kind)
            or strict_revision(data["subscription_revision"]) != subscription["revision"]
        ):
            return False
        current_policy = policy(state)
        if data["policy_fingerprint"] != _policy_fingerprint(state):
            return False
        local_day = scheduled_at.astimezone(ZoneInfo(current_policy["timezone"])).date()
        expected = _event_data(state, current_policy, actor, subscription, kind, local_day)
        if expected is None or data != expected:
            return False
        marker = _bucket(state, "digest_markers").get(
            _marker_key(actor["id"], kind, data["period_key"])
        )
        if (
            not isinstance(marker, dict)
            or set(marker) != MARKER_FIELDS
            or marker["event_id"] != event.get("id")
            or marker["recipient_revision"] != actor["revision"]
            or marker["subscription_revision"] != subscription["revision"]
            or marker["policy_fingerprint"] != data["policy_fingerprint"]
        ):
            return False
        return not content or _snapshot_has_content(
            state,
            actor,
            kind,
            data["window_start"],
            data["window_end"],
            current_now,
        )
    except (DomainError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return False


def delivery_allowed(state: dict, event: dict, now: datetime) -> bool:
    """Recheck current consent, marker, schedule and private content at dispatch."""
    return _event_current(state, event, now, content=True)


def target(state: dict, event: dict, now: datetime) -> dict | None:
    """Resolve only the current recipient's private Telegram target."""
    if not delivery_allowed(state, event, now):
        return None
    member = state.get("members", {}).get(event["recipient"], {})
    telegram_id = member.get("telegram_id")
    if type(telegram_id) is not int or telegram_id <= 0:
        return None
    language = member.get("language", state.get("settings", {}).get("language", "en"))
    if language not in {"en", "ru", "uk"}:
        language = "en"
    return {"channel": "telegram", "id": telegram_id, "language": language}


def _supersede_invalid(ctx: Context) -> None:
    try:
        outbox = _bucket(ctx.state, "outbox")
    except DomainError:
        return
    for event in outbox.values():
        if (
            not isinstance(event, dict)
            or event.get("key") != KEY
            or event.get("state") not in UNSENT
            or _event_current(ctx.state, event, ctx.now, content=True)
        ):
            continue
        deliveries = event.get("deliveries")
        if deliveries is None or deliveries == {}:
            event["state"] = "superseded"
            continue
        if not isinstance(deliveries, dict):
            continue
        states = {
            delivery.get("state") for delivery in deliveries.values() if isinstance(delivery, dict)
        }
        if states and states <= {"pending", "superseded"}:
            for delivery in deliveries.values():
                if isinstance(delivery, dict) and delivery.get("state") == "pending":
                    delivery["state"] = "superseded"
            event["state"] = "superseded"


def _marker_parts(value: str):
    try:
        parts = json.loads(value)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(parts, list)
        or len(parts) != 3
        or not all(isinstance(part, str) and part for part in parts)
        or parts[1] not in KINDS
        or value != json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    ):
        return None
    return parts


def _retired(state):
    values = _bucket(state, "digest_retired")
    if set(values) - set(KINDS):
        raise DomainError("invalid_field")
    for value in values.values():
        try:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError:
            raise DomainError("invalid_field") from None
    return values


def _scheduled_day(data):
    """Recover the canonical local period without relying on today's time zone."""
    kind = data["kind"]
    key = data["period_key"]
    raw = key.split(":", 1)[1] if kind == "weekly" else key.split("/", 1)[0]
    scheduled = date.fromisoformat(raw)
    expected_key, start, end = _period(kind, scheduled)
    if (
        raw != scheduled.isoformat()
        or key != expected_key
        or data["window_start"] != start.isoformat()
        or data["window_end"] != end.isoformat()
    ):
        raise ValueError("invalid period")
    return scheduled.isoformat()


def _prunable_pair(marker_key: str, marker: dict, event: dict, now: datetime) -> bool:
    parts = _marker_parts(marker_key)
    if (
        parts is None
        or not isinstance(marker, dict)
        or set(marker) != MARKER_FIELDS
        or not isinstance(event, dict)
        or event.get("id") != marker.get("event_id")
        or event.get("key") != KEY
        or event.get("recipient") != parts[0]
    ):
        return False
    data = event.get("data")
    if (
        not isinstance(data, dict)
        or set(data) != EVENT_FIELDS
        or data.get("kind") != parts[1]
        or data.get("period_key") != parts[2]
        or marker.get("recipient_revision") != data.get("recipient_revision")
        or marker.get("subscription_revision") != data.get("subscription_revision")
        or marker.get("policy_fingerprint") != data.get("policy_fingerprint")
    ):
        return False
    state = event.get("state")
    if state not in {*TERMINAL, "failed"}:
        return False
    deliveries = event.get("deliveries", {})
    allowed_delivery_states = {
        "sent": {"sent", "superseded"},
        "superseded": {"sent", "superseded"},
        "resolved": {"sent", "superseded", "failed", "uncertain"},
        "failed": {"failed", "superseded"},
    }[state]
    if not isinstance(deliveries, dict) or any(
        not isinstance(delivery, dict) or delivery.get("state") not in allowed_delivery_states
        for delivery in deliveries.values()
    ):
        return False
    try:
        period_day = date.fromisoformat(_scheduled_day(data))
        if type(data["schema"]) is not int or data["schema"] != 1:
            return False
        for field in ("recipient_revision", "subscription_revision"):
            if strict_revision(marker[field]) != strict_revision(data[field]):
                return False
        if (
            not isinstance(data["policy_fingerprint"], str)
            or re.fullmatch(r"[0-9a-f]{64}", data["policy_fingerprint"]) is None
        ):
            return False
        scheduled = timestamp(data["scheduled_at"], "scheduled_at").astimezone(UTC)
        created = timestamp(event["created_at"], "created_at").astimezone(UTC)
        expires = timestamp(data["expires_at"], "expires_at").astimezone(UTC)
        current = timestamp(now, "now").astimezone(UTC)
        # Original policy/time zone may no longer exist. Its local scheduled
        # date can differ from its UTC date by at most one calendar day. Do not
        # allow a fabricated distant period to poison the compact watermark.
        if (
            abs((period_day - scheduled.date()).days) > 1
            or not scheduled <= created <= scheduled + WINDOW
            or not scheduled
            < expires
            <= scheduled + timedelta(hours=24 if data["kind"] == "weekly" else 6)
        ):
            return False
    except (DomainError, KeyError, IndexError, TypeError, ValueError, OverflowError, OSError):
        return False
    horizon = (
        FAILED_RETENTION
        if state == "failed"
        else WEEKLY_RETENTION
        if data["kind"] == "weekly"
        else DAILY_RETENTION
    )
    return current >= scheduled + horizon


def prune(ctx: Context) -> int:
    """Delete only exact old terminal digest marker/event pairs."""
    markers = _bucket(ctx.state, "digest_markers")
    outbox = _bucket(ctx.state, "outbox")
    retired = _retired(ctx.state)
    removed = []
    for marker_key in sorted(markers):
        marker = markers[marker_key]
        event_id = marker.get("event_id") if isinstance(marker, dict) else None
        event = outbox.get(event_id) if isinstance(event_id, str) else None
        if _prunable_pair(marker_key, marker, event, ctx.now):
            removed.append((marker_key, event_id))
    for marker_key, event_id in removed:
        data = outbox[event_id]["data"]
        kind, scheduled_day = data["kind"], _scheduled_day(data)
        if scheduled_day > retired.get(kind, ""):
            retired = _mutable_bucket(ctx, "digest_retired")
            retired[kind] = scheduled_day
        markers.pop(marker_key, None)
        outbox.pop(event_id, None)
    return len(removed)


def health_stats(state: dict) -> dict:
    """Return counts-only operational retention health for HA Repairs."""
    try:
        _retired(state)
        markers = _bucket(state, "digest_markers")
        outbox = _bucket(state, "outbox")
    except DomainError:
        return {"markers": 0, "retained": 0, "unresolved": 0, "capacity": True}
    events = [
        event for event in outbox.values() if isinstance(event, dict) and event.get("key") == KEY
    ]
    unresolved = sum(
        event.get("state") in {"pending", "awaiting_channel", "sending", "uncertain", "failed"}
        for event in events
    )
    return {
        "markers": len(markers),
        "retained": len(events),
        "unresolved": unresolved,
        "capacity": len(markers) >= MAX_RECORDS or len(events) >= MAX_RECORDS,
    }


def tick(ctx: Context) -> None:
    """Create at most one content-free intent per recipient, kind and period."""
    try:
        prune(ctx)
        _supersede_invalid(ctx)
        if not _module_enabled(ctx.state):
            return
        current_policy = policy(ctx.state)
        retired = _retired(ctx.state)
        subscriptions = _bucket(ctx.state, "digest_subscriptions")
        markers = _bucket(ctx.state, "digest_markers")
        outbox = _bucket(ctx.state, "outbox")
        current_now = timestamp(ctx.now, "now").astimezone(UTC)
    except DomainError:
        return
    retained = sum(
        1 for event in outbox.values() if isinstance(event, dict) and event.get("key") == KEY
    )
    if len(markers) >= MAX_RECORDS or retained >= MAX_RECORDS:
        return
    local_now = current_now.astimezone(ZoneInfo(current_policy["timezone"]))
    for kind in KINDS:
        # Three monotonic dates survive pruning and configuration/clock rollback.
        # Retiring one old period closes that kind's older history for everyone;
        # outstanding unresolved deliveries retain their independent lifecycle.
        if local_now.date().isoformat() <= retired.get(kind, ""):
            continue
        trigger = _schedule(current_policy, kind, local_now.date())
        if (
            trigger is None
            or not trigger.astimezone(UTC) <= current_now <= trigger.astimezone(UTC) + WINDOW
        ):
            continue
        for recipient in sorted(subscriptions):
            try:
                actor = _current_actor(ctx.state, recipient)
                subscription = _subscription(ctx.state, recipient)
            except DomainError:
                continue
            if not _subscription_current(ctx.state, actor, subscription, kind):
                continue
            data = _event_data(
                ctx.state, current_policy, actor, subscription, kind, local_now.date()
            )
            if data is None:
                continue
            marker_key = _marker_key(recipient, kind, data["period_key"])
            if marker_key in markers:
                continue
            if not _snapshot_has_content(
                ctx.state,
                actor,
                kind,
                data["window_start"],
                data["window_end"],
                current_now,
            ):
                continue
            if len(markers) >= MAX_RECORDS or retained >= MAX_RECORDS:
                return
            notifier = Context(
                ctx.state,
                ctx.actor,
                ctx.now,
                f"digest:{recipient}:{kind}:{data['period_key']}",
            )
            event_id = notifier.notify(recipient, KEY, data)
            _mutable_bucket(ctx, "digest_markers")[marker_key] = {
                "event_id": event_id,
                "recipient_revision": actor["revision"],
                "subscription_revision": subscription["revision"],
                "policy_fingerprint": data["policy_fingerprint"],
            }
            markers = _bucket(ctx.state, "digest_markers")
            retained += 1
