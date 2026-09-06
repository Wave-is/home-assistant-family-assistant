"""Opt-in read-only HA calendar. Private family records never become entity attributes."""

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .domain.family_calendar import configuration, published
from .domain.validation import DomainError


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    added = False

    @callback
    def maybe_add():
        nonlocal added
        state = runtime.engine.snapshot()
        if (
            not added
            and "calendar" in state["settings"]["modules"]
            and configuration(state)["publish_to_ha"]
        ):
            added = True
            async_add_entities([FamilyCalendar(entry)])

    runtime.listeners.add(maybe_add)
    entry.async_on_unload(lambda: runtime.listeners.discard(maybe_add))
    maybe_add()


def event_from_record(record):
    parser = date.fromisoformat if record["all_day"] else datetime.fromisoformat
    return CalendarEvent(
        start=parser(record["start"]),
        end=parser(record["end"]),
        summary=record["title"],
        description=record["description"] or None,
        location=record["location"] or None,
        uid=record["id"],
    )


class FamilyCalendar(CalendarEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "family_calendar"
    _attr_icon = "mdi:calendar-heart"
    _attr_supported_features = 0

    def __init__(self, entry):
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_family_calendar"
        self._event = None
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Family Assistant",
            model="Household",
        )

    @property
    def event(self):
        return self._event

    @callback
    def _refresh(self, *_):
        state = self._runtime.engine.snapshot()
        self._event = None
        self._attr_available = (
            "calendar" in state["settings"]["modules"] and configuration(state)["publish_to_ha"]
        )
        if self._attr_available:
            now = dt_util.utcnow()
            try:
                records = published(
                    state, now, now + timedelta(days=366), self.hass.config.time_zone
                )
                self._event = event_from_record(records[0]) if records else None
            except DomainError:
                self._attr_available = False
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._runtime.listeners.add(self._refresh)
        self.async_on_remove(lambda: self._runtime.listeners.discard(self._refresh))
        self.async_on_remove(
            async_track_time_interval(self.hass, self._refresh, timedelta(minutes=1))
        )
        self._refresh()

    async def async_get_events(self, hass, start_date, end_date):
        try:
            return [
                event_from_record(record)
                for record in published(
                    self._runtime.engine.snapshot(), start_date, end_date, hass.config.time_zone
                )
            ]
        except DomainError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=err.code) from err
