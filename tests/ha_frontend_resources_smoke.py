"""Actual Home Assistant checks for Lovelace frontend resource registration."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

from aiohttp import ClientSession


async def verify_frontend_resources(hass, entry):
    """Exercise the real HA 2026.8 resource collection and HTTP static handler."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE, MODE_YAML
    from homeassistant.components.lovelace.resources import ResourceYAMLCollection
    from homeassistant.helpers import issue_registry as ir

    from custom_components.family_assistant.const import DOMAIN
    from custom_components.family_assistant.frontend_resources import (
        LEGACY_RESOURCE_URL,
        OWNERSHIP_QUERY,
        async_ensure_frontend_resource,
        async_prepare_frontend_resource,
        owned_fingerprint,
    )
    from custom_components.family_assistant.runtime import async_configure_frontend

    lovelace = hass.data[LOVELACE_DATA]
    assert lovelace.resource_mode == MODE_STORAGE
    collection = lovelace.resources
    await collection.async_get_info()
    resource = await async_prepare_frontend_resource(hass)

    initial_owned = [
        item for item in collection.async_items() if owned_fingerprint(item.get("url")) is not None
    ]
    assert len(initial_owned) == 1 and initial_owned[0]["url"] == resource.resource_url

    # Exercise the integration's per-installation lock with the actual HA collection.
    await collection.async_delete_item(initial_owned[0]["id"])
    concurrent = await asyncio.gather(
        *(async_ensure_frontend_resource(hass, resource) for _ in range(8))
    )
    assert [result.status for result in concurrent].count("created") == 1
    assert [result.status for result in concurrent].count("current") == 7
    owned = [
        item for item in collection.async_items() if owned_fingerprint(item.get("url")) is not None
    ]
    assert len(owned) == 1
    owned_id = owned[0]["id"]
    before = list(collection.async_items())
    assert (await async_ensure_frontend_resource(hass, resource)).status == "current"
    assert list(collection.async_items()) == before

    unrelated = await collection.async_create_item(
        {"res_type": "module", "url": "/local/family-assistant-smoke-unrelated.js"}
    )
    changed_hash = "f" * 64 if resource.fingerprint != "f" * 64 else "e" * 64
    changed = replace(
        resource,
        fingerprint=changed_hash,
        resource_url=(
            f"/family_assistant/frontend/{changed_hash}/family-assistant.js?{OWNERSHIP_QUERY}"
        ),
    )
    assert (await async_ensure_frontend_resource(hass, changed)).status == "updated"
    assert (
        next(item for item in collection.async_items() if item["id"] == owned_id)["url"]
        == changed.resource_url
    )
    assert (
        next(item for item in collection.async_items() if item["id"] == unrelated["id"])["url"]
        == unrelated["url"]
    )
    assert (await async_ensure_frontend_resource(hass, resource)).status == "updated"

    manual = await collection.async_create_item({"res_type": "module", "url": LEGACY_RESOURCE_URL})
    conflict_snapshot = list(collection.async_items())
    assert (await async_ensure_frontend_resource(hass, resource)).status == "manual_conflict"
    assert list(collection.async_items()) == conflict_snapshot
    peer = SimpleNamespace(health={"frontend": "stale-before-smoke"})
    hass.data[DOMAIN]["entries"]["frontend-resource-smoke-peer"] = peer
    try:
        await async_configure_frontend(hass, entry.runtime_data)
        assert entry.runtime_data.health["frontend"] == "frontend_resource_attention"
        assert peer.health["frontend"] == "frontend_resource_attention"
        assert ir.async_get(hass).async_get_issue(DOMAIN, "frontend_resource") is not None

        await collection.async_delete_item(manual["id"])
        await async_configure_frontend(hass, entry.runtime_data)
        assert "frontend" not in entry.runtime_data.health
        assert "frontend" not in peer.health
        assert ir.async_get(hass).async_get_issue(DOMAIN, "frontend_resource") is None
    finally:
        hass.data[DOMAIN]["entries"].pop("frontend-resource-smoke-peer", None)
    await collection.async_delete_item(unrelated["id"])

    original_mode = lovelace.resource_mode
    original_collection = lovelace.resources
    yaml_items = [{"type": "module", "url": LEGACY_RESOURCE_URL}]
    try:
        lovelace.resource_mode = MODE_YAML
        lovelace.resources = ResourceYAMLCollection(yaml_items)
        assert (await async_ensure_frontend_resource(hass, resource)).status == "yaml_current"
        assert yaml_items == [{"type": "module", "url": LEGACY_RESOURCE_URL}]
    finally:
        lovelace.resource_mode = original_mode
        lovelace.resources = original_collection

    versioned_root = resource.static_paths[0].url_path
    async with ClientSession() as session:
        async with session.get(f"http://127.0.0.1:8123{resource.resource_url}") as response:
            assert response.status == 200
            assert "max-age" in response.headers.get("Cache-Control", "")
            main = await response.text()
            assert 'from "./errors.js"' in main
        async with session.get(f"http://127.0.0.1:8123{versioned_root}/errors.js") as response:
            assert response.status == 200
            assert "max-age" in response.headers.get("Cache-Control", "")
            assert await response.read()
        async with session.get(f"http://127.0.0.1:8123{LEGACY_RESOURCE_URL}") as response:
            assert response.status == 200
            assert "max-age" not in response.headers.get("Cache-Control", "")

    print(
        "PASS: actual HA Lovelace storage collection ownership, version update, YAML refusal, "
        "idempotency and content-addressed module graph"
    )
