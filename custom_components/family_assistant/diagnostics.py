"""Diagnostics never expose names, identities, messages, URLs or credentials."""

from .runtime import safe_diagnostics


async def async_get_config_entry_diagnostics(hass, entry):
    return safe_diagnostics(entry.runtime_data)
