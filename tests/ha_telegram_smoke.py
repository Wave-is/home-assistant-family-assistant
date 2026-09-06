"""Real HA option flows and message routing with an isolated synthetic transport."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch


async def run_network(hass, entry, owner, child_id):
    from homeassistant.helpers import device_registry, entity_registry

    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.network.client import TABLES, RouterClient

    async def options():
        flow = await hass.config_entries.options.async_init(
            entry.entry_id, context={"user_id": owner.id}
        )
        return await hass.config_entries.options.async_configure(
            flow["flow_id"], {"next_step_id": "mikrotik"}
        )

    tables = {
        "resource": [{"version": "7.20.1"}],
        "leases": [
            {
                ".id": "*1",
                "mac-address": "02:11:22:33:44:55",
                "address": "198.51.100.10",
                "status": "bound",
                "comment": "Existing",
                "dynamic": "true",
                "server": "lan",
            }
        ],
        "servers": [{"name": "lan", "interface": "lan"}],
        "networks": [{"address": "198.51.100.0/24"}],
        "addresses": [{"address": "198.51.100.1/24", "interface": "lan"}],
    }
    failure = False
    writes = []

    async def request(_self, method, path, **_kwargs):
        if method != "GET":
            writes.append((method, path))
            if method == "POST" and path == "ip/dhcp-server/lease/make-static":
                assert _kwargs["json"] == {"numbers": "*1"}
                tables["leases"][0].update({".id": "*A", "dynamic": "false"})
                return []
            if method == "PATCH" and path == "ip/dhcp-server/lease/*A":
                tables["leases"][0].update(_kwargs["json"])
                return deepcopy(tables["leases"][0])
            raise AssertionError("Unexpected router write in smoke test")
        if failure == "deadline":
            raise TimeoutError
        if failure:
            raise DomainError("network_timeout")
        name = next(k for k, v in TABLES.items() if v[0] == path)
        if name in {"wifi", "wireless"}:
            raise DomainError("network_missing")
        return deepcopy(tables.get(name, []))

    device = device_registry.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("mac", "02:11:22:33:44:55")},
        name="Synthetic phone",
    )
    tracker = entity_registry.async_get(hass).async_get_or_create(
        "device_tracker", "family_assistant", "synthetic-network-tracker", device_id=device.id
    )
    hass.states.async_set(
        tracker.entity_id,
        "home",
        {
            "source_type": "router",
            "ip": "198.51.100.10",
            "host_name": "mobile",
            "private_unrelated": "must-not-copy",
        },
    )
    engine = entry.runtime_data.engine
    await engine.execute(
        "owner",
        "settings.save",
        {
            **engine.snapshot()["settings"],
            "modules": [*engine.snapshot()["settings"]["modules"], "mikrotik"],
        },
        "network-enable",
        datetime.now(UTC),
    )
    with (
        patch.object(RouterClient, "_request", request),
        patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=object()
        ),
    ):
        flow = await options()
        config = {
            "enabled": True,
            "url": "https://router.example.org",
            "username": "test-reader",
            "password": "synthetic-only",
            "ca_pem": "",
        }
        flow = await hass.config_entries.options.async_configure(flow["flow_id"], config)
        assert flow["type"] == "create_entry", flow
        await hass.async_block_till_done()
        manager = entry.runtime_data.network
        assert manager is not None
        await manager._task
        view = engine.view("owner")["network"]["inventory"]
        assert view["devices"][0]["suggested_name"] == "Synthetic phone", view
        assert view["devices"][0]["comments"] == ["Existing"]
        assert view["capabilities"]["wifi"] == "network_missing"
        assert "private_unrelated" not in str(view) and "password" not in str(view)
        assert "network" not in engine.view(child_id)
        failure = True
        manager._last_attempt = None
        try:
            await manager.refresh()
        except DomainError as err:
            assert err.code == "network_timeout"
        else:
            raise AssertionError("Router failure was reported as successful")
        assert engine.view("owner")["network"]["inventory"] == view
        assert entry.runtime_data.health["mikrotik"] == "network_timeout"
        # A throttled retry must not report success after a failed read.
        for deadline in (False, True):
            if deadline:
                failure = "deadline"
                manager._last_attempt = None
            try:
                await manager.refresh()
            except DomainError as err:
                assert err.code == "network_timeout"
            else:
                raise AssertionError("Failed/throttled inventory was reported as successful")
        failure = False
        flow = await options()
        flow = await hass.config_entries.options.async_configure(
            flow["flow_id"], {**config, "url": "https://another.example.org", "password": ""}
        )
        assert flow["errors"]["base"] == "network_credential_scope"
        flow = await hass.config_entries.options.async_configure(
            flow["flow_id"], {**config, "allow_write": True}
        )
        assert flow["errors"]["base"] == "network_management_required"
        flow = await hass.config_entries.options.async_configure(
            flow["flow_id"],
            {
                **config,
                "allow_write": True,
                "ha_mac": "02:11:22:33:44:77",
                "management_mac": "02:11:22:33:44:88",
                "management_confirmed": True,
            },
        )
        assert flow["type"] == "create_entry", flow
        await hass.async_block_till_done()
        manager = entry.runtime_data.network
        await manager._task
        planned = await engine.execute(
            "owner",
            "mikrotik.lease_plan",
            {"leases": [{"id": "*1", "comment": "Selected name", "replace_comment": True}]},
            "smoke-lease-plan",
            datetime.now(UTC),
        )
        assert planned["status"] == "preview" and not writes
        command = {"id": planned["id"], "confirmed": True, "dhcp_recovery": True}
        await engine.execute(
            "owner", "mikrotik.lease_apply", command, "smoke-lease-apply", datetime.now(UTC)
        )
        entry.runtime_data.updated()
        await manager._effects_task
        result = engine.snapshot()["network"]["plans"][planned["id"]]
        assert result["status"] == "applied", result
        assert result["progress"]["targets"][0]["phase"] == "verified"
        assert writes == [
            ("POST", "ip/dhcp-server/lease/make-static"),
            ("PATCH", "ip/dhcp-server/lease/*A"),
        ]
        assert engine.view("owner")["network"]["inventory"]["devices"][0]["comments"] == [
            "Selected name"
        ]
        await engine.execute(
            "owner", "mikrotik.lease_apply", command, "smoke-lease-apply", datetime.now(UTC)
        )
        assert len(writes) == 2
        assert (
            len(
                [
                    event
                    for event in engine.snapshot()["outbox"].values()
                    if event["key"] == "network_plan_finished"
                ]
            )
            == 1
        )
        flow = await options()
        flow = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"enabled": False}
        )
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.network is None
    print(
        "PASS: real HA RouterOS options, registry MAC matching, private projections "
        "and stale-data preservation; explicit write scope, lease preview/apply/read-back/replay"
    )


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
        learned = await conversation.async_converse(
            hass,
            text="/learn my balance details | /stats",
            conversation_id=result.conversation_id,
            context=Context(user_id=owner.id),
            language="en",
            agent_id=agents[0],
        )
        assert "Remembered" in learned.as_dict()["response"]["speech"]["plain"]["speech"]
        recalled = await conversation.async_converse(
            hass,
            text="my balance details",
            conversation_id=result.conversation_id,
            context=Context(user_id=owner.id),
            language="en",
            agent_id=agents[0],
        )
        assert "No records" in recalled.as_dict()["response"]["speech"]["plain"]["speech"]
        await run_llm_api(hass, entry, owner)
        flow = await options("conversation")
        flow = await submit(flow, {"enabled": False, "timeout": 5})
        assert flow["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.assistant is None
        print(
            "PASS: real HA model options/fallback, nonblocking Telegram queue, "
            "confirmation buttons and authenticated Assist context"
        )


async def run_llm_api(hass, entry, owner):
    from homeassistant.core import Context
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import llm

    context = llm.LLMContext(
        platform="synthetic_agent",
        context=Context(user_id=owner.id),
        language="en",
        assistant="conversation",
        device_id=None,
    )
    api = await llm.async_get_api(hass, "family_assistant_" + entry.entry_id, context)
    assert {tool.name for tool in api.tools} == {"ReadFamily", "PrepareFamilyPlan"}
    records = await api.async_call_tool(llm.ToolInput(tool_name="ReadFamily", tool_args={}))
    assert "tasks" in records and "telegram_id" not in str(records) and "audit" not in records
    before = len(entry.runtime_data.engine.snapshot()["shopping"])
    preview = await api.async_call_tool(
        llm.ToolInput(
            tool_name="PrepareFamilyPlan",
            tool_args={
                "request": "Buy bread",
                "commands": [{"action": "shopping.add", "payload": {"name": "Bread"}}],
            },
        )
    )
    assert preview["applied"] is False and preview["proposal_id"].startswith("P")
    assert len(entry.runtime_data.engine.snapshot()["shopping"]) == before
    try:
        await api.async_call_tool(
            llm.ToolInput(
                tool_name="PrepareFamilyPlan",
                tool_args={
                    "request": "Make owner",
                    "commands": [{"action": "members.save", "payload": {}}],
                },
            )
        )
    except HomeAssistantError:
        pass
    else:
        raise AssertionError("LLM API accepted a forbidden tool action")
    try:
        await llm.async_get_api(
            hass,
            "family_assistant_" + entry.entry_id,
            llm.LLMContext(
                platform="synthetic_agent",
                context=None,
                language="en",
                assistant="conversation",
                device_id=None,
            ),
        )
    except HomeAssistantError:
        pass
    else:
        raise AssertionError("LLM API accepted an anonymous context")
    print(
        "PASS: real HA bounded LLM API, non-mutating preview, "
        "invalid tool/anonymous denial and learned phrase"
    )
