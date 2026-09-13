"""Read-only validation of explicitly selected alarm companion controls.

Some sirens expose duration and volume as separate number/select entities, not
as siren service features. Selection never calls a service. Companions must be
registered to the same physical HA device; a generic unrelated number is not
an alarm output. No entity is inferred from a label, area or legacy name.
"""

from __future__ import annotations

import math

from .domain.validation import DomainError

COMPANION_KEYS = {"duration_entity_id", "volume_entity_id", "duration_seconds", "select_volume"}


def _finite(value):
    if isinstance(value, bool):
        raise DomainError("device_unsupported")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DomainError("device_unsupported") from None
    if not math.isfinite(number):
        raise DomainError("device_unsupported")
    return number


def validate_binding(hass, binding, *, device_for=None):
    """Return normalized selected controls or a fixed, non-sensitive error.

    Siren TURN_ON/TURN_OFF feature checks remain with the native caller. The
    injected registry lookup is only for isolated tests, never user input.
    """
    entity = binding.get("entity_id")
    if not isinstance(entity, str) or not entity.startswith("siren."):
        raise DomainError("device_unsupported")
    state = hass.states.get(entity)
    if state is None or state.state in {"unknown", "unavailable"}:
        raise DomainError("device_unavailable")
    volume = _finite(binding.get("volume", 0.5))
    if not 0 <= volume <= 1:
        raise DomainError("device_unsupported")
    result = {"entity_id": entity, "volume": volume, "confirmed": binding.get("confirmed") is True}
    duration_entity = binding.get("duration_entity_id") or ""
    volume_entity = binding.get("volume_entity_id") or ""
    if not duration_entity and not volume_entity:
        return result

    if device_for is None:
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)

        def device_for(entity_id):
            entry = registry.async_get(entity_id)
            return entry.device_id if entry else None

    device = device_for(entity)
    if not device or binding.get("companion_device_id", device) != device:
        raise DomainError("device_unsupported")
    result["companion_device_id"] = device
    for selected, domain in ((duration_entity, "number"), (volume_entity, "select")):
        if not selected:
            continue
        if not isinstance(selected, str) or not selected.startswith(f"{domain}."):
            raise DomainError("device_unsupported")
        if device_for(selected) != device:
            raise DomainError("device_unsupported")
        candidate = hass.states.get(selected)
        if candidate is None or candidate.state in {"unknown", "unavailable"}:
            raise DomainError("device_unavailable")
        if domain == "number":
            value = _finite(binding.get("duration_seconds", 1800))
            minimum = _finite(candidate.attributes.get("min"))
            maximum = _finite(candidate.attributes.get("max"))
            step = _finite(candidate.attributes.get("step", 1))
            if (
                not value.is_integer()
                or not 60 <= value <= 1800
                or not minimum <= value <= maximum
                or step <= 0
                or not math.isclose(
                    (value - minimum) / step, round((value - minimum) / step), abs_tol=1e-8
                )
            ):
                raise DomainError("device_unsupported")
            result.update(duration_entity_id=selected, duration_seconds=int(value))
        else:
            value = binding.get("select_volume", "high")
            available = candidate.attributes.get("options")
            if (
                not isinstance(value, str)
                or value not in {"low", "middle", "high"}
                or not isinstance(available, list)
                or value not in available
            ):
                raise DomainError("device_unsupported")
            result.update(volume_entity_id=selected, select_volume=value)
    return result


def pending_controls(hass, binding):
    """Read-only finite service plan; callers must revalidate after each await."""
    result = []
    duration = binding.get("duration_entity_id")
    if duration:
        state = hass.states.get(duration)
        if state is None or _finite(state.state) != binding["duration_seconds"]:
            result.append(
                (
                    "number",
                    "set_value",
                    {"entity_id": duration, "value": binding["duration_seconds"]},
                )
            )
    volume = binding.get("volume_entity_id")
    if volume:
        state = hass.states.get(volume)
        if state is None or state.state != binding["select_volume"]:
            result.append(
                (
                    "select",
                    "select_option",
                    {"entity_id": volume, "option": binding["select_volume"]},
                )
            )
    return result
