"""Actual HA Options Flow, service, scheduler and reload checks for expiry reminders."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import voluptuous as vol
from ha_options_menu import select_option
from homeassistant.core import Context


async def _general(hass, entry, user):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    return await select_option(hass, flow, "general")


async def verify_pantry_expiry(hass, owner):
    """Use a second synthetic household; never change the other smoke scenarios."""
    from custom_components.family_assistant.scheduler import Scheduler

    flow = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner.id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Synthetic pantry reminder household",
            "owner_name": "Parent",
            "language": "uk",
            "timezone": "Europe/Kyiv",
            "template": "manual",
        },
    )
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"pantry": True})
    entry = flow["result"]
    await hass.async_block_till_done()
    try:
        runtime = entry.runtime_data
        # Suspend only this synthetic household's interval. The real Scheduler
        # below is manually clocked; no production devices are bound or mounted.
        await runtime.scheduler.stop()
        engine = runtime.engine
        form = await _general(hass, entry, owner)
        defaults = dict(form["data_schema"]({}))
        assert defaults["pantry_expiry_reminders"] is False
        assert defaults["pantry_expiry_days"] == 3
        for invalid in (-1, 31, 1.5, "2"):
            try:
                form["data_schema"]({**defaults, "pantry_expiry_days": invalid})
            except vol.Invalid:
                pass
            else:
                raise AssertionError("expiry lead form silently coerced an invalid value")

        before = engine.snapshot()
        rejected = await hass.config_entries.options.async_configure(
            form["flow_id"], {**defaults, "pantry_expiry_days": True}
        )
        assert rejected["type"] == "form" and rejected["errors"]["base"] == "invalid_field"
        assert engine.snapshot() == before
        enabled = await hass.config_entries.options.async_configure(
            form["flow_id"],
            {**defaults, "pantry_expiry_reminders": True, "pantry_expiry_days": 0},
        )
        assert enabled["type"] == "create_entry", enabled
        assert engine.snapshot()["settings"]["pantry_expiry_days"] == 0

        # An unrelated supported settings command does not reset the opt-in.
        settings = engine.snapshot()["settings"]
        await engine.execute(
            "owner",
            "settings.save",
            {"name": settings["name"], "language": "en", "modules": settings["modules"]},
            "expiry-unrelated-settings",
            datetime.now(UTC),
        )
        form = await _general(hass, entry, owner)
        fresh = dict(form["data_schema"]({}))
        assert fresh["pantry_expiry_reminders"] is True and fresh["pantry_expiry_days"] == 0
        saved = await hass.config_entries.options.async_configure(form["flow_id"], fresh)
        assert saved["type"] == "create_entry", saved

        other = await hass.auth.async_create_user("Synthetic unlinked pantry observer")
        denied = await _general(hass, entry, other)
        assert denied["type"] == "abort" and denied["reason"] == "forbidden", denied

        response = await hass.services.async_call(
            "family_assistant",
            "execute",
            {
                "entry_id": entry.entry_id,
                "action": "pantry.item_save",
                "payload": {
                    "name": "Synthetic milk",
                    "unit": "l",
                    "quantity": 1,
                    "minimum_quantity": 0,
                    "expires_on": "2026-09-07",
                    "note": "Private pantry note must not reach reminders",
                },
                "operation_id": "ha-expiry-item",
            },
            blocking=True,
            return_response=True,
            context=Context(user_id=owner.id),
        )
        item = response["result"]
        stock = deepcopy(engine.snapshot()["pantry"]["items"])
        scheduler = Scheduler(hass, entry, runtime)
        nine = datetime(2026, 9, 7, 6, tzinfo=UTC)
        await scheduler.run(nine - timedelta(seconds=1))
        assert not engine.snapshot()["outbox"]
        await scheduler.run(nine)
        events = engine.snapshot()["outbox"]
        assert len(events) == 1
        event = next(iter(events.values()))
        assert event["recipient"] == "parents" and event["key"] == "pantry_expiry"
        assert event["data"] == {
            "id": item["id"],
            "source_revision": item["revision"],
            "name": item["name"],
            "expires_on": "2026-09-07",
        }
        await scheduler.run(nine + timedelta(minutes=1))
        assert len(engine.snapshot()["outbox"]) == 1
        assert engine.snapshot()["pantry"]["items"] == stock
        marker = engine.snapshot()["pantry"]["expiry_reminders"][item["id"]]
        assert marker["event_id"] == event["id"]

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        restored = entry.runtime_data.engine.snapshot()
        assert restored["settings"]["pantry_expiry_reminders"] is True
        assert restored["settings"]["pantry_expiry_days"] == 0
        assert restored["pantry"]["expiry_reminders"][item["id"]] == marker
        assert restored["pantry"]["items"] == stock
        assert len(restored["outbox"]) == 1
        print(
            "PASS: actual HA expiry opt-in, strict form, owner access, clock dedup and Store reload"
        )
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
