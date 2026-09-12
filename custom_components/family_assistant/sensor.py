"""Counts only. Private records are served by the authorized WebSocket API."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .domain.task_access import personal_task


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    known = set()
    async_add_entities([FamilyStatusSensor(entry)])

    def discover():
        state = runtime.engine.snapshot()
        if "court" not in state["settings"]["modules"]:
            return
        additions = []
        for member in state["members"].values():
            if member["role"] == "child" and member.get("active") and member["id"] not in known:
                known.add(member["id"])
                additions.append(FamilyCourtSensor(entry, member["id"]))
        if additions:
            async_add_entities(additions)

    discover()
    runtime.listeners.add(discover)
    entry.async_on_unload(lambda: runtime.listeners.discard(discover))


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


class FamilyCourtSensor(SensorEntity):
    """Optional HA-visible score; private defaults remain in the authorized panel."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_icon = "mdi:gavel"
    # HA states do not inherit the household's per-member WebSocket permissions.
    # Owners may opt in, but adding a child must not publish private points to
    # every HA account automatically. Existing explicit entity choices survive.
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry, child: str) -> None:
        self._runtime = entry.runtime_data
        self._child = child
        self.entity_id = f"sensor.family_court_{child}"
        self._attr_unique_id = f"{entry.entry_id}_family_court_{child}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Family Assistant",
            model="Household",
        )

    def _get_stats(self):
        from .court import calculate_court_stats
        from .domain.court_weekly import configuration

        state = self._runtime.engine.snapshot()
        tz = state.get("settings", {}).get("timezone", "UTC")
        policy = configuration(state)
        return calculate_court_stats(
            state.get("court", {}),
            timezone=tz,
            members=state.get("members", {}).values(),
            weekday=policy["weekday"],
            time_str=policy["time"],
        )

    @property
    def name(self):
        state = self._runtime.engine.snapshot()
        member = state["members"].get(self._child, {})
        label = {"en": "Family court", "ru": "Семейный суд", "uk": "Сімейний суд"}.get(
            state["settings"].get("language"), "Family court"
        )
        return f"{label}: {member.get('name', self._child)}"

    @property
    def available(self):
        state = self._runtime.engine.snapshot()
        member = state["members"].get(self._child, {})
        return (
            "court" in state["settings"]["modules"]
            and member.get("active", False)
            and member.get("role") == "child"
        )

    @property
    def native_value(self) -> int:
        summary = self._get_stats()
        return summary.stats.get(self._child, {}).get("balance", 0)

    @property
    def extra_state_attributes(self) -> dict:
        summary = self._get_stats()
        child_stats = summary.stats.get(self._child, {})
        return {
            "pluses": child_stats.get("pluses", 0),
            "minuses": child_stats.get("minuses", 0),
            "balance": child_stats.get("balance", 0),
            "penalty_points": child_stats.get("penalty_points", 0),
            "week_id": summary.week_id,
        }

    async def async_added_to_hass(self):
        self._runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self._runtime.listeners.discard(self.async_write_ha_state))
