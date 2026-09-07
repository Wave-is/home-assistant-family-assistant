"""Real CalendarEntity reads and authenticated, non-mutating school previews."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo


async def verify_school_import(hass, entry, owner, child_id):
    from ha_school_smoke import _general, _request, _socket
    from homeassistant.auth.const import GROUP_ID_ADMIN
    from homeassistant.components.calendar import DATA_COMPONENT, CalendarEntity, CalendarEvent
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util

    from custom_components.family_assistant.domain.school import _lessons
    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.school_import_api import _source

    class SyntheticCalendar(CalendarEntity):
        _attr_name = "Synthetic school import"
        _attr_unique_id = "synthetic-school-import"
        _attr_should_poll = False
        _attr_event = None

        def __init__(self):
            self.calls = []
            self.events = []
            self.hook = None

        async def async_get_events(self, _hass, start_date, end_date):
            self.calls.append((start_date, end_date))
            if self.hook:
                await self.hook()
            return self.events

    assert await async_setup_component(hass, "calendar", {})
    calendar = SyntheticCalendar()
    await hass.data[DATA_COMPONENT].async_add_entities([calendar])
    enabled = await _general(hass, entry, owner, school=True)
    assert enabled["type"] == "create_entry"
    runtime = entry.runtime_data
    state = runtime.engine.snapshot()
    zone = ZoneInfo(state["settings"]["timezone"])
    today = datetime.now(UTC).astimezone(zone).date()
    monday = today - timedelta(days=today.weekday())
    start = datetime.combine(monday, datetime.min.time(), zone) + timedelta(hours=9)
    calendar.events = [
        CalendarEvent(
            start=start,
            end=start + timedelta(minutes=45),
            summary="Synthetic calendar lesson",
            location="12",
        )
    ]

    async def request(user, **changes):
        async with _socket(hass, user) as ws:
            await ws.send_json(
                {
                    "id": 1,
                    "type": "family_assistant/school_calendar_preview",
                    "entry_id": entry.entry_id,
                    "entity_id": calendar.entity_id,
                    "week_start": monday.isoformat(),
                    **changes,
                }
            )
            return await ws.receive_json()

    result = await request(owner)
    assert result["success"], result.get("error", {}).get("code")
    proposal = result["result"]
    assert (
        proposal["saved"] is False
        and proposal["valid_until"] == (monday + timedelta(days=6)).isoformat()
    )
    assert proposal["lessons"] == _lessons(proposal["lessons"]) and proposal["count"] == 1
    assert runtime.engine.snapshot() == state
    assert calendar.calls == [
        (
            datetime.combine(monday, datetime.min.time(), zone),
            datetime.combine(monday + timedelta(days=7), datetime.min.time(), zone),
        )
    ]
    assert calendar.calls[0][0].tzinfo is dt_util.DEFAULT_TIME_ZONE
    child = await hass.auth.async_get_user(state["members"][child_id]["ha_user_id"])
    outsider = await hass.auth.async_create_user(
        "Synthetic unlinked import admin", group_ids=[GROUP_ID_ADMIN]
    )
    for user in (child, outsider):
        denied = await request(user)
        assert not denied["success"] and denied["error"]["code"] == "forbidden"
    assert len(calendar.calls) == 1
    # Explicit source permission is required independently of family parenthood.
    denied_user = SimpleNamespace(
        is_active=True, permissions=SimpleNamespace(check_entity=lambda *_: False)
    )
    try:
        _source(hass, denied_user, calendar.entity_id)
    except DomainError as error:
        assert error.code == "forbidden"
    else:
        raise AssertionError("calendar read permission was bypassed")
    invalid = await request(owner, week_start=(monday + timedelta(days=1)).isoformat())
    assert not invalid["success"] and len(calendar.calls) == 1
    invalid = await request(owner, week_start=(monday + timedelta(weeks=100)).isoformat())
    assert not invalid["success"] and len(calendar.calls) == 1
    calendar.events = [
        CalendarEvent(start=monday, end=monday + timedelta(days=1), summary="Synthetic all-day")
    ]
    invalid = await request(owner)
    assert not invalid["success"] and invalid["error"]["code"] == "invalid_field"
    calendar.events = [
        CalendarEvent(
            start=start, end=start + timedelta(minutes=45), summary="PRIVATE RESULT MUST NOT ESCAPE"
        )
    ]
    parent_row = next(
        row
        for row in state["members"].values()
        if row["role"] == "parent" and row.get("ha_user_id")
    )
    parent = await hass.auth.async_get_user(parent_row["ha_user_id"])

    async def revoke():
        await hass.auth.async_update_user(parent, is_active=False)

    calendar.hook = revoke
    try:
        denied = await request(parent)
        assert not denied["success"] and denied["error"]["code"] == "forbidden"
        assert "PRIVATE RESULT" not in str(denied)
    finally:
        await hass.auth.async_update_user(parent, is_active=True)
        calendar.hook = None
    assert not hass.data["family_assistant"].get("school_calendar_inflight")
    assert runtime.engine.snapshot() == state
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold():
        entered.set()
        await release.wait()

    calendar.hook = hold
    first = asyncio.create_task(request(owner))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        second = await request(owner)
        assert not second["success"] and second["error"]["code"] == "not_ready"
        assert hass.data["family_assistant"]["school_calendar_inflight"]
    finally:
        release.set()
        await asyncio.wait_for(first, 10)
        calendar.hook = None
    assert first.result()["success"]
    assert not hass.data["family_assistant"].get("school_calendar_inflight")
    assert runtime.engine.snapshot() == state

    # Only a separate ordinary, explicitly reviewed command persists the proposal.
    target = await _request(
        hass,
        entry,
        owner,
        6200,
        "members.save",
        {"name": "Synthetic calendar-import child", "role": "child"},
        "school-import-child",
    )
    assert target["success"]
    target = target["result"]
    payload = {
        "member": target["id"],
        "member_revision": target["revision"],
        "title": "Synthetic reviewed calendar week",
        "valid_from": proposal["valid_from"],
        "valid_until": proposal["valid_until"],
        "lessons": proposal["lessons"],
        "exceptions": [],
        "backpack_routine": None,
    }
    saved = await _request(
        hass, entry, owner, 6201, "school.timetable_save", payload, "school-import-reviewed-save"
    )
    assert saved["success"]
    replay = await _request(
        hass, entry, owner, 6202, "school.timetable_save", payload, "school-import-reviewed-save"
    )
    assert replay["success"] and replay["result"] == saved["result"]
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.const import SCHEMA_VERSION

    stored = await Store(hass, SCHEMA_VERSION, f"family_assistant.{entry.entry_id}").async_load()
    record = stored["school"]["timetables"][saved["result"]["id"]]
    assert (
        record["lessons"] == proposal["lessons"]
        and record["valid_until"] == proposal["valid_until"]
    )
    archived = await _request(
        hass,
        entry,
        owner,
        6203,
        "school.timetable_archive",
        {
            "id": record["id"],
            "revision": record["revision"],
            "reason": "Synthetic test completed",
        },
        "school-import-reviewed-archive",
    )
    assert archived["success"]
    print(
        "PASS: actual HA calendar week preview, parent/child identity, "
        "read scope/revocation/concurrency; separate reviewed save/Store/replay; no source writes"
    )
    return target["id"]
