"""Hydrated native alarm forms use the real read-only companion validator."""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from test_provider_options import native  # noqa: F401
from test_school_reminder_options import config_flow  # noqa: F401


@pytest.fixture
def alarm(native, monkeypatch):  # noqa: F811
    flow, entry, runtime, user = native
    siren = ModuleType("homeassistant.components.siren")
    siren.SirenEntityFeature = SimpleNamespace(TURN_ON=1, TURN_OFF=2)
    monkeypatch.setitem(sys.modules, siren.__name__, siren)
    selector = sys.modules["homeassistant.helpers.selector"]
    selector.EntitySelectorConfig = dict
    selector.EntitySelector = lambda config: str
    states = {
        "siren.synthetic": SimpleNamespace(state="off", attributes={"supported_features": 3}),
        "number.synthetic_duration": SimpleNamespace(
            state="60", attributes={"min": 60, "max": 1800, "step": 1}
        ),
        "select.synthetic_volume": SimpleNamespace(
            state="low", attributes={"options": ["low", "middle", "high"]}
        ),
    }
    devices = {key: "synthetic-alarm-device" for key in states}
    registry = ModuleType("homeassistant.helpers.entity_registry")
    registry.async_get = lambda hass: SimpleNamespace(
        async_get=lambda key: SimpleNamespace(device_id=devices.get(key))
    )
    monkeypatch.setitem(sys.modules, registry.__name__, registry)
    flow.hass.states = SimpleNamespace(get=states.get)
    return flow, entry, runtime, user, states, devices


def binding():
    return {
        "entity_id": "siren.synthetic",
        "volume": 0.7,
        "confirmed": True,
        "duration_entity_id": "number.synthetic_duration",
        "duration_seconds": 420,
        "volume_entity_id": "select.synthetic_volume",
        "select_volume": "middle",
        "companion_device_id": "synthetic-alarm-device",
    }


async def selected(flow, member="child"):
    pick = await flow.async_step_alarm_device()
    assert {key.schema for key in pick["data_schema"].schema} == {"member"}
    form = await flow.async_step_alarm_device({"member": member})
    assert form["step_id"] == "alarm_device_settings", form
    return form


async def test_selected_member_hydrates_exact_binding_without_actuating(alarm, store):
    flow, entry, *_ = alarm
    entry.options = {"alarm_devices": {"child": binding()}, "unrelated": {"keep": True}}
    form = await selected(flow)
    values = form["data_schema"]({"confirmed": True})
    assert values["volume"] == 0.7 and values["duration_seconds"] == 420
    assert values["select_volume"] == "middle" and "member" not in values
    writes = store.calls
    result = await flow.async_step_alarm_device_settings(values)
    assert result["data"] == entry.options and store.calls == writes


async def test_volume_schema_coerces_number_but_rejects_boolean(alarm):
    import voluptuous as vol

    flow, *_ = alarm
    form = await selected(flow)
    validator = next(
        value for key, value in form["data_schema"].schema.items() if key.schema == "volume"
    )
    # The actual HTTP serializer is exercised by the native HA settings case.
    assert isinstance(validator.validators[0], vol.Coerce)
    assert validator(0.6) == 0.6
    with pytest.raises(vol.Invalid):
        validator(True)


@pytest.mark.parametrize("change", ["device", "unavailable", "range", "volume", "unconfirmed"])
async def test_companion_capability_checks_reject_without_options_write(alarm, change):
    flow, entry, _, _, states, devices = alarm
    await selected(flow)
    values = {key: value for key, value in binding().items() if key != "companion_device_id"}
    values["enabled"] = True
    if change == "device":
        devices["number.synthetic_duration"] = "unrelated-device"
    elif change == "unavailable":
        states["select.synthetic_volume"].state = "unavailable"
    elif change == "range":
        values["duration_seconds"] = 2000
    elif change == "volume":
        values["select_volume"] = "silent"
    else:
        values["confirmed"] = False
    result = await flow.async_step_alarm_device_settings(values)
    assert result["type"] == "form" and result["errors"]
    assert entry.options == {}


async def test_explicit_clear_companion_preserves_other_output_settings(alarm):
    flow, entry, *_ = alarm
    entry.options = {"alarm_devices": {"child": binding()}}
    form = await selected(flow)
    values = form["data_schema"]({"confirmed": True, "clear_duration": True})
    result = await flow.async_step_alarm_device_settings(values)
    saved = result["data"]["alarm_devices"]["child"]
    assert "duration_entity_id" not in saved and "duration_seconds" not in saved
    assert (
        saved["volume_entity_id"] == binding()["volume_entity_id"]
        and saved["select_volume"] == "middle"
    )


async def test_companion_already_owned_by_another_member_is_rejected(alarm):
    flow, entry, *_ = alarm
    entry.options = {"alarm_devices": {"parent": binding()}}
    await selected(flow)
    result = await flow.async_step_alarm_device_settings({**binding(), "enabled": True})
    assert result["errors"]["base"] == "device_already_assigned"


@pytest.mark.parametrize("drift", ["member", "options"])
async def test_selected_member_revision_and_displayed_options_cannot_be_rebased(alarm, now, drift):
    flow, entry, runtime, *_ = alarm
    entry.options = {"alarm_devices": {"child": binding()}}
    await selected(flow)
    if drift == "member":
        await runtime.engine.system_update(
            "rename-child", now, lambda ctx: ctx.state["members"]["child"].update(revision=2)
        )
    else:
        entry.options = {**entry.options, "newer": True}
    result = await flow.async_step_alarm_device_settings({"enabled": False})
    assert result == {"type": "abort", "reason": "conflict"}
    assert "child" in entry.options["alarm_devices"]


async def test_disable_needs_no_available_hardware_and_removes_only_selected_binding(alarm):
    flow, entry, _, _, states, _ = alarm
    entry.options = {"alarm_devices": {"child": binding(), "parent": {"keep": True}}}
    await selected(flow)
    states.clear()
    result = await flow.async_step_alarm_device_settings({"enabled": False})
    assert result["data"]["alarm_devices"] == {"parent": {"keep": True}}
