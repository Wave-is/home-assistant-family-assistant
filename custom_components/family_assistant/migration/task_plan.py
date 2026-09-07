"""Pure task-record proposals; preserve unknown values instead of guessing."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from .preflight import _text
from .review import LegacyReview
from .task_progress import project_overdue_progress
from .task_reports import (
    ReportHistoryError,
    project_text_history,
    project_unreported_history,
    project_unsubmitted_photo_history,
)

SUPPORTED_STATES = frozenset(
    {"assigned", "accepted", "in_progress", "completed", "cancelled", "archived"}
)
OVERDUE_FROM_STATES = frozenset({"assigned", "accepted", "in_progress"})


class TaskPlanError(ValueError):
    """Fixed code only; no source fields or underlying exceptions."""


def _encode(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, repr=False)
class TaskPlan:
    """A private frozen proposal, not an import capability or a family view."""

    _summary: bytes = field(repr=False)
    _private_payload: bytes = field(repr=False)

    def __repr__(self) -> str:
        return "TaskPlan(private=True, import_available=False)"

    def summary(self) -> dict:
        return json.loads(self._summary)

    def private_data(self) -> dict:
        return json.loads(self._private_payload)


def _record(row: dict, mapping: dict, history: list, members: dict) -> dict:
    kind = row.get("kind")
    if kind not in {"task", "reminder"}:
        raise TaskPlanError("task_kind_unsupported")

    if not _text(row.get("title"), 500):
        raise TaskPlanError("task_title_unsupported")

    requires_report = row.get("requires_report")
    if type(requires_report) is not bool:
        raise TaskPlanError("task_report_settings_unsupported")

    report_type = row.get("report_type")
    report_projection = None
    if requires_report:
        if type(report_type) is str and report_type in {"text", "photo"}:
            try:
                projector = (
                    project_text_history
                    if report_type == "text"
                    else project_unsubmitted_photo_history
                )
                report_projection = projector(row, history, mapping, members)
            except ReportHistoryError as error:
                raise TaskPlanError(str(error)) from None
        else:
            raise TaskPlanError("task_report_settings_unsupported")

    # A no-report record must not silently lose a separate reviewer authority.
    if not requires_report and row.get("reviewer") is not None:
        raise TaskPlanError("task_report_review_required")

    # No-report notes must be reconstructed from explicit terminal events, never
    # relabelled as a submitted report from the overloaded last_note projection.
    lifecycle_notes = {}
    if not requires_report and report_type is not None:
        raise TaskPlanError("task_report_settings_unsupported")
    if not requires_report and row.get("submitted_at") is not None:
        raise TaskPlanError("task_report_settings_unsupported")
    if not requires_report and row.get("last_note") is not None:
        try:
            lifecycle_notes = project_unreported_history(row, history, mapping, members)
        except ReportHistoryError as error:
            raise TaskPlanError(str(error)) from None

    lifecycle = {}
    for key in ("accepted_at", "started_at", "completed_at", "cancelled_at", "archived_at"):
        value = row.get(key)
        if value is None:
            continue
        try:
            parsed = datetime.fromisoformat(value) if type(value) is str else None
            if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise TaskPlanError("task_lifecycle_timestamp_unsupported") from None
        lifecycle[key] = value

    state = row.get("state")
    supported = SUPPORTED_STATES | ({"submitted", "needs_changes"} if requires_report else set())
    if state == "overdue":
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            raise TaskPlanError("task_overdue_state_unsupported")
        overdue_from = metadata.get("overdue_from_state")
        overdue_states = OVERDUE_FROM_STATES | ({"needs_changes"} if requires_report else set())
        if (overdue_from is None and "overdue_from_state" in metadata) or (
            overdue_from is not None
            and (type(overdue_from) is not str or overdue_from not in overdue_states)
        ):
            raise TaskPlanError("task_overdue_state_unsupported")
        # Legacy acceptance/start while already overdue did not update the saved
        # pre-overdue state. Do not silently rewind subsequently recorded progress.
        if (
            overdue_from is None
            or (overdue_from == "assigned" and "accepted_at" in lifecycle)
            or (overdue_from in {"assigned", "accepted"} and "started_at" in lifecycle)
        ):
            try:
                status = project_overdue_progress(row, history, mapping, members)
            except ReportHistoryError as error:
                raise TaskPlanError(
                    "task_overdue_state_unsupported" if overdue_from is None else str(error)
                ) from None
        else:
            status = overdue_from
    elif state in supported:
        status = state
    else:
        raise TaskPlanError("task_state_unsupported")

    creator_key = row.get("creator")
    if not creator_key or creator_key not in mapping:
        raise TaskPlanError("invalid_member_reference")
    creator = mapping[creator_key]
    if creator.get("archive_only"):
        raise TaskPlanError("invalid_member_reference")

    assignee_key = row.get("assignee")
    if not assignee_key or assignee_key not in mapping:
        raise TaskPlanError("invalid_member_reference")
    assignee = mapping[assignee_key]
    if assignee.get("archive_only"):
        raise TaskPlanError("invalid_member_reference")
    if kind == "reminder" and creator != assignee:
        raise TaskPlanError("invalid_member_reference")

    projected_lifecycle = {
        key: value
        for key, value in lifecycle.items()
        if key in {"accepted_at", "started_at", "archived_at"}
    }
    close_key = {"completed": "completed_at", "cancelled": "cancelled_at"}.get(status)
    if close_key in lifecycle:
        projected_lifecycle["closed_at"] = lifecycle[close_key]
    if status == "archived" and row.get("archived_from_state") is not None:
        previous = row["archived_from_state"]
        if type(previous) is not str or previous not in supported - {"archived"}:
            raise TaskPlanError("task_archive_state_unsupported")
        projected_lifecycle["previous_status"] = previous
        archived_close = {"completed": "completed_at", "cancelled": "cancelled_at"}.get(previous)
        if archived_close in lifecycle:
            projected_lifecycle["closed_at"] = lifecycle[archived_close]

    return {
        "source_task": row["task_id"],
        "target_bindings": {
            "creator": creator,
            "assignee": assignee,
            **({"reviewer": report_projection["reviewer"]} if report_projection else {}),
        },
        **({"review_policy": report_projection["review_policy"]} if report_projection else {}),
        "record": {
            "title": row["title"],
            "creator": creator["member_id"],
            "assignee": assignee["member_id"],
            "assignee_revision": assignee["member_revision"],
            "created_at": row["created_at"],
            "due_at": row.get("due_at"),
            "status": status,
            "report_type": "none",
            "report": None,
            "deadline_policy": {
                "reminder_minutes": 0,
                "grace_minutes": 0,
                "penalty": 0,
            },
            "checklist": [],
            **({"delivery_scope": "personal"} if kind == "reminder" else {}),
            **projected_lifecycle,
            **lifecycle_notes,
            **(report_projection["fields"] if report_projection else {}),
        },
    }


def build_task_plan(review: LegacyReview, *, members=None) -> TaskPlan:
    if type(review) is not LegacyReview:
        raise TaskPlanError("invalid_review")
    if not review.matches_members(members):
        raise TaskPlanError("review_changed")
    assistant, _, mapping = review.private_data()
    ledger = assistant["ledger"] if "ledger" in assistant else assistant
    tasks = ledger.get("tasks", {})
    rows = {key: row for key, row in tasks.items() if row.get("kind") in {"task", "reminder"}}
    archive = {
        "tasks": rows,
        "history": [event for event in ledger.get("history", []) if event.get("task_id") in rows],
    }
    proposals, blocked = [], []
    issues = Counter()
    for identifier, row in sorted(rows.items()):
        try:
            proposals.append(
                _record(
                    row,
                    mapping,
                    [event for event in archive["history"] if event["task_id"] == identifier],
                    members,
                )
            )
        except TaskPlanError as error:
            code = str(error)
            issues[code] += 1
            blocked.append({"source_task": identifier, "code": code})
    private = _encode({"proposals": proposals, "blocked": blocked, "archive": archive})
    stamp = {
        "version": 1,
        "review": review.summary()["fingerprint"],
        "payload": hashlib.sha256(private).hexdigest(),
    }
    summary = {
        "mode": "task_plan_proposal",
        "fingerprint": hashlib.sha256(_encode(stamp)).hexdigest(),
        "review_fingerprint": stamp["review"],
        "source_items_count": len(rows),
        "record_proposals_count": len(proposals),
        "blocked_items_count": len(blocked),
        "archived_history_count": len(archive["history"]),
        "issues": [{"code": code, "count": count} for code, count in sorted(issues.items())],
        "coherence_verified": False,
        "import_available": False,
    }
    return TaskPlan(_encode(summary), private)
