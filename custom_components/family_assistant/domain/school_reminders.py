"""Opt-in, content-free intents for private school preparation reminders.

The domain records only current source versions and a local school date.  A
delivery adapter may render current names and materials only after calling
``delivery_allowed``.  This module never starts a routine, creates a task,
changes points, or controls a device.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import PRIVILEGED
from . import recurrence, school
from .context import Context
from .validation import DomainError, fields, text, timestamp
from .validation import revision as strict_revision

KEY = "school_preparation_reminder"
ACTION = "preparation_reminder_access_set"
WINDOW = timedelta(minutes=5)
MAX_MARKERS = 10_000
SUBSCRIPTION_FIELDS = frozenset(
    {
        "member",
        "member_revision",
        "recipient_revision",
        "subscription_revision",
        "enabled",
    }
)
EVENT_FIELDS = frozenset(
    {
        "timetable_id",
        "timetable_revision",
        "member",
        "member_revision",
        "recipient_revision",
        "date",
        "routine_id",
        "routine_revision",
        "subscription_revision",
        "policy_fingerprint",
        "expires_at",
    }
)


def _modules(state: dict, *, routines: bool) -> bool:
    settings = state.get("settings", {})
    modules = settings.get("modules", []) if isinstance(settings, dict) else []
    return (
        isinstance(modules, list)
        and "school" in modules
        and (not routines or "routines" in modules)
    )


def _policy(state: dict) -> dict:
    settings = state.get("settings", {})
    if not isinstance(settings, dict):
        raise DomainError("invalid_field", "settings")
    enabled = settings.get("school_preparation_reminders", False)
    days_before = settings.get("school_preparation_days_before", 1)
    clock = settings.get("school_preparation_time", "20:00")
    zone_name = settings.get("timezone", "UTC")
    if type(enabled) is not bool:
        raise DomainError("invalid_field", "school_preparation_reminders")
    if type(days_before) is not int or days_before not in {0, 1}:
        raise DomainError("invalid_field", "school_preparation_days_before")
    try:
        clock = recurrence.clock(clock)
    except DomainError:
        raise DomainError("invalid_field", "school_preparation_time") from None
    if not isinstance(zone_name, str):
        raise DomainError("invalid_field", "timezone")
    try:
        ZoneInfo(zone_name)
    except (ValueError, ZoneInfoNotFoundError):
        raise DomainError("invalid_field", "timezone") from None
    return {
        "enabled": enabled,
        "days_before": days_before,
        "time": clock,
        "timezone": zone_name,
    }


def _fingerprint(policy: dict) -> str:
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _school_state(state: dict) -> dict:
    value = state.get("school", {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "school")
    return value


def _bucket(state: dict, name: str) -> dict:
    value = _school_state(state).get(name, {})
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _mutable_bucket(ctx: Context, name: str) -> dict:
    school_state = ctx.state.get("school")
    if school_state is None:
        school_state = {}
        ctx.state["school"] = school_state
    if not isinstance(school_state, dict):
        raise DomainError("invalid_field", "school")
    value = school_state.get(name)
    if value is None:
        value = {}
        school_state[name] = value
    if not isinstance(value, dict):
        raise DomainError("invalid_field", name)
    return value


def _key(recipient: str, member: str) -> str:
    return json.dumps([recipient, member], ensure_ascii=False, separators=(",", ":"))


def _marker_key(recipient: str, timetable_id: str, day: str) -> str:
    return json.dumps([recipient, timetable_id, day], ensure_ascii=False, separators=(",", ":"))


def _current_actor(state: dict, actor_id: str) -> dict:
    actor = state.get("members", {}).get(actor_id)
    if (
        not isinstance(actor, dict)
        or actor.get("id") != actor_id
        or actor.get("active") is not True
        or actor.get("role") not in {*PRIVILEGED, "child"}
    ):
        raise DomainError("forbidden")
    strict_revision(actor.get("revision"))
    return actor


def _current_child(state: dict, member_id, member_revision) -> dict:
    member_id = text(member_id, "member", 80)
    member = state.get("members", {}).get(member_id)
    if (
        not isinstance(member, dict)
        or member.get("id") != member_id
        or member.get("active") is not True
        or member.get("role") != "child"
    ):
        raise DomainError("unknown_member")
    if strict_revision(member_revision) != strict_revision(member.get("revision")):
        raise DomainError("conflict")
    return member


def _target(ctx: Context, payload: dict) -> tuple[dict, dict]:
    if not _modules(ctx.state, routines=False):
        raise DomainError("module_disabled")
    actor = _current_actor(ctx.state, ctx.actor_id)
    if strict_revision(payload["recipient_revision"]) != actor["revision"]:
        raise DomainError("conflict")
    if actor["role"] == "child" and payload["member"] != actor["id"]:
        raise DomainError("forbidden")
    member = _current_child(ctx.state, payload["member"], payload["member_revision"])
    return actor, member


def _requested_revision(value) -> int | None:
    if value is None:
        return None
    try:
        return strict_revision(value)
    except DomainError:
        raise DomainError("invalid_field", "subscription_revision") from None


def _record_receipt(record: dict) -> dict:
    return {
        "member": record["member"],
        "enabled": record["enabled"],
        "revision": record["revision"],
    }


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Set the current actor's own subscription for one current child."""
    if action != ACTION:
        raise DomainError("unknown_action")
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    fields(payload, SUBSCRIPTION_FIELDS, SUBSCRIPTION_FIELDS)
    actor, member = _target(ctx, payload)
    if type(payload["enabled"]) is not bool:
        raise DomainError("invalid_field", "enabled")
    requested = _requested_revision(payload["subscription_revision"])
    subscriptions = _bucket(ctx.state, "preparation_reminder_subscriptions")
    key = _key(actor["id"], member["id"])
    previous = subscriptions.get(key)
    if previous is None:
        if requested is not None:
            raise DomainError("conflict")
        if payload["enabled"] is not True:
            raise DomainError("invalid_transition")
        revision = 1
    else:
        if not isinstance(previous, dict):
            raise DomainError("invalid_field", "preparation_reminder_subscriptions")
        current_revision = strict_revision(previous.get("revision"))
        if requested is None or requested != current_revision:
            raise DomainError("conflict")
        revision = current_revision + 1
        if revision > 2**53 - 1:
            raise DomainError("invalid_field", "subscription_revision")
        if (
            previous.get("recipient") == actor["id"]
            and previous.get("recipient_revision") == actor["revision"]
            and previous.get("member") == member["id"]
            and previous.get("member_revision") == member["revision"]
            and previous.get("enabled") is payload["enabled"]
        ):
            raise DomainError("invalid_transition")
    record = {
        "recipient": actor["id"],
        "recipient_revision": actor["revision"],
        "member": member["id"],
        "member_revision": member["revision"],
        "enabled": payload["enabled"],
        "revision": revision,
    }
    _mutable_bucket(ctx, "preparation_reminder_subscriptions")[key] = record
    return _record_receipt(record)


def authorize_replay(ctx: Context, action: str, payload: dict, result: dict) -> None:
    """Return a stored receipt only while its private subscription is current."""
    if action != ACTION or not isinstance(payload, dict):
        raise DomainError("forbidden")
    fields(payload, SUBSCRIPTION_FIELDS, SUBSCRIPTION_FIELDS)
    actor, member = _target(ctx, payload)
    if type(payload["enabled"]) is not bool:
        raise DomainError("invalid_field", "enabled")
    requested = _requested_revision(payload["subscription_revision"])
    record = _bucket(ctx.state, "preparation_reminder_subscriptions").get(
        _key(actor["id"], member["id"])
    )
    if not isinstance(record, dict):
        raise DomainError("forbidden")
    expected_revision = 1 if requested is None else requested + 1
    if (
        record.get("recipient") != actor["id"]
        or record.get("recipient_revision") != actor["revision"]
        or record.get("member") != member["id"]
        or record.get("member_revision") != member["revision"]
        or record.get("enabled") is not payload["enabled"]
        or record.get("revision") != expected_revision
        or result != _record_receipt(record)
    ):
        raise DomainError("forbidden")


def view(state: dict, actor: dict) -> dict:
    """Project only the current actor's own per-child subscription controls."""
    empty = {"preparation_reminders": {"policy": None, "self_targets": []}}
    if not _modules(state, routines=False) or not isinstance(actor, dict):
        return empty
    try:
        current = _current_actor(state, actor.get("id"))
        policy = _policy(state)
        subscriptions = _bucket(state, "preparation_reminder_subscriptions")
    except (DomainError, TypeError):
        return empty
    if current["role"] == "child":
        targets = [current]
    else:
        targets = sorted(
            (
                member
                for member in state.get("members", {}).values()
                if isinstance(member, dict)
                and member.get("active") is True
                and member.get("role") == "child"
            ),
            key=lambda item: item.get("id", ""),
        )
    rows = []
    for member in targets:
        try:
            member_revision = strict_revision(member.get("revision"))
        except DomainError:
            continue
        record = subscriptions.get(_key(current["id"], member["id"]))
        subscription_revision = None
        enabled = False
        if isinstance(record, dict):
            try:
                subscription_revision = strict_revision(record.get("revision"))
            except DomainError:
                subscription_revision = None
            enabled = bool(
                subscription_revision is not None
                and record.get("recipient") == current["id"]
                and record.get("recipient_revision") == current["revision"]
                and record.get("member") == member["id"]
                and record.get("member_revision") == member_revision
                and record.get("enabled") is True
            )
        rows.append(
            {
                "member": member["id"],
                "member_revision": member_revision,
                "recipient_revision": current["revision"],
                "enabled": enabled,
                "subscription_revision": subscription_revision,
            }
        )
    return {"preparation_reminders": {"policy": policy, "self_targets": rows}}


def _source(state: dict, timetable: dict, target_date) -> tuple[dict, object] | None:
    if (
        not isinstance(timetable, dict)
        or timetable.get("status") != "active"
        or not isinstance(timetable.get("id"), str)
    ):
        return None
    member = state.get("members", {}).get(timetable.get("member"))
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") != "child"
    ):
        return None
    try:
        timetable_revision = strict_revision(timetable.get("revision"))
        member_revision = strict_revision(member.get("revision"))
        if strict_revision(timetable.get("member_revision")) != member_revision:
            return None
    except DomainError:
        return None
    occurrences = [
        item
        for item in school._occurrences(state, [timetable], target_date)
        if item.get("timetable_id") == timetable["id"]
        and item.get("date") == target_date.isoformat()
    ]
    if not occurrences:
        return None
    link = timetable.get("backpack_routine")
    if not isinstance(link, dict) or set(link) != {"id", "revision"}:
        return None
    routine_id = link.get("id")
    routine_revision = link.get("revision")
    if not isinstance(routine_id, str) or not routine_id:
        return None
    try:
        routine_revision = strict_revision(routine_revision)
    except DomainError:
        return None
    routine = state.get("routines", {}).get(routine_id)
    if not school._routine_usable(state, routine, member["id"], routine_revision, routine_id):
        return None
    zone = state["settings"]["timezone"]
    starts = [recurrence.local_clock(target_date, item.get("start"), zone) for item in occurrences]
    starts = [value for value in starts if value is not None]
    if not starts:
        return None
    return (
        {
            "timetable_id": timetable["id"],
            "timetable_revision": timetable_revision,
            "member": member["id"],
            "member_revision": member_revision,
            "routine_id": routine_id,
            "routine_revision": routine_revision,
        },
        min(starts, key=lambda value: value.astimezone(UTC)),
    )


def _already_started(state: dict, timetable_id: str, day: str) -> bool:
    preparations = _school_state(state).get("preparations", {})
    if not isinstance(preparations, dict):
        return True
    return any(
        isinstance(item, dict)
        and item.get("timetable_id") == timetable_id
        and item.get("date") == day
        for item in preparations.values()
    )


def _subscription_current(state: dict, record: dict, member_id: str, member_revision: int) -> bool:
    recipient = state.get("members", {}).get(record.get("recipient"))
    if (
        not isinstance(recipient, dict)
        or recipient.get("active") is not True
        or recipient.get("role") not in {*PRIVILEGED, "child"}
        or recipient.get("role") == "child"
        and recipient.get("id") != member_id
    ):
        return False
    try:
        return (
            record.get("enabled") is True
            and record.get("member") == member_id
            and strict_revision(record.get("member_revision")) == member_revision
            and strict_revision(record.get("recipient_revision"))
            == strict_revision(recipient.get("revision"))
            and strict_revision(record.get("revision")) >= 1
        )
    except DomainError:
        return False


def tick(ctx: Context) -> None:
    """Create bounded private intents only in the five-minute local window."""
    from . import school_retention

    school_retention.prune(ctx)
    try:
        policy = _policy(ctx.state)
        if not policy["enabled"] or not _modules(ctx.state, routines=True):
            return
        markers = _bucket(ctx.state, "preparation_reminder_markers")
        subscriptions = _bucket(ctx.state, "preparation_reminder_subscriptions")
        timetables = _bucket(ctx.state, "timetables")
    except DomainError:
        return
    if len(markers) >= MAX_MARKERS:
        return
    now = timestamp(ctx.now, "now").astimezone(UTC)
    zone = ZoneInfo(policy["timezone"])
    local_now = now.astimezone(zone)
    trigger = recurrence.local_clock(local_now.date(), policy["time"], policy["timezone"])
    if trigger is None or not trigger.astimezone(UTC) <= now <= trigger.astimezone(UTC) + WINDOW:
        return
    try:
        target_date = local_now.date() + timedelta(days=policy["days_before"])
    except OverflowError:
        return
    if not school_retention.creation_allowed(ctx.state, target_date):
        return
    fingerprint = _fingerprint(policy)
    for timetable_id in sorted(timetables):
        timetable = timetables[timetable_id]
        source = _source(ctx.state, timetable, target_date)
        if source is None:
            continue
        stamp, first_lesson = source
        day = target_date.isoformat()
        expires_at = first_lesson.astimezone(UTC)
        if expires_at <= now or _already_started(ctx.state, stamp["timetable_id"], day):
            continue
        for key in sorted(subscriptions):
            subscription = subscriptions[key]
            if not isinstance(subscription, dict) or subscription.get("member") != stamp["member"]:
                continue
            if not _subscription_current(
                ctx.state, subscription, stamp["member"], stamp["member_revision"]
            ):
                continue
            marker_key = _marker_key(subscription["recipient"], stamp["timetable_id"], day)
            if marker_key in markers:
                continue
            if len(markers) >= MAX_MARKERS:
                return
            data = {
                **stamp,
                "recipient_revision": subscription["recipient_revision"],
                "date": day,
                "subscription_revision": subscription["revision"],
                "policy_fingerprint": fingerprint,
                "expires_at": expires_at.isoformat(),
            }
            notifier = Context(
                ctx.state,
                ctx.actor,
                ctx.now,
                f"school-reminder:{subscription['recipient']}:{stamp['timetable_id']}:{day}",
            )
            if not school_retention.creation_allowed(ctx.state, target_date):
                return
            event_id = notifier.notify(subscription["recipient"], KEY, data)
            markers = _mutable_bucket(ctx, "preparation_reminder_markers")
            markers[marker_key] = {
                "event_id": event_id,
                "timetable_revision": stamp["timetable_revision"],
                "member_revision": stamp["member_revision"],
                "recipient_revision": subscription["recipient_revision"],
                "routine_revision": stamp["routine_revision"],
                "subscription_revision": subscription["revision"],
            }


def delivery_allowed(state: dict, event: dict, now) -> bool:
    """Fail closed unless a content-free intent is still current and useful."""
    try:
        if (
            not isinstance(event, dict)
            or event.get("key") != KEY
            or not isinstance(event.get("recipient"), str)
            or not _modules(state, routines=True)
        ):
            return False
        data = event.get("data")
        if not isinstance(data, dict) or set(data) != EVENT_FIELDS:
            return False
        policy = _policy(state)
        if not policy["enabled"] or data["policy_fingerprint"] != _fingerprint(policy):
            return False
        current_now = timestamp(now, "now").astimezone(UTC)
        expires_at = timestamp(data["expires_at"], "expires_at").astimezone(UTC)
        if current_now >= expires_at:
            return False
        for field in (
            "timetable_revision",
            "member_revision",
            "recipient_revision",
            "routine_revision",
            "subscription_revision",
        ):
            strict_revision(data[field])
        target_date = recurrence.local_date(data["date"])
        recipient = _current_actor(state, event["recipient"])
        if recipient["revision"] != data["recipient_revision"]:
            return False
        member = _current_child(state, data["member"], data["member_revision"])
        if recipient["role"] == "child" and recipient["id"] != member["id"]:
            return False
        subscription = _bucket(state, "preparation_reminder_subscriptions").get(
            _key(recipient["id"], member["id"])
        )
        if (
            not isinstance(subscription, dict)
            or not _subscription_current(state, subscription, member["id"], member["revision"])
            or subscription.get("revision") != data["subscription_revision"]
        ):
            return False
        timetable = _bucket(state, "timetables").get(data["timetable_id"])
        source = _source(state, timetable, target_date)
        if source is None:
            return False
        stamp, first_lesson = source
        expected = {
            **stamp,
            "recipient_revision": recipient["revision"],
            "date": data["date"],
            "subscription_revision": subscription["revision"],
            "policy_fingerprint": _fingerprint(policy),
            "expires_at": first_lesson.astimezone(UTC).isoformat(),
        }
        if data != expected or _already_started(state, stamp["timetable_id"], data["date"]):
            return False
        marker = _bucket(state, "preparation_reminder_markers").get(
            _marker_key(recipient["id"], stamp["timetable_id"], data["date"])
        )
        return bool(
            isinstance(marker, dict)
            and marker.get("event_id") == event.get("id")
            and marker.get("timetable_revision") == stamp["timetable_revision"]
            and marker.get("member_revision") == stamp["member_revision"]
            and marker.get("recipient_revision") == recipient["revision"]
            and marker.get("routine_revision") == stamp["routine_revision"]
            and marker.get("subscription_revision") == subscription["revision"]
        )
    except (DomainError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return False
