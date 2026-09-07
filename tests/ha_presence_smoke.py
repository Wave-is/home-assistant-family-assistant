"""Actual Home Assistant presence Options, WebSocket and Store regression."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import ClientSession


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/presence-smoke"
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


async def _request(hass, entry, user, identifier, action="view", payload=None, operation=None):
    async with _socket(hass, user) as ws:
        message = (
            {
                "id": identifier,
                "type": "family_assistant/view",
                "entry_id": entry.entry_id,
            }
            if action == "view"
            else {
                "id": identifier,
                "type": "family_assistant/execute",
                "entry_id": entry.entry_id,
                "action": action,
                "payload": payload,
                "operation_id": operation or f"presence-ha-{identifier}",
            }
        )
        await ws.send_json(message)
        return await ws.receive_json()


async def _general_presence(hass, entry, owner, enabled):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": owner.id}
    )
    assert flow["type"] == "menu" and flow["step_id"] == "init", flow
    form = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "general"}
    )
    assert form["type"] == "form" and form["step_id"] == "general", form
    values = dict(form["data_schema"]({}))
    values["presence"] = enabled
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()


async def _presence_source(hass, entry, owner, member, enabled, entity_id=""):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": owner.id}
    )
    assert flow["type"] == "menu" and flow["step_id"] == "init", flow
    form = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "presence_sources"}
    )
    assert form["type"] == "form" and form["step_id"] == "presence_sources", form
    review = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "member": member,
            "enabled": enabled,
            "entity_id": entity_id,
            "presence_max_age_seconds": 300,
        },
    )
    assert review["type"] == "form" and review["step_id"] == "presence_source_review", review
    result = await hass.config_entries.options.async_configure(
        review["flow_id"], {"confirmed": True}
    )
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()


@contextmanager
def _state_reads(hass):
    reads = []
    # HA StateMachine uses slots: intercept its class method, retaining the real
    # state lookup, rather than trying to replace a read-only instance attribute.
    original = type(hass.states).get

    def read(machine, entity_id):
        if machine is hass.states:
            reads.append(entity_id)
        return original(machine, entity_id)

    with patch.object(type(hass.states), "get", new=read):
        yield reads


def _protected(engine):
    state = engine.snapshot()
    return {
        key: deepcopy(state[key])
        for key in (
            "tasks",
            "task_series",
            "shopping",
            "court",
            "rewards",
            "alarms",
            "alarm_runs",
            "routine_runs",
            "outbox",
        )
    }


async def verify_presence(hass, entry, owner_user):
    """Verify ephemeral presence against actual HA registry/state/auth boundaries."""
    from homeassistant import config_entries
    from homeassistant.auth.permissions.const import POLICY_READ
    from homeassistant.helpers import entity_registry

    from custom_components.family_assistant import presence_observations

    engine = entry.runtime_data.engine
    assert "presence" not in engine.view("owner", now=datetime.now(UTC))
    original_modules = list(engine.snapshot()["settings"]["modules"])
    await _general_presence(hass, entry, owner_user, True)
    engine = entry.runtime_data.engine
    assert set(engine.snapshot()["settings"]["modules"]) == {
        *original_modules,
        "presence",
    }
    owner = engine.snapshot()["members"]["owner"]
    assert owner["ha_user_id"] == owner_user.id

    registry = entity_registry.async_get(hass)
    first = registry.async_get_or_create(
        "person",
        "family_assistant",
        "synthetic-presence-owner",
        suggested_object_id="synthetic_presence_owner",
    )
    first_id = first.entity_id
    assert owner_user.permissions.check_entity(first_id, POLICY_READ)
    private_zone = "SYNTHETIC_PRIVATE_ZONE_CANARY"
    private_attribute = "SYNTHETIC_PRIVATE_COORDINATE_CANARY"
    hass.states.async_set(
        first_id,
        "home",
        {"latitude": private_attribute, "zone": private_zone},
    )
    await hass.async_block_till_done()
    await _presence_source(hass, entry, owner_user, "owner", True, first_id)
    engine = entry.runtime_data.engine
    source = entry.options["presence_sources"]["owner"]
    assert source["revision"] == 1 and source["entity_id"] == first_id
    assert first_id not in repr(engine.snapshot()["presence"])

    before_effects = _protected(engine)
    initial = await _request(hass, entry, owner_user, 1)
    assert initial["success"], initial
    self_row = initial["result"]["presence"]["self"]
    assert self_row["enabled"] is False and self_row["can_edit"] is True
    assert self_row["status"] == "unknown" and self_row["reason"] == "not_shared"
    consent_payload = {
        "member": "owner",
        "member_revision": owner["revision"],
        "binding_revision": source["revision"],
        "subscription_revision": None,
        "enabled": True,
    }
    consent = await _request(
        hass,
        entry,
        owner_user,
        2,
        "presence.access_set",
        consent_payload,
        "presence-ha-consent",
    )
    assert consent["success"] and consent["result"] == {
        "member": "owner",
        "revision": 1,
        "status": "enabled",
    }
    replay = await _request(
        hass,
        entry,
        owner_user,
        3,
        "presence.access_set",
        consent_payload,
        "presence-ha-consent",
    )
    assert replay["success"] and replay["result"] == consent["result"]

    before_view = engine.snapshot()
    with _state_reads(hass) as reads:
        current = await _request(hass, entry, owner_user, 4)
    assert current["success"], current
    assert reads == [first_id]
    row = current["result"]["presence"]["self"]
    assert row["status"] == "reported_home" and row["reason"] == "fresh"
    assert row["observed_at"] is not None
    assert engine.snapshot() == before_view
    assert "presence" not in engine.view("owner", now=datetime.now(UTC))
    encoded = repr(current["result"]["presence"])
    for canary in (first_id, private_zone, private_attribute, "latitude"):
        assert canary not in encoded
    state_text = repr(engine.snapshot())
    assert private_zone not in state_text and private_attribute not in state_text
    assert _protected(engine) == before_effects

    reported = hass.states.get(first_id).last_reported
    with patch(
        "custom_components.family_assistant.websocket.dt_util.utcnow",
        return_value=reported + timedelta(seconds=301),
    ):
        stale = await _request(hass, entry, owner_user, 5)
    assert stale["success"]
    assert stale["result"]["presence"]["self"]["status"] == "unknown"
    assert stale["result"]["presence"]["self"]["reason"] == "stale"

    class DeniedPermissions:
        def check_entity(self, entity_id, policy):
            assert entity_id == first_id and policy == POLICY_READ
            return False

    denied_user = SimpleNamespace(id=owner_user.id, permissions=DeniedPermissions())
    with _state_reads(hass) as reads:
        denied = presence_observations.project(
            hass,
            entry,
            entry.runtime_data,
            "owner",
            denied_user,
            datetime.now(UTC),
        )
    assert reads == []
    assert denied["self"]["status"] == "unknown"
    assert denied["self"]["reason"] == "unavailable"

    disabled_consent = await _request(
        hass,
        entry,
        owner_user,
        51,
        "presence.access_set",
        {**consent_payload, "subscription_revision": 1, "enabled": False},
        "presence-ha-consent-disable",
    )
    assert disabled_consent["success"] and disabled_consent["result"] == {
        "member": "owner",
        "revision": 2,
        "status": "disabled",
    }
    with _state_reads(hass) as reads:
        consent_revoked = await _request(hass, entry, owner_user, 52)
    assert consent_revoked["success"] and reads == []
    revoked_row = consent_revoked["result"]["presence"]["self"]
    assert revoked_row["enabled"] is False and revoked_row["reason"] == "not_shared"
    restored_consent = await _request(
        hass,
        entry,
        owner_user,
        53,
        "presence.access_set",
        {**consent_payload, "subscription_revision": 2},
        "presence-ha-consent-restore",
    )
    assert restored_consent["success"] and restored_consent["result"] == {
        "member": "owner",
        "revision": 3,
        "status": "enabled",
    }

    replacement = registry.async_get_or_create(
        "device_tracker",
        "family_assistant",
        "synthetic-presence-owner-replacement",
        suggested_object_id="synthetic_presence_owner_replacement",
    )
    replacement_id = replacement.entity_id
    hass.states.async_set(
        replacement_id,
        private_zone,
        {"longitude": private_attribute, "source_type": "gps"},
    )
    await hass.async_block_till_done()
    await _presence_source(hass, entry, owner_user, "owner", True, replacement_id)
    engine = entry.runtime_data.engine
    replacement_source = entry.options["presence_sources"]["owner"]
    assert replacement_source["revision"] == 2
    with _state_reads(hass) as reads:
        invalidated = await _request(hass, entry, owner_user, 6)
    assert invalidated["success"] and reads == []
    invalidated_row = invalidated["result"]["presence"]["self"]
    assert invalidated_row["enabled"] is False
    assert invalidated_row["binding_revision"] == 2
    assert invalidated_row["subscription_revision"] == 3

    renew_payload = {
        "member": "owner",
        "member_revision": owner["revision"],
        "binding_revision": 2,
        "subscription_revision": 3,
        "enabled": True,
    }
    renewed = await _request(
        hass,
        entry,
        owner_user,
        7,
        "presence.access_set",
        renew_payload,
        "presence-ha-renew",
    )
    assert renewed["success"] and renewed["result"]["revision"] == 4
    with _state_reads(hass) as reads:
        away = await _request(hass, entry, owner_user, 8)
    assert away["success"] and reads == [replacement_id]
    assert away["result"]["presence"]["self"]["status"] == "reported_away"
    assert private_zone not in repr(away["result"]["presence"])

    expected_presence = deepcopy(engine.snapshot()["presence"])
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == config_entries.ConfigEntryState.LOADED
    engine = entry.runtime_data.engine
    assert engine.snapshot()["presence"] == expected_presence
    assert first_id not in repr(engine.snapshot()["presence"])
    with _state_reads(hass) as reads:
        reloaded = await _request(hass, entry, owner_user, 9)
    assert reloaded["success"] and reads == [replacement_id]
    assert reloaded["result"]["presence"]["self"]["status"] == "reported_away"

    await _general_presence(hass, entry, owner_user, False)
    engine = entry.runtime_data.engine
    with _state_reads(hass) as reads:
        disabled = await _request(hass, entry, owner_user, 10)
    assert disabled["success"] and "presence" not in disabled["result"]
    assert reads == []
    disabled_replay = await _request(
        hass,
        entry,
        owner_user,
        11,
        "presence.access_set",
        renew_payload,
        "presence-ha-renew",
    )
    assert not disabled_replay["success"]
    assert disabled_replay["error"]["code"] == "module_disabled"

    await _general_presence(hass, entry, owner_user, True)
    engine = entry.runtime_data.engine
    owner = engine.snapshot()["members"]["owner"]
    member_edit = await _request(
        hass,
        entry,
        owner_user,
        12,
        "members.save",
        {
            "id": "owner",
            "revision": owner["revision"],
            "name": owner["name"] + " refreshed",
            "role": "owner",
        },
        "presence-ha-owner-refresh",
    )
    assert member_edit["success"], member_edit
    with _state_reads(hass) as reads:
        epoch_changed = await _request(hass, entry, owner_user, 13)
    assert epoch_changed["success"] and reads == []
    changed_row = epoch_changed["result"]["presence"]["self"]
    assert changed_row["status"] == "unknown" and changed_row["enabled"] is False
    assert _protected(engine) == before_effects
    final_state = engine.snapshot()
    for bucket in ("outbox", "audit", "processed", "memory"):
        assert private_zone not in repr(final_state[bucket])
        assert private_attribute not in repr(final_state[bucket])
    print(
        "PASS: actual HA presence source review, self consent, permission-scoped "
        "ephemeral projection, replacement, revocation and Store reload"
    )
