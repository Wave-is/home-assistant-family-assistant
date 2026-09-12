"""Existing-agent selection is owner-reviewed and preserves independent providers."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_article_options import Flow, home_assistant_config_entries  # noqa: F401

from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def setup(monkeypatch, home_assistant_config_entries):  # noqa: F811 - imported pytest fixture
    flow = Flow()
    flow.target_revision = 1
    flow.inspections = 0
    flow.after_inspect = None
    selector = ModuleType("homeassistant.helpers.selector")
    selector.EntitySelectorConfig = dict
    selector.EntitySelector = lambda _config: str
    monkeypatch.setitem(sys.modules, selector.__name__, selector)
    translation = sys.modules["homeassistant.helpers.translation"]

    async def labels(*_args):
        if flow.after_translation:
            callback, flow.after_translation = flow.after_translation, None
            callback()
        prefix = "component.family_assistant.selector.ha_agent_state.options."
        return {prefix + "enabled": "Enabled", prefix + "disabled": "Disabled"}

    monkeypatch.setattr(translation, "async_get_translations", labels)
    provider_module = ModuleType("custom_components.family_assistant.assistant.ha_agent_provider")

    class Provider:
        def __init__(self, hass, entry, config):
            assert hass is flow.hass and entry is flow.config_entry
            self.config = deepcopy(config)

        async def inspect(self):
            flow.inspections += 1
            proof = SimpleNamespace(
                revision=flow.target_revision,
                binding={
                    "config_entry_id": "synthetic-model",
                    "config_subentry_id": "synthetic-chat",
                },
            )
            if flow.after_inspect:
                callback, flow.after_inspect = flow.after_inspect, None
                callback()
            return proof

        def validate_review(self, proof):
            if proof.revision != flow.target_revision:
                raise DomainError("ha_agent_changed")

        async def generate_for_actor(self, *_args):
            raise AssertionError("Options must not invoke inference")

    provider_module.HAConversationAgent = Provider
    monkeypatch.setitem(sys.modules, provider_module.__name__, provider_module)
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components/family_assistant/assistant/ha_agent_options.py"
    )
    name = "custom_components.family_assistant.assistant._ha_agent_options_test"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return flow, module


INPUT = {"enabled": True, "entity_id": "conversation.synthetic", "timeout": 15}


async def begin(flow, module, values=None):
    result = await module.options_step(flow)
    assert result["step_id"] == "ha_agent"
    return await module.options_step(flow, deepcopy(INPUT if values is None else values))


async def test_initial_selection_is_optional_and_does_not_infer(setup):
    flow, module = setup
    result = await module.options_step(flow)
    assert result["data_schema"]({}) == {"enabled": False, "timeout": 15}
    assert not flow.inspections and not flow.created


async def test_enable_requires_separate_review_and_keeps_direct_credentials(setup):
    flow, module = setup
    before = deepcopy(flow.config_entry.options)
    review = await begin(flow, module)
    assert review["step_id"] == "ha_agent_review"
    assert review["data_schema"]({}) == {"confirmed": False}
    assert review["description_placeholders"] == {
        "entity": "conversation.synthetic",
        "state": "Enabled",
    }
    assert flow.config_entry.options == before and not flow.created
    result = await module.review_step(flow, {"confirmed": True})
    assert result["type"] == "create_entry"
    assert result["data"]["conversation"]["primary"] == before["conversation"]["primary"]
    assert result["data"]["unrelated"] == before["unrelated"]
    assert result["data"]["conversation"]["ha_agent"]["binding"] == {
        "config_entry_id": "synthetic-model",
        "config_subentry_id": "synthetic-chat",
    }


@pytest.mark.parametrize("primary", [True, False])
async def test_disable_removes_only_selection_and_preserves_other_options(setup, primary):
    flow, module = setup
    if not primary:
        flow.config_entry.options["conversation"].pop("primary")
    await begin(flow, module)
    await module.review_step(flow, {"confirmed": True})
    before = deepcopy(flow.config_entry.options)
    inspections = flow.inspections
    await begin(flow, module, {"enabled": False, "timeout": 15})
    result = await module.review_step(flow, {"confirmed": True})
    expected = deepcopy(before)
    expected["conversation"].pop("ha_agent")
    expected["conversation"]["enabled"] = primary
    assert result["data"] == expected
    assert flow.inspections == inspections


@pytest.mark.parametrize(
    "values",
    [
        {"enabled": 1, "timeout": 15},
        {"enabled": True, "timeout": True},
        {"enabled": True, "timeout": "15"},
        {"enabled": True, "timeout": 61},
        {"enabled": True},
        {**INPUT, "unknown": "no"},
    ],
)
async def test_bad_editor_input_never_reaches_target(setup, values):
    flow, module = setup
    result = await begin(flow, module, values)
    assert result["errors"]["base"] == "invalid_field"
    assert not flow.inspections and not flow.created


async def test_editor_accepts_maximum_timeout(setup):
    flow, module = setup
    result = await begin(flow, module, {**INPUT, "timeout": 60})
    assert result["step_id"] == "ha_agent_review"
    result = await module.review_step(flow, {"confirmed": True})
    assert result["data"]["conversation"]["ha_agent"]["timeout"] == 60


async def test_module_off_disallows_enabling_agent(setup):
    flow, module = setup
    flow.engine.state["settings"]["modules"] = []
    result = await begin(flow, module)
    assert result["errors"]["base"] == "module_disabled"
    assert not flow.inspections and not flow.created


@pytest.mark.parametrize("stage", ["editor", "inspect", "translations", "confirm"])
@pytest.mark.parametrize("mutation", ["role", "user", "options", "engine", "target"])
async def test_authority_and_target_changes_cannot_commit(setup, stage, mutation):
    flow, module = setup

    def change():
        if mutation == "role":
            flow.engine.state["members"]["owner"]["role"] = "parent"
        elif mutation == "user":
            flow.user.is_active = False
        elif mutation == "options":
            flow.config_entry.options["unrelated"]["keep"] = False
        elif mutation == "engine":
            flow.runtime.engine = SimpleNamespace(snapshot=flow.engine.snapshot)
        else:
            flow.target_revision += 1

    await module.options_step(flow)
    if stage == "editor":
        flow.after_user_lookup = change
    elif stage == "inspect":
        flow.after_inspect = change
    elif stage == "translations":
        flow.after_translation = change
    result = await module.options_step(flow, deepcopy(INPUT))
    if stage == "confirm":
        assert result["step_id"] == "ha_agent_review"
        flow.after_user_lookup = change
        result = await module.review_step(flow, {"confirmed": True})
    if stage == "editor" and mutation == "target":
        # Nothing was inspected/reviewed before this target changed; inspect the new target.
        assert result["type"] == "form" and result["step_id"] == "ha_agent_review"
    else:
        assert result["type"] == "abort", result
        assert result["reason"] in {"conflict", "forbidden", "ha_agent_changed"}
    assert not flow.created


async def test_unconfirmed_selection_returns_editor_without_mutation(setup):
    flow, module = setup
    await begin(flow, module)
    result = await module.review_step(flow, {"confirmed": False})
    assert result["step_id"] == "ha_agent" and flow._ha_agent_review is None
    assert not flow.created
