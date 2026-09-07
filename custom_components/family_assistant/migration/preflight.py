"""Bounded, counts-only inspection of legacy domain data without normalizing it.

This is deliberately not a converter. It has no filesystem, HA, provider or
Engine dependency and never returns source text, identities or transport data.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime

MAX_NODES = 100_000
MAX_DEPTH = 32
MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT = 65_536
STATES = frozenset(
    {
        "assigned",
        "pending_approval",
        "accepted",
        "in_progress",
        "submitted",
        "needs_changes",
        "completed",
        "overdue",
        "cancelled",
        "archived",
    }
)
KINDS = frozenset({"task", "reminder", "shopping"})
PERIODS = frozenset({"weekday", "weekend"})


def _bounded_json(root):
    """Iterative traversal: reject cycles and bound work before serialization."""
    stack = [(root, 0, False)]
    active = set()
    nodes = size = 0
    while stack:
        value, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(value))
            continue
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            return False
        kind = type(value)
        if kind in {dict, list}:
            if id(value) in active or len(value) > MAX_NODES - nodes:
                return False
            active.add(id(value))
            stack.append((value, depth, True))
            size += 2 + len(value)
            if kind is dict:
                for key, child in value.items():
                    if type(key) is not str:
                        return False
                    stack.append((child, depth + 1, False))
                    stack.append((key, depth + 1, False))
            else:
                stack.extend((child, depth + 1, False) for child in value)
        elif kind is str:
            if len(value) > MAX_TEXT:
                return False
            try:
                # Conservative JSON escaping bound, including control characters.
                size += len(value.encode("utf-8")) * 6 + 2
            except UnicodeEncodeError:
                return False
        elif value is None or kind is bool:
            size += 5
        elif kind in {int, float}:
            if (kind is int and abs(value) > 2**53 - 1) or (
                kind is float and not math.isfinite(value)
            ):
                return False
            size += 32
        else:
            return False
        if size > MAX_BYTES:
            return False
    return True


def _text(value, maximum=500):
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**53 - 1


def _quantity(value, minimum):
    return type(value) in {int, float} and math.isfinite(value) and minimum <= value <= 100000


class _Inspection:
    def __init__(self, known_members):
        self.known_members = known_members
        self.unmapped = set()
        self.issues = Counter()
        self.counts = {
            "tasks": 0,
            "reminders": 0,
            "shopping": 0,
            "task_history": 0,
            "task_receipts": 0,
            "alarm_schedules": 0,
            "enabled_alarm_schedules": 0,
            "alarm_runs": 0,
            "court_events": 0,
            "court_archived_weeks": 0,
            "court_receipts": 0,
        }

    def member(self, value, *, optional=False):
        if optional and value is None:
            return
        if not _text(value, 128):
            self.issues["invalid_member_reference"] += 1
        elif value not in self.known_members:
            self.unmapped.add(value)

    def stamp(self, value):
        try:
            if type(value) is not str:
                raise ValueError
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                self.issues["naive_timestamp"] += 1
        except (TypeError, ValueError, OverflowError):
            self.issues["invalid_timestamp"] += 1

    def ledger(self, ledger):
        if (
            type(ledger) is not dict
            or type(ledger.get("schema_version")) is not int
            or ledger["schema_version"] != 1
        ):
            self.issues["unsupported_task_schema"] += 1
            return
        tasks, history, receipts = (
            ledger.get(k) for k in ("tasks", "history", "processed_commands")
        )
        if type(tasks) is not dict or type(history) is not list or type(receipts) is not dict:
            self.issues["invalid_task_buckets"] += 1
            return
        self.counts["task_history"] = len(history)
        self.counts["task_receipts"] = len(receipts)
        for key in ("next_task_sequence", "next_event_sequence"):
            if not _integer(ledger.get(key), 1):
                self.issues["invalid_task_sequence"] += 1
        for task_id, row in tasks.items():
            if type(row) is not dict or not _text(task_id, 128) or row.get("task_id") != task_id:
                self.issues["invalid_task_record"] += 1
                continue
            kind = row.get("kind")
            if type(kind) is not str or kind not in KINDS:
                self.issues["unsupported_task_kind"] += 1
            else:
                self.counts[
                    {"task": "tasks", "reminder": "reminders", "shopping": "shopping"}[kind]
                ] += 1
            state = row.get("state")
            if type(state) is not str or state not in STATES:
                self.issues["unsupported_task_status"] += 1
            if not _text(row.get("title")):
                self.issues["invalid_task_title"] += 1
            self.member(row.get("creator"))
            self.member(row.get("assignee"), optional=kind == "shopping")
            self.member(row.get("reviewer"), optional=True)
            if kind == "reminder" and row.get("creator") != row.get("assignee"):
                self.issues["private_reminder_owner_mismatch"] += 1
            self.stamp(row.get("created_at"))
            self.stamp(row.get("due_at"))
            metadata = row.get("metadata")
            if type(metadata) is not dict:
                self.issues["invalid_task_metadata"] += 1
            elif kind == "shopping":
                quantity = metadata.get("shopping_quantity")
                remaining = metadata.get("shopping_remaining_quantity")
                valid_quantity = quantity is None or (_quantity(quantity, 0) and quantity > 0)
                valid_remaining = remaining is None or _quantity(remaining, 0)
                if (
                    not valid_quantity
                    or not valid_remaining
                    or (
                        remaining is not None
                        and (quantity is None or (valid_quantity and remaining > quantity))
                    )
                ):
                    self.issues["invalid_shopping_quantity"] += 1
                unit = metadata.get("shopping_unit")
                if unit is not None and not _text(unit, 20):
                    self.issues["invalid_shopping_unit"] += 1
                if metadata.get("shopping_approval") not in ("pending", "approved", "rejected"):
                    self.issues["invalid_shopping_approval"] += 1
        previous = 0
        for event in history:
            if type(event) is not dict:
                self.issues["invalid_task_event"] += 1
                continue
            sequence = event.get("sequence")
            if not _integer(sequence, 1) or sequence <= previous:
                self.issues["invalid_history_sequence"] += 1
            else:
                previous = sequence
            reference = event.get("task_id")
            if type(reference) is not str or reference not in tasks:
                self.issues["broken_task_reference"] += 1
            self.member(event.get("actor"))
            self.stamp(event.get("at"))
        if (
            _integer(ledger.get("next_event_sequence"), 1)
            and ledger["next_event_sequence"] <= previous
        ):
            self.issues["invalid_task_sequence"] += 1

    def alarms(self, data):
        if (
            type(data) is not dict
            or type(data.get("schedules", {})) is not dict
            or type(data.get("runs", {})) is not dict
        ):
            self.issues["invalid_alarm_buckets"] += 1
            return
        for member, periods in data.get("schedules", {}).items():
            self.member(member)
            if type(periods) is not dict or periods.keys() - PERIODS:
                self.issues["invalid_alarm_schedule"] += 1
                continue
            for schedule in periods.values():
                self.counts["alarm_schedules"] += 1
                if (
                    type(schedule) is not dict
                    or type(schedule.get("enabled")) is not bool
                    or type(schedule.get("time")) is not str
                    or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule["time"])
                ):
                    self.issues["invalid_alarm_schedule"] += 1
                elif schedule["enabled"]:
                    self.counts["enabled_alarm_schedules"] += 1
        self.counts["alarm_runs"] = len(data.get("runs", {}))
        for row in data.get("runs", {}).values():
            if type(row) is not dict:
                self.issues["invalid_alarm_run"] += 1
                continue
            self.member(row.get("child"))
            self.stamp(row.get("scheduled_at"))
            if not row.get("confirmed_at") and not row.get("cancelled_at"):
                self.issues["active_alarm_runs"] += 1

    def court(self, data):
        if (
            type(data) is not dict
            or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1
        ):
            self.issues["unsupported_court_schema"] += 1
            return
        children, history, weeks, receipts = (
            data.get(k) for k in ("children", "history", "archived_weeks", "processed_messages")
        )
        if (
            type(children) is not dict
            or type(history) is not list
            or type(weeks) is not list
            or type(receipts) is not dict
            or not _text(data.get("week_id"), 128)
        ):
            self.issues["invalid_court_buckets"] += 1
            return
        self.counts.update(
            court_events=len(history), court_archived_weeks=len(weeks), court_receipts=len(receipts)
        )
        totals = {member: {"pluses": 0, "minuses": 0} for member in children}
        seen = set()
        for row in history:
            if type(row) is not dict:
                self.issues["invalid_court_event"] += 1
                continue
            self.member(row.get("child"))
            self.stamp(row.get("timestamp"))
            event_id = row.get("event_id")
            kind = row.get("type")
            if not _text(event_id, 128) or event_id in seen:
                self.issues["invalid_court_event_id"] += 1
            else:
                seen.add(event_id)
            delta = row.get("delta")
            if (
                kind not in ("plus", "minus")
                or type(delta) is not int
                or delta != (1 if kind == "plus" else -1)
                or type(row.get("cancelled")) is not bool
            ):
                self.issues["invalid_court_event"] += 1
                continue
            member = row.get("child")
            if type(member) is not str or member not in totals:
                self.issues["broken_court_reference"] += 1
            elif row.get("week_id") == data["week_id"] and not row["cancelled"]:
                totals[member]["pluses" if kind == "plus" else "minuses"] += 1
        for member, values in children.items():
            self.member(member)
            if type(values) is not dict or not all(
                _integer(values.get(k)) for k in ("pluses", "minuses")
            ):
                self.issues["invalid_court_counter"] += 1
            elif any(values[k] != totals[member][k] for k in ("pluses", "minuses")):
                self.issues["court_balance_mismatch"] += 1


def inspect_legacy(assistant, court, known_members: set[str]) -> dict:
    """Return only inventory counts and blockers; never an import-ready state."""
    report = {"mode": "preflight_only", "conversion_available": False, "counts": {}, "issues": []}
    if (
        type(known_members) is not set
        or len(known_members) > 512
        or not all(_text(v, 128) for v in known_members)
    ):
        report["issues"] = [{"code": "invalid_member_mapping", "count": 1}]
        return report
    if not _bounded_json(assistant) or not _bounded_json(court):
        report["issues"] = [{"code": "source_json_limits", "count": 1}]
        return report
    inspector = _Inspection(known_members)
    envelope = type(assistant) is dict and "ledger" in assistant
    inspector.ledger(assistant["ledger"] if envelope else assistant)
    if envelope:
        inspector.alarms(assistant.get("alarms", {}))
    inspector.court(court)
    if inspector.unmapped:
        inspector.issues["unmapped_members"] = len(inspector.unmapped)
    report["counts"] = inspector.counts
    report["issues"] = [
        {"code": code, "count": count} for code, count in sorted(inspector.issues.items())
    ]
    return report
