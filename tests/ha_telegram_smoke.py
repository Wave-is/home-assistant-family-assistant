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

        async def receive(text, *, user_id=1001, private=False, reply_to=None):
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
            if reply_to:
                update["message"]["reply_to_message"] = {
                    "message_id": reply_to,
                    "from": {"id": 1000},
                    "text": "Untrusted quote",
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
        await receive(
            "Child задача. перенести детали, срок до конца следующей недели", private=True
        )
        task = next(iter(engine.snapshot()["tasks"].values()))
        for seconds in (10, 12, 14):
            await entry.runtime_data.telegram.notifications.run(
                datetime.now(UTC) + timedelta(seconds=seconds)
            )
        receipt = next(
            i
            for i, sent in enumerate(SyntheticTelegram.sent, 1)
            if "Saved:" in sent["text"] and task["id"] in sent["text"]
        )
        before = task["revision"]
        await receive("установи срок завтра", private=True, reply_to=receipt)
        assert engine.snapshot()["tasks"][task["id"]]["revision"] == before + 1
        # A different bot's cursor must not suppress this bot's legitimate update.
        assert str(1000) in engine.snapshot()["telegram"]["offsets"]
        await run_assistant(hass, entry, owner_user, child_id, receive, options, submit)
        flow = await options("telegram")
        flow = await submit(flow, {"enabled": False})
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.telegram is None
        print(
            "PASS: real HA own-bot options, group/member enrollment, "
            "mention/reply context, command replay/roles"
        )


async def run_assistant(hass, entry, owner, child_id, receive, options, submit):
    from homeassistant.components import conversation
    from homeassistant.core import Context

    from custom_components.family_assistant.domain.validation import DomainError

    gate, started = asyncio.Event(), asyncio.Event()

    class SyntheticOllama:
        def __init__(self, session, config):
            self.model = config["model"]

        async def inspect(self):
            if self.model not in {"synthetic-primary", "synthetic-fallback"}:
                raise DomainError("provider_model_missing")

        async def generate(self, messages, schema):
            if self.model == "synthetic-primary":
                raise DomainError("provider_timeout")
            started.set()
            await gate.wait()
            return {
                "kind": "commands",
                "commands": [
                    {
                        "action": "tasks.create",
                        "payload": {"title": "Synthetic model task", "assignee": child_id},
                    }
                ],
            }

    engine = entry.runtime_data.engine
    with patch("custom_components.family_assistant.assistant.provider.Ollama", SyntheticOllama):
        settings = engine.snapshot()["settings"]
        flow = await options("general")
        flow = await submit(
            flow,
            {
                "name": settings["name"],
                "language": "en",
                "timezone": settings["timezone"],
                "shopping": True,
                "tasks": True,
                "alarms": True,
                "court": True,
                "conversation": True,
            },
        )
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        flow = await options("conversation")
        config = {
            "enabled": True,
            "primary_url": "https://example.invalid/primary",
            "primary_model": "missing",
            "fallback_enabled": True,
            "fallback_url": "https://example.invalid/fallback",
            "fallback_model": "synthetic-fallback",
            "timeout": 5,
            "allow_http": False,
        }
        flow = await submit(flow, config)
        assert flow["errors"]["base"] == "provider_model_missing"
        flow = await submit(flow, {**config, "primary_model": "synthetic-primary"})
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.assistant is not None
        update = await receive("@synthetic_family_bot Please interpret this request")
        await asyncio.wait_for(started.wait(), 4)
        # Slow fallback inference must not hold the Telegram polling path.
        await asyncio.wait_for(receive("@synthetic_family_bot /ping"), 0.5)
        before = len(engine.snapshot()["tasks"])
        gate.set()
        async with asyncio.timeout(4):
            while any(
                j["status"] == "pending" for j in engine.snapshot()["assistant_jobs"].values()
            ):
                await asyncio.sleep(0.05)
        assert len(engine.snapshot()["tasks"]) == before
        assert entry.runtime_data.health["conversation"] == "fallback"
        proposal = next(iter(engine.snapshot()["proposals"]))
        assert engine.snapshot()["proposals"][proposal]["status"] == "pending"
        for seconds in (20, 22, 24):
            await entry.runtime_data.telegram.notifications.run(
                datetime.now(UTC) + timedelta(seconds=seconds)
            )
        assert any(
            "fp:confirm:" in str(sent.get("reply_markup", {})) for sent in SyntheticTelegram.sent
        )
        callback_update = {
            "update_id": update["update_id"] + 2,
            "callback_query": {
                "id": "synthetic-callback",
                "from": {"id": 1001, "is_bot": False},
                "message": {"message_id": 1, "chat": {"id": -10001, "type": "supergroup"}},
                "data": "fp:confirm:" + proposal,
            },
        }
        await entry.runtime_data.telegram.process(callback_update)
        assert len(engine.snapshot()["tasks"]) == before + 1
        await entry.runtime_data.telegram.process(callback_update)
        assert len(engine.snapshot()["tasks"]) == before + 1
        agents = [
            s.entity_id for s in hass.states.async_all("conversation") if "family" in s.entity_id
        ]
        assert agents, [s.entity_id for s in hass.states.async_all("conversation")]
        result = await conversation.async_converse(
            hass,
            text="/ping",
            conversation_id=None,
            context=Context(user_id=owner.id),
            language="en",
            agent_id=agents[0],
        )
        assert "I'm here" in result.as_dict()["response"]["speech"]["plain"]["speech"]
        result = await conversation.async_converse(
            hass,
            text="/task Child | Synthetic Assist task",
            conversation_id=result.conversation_id,
            context=Context(user_id=owner.id),
            language="en",
            agent_id=agents[0],
        )
        assert "Synthetic Assist task" in result.as_dict()["response"]["speech"]["plain"]["speech"]
        result = await conversation.async_converse(
            hass,
            text="установи срок завтра",
            conversation_id=result.conversation_id,
            context=Context(user_id=owner.id),
            language="en",
            agent_id=agents[0],
        )
        assert "Saved:" in result.as_dict()["response"]["speech"]["plain"]["speech"]
        denied = await conversation.async_converse(
            hass,
            text="/task Child | Unauthorized",
            conversation_id=result.conversation_id,
            context=Context(),
            language="en",
            agent_id=agents[0],
        )
        assert "permission" in denied.as_dict()["response"]["speech"]["plain"]["speech"]
        flow = await options("conversation")
        flow = await submit(flow, {"enabled": False, "timeout": 5})
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.assistant is None
        print(
            "PASS: real HA model options/fallback, nonblocking Telegram queue, "
            "confirmation buttons and authenticated Assist context"
        )
