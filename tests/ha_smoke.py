"""Run with the real HA image; no production config, network or credentials.

docker run --rm --network none -v "$PWD:/work:ro" --entrypoint python \
  ghcr.io/home-assistant/home-assistant:2026.8.2 /work/tests/ha_smoke.py
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aiohttp import ClientSession
from homeassistant import bootstrap, config_entries, loader
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.components.siren import DATA_COMPONENT, SirenEntity, SirenEntityFeature
from homeassistant.core import Context, HomeAssistant
from homeassistant.setup import async_setup_component


class SyntheticSiren(SirenEntity):
    _attr_name = "Synthetic wake-up siren"
    _attr_unique_id = "synthetic-wakeup-test"
    _attr_should_poll = False
    _attr_is_on = False
    _attr_available_tones = {1: "Chime", 2: "Melody"}
    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.DURATION
        | SirenEntityFeature.VOLUME_SET
        | SirenEntityFeature.TONES
    )

    def __init__(self):
        self.calls = []

    async def async_turn_on(self, **kwargs):
        self.calls.append((True, kwargs))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self.calls.append((False, kwargs))
        self._attr_is_on = False
        self.async_write_ha_state()


async def main():
    source = Path(__file__).resolve().parents[1] / "custom_components" / "family_assistant"
    with tempfile.TemporaryDirectory(prefix="family-ha-smoke-") as directory:
        shutil.copytree(source, Path(directory) / "custom_components" / "family_assistant")
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        assert await bootstrap.async_from_config_dict(
            {
                "homeassistant": {
                    "name": "Sandbox",
                    "latitude": 0,
                    "longitude": 0,
                    "elevation": 0,
                    "unit_system": "metric",
                    "time_zone": "UTC",
                    "country": "GB",
                },
                "http": {"server_host": "127.0.0.1", "server_port": 8123},
            },
            hass,
        )
        user = await hass.auth.async_create_user("Synthetic owner", group_ids=[GROUP_ID_ADMIN])
        try:
            await async_setup_component(hass, "websocket_api", {})
            result = await hass.config_entries.flow.async_init(
                "family_assistant", context={"source": "user", "user_id": user.id}
            )
            assert result["type"] == "form", result
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "name": "Synthetic family",
                    "owner_name": "Parent",
                    "language": "en",
                    "timezone": "Europe/Berlin",
                    "template": "pair",
                },
            )
            assert result["step_id"] == "modules", result
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "shopping": True,
                    "tasks": True,
                    "court": True,
                    "alarms": True,
                },
            )
            assert result["type"] == "create_entry", result
            entry = result["result"]
            await hass.async_block_till_done()
            assert entry.state == config_entries.ConfigEntryState.LOADED, entry.state
            engine = entry.runtime_data.engine
            record = await engine.execute(
                "owner", "shopping.add", {"name": "Milk"}, "smoke-add", datetime.now(UTC)
            )
            assert record["id"] == "S000001"
            entry.runtime_data.updated()
            await hass.async_block_till_done()
            assert any(state.domain == "sensor" for state in hass.states.async_all())
            options = await hass.config_entries.options.async_init(
                entry.entry_id, context={"user_id": user.id}
            )
            assert options["type"] == "menu", options
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"next_step_id": "member"}
            )
            assert options["type"] == "form", options
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"member_id": "_new"}
            )
            assert options["step_id"] == "edit_member", options
            options = await hass.config_entries.options.async_configure(
                options["flow_id"],
                {
                    "name": "Child",
                    "role": "child",
                    "language": "uk",
                    "active": True,
                },
            )
            assert options["type"] == "create_entry", options
            assert len(engine.view("owner")["members"]) == 3
            assert engine.snapshot()["settings"]["timezone"] == "Europe/Berlin"
            assert engine.snapshot()["members"]["M000001"]["ha_user_id"] is None
            # Exercise the real core service registry with authenticated context.
            response = await hass.services.async_call(
                "family_assistant",
                "execute",
                {
                    "entry_id": entry.entry_id,
                    "action": "shopping.add",
                    "payload": {"name": "Bread"},
                    "operation_id": "smoke-service",
                },
                blocking=True,
                return_response=True,
                context=Context(user_id=user.id),
            )
            assert response["result"]["name"] == "Bread"
            # No physical device: this virtual entity uses HA's real siren platform,
            # including feature checks, tone mapping and service parameter validation.
            assert await async_setup_component(hass, "siren", {})
            siren = SyntheticSiren()
            await hass.data[DATA_COMPONENT].async_add_entities([siren])
            child_id = next(
                m["id"] for m in engine.view("owner")["members"] if m["role"] == "child"
            )
            options = await hass.config_entries.options.async_init(
                entry.entry_id, context={"user_id": user.id}
            )
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"next_step_id": "alarm_device"}
            )
            options = await hass.config_entries.options.async_configure(
                options["flow_id"],
                {
                    "member": child_id,
                    "entity_id": siren.entity_id,
                    "volume": 0.5,
                    "enabled": True,
                    "confirmed": False,
                },
            )
            assert options["errors"]["base"] == "device_confirmation_required"
            options = await hass.config_entries.options.async_configure(
                options["flow_id"],
                {
                    "member": child_id,
                    "entity_id": siren.entity_id,
                    "volume": 0.5,
                    "enabled": True,
                    "confirmed": True,
                },
            )
            assert options["type"] == "create_entry"
            clock = datetime.now(UTC)
            alarm = await engine.execute(
                "owner",
                "alarms.save",
                {
                    "member": child_id,
                    "time": "00:00",
                    "days": [0],
                    "timezone": "UTC",
                    "profile": "strict",
                },
                "smoke-alarm",
                clock,
            )
            run = await engine.execute(
                "owner", "alarms.test", {"id": alarm["id"]}, "smoke-ring", clock
            )
            await entry.runtime_data.scheduler.run(clock)
            assert siren.calls[-1] == (True, {"duration": 35, "volume_level": 0.5, "tone": 1}), (
                siren.calls
            )
            await entry.runtime_data.scheduler.run(clock + timedelta(seconds=20))
            assert siren.calls[-1][1]["tone"] == 2
            correct = sum(int(n) for n in run["challenge"]["question"].split(" + "))
            await engine.execute(
                child_id,
                "alarms.answer",
                {"id": run["id"], "nonce": run["challenge"]["nonce"], "answer": correct},
                "smoke-woke",
                clock + timedelta(seconds=21),
            )
            await entry.runtime_data.scheduler.run(clock + timedelta(seconds=21))
            assert siren.calls[-1][0] is False
            from ha_telegram_smoke import run as telegram_smoke

            await telegram_smoke(hass, entry, user, child_id)
            await run_websocket(hass, entry, user, child_id)
            # Reload reads the same Store; HACS code updates do not replace it.
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state == config_entries.ConfigEntryState.LOADED
            assert len(entry.runtime_data.engine.view("owner")["shopping"]) == 3
            assert len(entry.runtime_data.engine.view("owner")["members"]) == 3
            assert await hass.config_entries.async_unload(entry.entry_id)
            assert not hass.data["family_assistant"]["entries"]
            print(
                "PASS: real HA config/options/service, siren renewal/tones/answer, "
                "Store/reload/unload"
            )
        finally:
            await hass.async_stop(force=True)


async def run_websocket(hass, entry, owner, child_id):
    """Real HTTP/WebSocket protocol on container loopback, not handler mocks."""
    await hass.http.start()
    child = await hass.auth.async_create_user("Synthetic child HA user")
    stranger = await hass.auth.async_create_user("Synthetic unlinked HA user")
    engine = entry.runtime_data.engine
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": child_id,
            "name": "Child",
            "role": "child",
            "ha_user_id": child.id,
        },
        "ws-bind-child",
        datetime.now(UTC),
    )
    async with ClientSession() as client:
        for user, allowed in ((owner, True), (child, True), (stranger, False)):
            refresh = await hass.auth.async_create_refresh_token(
                user, client_id="https://example.invalid/synthetic-client"
            )
            token = hass.auth.async_create_access_token(refresh)
            async with client.ws_connect("http://127.0.0.1:8123/api/websocket") as ws:
                assert (await ws.receive_json())["type"] == "auth_required"
                await ws.send_json({"type": "auth", "access_token": token})
                assert (await ws.receive_json())["type"] == "auth_ok"
                await ws.send_json({"id": 1, "type": "family_assistant/households"})
                result = await ws.receive_json()
                assert result["success"]
                assert result["result"] == (
                    [{"entry_id": entry.entry_id, "title": entry.title}] if allowed else []
                )
                await ws.send_json(
                    {"id": 2, "type": "family_assistant/view", "entry_id": entry.entry_id}
                )
                result = await ws.receive_json()
                assert result["success"] == allowed
                if allowed:
                    assert result["result"]["role"] == ("owner" if user is owner else "child")
                    assert "telegram_id" not in str(result["result"])
                if user is child:
                    await ws.send_json(
                        {
                            "id": 3,
                            "type": "family_assistant/execute",
                            "entry_id": entry.entry_id,
                            "action": "court.award",
                            "payload": {"member": child_id, "points": 1, "reason": "Self-award"},
                            "operation_id": "ws-forbidden",
                        }
                    )
                    result = await ws.receive_json()
                    assert not result["success"] and result["error"]["code"] == "forbidden"
                    assert not engine.snapshot()["court"]
            hass.auth.async_remove_refresh_token(refresh)
    print("PASS: actual HA WebSocket auth, household names, projections and command denial")


if __name__ == "__main__":
    asyncio.run(main())
