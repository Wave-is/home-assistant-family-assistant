"""Counts-only school reminder retention health and Home Assistant Repair."""

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .domain.school_retention import health_stats

CODE = "school_retention_attention"
HEALTH_KEY = "school_retention"


def synchronize(hass, entry, runtime, now=None):
    """Synchronize one counts-only Repair from the current durable snapshot."""
    stats = health_stats(runtime.engine.snapshot(), now)
    issue_id = f"{entry.entry_id}_school_retention"
    attention = bool(
        stats["capacity"]
        or stats["unpaired"]
        or stats["retention_errors"]
        or stats["clock_rollback"]
    )
    if attention:
        if runtime.health.get(HEALTH_KEY) != CODE:
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=CODE,
            )
        runtime.health[HEALTH_KEY] = CODE
    else:
        runtime.health.pop(HEALTH_KEY, None)
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    return stats
