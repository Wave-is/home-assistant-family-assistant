"""Strict type boundaries for the real digest Options form."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import voluptuous as vol


@pytest.fixture
def options(monkeypatch, now):
    util = ModuleType("homeassistant.util")
    util.dt = SimpleNamespace(utcnow=lambda: now)
    monkeypatch.setitem(sys.modules, "homeassistant", ModuleType("homeassistant"))
    monkeypatch.setitem(sys.modules, "homeassistant.util", util)
    name = "custom_components.family_assistant._digest_schema_test"
    path = Path(__file__).parents[1] / "custom_components/family_assistant/digest_options.py"
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class Flow:
    def __init__(self, engine):
        self.engine = engine
        self.runtime = SimpleNamespace(engine=engine)
        self.user_id = "synthetic-owner"

    def _authorized_runtime(self):
        return self.runtime, "owner"

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}


@pytest.mark.asyncio
async def test_real_form_and_policy_keep_boolean_and_integer_types_strict(options, engine):
    flow = Flow(engine)
    form = await options.policy_step(flow)
    schema = form["data_schema"]
    values = schema({})
    before = engine.snapshot()

    with pytest.raises(vol.Invalid):
        schema({**values, "digest_morning_enabled": "false"})

    bool_weekday = schema({**values, "digest_weekly_weekday": True})
    assert bool_weekday["digest_weekly_weekday"] is True
    rejected = await options.policy_step(flow, bool_weekday)
    assert rejected["errors"] == {"base": "invalid_field"}
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_policy_step_rejects_string_boolean_when_called_without_schema(options, engine):
    flow = Flow(engine)
    form = await options.policy_step(flow)
    values = form["data_schema"]({})
    before = engine.snapshot()
    rejected = await options.policy_step(flow, {**values, "digest_evening_enabled": "false"})
    assert rejected["errors"] == {"base": "invalid_field"}
    assert engine.snapshot() == before
