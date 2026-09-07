"""Actual HA acceptance helper for standard Assist and Family LLM tools."""

from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy
from uuid import uuid4


def _speech(result):
    return result.as_dict()["response"]["speech"]["plain"]["speech"]


class _BlockedCascade:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    @staticmethod
    async def check_scope(scope_check):
        result = scope_check()
        if inspect.isawaitable(result):
            await result

    async def generate(self, _messages, _schema, validate, *, scope_check=None):
        await self.check_scope(scope_check)
        self.started.set()
        await self.release.wait()
        await self.check_scope(scope_check)
        return validate({"kind": "answer", "text": "private stale Assist answer"})


async def verify_ha_assistant_scope(hass, entry, owner, child_id):
    """Exercise the real Assist entity, LLM API registry and reload boundary."""
    from homeassistant.components import conversation
    from homeassistant.core import Context
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import llm

    from custom_components.family_assistant.assistant.service import Assistant

    del child_id
    runtime = entry.runtime_data
    engine = runtime.engine
    registered = er.async_get(hass)
    agents = [
        value.entity_id
        for value in registered.entities.values()
        if value.domain == "conversation"
        and value.platform == "family_assistant"
        and value.config_entry_id == entry.entry_id
    ]
    assert len(agents) == 1, agents
    agent = agents[0]
    agent_state = hass.states.get(agent)
    assert agent_state is not None and agent_state.state != "unavailable"

    repeated_context = Context(id=uuid4().hex, user_id=owner.id)
    before_ids = set(engine.snapshot()["shopping"])
    item_name = "Synthetic standard Assist scoped item"
    first = await conversation.async_converse(
        hass,
        text=f"/buy {item_name}",
        conversation_id=None,
        context=repeated_context,
        language="en",
        agent_id=agent,
    )
    second = await conversation.async_converse(
        hass,
        text=f"/buy {item_name}",
        conversation_id=first.conversation_id,
        context=repeated_context,
        language="en",
        agent_id=agent,
    )
    assert _speech(first) == _speech(second)
    new_ids = set(engine.snapshot()["shopping"]) - before_ids
    assert len(new_ids) == 1
    assert "conversation_refs" not in engine.snapshot()["memory"]

    anonymous = await conversation.async_converse(
        hass,
        text="/ping",
        conversation_id=None,
        context=Context(),
        language="en",
        agent_id=agent,
    )
    assert "permission" in _speech(anonymous).lower()

    context = llm.LLMContext(
        platform="synthetic_scope_agent",
        context=Context(user_id=owner.id),
        language="en",
        assistant="conversation",
        device_id=None,
    )
    api = await llm.async_get_api(hass, f"family_assistant_{entry.entry_id}", context)
    read = await api.async_call_tool(llm.ToolInput(tool_name="ReadFamily", tool_args={}))
    assert "shopping" in read and "ha_user_id" not in str(read)
    proposal_before = set(engine.snapshot()["proposals"])
    tool = llm.ToolInput(
        tool_name="PrepareFamilyPlan",
        tool_args={
            "request": "Preview an external-model plan",
            "commands": [{"action": "shopping.add", "payload": {"name": "External preview only"}}],
        },
    )
    preview = await api.async_call_tool(tool)
    retry = await api.async_call_tool(tool)
    assert preview == retry and preview["applied"] is False
    assert len(set(engine.snapshot()["proposals"]) - proposal_before) == 1
    assert all(
        row["name"] != "External preview only" for row in engine.snapshot()["shopping"].values()
    )

    original_assistant = runtime.assistant
    original_revision = runtime.assistant_revision
    blocked = _BlockedCascade()
    runtime.assistant = Assistant(engine, blocked)
    try:
        request = asyncio.create_task(
            conversation.async_converse(
                hass,
                text="A synthetic unknown Assist question",
                conversation_id=None,
                context=Context(user_id=owner.id),
                language="en",
                agent_id=agent,
            )
        )
        await asyncio.wait_for(blocked.started.wait(), 10)
        runtime.assistant_revision = uuid4().hex
        blocked.release.set()
        stale = await asyncio.wait_for(request, 10)
        assert "private stale Assist answer" not in _speech(stale)
    finally:
        blocked.release.set()
        runtime.assistant = original_assistant
        runtime.assistant_revision = original_revision

    old_api = api
    old_engine = engine
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data is not runtime
    try:
        await old_api.async_call_tool(llm.ToolInput(tool_name="ReadFamily", tool_args={}))
    except HomeAssistantError:
        pass
    else:
        raise AssertionError("an old LLM API instance crossed a runtime reload")
    assert deepcopy(old_engine.snapshot())["revision"] >= 1
    print(
        "PASS: actual HA Assist and LLM tools pin user epoch, provider generation, "
        "retry IDs and runtime reload scope"
    )


__all__ = ["verify_ha_assistant_scope"]
