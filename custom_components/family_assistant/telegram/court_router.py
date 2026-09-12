"""Natural court language routed through the canonical, authorized domain ledger."""

from __future__ import annotations

from datetime import datetime

from ..court import (
    ParsedMessage,
    all_stats,
    assessment_response,
    calculate_court_stats,
    case_report,
    history_report,
)
from ..court.responses import localized
from ..domain.validation import DomainError
from . import commands


def _stats(view: dict, now: datetime):
    settings = view.get("settings", {})
    config = settings.get("court", {})
    privileged = view.get("role") in {"owner", "parent"}
    members = [
        member
        for member in view.get("members", [])
        if (privileged or member["id"] == view["actor"]) and member.get("role") != "guest"
    ]
    result = calculate_court_stats(
        view.get("court", []),
        timezone=settings.get("timezone", "UTC"),
        now=now,
        members=members,
        weekday=config.get("weekday", 0),
        time_str=config.get("time", "00:00"),
        thresholds=config.get("thresholds", []),
    )
    if not privileged:
        for member, stats in result.stats.items():
            stats["thresholds"] = [
                rule
                for rule in view.get("court_summary", {}).get("thresholds", [])
                if rule["member"] == member
            ]
    return result


async def route_court(
    engine,
    actor: str,
    content: str,
    operation_id: str,
    now: datetime,
    parsed: ParsedMessage,
    view: dict,
    language: str,
    *,
    refs=(),
) -> str | None:
    """Handle court intent using fresh permissions, durable plans and one commit."""
    if parsed.action == "ignore":
        return None
    # A caller-supplied/stale projection never authorizes a read or mutation.
    view = engine.view(actor, now=now)
    if "court" not in view["settings"]["modules"]:
        raise DomainError("module_disabled")
    if view["role"] == "guest":
        return localized("denied", language)
    if parsed.action in {"undo", "assessments", "ambiguous", "missing_child"}:
        if view["role"] not in {"owner", "parent"}:
            return localized("denied", language)

    copy_key = {
        "appeal": "appeal",
        "help": "help",
        "rules": "rules",
        "ambiguous": "ambiguous",
        "missing_child": "missing",
    }.get(parsed.action)
    if copy_key:
        return localized(copy_key, language)

    stats_data = _stats(view, now)
    names = {member["id"]: member["name"] for member in view["members"]}
    if parsed.action == "stats":
        return (
            all_stats(stats_data.stats, stats_data.week_id, language=language)
            + "\n\n"
            + history_report(stats_data.history, names=names, language=language)
        )
    if parsed.action in {"case", "history"}:
        history = stats_data.history
        if parsed.child:
            if parsed.child not in history:
                return localized("denied", language)
            history = {parsed.child: history[parsed.child]}
        if parsed.action == "case" and parsed.child:
            return case_report(
                parsed.child,
                stats_data.stats[parsed.child],
                history[parsed.child],
                language=language,
            )
        return history_report(history, kind=parsed.detail, names=names, language=language)

    if parsed.action == "undo":
        prior = commands.previous(engine, actor, content, refs, operation_id)
        if prior:
            action, payload = prior["action"], prior["payload"]
        else:
            if not stats_data.active_records_sorted:
                return localized("undo_empty", language)
            target = stats_data.active_records_sorted[0]
            action = "court.reverse"
            payload = {
                "id": target["id"],
                "revision": target["revision"],
                "reason": content.strip(),
            }
        await commands.execute(
            engine,
            actor,
            content,
            refs,
            operation_id,
            now,
            action,
            payload,
        )
        return localized("undo_ok", language)

    if parsed.action == "assessments":
        if not parsed.assessments:
            return localized("ambiguous", language)
        # Both assignments validate on one working copy. A bad second member
        # cannot leave the first score committed.
        payload = {
            "commands": [
                {
                    "action": "court.award",
                    "payload": {
                        "member": item.child,
                        "points": 1 if item.kind == "plus" else -1,
                        "reason": item.reason,
                    },
                }
                for item in parsed.assessments
            ]
        }
        if any(item.kind not in {"plus", "minus"} for item in parsed.assessments):
            raise DomainError("invalid_field", "kind")
        result = await commands.execute(
            engine,
            actor,
            content,
            refs,
            operation_id,
            now,
            "batch",
            payload,
        )
        updated = _stats(engine.view(actor, now=now), now)
        return "\n\n".join(
            assessment_response(
                record["member"],
                "plus" if record["points"] > 0 else "minus",
                updated.stats[record["member"]],
                record["reason"],
                record["id"],
                language=language,
            )
            for record in result["items"]
        )
    return None
