"""Authenticated developer report WebSocket boundary and immutable scope tests."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from copy import deepcopy
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import voluptuous as vol
from test_command_scope import NOW, Store, harness
from test_command_scope import command_scope as command_scope

from custom_components.family_assistant.domain import developer_diagnostics as diag
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.shadow import SCHEMA as SHADOW_SCHEMA

_SEMVER_REGEX = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(alpha|beta|rc)\.(0|[1-9][0-9]*))?\Z",
    re.ASCII,
)


class _ConfigEntryState(Enum):
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"


@pytest.fixture
def developer_api(monkeypatch, command_scope):
    homeassistant = ModuleType("homeassistant")
    components = ModuleType("homeassistant.components")
    websocket_api = ModuleType("homeassistant.components.websocket_api")
    config_entries = ModuleType("homeassistant.config_entries")

    def websocket_command(schema):
        command_schema = vol.Schema(schema, extra=vol.PREVENT_EXTRA)

        def decorate(function):
            function.command_schema = command_schema
            return function

        return decorate

    websocket_api.websocket_command = websocket_command
    websocket_api.async_response = lambda function: function
    config_entries.ConfigEntryState = _ConfigEntryState
    components.websocket_api = websocket_api
    homeassistant.components = components
    homeassistant.config_entries = config_entries

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.websocket_api": websocket_api,
        "homeassistant.config_entries": config_entries,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.setitem(
        sys.modules, "custom_components.family_assistant.command_scope", command_scope
    )

    module_path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "family_assistant"
        / "developer_api.py"
    )
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.developer_api", module_path
    )
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "custom_components.family_assistant.developer_api", loaded)
    assert spec.loader is not None
    spec.loader.exec_module(loaded)
    return loaded


class Connection:
    def __init__(self, user: Any) -> None:
        self.user = user
        self.results: list[tuple[int, dict[str, Any]]] = []
        self.errors: list[tuple[int, str, str]] = []

    def send_result(self, message_id: int, result: dict[str, Any]) -> None:
        self.results.append((message_id, deepcopy(result)))

    def send_error(self, message_id: int, code: str, message: str) -> None:
        self.errors.append((message_id, code, message))


@pytest.mark.asyncio
async def test_owner_report_success_bounded_version(developer_api, command_scope) -> None:
    hass, entry, runtime, engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = async_add_executor_job
    connection = Connection(user)

    msg = {
        "id": 1,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.errors
    assert len(connection.results) == 1
    msg_id, result = connection.results[0]
    assert msg_id == 1
    assert result["format"] == "family_assistant_defect_report"
    assert result["schema"] == 1
    assert result["cases"] == []
    assert result["overflow_count"] == 0
    assert result["saturated"] is False
    assert result["limitations"] == [
        "technical_observations_only",
        "no_message_content",
        "not_a_semantic_reproducer",
    ]

    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "family_assistant"
        / "manifest.json"
    )
    manifest_version = json.loads(manifest_path.read_text(encoding="utf-8"))["version"]
    assert result["version"] == manifest_version
    assert _SEMVER_REGEX.fullmatch(result["version"])
    assert len(result["version"]) <= 64

    # With recorded failure cases after owner enables diagnostics
    await engine.execute(
        "owner",
        "settings.developer_policy",
        {"enabled": True, "expected_generation": 1},
        "op-enable",
        NOW,
    )

    def record_case(ctx):
        diag.record_failure(
            ctx.state,
            generation=2,
            code="provider_timeout",
            has_quote=True,
            has_refs=False,
        )

    await engine.system_update("record", NOW, record_case)

    connection_with_case = Connection(user)
    msg_enabled = {
        "id": 2,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 2,
    }
    await developer_api.report(hass, connection_with_case, msg_enabled)

    assert not connection_with_case.errors
    assert len(connection_with_case.results) == 1
    _, result_enabled = connection_with_case.results[0]
    assert result_enabled["cases"] == [
        {
            "stage": "assistant_job",
            "code": "provider_timeout",
            "has_quote": True,
            "has_refs": False,
            "count": 1,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_version",
    [
        "not-a-semver",
        "1.0",
        "",
        "v1.0.0",
        "1.0.0-unknown.1",
        "1.0.0." + "0" * 70,
        None,
        123,
    ],
)
async def test_fixed_error_for_malformed_version_strings(
    developer_api, command_scope, bad_version
) -> None:
    hass, entry, _runtime, _engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return bad_version

    hass.async_add_executor_job = async_add_executor_job
    connection = Connection(user)

    msg = {
        "id": 1,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.results
    assert connection.errors == [(1, "invalid_field", "invalid_field")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manifest_error",
    [
        OSError("manifest disk read failed"),
        json.JSONDecodeError("Expecting value", "bad json", 0),
        KeyError("version"),
    ],
)
async def test_fixed_error_for_manifest_io_and_decode_failure(
    developer_api, command_scope, manifest_error
) -> None:
    hass, entry, _runtime, _engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        raise manifest_error

    hass.async_add_executor_job = async_add_executor_job
    connection = Connection(user)

    msg = {
        "id": 1,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.results
    assert connection.errors == [(1, "invalid_field", "invalid_field")]


@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt_mode", ["bad_schema", "non_dict_diag", "non_dict_memory"])
async def test_fixed_error_for_malformed_store(developer_api, command_scope, corrupt_mode) -> None:
    hass, entry, _runtime, engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = async_add_executor_job

    def corrupt(ctx):
        if corrupt_mode == "bad_schema":
            ctx.state["memory"]["developer_diagnostics"] = {"schema": 999}
        elif corrupt_mode == "non_dict_diag":
            ctx.state["memory"]["developer_diagnostics"] = "not-a-dict"
        else:
            ctx.state["memory"] = "not-a-dict"

    await engine.system_update("corrupt", NOW, corrupt)

    connection = Connection(user)
    msg = {
        "id": 1,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.results
    assert connection.errors == [(1, "conflict", "conflict")]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["parent", "child", "adult", "guest"])
async def test_forbidden_for_non_owner_roles(developer_api, command_scope, role) -> None:
    hass, entry, runtime, engine, _store, _owner_user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = async_add_executor_job

    member_user_id = f"ha-{role}"
    member_user = SimpleNamespace(id=member_user_id, is_active=True)

    def add_member(ctx):
        ctx.state["members"][role] = {
            "id": role,
            "name": f"Member {role}",
            "role": role,
            "language": "en",
            "ha_user_id": member_user_id,
            "aliases": [],
            "active": True,
            "revision": 1,
        }

    await engine.system_update("add_member", NOW, add_member)

    hass.auth.user = member_user
    connection = Connection(member_user)

    msg = {
        "id": 10,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.results
    assert connection.errors == [(10, "forbidden", "forbidden")]

    assert developer_api.source_view(runtime, role) is None


@pytest.mark.asyncio
async def test_forbidden_for_unauthenticated_or_unbound_user(developer_api, command_scope) -> None:
    hass, entry, _runtime, _engine, _store, _owner_user = harness(command_scope)

    stranger = SimpleNamespace(id="ha-stranger", is_active=True)
    hass.auth.user = stranger
    connection = Connection(stranger)

    msg = {
        "id": 15,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.results
    assert connection.errors == [(15, "forbidden", "forbidden")]


@pytest.mark.asyncio
async def test_no_names_provider_config_health_canaries(developer_api, command_scope) -> None:
    hass, entry, _runtime, engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = async_add_executor_job

    canaries = [
        "CANARY_HOUSEHOLD_NAME_9876",
        "CANARY_OWNER_NAME_5432",
        "CANARY_ALIAS_SECRET_1111",
        "CANARY_PROVIDER_API_KEY_2222",
        "CANARY_PROVIDER_MODEL_3333",
        "CANARY_CONFIG_PROMPT_4444",
        "CANARY_HEALTH_ENDPOINT_5555",
        "CANARY_HEALTH_INCIDENT_6666",
        "CANARY_TASK_SECRET_7777",
        "CANARY_SHOPPING_SECRET_8888",
    ]

    def inject(ctx):
        ctx.state["settings"]["name"] = "CANARY_HOUSEHOLD_NAME_9876"
        ctx.state["members"]["owner"]["name"] = "CANARY_OWNER_NAME_5432"
        ctx.state["members"]["owner"]["aliases"] = ["CANARY_ALIAS_SECRET_1111"]
        ctx.state["memory"]["provider_key"] = "CANARY_PROVIDER_API_KEY_2222"
        ctx.state["memory"]["provider_model"] = "CANARY_PROVIDER_MODEL_3333"
        ctx.state["settings"]["custom_prompt"] = "CANARY_CONFIG_PROMPT_4444"
        ctx.state["network"]["endpoint"] = "CANARY_HEALTH_ENDPOINT_5555"
        ctx.state["incidents"]["inc1"] = {"summary": "CANARY_HEALTH_INCIDENT_6666"}
        ctx.state["tasks"]["t1"] = {"title": "CANARY_TASK_SECRET_7777"}
        ctx.state["shopping"]["s1"] = {"name": "CANARY_SHOPPING_SECRET_8888"}

    await engine.system_update("inject", NOW, inject)

    connection = Connection(user)
    msg = {
        "id": 1,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.errors
    assert len(connection.results) == 1
    _, result = connection.results[0]

    raw = json.dumps(result)
    for canary in canaries:
        assert canary not in raw
    assert "CANARY_" not in raw
    assert set(result.keys()) == {
        "format",
        "schema",
        "version",
        "cases",
        "overflow_count",
        "saturated",
        "limitations",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_gen",
    [
        True,
        False,
        1.0,
        0.0,
        "1",
        2,
        0,
        -1,
        None,
    ],
)
async def test_expected_generation_strictly_exact_including_bool_rejection(
    developer_api, command_scope, bad_gen
) -> None:
    hass, entry, _runtime, _engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = async_add_executor_job
    connection = Connection(user)

    msg = {
        "id": 1,
        "type": "family_assistant/developer_report",
        "entry_id": entry.entry_id,
        "expected_generation": bad_gen,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.results
    assert connection.errors == [(1, "conflict", "conflict")]


@pytest.mark.asyncio
async def test_consent_aba_monotonically_advances_and_prevents_stale_access(
    developer_api, command_scope
) -> None:
    hass, entry, _runtime, engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = async_add_executor_job

    # State A: default disabled, gen 1
    # Advance to State B: enabled, gen 2
    await engine.execute(
        "owner",
        "settings.developer_policy",
        {"enabled": True, "expected_generation": 1},
        "op-enable",
        NOW,
    )

    # Advance to State A': disabled, gen 3 (same enabled=False as state A, but gen 3)
    await engine.execute(
        "owner",
        "settings.developer_policy",
        {"enabled": False, "expected_generation": 2},
        "op-disable",
        NOW,
    )

    # Stale generation 1 (State A) must be rejected
    conn_a = Connection(user)
    await developer_api.report(
        hass,
        conn_a,
        {
            "id": 101,
            "type": "family_assistant/developer_report",
            "entry_id": entry.entry_id,
            "expected_generation": 1,
        },
    )
    assert not conn_a.results
    assert conn_a.errors == [(101, "conflict", "conflict")]

    # Advance to State B': enabled, gen 4 (same enabled=True as state B, but gen 4)
    await engine.execute(
        "owner",
        "settings.developer_policy",
        {"enabled": True, "expected_generation": 3},
        "op-re-enable",
        NOW,
    )

    # Stale generation 2 (State B) must be rejected
    conn_b = Connection(user)
    await developer_api.report(
        hass,
        conn_b,
        {
            "id": 102,
            "type": "family_assistant/developer_report",
            "entry_id": entry.entry_id,
            "expected_generation": 2,
        },
    )
    assert not conn_b.results
    assert conn_b.errors == [(102, "conflict", "conflict")]

    # Concurrent ABA race during async manifest read
    async def toggle_during_manifest(target, *args):
        await engine.execute(
            "owner",
            "settings.developer_policy",
            {"enabled": False, "expected_generation": 4},
            "race-toggle-1",
            NOW,
        )
        await engine.execute(
            "owner",
            "settings.developer_policy",
            {"enabled": True, "expected_generation": 5},
            "race-toggle-2",
            NOW,
        )
        return target(*args)

    hass.async_add_executor_job = toggle_during_manifest
    conn_race = Connection(user)
    await developer_api.report(
        hass,
        conn_race,
        {
            "id": 103,
            "type": "family_assistant/developer_report",
            "entry_id": entry.entry_id,
            "expected_generation": 4,
        },
    )
    assert not conn_race.results
    assert conn_race.errors == [(103, "conflict", "conflict")]


@pytest.mark.asyncio
async def test_fresh_identity_recheck_after_async_manifest_read_deactivated_user(
    developer_api, command_scope
) -> None:
    hass, entry, _runtime, _engine, _store, user = harness(command_scope)

    # Pre-capture deactivated user
    user.is_active = False
    conn_pre = Connection(user)
    await developer_api.report(
        hass,
        conn_pre,
        {
            "id": 1,
            "type": "family_assistant/developer_report",
            "entry_id": entry.entry_id,
            "expected_generation": 1,
        },
    )
    assert not conn_pre.results
    assert conn_pre.errors == [(1, "forbidden", "forbidden")]

    # Active during capture, deactivated during async manifest read
    user.is_active = True

    async def deactivate_during_manifest(target, *args):
        user.is_active = False
        return target(*args)

    hass.async_add_executor_job = deactivate_during_manifest
    conn_post = Connection(user)
    await developer_api.report(
        hass,
        conn_post,
        {
            "id": 2,
            "type": "family_assistant/developer_report",
            "entry_id": entry.entry_id,
            "expected_generation": 1,
        },
    )
    assert not conn_post.results
    assert conn_post.errors == [(2, "forbidden", "forbidden")]


@pytest.mark.asyncio
async def test_fresh_identity_recheck_after_async_manifest_read_same_id_user_replacement(
    developer_api, command_scope
) -> None:
    hass, entry, _runtime, _engine, _store, user = harness(command_scope)

    async def replace_user_during_manifest(target, *args):
        hass.auth.user = SimpleNamespace(id=user.id, is_active=True)
        return target(*args)

    hass.async_add_executor_job = replace_user_during_manifest
    connection = Connection(user)
    await developer_api.report(
        hass,
        connection,
        {
            "id": 1,
            "type": "family_assistant/developer_report",
            "entry_id": entry.entry_id,
            "expected_generation": 1,
        },
    )
    assert not connection.results
    assert connection.errors == [(1, "conflict", "conflict")]


@pytest.mark.asyncio
async def test_fresh_identity_recheck_after_async_manifest_read_runtime_replacement(
    developer_api, command_scope
) -> None:
    hass, entry, runtime, engine, _store, user = harness(command_scope)

    async def replace_runtime_during_manifest(target, *args):
        replacement = type(runtime)(Engine(engine.snapshot(), Store().save))
        entry.runtime_data = replacement
        hass.data["family_assistant"]["entries"][entry.entry_id] = replacement
        return target(*args)

    hass.async_add_executor_job = replace_runtime_during_manifest
    connection = Connection(user)
    await developer_api.report(
        hass,
        connection,
        {
            "id": 1,
            "type": "family_assistant/developer_report",
            "entry_id": entry.entry_id,
            "expected_generation": 1,
        },
    )
    assert not connection.results
    assert connection.errors == [(1, "conflict", "conflict")]


@pytest.mark.asyncio
async def test_shadow_mode_denial(developer_api, command_scope) -> None:
    store = Store()
    shadow_state = new_state("ha-owner", "Shadow household", modules=[])
    shadow_state["schema_version"] = SHADOW_SCHEMA
    shadow_state["migration_shadow"] = {
        "version": 1,
        "mode": "read_only",
        "source_fingerprint": "a" * 64,
        "conversion_fingerprint": "b" * 64,
    }
    shadow_engine = Engine(shadow_state, store.save)
    assert shadow_engine.shadow_mode is True

    hass, standard_entry, standard_runtime, _engine, _store, user = harness(command_scope)

    async def async_add_executor_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = async_add_executor_job

    shadow_runtime = type(standard_runtime)(shadow_engine)
    shadow_entry = SimpleNamespace(
        entry_id="shadow-entry",
        domain="family_assistant",
        state=command_scope.ConfigEntryState.LOADED,
        runtime_data=shadow_runtime,
    )

    entries_map = {
        standard_entry.entry_id: standard_entry,
        shadow_entry.entry_id: shadow_entry,
    }
    hass.config_entries.async_get_entry = lambda eid: entries_map.get(eid)
    hass.data["family_assistant"]["entries"][shadow_entry.entry_id] = shadow_runtime

    connection = Connection(user)
    msg = {
        "id": 200,
        "type": "family_assistant/developer_report",
        "entry_id": shadow_entry.entry_id,
        "expected_generation": 1,
    }
    await developer_api.report(hass, connection, msg)

    assert not connection.results
    assert connection.errors == [(200, "forbidden", "forbidden")]

    assert developer_api.source_view(shadow_runtime, "owner") is None


def test_source_view_contracts(developer_api, command_scope) -> None:
    _hass, _entry, runtime, engine, _store, _user = harness(command_scope)

    # Owner on standard engine returns configuration
    view = developer_api.source_view(runtime, "owner")
    assert view == {
        "available": True,
        "enabled": False,
        "generation": 1,
        "count": 0,
        "saturated": False,
    }

    # Non-owner roles return None
    state = engine.snapshot()
    state["members"]["parent"] = {
        "id": "parent",
        "role": "parent",
        "active": True,
        "language": "en",
    }
    state["members"]["child"] = {
        "id": "child",
        "role": "child",
        "active": True,
        "language": "en",
    }
    parent_engine = Engine(state, Store().save)
    parent_runtime = type(runtime)(parent_engine)

    assert developer_api.source_view(parent_runtime, "parent") is None
    assert developer_api.source_view(parent_runtime, "child") is None


def test_websocket_command_schema(developer_api) -> None:
    schema = developer_api.report.command_schema
    valid = {
        "type": "family_assistant/developer_report",
        "entry_id": "scope-entry",
        "expected_generation": 1,
    }
    assert schema(valid) == valid

    with pytest.raises(vol.Invalid):
        schema({"type": "wrong_type", "entry_id": "scope-entry", "expected_generation": 1})

    with pytest.raises(vol.Invalid):
        schema({"type": "family_assistant/developer_report", "expected_generation": 1})

    with pytest.raises(vol.Invalid):
        schema({"type": "family_assistant/developer_report", "entry_id": "scope-entry"})

    with pytest.raises(vol.Invalid):
        schema(
            {
                "type": "family_assistant/developer_report",
                "entry_id": "scope-entry",
                "expected_generation": "not-an-int",
            }
        )
