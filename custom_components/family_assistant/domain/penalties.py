"""Shared opt-in automatic penalty policy. Manual awards are a separate action."""

from datetime import UTC
from zoneinfo import ZoneInfo

from .context import Context
from .validation import timestamp


def award(
    ctx: Context,
    *,
    source: str,
    source_id: str,
    member: str,
    points: int,
    reason_key: str,
    reason_data: dict,
    timezone: str = "UTC",
) -> bool:
    settings = ctx.state["settings"]
    if not settings.get("automatic_penalties") or "court" not in settings["modules"] or points >= 0:
        return False
    record_id = f"{source}:{source_id}"
    if record_id in ctx.state["court"]:
        return False
    zone = ZoneInfo(timezone)
    today = ctx.now.astimezone(zone).date()
    spent = sum(
        -event["points"]
        for event in ctx.state["court"].values()
        if event["member"] == member
        and event["points"] < 0
        and event["source"] != "manual"
        and event["status"] == "active"
        and timestamp(event["created_at"], "created_at").astimezone(zone).date() == today
    )
    remaining = max(0, settings.get("daily_penalty_cap", 1) - spent)
    if remaining == 0:
        return False
    ctx.state["court"][record_id] = {
        "id": record_id,
        "member": member,
        "points": -min(remaining, -points),
        "reason_key": reason_key,
        "reason_data": reason_data,
        "actor": "system",
        "source": source,
        "status": "active",
        "created_at": ctx.now.astimezone(UTC).isoformat(),
        "revision": 1,
    }
    return True
