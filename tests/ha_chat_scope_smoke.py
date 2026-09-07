"""Actual Home Assistant acceptance helper for scoped dashboard chat."""

from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from aiohttp import ClientSession


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/chat-scope-smoke"
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


async def _message(hass, user, message):
    async with _socket(hass, user) as ws:
        await ws.send_json(message)
        return await ws.receive_json()


def _request(entry, runtime, actor_revision, identifier, operation, content):
    return {
        "id": identifier,
        "type": "family_assistant/chat",
        "entry_id": entry.entry_id,
        "text": content,
        "operation_id": operation,
        "session_id": "actual-ha-chat-session",
        "actor_revision": actor_revision,
        "source_revision": runtime.assistant_revision,
    }


async def _wait_until(predicate, *, timeout=10):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


class _BlockedCascade:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    @staticmethod
    async def check_scope(scope_check):
        result = scope_check()
        if inspect.isawaitable(result):
            await result

    async def generate(self, _messages, _schema, validate, *, scope_check=None):
        self.calls += 1
        await self.check_scope(scope_check)
        self.started.set()
        await self.release.wait()
        await self.check_scope(scope_check)
        return validate({"kind": "answer", "text": "private stale provider answer"})


async def _setup(hass, entry):
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert result, {"state": str(entry.state)}


async def verify_chat_scope(hass, entry, owner, child_id):
    """Exercise real registration, runtime lifecycle and scoped Engine writes."""
    from custom_components.family_assistant import async_unload_entry
    from custom_components.family_assistant.assistant.chat_service import ChatService
    from custom_components.family_assistant.domain.validation import DomainError

    original_options = deepcopy(dict(entry.options))
    configured = deepcopy(original_options)
    configured["conversation"] = {
        "enabled": True,
        "primary": {
            "url": "https://chat-smoke.test.invalid",
            "model": "synthetic-chat-model",
            "allow_http": False,
            "timeout": 5,
        },
    }
    provider_session = ClientSession()
    try:
        with patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            return_value=provider_session,
        ):
            assert await hass.config_entries.async_unload(entry.entry_id)
            hass.config_entries.async_update_entry(entry, options=configured)
            await _setup(hass, entry)
            runtime = entry.runtime_data
            engine = runtime.engine
            assert isinstance(runtime.chat, ChatService)
            assert runtime.assistant is not None
            actor = engine.actor_for_ha(owner.id)
            actor_revision = engine.snapshot()["members"][actor]["revision"]

            view = await _message(
                hass,
                owner,
                {"id": 701, "type": "family_assistant/view", "entry_id": entry.entry_id},
            )
            assert view["success"], view
            assert view["result"]["conversation_source"] == {
                "enabled": True,
                "configured": True,
                "allowed": True,
                "revision": runtime.assistant_revision,
            }
            context_before_ping = deepcopy(engine.snapshot()["memory"].get("dashboard_chat"))
            ping = await _message(
                hass,
                owner,
                _request(entry, runtime, actor_revision, 702, "ha-chat-ping", "/ping"),
            )
            assert ping["success"] and isinstance(ping["result"]["reply"], str), ping
            assert engine.snapshot()["memory"].get("dashboard_chat") == context_before_ping

            child_record = engine.snapshot()["members"][child_id]
            child = await hass.auth.async_get_user(child_record["ha_user_id"])
            assert child is not None
            child_ping = await _message(
                hass,
                child,
                _request(
                    entry,
                    runtime,
                    child_record["revision"],
                    703,
                    "ha-chat-child-ping",
                    "/ping",
                ),
            )
            assert child_ping["success"], child_ping

            operation = "ha-chat-response-loss"
            item_name = "Synthetic chat response-loss item"
            before_ids = set(engine.snapshot()["shopping"])
            async with _socket(hass, owner) as ws:
                await ws.send_json(
                    _request(entry, runtime, actor_revision, 704, operation, f"/buy {item_name}")
                )
            await _wait_until(lambda: operation in engine.snapshot()["processed"])
            after_loss = engine.snapshot()
            new_ids = set(after_loss["shopping"]) - before_ids
            assert len(new_ids) == 1
            context = after_loss["memory"]["dashboard_chat"]
            assert item_name not in json.dumps(context)

            blocked = _BlockedCascade()
            runtime.assistant.cascade = blocked
            async with _socket(hass, owner) as ws:
                await ws.send_json(
                    _request(
                        entry,
                        runtime,
                        actor_revision,
                        705,
                        "ha-chat-provider-drift",
                        "A synthetic model question",
                    )
                )
                await asyncio.wait_for(blocked.started.wait(), 10)
                runtime.assistant_revision = uuid4().hex
                blocked.release.set()
                stale = await asyncio.wait_for(ws.receive_json(), 10)
            assert not stale["success"] and stale["error"]["code"] == "conflict"
            assert "private stale provider answer" not in repr(stale)

            # Probe the integration hook directly: HA makes FAILED_UNLOAD
            # nonrecoverable, so deliberately poisoning this shared fixture's
            # ConfigEntry state would prevent the later successful-unload test.
            # The real HA manager drives the successful unload below.
            current_runtime = runtime
            current_engine = engine
            with patch.object(
                hass.config_entries,
                "async_unload_platforms",
                new=AsyncMock(return_value=False),
            ):
                assert not await async_unload_entry(hass, entry)
            assert entry.runtime_data is current_runtime
            assert entry.state.name == "LOADED"
            await current_engine.system_update(
                "chat_failed_unload_probe", datetime.now(UTC), lambda _ctx: None
            )
            assert await hass.config_entries.async_unload(entry.entry_id)
            try:
                await current_engine.system_update(
                    "chat_closed_probe",
                    datetime.now(UTC),
                    lambda _ctx: None,
                )
            except DomainError as error:
                assert error.code == "not_ready"
            else:
                raise AssertionError("successfully unloaded Engine remained writable")
            try:
                await current_engine.execute(
                    actor,
                    "shopping.add",
                    {"name": "Must not be written by a closed Engine"},
                    "ha-chat-closed-engine",
                    datetime.now(UTC),
                )
            except DomainError as error:
                assert error.code == "not_ready"
            else:
                raise AssertionError("successfully unloaded Engine accepted a command")
            await _setup(hass, entry)
            runtime = entry.runtime_data
            engine = runtime.engine
            actor_revision = engine.snapshot()["members"][actor]["revision"]
            replay = await _message(
                hass,
                owner,
                _request(entry, runtime, actor_revision, 706, operation, f"/buy {item_name}"),
            )
            assert replay["success"], replay
            assert set(engine.snapshot()["shopping"]) - before_ids == new_ids
            print(
                "PASS: actual HA scoped chat, response-loss replay, provider revocation, "
                "failed-unload hook preservation and successful runtime retirement"
            )
    finally:
        try:
            if entry.state.name == "LOADED":
                await hass.config_entries.async_unload(entry.entry_id)
                await hass.async_block_till_done()
            hass.config_entries.async_update_entry(entry, options=original_options)
            await _setup(hass, entry)
        finally:
            await provider_session.close()


__all__ = ["verify_chat_scope"]
