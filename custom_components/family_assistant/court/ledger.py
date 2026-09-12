"""Legacy Court Store compatibility model, not the integration's live ledger.

Live commands use domain.court and the canonical Engine Store. This isolated
model retains the legacy shape for conversion checks and never supplies names or
consequences for a new household.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import uuid4

from .parser import Assessment

SCHEMA_VERSION = 1
MAX_PROCESSED_MESSAGES = 5000


def new_week_id(now: datetime) -> str:
    """Return a readable unique identifier for a newly opened court week."""

    return f"{now.isoformat(timespec='seconds')}#{uuid4().hex[:8]}"


def default_state(now: datetime, children: Iterable[str] = ()) -> dict[str, Any]:
    """Create an empty, serializable ledger state."""

    return {
        "schema_version": SCHEMA_VERSION,
        "week_id": new_week_id(now),
        "opened_at": now.isoformat(),
        "children": {child: {"pluses": 0, "minuses": 0} for child in children},
        "history": [],
        "archived_weeks": [],
        "processed_messages": {},
        "last_weekly_report_key": None,
    }


class FamilyLedger:
    """Atomic state transitions; synchronization and I/O live in controller."""

    def __init__(
        self, state: dict[str, Any] | None, now: datetime, *, children: Iterable[str] = ()
    ) -> None:
        self.state = self._normalize(state, now, children)

    @staticmethod
    def _normalize(
        state: dict[str, Any] | None, now: datetime, member_ids: Iterable[str] = ()
    ) -> dict[str, Any]:
        if not isinstance(state, dict):
            return default_state(now, member_ids)
        result = deepcopy(state)
        result.setdefault("schema_version", SCHEMA_VERSION)
        result.setdefault("week_id", new_week_id(now))
        result.setdefault("opened_at", now.isoformat())
        result.setdefault("history", [])
        result.setdefault("archived_weeks", [])
        result.setdefault("processed_messages", {})
        result.setdefault("last_weekly_report_key", None)
        children = result.setdefault("children", {})
        for child in set(children) | set(member_ids):
            stats = children.setdefault(child, {})
            stats["pluses"] = max(0, int(stats.get("pluses", 0)))
            stats["minuses"] = max(0, int(stats.get("minuses", 0)))
        return result

    @staticmethod
    def message_key(chat_id: int, message_id: int | str) -> str:
        return f"{int(chat_id)}:{message_id}"

    def is_processed(self, chat_id: int, message_id: int | str) -> bool:
        return self.message_key(chat_id, message_id) in self.state["processed_messages"]

    def stats(self, child: str) -> dict[str, int]:
        values = self.state["children"][child]
        pluses = int(values["pluses"])
        minuses = int(values["minuses"])
        penalty_points = max(0, minuses - pluses)
        return {
            "pluses": pluses,
            "minuses": minuses,
            "balance": pluses - minuses,
            "penalty_points": penalty_points,
        }

    def apply_assessments(
        self,
        assessments: Iterable[Assessment],
        *,
        timestamp: datetime,
        chat_id: int,
        message_id: int | str,
        original_text: str,
        parent_user_id: int,
        parent_name: str,
        telegram_from_first: str = "",
        telegram_from_last: str = "",
    ) -> list[dict[str, Any]]:
        """Apply one Telegram update exactly once and return created records."""

        key = self.message_key(chat_id, message_id)
        if key in self.state["processed_messages"]:
            return []

        assessments = tuple(assessments)
        for assessment in assessments:
            if assessment.child not in self.state["children"]:
                raise ValueError("unknown legacy member")
            if assessment.kind not in {"plus", "minus"} or not assessment.reason.strip():
                raise ValueError("invalid legacy assessment")

        records: list[dict[str, Any]] = []
        for assessment in assessments:
            stats = self.state["children"][assessment.child]
            counter = "pluses" if assessment.kind == "plus" else "minuses"
            stats[counter] = int(stats[counter]) + 1
            record = {
                "event_id": uuid4().hex,
                "timestamp": timestamp.isoformat(),
                "week_id": self.state["week_id"],
                "child": assessment.child,
                "type": assessment.kind,
                "delta": 1 if assessment.kind == "plus" else -1,
                "original_text": original_text,
                "reason": assessment.reason,
                "parent_user_id": int(parent_user_id),
                "parent_name": parent_name,
                "telegram_from_first": telegram_from_first,
                "telegram_from_last": telegram_from_last,
                "telegram_chat_id": int(chat_id),
                "telegram_message_id": message_id,
                "cancelled": False,
                "cancelled_at": None,
                "cancelled_by_user_id": None,
                "cancelled_by_name": None,
            }
            self.state["history"].append(record)
            records.append(record)

        self._remember_processed(
            key,
            {
                "timestamp": timestamp.isoformat(),
                "action": "assessments",
                "event_ids": [record["event_id"] for record in records],
            },
        )
        return records

    def undo_last(
        self,
        *,
        timestamp: datetime,
        chat_id: int,
        message_id: int | str,
        parent_user_id: int,
        parent_name: str,
    ) -> dict[str, Any] | None:
        """Cancel the latest active score event in the current week."""

        key = self.message_key(chat_id, message_id)
        if key in self.state["processed_messages"]:
            return None

        target = next(
            (
                item
                for item in reversed(self.state["history"])
                if item.get("week_id") == self.state["week_id"]
                and not item.get("cancelled", False)
                and item.get("type") in {"plus", "minus"}
            ),
            None,
        )
        if target is not None:
            child = target["child"]
            counter = "pluses" if target["type"] == "plus" else "minuses"
            current = int(self.state["children"][child][counter])
            self.state["children"][child][counter] = max(0, current - 1)
            target["cancelled"] = True
            target["cancelled_at"] = timestamp.isoformat()
            target["cancelled_by_user_id"] = int(parent_user_id)
            target["cancelled_by_name"] = parent_name

        self._remember_processed(
            key,
            {
                "timestamp": timestamp.isoformat(),
                "action": "undo",
                "event_ids": [target["event_id"]] if target else [],
            },
        )
        return target

    def reverse_system_assessment(
        self,
        *,
        timestamp: datetime,
        chat_id: int,
        source_message_id: int | str,
        reversal_message_id: int | str,
        expected_child: str,
        parent_user_id: int,
        parent_name: str,
        reason: str,
    ) -> dict[str, Any]:
        """Cancel one exact automatic minus without touching later events.

        The source must be an idempotent system assessment already present in
        ``processed_messages``.  This deliberately cannot reverse a parent's
        ordinary Telegram verdict and therefore is safe for task-controller
        reconciliation after a late parent confirmation.
        """

        if expected_child not in self.state["children"]:
            raise ValueError("unsupported child for system assessment reversal")
        clean_reason = str(reason or "").strip()
        if not clean_reason:
            raise ValueError("system assessment reversal reason is required")

        reversal_key = self.message_key(chat_id, reversal_message_id)
        existing = self.state["processed_messages"].get(reversal_key)
        if existing is not None:
            return {
                "accepted": True,
                "created": False,
                "event_ids": list(existing.get("event_ids") or ()),
            }

        source_key = self.message_key(chat_id, source_message_id)
        source = self.state["processed_messages"].get(source_key)
        if not isinstance(source, dict) or source.get("action") != "assessments":
            return {"accepted": False, "created": False, "event_ids": []}

        source_event_ids = set(source.get("event_ids") or ())
        targets = [
            item
            for item in self.state["history"]
            if item.get("event_id") in source_event_ids
            and item.get("week_id") == self.state["week_id"]
            and item.get("child") == expected_child
            and item.get("type") == "minus"
            and int(item.get("parent_user_id", -1)) == 0
            and str(item.get("original_text") or "").startswith("automatic task control:")
        ]
        if not targets:
            return {"accepted": False, "created": False, "event_ids": []}

        reversed_ids: list[str] = []
        for target in targets:
            if target.get("cancelled", False):
                continue
            current = int(self.state["children"][expected_child]["minuses"])
            self.state["children"][expected_child]["minuses"] = max(0, current - 1)
            target["cancelled"] = True
            target["cancelled_at"] = timestamp.isoformat()
            target["cancelled_by_user_id"] = int(parent_user_id)
            target["cancelled_by_name"] = parent_name
            target["cancellation_reason"] = clean_reason
            target["cancellation_source_message_id"] = reversal_message_id
            reversed_ids.append(str(target["event_id"]))

        self._remember_processed(
            reversal_key,
            {
                "timestamp": timestamp.isoformat(),
                "action": "reverse_system_assessment",
                "event_ids": [str(item["event_id"]) for item in targets],
                "source_message_id": source_message_id,
            },
        )
        return {
            "accepted": True,
            "created": bool(reversed_ids),
            "event_ids": reversed_ids,
        }

    def active_history(self, child: str) -> list[dict[str, Any]]:
        return [
            item
            for item in self.state["history"]
            if item.get("week_id") == self.state["week_id"]
            and item.get("child") == child
            and not item.get("cancelled", False)
        ]

    def close_week(
        self, *, report_key: str, sent_at: datetime, report_message: str
    ) -> dict[str, Any]:
        """Archive and reset only after the controller confirms report delivery."""

        summary = {
            "week_id": self.state["week_id"],
            "opened_at": self.state["opened_at"],
            "closed_at": sent_at.isoformat(),
            "report_key": report_key,
            "report_message": report_message,
            "children": deepcopy(self.state["children"]),
        }
        self.state["archived_weeks"].append(summary)
        self.state["last_weekly_report_key"] = report_key
        self.state["week_id"] = new_week_id(sent_at)
        self.state["opened_at"] = sent_at.isoformat()
        self.state["children"] = {
            child: {"pluses": 0, "minuses": 0} for child in self.state["children"]
        }
        return summary

    def _remember_processed(self, key: str, value: dict[str, Any]) -> None:
        processed = self.state["processed_messages"]
        processed[key] = value
        overflow = len(processed) - MAX_PROCESSED_MESSAGES
        if overflow > 0:
            for old_key in list(processed)[:overflow]:
                del processed[old_key]

    def serializable(self) -> dict[str, Any]:
        return deepcopy(self.state)
