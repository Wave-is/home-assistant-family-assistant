"""Administrator-confirmed retry for an exact failed backup unwind."""

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import backup
from .backup_recovery import ISSUE_ID


class BackupRecoveryFlow(RepairsFlow):
    """Retry only the process-local generation captured at flow creation."""

    def __init__(self, coordinator, generation: object) -> None:
        self._coordinator = coordinator
        self._generation = generation

    def _current(self) -> bool:
        return backup.recovery_matches(self.hass, self._coordinator, self._generation)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        """Open the named confirmation step."""
        # HA initializes Repairs with transport metadata (including issue_id).
        # Opening the flow is not confirmation, even when init data is non-empty.
        return await self.async_step_confirm(None)

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Retry the exact remaining leases after explicit confirmation."""
        if not self._current():
            return self.async_abort(reason="stale_recovery")
        if user_input is None:
            return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))
        try:
            await backup.async_retry_recovery(self.hass, self._coordinator, self._generation)
        except HomeAssistantError as error:
            if str(error) == "stale_recovery":
                return self.async_abort(reason="stale_recovery")
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                errors={"base": "backup_unavailable"},
            )
        return self.async_create_entry(title="", data={})


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a flow only for the current content-free recovery issue."""
    if issue_id != ISSUE_ID or data is not None:
        raise data_entry_flow.UnknownStep
    current = backup.recovery_identity(hass)
    if current is None:
        raise data_entry_flow.UnknownStep
    return BackupRecoveryFlow(*current)
