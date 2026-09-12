"""Check explicit legacy cross-ledger receipts without repairing or executing them.

Matching receipts are necessary, not proof of a coherent live capture. Unknown
history must be reviewed; this module never guesses a child from a display name.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime

from .preflight import _text
from .review import LegacyReview

_PREFIX = "automatic task control: "
_TASK = re.compile(r"task:(T[0-9]{6,12}):missed:(\d{4}-\d{2}-\d{2})")
_ALARM = re.compile(r"alarm:(.+):(\d{4}-\d{2}-\d{2}):missed")


class SourceLinkError(ValueError):
    """Fixed code only; source identities and notes are never error text."""


def _date(value):
    try:
        return type(value) is str and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _stamp(value):
    if type(value) is not str:
        raise ValueError
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError
    return parsed


def inspect_source_links(review: LegacyReview, *, members=None):
    """Counts-only two-sided task/alarm penalty and correction checks.

    Manual Court decisions are outside these automatic-effect links. Old alarm
    events outside the current Court period may lack pruned runs; those are counted
    as archive-only, never described as verified. Task history is not pruned by the
    legacy ledger, so missing task counterparts always require review.
    """
    if type(review) is not LegacyReview or not review.matches_members(members):
        raise SourceLinkError("source_link_review_changed")
    try:
        return _inspect(review)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        raise SourceLinkError("source_link_shape_invalid") from None


def _inspect(review):
    assistant, court, mapping = review.private_data()
    ledger = assistant.get("ledger", assistant)
    issues = Counter()
    automatic, rollovers, requests, acknowledgements = {}, {}, {}, {}
    assignees = {}

    def issue(code):
        issues[code] += 1

    def member(key):
        binding = mapping.get(key) if type(key) is str else None
        return binding.get("member_id") if type(binding) is dict else None

    for row in court["history"]:
        original = row.get("original_text")
        prefixed = type(original) is str and original.startswith(_PREFIX)
        if not prefixed:
            if type(row.get("parent_user_id")) is int and row["parent_user_id"] == 0:
                issue("automatic_source_unknown")
            continue
        key = original[len(_PREFIX) :]
        task, alarm = _TASK.fullmatch(key), _ALARM.fullmatch(key)
        match = task or alarm
        if (
            type(row.get("parent_user_id")) is not int
            or row["parent_user_id"] != 0
            or row.get("type") != "minus"
            or type(row.get("delta")) is not int
            or row["delta"] != -1
            or row.get("telegram_message_id") != f"system:{key}"
            or match is None
            or not _date(match[2])
            or not _text(row.get("week_id"), 128)
        ):
            issue("automatic_source_invalid")
            continue
        if key in automatic:
            issue("automatic_source_duplicate")
            continue
        automatic[key] = ("task" if task else "alarm", match[1], match[2], row)

    for event in ledger["history"]:
        kind, task_id, details = event.get("type"), event["task_id"], event.get("details")
        if type(details) is not dict:
            if kind in {
                "missed_and_rolled_over",
                "court_correction_requested",
                "court_correction_applied",
            }:
                issue("task_effect_details_invalid")
            continue
        if kind == "created":
            assignees[task_id] = None if task_id in assignees else details.get("assignee")
        elif kind == "revised":
            previous, current = details.get("previous"), details.get("current")
            if type(previous) is dict and type(current) is dict:
                if "assignee" in previous or "assignee" in current:
                    if (
                        "assignee" in previous
                        and "assignee" in current
                        and previous["assignee"] == assignees.get(task_id)
                    ):
                        assignees[task_id] = current["assignee"]
                    else:
                        assignees[task_id] = None
            else:
                assignees[task_id] = None

        elif kind == "missed_and_rolled_over":
            day = details.get("missed_date")
            expected = f"task:{task_id}:missed:{day}"
            key = details.get("court_source_key") or expected
            if (
                not _date(day)
                or key != expected
                or type(details.get("court_delta")) is not int
                or details["court_delta"] != -1
                or event.get("actor") != "system"
                or ledger["tasks"][task_id]["kind"] != "task"
                or member(assignees.get(task_id)) is None
            ):
                issue("task_penalty_link_invalid")
                continue
            if key in rollovers:
                issue("task_penalty_link_duplicate")
            else:
                rollovers[key] = (task_id, member(assignees[task_id]))
        elif kind in {"completed", "court_correction_requested", "court_correction_applied"}:
            key = details.get(
                "court_correction_source_key" if kind == "completed" else "source_key"
            )
            if key is None and kind == "completed":
                continue
            match = _TASK.fullmatch(key) if type(key) is str else None
            if match is None or match[1] != task_id or not _date(match[2]):
                issue("task_correction_link_invalid")
                continue
            pair = (task_id, key)
            if kind == "court_correction_applied":
                if (
                    pair not in requests
                    or event.get("actor") != "system"
                    or type(details.get("court_delta_reversed")) is not int
                    or details["court_delta_reversed"] != 1
                ):
                    issue("task_correction_ack_invalid")
                    continue
                if pair in acknowledgements:
                    issue("task_correction_ack_duplicate")
                acknowledgements[pair] = event["sequence"]
            else:
                requests.setdefault(pair, event["sequence"])

    runs = assistant.get("alarms", {}).get("runs", {}) if "ledger" in assistant else {}
    alarm_links = {}
    for run in runs.values():
        if not _date(run.get("date")):
            if run.get("penalty_applied_at") is not None:
                issue("alarm_penalty_link_invalid")
            # Historical unpenalized archive rows need no automatic-effect link.
            continue
        try:
            if _stamp(run["scheduled_at"]).date().isoformat() != run["date"]:
                raise ValueError
            if run.get("penalty_applied_at") is not None and _stamp(
                run["penalty_applied_at"]
            ) < _stamp(run["scheduled_at"]):
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            issue("alarm_penalty_link_invalid")
            continue
        key = f"alarm:{run['child']}:{run['date']}:missed"
        if key in alarm_links:
            issue("alarm_link_duplicate")
        alarm_links[key] = run
        if run.get("penalty_applied_at") is not None and key not in automatic:
            issue("alarm_penalty_without_court")

    matched_tasks = matched_alarms = archive_only = 0
    for key, (kind, subject, _day, row) in automatic.items():
        if kind == "task":
            linked = rollovers.get(key)
            if linked is None:
                issue("court_penalty_without_task")
            elif linked[1] != member(row["child"]):
                issue("task_penalty_member_mismatch")
            else:
                matched_tasks += 1
        else:
            if member(subject) is None or member(subject) != member(row["child"]):
                issue("alarm_penalty_member_mismatch")
                continue
            run = alarm_links.get(key)
            if run is None:
                if row["week_id"] == court["week_id"]:
                    issue("court_penalty_without_alarm")
                else:
                    archive_only += 1
            elif run.get("penalty_applied_at") is None:
                issue("alarm_penalty_not_acknowledged")
            elif member(run["child"]) != member(row["child"]):
                issue("alarm_penalty_member_mismatch")
            else:
                matched_alarms += 1
    for key in rollovers:
        if key not in automatic:
            issue("task_penalty_without_court")
    for pair in requests:
        row = automatic.get(pair[1])
        if pair not in acknowledgements:
            issue("task_correction_pending")
        elif pair[1] not in rollovers or row is None or row[3].get("cancelled") is not True:
            issue("task_correction_without_reversal")
    return {
        "mode": "legacy_effect_link_review",
        "task_penalties_matched": matched_tasks,
        "alarm_penalties_matched": matched_alarms,
        "corrections_checked": len(requests),
        "pruned_alarm_events_archive_only": archive_only,
        "issues": [{"code": code, "count": count} for code, count in sorted(issues.items())],
        "coherence_verified": False,
        "activation_available": False,
    }
