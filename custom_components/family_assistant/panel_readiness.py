"""Read-only setup facts, separate from verified external-service health."""

from .const import MODULES


def member_readiness(state, options, visible_members):
    """Bound to the already-authorized projection; no personal values or source IDs."""
    result = []
    enabled = set(state["settings"]["modules"])
    for member in visible_members:
        if not member.get("active") or member.get("role") != "child":
            continue
        member_id = member["id"]
        alarms = [row for row in state.get("alarms", {}).values() if row["member"] == member_id]
        active = [row for row in alarms if row.get("enabled") is True]
        strict = [row for row in active if row.get("profile") == "strict"]
        binding = options.get("alarm_devices", {}).get(member_id, {})
        output = binding.get("confirmed") is True and bool(binding.get("entity_id"))
        alarm_issues = []
        if "alarms" in enabled:
            if not alarms:
                alarm_issues.append("alarm_no_schedule")
            elif not active:
                alarm_issues.append("alarm_schedules_disabled")
            if strict and not output:
                alarm_issues.append("alarm_output_missing")
        timetables = [
            row
            for row in state.get("school", {}).get("timetables", {}).values()
            if row.get("member") == member_id
            and row.get("status") == "active"
            and row.get("member_revision") == member.get("revision")
        ]
        result.append(
            {
                "id": member_id,
                "alarms": {
                    "total": len(alarms),
                    "enabled": len(active),
                    "strict": len(strict),
                    "output_configured": output,
                    "issues": alarm_issues,
                },
                "school": {
                    "timetables": len(timetables),
                    "issues": (
                        ["school_no_timetable"] if "school" in enabled and not timetables else []
                    ),
                },
            }
        )
    return result


def capabilities(state, services, health, members):
    enabled = set(state["settings"]["modules"])
    result = []
    for module in MODULES:
        issues = []
        ready = module in enabled
        if ready and module == "conversation":
            if not services.get("conversation"):
                issues.append("provider_unavailable")
            elif health.get("conversation") not in {None, "connected", "fallback"}:
                issues.append("provider_unavailable")
            elif not health.get("conversation"):
                ready = None
        if ready and module == "mikrotik":
            if not services.get("mikrotik"):
                issues.append("network_not_configured")
            elif health.get("mikrotik") not in {None, "network_connected"}:
                issues.append("network_unavailable")
            elif not health.get("mikrotik"):
                ready = None
        if module in enabled and module in {"alarms", "school"}:
            for member in members:
                for code in member[module]["issues"]:
                    if code not in issues:
                        issues.append(code)
        if issues:
            ready = False
        result.append(
            {"id": module, "enabled": module in enabled, "ready": ready, "issues": issues}
        )
    return result
