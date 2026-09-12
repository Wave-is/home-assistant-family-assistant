"""Private, bounded online-school facts; no provider I/O or automatic effects.

The synchronization helpers are synchronous transaction callbacks. Adapters must
call them through a guarded Engine.system_update and serialize a source's fetches
or pass their start time as ``now`` so an older completion cannot replace newer
facts. Credentials and cookies never belong in this store.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import PRIVILEGED
from .context import Context
from .validation import DomainError, fields, revision, timestamp

MAX_SOURCES = 8
MAX_LESSONS = 300
MAX_GRADES = 1000
MAX_ABSENCES = 500
MAX_CHANGES = 100
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
FRESH_FOR = timedelta(hours=6)
FAILURES = frozenset(
    {
        "online_school_auth_failed",
        "online_school_unavailable",
        "online_school_rate_limited",
        "online_school_invalid_response",
        "online_school_student_mismatch",
        "online_school_invalid_config",
        "online_school_timeout",
    }
)
RULE_DEFAULTS = {
    "enabled": False,
    "homework_time": "18:00",
    "notify_changes": False,
    "recipients": [],
}
SNAPSHOT_FIELDS = {
    "student_id",
    "student_name",
    "timezone",
    "source_url",
    "coverage_start",
    "coverage_end",
    "lessons",
    "grades",
    "absences",
}
LESSON_FIELDS = {
    "id",
    "date",
    "start",
    "end",
    "subject",
    "room",
    "teacher",
    "topic",
    "homework",
    "estimated_minutes",
    "cancelled",
    "replacement",
    "links",
    "attachments",
}
GRADE_FIELDS = {"id", "date", "period", "subject", "value", "comment", "kind"}
ABSENCE_FIELDS = {"id", "date", "period", "subject", "comment"}
CONFIG_FIELDS = {
    "id",
    "revision",
    "member",
    "member_revision",
    "provider",
    "student_id",
    "generation",
    "label",
    "timezone",
    "enabled",
    "rules",
}
CONFIG_REQUIRED = CONFIG_FIELDS - {"id", "revision", "enabled", "rules"}
_CLOCK = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_HTML = re.compile(r"</?[A-Za-z][^>]*>")


def _plain(value, field, maximum, *, empty=False):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (not empty and not value.strip())
        or any(ord(char) < 32 and char not in "\n\t" for char in value)
        or _HTML.search(value)
    ):
        raise DomainError("invalid_field", field)
    return value.strip()


def _object(value, allowed, required=None, field="snapshot"):
    if not isinstance(value, dict):
        raise DomainError("invalid_field", field)
    fields(value, allowed, allowed if required is None else required)
    return value


def _bool(value, field):
    if type(value) is not bool:
        raise DomainError("invalid_field", field)
    return value


def _integer(value, field, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise DomainError("invalid_field", field)
    return value


def _day(value, field, *, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise DomainError("invalid_field", field)
    try:
        date.fromisoformat(value)
    except ValueError:
        raise DomainError("invalid_field", field) from None
    return value


def _clock(value, field, *, empty=False):
    if empty and value == "":
        return value
    if not isinstance(value, str) or not _CLOCK.fullmatch(value):
        raise DomainError("invalid_field", field)
    return value


def _zone(value):
    value = _plain(value, "timezone", 80)
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise DomainError("invalid_field", "timezone") from None
    return value


def _url(value, field, *, source=False):
    value = _plain(value, field, 2048)
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "\\" in value
            or any(char.isspace() for char in value)
            or (source and (parsed.query or parsed.fragment))
        ):
            raise ValueError
        _ = parsed.port
    except ValueError:
        raise DomainError("invalid_field", field) from None
    return value


def _items(value, maximum, field):
    if not isinstance(value, list) or len(value) > maximum:
        raise DomainError("invalid_field", field)
    return value


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def normalize_snapshot(value):
    """Validate the complete provider-neutral contract before touching good cache."""
    _object(value, SNAPSHOT_FIELDS)
    result = {
        "student_id": _plain(value["student_id"], "student_id", 160),
        "student_name": _plain(value["student_name"], "student_name", 200, empty=True),
        "timezone": _zone(value["timezone"]),
        "source_url": _url(value["source_url"], "source_url", source=True),
        "coverage_start": _day(value["coverage_start"], "coverage_start"),
        "coverage_end": _day(value["coverage_end"], "coverage_end"),
        "lessons": [],
        "grades": [],
        "absences": [],
    }
    start, end = (
        date.fromisoformat(result["coverage_start"]),
        date.fromisoformat(result["coverage_end"]),
    )
    if not timedelta(0) <= end - start <= timedelta(days=92):
        raise DomainError("invalid_field", "coverage_end")
    for lesson in _items(value["lessons"], MAX_LESSONS, "lessons"):
        _object(lesson, LESSON_FIELDS, field="lessons")
        row = {
            key: _plain(lesson[key], key, cap, empty=key != "id")
            for key, cap in (
                ("id", 160),
                ("subject", 200),
                ("room", 200),
                ("teacher", 200),
                ("topic", 2000),
                ("homework", 4000),
            )
        }
        row.update(
            date=_day(lesson["date"], "date"),
            start=_clock(lesson["start"], "start", empty=True),
            end=_clock(lesson["end"], "end", empty=True),
            estimated_minutes=None
            if lesson["estimated_minutes"] is None
            else _integer(lesson["estimated_minutes"], "estimated_minutes", 1440),
            cancelled=_bool(lesson["cancelled"], "cancelled"),
            replacement=_bool(lesson["replacement"], "replacement"),
            links=sorted(set(_url(link, "links") for link in _items(lesson["links"], 20, "links"))),
            attachments=[],
        )
        if not result["coverage_start"] <= row["date"] <= result["coverage_end"]:
            raise DomainError("invalid_field", "date")
        if row["start"] and row["end"] and row["start"] >= row["end"]:
            raise DomainError("invalid_field", "end")
        for attachment in _items(lesson["attachments"], 20, "attachments"):
            _object(attachment, {"id", "name", "ext", "size"}, field="attachments")
            row["attachments"].append(
                {
                    "id": _plain(attachment["id"], "id", 160),
                    "name": _plain(attachment["name"], "name", 200),
                    "ext": _plain(attachment["ext"], "ext", 16, empty=True),
                    "size": _integer(attachment["size"], "size", 2**53 - 1),
                }
            )
        _unique(row["attachments"], "attachments")
        row["attachments"].sort(key=lambda item: item["id"])
        result["lessons"].append(row)
    for bucket, allowed, cap in (
        ("grades", GRADE_FIELDS, MAX_GRADES),
        ("absences", ABSENCE_FIELDS, MAX_ABSENCES),
    ):
        for item in _items(value[bucket], cap, bucket):
            _object(item, allowed, field=bucket)
            row = {
                "id": _plain(item["id"], "id", 160),
                "date": _day(item["date"], "date", nullable=True),
                "period": _plain(item["period"], "period", 200, empty=True),
                "subject": _plain(item["subject"], "subject", 200, empty=True),
                "comment": _plain(item["comment"], "comment", 1000, empty=True),
            }
            if row["date"] is None and not row["period"]:
                raise DomainError("invalid_field", "period")
            if bucket == "grades":
                row.update(
                    value=_plain(item["value"], "value", 200),
                    kind=_plain(item["kind"], "kind", 200, empty=True),
                )
            result[bucket].append(row)
    for bucket in ("lessons", "grades", "absences"):
        _unique(result[bucket], bucket)
        result[bucket].sort(key=lambda row: (row["date"] or "", row.get("start", ""), row["id"]))
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_SNAPSHOT_BYTES:
        raise DomainError("invalid_field", "snapshot")
    return result


def _unique(rows, field):
    if len({row["id"] for row in rows}) != len(rows):
        raise DomainError("invalid_field", field)


def _sources(state):
    school = state.get("school", {})
    if not isinstance(school, dict) or not isinstance(school.get("online", {}), dict):
        raise DomainError("invalid_field", "school")
    sources = school.get("online", {}).get("sources", {})
    if not isinstance(sources, dict):
        raise DomainError("invalid_field", "sources")
    return sources


def _enabled(state):
    if "school" not in state.get("settings", {}).get("modules", []):
        raise DomainError("module_disabled")


def _actor(state, actor_id, *, owner=False):
    _enabled(state)
    member = state.get("members", {}).get(actor_id)
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") not in ({"owner"} if owner else {*PRIVILEGED, "child"})
    ):
        raise DomainError("forbidden")
    revision(member.get("revision"))
    return member


def _child(state, member_id, member_revision):
    member_id = _plain(member_id, "member", 80)
    child = state.get("members", {}).get(member_id, {})
    if child.get("active") is not True or child.get("role") != "child":
        raise DomainError("unknown_member")
    if revision(member_revision) != revision(child.get("revision")):
        raise DomainError("conflict")
    return child


def _record(state, source_id, expected_revision=None):
    source_id = _plain(source_id, "id", 80)
    source = _sources(state).get(source_id)
    if source is None:
        raise DomainError("not_found")
    if expected_revision is not None and revision(expected_revision) != source["revision"]:
        raise DomainError("conflict")
    return source


def _rules(state, value, member_id, previous=None):
    _object(value, set(RULE_DEFAULTS), set(), "rules")
    result = {**deepcopy(RULE_DEFAULTS), **deepcopy(previous or {}), **value}
    _bool(result["enabled"], "enabled")
    _bool(result["notify_changes"], "notify_changes")
    _clock(result["homework_time"], "homework_time")
    recipients = [
        _plain(recipient, "recipients", 80)
        for recipient in _items(result["recipients"], 16, "recipients")
    ]
    for recipient in recipients:
        member = state["members"].get(recipient, {})
        if member.get("active") is not True or not (
            member.get("role") in PRIVILEGED
            or (recipient == member_id and member.get("role") == "child")
        ):
            raise DomainError("forbidden")
    result["recipients"] = sorted(set(recipients))
    return result


def _configuration(source):
    return {key: deepcopy(source[key]) for key in CONFIG_FIELDS if key in source}


def handle(ctx, action, payload):
    """Canonical command handler; configuration authority is never payload-supplied."""
    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")
    if action == "homework_ack":
        return _acknowledge(ctx, payload)
    _actor(ctx.state, ctx.actor_id, owner=True)
    if action == "source_disable":
        fields(payload, {"id", "revision"}, {"id", "revision"})
        source = _record(ctx.state, payload["id"], revision(payload["revision"]))
        next_revision = revision(source["revision"] + 1)
        source.update(
            enabled=False, revision=next_revision, updated_at=ctx.now.isoformat(), status="disabled"
        )
        return _configuration(source)
    if action != "source_save":
        raise DomainError("unknown_action")
    return _save_source(ctx, payload)


def _save_source(ctx, payload, *, assigned_id=None):
    """Shared validated state transform, called only after adapter authorization."""
    fields(payload, CONFIG_FIELDS, CONFIG_REQUIRED)
    if ("id" in payload) != ("revision" in payload):
        raise DomainError("invalid_field", "revision")
    child = _child(ctx.state, payload["member"], payload["member_revision"])
    previous = (
        _record(ctx.state, payload["id"], revision(payload["revision"]))
        if "id" in payload
        else None
    )
    if previous is None and len(_sources(ctx.state)) >= MAX_SOURCES:
        raise DomainError("capacity_exceeded")
    provider = _plain(payload["provider"], "provider", 40)
    if provider != "respublika":
        raise DomainError("invalid_field", "provider")
    config = {
        "member": child["id"],
        "member_revision": child["revision"],
        "provider": provider,
        "student_id": _plain(payload["student_id"], "student_id", 160),
        "generation": _plain(payload["generation"], "generation", 80),
        "label": _plain(payload["label"], "label", 200),
        "timezone": _zone(payload["timezone"]),
        "enabled": _bool(payload.get("enabled", True), "enabled"),
    }
    identity_fields = (
        "member",
        "member_revision",
        "student_id",
        "provider",
        "timezone",
        "generation",
    )
    reset = previous is None or any(previous[key] != config[key] for key in identity_fields)
    if (
        previous
        and previous["generation"] == config["generation"]
        and any(
            previous[key] != config[key] for key in ("member", "student_id", "provider", "timezone")
        )
    ):
        raise DomainError("conflict")
    config["rules"] = _rules(
        ctx.state, payload.get("rules", {}), child["id"], None if reset else previous["rules"]
    )
    source = deepcopy(previous) if previous else {}
    source.update(
        config,
        revision=revision(previous["revision"] + 1) if previous else 1,
        updated_at=ctx.now.isoformat(),
    )
    if reset:
        source.update(
            snapshot=None,
            snapshot_hash=None,
            last_attempt=None,
            last_success=None,
            changes=[],
            change_sequence=0,
            acknowledgements={},
            status="pending",
        )
    if not config["enabled"]:
        source["status"] = "disabled"
    elif previous and not previous["enabled"]:
        source["status"] = "pending"
    if previous is None:
        source["id"] = assigned_id or ctx.identifier("OS")
        while not assigned_id and source["id"] in _sources(ctx.state):
            source["id"] = ctx.identifier("OS")
        source["created_at"] = ctx.now.isoformat()
    ctx.state.setdefault("school", {}).setdefault("online", {}).setdefault("sources", {})[
        source["id"]
    ] = source
    return _configuration(source)


def sync_bindings(ctx, options):
    """Reconcile a newer, guarded native Options envelope without copying secrets.

    ``options.online_school`` is {revision: positive int, sources: {OSid: record}}.
    The adapter must additionally fence the exact current Options digest inside
    Engine's lock. An unchanged Options generation never revives a canonical
    disable/rebind. A newly reviewed generation is explicit reauthorization.
    """
    if "school" not in ctx.state.get("settings", {}).get("modules", []):
        return {"applied": False, "sources": []}
    if not isinstance(options, dict) or "online_school" not in options:
        return {"applied": False, "sources": []}
    envelope = _object(options["online_school"], {"revision", "sources"}, field="online_school")
    incoming_revision = revision(envelope["revision"])
    online = ctx.state.get("school", {}).get("online", {})
    previous_revision = online.get("options_revision", 0)
    if incoming_revision <= previous_revision:
        return {"applied": False, "sources": []}
    records = envelope["sources"]
    if not isinstance(records, dict) or len(records) > MAX_SOURCES:
        raise DomainError("invalid_field", "sources")
    for source_id, record in records.items():
        if not isinstance(source_id, str) or not re.fullmatch(r"OS[A-Za-z0-9]{1,78}", source_id):
            raise DomainError("invalid_field", "id")
        if not isinstance(record, dict) or record.get("id", source_id) != source_id:
            raise DomainError("invalid_field", "sources")
    # Use a detached school bucket to keep this helper itself atomic on validation
    # failures. Other school records are retained exactly, never reinterpreted.
    working = {**ctx.state, "school": deepcopy(ctx.state.get("school", {}))}
    scoped = Context(working, ctx.actor, ctx.now, ctx.operation_id)
    changed = []
    for source_id, record in sorted(records.items()):
        previous = _sources(working).get(source_id)
        generation = _plain(record.get("generation"), "generation", 80)
        if previous and generation in {
            previous.get("options_generation"),
            previous["generation"],
        }:
            continue
        payload = {key: record[key] for key in CONFIG_FIELDS - {"id", "revision"} if key in record}
        if previous:
            payload.update(id=source_id, revision=previous["revision"])
        try:
            _child(working, record.get("member"), record.get("member_revision"))
        except DomainError:
            # A saved Options binding is not consent to a later member identity.
            # Retain its last cache privately; current_source/view already hide it.
            if previous and previous["enabled"]:
                previous.update(
                    enabled=False,
                    revision=revision(previous["revision"] + 1),
                    status="disabled",
                    updated_at=ctx.now.isoformat(),
                )
                changed.append(_configuration(previous))
            continue
        saved = _save_source(scoped, payload, assigned_id=source_id)
        _sources(working)[source_id]["options_generation"] = generation
        changed.append(saved)
    for source_id, source in _sources(working).items():
        if (
            source_id not in records
            and source.get("options_generation") is not None
            and source["enabled"]
        ):
            source.update(
                enabled=False,
                revision=revision(source["revision"] + 1),
                status="disabled",
                updated_at=ctx.now.isoformat(),
            )
            changed.append(_configuration(source))
    working.setdefault("school", {}).setdefault("online", {})["options_revision"] = (
        incoming_revision
    )
    ctx.state["school"] = working["school"]
    return {"applied": True, "sources": changed}


def current_source(state, source_id, generation, member_revision):
    """An exact live binding, or None; stale background work has no authority."""
    try:
        _enabled(state)
        source = _record(state, source_id)
        if source.get("enabled") is not True or source.get("generation") != generation:
            return None
        if revision(member_revision) != source["member_revision"]:
            return None
        _child(state, source["member"], member_revision)
        return source
    except DomainError:
        return None


def homework_fingerprint(lesson):
    return _digest(
        {
            key: lesson[key]
            for key in (
                "id",
                "date",
                "subject",
                "topic",
                "homework",
                "estimated_minutes",
                "links",
                "attachments",
            )
        }
    )


def _facts(kind, row):
    if row is None:
        return None
    keys = (
        ("date", "subject", "homework", "topic", "estimated_minutes")
        if kind == "homework"
        else ("date", "start", "end", "subject", "room", "teacher", "cancelled", "replacement")
        if kind == "lesson"
        else ("date", "period", "subject", "value", "comment", "kind")
    )
    return {key: deepcopy(row[key]) for key in keys}


def _changes(source, previous, current, now):
    changes = []
    for kind, bucket in (("lesson", "lessons"), ("homework", "lessons"), ("grade", "grades")):
        old = {row["id"]: row for row in previous[bucket]}
        for row in current[bucket]:
            before = old.get(row["id"])
            if kind == "homework":
                if not row["homework"] and not (before and before["homework"]):
                    continue
                same = before is not None and homework_fingerprint(before) == homework_fingerprint(
                    row
                )
            else:
                same = before is not None and _facts(kind, before) == _facts(kind, row)
            if same:
                continue
            sequence = source["change_sequence"] + len(changes) + 1
            after_facts, before_facts = _facts(kind, row), _facts(kind, before)
            changes.append(
                {
                    "id": _digest(
                        [
                            source["id"],
                            source["generation"],
                            sequence,
                            kind,
                            row["id"],
                            before_facts,
                            after_facts,
                        ]
                    ),
                    "kind": kind,
                    "change": "changed"
                    if before is not None and (kind != "homework" or before["homework"])
                    else "new",
                    "record_id": row["id"],
                    "at": now.isoformat(),
                    "before": before_facts,
                    "after": after_facts,
                }
            )
    return changes


def _newer(source, now):
    return source.get("last_attempt") is None or now > timestamp(
        source["last_attempt"], "last_attempt"
    )


def apply_snapshot(state, source_id, generation, member_revision, snapshot, now):
    """Replace only a validated complete cache. Baseline and replay are silent."""
    now = timestamp(now, "now")
    source = current_source(state, source_id, generation, member_revision)
    if source is None or not _newer(source, now):
        return {"applied": False, "baseline": False, "changes": []}
    normalized = normalize_snapshot(snapshot)
    if normalized["student_id"] != source["student_id"]:
        raise DomainError("online_school_student_mismatch")
    if normalized["timezone"] != source["timezone"]:
        raise DomainError("online_school_invalid_response")
    baseline = source.get("snapshot") is None
    changes = [] if baseline else _changes(source, source["snapshot"], normalized, now)
    current_lessons = {row["id"]: row for row in normalized["lessons"] if row["homework"]}
    acknowledgements = {
        key: item
        for key, item in source.get("acknowledgements", {}).items()
        if key in current_lessons
        and item["homework_hash"] == homework_fingerprint(current_lessons[key])
    }
    source.update(
        snapshot=normalized,
        snapshot_hash=_digest(normalized),
        last_attempt=now.isoformat(),
        last_success=now.isoformat(),
        status="ready",
        acknowledgements=acknowledgements,
        changes=(source.get("changes", []) + changes)[-MAX_CHANGES:],
        change_sequence=source.get("change_sequence", 0) + len(changes),
    )
    return {"applied": True, "baseline": baseline, "changes": deepcopy(changes[-MAX_CHANGES:])}


def record_failure(state, source_id, generation, member_revision, code, now):
    """Record only stable failure codes; never raw provider exceptions or bodies."""
    now = timestamp(now, "now")
    source = current_source(state, source_id, generation, member_revision)
    if source is None or not _newer(source, now):
        return {"applied": False, "status": None}
    if not isinstance(code, str) or code not in FAILURES:
        raise DomainError("invalid_field", "status")
    source.update(last_attempt=now.isoformat(), status=code)
    return {"applied": True, "status": code}


def _authorized_source(state, actor_id, source_id):
    actor = _actor(state, actor_id)
    source = _record(state, source_id)
    if actor["role"] == "child" and source["member"] != actor_id:
        raise DomainError("forbidden")
    if current_source(state, source_id, source["generation"], source["member_revision"]) is None:
        raise DomainError("conflict")
    return source


def _acknowledge(ctx, payload):
    allowed = {
        "id",
        "revision",
        "member_revision",
        "lesson_id",
        "homework_hash",
        "ack_revision",
        "done",
    }
    fields(payload, allowed, allowed)
    source = _authorized_source(ctx.state, ctx.actor_id, payload["id"])
    if (
        revision(payload["revision"]) != source["revision"]
        or revision(payload["member_revision"]) != source["member_revision"]
    ):
        raise DomainError("conflict")
    lesson_id = _plain(payload["lesson_id"], "lesson_id", 160)
    lesson = next(
        (
            row
            for row in (source.get("snapshot") or {}).get("lessons", [])
            if row["id"] == lesson_id
        ),
        None,
    )
    if (
        lesson is None
        or not lesson["homework"]
        or homework_fingerprint(lesson) != payload["homework_hash"]
    ):
        raise DomainError("conflict")
    done = _bool(payload["done"], "done")
    previous = source["acknowledgements"].get(lesson_id)
    if payload["ack_revision"] is None:
        if previous is not None:
            raise DomainError("conflict")
    elif previous is None or revision(payload["ack_revision"]) != previous["revision"]:
        raise DomainError("conflict")
    record = {
        "lesson_id": lesson_id,
        "homework_hash": payload["homework_hash"],
        "done": done,
        "revision": revision(previous["revision"] + 1) if previous else 1,
        "member": source["member"],
        "member_revision": source["member_revision"],
        "updated_at": ctx.now.isoformat(),
        "updated_by": ctx.actor_id,
    }
    source["acknowledgements"][lesson_id] = record
    return {"id": source["id"], "generation": source["generation"], **deepcopy(record)}


def authorize_replay(state, actor_id, action, payload, result, now):
    """A receipt cannot restore a revoked role, source binding or old assignment."""
    timestamp(now, "now")
    if action in {"source_save", "source_disable"}:
        _actor(state, actor_id, owner=True)
        return
    if action != "homework_ack":
        raise DomainError("unknown_action")
    source = _authorized_source(state, actor_id, payload["id"])
    if (
        source["generation"] != result.get("generation")
        or source["member"] != result.get("member")
        or source["member_revision"] != result.get("member_revision")
    ):
        raise DomainError("conflict")
    current = source["acknowledgements"].get(payload["lesson_id"])
    if current is None or current != {
        key: value for key, value in result.items() if key not in {"id", "generation"}
    }:
        raise DomainError("conflict")


def view(state, actor_id, now=None):
    """Freshly authorize every projection. Disabled/stale identities reveal no cache."""
    now = timestamp(now, "now") if now is not None else None
    try:
        actor = _actor(state, actor_id)
    except DomainError:
        return {"sources": []}
    result = []
    for source in _sources(state).values():
        if actor["role"] == "child" and source["member"] != actor_id:
            continue
        try:
            _child(state, source["member"], source["member_revision"])
        except DomainError:
            continue
        if actor["role"] == "child" and not source["enabled"]:
            continue
        item = _configuration(source)
        item.pop("generation", None)
        if actor["role"] == "child":
            item["rules"] = {
                key: deepcopy(value) for key, value in item["rules"].items() if key != "recipients"
            }
        success = (
            timestamp(source["last_success"], "last_success")
            if source.get("last_success")
            else None
        )
        stale = (
            now is None
            or source["status"] != "ready"
            or success is None
            or now < success
            or now - success > FRESH_FOR
        )
        item.update(
            status=source["status"],
            last_attempt=source.get("last_attempt"),
            last_success=source.get("last_success"),
            stale=stale,
            snapshot=deepcopy(source.get("snapshot")) if source["enabled"] else None,
            changes=deepcopy(source.get("changes", [])) if source["enabled"] else [],
            acknowledgements=deepcopy(source.get("acknowledgements", {}))
            if source["enabled"]
            else {},
        )
        for ack in item["acknowledgements"].values():
            ack.pop("updated_by", None)
        if item["snapshot"]:
            for lesson in item["snapshot"]["lessons"]:
                lesson["homework_hash"] = homework_fingerprint(lesson)
        result.append(item)
    return {"sources": result}
