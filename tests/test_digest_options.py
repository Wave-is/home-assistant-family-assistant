"""Digest Options use the actual Engine, policy guards and persistence contract."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant.domain import digest_settings as policy
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def options(monkeypatch, now):
    util = ModuleType("homeassistant.util")
    util.dt = SimpleNamespace(utcnow=lambda: now)
    monkeypatch.setitem(sys.modules, "homeassistant", ModuleType("homeassistant"))
    monkeypatch.setitem(sys.modules, "homeassistant.util", util)
    name = "custom_components.family_assistant._digest_options_test"
    path = Path(__file__).parents[1] / "custom_components/family_assistant/digest_options.py"
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class Flow:
    def __init__(self, engine):
        self.engine = engine
        self.runtime = SimpleNamespace(engine=engine, updated=lambda: None)
        self.config_entry = SimpleNamespace(options={"synthetic_unchanged": "preserve"})
        self.user_id = "synthetic-owner"
        self.fail_finish = False

    def _authorized_runtime(self):
        actor = self.engine.actor_for_ha(self.user_id)
        if self.engine.snapshot()["members"][actor]["role"] != "owner":
            raise DomainError("forbidden")
        return self.runtime, actor

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_create_entry(self, **kwargs):
        if self.fail_finish:
            raise OSError("synthetic private path must not escape")
        return {"type": "create_entry", **kwargs}


async def review(options, flow):
    initial = await options.policy_step(flow)
    values = initial["data_schema"]({})
    assert values == policy.values(flow.engine.snapshot())
    values["digest_morning_enabled"] = True
    values["digest_morning_time"] = "08:10"
    result = await options.policy_step(flow, values)
    assert result["step_id"] == "digest_policy_review" and not result["errors"]
    return deepcopy(flow._digest_review)


@pytest.mark.asyncio
async def test_named_policy_review_and_unrelated_options_preservation(options, engine, store):
    flow = Flow(engine)
    await review(options, flow)
    assert store.calls == 0
    result = await options.review_step(flow, {"confirmed": True})
    assert result["type"] == "create_entry"
    assert result["data"] == {"synthetic_unchanged": "preserve"}
    assert engine.snapshot()["settings"]["digest_morning_time"] == "08:10"
    assert engine.snapshot()["outbox"] == {}
    assert flow._digest_review is None


@pytest.mark.asyncio
async def test_store_and_finish_failure_reuse_exact_request(options, engine, store):
    flow = Flow(engine)
    await review(options, flow)
    operation = flow._digest_review["operation_id"]
    before = engine.snapshot()
    store.fail = True
    failed = await options.review_step(flow, {"confirmed": True})
    assert failed["errors"] == {"base": "storage_error"}
    assert engine.snapshot() == before and flow._digest_review["operation_id"] == operation
    store.fail = False
    flow.fail_finish = True
    failed = await options.review_step(flow, {"confirmed": True})
    assert failed["errors"] == {"base": "storage_error"}
    assert operation in engine.snapshot()["processed"]
    committed = engine.snapshot()
    calls = store.calls
    flow.fail_finish = False
    assert (await options.review_step(flow, {"confirmed": True}))["type"] == "create_entry"
    assert store.calls == calls and engine.snapshot() == committed


@pytest.mark.asyncio
async def test_revoked_review_never_renders_cached_policy(options, engine):
    flow = Flow(engine)
    await review(options, flow)
    flow.user_id = "synthetic-child"
    result = await options.review_step(flow)
    assert result == {"type": "abort", "reason": "forbidden"}
    assert flow._digest_review is None
    assert engine.snapshot()["processed"] == {}


@pytest.mark.asyncio
async def test_policy_or_epoch_change_invalidates_form_and_review(options, engine, now):
    flow = Flow(engine)
    initial = await options.policy_step(flow)
    selected = initial["data_schema"]({})
    selected["digest_morning_enabled"] = True
    state = engine.snapshot()
    await engine.execute(
        "owner",
        "settings.digest_policy",
        {
            "actor_revision": 1,
            "policy_fingerprint": policy.fingerprint(state),
            **policy.values(state),
            "digest_weekly_time": "17:00",
        },
        "another-policy",
        now,
    )
    result = await options.policy_step(flow, selected)
    assert result["errors"] == {"base": "conflict"}
    assert not hasattr(flow, "_digest_review")
    await review(options, flow)
    owner = engine.snapshot()["members"]["owner"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "owner",
            "revision": owner["revision"],
            "name": "Updated owner",
            "role": "owner",
        },
        "new-owner-epoch",
        now,
    )
    before = engine.snapshot()
    assert await options.review_step(flow, {"confirmed": True}) == {
        "type": "abort",
        "reason": "conflict",
    }
    assert engine.snapshot() == before


@pytest.mark.parametrize("input_value", [{"confirmed": 1}, {"confirmed": True, "extra": True}, {}])
@pytest.mark.asyncio
async def test_confirmation_is_explicit_strict_and_nonmutating(options, engine, input_value):
    flow = Flow(engine)
    await review(options, flow)
    before = engine.snapshot()
    rejected = await options.review_step(flow, input_value)
    assert rejected["errors"] == {"base": "invalid_field"}
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_cancel_and_invalid_weekday_do_not_save(options, engine):
    flow = Flow(engine)
    await review(options, flow)
    cancelled = await options.review_step(flow, {"confirmed": False})
    assert cancelled["step_id"] == "digests" and flow._digest_review is None
    values = cancelled["data_schema"]({})
    values["digest_weekly_weekday"] = True
    rejected = await options.policy_step(flow, values)
    assert rejected["errors"] == {"base": "invalid_field"}
    assert engine.snapshot()["processed"] == {}
