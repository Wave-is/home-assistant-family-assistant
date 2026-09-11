"""Family Assistant. Domain code intentionally has no Home Assistant imports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Family Assistant from configuration.yaml."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one household and its server-side API."""
    from .runtime import async_setup_runtime

    return await async_setup_runtime(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload all listeners and platforms belonging to this household."""
    from .runtime import async_unload_runtime

    return await async_unload_runtime(hass, entry)
