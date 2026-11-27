"""Academy: local assignments, deterministic grading and spaced review."""

import re
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction

from ..const import PRIVILEGED
from . import academy_curriculum as curriculum
from .validation import DomainError, enum, fields, revision, text, timestamp

PASS_STREAK = 3
MAX_ASSIGNMENTS = 200
MAX_ATTEMPTS = 10000
REVIEW_DAYS = (1, 3, 7, 14, 30)


def _bucket(state):
    return state.get("academy", {})


def _require(state, actor):
    if "academy" not in state["settings"]["modules"]:
        raise DomainError("module_disabled")
    if not actor.get("active", True) or actor["role"] not in {*PRIVILEGED, "child"}:
        raise DomainError("forbidden")


def _bound(state, record):
    child = state["members"].get(record["member"], {})
    return (child.get("active", False) and child.get("role") == "child"
            and child.get("revision") == record["member_revision"])


def _record(ctx, record_id):
    record_id = text(record_id, "id", 80)
    record = _bucket(ctx.state).get(record_id)
    if record is None:
        raise DomainError("not_found")
    if not ctx.privileged and (record["member"] != ctx.actor_id or not _bound(ctx.state, record)):
        raise DomainError("forbidden")
    return record


def _next(record, now):
    # Prioritize overdue review, then unfinished topics in the selected course order.
    due = [key for key in record["topics"]
           if record["progress"][key]["due"] is not None
           and timestamp(record["progress"][key]["due"], "due") <= now]
    if due:
        return min(due, key=lambda key: timestamp(record["progress"][key]["due"], "due"))
    return next((key for key in record["topics"]
                 if not record["progress"][key]["mastered"]), None)


def _language(actor, record=None):
    return record["language"] if record else ("uk" if actor.get("language") == "uk" else "en")


def _answer(value):
    value = text(value, "answer", 64).replace("−", "-").replace(",", ".")
    if not re.fullmatch(r"[+-]?(?:[0-9]{1,12}(?:\.[0-9]{1,10})?|[0-9]{1,12}/[0-9]{1,12})", value):
        raise DomainError("invalid_field", "answer")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        raise DomainError("invalid_field", "answer") from None


def handle(ctx, command, payload):
    _require(ctx.state, ctx.actor)
    if command == "assign":
        ctx.require_parent()
        required = {"member", "member_revision", "grade", "language"}
        fields(payload, required | {"topics", "allow_ai"}, required)
        child = ctx.member(payload["member"])
        if child["role"] != "child":
            raise DomainError("invalid_field", "member")
        if revision(payload["member_revision"]) != child["revision"]:
            raise DomainError("conflict")
        grade = payload["grade"]
        if type(grade) is not int or grade not in (6, 7):
            raise DomainError("invalid_field", "grade")
        language = enum(payload["language"], ("uk", "en"), "language")
        allow_ai = payload.get("allow_ai", False)
        if type(allow_ai) is not bool:
            raise DomainError("invalid_field", "allow_ai")
        available = [row[0] for row in curriculum.TOPICS if row[1] == grade]
        topics = payload.get("topics", available)
        if (not isinstance(topics, list) or not topics or len(topics) > len(available)
                or any(not isinstance(key, str) or key not in available for key in topics)
                or len(set(topics)) != len(topics)):
            raise DomainError("invalid_field", "topics")
        bucket = ctx.state.setdefault("academy", {})
        if len(bucket) >= MAX_ASSIGNMENTS:
            raise DomainError("invalid_field", "limit")
        if any(row["member"] == child["id"] and row["grade"] == grade
               and row["active"] and _bound(ctx.state, row) for row in bucket.values()):
            raise DomainError("conflict")
        record_id = ctx.identifier("AC")
        bucket[record_id] = {
            "id": record_id, "member": child["id"], "member_revision": child["revision"],
            "grade": grade, "language": language, "topics": topics[:],
            "curriculum_version": curriculum.VERSION, "active": True, "revision": 1,
            "allow_ai": allow_ai,
            "created_at": ctx.now.isoformat(), "sequence": 0, "history": [],
            "progress": {key: {"attempts": 0, "correct": 0, "streak": 0,
                               "mastered": False, "review": 0, "due": None} for key in topics},
        }
        return {"id": record_id, "revision": 1}
    if command not in {"answer", "archive"}:
        raise DomainError("unknown_action")
    required = {"id", "revision"}
    if command == "answer":
        required |= {"topic", "answer"}
    fields(payload, required, required)
    row = _record(ctx, payload["id"])
    if revision(payload["revision"]) != row["revision"] or not row["active"]:
        raise DomainError("conflict")
    if command == "archive":
        ctx.require_parent()
        row["active"] = False
    else:
        if ctx.actor["role"] != "child" or not _bound(ctx.state, row):
            raise DomainError("forbidden")
        if row["sequence"] >= MAX_ATTEMPTS:
            raise DomainError("invalid_field", "limit")
        topic = _next(row, ctx.now)
        if topic is None or payload["topic"] != topic:
            raise DomainError("conflict")
        _, expected = curriculum.question(topic, row["id"], row["sequence"], row["language"])
        correct = _answer(payload["answer"]) == expected
        item = row["progress"][topic]
        item["attempts"] += 1
        item["correct"] += int(correct)
        if correct:
            item["streak"] += 1
            if item["mastered"]:
                item["review"] = min(item["review"] + 1, len(REVIEW_DAYS) - 1)
            elif item["streak"] >= PASS_STREAK:
                item["mastered"] = True
                item["review"] = 0
            if item["mastered"]:
                item["due"] = (ctx.now + timedelta(days=REVIEW_DAYS[item["review"]])).isoformat()
        else:
            item.update(streak=0, mastered=False, review=0, due=None)
        row["sequence"] += 1
        row["history"] = (row["history"] + [{"topic": topic, "correct": correct,
                                             "at": ctx.now.isoformat()}])[-100:]
    ctx.touch(row)
    # No submitted answer, answer key or lesson text in journal/processed receipts.
    return {"id": row["id"], "revision": row["revision"]}


def authorize_replay(ctx, command, payload, result):
    _require(ctx.state, ctx.actor)
    row = _record(ctx, result["id"])
    if command in {"assign", "archive"}:
        ctx.require_parent()
    elif command == "answer":
        if ctx.actor["role"] != "child" or not row["active"] or not _bound(ctx.state, row):
            raise DomainError("forbidden")
    else:
        raise DomainError("unknown_action")


def project(state, actor, now):
    _require(state, actor)
    parent = actor["role"] in PRIVILEGED
    rows = []
    for row in _bucket(state).values():
        if not parent and (not row["active"] or row["member"] != actor["id"]
                           or not _bound(state, row)):
            continue
        data = deepcopy(row)
        data["bound"] = _bound(state, row)
        data["allow_ai"] = row.get("allow_ai", False)
        data["mastered"] = sum(item["mastered"] for item in row["progress"].values())
        data["attempts"] = sum(item["attempts"] for item in row["progress"].values())
        data["correct"] = sum(item["correct"] for item in row["progress"].values())
        data["question"] = None
        if not parent and row["active"] and (topic := _next(row, now)):
            prompt, _ = curriculum.question(topic, row["id"], row["sequence"], row["language"])
            lesson = next(item for item in curriculum.catalog(row["language"]) if item["id"] == topic)
            data["question"] = {"topic": topic, "prompt": prompt, **lesson}
        rows.append(data)
    return {"assignments": rows, "catalog": curriculum.catalog(_language(actor))}
