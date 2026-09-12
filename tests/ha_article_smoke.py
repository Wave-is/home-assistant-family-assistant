"""Actual Home Assistant acceptance for explicit public-article requests."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import traceback
from contextlib import asynccontextmanager
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from aiohttp import ClientSession
from ha_options_menu import select_option

URL = "https://public.example/article"
FETCHED = {
    "title": "Synthetic public article",
    "text": "Synthetic public evidence for an explicit request.",
    "requested_url": URL,
    "final_url": "https://public.example/final",
}


class _SetupDiagnostics(logging.Handler):
    """Capture bounded structural exception evidence without messages or args."""

    def __init__(self):
        super().__init__()
        self.exceptions = []

    def emit(self, record):
        info = record.exc_info
        if not isinstance(info, tuple) or len(info) != 3 or info[0] is None:
            return
        frames = traceback.extract_tb(info[2])[-12:] if info[2] is not None else []
        self.exceptions.append(
            {
                "exception": getattr(info[0], "__name__", "Exception"),
                "frames": [
                    {
                        "file": os.path.basename(frame.filename),
                        "function": frame.name,
                        "line": frame.lineno,
                    }
                    for frame in frames
                ],
            }
        )
        if len(self.exceptions) > 12:
            del self.exceptions[:-12]


async def _lifecycle(hass, operation):
    diagnostics = _SetupDiagnostics()
    logger = logging.getLogger()
    logger.addHandler(diagnostics)
    try:
        result = await operation()
        await hass.async_block_till_done()
        return result, diagnostics.exceptions
    finally:
        logger.removeHandler(diagnostics)


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/article-smoke"
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


async def _view(hass, entry, user, identifier):
    return await _message(
        hass,
        user,
        {
            "id": identifier,
            "type": "family_assistant/view",
            "entry_id": entry.entry_id,
        },
    )


def _request(entry, identifier, source_revision, operation_id):
    return {
        "id": identifier,
        "type": "family_assistant/article",
        "entry_id": entry.entry_id,
        "url": URL,
        "operation_id": operation_id,
        "source_revision": source_revision,
    }


async def _set_policy(hass, entry, owner, *, enabled, allow_children):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": owner.id}
    )
    assert flow["type"] == "menu" and flow["step_id"] == "init", flow
    form = await select_option(hass, flow, "articles")
    assert form["type"] == "form" and form["step_id"] == "articles", form
    review = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {"enabled": enabled, "allow_children": allow_children},
    )
    assert review["type"] == "form" and review["step_id"] == "article_policy_review", review
    result = await hass.config_entries.options.async_configure(
        review["flow_id"], {"confirmed": True}
    )
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    return result


class _Cascade:
    def __init__(self):
        self.calls = 0

    @staticmethod
    async def check_scope(scope_check):
        result = scope_check()
        if inspect.isawaitable(result):
            await result

    async def generate(self, messages, schema, validate, *, scope_check=None):
        del schema
        self.calls += 1
        assert messages and all("http" not in str(message).lower() for message in messages)
        await self.check_scope(scope_check)
        return validate({"kind": "answer", "text": "Synthetic answer without a URL."})


class _Fetcher:
    def __init__(self, *, blocked=False):
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()

    async def __call__(self, url, *, scope_check):
        self.calls += 1
        assert url == URL
        await scope_check()
        self.started.set()
        await self.release.wait()
        await scope_check()
        return deepcopy(FETCHED)


async def _install_synthetic(runtime, *, blocked=False):
    from custom_components.family_assistant.assistant.article_service import ArticleService

    previous = runtime.articles
    if previous is not None:
        await previous.async_stop()
    cascade = _Cascade()
    runtime.assistant.cascade = cascade
    fetcher = _Fetcher(blocked=blocked)
    runtime.articles = ArticleService(cascade, fetcher=fetcher)
    return runtime.articles, cascade, fetcher


async def _verify_enabled(hass, entry, owner, child_id):
    from homeassistant import config_entries

    from custom_components.family_assistant.assistant.article_service import ArticleService

    enabled = await _set_policy(hass, entry, owner, enabled=True, allow_children=False)
    assert enabled["data"]["articles"]["enabled"] is True
    assert enabled["data"]["articles"]["allow_children"] is False
    assert len(enabled["data"]["articles"]["revision"]) == 32
    runtime = entry.runtime_data
    engine = runtime.engine
    assert isinstance(runtime.articles, ArticleService)
    assert runtime.assistant is not None
    assert runtime.articles.cascade is runtime.assistant.cascade
    configured_source = await _view(hass, entry, owner, 609)
    assert configured_source["success"], configured_source
    assert configured_source["result"]["article_source"] == {
        "enabled": True,
        "configured": True,
        "allowed": True,
        "revision": runtime.article_revision,
    }
    child_record = engine.snapshot()["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None

    service, cascade, fetcher = await _install_synthetic(runtime)
    source_revision = runtime.article_revision
    source = await _view(hass, entry, owner, 610)
    assert source["success"], source
    assert source["result"]["article_source"] == {
        "enabled": True,
        "configured": True,
        "allowed": True,
        "revision": source_revision,
    }

    before = deepcopy(engine.snapshot())
    response = await _message(
        hass,
        owner,
        _request(entry, 611, source_revision, "ha-article-owner"),
    )
    assert response["success"], response
    assert response["result"]["answer"] == "Synthetic answer without a URL."
    assert response["result"]["sources"] == [
        {
            "title": FETCHED["title"],
            "url": FETCHED["final_url"],
            "requested_url": URL,
            "retrieved_at": response["result"]["sources"][0]["retrieved_at"],
        }
    ]
    assert engine.snapshot() == before
    assert fetcher.calls == 1 and cascade.calls == 1

    denied = await _message(
        hass,
        child,
        _request(entry, 612, source_revision, "ha-article-child-denied"),
    )
    assert not denied["success"]
    assert denied["error"] == {
        "code": "forbidden",
        "message": "forbidden",
    }
    assert fetcher.calls == 1

    await service.async_stop()
    allowed = await _set_policy(hass, entry, owner, enabled=True, allow_children=True)
    assert allowed["data"]["articles"]["allow_children"] is True
    runtime = entry.runtime_data
    engine = runtime.engine
    service, cascade, fetcher = await _install_synthetic(runtime)
    source_revision = runtime.article_revision
    child_response = await _message(
        hass,
        child,
        _request(entry, 613, source_revision, "ha-article-child-allowed"),
    )
    assert child_response["success"], child_response
    assert child_response["result"]["answer"] == "Synthetic answer without a URL."
    assert fetcher.calls == 1 and cascade.calls == 1

    await service.async_stop()
    service, _, blocked = await _install_synthetic(runtime, blocked=True)
    async with _socket(hass, owner) as ws:
        await ws.send_json(
            _request(entry, 614, runtime.article_revision, "ha-article-generation-drift")
        )
        await asyncio.wait_for(blocked.started.wait(), 10)
        runtime.article_revision = uuid4().hex
        blocked.release.set()
        stale = await asyncio.wait_for(ws.receive_json(), 10)
    assert not stale["success"] and stale["error"]["code"] == "conflict"
    assert set(stale["error"]) == {"code", "message"}

    await service.async_stop()
    service, _, blocked = await _install_synthetic(runtime, blocked=True)
    async with _socket(hass, owner) as ws:
        await ws.send_json(_request(entry, 615, runtime.article_revision, "ha-article-unload"))
        await asyncio.wait_for(blocked.started.wait(), 10)
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert entry.state is config_entries.ConfigEntryState.NOT_LOADED
        unloaded = await asyncio.wait_for(ws.receive_json(), 10)
    assert not unloaded["success"]
    assert unloaded["error"] == {
        "code": "article_unavailable",
        "message": "article_unavailable",
    }
    assert service._workers == set()

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED
    print(
        "PASS: actual HA article Options, WS auth, synthetic fetch/model, "
        "child policy, generation revocation and unload settlement"
    )


async def _verify_articles_lifecycle(hass, entry, owner, child_id):
    """Verify article boundaries without depending on earlier smoke-test Options."""
    from homeassistant import config_entries

    original_options = deepcopy(dict(entry.options))
    configured_options = deepcopy(original_options)
    configured_options["conversation"] = {
        "enabled": True,
        "primary": {
            "url": "https://article-smoke.test.invalid",
            "model": "synthetic-article-model",
            "allow_http": False,
            "timeout": 5,
        },
    }
    configured_options["articles"] = {
        "enabled": False,
        "allow_children": False,
        "revision": uuid4().hex,
    }
    original_modules = list(entry.runtime_data.engine.snapshot()["settings"]["modules"])
    assert "conversation" in original_modules
    try:
        # Isolate this synthetic configuration with supported unload/setup
        # boundaries; no provider inspection or request occurs during setup.
        assert await hass.config_entries.async_unload(entry.entry_id)
        hass.config_entries.async_update_entry(entry, options=configured_options)
        setup, diagnostics = await _lifecycle(
            hass, lambda: hass.config_entries.async_setup(entry.entry_id)
        )
        assert setup, {
            "phase": "synthetic_setup",
            "state": str(entry.state),
            "diagnostics": diagnostics,
        }
        assert entry.state is config_entries.ConfigEntryState.LOADED
        assert entry.runtime_data.assistant is not None
        await _verify_enabled(hass, entry, owner, child_id)
        assert entry.runtime_data.engine.snapshot()["settings"]["modules"] == original_modules
    finally:
        if entry.state is config_entries.ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
        hass.config_entries.async_update_entry(entry, options=original_options)

        async def restore_operation():
            if entry.state is config_entries.ConfigEntryState.SETUP_ERROR:
                return await hass.config_entries.async_reload(entry.entry_id)
            return await hass.config_entries.async_setup(entry.entry_id)

        restored, diagnostics = await _lifecycle(hass, restore_operation)
        assert restored, {
            "phase": "original_restore",
            "state": str(entry.state),
            "diagnostics": diagnostics,
        }
        assert entry.state is config_entries.ConfigEntryState.LOADED
        assert dict(entry.options) == original_options


async def verify_articles(hass, entry, owner, child_id):
    """Run with a real HTTP session but no HA multicast resolver in the test lab."""
    provider_session = ClientSession()
    try:
        with patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            return_value=provider_session,
        ):
            await _verify_articles_lifecycle(hass, entry, owner, child_id)
    finally:
        await provider_session.close()


__all__ = ["verify_articles"]
