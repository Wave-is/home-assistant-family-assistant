"""Family events with private projections, approval and bounded preparation reminders."""

from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..const import PRIVILEGED
from .calendar_occurrences import expand
from .context import Context
from .household import timezone
from .recurrence import validate as validate_rule
from .task_access import personal_task
from .validation import DomainError, enum, fields, text, timestamp

EVENT_FIELDS = {
    "title",
    "description",
    "location",
    "start",
    "end",
    "all_day",
    "timezone",
    "rule",
    "participants",
    "escort",
    "task_ids",
    "preparation",
    "reminder_minutes",
    "visibility",
}
EXPANSION_FIELDS = {
    "id",
    "title",
    "description",
    "location",
    "start",
    "end",
    "all_day",
    "timezone",
    "rule",
    "status",
}


def configuration(state):
    return {"publish_to_ha": False, "revision": 0, **state["settings"].get("calendar", {})}


def _integer(value, key, lower=1, upper=2**53 - 1):
    if type(value) is not int or not lower <= value <= upper:
        raise DomainError("invalid_field", key)
    return value


def _optional(value, key, maximum):
    return "" if value == "" else text(value, key, maximum)


def visible(record, actor):
    return actor["role"] != "guest" and (
        actor["role"] in PRIVILEGED
        or record["visibility"] == "family"
        or actor["id"] == record["creator"]
        or actor["id"] in record["participants"]
        or actor["id"] == record.get("escort")
    )


def _editable(ctx, record):
    if not ctx.privileged and record["creator"] != ctx.actor_id:
        raise DomainError("forbidden")


def _member(ctx, value):
    member = ctx.member(value)
    if member["role"] == "guest":
        raise DomainError("invalid_field", "participants")
    return member


def _list(value, key, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise DomainError("invalid_field", key)
    return value


def _normalized(ctx, value):
    value["title"] = text(value["title"], "title", 255)
    value["description"] = _optional(value["description"], "description", 2000)
    value["location"] = _optional(value["location"], "location", 500)
    value["timezone"] = timezone(value["timezone"])
    enum(value["visibility"], {"family", "participants"}, "visibility")
    participants = [_member(ctx, m)["id"] for m in _list(value["participants"], "participants", 20)]
    if not participants or len(set(participants)) != len(participants):
        raise DomainError("invalid_field", "participants")
    if not ctx.privileged and participants != [ctx.actor_id]:
        raise DomainError("forbidden")
    value["participants"] = participants
    if value["escort"] is not None:
        escort = _member(ctx, value["escort"])
        if escort["role"] not in {"owner", "parent", "adult"}:
            raise DomainError("invalid_field", "escort")
        value["escort"] = escort["id"]
    tasks = []
    for identifier in _list(value["task_ids"], "task_ids", 30):
        task = ctx.record("tasks", identifier)
        if personal_task(task) or task["assignee"] not in participants:
            raise DomainError("invalid_field", "task_ids")
        tasks.append(task["id"])
    if len(set(tasks)) != len(tasks):
        raise DomainError("invalid_field", "task_ids")
    value["task_ids"] = tasks
    value["preparation"] = [
        text(v, "preparation", 200) for v in _list(value["preparation"], "preparation", 30)
    ]
    reminders = [
        _integer(v, "reminder_minutes", 0, 10080)
        for v in _list(value["reminder_minutes"], "reminder_minutes", 6)
    ]
    if len(set(reminders)) != len(reminders):
        raise DomainError("invalid_field", "reminder_minutes")
    value["reminder_minutes"] = sorted(reminders, reverse=True)
    value["rule"] = validate_rule(value["rule"]) if value["rule"] is not None else None
    # Validate the entire event even when outside the current displayed range.
    occurrences(
        value, ctx.now, ctx.now + timedelta(days=1), ctx.state["settings"].get("timezone", "UTC")
    )
    return value


def occurrences(record, start, end, zone):
    if record.get("archived"):
        return []
    return expand({key: record[key] for key in EXPANSION_FIELDS}, start, end, zone)


def _supersede(ctx, identifier=None):
    for event in ctx.state["outbox"].values():
        if (
            event["key"] == "calendar_reminder"
            and (identifier is None or event["data"]["event_id"] == identifier)
            and event["state"] in {"pending", "awaiting_channel"}
        ):
            event["state"] = "superseded"


def _history(ctx, record, action, reason=""):
    record.setdefault("history", []).append(
        {"actor": ctx.actor_id, "at": ctx.now.isoformat(), "action": action, "reason": reason}
    )
    ctx.touch(record)


def handle(ctx, action, payload):
    if ctx.actor["role"] == "guest":
        raise DomainError("forbidden")
    if action == "configure":
        if ctx.actor["role"] != "owner":
            raise DomainError("forbidden")
        fields(
            payload,
            {"revision", "publish_to_ha", "confirm_public_visibility"},
            {"revision", "publish_to_ha"},
        )
        previous = configuration(ctx.state)
        if _integer(payload["revision"], "revision", 0) != previous["revision"]:
            raise DomainError("conflict")
        if type(payload["publish_to_ha"]) is not bool or (
            "confirm_public_visibility" in payload
            and type(payload["confirm_public_visibility"]) is not bool
        ):
            raise DomainError("invalid_field", "publish_to_ha")
        if (
            payload["publish_to_ha"]
            and not previous["publish_to_ha"]
            and payload.get("confirm_public_visibility") is not True
        ):
            raise DomainError("confirmation_required")
        value = {"publish_to_ha": payload["publish_to_ha"], "revision": previous["revision"] + 1}
        ctx.state["settings"]["calendar"] = value
        return value
    if action == "save":
        fields(
            payload,
            EVENT_FIELDS | {"id", "revision"},
            {"title", "start", "end"} | ({"revision"} if "id" in payload else set()),
        )
        previous = None
        if "id" in payload:
            _integer(payload["revision"], "revision")
            previous = ctx.record("calendar", payload["id"], payload["revision"])
            _editable(ctx, previous)
            if previous["archived"] or previous["status"] == "cancelled":
                raise DomainError("invalid_transition")
        elif "revision" in payload:
            raise DomainError("invalid_field", "revision")
        value = {
            "description": "",
            "location": "",
            "all_day": False,
            "timezone": ctx.state["settings"].get("timezone", "UTC"),
            "rule": None,
            "participants": [ctx.actor_id],
            "escort": None,
            "task_ids": [],
            "preparation": [],
            "reminder_minutes": [],
            "visibility": "family",
            "archived": False,
            **deepcopy(previous or {}),
            **payload,
        }
        value["status"] = "tentative" if ctx.actor["role"] == "child" else "confirmed"
        value["id"] = previous["id"] if previous else ctx.identifier("E")
        _normalized(ctx, value)
        if not previous:
            value.update(creator=ctx.actor_id, created_at=ctx.now.isoformat(), reminders={})
        value["effective_at"] = ctx.now.isoformat()
        value["approved_by"] = ctx.actor_id if value["status"] == "confirmed" else None
        _history(ctx, value, "updated" if previous else "created")
        ctx.state["calendar"][value["id"]] = value
        _supersede(ctx, value["id"])
        return value
    if action not in {"approve", "cancel", "archive"}:
        raise DomainError("unknown_action")
    fields(payload, {"id", "revision", "reason"}, {"id", "revision", "reason"})
    _integer(payload["revision"], "revision")
    record = ctx.record("calendar", payload["id"], payload["revision"])
    reason = text(payload["reason"], "reason", 500)
    if action == "approve":
        ctx.require_parent()
        if record["status"] != "tentative" or record["archived"]:
            raise DomainError("invalid_transition")
        _normalized(ctx, record)
        record.update(
            status="confirmed", approved_by=ctx.actor_id, effective_at=ctx.now.isoformat()
        )
    else:
        _editable(ctx, record)
        if record["archived"] or action == "cancel" and record["status"] == "cancelled":
            raise DomainError("invalid_transition")
        if action == "archive":
            record["archived"] = True
        else:
            record["status"] = "cancelled"
    _history(ctx, record, action, reason)
    _supersede(ctx, record["id"])
    return record


def view(state, actor, now=None):
    now = now or datetime.now(UTC)
    zone = state["settings"].get("timezone", "UTC")
    records = [r for r in state["calendar"].values() if visible(r, actor)]
    return {
        "config": configuration(state),
        "events": [{k: v for k, v in r.items() if k != "reminders"} for r in records],
        "occurrences": sorted(
            [item for r in records for item in occurrences(r, now, now + timedelta(days=30), zone)],
            key=lambda r: moment(r, zone),
        ),
    }


def moment(occurrence, zone):
    if occurrence["all_day"]:
        return datetime.combine(
            date.fromisoformat(occurrence["start"]), time.min, ZoneInfo(zone)
        ).astimezone(UTC)
    return timestamp(occurrence["start"], "start").astimezone(UTC)


def published(state, start, end, display_timezone=None):
    if "calendar" not in state["settings"]["modules"] or not configuration(state)["publish_to_ha"]:
        return []
    zone = display_timezone or state["settings"].get("timezone", "UTC")
    result = [
        item
        for record in state["calendar"].values()
        if record["visibility"] == "family" and record["status"] == "confirmed"
        for item in occurrences(record, start, end, zone)
    ]
    if len(result) > 5000:
        raise DomainError("command_too_large")
    return sorted(result, key=lambda r: moment(r, zone))


def tick(ctx):
    if "calendar" not in ctx.state["settings"]["modules"]:
        _supersede(ctx)
        return
    now = ctx.now.astimezone(UTC)
    zone = ctx.state["settings"].get("timezone", "UTC")
    for record in ctx.state["calendar"].values():
        if record["archived"] or record["status"] != "confirmed" or not record["reminder_minutes"]:
            continue
        # Only five minutes of catch-up; never send weeks of missed preparation messages.
        for item in occurrences(record, now - timedelta(minutes=5), now + timedelta(days=8), zone):
            start = moment(item, zone)
            for minutes in record["reminder_minutes"]:
                due = start - timedelta(minutes=minutes)
                key = f"{item['id']}:{item['start']}:{minutes}"
                if (
                    not (
                        now - timedelta(minutes=5) <= due <= now
                        and due >= timestamp(record["effective_at"], "effective_at")
                    )
                    or key in record["reminders"]
                ):
                    continue
                record["reminders"][key] = now.isoformat()
                notifier = Context(ctx.state, ctx.actor, ctx.now, f"calendar:{key}")
                targets = set(record["participants"]) | (
                    {record["escort"]} if record["escort"] else set()
                )
                for target in sorted(targets):
                    member = ctx.state["members"].get(target)
                    if member and member.get("active", True) and member["role"] != "guest":
                        notifier.notify(
                            target,
                            "calendar_reminder",
                            {
                                "event_id": record["id"],
                                "expires_at": (due + timedelta(minutes=5)).isoformat(),
                                "title": record["title"],
                                "start": item["start"],
                                "all_day": item["all_day"],
                                "timezone": record["timezone"],
                                "location": record["location"],
                                "preparation": record["preparation"],
                            },
                        )
        record["reminders"] = {
            k: v
            for k, v in record["reminders"].items()
            if timestamp(v, "reminder") >= now - timedelta(days=90)
        }
