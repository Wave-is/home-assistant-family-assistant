"""Reconstruct explicit task history; never guess the meaning of an old note."""

import hashlib
from copy import deepcopy
from datetime import datetime


class ReportHistoryError(ValueError):
    """Fixed review blocker, with no source content or exception details."""


def _fail(code="task_report_history_review_required"):
    raise ReportHistoryError(code)


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(value) if type(value) is str else None
        if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (TypeError, ValueError, OverflowError):
        _fail()


def _body(value, *, empty=False):
    if type(value) is not str or len(value) > 2000 or (not empty and not value.strip()):
        _fail()
    return value


def _binding(key, mapping, members, *, parent=False):
    binding = mapping.get(key) if type(key) is str else None
    if (
        not isinstance(binding, dict)
        or binding.get("archive_only")
        or type(binding.get("member_id")) is not str
    ):
        _fail("task_report_identity_review_required")
    member = members.get(binding.get("member_id"))
    if (
        not isinstance(member, dict)
        or member.get("active") is not True
        or member.get("role") == "guest"
        or type(binding.get("member_revision")) is not int
        or type(member.get("revision")) is not int
        or binding["member_revision"] != member.get("revision")
    ):
        _fail("task_report_identity_review_required")
    if parent and member.get("role") not in {"owner", "parent"}:
        _fail("task_reviewer_role_review_required")
    return deepcopy(binding)


PASSIVE = {
    "accepted": {"accepted", "overdue"},
    "started": {"in_progress", "overdue"},
    "overdue": {"overdue"},
    "review_overdue": {"submitted"},
    "missed_and_rolled_over": {"assigned", "accepted", "in_progress", "needs_changes"},
    "court_correction_requested": {"completed"},
    "court_correction_applied": {"completed"},
}
OPEN = {"assigned", "accepted", "in_progress", "needs_changes", "overdue"}
TERMINAL = {
    "completed": "completion_note",
    "cancelled": "cancellation_note",
    "archived": "archive_note",
}


def project_text_history(row, events, mapping, members):
    """Reconstruct report rounds only from explicit submission/review events."""
    return _project_history(row, events, mapping, members, reports=True)


def project_unreported_history(row, events, mapping, members):
    """Separate completion/cancellation/archive notes without inventing a report."""
    return _project_history(row, events, mapping, members, reports=False)["fields"]


def project_unsubmitted_photo_history(row, events, mapping, members):
    """Retain a future photo requirement, never synthesize historical evidence."""
    return _project_history(row, events, mapping, members, reports=True, photo=True)


def project_photo_history(row, events, mapping, members, photos):
    """Use only the separate, complete, decoded and owner-matched evidence set."""
    return _project_history(row, events, mapping, members, reports=True, photo=True, photos=photos)


def _project_history(row, events, mapping, members, *, reports, photo=False, photos=None):
    """Only validated, current-mapped parent review; no implicit role creation.

    Explicit assignment changes archive the prior person's report; the legacy
    last_note is retained solely for source reconciliation, never reassigned to
    the new person. Raw history remains archived even for blocked records.
    """
    report_type = ("photo" if photo else "text") if reports else None
    if (
        row.get("kind") not in ({"task"} if reports else {"task", "reminder"})
        or row.get("requires_report") is not reports
        or row.get("report_type") != report_type
        or (not reports and row.get("reviewer") is not None)
    ):
        _fail()
    reviewer = _binding(row.get("reviewer"), mapping, members, parent=True) if reports else None
    _binding(row.get("assignee"), mapping, members)
    assignee_key, assignee = None, None
    fields = {"report_type": report_type or "none", "report": None}
    current, previous, last_note, state = None, [], None, None
    last_at, sequence = _stamp(row.get("created_at")), 0
    generation = 0
    if type(events) is not list or not events:
        _fail()
    for event in events:
        if (
            type(event) is not dict
            or event.get("task_id") != row.get("task_id")
            or type(event.get("sequence")) is not int
            or event["sequence"] <= sequence
            or type(event.get("type")) is not str
            or type(event.get("details")) is not dict
            or event.get("from_state") != state
        ):
            _fail()
        at, kind, details = _stamp(event.get("at")), event["type"], event["details"]
        if at < last_at or type(event.get("to_state")) is not str:
            _fail()
        last_at, sequence = at, event["sequence"]
        destination = event["to_state"]
        if kind == "created":
            if (
                state is not None
                or destination not in {"assigned", "accepted"}
                or at != _stamp(row["created_at"])
            ):
                _fail()
            if event.get("actor") != row.get("creator"):
                _fail()
            assignee_key = details.get("assignee")
            assignee = _binding(assignee_key, mapping, members)
            if destination != ("accepted" if assignee_key == row.get("creator") else "assigned"):
                _fail()
            if (
                details.get("requires_report") is not reports
                or details.get("report_type") != report_type
                or details.get("reviewer") != row.get("reviewer")
            ):
                _fail()
        elif state is None:
            _fail()
        elif kind == "submitted":
            if (
                not reports
                or state not in OPEN
                or destination != "submitted"
                or event.get("actor") != assignee_key
            ):
                _fail()
            _binding(event.get("actor"), mapping, members)
            report = _body(details.get("report"), empty=True)
            image = None
            if photo:
                image = (photos or {}).get(sequence)
                if (
                    not isinstance(image, dict)
                    or image.get("task_id") != row["task_id"]
                    or image.get("event_sequence") != sequence
                    or image.get("report_sha256") != hashlib.sha256(report.encode()).hexdigest()
                    or image.get("assignee") != assignee["member_id"]
                    or image.get("assignee_revision") != assignee["member_revision"]
                ):
                    _fail("task_photo_evidence_review_required")
                generation += 1
            if current is not None:
                previous.append(
                    {
                        **current,
                        "review_note": current.get("review_note"),
                        "resubmitted_at": event["at"],
                    }
                )
            current = {
                "assignee": assignee["member_id"],
                "assignee_revision": assignee["member_revision"],
                "report": None if photo else report,
                "submitted_at": event["at"],
                **(
                    {"report_generation": generation, "report_media": [image["media_id"]]}
                    if photo
                    else {}
                ),
            }
            last_note = report or None
        elif kind == "changes_requested":
            if (
                not reports
                or state != "submitted"
                or destination != "needs_changes"
                or current is None
            ):
                _fail()
            _binding(event.get("actor"), mapping, members, parent=True)
            last_note = _body(details.get("note"))
            current["review_note"] = last_note
        elif kind in TERMINAL:
            if (
                destination != kind
                or state == "archived"
                or (kind != "archived" and state not in OPEN | {"submitted"})
            ):
                _fail()
            if kind == "completed" and reports:
                _binding(event.get("actor"), mapping, members, parent=True)
                if state != "submitted" and details.get("direct_parent_confirmation") is not True:
                    _fail()
            elif kind == "completed":
                if event.get("actor") not in {row.get("creator"), assignee_key} or state not in {
                    "accepted",
                    "in_progress",
                    "overdue",
                }:
                    _fail("task_report_identity_review_required")
                _binding(event.get("actor"), mapping, members)
            elif not reports:
                actor = event.get("actor")
                _binding(
                    actor, mapping, members, parent=actor not in {row.get("creator"), assignee_key}
                )
            note = _body(details.get("note"), empty=True)
            if note:
                last_note = note
                fields[TERMINAL[kind]] = note
        elif kind == "revised":
            _binding(
                event.get("actor"),
                mapping,
                members,
                parent=reports or event.get("actor") != row.get("creator"),
            )
            before, after = details.get("previous"), details.get("current")
            if (
                not isinstance(before, dict)
                or not isinstance(after, dict)
                or before.get("assignee", assignee_key) != assignee_key
            ):
                _fail("task_report_reassignment_review_required")
            if state not in OPEN or destination not in OPEN:
                _fail()
            next_key = after.get("assignee", assignee_key)
            next_assignee = _binding(next_key, mapping, members)
            if next_key != assignee_key:
                if destination not in {"assigned", "overdue"}:
                    _fail()
                if current is not None:
                    previous.append(
                        {
                            **current,
                            "review_note": current.get("review_note"),
                            "reassigned_at": event["at"],
                        }
                    )
                current = None
                assignee_key, assignee = next_key, next_assignee
            elif state != "overdue" and destination not in {state, "overdue"}:
                _fail()
        elif kind in PASSIVE:
            if kind in {"accepted", "started"} and event.get("actor") != assignee_key:
                _fail("task_report_identity_review_required")
            if destination not in PASSIVE[kind]:
                _fail()
            if (
                (kind == "accepted" and state not in {"assigned", "overdue"})
                or (kind == "started" and state not in {"accepted", "needs_changes", "overdue"})
                or (kind == "overdue" and state == "overdue")
            ):
                _fail()
            if (
                kind in {"accepted", "started", "overdue", "missed_and_rolled_over"}
                and state not in OPEN
            ):
                _fail()
            if (
                kind in {"review_overdue", "court_correction_requested", "court_correction_applied"}
                and state != destination
            ):
                _fail()
        else:
            _fail()
        if destination == "needs_changes" and (current is None or not current.get("review_note")):
            _fail()
        if row.get("kind") == "reminder" and (
            assignee_key != row.get("creator")
            or (
                kind not in {"overdue", "missed_and_rolled_over"}
                and event.get("actor") != assignee_key
            )
        ):
            _fail("task_report_identity_review_required")
        state = destination
    if assignee_key != row.get("assignee"):
        _fail("task_report_reassignment_review_required")
    if state != row.get("state") or last_note != row.get("last_note"):
        _fail()
    submitted = current.get("submitted_at") if current else None
    if (row.get("submitted_at") is None) != (submitted is None):
        _fail()
    if submitted is not None and _stamp(row["submitted_at"]) != _stamp(submitted):
        _fail()
    if state in {"submitted", "needs_changes"} and current is None:
        _fail()
    if state == "needs_changes" and not current.get("review_note"):
        _fail()
    if current is not None:
        fields.update(
            {
                key: value
                for key, value in current.items()
                if key not in {"assignee", "assignee_revision"}
            }
        )
        # Equal instants can have different original offsets/ISO spelling. Keep
        # the current row's exact representation; historic rounds keep event time.
        fields["submitted_at"] = row["submitted_at"]
    if previous:
        fields["previous_reports"] = previous
    if photo and generation:
        # Preserve the high-water mark even after a reassignment cleared current.
        fields["report_generation"] = generation
    return {"fields": fields, "reviewer": reviewer, "review_policy": "household_parents"}
