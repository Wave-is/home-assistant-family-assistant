"""School preparation reminder Options schema and localization contracts."""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import voluptuous as vol

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "family_assistant"


class _FlowBase:
    def __init_subclass__(cls, **_kwargs):
        return super().__init_subclass__()

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_show_menu(self, **kwargs):
        return {"type": "menu", **kwargs}

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}

    def async_create_entry(
        self,
        *,
        title=None,
        data,
        description=None,
        description_placeholders=None,
    ):
        return {
            "type": "create_entry",
            "title": title,
            "data": data,
            "description": description,
            "description_placeholders": description_placeholders,
        }


class _Select:
    def __init__(self, config):
        self.options = config["options"]

    def __call__(self, value):
        if value not in self.options:
            raise vol.Invalid("selection")
        return value


@pytest.fixture
def config_flow(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigFlow = _FlowBase
    config_entries.OptionsFlow = _FlowBase
    core = ModuleType("homeassistant.core")
    core.callback = lambda value: value
    helpers = ModuleType("homeassistant.helpers")
    selector = ModuleType("homeassistant.helpers.selector")
    selector.SelectSelectorConfig = lambda **kwargs: kwargs
    selector.SelectSelector = _Select
    helpers.selector = selector
    util = ModuleType("homeassistant.util")
    dt_util = ModuleType("homeassistant.util.dt")
    dt_util.utcnow = lambda: datetime(2026, 9, 7, tzinfo=UTC)
    util.dt = dt_util
    homeassistant.config_entries = config_entries
    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.selector": selector,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_util,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "custom_components.family_assistant._school_reminder_config_test"
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "config_flow.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Engine:
    def __init__(self, settings):
        self.settings = deepcopy(settings)
        self.calls = []

    def snapshot(self):
        return {"settings": deepcopy(self.settings)}

    async def execute(self, actor, action, payload, operation, _now):
        self.calls.append((actor, action, deepcopy(payload), operation))
        self.settings.update(payload)
        return deepcopy(self.settings)


def _flow(module, settings):
    engine = _Engine(settings)
    runtime = SimpleNamespace(engine=engine, updated=lambda: None)
    flow = module.FamilyOptionsFlow()
    flow._authorized_runtime = lambda: (runtime, "owner")
    flow.config_entry = SimpleNamespace(options={})
    flow.hass = SimpleNamespace(
        data={module.DOMAIN: {}},
        config=SimpleNamespace(time_zone="UTC"),
        config_entries=SimpleNamespace(async_update_entry=lambda *_args, **_kwargs: None),
    )
    return flow, engine


def _settings(module, **changes):
    return {
        "name": "Family",
        "language": "en",
        "timezone": "Europe/Kyiv",
        "modules": list(module.CONFIGURABLE_MODULES),
        "automatic_penalties": False,
        "daily_penalty_cap": 1,
        "pantry_expiry_reminders": False,
        "pantry_expiry_days": 3,
        **changes,
    }


def test_backup_allows_domain_receipt_but_blocks_options_commit(config_flow):
    flow = config_flow.FamilyOptionsFlow()
    flow.hass = SimpleNamespace(data={config_flow.DOMAIN: {"backup": object()}})
    flow.config_entry = SimpleNamespace(options={"existing": True})

    # An Engine action may have committed before backup acquired its Engine
    # lease. Finishing that flow writes no options and must acknowledge success.
    acknowledged = flow.async_create_entry(title="", data={"existing": True})
    blocked = flow.async_create_entry(title="", data={"existing": False})

    assert acknowledged["type"] == "create_entry"
    assert acknowledged["data"] == {"existing": True}
    assert blocked == {"type": "abort", "reason": "backup_in_progress"}


@pytest.mark.asyncio
async def test_general_schema_defaults_and_strict_values(config_flow):
    flow, _engine = _flow(config_flow, _settings(config_flow))
    form = await flow.async_step_general()
    defaults = dict(form["data_schema"]({}))
    assert defaults["school_preparation_reminders"] is False
    assert defaults["school_preparation_days_before"] == 1
    assert defaults["school_preparation_time"] == "20:00"

    for field, value in (
        ("school_preparation_reminders", 1),
        ("school_preparation_reminders", "true"),
        ("school_preparation_days_before", True),
        ("school_preparation_days_before", False),
        ("school_preparation_days_before", -1),
        ("school_preparation_days_before", 2),
        ("school_preparation_days_before", 1.0),
        ("school_preparation_days_before", "1"),
        ("school_preparation_time", "8:00"),
        ("school_preparation_time", "20:0"),
        ("school_preparation_time", "24:00"),
        ("school_preparation_time", "20:60"),
        ("school_preparation_time", 2000),
    ):
        with pytest.raises(vol.Invalid):
            form["data_schema"]({**defaults, field: value})

    for days in (0, 1):
        validated = form["data_schema"](
            {
                **defaults,
                "school_preparation_days_before": days,
                "school_preparation_time": "00:00" if days == 0 else "23:59",
            }
        )
        assert validated["school_preparation_days_before"] == days


@pytest.mark.asyncio
async def test_unrelated_general_save_preserves_existing_policy(config_flow):
    settings = _settings(
        config_flow,
        school_preparation_reminders=True,
        school_preparation_days_before=0,
        school_preparation_time="18:35",
    )
    flow, engine = _flow(config_flow, settings)
    user_input = {
        "name": "Renamed family",
        "language": "uk",
        "timezone": "Europe/Kyiv",
        "automatic_penalties": False,
        "daily_penalty_cap": 1,
        "pantry_expiry_reminders": False,
        "pantry_expiry_days": 3,
        **{module: True for module in config_flow.CONFIGURABLE_MODULES},
    }

    result = await flow.async_step_general(user_input)

    assert result["type"] == "create_entry"
    payload = engine.calls[0][2]
    assert payload["school_preparation_reminders"] is True
    assert payload["school_preparation_days_before"] == 0
    assert payload["school_preparation_time"] == "18:35"


def test_locales_explain_global_and_per_recipient_controls():
    paths = {
        "strings": PACKAGE / "strings.json",
        "en": PACKAGE / "translations" / "en.json",
        "ru": PACKAGE / "translations" / "ru.json",
        "uk": PACKAGE / "translations" / "uk.json",
    }
    values = {
        language: json.loads(path.read_text(encoding="utf-8"))["options"]["step"]["general"]
        for language, path in paths.items()
    }
    keys = {
        "school_preparation_reminders",
        "school_preparation_days_before",
        "school_preparation_time",
    }
    for value in values.values():
        assert keys <= value["data"].keys()
        assert all(value["data"][key].strip() for key in keys)
    assert values["strings"] == values["en"]
    assert values["ru"]["data"] != values["en"]["data"]
    assert values["uk"]["data"] != values["en"]["data"]
    assert "each recipient" in values["en"]["description"]
    assert "School card" in values["en"]["description"]
    assert "household time zone" in values["en"]["description"]
    assert "do not create tasks" in values["en"]["description"]
    assert "каждый получатель" in values["ru"]["description"]
    assert "кожен одержувач" in values["uk"]["description"]
