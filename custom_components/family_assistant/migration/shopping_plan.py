"""Pure shopping-record proposals; preserve unknown values instead of guessing."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from .preflight import _text
from .review import LegacyReview


class ShoppingPlanError(ValueError):
    """Fixed code only; no source fields or underlying exceptions."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, repr=False)
class ShoppingPlan:
    """A private frozen proposal, not an import capability or a family view."""

    _summary: bytes = field(repr=False)
    _private_payload: bytes = field(repr=False)

    def __repr__(self):
        return "ShoppingPlan(private=True, import_available=False)"

    def summary(self):
        return json.loads(self._summary)

    def private_data(self):
        return json.loads(self._private_payload)


def _record(row, mapping):
    metadata = row["metadata"]
    quantity, remaining = (
        metadata.get("shopping_quantity"),
        metadata.get("shopping_remaining_quantity"),
    )
    if quantity is None or remaining is None:
        raise ShoppingPlanError("shopping_quantity_unknown")
    # No rounding of legacy data: a six-decimal domain cannot promise losslessness
    # for finer quantities (including floating-point remnants) without review.
    quantity, remaining = Decimal(str(quantity)), Decimal(str(remaining))
    if quantity < Decimal("0.001") or any(
        value != value.quantize(Decimal("0.000001")) for value in (quantity, remaining)
    ):
        raise ShoppingPlanError("shopping_precision_unsupported")
    if not _text(row["title"], 200):
        raise ShoppingPlanError("shopping_name_unsupported")
    approval, state = metadata["shopping_approval"], row["state"]
    if approval in {"pending", "rejected"} and remaining != quantity:
        raise ShoppingPlanError("shopping_state_conflict")
    if state == "pending_approval" and approval == "pending":
        status = "pending"
    elif state in {"assigned", "accepted"} and approval == "approved" and remaining > 0:
        status = "approved"
    elif state == "completed" and approval == "approved" and remaining == 0:
        status = "purchased"
    elif state == "cancelled" and approval == "rejected":
        status = "rejected"
    elif state in {"cancelled", "archived"}:
        status = "archived"
    elif state in {"pending_approval", "assigned", "accepted", "completed"}:
        raise ShoppingPlanError("shopping_state_conflict")
    else:
        raise ShoppingPlanError("shopping_state_unsupported")
    creator = mapping[row["creator"]]
    buyer = mapping[row["assignee"]] if row.get("assignee") else None
    return {
        "source_task": row["task_id"],
        "target_bindings": {"creator": creator, "buyer": buyer},
        "record": {
            "name": row["title"],
            "quantity": float(quantity),
            "purchased": float(quantity - remaining),
            "unit": metadata.get("shopping_unit") or "",
            "category": "",
            "store": "",
            "note": "",
            "creator": creator["member_id"],
            "buyer": buyer["member_id"] if buyer else None,
            "created_at": row["created_at"],
            "status": status,
            # Old transport-specific events remain in the private archive, not
            # new authenticated shopping-history events or command receipts.
            "history": [],
        },
    }


def build_shopping_plan(review: LegacyReview, *, members=None) -> ShoppingPlan:
    if type(review) is not LegacyReview:
        raise ShoppingPlanError("invalid_review")
    if not review.matches_members(members):
        raise ShoppingPlanError("review_changed")
    assistant, _, mapping = review.private_data()
    ledger = assistant["ledger"] if "ledger" in assistant else assistant
    rows = {key: row for key, row in ledger["tasks"].items() if row["kind"] == "shopping"}
    archive = {
        "tasks": rows,
        "history": [event for event in ledger["history"] if event["task_id"] in rows],
    }
    proposals, blocked = [], []
    issues = Counter()
    for identifier, row in sorted(rows.items()):
        try:
            proposals.append(_record(row, mapping))
        except ShoppingPlanError as error:
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
        "mode": "shopping_plan_proposal",
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
    return ShoppingPlan(_encode(summary), private)
