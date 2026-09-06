"""Real HA option flows and message routing with an isolated synthetic transport."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch


class SyntheticTelegram:
    sent = []

    def __init__(self, session, token):
        pass

    async def inspect(self):
        return {
            "id": 1000,
            "username": "synthetic_family_bot",
            "can_read_all_group_messages": False,
        }

    async def updates(self, offset):
        await asyncio.Event().wait()

    async def call(self, method, payload):
        if method == "sendMessage":
            self.sent.append(payload)
            return {"message_id": len(self.sent)}
        return True


async def run(hass, entry, owner_user, child_id):
    SyntheticTelegram.sent = []
    with (
        patch(
            "custom_components.family_assistant.telegram.client.TelegramClient", SyntheticTelegram
        ),
        # No network/multicast exists in this sandbox. The synthetic transport
        # does not need HA's DNS connector or any HTTP session.
        patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=None),
    ):

        async def options(step):
            flow = await hass.config_entries.options.async_init(
                entry.entry_id, context={"user_id": owner_user.id}
            )
            return await hass.config_entries.options.async_configure(
                flow["flow_id"], {"next_step_id": step}
            )

        async def submit(flow, data):
            return await hass.config_entries.options.async_configure(flow["flow_id"], data)

        flow = await options("telegram")
        flow = await submit(flow, {"enabled": True, "token": "1" * 8 + ":" + "x" * 35})
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.telegram is not None

        update_id = 100

        async def receive(text, *, user_id=1001, private=False):
            nonlocal update_id
            update_id += 1
            update = {
                "update_id": update_id,
                "message": {
                    "message_id": update_id,
                    "date": int(datetime.now(UTC).timestamp()),
                    "from": {"id": user_id, "is_bot": False, "first_name": "Synthetic person"},
                    "chat": {
                        "id": user_id if private else -10001,
                        "type": "private" if private else "supergroup",
                        "title": "Synthetic group",
                    },
                    "text": text,
                },
            }
            await entry.runtime_data.telegram.process(update)
            return update

        flow = await options("telegram_group")
        assert flow["step_id"] == "telegram_wait"
        await receive(flow["description_placeholders"]["instruction"])
        flow = await submit(flow, {})
        assert flow["step_id"] == "telegram_confirm"
        assert "group_id" not in entry.runtime_data.engine.snapshot()["telegram"]
        flow = await submit(flow, {"confirmed": True})
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()

        for member, user_id in (("owner", 1001), (child_id, 1002)):
            flow = await options("telegram_member")
            flow = await submit(flow, {"member": member})
            link = flow["description_placeholders"]["instruction"]
            code = link.split("?start=", 1)[1]
            await receive("/start " + code, user_id=user_id, private=True)
            flow = await submit(flow, {})
            assert flow["step_id"] == "telegram_confirm"
            flow = await submit(flow, {"confirmed": True})
            assert flow["type"] == "create_entry"
            await hass.async_block_till_done()

        engine = entry.runtime_data.engine
        await receive("@synthetic_family_bot тут?")
        before = len(engine.snapshot()["shopping"])
        update = await receive("/buy@synthetic_family_bot Synthetic oranges | 2 | kg")
        await entry.runtime_data.telegram.process(update)
        assert len(engine.snapshot()["shopping"]) == before + 1
        await receive("/buy Intruder item", user_id=1003)
        assert len(engine.snapshot()["shopping"]) == before + 1
        # The family group does not grant parental privileges to a child.
        await receive("/task Parent | Unauthorized task", user_id=1002)
        assert not engine.snapshot()["tasks"]
        for seconds in (2, 4, 6):
            await entry.runtime_data.telegram.notifications.run(
                datetime.now(UTC) + timedelta(seconds=seconds)
            )
        assert any("I'm here" in event["text"] for event in SyntheticTelegram.sent)
        assert any("Synthetic oranges" in event["text"] for event in SyntheticTelegram.sent)
        assert all("parse_mode" not in event for event in SyntheticTelegram.sent)
        assert engine.actor_for_telegram(1002, -10001, private=False) == child_id
        flow = await options("telegram")
        flow = await submit(flow, {"enabled": False})
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.telegram is None
        print(
            "PASS: real HA own-bot options, group/member enrollment, "
            "mention reply, command replay/roles"
        )
