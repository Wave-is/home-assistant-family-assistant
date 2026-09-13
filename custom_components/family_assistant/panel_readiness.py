"""Read-only setup facts, separate from verified external-service health."""

import re

from .assistant.provider_registry import http_provider, provider_rows
from .const import MODULES
from .domain.validation import DomainError


def conversation_configuration(config):
    """Use the runtime's authoritative chain, without discovery or HA access."""
    result = {"configured": False, "search_enabled": False}
    if not isinstance(config, dict):
        return result
    try:
        search = config.get("search", {})
        if not isinstance(search, dict) or type(search.get("enabled", True)) is not bool:
            return result
        separate_search = bool(search) and search.get("enabled", True)
        if separate_search:
            http_provider(None, {**search, "kind": "ollama", "model": ""}, require_model=False)
        if "providers" not in config:
            # Legacy readiness counted a saved standalone search opt-in even
            # before adding/enabling a model. This is not runtime availability.
            # Explicit chains, including [], retain their authoritative meaning.
            result["search_enabled"] = separate_search
        if config.get("enabled") is not True:
            return result
        rows = [row for row in provider_rows(config) if row["enabled"]]
        if not rows:
            return result
        if any(row["kind"] == "ha_agent" for row in rows):
            # A chain row chooses the adapter; its separately reviewed selection
            # is still required. This is shape validation, not a live HA review.
            agent = config.get("ha_agent")
            required = {"type", "entity_id", "timeout"}
            if (
                not isinstance(agent, dict)
                or not required <= set(agent) <= required | {"binding"}
                or agent.get("type") != "ha_agent"
                or not isinstance(agent.get("entity_id"), str)
                or len(agent["entity_id"]) > 128
                or not re.fullmatch(r"conversation\.[a-z0-9_]+", agent["entity_id"])
                or type(agent.get("timeout")) is not int
                or not 5 <= agent["timeout"] <= 60
            ):
                return result
            if "binding" in agent:
                binding = agent["binding"]
                if (
                    not isinstance(binding, dict)
                    or set(binding) != {"config_entry_id", "config_subentry_id"}
                    or any(
                        not isinstance(value, str) or not value.strip() or len(value) > 128
                        for value in binding.values()
                    )
                ):
                    return result
    except DomainError:
        return result
    result["configured"] = True
    result["search_enabled"] = separate_search or any(row.get("search_enabled") for row in rows)
    return result


def image_connection(state, config, service, health):
    """Optional configuration/adapter facts; never infer successful HTTP health."""
    from .assistant.image_jobs import ImageJobs, digest
    from .assistant.image_providers import normalize_config

    result = {
        "optional": True,
        "configured": False,
        "enabled": (
            isinstance(config, dict)
            and config.get("enabled") is True
            and "conversation" in state["settings"]["modules"]
        ),
        "available": False,
        "health": None,
    }
    try:
        checked = normalize_config(config or {})
        result["configured"] = any(row["enabled"] for row in checked["providers"])
        if (
            result["enabled"]
            and isinstance(service, ImageJobs)
            and service.marker == digest(config)
        ):
            service._guard()
            result["available"] = True
    except DomainError:
        pass
    if (
        result["enabled"]
        and isinstance(health, str)
        and health
        in {
            "invalid_field",
            "provider_not_configured",
            "provider_invalid_url",
            "image_unavailable",
            "media_unavailable",
            "storage_error",
            "image_invalid",
            "image_too_large",
            "image_model_unavailable",
            "image_submission_uncertain",
            "image_delivery_uncertain",
            "image_rejected",
            "provider_authentication",
            "provider_bad_response",
            "provider_unreachable",
            "provider_timeout",
            "provider_quota_exceeded",
        }
    ):
        result["health"] = health
    return result


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
        if ready and module == "home_status":
            # Enabling a read-on-request module proves neither configured sources
            # nor current ACL/freshness. The dedicated card performs the read.
            ready = None
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
