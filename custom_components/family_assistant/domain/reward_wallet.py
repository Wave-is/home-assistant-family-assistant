"""Bounded pure reward wallet helper."""

from __future__ import annotations

from typing import Any

from .validation import DomainError

VALID_REDEMPTION_STATUSES = frozenset(
    {"requested", "approved", "fulfilled", "rejected", "cancelled", "expired", "refunded"}
)
VALID_COURT_STATUSES = frozenset({"active", "reversed"})
RESERVED_STATUSES = frozenset({"requested", "approved"})


def _check_string(value: Any, field_name: str, max_len: int = 80) -> str:
    if not isinstance(value, str):
        raise DomainError("invalid_field", field_name)
    if value != value.strip() or not value or len(value) > max_len:
        raise DomainError("invalid_field", field_name)
    return value


def balance(
    court_records: list[dict[str, Any]],
    redemptions: list[dict[str, Any]],
    member: str,
) -> dict[str, int]:
    """Compute member reward balance snapshot strictly and purely."""
    target_member = _check_string(member, "member")

    if not isinstance(court_records, list):
        raise DomainError("invalid_field", "court_records")
    if not isinstance(redemptions, list):
        raise DomainError("invalid_field", "redemptions")

    seen_court_ids: set[str] = set()
    earned = 0

    for rec in court_records:
        if not isinstance(rec, dict):
            raise DomainError("invalid_field", "court_records")
        for req in ("id", "member", "points", "status"):
            if req not in rec:
                raise DomainError("invalid_field", req)

        rec_id = _check_string(rec["id"], "id")
        if rec_id in seen_court_ids:
            raise DomainError("invalid_field", "id")
        seen_court_ids.add(rec_id)

        rec_member = _check_string(rec["member"], "member")

        pts = rec["points"]
        if isinstance(pts, bool) or not isinstance(pts, int):
            raise DomainError("invalid_field", "points")
        if pts == 0 or not (-100 <= pts <= 100):
            raise DomainError("invalid_field", "points")

        status = rec["status"]
        if not isinstance(status, str) or status not in VALID_COURT_STATUSES:
            raise DomainError("invalid_field", "status")

        if rec_member == target_member and status == "active":
            earned += pts

    seen_redemption_ids: set[str] = set()
    reserved = 0
    spent = 0

    for red in redemptions:
        if not isinstance(red, dict):
            raise DomainError("invalid_field", "redemptions")
        for req in ("id", "member", "cost", "status"):
            if req not in red:
                raise DomainError("invalid_field", req)

        red_id = _check_string(red["id"], "id")
        if red_id in seen_redemption_ids:
            raise DomainError("invalid_field", "id")
        seen_redemption_ids.add(red_id)

        red_member = _check_string(red["member"], "member")

        cost = red["cost"]
        if isinstance(cost, bool) or not isinstance(cost, int):
            raise DomainError("invalid_field", "cost")
        if not (1 <= cost <= 10000):
            raise DomainError("invalid_field", "cost")

        status = red["status"]
        if not isinstance(status, str) or status not in VALID_REDEMPTION_STATUSES:
            raise DomainError("invalid_field", "status")

        if red_member == target_member:
            if status in RESERVED_STATUSES:
                reserved += cost
            elif status == "fulfilled":
                spent += cost

    net = earned - reserved - spent
    available = max(0, net)

    return {
        "earned": earned,
        "reserved": reserved,
        "spent": spent,
        "net": net,
        "available": available,
    }
