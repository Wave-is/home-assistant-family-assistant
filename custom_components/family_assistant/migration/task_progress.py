"""Recover overdue progress only from a fully reconciled assignment history."""

from datetime import datetime

from .task_reports import (
    ReportHistoryError,
    project_text_history,
    project_unreported_history,
    project_unsubmitted_photo_history,
)


def project_overdue_progress(row, events, mapping, members):
    """The old saved pre-overdue phase sometimes lagged a later acceptance/start.

    This is a pure proposal, not a source repair. Keep every original source byte;
    only reconcile the current assignment's explicit activity and timestamps.
    """
    try:
        projector = (
            project_unreported_history
            if row.get("requires_report") is False
            else project_unsubmitted_photo_history
            if row.get("report_type") == "photo"
            else project_text_history
        )
        projector(row, events, mapping, members)
        if row.get("state") != "overdue":
            raise ValueError
        accepted, started, phase, legacy_prior = None, None, None, None
        for event in events:
            kind, before, after = event["type"], event["from_state"], event["to_state"]
            stamp, details = event["at"], event["details"]
            assignment_changed = (
                kind == "revised"
                and details["previous"]["assignee"] != details["current"]["assignee"]
            )
            if kind == "created" and after == "accepted":
                accepted = stamp
            elif kind == "accepted":
                if accepted is not None:
                    raise ValueError
                accepted = stamp
            elif kind == "started":
                if accepted is None:
                    raise ValueError
                started = stamp
            elif kind == "submitted" and accepted is None:
                accepted = stamp
            elif assignment_changed:
                accepted, started = None, None
            if after != "overdue":
                phase = after
            elif assignment_changed:
                phase = "assigned"
            elif kind == "accepted":
                phase = "accepted"
            elif kind == "started":
                phase = "in_progress"
            elif kind == "overdue":
                phase = before
            if kind == "overdue":
                legacy_prior = before
            elif assignment_changed:
                legacy_prior = "assigned" if after == "overdue" else None
            elif (
                kind in {"revised", "missed_and_rolled_over"}
                and before == "overdue"
                and after != "overdue"
            ):
                legacy_prior = None
        if row["metadata"].get("overdue_from_state") != legacy_prior or phase not in {
            "assigned",
            "accepted",
            "in_progress",
            "needs_changes",
        }:
            raise ValueError
        if (
            (phase == "assigned" and (accepted is not None or started is not None))
            or (phase == "accepted" and (accepted is None or started is not None))
            or (phase == "in_progress" and (accepted is None or started is None))
            or (phase == "needs_changes" and accepted is None)
        ):
            # A later legacy deadline edit may itself have restored stale phase
            # metadata. Do not carry that source inconsistency into a proposal.
            raise ValueError
        for key, expected in [("accepted_at", accepted), ("started_at", started)]:
            actual = row.get(key)
            if actual is None or expected is None:
                if actual != expected:
                    raise ValueError
            elif datetime.fromisoformat(actual) != datetime.fromisoformat(expected):
                raise ValueError
        return phase
    except (ReportHistoryError, ValueError, TypeError, KeyError):
        raise ReportHistoryError("task_overdue_progress_review_required") from None
