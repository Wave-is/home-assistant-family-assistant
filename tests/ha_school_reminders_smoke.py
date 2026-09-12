"""Actual HA acceptance for opt-in private school preparation reminders."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import voluptuous as vol
from aiohttp import ClientSession
from ha_options_menu import select_option


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/school-reminder-smoke"
    )
    token = hass.auth.async_create_access_token(refresh)
    session = ClientSession()
    try:
        ws = await session.ws_connect("http://127.0.0.1:8123/api/websocket")
        assert (await ws.receive_json())["type"] == "auth_required"
        await ws.send_json({"type": "auth", "access_token": token})
        assert (await ws.receive_json())["type"] == "auth_ok"
        yield ws
        await ws.close()
    finally:
        await session.close()
        hass.auth.async_remove_refresh_token(refresh)


async def _request(hass, entry, user, identifier, action, payload, operation):
    async with _socket(hass, user) as ws:
        await ws.send_json(
            {
                "id": identifier,
                "type": "family_assistant/execute",
                "entry_id": entry.entry_id,
                "action": action,
                "payload": payload,
                "operation_id": operation,
            }
        )
        return await ws.receive_json()


async def _view(hass, entry, user, identifier):
    async with _socket(hass, user) as ws:
        await ws.send_json(
            {
                "id": identifier,
                "type": "family_assistant/view",
                "entry_id": entry.entry_id,
            }
        )
        return await ws.receive_json()


async def _general(hass, entry, user):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    assert flow["type"] == "menu", flow
    return await select_option(hass, flow, "general")


async def _save_general(hass, entry, user, **changes):
    from custom_components.family_assistant.config_flow import CONFIGURABLE_MODULES

    form = await _general(hass, entry, user)
    if form["type"] == "abort":
        return form
    assert form["type"] == "form" and form["step_id"] == "general", form
    settings = entry.runtime_data.engine.snapshot()["settings"]
    values = {
        "name": settings["name"],
        "language": settings["language"],
        "timezone": settings["timezone"],
        "automatic_penalties": settings.get("automatic_penalties", False),
        "daily_penalty_cap": settings.get("daily_penalty_cap", 1),
        "pantry_expiry_reminders": settings.get("pantry_expiry_reminders", False),
        "pantry_expiry_days": settings.get("pantry_expiry_days", 3),
        "school_preparation_reminders": settings.get("school_preparation_reminders", False),
        "school_preparation_days_before": settings.get("school_preparation_days_before", 1),
        "school_preparation_time": settings.get("school_preparation_time", "20:00"),
        **{module: module in settings["modules"] for module in CONFIGURABLE_MODULES},
        **changes,
    }
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    await hass.async_block_till_done()
    return result


def _member_payload(member, *, role=None):
    return {
        "id": member["id"],
        "revision": member["revision"],
        "name": member["name"],
        "role": role or member["role"],
        "ha_user_id": member.get("ha_user_id"),
    }


async def verify_school_reminders(hass, owner):
    """Verify isolated Options, WebSocket, scheduling, privacy and persistence."""
    from custom_components.family_assistant.domain import recurrence, school_reminders
    from custom_components.family_assistant.scheduler import Scheduler

    flow = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner.id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Synthetic school reminder household",
            "owner_name": "Reminder owner",
            "language": "en",
            "timezone": "Europe/Kyiv",
            "template": "manual",
        },
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"school": True, "routines": True}
    )
    entry = flow["result"]
    await hass.async_block_till_done()
    child_user = None
    try:
        runtime = entry.runtime_data
        await runtime.scheduler.stop()
        await hass.async_block_till_done()
        engine = runtime.engine

        defaults_form = await _general(hass, entry, owner)
        assert defaults_form["type"] == "form", defaults_form
        defaults = dict(defaults_form["data_schema"]({}))
        assert defaults["school_preparation_reminders"] is False
        assert defaults["school_preparation_days_before"] == 1
        assert defaults["school_preparation_time"] == "20:00"
        for changes in (
            {"school_preparation_days_before": 2},
            {"school_preparation_days_before": True},
            {"school_preparation_time": "24:00"},
        ):
            try:
                defaults_form["data_schema"]({**defaults, **changes})
            except vol.Invalid:
                pass
            else:
                raise AssertionError("school reminder Options accepted invalid policy")

        child_user = await hass.auth.async_create_user("Synthetic isolated school reminder child")
        child = await engine.execute(
            "owner",
            "members.save",
            {
                "name": "Reminder child",
                "role": "child",
                "ha_user_id": child_user.id,
            },
            "school-reminder-child",
            datetime.now(UTC),
        )
        child_id = child["id"]
        child_record = engine.snapshot()["members"][child_id]

        denied = await _general(hass, entry, child_user)
        assert denied["type"] == "abort" and denied["reason"] == "forbidden"
        enabled = await _save_general(
            hass,
            entry,
            owner,
            school=True,
            routines=True,
            school_preparation_reminders=True,
            school_preparation_days_before=1,
            school_preparation_time="20:00",
        )
        assert enabled["type"] == "create_entry", enabled

        routine = await engine.execute(
            "owner",
            "routines.save",
            {
                "title": "SYNTHETIC_PRIVATE_REMINDER_ROUTINE",
                "description": "Private routine details",
                "assignees": [child_id],
                "steps": [{"title": "SYNTHETIC_PRIVATE_PACK_BOOKS"}],
            },
            "school-reminder-routine",
            datetime.now(UTC),
        )
        zone = ZoneInfo(engine.snapshot()["settings"]["timezone"])
        local_today = datetime.now(UTC).astimezone(zone).date()
        lesson_day = local_today + timedelta(days=1)
        timetable = await engine.execute(
            "owner",
            "school.timetable_save",
            {
                "member": child_id,
                "member_revision": child_record["revision"],
                "title": "SYNTHETIC_PRIVATE_REMINDER_TIMETABLE",
                "valid_from": local_today.isoformat(),
                "valid_until": (lesson_day + timedelta(days=7)).isoformat(),
                "exceptions": [],
                "lessons": [
                    {
                        "weekday": lesson_day.weekday(),
                        "start": "08:30",
                        "end": "09:15",
                        "subject": "SYNTHETIC_PRIVATE_REMINDER_SUBJECT",
                        "room": "Private room",
                        "materials": ["SYNTHETIC_PRIVATE_REMINDER_MATERIAL"],
                    }
                ],
                "backpack_routine": {
                    "id": routine["id"],
                    "revision": routine["revision"],
                },
            },
            "school-reminder-timetable",
            datetime.now(UTC),
        )

        owner_record = engine.snapshot()["members"]["owner"]
        owner_request = {
            "member": child_id,
            "member_revision": child_record["revision"],
            "recipient_revision": owner_record["revision"],
            "subscription_revision": None,
            "enabled": True,
        }
        owner_subscription = await _request(
            hass,
            entry,
            owner,
            1,
            "school.preparation_reminder_access_set",
            owner_request,
            "school-reminder-owner-subscribe",
        )
        assert owner_subscription["success"], owner_subscription
        assert owner_subscription["result"] == {
            "member": child_id,
            "enabled": True,
            "revision": 1,
        }
        stale_before = engine.snapshot()
        stale = await _request(
            hass,
            entry,
            owner,
            2,
            "school.preparation_reminder_access_set",
            {**owner_request, "recipient_revision": owner_record["revision"] + 1},
            "school-reminder-stale-recipient",
        )
        assert not stale["success"] and stale["error"]["code"] == "conflict"
        assert engine.snapshot() == stale_before

        child_request = {
            "member": child_id,
            "member_revision": child_record["revision"],
            "recipient_revision": child_record["revision"],
            "subscription_revision": None,
            "enabled": True,
        }
        child_subscription = await _request(
            hass,
            entry,
            child_user,
            3,
            "school.preparation_reminder_access_set",
            child_request,
            "school-reminder-child-subscribe",
        )
        assert child_subscription["success"], child_subscription
        assert child_subscription["result"]["revision"] == 1
        owner_view = await _view(hass, entry, owner, 10)
        child_view = await _view(hass, entry, child_user, 11)
        assert owner_view["success"] and child_view["success"]
        owner_targets = owner_view["result"]["school"]["preparation_reminders"]
        child_targets = child_view["result"]["school"]["preparation_reminders"]
        assert owner_targets["policy"] == {
            "enabled": True,
            "days_before": 1,
            "time": "20:00",
            "timezone": "Europe/Kyiv",
        }
        assert owner_targets["self_targets"] == [
            {
                "member": child_id,
                "member_revision": child_record["revision"],
                "recipient_revision": owner_record["revision"],
                "enabled": True,
                "subscription_revision": 1,
            }
        ]
        assert child_targets["self_targets"] == [
            {
                "member": child_id,
                "member_revision": child_record["revision"],
                "recipient_revision": child_record["revision"],
                "enabled": True,
                "subscription_revision": 1,
            }
        ]

        await hass.async_block_till_done()
        scheduler = Scheduler(hass, entry, runtime)
        trigger = recurrence.local_clock(
            local_today,
            "20:00",
            engine.snapshot()["settings"]["timezone"],
        )
        assert trigger is not None
        trigger_utc = trigger.astimezone(UTC)
        before_tick = deepcopy(
            {
                key: engine.snapshot()[key]
                for key in ("tasks", "routine_runs", "court", "shopping", "pantry")
            }
        )
        await scheduler.run(trigger_utc - timedelta(seconds=1))
        assert engine.snapshot()["outbox"] == {}
        await scheduler.run(trigger_utc)
        events = [
            event
            for event in engine.snapshot()["outbox"].values()
            if event["key"] == school_reminders.KEY
        ]
        assert len(events) == 2
        assert {event["recipient"] for event in events} == {"owner", child_id}
        canaries = {
            "SYNTHETIC_PRIVATE_REMINDER_ROUTINE",
            "SYNTHETIC_PRIVATE_PACK_BOOKS",
            "SYNTHETIC_PRIVATE_REMINDER_TIMETABLE",
            "SYNTHETIC_PRIVATE_REMINDER_SUBJECT",
            "SYNTHETIC_PRIVATE_REMINDER_MATERIAL",
            "Private room",
        }
        for event in events:
            assert set(event["data"]) == school_reminders.EVENT_FIELDS
            assert not any(canary in str(event) for canary in canaries)
            assert school_reminders.delivery_allowed(
                engine.snapshot(), event, trigger_utc + timedelta(minutes=1)
            )
        assert {key: engine.snapshot()[key] for key in before_tick} == before_tick
        await scheduler.run(trigger_utc + timedelta(minutes=1))
        assert (
            len(
                [
                    event
                    for event in engine.snapshot()["outbox"].values()
                    if event["key"] == school_reminders.KEY
                ]
            )
            == 2
        )

        owner_event = next(event for event in events if event["recipient"] == "owner")
        child_event = next(event for event in events if event["recipient"] == child_id)
        disabled_subscription = await _request(
            hass,
            entry,
            owner,
            4,
            "school.preparation_reminder_access_set",
            {
                **owner_request,
                "subscription_revision": owner_subscription["result"]["revision"],
                "enabled": False,
            },
            "school-reminder-owner-disable",
        )
        assert disabled_subscription["success"], disabled_subscription
        current = engine.snapshot()
        assert not school_reminders.delivery_allowed(current, owner_event, trigger_utc)
        assert school_reminders.delivery_allowed(current, child_event, trigger_utc)

        policy_changed = await _save_general(
            hass,
            entry,
            owner,
            school=True,
            routines=True,
            school_preparation_reminders=True,
            school_preparation_days_before=0,
            school_preparation_time="20:00",
        )
        assert policy_changed["type"] == "create_entry", policy_changed
        assert not school_reminders.delivery_allowed(engine.snapshot(), child_event, trigger_utc)
        policy_restored = await _save_general(
            hass,
            entry,
            owner,
            school=True,
            routines=True,
            school_preparation_reminders=True,
            school_preparation_days_before=1,
            school_preparation_time="20:00",
        )
        assert policy_restored["type"] == "create_entry", policy_restored
        assert school_reminders.delivery_allowed(engine.snapshot(), child_event, trigger_utc)
        routines_disabled = await _save_general(
            hass,
            entry,
            owner,
            school=True,
            routines=False,
            school_preparation_reminders=True,
            school_preparation_days_before=1,
            school_preparation_time="20:00",
        )
        assert routines_disabled["type"] == "create_entry", routines_disabled
        assert not school_reminders.delivery_allowed(engine.snapshot(), child_event, trigger_utc)
        routines_restored = await _save_general(
            hass,
            entry,
            owner,
            school=True,
            routines=True,
            school_preparation_reminders=True,
            school_preparation_days_before=1,
            school_preparation_time="20:00",
        )
        assert routines_restored["type"] == "create_entry", routines_restored
        assert school_reminders.delivery_allowed(engine.snapshot(), child_event, trigger_utc)

        stored_table = engine.snapshot()["school"]["timetables"][timetable["id"]]
        edited = await engine.execute(
            "owner",
            "school.timetable_save",
            {
                "id": stored_table["id"],
                "revision": stored_table["revision"],
                "member": child_id,
                "member_revision": child_record["revision"],
                "title": stored_table["title"] + " revised",
                "valid_from": stored_table["valid_from"],
                "valid_until": stored_table["valid_until"],
                "exceptions": stored_table["exceptions"],
                "lessons": stored_table["lessons"],
                "backpack_routine": stored_table["backpack_routine"],
            },
            "school-reminder-source-edit",
            datetime.now(UTC),
        )
        assert edited["revision"] > timetable["revision"]
        assert not school_reminders.delivery_allowed(engine.snapshot(), child_event, trigger_utc)

        disabled_module = await _save_general(
            hass,
            entry,
            owner,
            school=False,
            routines=True,
            school_preparation_reminders=True,
            school_preparation_days_before=1,
            school_preparation_time="20:00",
        )
        assert disabled_module["type"] == "create_entry", disabled_module
        replay = await _request(
            hass,
            entry,
            owner,
            5,
            "school.preparation_reminder_access_set",
            owner_request,
            "school-reminder-owner-subscribe",
        )
        assert not replay["success"] and replay["error"]["code"] == "module_disabled"
        restored_module = await _save_general(
            hass,
            entry,
            owner,
            school=True,
            routines=True,
            school_preparation_reminders=True,
            school_preparation_days_before=1,
            school_preparation_time="20:00",
        )
        assert restored_module["type"] == "create_entry", restored_module

        expected = deepcopy(engine.snapshot()["school"])
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        restored = entry.runtime_data.engine.snapshot()
        assert restored["settings"]["school_preparation_reminders"] is True
        assert restored["settings"]["school_preparation_days_before"] == 1
        assert restored["settings"]["school_preparation_time"] == "20:00"
        assert restored["school"] == expected
        print(
            "PASS: actual HA school reminder Options, WebSocket subscriptions, "
            "private clock intents, revocation and Store reload"
        )
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
