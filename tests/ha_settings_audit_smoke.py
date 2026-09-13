"""Native HA settings acceptance with synthetic providers and registered virtual outputs."""

import asyncio
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from aiohttp import ClientSession


async def verify_settings_audit(hass, user):
    # Isolated synthetic fixture only: make actual HA route exceptions visible in CI.
    server_logger = logging.getLogger("aiohttp.server")
    server_handler = logging.StreamHandler()
    server_handler.setLevel(logging.ERROR)
    server_logger.addHandler(server_handler)
    from homeassistant.auth.const import GROUP_ID_ADMIN
    from homeassistant.helpers import aiohttp_client, device_registry, entity_registry
    from homeassistant.setup import async_setup_component

    from custom_components.family_assistant.assistant.provider import Ollama
    from custom_components.family_assistant.assistant.search import Search
    from custom_components.family_assistant.diagnostics import async_get_config_entry_diagnostics

    await async_setup_component(hass, "websocket_api", {})
    await async_setup_component(hass, "config", {})
    result = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": user.id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Synthetic settings audit",
            "owner_name": "Synthetic guardian",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"conversation": True, "alarms": True}
    )
    entry = result["result"]
    await hass.async_block_till_done()
    await entry.runtime_data.scheduler.stop()
    outsider = await hass.auth.async_create_user(
        "Synthetic other admin", group_ids=[GROUP_ID_ADMIN]
    )
    refreshes = [
        await hass.auth.async_create_refresh_token(
            selected, client_id="https://example.invalid/settings-audit"
        )
        for selected in (user, outsider)
    ]
    headers = [
        {"Authorization": "Bearer " + hass.auth.async_create_access_token(refresh)}
        for refresh in refreshes
    ]
    calls, gate = [], {}

    async def inspect(self):
        calls.append("model")
        if gate:
            gate["entered"].set()
            await gate["release"].wait()
        return []

    async def query(self, *_args, **_kwargs):
        calls.append("search")
        return []

    try:
        with (
            patch.object(aiohttp_client, "async_get_clientsession", lambda *_args: object()),
            patch.object(Ollama, "inspect", inspect),
            patch.object(Search, "query", query),
        ):
            async with ClientSession() as client:

                async def post(path, values, *, selected=0):
                    async with client.post(
                        "http://127.0.0.1:8123" + path, headers=headers[selected], json=values
                    ) as response:
                        if response.status != 200:
                            raise AssertionError((response.status, await response.text()))
                        result = await response.json()
                        assert response.status == 200, (response.status, result)
                        return result

                async def form(step, group="menu_ai"):
                    opened = await post(
                        "/api/config/config_entries/options/flow", {"handler": entry.entry_id}
                    )
                    path = "/api/config/config_entries/options/flow/" + opened["flow_id"]
                    await post(path, {"next_step_id": group})
                    return await post(path, {"next_step_id": step}), path

                model = {
                    "enabled": True,
                    "primary_url": "https://model.example.invalid",
                    "primary_model": "synthetic-model",
                    "primary_key": "synthetic-settings-key",
                    "timeout": 15,
                }
                _, path = await form("conversation")
                assert (await post(path, model))["type"] == "create_entry"
                await hass.async_block_till_done()
                assert entry.runtime_data.assistant is not None
                _, path = await form("search")
                assert (
                    await post(
                        path,
                        {
                            "enabled": True,
                            "url": "https://search.example.invalid",
                            "api_key": "synthetic-search-key",
                        },
                    )
                )["type"] == "create_entry"
                await hass.async_block_till_done()
                assert entry.runtime_data.assistant.search is not None
                await _provider_drafts(hass, entry, form, post, calls)
                _, path = await form("conversation")
                denied = await post(path, {"enabled": False}, selected=1)
                assert denied["type"] == "abort" and denied["reason"] == "forbidden"

                # The native HTTP request supplies identity: no context.user_id is injected.
                _, path = await form("conversation")
                gate.update(entered=asyncio.Event(), release=asyncio.Event())
                pending = asyncio.create_task(post(path, model))
                await asyncio.wait_for(gate["entered"].wait(), 5)
                newer = {**deepcopy(dict(entry.options)), "synthetic_unrelated": {"keep": True}}
                hass.config_entries.async_update_entry(entry, options=newer)
                gate["release"].set()
                conflict = await asyncio.wait_for(pending, 5)
                gate.clear()
                assert conflict["type"] == "abort" and conflict["reason"] == "conflict"
                await hass.async_block_till_done()
                assert dict(entry.options) == newer

                _, path = await form("search")
                before = len(calls)
                assert (await post(path, {"enabled": False}))["type"] == "create_entry"
                await hass.async_block_till_done()
                assert len(calls) == before and entry.runtime_data.assistant.search is None
                assert (
                    entry.options["conversation"]["search"]["url"]
                    == "https://search.example.invalid"
                )
                _, path = await form("search")
                assert (await post(path, {"enabled": True}))["type"] == "create_entry"
                await hass.async_block_till_done()
                assert entry.runtime_data.assistant.search is not None
                _, path = await form("conversation")
                before = len(calls)
                assert (await post(path, {"enabled": False, "primary_clear_key": True}))[
                    "type"
                ] == "create_entry"
                await hass.async_block_till_done()
                assert len(calls) == before and entry.runtime_data.assistant is None
                assert "api_key" not in entry.options["conversation"]["primary"]
                retained = deepcopy(dict(entry.options))
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                await entry.runtime_data.scheduler.stop()
                assert dict(entry.options) == retained and entry.runtime_data.assistant is None
                assert "synthetic-search-key" not in repr(
                    await async_get_config_entry_diagnostics(hass, entry)
                )
                await _alarm_controls(hass, entry, form, post, device_registry, entity_registry)
    finally:
        if gate:
            gate["release"].set()
        await hass.config_entries.async_unload(entry.entry_id)
        for refresh in refreshes:
            hass.auth.async_remove_refresh_token(refresh)
        server_logger.removeHandler(server_handler)
    print(
        "PASS: native HTTP Options identity, conflict fences, "
        "disabled provider drafts/fallback, clear/reload and alarm controls"
    )


async def _provider_drafts(hass, entry, form, post, calls):
    # HTTP form defaults and ConfigEntry reloads must agree with the actual runtime.
    _, path = await form("conversation")
    before = len(calls)
    assert (
        await post(
            path,
            {
                "enabled": False,
                "primary_model": "edited-primary",
                "fallback_enabled": False,
                "fallback_url": "https://fallback.example.invalid",
                "fallback_model": "edited-fallback",
                "fallback_key": "synthetic-fallback-key",
                "timeout": 27,
            },
        )
    )["type"] == "create_entry"
    await hass.async_block_till_done()
    assert len(calls) == before and entry.runtime_data.assistant is None
    config = entry.options["conversation"]
    assert config["primary"]["model"] == "edited-primary" and config["primary"]["timeout"] == 27
    assert config["fallback"]["enabled"] is False and config["search"]["api_key"]
    _, path = await form("conversation")
    assert (await post(path, {"enabled": True}))["type"] == "create_entry"
    await hass.async_block_till_done()
    assert len(calls) == before + 1
    assert [provider.model for provider in entry.runtime_data.assistant.cascade.providers] == [
        "edited-primary"
    ]
    _, path = await form("conversation")
    assert (await post(path, {"enabled": True, "fallback_enabled": True}))["type"] == "create_entry"
    await hass.async_block_till_done()
    assert len(calls) == before + 3
    assert [provider.model for provider in entry.runtime_data.assistant.cascade.providers] == [
        "edited-primary",
        "edited-fallback",
    ]
    assert entry.options["conversation"]["fallback"]["api_key"] == "synthetic-fallback-key"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.scheduler.stop()
    assert len(entry.runtime_data.assistant.cascade.providers) == 2

    # Save connection edits while disabled. These transports are never constructed
    # by runtime because both provider/module switches are off in this fixture.
    _, path = await form("mikrotik", "menu_services")
    assert (
        await post(
            path,
            {
                "enabled": False,
                "url": "https://router.example.invalid",
                "username": "synthetic-owner",
                "password": "synthetic-router-password",
                "allow_write": True,
                "allow_kid_control": True,
                "ha_mac": "02:00:00:00:00:01",
                "management_mac": "02:00:00:00:00:02",
                "management_confirmed": True,
            },
        )
    )["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["mikrotik"]["allow_kid_control"] is True
    assert entry.runtime_data.network is None
    _, path = await form("telegram", "menu_telegram")
    token = "123456" + ":" + "s" * 32
    assert (await post(path, {"enabled": False, "token": token}))["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["telegram"]["token"] == token and "bot" not in entry.options["telegram"]
    assert entry.runtime_data.telegram is None


async def _alarm_controls(hass, entry, form, post, device_registry, entity_registry):
    from homeassistant.components.siren import SirenEntityFeature

    from custom_components.family_assistant.scheduler import Scheduler

    device = device_registry.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("family_assistant", "synthetic-settings-alarm")},
    )
    registry = entity_registry.async_get(hass)
    entities = {}
    for domain in ("siren", "number", "select"):
        entity = registry.async_get_or_create(
            domain,
            "family_assistant",
            "synthetic-settings-" + domain,
            config_entry=entry,
            device_id=device.id,
        )
        entities[domain] = entity.entity_id
    features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.DURATION
        | SirenEntityFeature.VOLUME_SET
    )
    hass.states.async_set(entities["siren"], "off", {"supported_features": int(features)})
    hass.states.async_set(entities["number"], "60", {"min": 60, "max": 1800, "step": 1})
    hass.states.async_set(entities["select"], "low", {"options": ["low", "middle", "high"]})
    calls = []

    async def output(call):
        calls.append((call.domain, call.service, dict(call.data)))
        entity = call.data["entity_id"]
        value = call.data.get(
            "value", call.data.get("option", "on" if call.service == "turn_on" else "off")
        )
        hass.states.async_set(entity, str(value), dict(hass.states.get(entity).attributes))

    for domain, service in (
        ("siren", "turn_on"),
        ("siren", "turn_off"),
        ("number", "set_value"),
        ("select", "select_option"),
    ):
        hass.services.async_register(domain, service, output)
    _, path = await form("alarm_device", "menu_telegram")
    selected = await post(path, {"member": "owner"})
    assert selected["step_id"] == "alarm_device_settings"
    values = {
        "enabled": True,
        "entity_id": entities["siren"],
        "volume": 0.6,
        "confirmed": True,
        "duration_entity_id": entities["number"],
        "duration_seconds": 420,
        "volume_entity_id": entities["select"],
        "select_volume": "middle",
    }
    assert (await post(path, values))["type"] == "create_entry"
    await hass.async_block_till_done()
    assert calls == []
    engine = entry.runtime_data.engine
    clock = datetime.now(UTC)
    alarm = await engine.execute(
        "owner",
        "alarms.save",
        {"member": "owner", "time": "00:00", "days": [0], "timezone": "UTC", "profile": "strict"},
        uuid4().hex,
        clock,
    )
    run = await engine.execute("owner", "alarms.test", {"id": alarm["id"]}, uuid4().hex, clock)
    driver = Scheduler(hass, entry, entry.runtime_data)  # No timer; actual desired-state/send path.
    await driver.devices.reconcile(clock)
    assert [(domain, service) for domain, service, _ in calls] == [
        ("number", "set_value"),
        ("select", "select_option"),
        ("siren", "turn_on"),
    ]
    assert calls[-1][2] == {"entity_id": entities["siren"]}
    answer = sum(int(value) for value in run["challenge"]["question"].split(" + "))
    await engine.execute(
        "owner",
        "alarms.answer",
        {"id": run["id"], "nonce": run["challenge"]["nonce"], "answer": answer},
        uuid4().hex,
        clock + timedelta(seconds=1),
    )
    await driver.devices.reconcile(clock + timedelta(seconds=1))
    assert calls[-1][1] == "turn_off"
    await engine.execute(
        "owner",
        "alarms.cancel",
        {"id": run["id"], "reason": "Synthetic acceptance complete"},
        uuid4().hex,
        clock + timedelta(seconds=1),
    )
    await _cancelled_alarm_preparation(hass, entry, alarm, entities, output, calls, clock)
    _, path = await form("alarm_device", "menu_telegram")
    await post(path, {"member": "owner"})
    assert (await post(path, {"confirmed": True, "clear_duration": True, "clear_volume": True}))[
        "type"
    ] == "create_entry"
    await hass.async_block_till_done()
    plain = entry.options["alarm_devices"]["owner"]
    assert plain == {"entity_id": entities["siren"], "volume": 0.6, "confirmed": True}
    await engine.execute(
        "owner", "alarms.test", {"id": alarm["id"]}, uuid4().hex, clock + timedelta(seconds=4)
    )
    await driver.devices.reconcile(clock + timedelta(seconds=4))
    assert calls[-1] == (
        "siren",
        "turn_on",
        {"entity_id": entities["siren"], "duration": 35, "volume_level": 0.6},
    )
    await driver.stop()


async def _cancelled_alarm_preparation(hass, entry, alarm, entities, output, calls, clock):
    """Actual HA cancellation before siren start cannot own a later manual signal."""
    from custom_components.family_assistant.scheduler import Scheduler

    engine = entry.runtime_data.engine
    now = clock + timedelta(seconds=2)
    state = hass.states.get(entities["number"])
    hass.states.async_set(entities["number"], "60", dict(state.attributes))
    run = await engine.execute("owner", "alarms.test", {"id": alarm["id"]}, uuid4().hex, now)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_number(call):
        entered.set()
        await release.wait()
        await output(call)

    hass.services.async_register("number", "set_value", delayed_number)
    driver = Scheduler(hass, entry, entry.runtime_data)
    before = len(calls)
    pending = asyncio.create_task(driver.devices.reconcile(now))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        pending.cancel()
        cancelled = False
        try:
            await asyncio.wait_for(pending, 5)
        except asyncio.CancelledError:
            cancelled = True
        assert cancelled, "HA preparation cancellation must still propagate"
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
        await hass.async_block_till_done()
        hass.services.async_register("number", "set_value", output)
    assert not any(domain == "siren" for domain, _service, _data in calls[before:])
    assert engine.snapshot()["alarm_outputs"][entities["siren"]]["owned"] is False
    await engine.execute(
        "owner",
        "alarms.cancel",
        {"id": run["id"], "reason": "Synthetic cancelled preparation"},
        uuid4().hex,
        now + timedelta(seconds=1),
    )
    attributes = dict(hass.states.get(entities["siren"]).attributes)
    hass.states.async_set(entities["siren"], "on", attributes)
    count = len(calls)
    await driver.stop()
    assert len(calls) == count and hass.states.get(entities["siren"]).state == "on"
    # This is a synthetic manually started state owned by the test, not an output
    # command. Leave the shared fixture ready for the plain-siren service case.
    hass.states.async_set(entities["siren"], "off", attributes)
    print("PASS: native HA pre-start cancellation preserves later unowned manual siren")
