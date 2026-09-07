"""Counts only. Private records are served by the authorized WebSocket API."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .domain.task_access import personal_task


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FamilyStatusSensor(entry)])


class FamilyStatusSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "pending_actions"
    _attr_icon = "mdi:account-group-outline"

    def __init__(self, entry):
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_pending_actions"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Family Assistant",
            model="Household",
        )

    @property
    def native_value(self):
        state = self._runtime.engine.snapshot()
        return sum(
            task["status"] not in {"completed", "archived", "cancelled"}
            for task in state["tasks"].values()
            if not personal_task(task)
        )

    async def async_added_to_hass(self):
        self._runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self._runtime.listeners.discard(self.async_write_ha_state))
