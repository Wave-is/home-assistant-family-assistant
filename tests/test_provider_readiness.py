"""Readiness follows the actual provider contracts, never guessed HTTP health."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_chat_api import chat_api  # noqa: F401 - isolated HA import boundary

from custom_components.family_assistant.assistant.image_jobs import ImageJobs
from custom_components.family_assistant.onboarding import item, readiness
from custom_components.family_assistant.panel_readiness import (
    conversation_configuration,
    image_connection,
)

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "family_assistant"
HTTP = {"url": "https://provider.invalid", "model": "synthetic-model", "api_key": "CANARY-KEY"}
AGENT = {"type": "ha_agent", "entity_id": "conversation.synthetic", "timeout": 15}


@pytest.mark.parametrize("slot", ["agy", "primary", "fallback", "ha_agent", "providers"])
def test_every_supported_provider_entry_is_recognized_without_discovery(engine, slot):
    config = {"enabled": True}
    if slot == "providers":
        config[slot] = [{**HTTP, "id": "agy-first", "kind": "agy"}]
    else:
        config[slot] = AGENT if slot == "ha_agent" else HTTP
    state = engine.snapshot()
    state["settings"]["modules"] = ["conversation"]
    before = deepcopy(config)
    for active in (False, True):
        result = readiness(state, {"conversation": config}, "owner", {"assistant_ready": active})
        models = item(result, "models")
        assert models["status"] == ("ready" if active else "attention")
        assert models["action"] == "provider_chain"
        assert "CANARY" not in json.dumps(result)
    assert config == before


@pytest.mark.parametrize("rows", [[], [{**HTTP, "id": "off", "kind": "agy", "enabled": False}]])
def test_explicit_empty_or_disabled_chain_never_revives_legacy_slots(engine, rows):
    config = {"enabled": True, "providers": rows, "primary": HTTP, "agy": HTTP}
    assert conversation_configuration(config) == {"configured": False, "search_enabled": False}
    state = engine.snapshot()
    state["settings"]["modules"] = ["conversation"]
    report = readiness(state, {"conversation": config}, "owner", {"assistant_ready": True})
    assert item(report, "models")["status"] == "attention"


@pytest.mark.parametrize(
    ("kind", "enabled", "opt_in", "expected"),
    [
        ("agy", True, True, True),
        ("agy", False, True, False),
        ("agy", True, False, False),
        ("ollama", True, False, False),
    ],
)
def test_agy_search_requires_an_enabled_explicit_opt_in(kind, enabled, opt_in, expected):
    config = {
        "enabled": True,
        "providers": [
            {**HTTP, "id": "source", "kind": kind, "enabled": enabled, "search_enabled": opt_in},
            {**HTTP, "id": "local", "kind": "ollama"},
        ],
    }
    assert conversation_configuration(config)["search_enabled"] is expected
    config["enabled"] = False
    assert conversation_configuration(config)["search_enabled"] is False


def test_authoritative_chain_ignores_dormant_legacy_search_opt_in():
    config = {
        "enabled": True,
        "providers": [{**HTTP, "id": "local", "kind": "ollama"}],
        "agy": {**HTTP, "search_enabled": True},
    }
    assert conversation_configuration(config)["search_enabled"] is False
    config["search"] = {"url": "https://search.invalid", "enabled": True}
    assert conversation_configuration(config)["search_enabled"] is True
    config["search"]["enabled"] = False
    assert conversation_configuration(config)["search_enabled"] is False


@pytest.mark.parametrize("enabled", [None, False, True])
def test_saved_legacy_search_count_is_not_a_claim_that_a_model_is_ready(enabled):
    config = {"search": {"url": "https://search.invalid", "enabled": True}}
    if enabled is not None:
        config["enabled"] = enabled
    assert conversation_configuration(config) == {"configured": False, "search_enabled": True}
    config["providers"] = []
    assert conversation_configuration(config) == {"configured": False, "search_enabled": False}


@pytest.mark.parametrize(
    "selection", [None, {}, {**AGENT, "timeout": True}, {**AGENT, "binding": {}}]
)
def test_native_adapter_row_requires_its_separate_valid_selection(selection):
    assert (
        conversation_configuration(
            {
                "enabled": True,
                "providers": [{"id": "native", "kind": "ha_agent"}],
                "ha_agent": selection,
            }
        )["configured"]
        is False
    )


@pytest.fixture
def panel_api(monkeypatch, chat_api):  # noqa: F811 - reuse HA import shims, real projection
    name = "custom_components.family_assistant._panel_provider_test"
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "panel_api.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def runtime_for(engine):
    return SimpleNamespace(
        engine=engine, assistant=object(), telegram=None, network=None, recipes=None, health={}
    )


def image_config():
    return {"enabled": True, "providers": [{**HTTP, "id": "draw", "type": "agy_gateway"}]}


def image_service(engine, config, now):
    return ImageJobs(
        engine, None, None, config, clock=lambda: now, scope_check=lambda: None, scope_id="entry"
    )


def test_panel_empty_chain_cannot_claim_configured_or_available_from_master_alone(
    panel_api,
    engine,
    now,
):
    engine._state["settings"]["modules"] = ["conversation"]
    runtime = runtime_for(engine)
    runtime.health["conversation"] = "connected"  # Old runtime has not reconciled yet.
    entry = SimpleNamespace(options={"conversation": {"enabled": True, "providers": []}})
    result = panel_api.project(runtime, entry, "owner", now)
    assert result["connections"]["conversation"]["configured"] is False
    assert result["connections"]["conversation"]["available"] is False
    assert (
        next(row for row in result["capabilities"] if row["id"] == "conversation")["ready"] is False
    )


def test_panel_constructed_agy_is_configured_but_not_verified_healthy(panel_api, engine, now):
    engine._state["settings"]["modules"] = ["conversation"]
    config = {"enabled": True, "providers": [{**HTTP, "id": "agy", "kind": "agy"}]}
    result = panel_api.project(
        runtime_for(engine), SimpleNamespace(options={"conversation": config}), "owner", now
    )
    assert result["connections"]["conversation"] == {
        "configured": True,
        "available": True,
        "health": None,
    }
    assert (
        next(row for row in result["capabilities"] if row["id"] == "conversation")["ready"] is None
    )
    assert "CANARY" not in json.dumps(result)


@pytest.mark.parametrize(
    "health", [None, "image_unavailable", "provider_quota_exceeded", "media_unavailable"]
)
def test_images_are_optional_not_an_added_required_capability(panel_api, engine, now, health):
    engine._state["settings"]["modules"] = ["conversation"]
    runtime, config = runtime_for(engine), image_config()
    runtime.image_generation = image_service(engine, config, now)
    runtime.health["images"] = health
    entry = SimpleNamespace(options={"image_generation": config})
    result = panel_api.project(runtime, entry, "owner", now)
    assert result["connections"]["image_generation"] == {
        "optional": True,
        "configured": True,
        "enabled": True,
        "available": True,
        "health": health,
    }
    assert not any(row["id"] == "image_generation" for row in result["capabilities"])
    assert "CANARY" not in json.dumps(result)
    assert panel_api.project(runtime, entry, "child", now)["connections"] == {}


@pytest.mark.parametrize("change", ["disabled", "module", "replaced", "closed"])
def test_disabled_or_replaced_image_adapter_is_not_available(engine, now, change):
    engine._state["settings"]["modules"] = ["conversation"]
    config = image_config()
    service = image_service(engine, config, now)
    if change == "disabled":
        config["enabled"] = False
    elif change == "module":
        engine._state["settings"]["modules"] = []
    elif change == "replaced":
        config["width"] = 768
    else:
        service.close()
    result = image_connection(engine.snapshot(), config, service, "image_unavailable")
    assert result["available"] is False
    if change in {"disabled", "module"}:
        assert result["enabled"] is False and result["health"] is None


def test_image_projection_never_passes_arbitrary_health_or_options_values(engine, now):
    config = image_config()
    engine._state["settings"]["modules"] = ["conversation"]
    result = image_connection(
        engine.snapshot(), config, image_service(engine, config, now), "CANARY-KEY"
    )
    assert result["health"] is None
    assert "CANARY" not in json.dumps(result)


def test_invalid_enabled_image_config_surfaces_only_known_optional_error(engine):
    engine._state["settings"]["modules"] = ["conversation"]
    result = image_connection(
        engine.snapshot(), {"enabled": True, "providers": []}, None, "provider_not_configured"
    )
    assert result == {
        "optional": True,
        "configured": False,
        "enabled": True,
        "available": False,
        "health": "provider_not_configured",
    }


def test_new_runtime_failure_codes_have_all_generated_translations():
    from custom_components.family_assistant.telegram.errors import ERRORS

    codes = {
        "image_busy",
        "image_invalid",
        "image_rejected",
        "image_too_large",
        "image_unavailable",
        "image_submission_uncertain",
        "image_delivery_uncertain",
        "image_model_unavailable",
        "provider_quota_exceeded",
        "provider_search_unsupported",
    }
    for language in ("en", "ru", "uk"):
        assert codes <= ERRORS[language].keys()
        assert all(ERRORS[language][code].strip() for code in codes)
