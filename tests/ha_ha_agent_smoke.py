"""Actual Core Ollama conversation entity, synthetic model transport and no network."""

from copy import deepcopy
from types import MappingProxyType
from unittest.mock import patch
from uuid import uuid4

from ha_options_menu import select_option


async def verify_existing_ha_agent(hass, owner):
    from homeassistant.auth.const import GROUP_ID_USER
    from homeassistant.components import conversation
    from homeassistant.components.ollama.conversation import OllamaConversationEntity
    from homeassistant.config_entries import ConfigEntry, ConfigEntryState
    from homeassistant.core import Context
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.storage import Store
    from homeassistant.util import dt as dt_util

    from custom_components.family_assistant.assistant.ha_agent_provider import HAConversationAgent
    from custom_components.family_assistant.assistant.provider import (
        ActorProviderUnavailable,
        ActorRequest,
    )
    from custom_components.family_assistant.domain.validation import DomainError

    class Client:
        def __init__(self):
            self.calls = []
            self.response = '{"kind":"answer","text":"Synthetic native answer"}'
            self.tool_calls = None

        async def list(self):
            return {"models": []}

        async def chat(self, **kwargs):
            self.calls.append(deepcopy(kwargs))
            assert kwargs["tools"] is None, "HA control tools must never reach the model"

            async def chunks():
                message = {"role": "assistant", "content": self.response}
                if self.tool_calls is not None:
                    message["tool_calls"] = self.tool_calls
                yield {"message": message, "done": True}

            return chunks()

    client = Client()

    def entry(domain, title, data, options, subentries=None, version=1, minor=1):
        return ConfigEntry(
            domain=domain,
            title=title,
            data=data,
            options=options,
            version=version,
            minor_version=minor,
            source="user",
            unique_id=None,
            discovery_keys=MappingProxyType({}),
            subentries_data=subentries,
        )

    ollama_entry = entry(
        "ollama",
        "Synthetic native model",
        {"url": "http://192.0.2.1:11434"},
        {},
        [
            {
                "subentry_type": "conversation",
                "title": "Synthetic no-tools agent",
                "unique_id": None,
                "data": {"model": "synthetic-model", "llm_hass_api": None},
            },
            {
                "subentry_type": "conversation",
                "title": "Synthetic control agent",
                "unique_id": None,
                "data": {"model": "synthetic-model", "llm_hass_api": ["assist"]},
            },
        ],
        version=3,
        minor=3,
    )
    family = None
    with (
        patch("ollama.AsyncClient", return_value=client),
        patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            side_effect=AssertionError("HA-only inference must use its native transport"),
        ),
    ):
        await hass.config_entries.async_add(ollama_entry)
        try:
            await hass.async_block_till_done()
            assert ollama_entry.state is ConfigEntryState.LOADED
            entries = [
                r
                for r in er.async_get(hass).entities.values()
                if r.domain == "conversation" and r.config_entry_id == ollama_entry.entry_id
            ]
            assert len(entries) == 2
            safe = next(
                r.entity_id
                for r in entries
                if not conversation.async_get_agent(hass, r.entity_id).supported_features
            )
            unsafe = next(r.entity_id for r in entries if r.entity_id != safe)
            assert type(conversation.async_get_agent(hass, safe)) is OllamaConversationEntity
            assert hass.states.get(safe).state == "unknown"
            assert conversation.async_get_agent(hass, safe).available
            config = {"type": "ha_agent", "entity_id": safe, "timeout": 15}
            family = entry(
                "family_assistant",
                "Synthetic HA provider family",
                {
                    "owner_user_id": owner.id,
                    "owner_name": "Synthetic parent",
                    "language": "en",
                    "modules": ["shopping", "tasks", "conversation"],
                },
                {"conversation": {"enabled": False}, "synthetic_preserve": {"value": "keep"}},
            )
            await hass.config_entries.async_add(family)
            await hass.async_block_till_done()
            assert family.state is ConfigEntryState.LOADED
            assert family.runtime_data.assistant is None
            initial_options = deepcopy(dict(family.options))
            assert family.update_listeners, "Native setup did not register its update listener"
            flow = await hass.config_entries.options.async_init(
                family.entry_id, context={"user_id": owner.id}
            )
            form = await select_option(hass, flow, "ha_agent")
            assert form["type"] == "form" and form["step_id"] == "ha_agent", form
            denied = await hass.config_entries.options.async_configure(
                form["flow_id"], {"enabled": True, "entity_id": unsafe, "timeout": 15}
            )
            assert denied["errors"]["base"] == "ha_agent_unsupported", denied
            review = await hass.config_entries.options.async_configure(
                form["flow_id"], {"enabled": True, "entity_id": safe, "timeout": 15}
            )
            assert review["type"] == "form" and review["step_id"] == "ha_agent_review", review
            assert review["description_placeholders"]["entity"] == safe
            assert not client.calls
            assert dict(family.options) == initial_options
            result = await hass.config_entries.options.async_configure(
                review["flow_id"], {"confirmed": True}
            )
            assert result["type"] == "create_entry", result
            await hass.async_block_till_done()
            assert family.options["conversation"]["enabled"] is True
            assert family.options["synthetic_preserve"] == {"value": "keep"}
            assert family.options["conversation"]["ha_agent"]["binding"] == {
                "config_entry_id": ollama_entry.entry_id,
                "config_subentry_id": er.async_get(hass).async_get(safe).config_subentry_id,
            }
            runtime = family.runtime_data
            provider = runtime.assistant.cascade.providers[0]
            assert isinstance(provider, HAConversationAgent)
            await provider.inspect()
            assert not client.calls  # Selecting/inspecting is not an inference call.
            try:
                await HAConversationAgent(hass, family, {**config, "entity_id": unsafe}).inspect()
            except DomainError as error:
                assert error.code == "ha_agent_unsupported"
            else:
                raise AssertionError("Control-enabled native agent accepted")
            assert not client.calls

            family_agent = next(
                r.entity_id
                for r in er.async_get(hass).entities.values()
                if r.domain == "conversation" and r.config_entry_id == family.entry_id
            )
            before = runtime.engine.snapshot()
            response = await conversation.async_converse(
                hass,
                "Tell me a synthetic greeting",
                None,
                Context(user_id=owner.id),
                language="en",
                agent_id=family_agent,
            )
            assert (
                "Synthetic native answer"
                in response.as_dict()["response"]["speech"]["plain"]["speech"]
            )
            assert len(client.calls) == 1
            assert runtime.engine.snapshot()["shopping"] == before["shopping"]

            client.response = (
                '{"kind":"commands","operations":[{"action":"shopping.add",'
                '"payload":{"name":"Synthetic native carrots","quantity":1,"unit":"pcs"}}]}'
            )
            response = await conversation.async_converse(
                hass,
                "Please add synthetic carrots to the shopping list",
                None,
                Context(id=uuid4().hex, user_id=owner.id),
                language="en",
                agent_id=family_agent,
            )
            assert len(client.calls) == 2
            assert runtime.engine.snapshot()["shopping"] == before["shopping"]
            proposals = list(runtime.engine.snapshot()["proposals"].values())
            assert len(proposals) == 1
            await conversation.async_converse(
                hass,
                f"/confirm {proposals[0]['id']}",
                response.conversation_id,
                Context(user_id=owner.id),
                language="en",
                agent_id=family_agent,
            )
            assert len(runtime.engine.snapshot()["shopping"]) == len(before["shopping"]) + 1
            assert len(client.calls) == 2
            stored = await Store(hass, 1, f"family_assistant.{family.entry_id}").async_load()
            assert stored["shopping"] == runtime.engine.snapshot()["shopping"]
            member_id = runtime.engine.actor_for_ha(owner.id)
            member = runtime.engine.snapshot()["members"][member_id]
            client.response = "not JSON"
            try:
                await provider.generate_for_actor(
                    [{"role": "user", "content": "Synthetic malformed output check"}],
                    {},
                    ActorRequest(member_id, member["revision"], "en"),
                )
            except DomainError as error:
                assert error.code == "provider_bad_response"
            else:
                raise AssertionError("Malformed native agent output accepted")
            assert runtime.engine.snapshot()["shopping"] == stored["shopping"]
            client.response = '{"kind":"answer","text":"Must not accept tool injection"}'
            client.tool_calls = [
                {"function": {"name": "HassTurnOn", "arguments": {"name": "Synthetic light"}}}
            ]
            with patch("homeassistant.helpers.llm.async_get_api") as get_api:
                try:
                    await provider.generate_for_actor(
                        [{"role": "user", "content": "Synthetic unsolicited tool call check"}],
                        {},
                        ActorRequest(member_id, member["revision"], "en"),
                    )
                except DomainError as error:
                    assert error.code in {"provider_bad_response", "provider_unreachable"}
                else:
                    raise AssertionError("Native unsolicited tool call accepted")
                get_api.assert_not_called()
            assert runtime.engine.snapshot()["shopping"] == stored["shopping"]
            # Real non-admin HA user: own context, role-filtered request and no
            # inherited owner identity or private task text at the native model.
            client.tool_calls = None
            client.response = '{"kind":"answer","text":"Synthetic child answer"}'
            child_user = await hass.auth.async_create_user(
                "Synthetic native child", group_ids=[GROUP_ID_USER]
            )
            child_member = await runtime.engine.execute(
                member_id,
                "members.save",
                {
                    "name": "Synthetic native child",
                    "role": "child",
                    "language": "en",
                    "ha_user_id": child_user.id,
                },
                "native-agent-child",
                dt_util.utcnow(),
            )
            await runtime.engine.execute(
                member_id,
                "tasks.create",
                {"title": "PRIVATE-NATIVE-OWNER-CANARY", "assignee": member_id, "personal": True},
                "native-agent-private-task",
                dt_util.utcnow(),
            )
            with patch.object(
                conversation, "async_converse", wraps=conversation.async_converse
            ) as native_call:
                child_response = await conversation.async_converse(
                    hass,
                    "Tell me a synthetic story",
                    None,
                    Context(user_id=child_user.id),
                    language="en",
                    agent_id=family_agent,
                )
                selected_calls = [
                    call
                    for call in native_call.await_args_list
                    if call.kwargs.get("agent_id") == safe
                ]
            assert len(selected_calls) == 1
            assert selected_calls[0].kwargs["context"].user_id == child_user.id
            assert selected_calls[0].kwargs["conversation_id"] is None
            assert (
                "Synthetic child answer"
                in child_response.as_dict()["response"]["speech"]["plain"]["speech"]
            )
            assert "PRIVATE-NATIVE-OWNER-CANARY" not in str(client.calls[-1]["messages"])
            assert child_user.id not in str(client.calls[-1]["messages"])
            assert owner.id not in str(client.calls[-1]["messages"])
            count = len(client.calls)
            await hass.auth.async_update_user(child_user, is_active=False)
            try:
                await provider.generate_for_actor(
                    [{"role": "user", "content": "Synthetic revoked request"}],
                    {},
                    ActorRequest(child_member["id"], child_member["revision"], "en"),
                )
            except DomainError as error:
                assert error.code == "forbidden"
            else:
                raise AssertionError("Inactive native HA user accepted")
            assert len(client.calls) == count
            unlinked = await runtime.engine.execute(
                member_id,
                "members.save",
                {"name": "Synthetic Telegram-only child", "role": "child"},
                "native-agent-unlinked",
                dt_util.utcnow(),
            )
            try:
                await provider.generate_for_actor(
                    [{"role": "user", "content": "Synthetic unlinked request"}],
                    {},
                    ActorRequest(unlinked["id"], unlinked["revision"], "en"),
                )
            except ActorProviderUnavailable as error:
                assert error.code == "ha_agent_account_required"
            else:
                raise AssertionError("Unlinked caller borrowed an HA identity")
            assert len(client.calls) == count
            persisted_options = deepcopy(dict(family.options))
            persisted_state = runtime.engine.snapshot()
            assert await hass.config_entries.async_unload(family.entry_id)
            assert await hass.config_entries.async_setup(family.entry_id)
            await hass.async_block_till_done()
            assert dict(family.options) == persisted_options
            assert family.runtime_data is not runtime
            assert family.runtime_data.engine.snapshot()["shopping"] == persisted_state["shopping"]
            try:
                await provider.generate_for_actor(
                    [{"role": "user", "content": "Synthetic obsolete provider"}],
                    {},
                    ActorRequest(member_id, member["revision"], "en"),
                )
            except DomainError as error:
                assert error.code == "conflict"
            else:
                raise AssertionError("Old native adapter crossed runtime reload")
            await family.runtime_data.assistant.cascade.providers[0].inspect()
            off = await hass.config_entries.options.async_init(
                family.entry_id, context={"user_id": owner.id}
            )
            await select_option(hass, off, "ha_agent")
            off_review = await hass.config_entries.options.async_configure(
                off["flow_id"], {"enabled": False, "timeout": 15}
            )
            assert off_review["step_id"] == "ha_agent_review"
            off_result = await hass.config_entries.options.async_configure(
                off["flow_id"], {"confirmed": True}
            )
            assert off_result["type"] == "create_entry"
            await hass.async_block_till_done()
            assert family.runtime_data.assistant is None
            assert "ha_agent" not in family.options["conversation"]
            assert family.options["synthetic_preserve"] == {"value": "keep"}
            assert family.runtime_data.engine.snapshot()["shopping"] == persisted_state["shopping"]
            assert len(client.calls) == count
            print(
                "PASS: actual native Ollama entity and reviewed Options, no tool schema, "
                "explicit family proposal/confirmation, Store, malformed output and "
                "unsolicited tool-call denial, child identity/privacy, revoked/unlinked "
                "callers, exact Options/Store reload and provider disable"
            )
        finally:
            if family is not None:
                await hass.config_entries.async_unload(family.entry_id)
            await hass.config_entries.async_unload(ollama_entry.entry_id)
