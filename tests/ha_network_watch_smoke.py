"""Actual HA private discovery subscription and TelegramManager synthetic delivery."""

from copy import deepcopy
from datetime import UTC, datetime

from ha_presence_smoke import _request


async def verify_network_watch(hass, entry, owner_user):
    from custom_components.family_assistant.network.watch import KEY
    from custom_components.family_assistant.telegram.manager import TelegramManager

    runtime = entry.runtime_data
    engine = runtime.engine
    now = datetime.now(UTC)
    view = await _request(hass, entry, owner_user, 720)
    projection = view["result"]["network"]["admission"]
    assert projection["watch"]["enabled"] is False
    payload = {
        "actor_revision": projection["watch"]["actor_revision"],
        "watch_revision": None,
        "enabled": True,
        "min_interval_minutes": 5,
        "observation_token": projection["token"],
    }
    enabled = await _request(
        hass, entry, owner_user, 721, "mikrotik.admission_watch_set", payload, "ha-watch-enable"
    )
    assert enabled["success"], enabled
    await engine.tick(now)
    assert not any(event["key"] == KEY for event in engine.snapshot()["outbox"].values())

    async def observe(address):
        def seed(ctx):
            inventory = ctx.state["network"]["inventory"]
            inventory["observed_at"] = ctx.now.isoformat()
            inventory["devices"].append(
                {
                    "mac": address,
                    "addresses": ["198.51.100.25"],
                    "suggested_name": "Synthetic new device",
                    "warnings": [],
                }
            )

        await engine.system_update("synthetic-watch-discovery", datetime.now(UTC), seed)
        await engine.tick(datetime.now(UTC))

    new = "02:11:22:33:44:77"
    await observe(new)
    queued = [event for event in engine.snapshot()["outbox"].values() if event["key"] == KEY]
    assert len(queued) == 1 and queued[0]["data"]["macs"] == [new]
    no_effects = deepcopy(engine.snapshot()["network"]["tables"])

    class SyntheticTelegram:
        def __init__(self):
            self.sent = []

        async def call(self, method, body):
            assert method == "sendMessage", method
            self.sent.append(deepcopy(body))
            return {"message_id": len(self.sent)}

    client = SyntheticTelegram()
    manager = TelegramManager(
        hass, entry, runtime, client, {"id": 1000, "username": "synthetic_family_bot"}
    )
    previous = runtime.telegram
    runtime.telegram = manager
    try:
        assert await manager.notifications.run(datetime.now(UTC)) == 1
        assert len(client.sent) == 1 and client.sent[0]["chat_id"] == 840001
        assert new in client.sent[0]["text"]
        assert await manager.notifications.run(datetime.now(UTC)) == 0
        # Actual Telegram update uses current actor binding and durable interpretation.
        update = {
            "update_id": 860001,
            "message": {
                "message_id": 860002,
                "chat": {"id": 840001, "type": "private"},
                "from": {"id": 840001, "is_bot": False},
                "text": "/network_alerts off",
            },
        }
        await manager.process(update)
        assert engine.snapshot()["network"]["admission_watches"]["owner"]["enabled"] is False
        disabled = deepcopy(engine.snapshot()["network"]["admission_watches"])
        await manager.process(update)
        assert engine.snapshot()["network"]["admission_watches"] == disabled
        assert engine.snapshot()["network"]["tables"] == no_effects
    finally:
        await manager.stop()
        runtime.telegram = previous
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await entry.runtime_data.scheduler.stop()
    assert entry.runtime_data.engine.snapshot()["network"]["admission_watches"] == disabled
    print(
        "PASS: actual HA authenticated discovery baseline, private TelegramManager delivery, "
        "duplicate suppression, private command withdrawal and Store reload; zero router writes"
    )
