"""Guided Options flow routing, localization and current-authority tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant.domain.engine import new_state

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "family_assistant"


@pytest.fixture
def module(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    helpers = ModuleType("homeassistant.helpers")
    translation = ModuleType("homeassistant.helpers.translation")

    async def translations(_hass, _language, _category, _integrations):
        return {
            "component.family_assistant.selector.onboarding_status.options.ready": "Готово",
            "component.family_assistant.selector.onboarding_status.options.attention": "Проверить",
            "component.family_assistant.selector.onboarding_status.options.optional": (
                "Необязательно"
            ),
            "component.family_assistant.selector.onboarding_status.options.off": "Выключено",
        }

    translation.async_get_translations = translations
    helpers.translation = translation
    homeassistant.helpers = helpers
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.translation", translation)
    name = "custom_components.family_assistant._onboarding_options_test"
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "onboarding_options.py")
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    assert spec.loader is not None
    spec.loader.exec_module(loaded)
    return loaded


def base_state():
    return new_state(
        "ha-owner",
        "Household",
        "ru",
        ["shopping", "tasks", "alarms"],
        timezone="Europe/Kyiv",
    )


class Engine:
    def __init__(self, state):
        self.state = state
        self.snapshots = 0

    def snapshot(self):
        self.snapshots += 1
        return deepcopy(self.state)


class Flow:
    def __init__(self, mixin, state=None, options=None):
        self.state = state or base_state()
        self.runtime = SimpleNamespace(engine=Engine(self.state), telegram=None, assistant=None)
        self.config_entry = SimpleNamespace(
            entry_id="entry-one", options=options or {}, runtime_data=self.runtime
        )
        self.hass = SimpleNamespace(
            config_entries=SimpleNamespace(
                async_get_entry=lambda entry_id: (
                    self.config_entry if entry_id == self.config_entry.entry_id else None
                )
            )
        )
        self.aborts = []
        self.menus = []
        self.authorizations = 0
        self.__class__ = type("MixedFlow", (mixin.GuidedOnboardingMixin, Flow), {})

    def _authorized_runtime(self):
        self.authorizations += 1
        return self.runtime, "owner"

    def async_show_menu(self, **kwargs):
        self.menus.append(kwargs)
        return {"type": "menu", **kwargs}

    def async_abort(self, *, reason):
        self.aborts.append(reason)
        return {"type": "abort", "reason": reason}


@pytest.mark.asyncio
async def test_guide_is_localized_read_only_and_routes_only_available_steps(module):
    flow = Flow(module)
    before_state = deepcopy(flow.state)
    before_options = deepcopy(flow.config_entry.options)

    result = await flow.async_step_guided_onboarding()

    assert result["type"] == "menu"
    assert result["step_id"] == "guided_onboarding"
    assert result["menu_options"] == [
        "general",
        "member",
        "telegram",
        "conversation",
        "search",
        "alarm_device",
        "guided_finish",
    ]
    placeholders = result["description_placeholders"]
    assert placeholders["household_status"] == "Готово"
    assert placeholders["telegram_status"] == "Выключено"
    assert placeholders["siren_status"] == "Необязательно"
    assert placeholders["active_members"] == "1"
    assert not ({"ready", "attention", "optional", "off"} & set(placeholders.values()))
    assert flow.state == before_state
    assert flow.config_entry.options == before_options
    assert flow.authorizations == 2


@pytest.mark.asyncio
async def test_ready_own_bot_reveals_enrollment_routes_but_no_bot_details(module):
    options = {
        "telegram": {
            "enabled": True,
            "token": "SECRET-TOKEN-CANARY",
            "bot": {"id": 992211, "username": "PRIVATE-BOT-CANARY"},
        }
    }
    flow = Flow(module, options=options)
    flow.runtime.telegram = object()

    result = await flow.async_step_guided_onboarding()

    assert result["menu_options"][3:5] == ["telegram_member", "telegram_group"]
    encoded = json.dumps(result, sort_keys=True)
    assert "SECRET-TOKEN-CANARY" not in encoded
    assert "PRIVATE-BOT-CANARY" not in encoded
    assert "992211" not in encoded


@pytest.mark.asyncio
async def test_finish_aborts_without_creating_or_updating_options(module):
    flow = Flow(module, options={"secret": "UNCHANGED-CANARY"})
    before = deepcopy(flow.config_entry.options)

    result = await flow.async_step_guided_finish()

    assert result == {"type": "abort", "reason": "guided_finished"}
    assert flow.config_entry.options == before
    assert flow.runtime.engine.snapshots == 1


@pytest.mark.asyncio
async def test_entry_replacement_fails_closed(module):
    flow = Flow(module)
    flow.hass.config_entries.async_get_entry = lambda _entry_id: SimpleNamespace(
        entry_id="entry-one"
    )

    result = await flow.async_step_guided_onboarding()

    assert result == {"type": "abort", "reason": "conflict"}
    assert flow.menus == []


@pytest.mark.asyncio
async def test_role_change_during_translation_cannot_leave_old_menu(module, monkeypatch):
    flow = Flow(module)

    async def revoke(_hass, _language, _category, _integrations):
        flow.state["members"]["owner"]["role"] = "parent"
        return {
            module._STATUS_PREFIX + status: status.title()
            for status in ("ready", "attention", "optional", "off")
        }

    monkeypatch.setattr(
        sys.modules["homeassistant.helpers.translation"], "async_get_translations", revoke
    )
    result = await flow.async_step_guided_onboarding()

    assert result == {"type": "abort", "reason": "forbidden"}
    assert flow.menus == []


@pytest.mark.asyncio
async def test_identity_epoch_change_during_translation_requires_fresh_flow(module, monkeypatch):
    flow = Flow(module)

    async def rebind(_hass, _language, _category, _integrations):
        flow.state["members"]["owner"]["revision"] += 1
        return {
            module._STATUS_PREFIX + status: status.title()
            for status in ("ready", "attention", "optional", "off")
        }

    monkeypatch.setattr(
        sys.modules["homeassistant.helpers.translation"], "async_get_translations", rebind
    )
    result = await flow.async_step_guided_onboarding()

    assert result == {"type": "abort", "reason": "conflict"}
    assert flow.menus == []


@pytest.mark.asyncio
async def test_missing_status_translation_never_displays_raw_enum(module, monkeypatch):
    async def missing(_hass, _language, _category, _integrations):
        return {}

    monkeypatch.setattr(
        sys.modules["homeassistant.helpers.translation"], "async_get_translations", missing
    )
    flow = Flow(module)

    result = await flow.async_step_guided_onboarding()

    assert result == {"type": "abort", "reason": "not_ready"}
    assert flow.menus == []
