"""Bounded owner-private source references for the export preparation wizard.

No name matching, inferred reviewer permissions, file access or source repair.
The caller must freshly authorize the private UI; this is not diagnostics.
"""

from .preflight import _text
from .review import LegacySource, _required_subjects


class CopyInventoryError(ValueError):
    """Fixed code only; never include private records in an error."""


def source_inventory(source, *, additional_members):
    if type(source) is not LegacySource or type(additional_members) is not list:
        raise CopyInventoryError("migration_prepare_source_invalid")
    if (
        len(additional_members) > 512
        or not all(_text(key, 128) for key in additional_members)
        or len(set(additional_members)) != len(additional_members)
    ):
        raise CopyInventoryError("migration_prepare_source_invalid")
    try:
        report = source.inspect(set())
        if any(row["code"] != "unmapped_members" for row in report["issues"]):
            raise ValueError
        assistant, court = source.private_data()
        ledger = assistant.get("ledger", assistant)
        required = _required_subjects(assistant, court)
        identities = set(required) | set(additional_members)
        reviewers = []
        for key, task in sorted(ledger["tasks"].items()):
            if task["kind"] == "task" and task.get("requires_report") is True:
                reviewers.append(
                    {"task_id": key, "title": task["title"], "reviewer": task.get("reviewer")}
                )
        for event in ledger["history"]:
            identities.add(event["actor"])
            task = ledger["tasks"][event["task_id"]]
            if task["kind"] in {"task", "reminder"} and event.get("type") in {
                "submitted",
                "changes_requested",
                "completed",
                "cancelled",
                "archived",
            }:
                required.add(event["actor"])
            details = event.get("details")
            if type(details) is not dict:
                continue
            assignments = []
            if event.get("type") == "created":
                assignments.append(details.get("assignee"))
            elif event.get("type") == "revised":
                for field in ("previous", "current"):
                    value = details.get(field)
                    if type(value) is dict:
                        assignments.append(value.get("assignee"))
            for actor in assignments:
                if actor is not None:
                    if not _text(actor, 128):
                        raise ValueError
                    identities.add(actor)
                    required.add(actor)
        identities.update(row["child"] for row in court["history"])
        if not 1 <= len(identities) <= 512 or len(identities) + len(reviewers) > 1000:
            raise ValueError
        return {
            "members": [
                {"source_id": key, "archive_allowed": key not in required}
                for key in sorted(identities)
            ],
            "reviewers": reviewers,
            "coherence_verified": False,
        }
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise CopyInventoryError("migration_prepare_source_invalid") from None
