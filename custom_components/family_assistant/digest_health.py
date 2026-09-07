"""Counts-only digest retention health and a persistent Home Assistant Repair."""

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .domain.digests import health_stats

CODE = "digest_retention_attention"


def synchronize(hass, entry, runtime):
    stats = health_stats(runtime.engine.snapshot())
    issue_id = f"{entry.entry_id}_digest_retention"
    if stats["capacity"]:
        if runtime.health.get("digests") != CODE:
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=CODE,
            )
        runtime.health["digests"] = CODE
    else:
        runtime.health.pop("digests", None)
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    return stats
