"""Content-free Home Assistant Repairs visibility for a stuck backup lease."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

ISSUE_ID = "backup_recovery"


def create_issue(hass: HomeAssistant) -> None:
    """Expose one actionable issue without generation or household data."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_ID,
    )


def delete_issue(hass: HomeAssistant) -> None:
    """Remove recovery visibility after the exact leases are released."""
    ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
