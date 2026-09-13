"""Separate alarm settings are real explicit device contracts, not guessed IDs."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from custom_components.family_assistant.alarm_binding import pending_controls, validate_binding
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def binding_harness():
    def state(value, **attributes):
        return SimpleNamespace(state=value, attributes=attributes)

    states = {
        "siren.example": state("off"),
        "number.example_duration": state("60", min=60, max=1800, step=1),
        "select.example_volume": state("low", options=["low", "middle", "high"]),
    }
    devices = dict.fromkeys(states, "synthetic-alarm-device")
    binding = {
        "entity_id": "siren.example",
        "confirmed": True,
        "volume": 0.7,
        "duration_entity_id": "number.example_duration",
        "duration_seconds": 1800,
        "volume_entity_id": "select.example_volume",
        "select_volume": "high",
    }
    return SimpleNamespace(states=SimpleNamespace(get=states.get)), states, devices, binding


def test_selected_helpers_are_pinned_and_read_only(binding_harness):
    hass, states, devices, binding = binding_harness
    before = deepcopy(states)
    result = validate_binding(hass, binding, device_for=devices.get)
    assert result == {**binding, "companion_device_id": "synthetic-alarm-device"}
    assert pending_controls(hass, result) == [
        ("number", "set_value", {"entity_id": "number.example_duration", "value": 1800}),
        ("select", "select_option", {"entity_id": "select.example_volume", "option": "high"}),
    ]
    assert states == before
    states["number.example_duration"].state = "1800.0"
    states["select.example_volume"].state = "high"
    assert pending_controls(hass, result) == []


def test_plain_native_siren_remains_supported_without_registry(binding_harness):
    hass, _, _, _ = binding_harness
    result = validate_binding(hass, {"entity_id": "siren.example", "confirmed": True})
    assert result == {"entity_id": "siren.example", "confirmed": True, "volume": 0.5}
    assert pending_controls(hass, result) == []


@pytest.mark.parametrize("value", [True, None, "NaN", float("inf"), -1, 1.1, {}])
def test_invalid_native_volume_rejected(binding_harness, value):
    hass, _, devices, binding = binding_harness
    binding["volume"] = value
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, binding, device_for=devices.get)


@pytest.mark.parametrize("value", [True, "NaN", float("inf"), 0, 59, 1801, 120.5, {}])
def test_duration_bounds_are_not_silently_coerced(binding_harness, value):
    hass, _, devices, binding = binding_harness
    binding["duration_seconds"] = value
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, binding, device_for=devices.get)


@pytest.mark.parametrize(
    "attributes", [{"min": 60, "max": 120}, {"step": 0}, {"step": "NaN"}, {"min": 61, "step": 2}]
)
def test_device_duration_range_step_checked(binding_harness, attributes):
    hass, states, devices, binding = binding_harness
    states["number.example_duration"].attributes.update(attributes)
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, binding, device_for=devices.get)


@pytest.mark.parametrize("value", [None, 1, [], {}, "loud", "HIGH"])
def test_volume_option_is_exact_and_bounded(binding_harness, value):
    hass, _, devices, binding = binding_harness
    binding["select_volume"] = value
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, binding, device_for=devices.get)


@pytest.mark.parametrize(
    "key", ["siren.example", "number.example_duration", "select.example_volume"]
)
def test_missing_unavailable_and_cross_device_companions_fail_closed(binding_harness, key):
    hass, states, devices, binding = binding_harness
    original = states[key]
    states[key].state = "unavailable"
    with pytest.raises(DomainError, match="device_unavailable"):
        validate_binding(hass, binding, device_for=devices.get)
    states.pop(key)
    with pytest.raises(DomainError, match="device_unavailable"):
        validate_binding(hass, binding, device_for=devices.get)
    states[key] = original
    original.state = "off" if key.startswith("siren.") else "60"
    devices[key] = "another-device"
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, binding, device_for=devices.get)


def test_device_pin_prevents_reuse_after_registry_replacement(binding_harness):
    hass, _, devices, binding = binding_harness
    checked = validate_binding(hass, binding, device_for=devices.get)
    devices.update(dict.fromkeys(devices, "replacement-device"))
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, checked, device_for=devices.get)


def test_empty_companions_clear_explicit_fields(binding_harness):
    hass, _, devices, binding = binding_harness
    binding.update(duration_entity_id="", volume_entity_id="")
    assert validate_binding(hass, binding, device_for=devices.get) == {
        "entity_id": "siren.example",
        "confirmed": True,
        "volume": 0.7,
    }


def test_unrelated_control_domain_and_missing_registry_rejected(binding_harness):
    hass, _, devices, binding = binding_harness
    devices.clear()
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, binding, device_for=devices.get)
    binding["entity_id"] = "switch.example"
    with pytest.raises(DomainError, match="device_unsupported"):
        validate_binding(hass, binding, device_for=devices.get)
