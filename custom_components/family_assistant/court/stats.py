"""Pure presentation of the canonical court ledger's configured weekly period."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..domain.court_periods import period_bounds, summarize
from ..domain.court_rules import project

# Kept for old importers; household identifiers are never public defaults.
CHILDREN: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CourtStatsSummary:
    """Calculated court stats for the active weekly period."""

    stats: dict[str, dict[str, Any]]
    history: dict[str, list[dict[str, Any]]]
    week_id: str
    start: datetime
    end: datetime
    active_records_sorted: list[dict[str, Any]]


def calculate_court_stats(
    court_records: Iterable[dict[str, Any]],
    timezone: str = "UTC",
    now: datetime | None = None,
    members: Iterable[dict[str, Any]] | None = None,
    weekday: int = 0,
    time_str: str = "00:00",
    thresholds: Iterable[dict[str, Any]] = (),
) -> CourtStatsSummary:
    """Use the same validation, balance and period bounds as the domain ledger.

    Callers supply authorized records and members. This helper does not expand
    visibility or infer a consequence from a numeric score.
    """
    start, end = period_bounds(now or datetime.now(UTC), timezone, weekday, time_str)
    thresholds = tuple(thresholds)
    records = (
        list(court_records.values()) if isinstance(court_records, dict) else list(court_records)
    )
    totals = summarize(records, start, end)
    member_map = {member["id"]: member.get("name", member["id"]) for member in members or ()}
    member_ids = list(member_map) if members is not None else sorted({r["member"] for r in records})
    rows = {row["member"]: row for row in totals["rows"]}
    current = set(totals["events"])
    active = [r for r in records if r["id"] in current and r["status"] == "active"]
    active.sort(key=lambda r: datetime.fromisoformat(r["created_at"]), reverse=True)
    stats = {}
    history = {}
    for member_id in member_ids:
        row = rows.get(member_id, {})
        pluses = row.get("active_positives", 0)
        minuses = -row.get("active_negatives", 0)
        stats[member_id] = {
            "name": member_map.get(member_id, member_id),
            "pluses": pluses,
            "minuses": minuses,
            "balance": pluses - minuses,
            "penalty_points": max(0, minuses - pluses),
            "thresholds": project(thresholds, [{"member": member_id, "total": pluses - minuses}]),
        }
        history[member_id] = [
            {
                "event_id": r["id"],
                "type": "plus" if r["points"] > 0 else "minus",
                "points": r["points"],
                "reason": r.get("reason", ""),
                "reason_key": r.get("reason_key", ""),
                "reason_data": r.get("reason_data", {}),
                "parent_name": member_map.get(r.get("actor"), r.get("actor") or ""),
                "timestamp": r["created_at"],
            }
            for r in reversed(active)
            if r["member"] == member_id
        ]
    return CourtStatsSummary(
        stats=stats,
        history=history,
        week_id=f"{start.isoformat()}/{end.isoformat()}",
        start=start,
        end=end,
        active_records_sorted=[r for r in active if r["member"] in stats],
    )
