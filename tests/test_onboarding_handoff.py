"""Post-create guided onboarding handoff contract tests."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "family_assistant"
DOMAIN = "family_assistant"


@pytest.fixture
def module(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    data_entry_flow = ModuleType("homeassistant.data_entry_flow")

    class ConfigEntry:
        pass

    class ConfigEntryState(Enum):
        LOADED = "loaded"
        SETUP_RETRY = "setup_retry"
        SETUP_ERROR = "setup_error"
        NOT_LOADED = "not_loaded"

    class FlowType(Enum):
        OPTIONS_FLOW = "options_flow"

    class FlowResultType(Enum):
        MENU = "menu"
        ABORT = "abort"

    config_entries.SOURCE_USER = "user"
    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigEntryState = ConfigEntryState
    config_entries.ConfigFlowResult = dict
    config_entries.FlowType = FlowType
    data_entry_flow.FlowResultType = FlowResultType
    homeassistant.config_entries = config_entries
    homeassistant.data_entry_flow = data_entry_flow
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.data_entry_flow", data_entry_flow)
    name = "custom_components.family_assistant._onboarding_handoff_test"
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "onboarding_handoff.py")
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    assert spec.loader is not None
    spec.loader.exec_module(loaded)
    return loaded


class Engine:
    def __init__(self, user_id="ha-owner", role="owner", revision=1):
        self.user_id = user_id
        self.role = role
        self.revision = revision
        self.views = 0

    def actor_for_ha(self, user_id):
        if user_id != self.user_id:
            raise ValueError("unbound")
        return "owner"

    def view(self, actor):
        assert actor == "owner"
        self.views += 1
        return {"role": self.role}

    def snapshot(self):
        return {
            "members": {
                "owner": {
                    "id": "owner",
                    "active": True,
                    "role": self.role,
                    "ha_user_id": self.user_id,
                    "revision": self.revision,
                }
            }
        }


class OptionsManager:
    def __init__(self, module):
        self.module = module
        self.flows = {}
        self.next_id = 1
        self.init_calls = []
        self.aborted = []
        self.on_init = None
        self.option_writes = 0

    def add_flow(self, entry_id, context, data, step_id="guided_onboarding"):
        flow_id = f"flow-{self.next_id}"
        self.next_id += 1
        self.flows[flow_id] = {
            "flow_id": flow_id,
            "handler": entry_id,
            "context": dict(context),
            "init_data": data,
            "step_id": step_id,
        }
        return flow_id

    def _public(self, flow):
        return {key: flow[key] for key in ("flow_id", "handler", "context", "step_id")}

    def async_progress_by_handler(self, handler, include_uninitialized=False):
        del include_uninitialized
        return [self._public(flow) for flow in self.flows.values() if flow["handler"] == handler]

    def async_progress_by_init_data_type(self, kind, matcher, include_uninitialized=False):
        del include_uninitialized
        return [
            self._public(flow)
            for flow in self.flows.values()
            if type(flow["init_data"]) is kind and matcher(flow["init_data"])
        ]

    def async_get(self, flow_id):
        return self._public(self.flows[flow_id])

    async def async_init(self, handler, *, context, data):
        self.init_calls.append((handler, dict(context), dict(data)))
        flow_id = self.add_flow(handler, context, data)
        if self.on_init is not None:
            outcome = self.on_init(flow_id)
            if hasattr(outcome, "__await__"):
                await outcome
        return {
            "type": self.module.FlowResultType.MENU,
            "flow_id": flow_id,
            "handler": handler,
            "context": dict(context),
            "step_id": "guided_onboarding",
        }

    def async_abort(self, flow_id):
        self.aborted.append(flow_id)
        del self.flows[flow_id]


class ConfigEntries:
    def __init__(self, options):
        self.options = options
        self.entries = {}

    def async_get_entry(self, entry_id):
        return self.entries.get(entry_id)


def environment(module, *, entry_id="entry-new", role="owner", state=None):
    runtime = SimpleNamespace(engine=Engine(role=role))
    entry = module.ConfigEntry()
    entry.entry_id = entry_id
    entry.domain = DOMAIN
    entry.state = state or module.ConfigEntryState.LOADED
    entry.runtime_data = runtime
    options = OptionsManager(module)
    entries = ConfigEntries(options)
    entries.entries[entry_id] = entry
    user = SimpleNamespace(id="ha-owner", is_active=True, is_admin=True)

    class Auth:
        async def async_get_user(self, user_id):
            return user if user_id == user.id else None

    hass = SimpleNamespace(
        auth=Auth(),
        config_entries=entries,
        data={DOMAIN: {"entries": {entry_id: runtime}}},
    )
    return hass, entry, runtime, options, user


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"guided_onboarding_handoff": True}, True),
        ({"guided_onboarding_handoff": False}, False),
        ({"guided_onboarding_handoff": 1}, False),
        ({"guided_onboarding_handoff": True, "extra": True}, False),
        (None, False),
        (True, False),
    ],
)
def test_sentinel_match_is_exact(module, value, expected):
    assert module.is_guided_handoff(value) is expected


@pytest.mark.asyncio
async def test_exact_new_same_title_entry_gets_read_only_handoff(module):
    hass, entry, runtime, options, user = environment(module)
    old_runtime = SimpleNamespace(engine=Engine())
    old_entry = module.ConfigEntry()
    old_entry.entry_id = "entry-old"
    old_entry.domain = DOMAIN
    old_entry.state = module.ConfigEntryState.LOADED
    old_entry.runtime_data = old_runtime
    old_entry.title = entry.title = "Same title"
    hass.config_entries.entries[old_entry.entry_id] = old_entry
    hass.data[DOMAIN]["entries"][old_entry.entry_id] = old_runtime
    result = {"type": "create_entry", "result": entry, "options": {}}
    original_id = id(result)

    returned = await module.async_post_create_handoff(
        hass, result, {"source": "user", "user_id": user.id}
    )

    assert id(returned) == original_id
    assert returned["next_flow"] == (module.FlowType.OPTIONS_FLOW, "flow-1")
    assert options.init_calls == [
        (
            entry.entry_id,
            {"source": "user", "user_id": user.id},
            {"guided_onboarding_handoff": True},
        )
    ]
    assert options.flows["flow-1"]["handler"] == entry.entry_id
    assert options.option_writes == 0
    assert entry.runtime_data is runtime
    assert old_entry.runtime_data is old_runtime


@pytest.mark.asyncio
@pytest.mark.parametrize("state_name", ["SETUP_RETRY", "SETUP_ERROR", "NOT_LOADED"])
async def test_nonloaded_setup_outcome_preserves_created_entry(module, state_name):
    hass, entry, _runtime, options, user = environment(
        module, state=getattr(module.ConfigEntryState, state_name)
    )
    result = {"type": "create_entry", "result": entry}

    returned = await module.async_post_create_handoff(
        hass, result, {"source": "user", "user_id": user.id}
    )

    assert returned is result and "next_flow" not in result
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    assert options.init_calls == []


@pytest.mark.asyncio
async def test_runtime_drift_after_initialization_aborts_only_new_flow(module):
    hass, entry, runtime, options, user = environment(module)
    result = {"type": "create_entry", "result": entry}

    def drift(_flow_id):
        hass.data[DOMAIN]["entries"][entry.entry_id] = SimpleNamespace(engine=Engine())

    options.on_init = drift
    returned = await module.async_post_create_handoff(
        hass, result, {"source": "user", "user_id": user.id}
    )

    assert returned is result and "next_flow" not in result
    assert options.aborted == ["flow-1"]
    assert options.flows == {}
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    assert entry.runtime_data is runtime


@pytest.mark.asyncio
async def test_actor_epoch_change_during_initialization_cannot_rebase_handoff(module):
    hass, entry, runtime, options, user = environment(module)
    result = {"type": "create_entry", "result": entry}

    def rebind(_flow_id):
        runtime.engine.revision += 1

    options.on_init = rebind
    returned = await module.async_post_create_handoff(
        hass, result, {"source": "user", "user_id": user.id}
    )

    assert returned is result and "next_flow" not in result
    assert options.aborted == ["flow-1"] and options.flows == {}
    assert runtime.engine.revision == 2


@pytest.mark.asyncio
async def test_optional_exception_is_sanitized_and_cleans_new_flow(module, caplog):
    hass, entry, _runtime, options, user = environment(module)
    result = {"type": "create_entry", "result": entry}

    def fail(_flow_id):
        raise RuntimeError("SECRET-OPTION-CANARY")

    options.on_init = fail
    with caplog.at_level(logging.WARNING):
        returned = await module.async_post_create_handoff(
            hass, result, {"source": "user", "user_id": user.id}
        )

    assert returned is result and "next_flow" not in result
    assert options.aborted == ["flow-1"] and options.flows == {}
    assert "SECRET-OPTION-CANARY" not in caplog.text
    assert "Automatic guided onboarding handoff was skipped" in caplog.text


@pytest.mark.asyncio
async def test_missing_options_manager_is_optional_and_keeps_entry(module, caplog):
    hass, entry, _runtime, _options, user = environment(module)
    result = {"type": "create_entry", "result": entry}
    del hass.config_entries.options

    with caplog.at_level(logging.WARNING):
        returned = await module.async_post_create_handoff(
            hass, result, {"source": "user", "user_id": user.id}
        )

    assert returned is result and "next_flow" not in result
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    assert "Automatic guided onboarding handoff was skipped" in caplog.text


@pytest.mark.asyncio
async def test_cancellation_cleans_only_new_handoff_and_propagates(module):
    hass, entry, _runtime, options, user = environment(module)
    manual = options.add_flow(
        "other-entry", {"source": "user", "user_id": "another"}, None, step_id="init"
    )
    result = {"type": "create_entry", "result": entry}

    def cancel(_flow_id):
        raise asyncio.CancelledError

    options.on_init = cancel
    with pytest.raises(asyncio.CancelledError):
        await module.async_post_create_handoff(hass, result, {"source": "user", "user_id": user.id})

    assert options.aborted == ["flow-2"]
    assert list(options.flows) == [manual]
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    assert "next_flow" not in result


@pytest.mark.asyncio
async def test_exact_retry_reuses_one_marked_flow(module):
    hass, entry, _runtime, options, user = environment(module)
    existing = options.add_flow(
        entry.entry_id,
        {"source": "user", "user_id": user.id},
        {"guided_onboarding_handoff": True},
    )
    result = {"type": "create_entry", "result": entry}

    returned = await module.async_post_create_handoff(
        hass, result, {"source": "user", "user_id": user.id}
    )

    assert returned["next_flow"] == (module.FlowType.OPTIONS_FLOW, existing)
    assert options.init_calls == []
    assert list(options.flows) == [existing]


@pytest.mark.asyncio
async def test_two_concurrent_handoffs_share_one_runtime_scoped_flow(module):
    hass, entry, _runtime, options, user = environment(module)
    started = asyncio.Event()
    release = asyncio.Event()

    async def gate(_flow_id):
        started.set()
        await release.wait()

    options.on_init = gate
    first_result = {"type": "create_entry", "result": entry}
    second_result = {"type": "create_entry", "result": entry}
    first = asyncio.create_task(
        module.async_post_create_handoff(hass, first_result, {"source": "user", "user_id": user.id})
    )
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(
        module.async_post_create_handoff(
            hass, second_result, {"source": "user", "user_id": user.id}
        )
    )
    await asyncio.sleep(0)
    assert len(options.init_calls) == 1
    release.set()

    first_returned, second_returned = await asyncio.gather(first, second)

    assert first_returned["next_flow"] == second_returned["next_flow"]
    assert first_returned["next_flow"] == (module.FlowType.OPTIONS_FLOW, "flow-1")
    assert len(options.init_calls) == 1
    assert list(options.flows) == ["flow-1"]


@pytest.mark.asyncio
async def test_cancelled_concurrent_owner_cannot_abort_successor_flow(module):
    hass, entry, _runtime, options, user = environment(module)
    started = asyncio.Event()
    release = asyncio.Event()

    async def gate(_flow_id):
        started.set()
        await release.wait()

    options.on_init = gate
    first_result = {"type": "create_entry", "result": entry}
    second_result = {"type": "create_entry", "result": entry}
    first = asyncio.create_task(
        module.async_post_create_handoff(hass, first_result, {"source": "user", "user_id": user.id})
    )
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(
        module.async_post_create_handoff(
            hass, second_result, {"source": "user", "user_id": user.id}
        )
    )
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    second_returned = await asyncio.wait_for(second, 1)

    assert options.aborted == ["flow-1"]
    assert second_returned["next_flow"] == (module.FlowType.OPTIONS_FLOW, "flow-2")
    assert list(options.flows) == ["flow-2"]
    assert "next_flow" not in first_result


@pytest.mark.asyncio
async def test_runtime_replacement_cannot_reuse_flow_owned_by_old_attempt(module):
    hass, entry, _runtime, options, user = environment(module)
    started = asyncio.Event()
    release = asyncio.Event()

    async def gate(_flow_id):
        started.set()
        await release.wait()

    options.on_init = gate
    context = {"source": "user", "user_id": user.id}
    first_result = {"type": "create_entry", "result": entry}
    first = asyncio.create_task(module.async_post_create_handoff(hass, first_result, context))
    await asyncio.wait_for(started.wait(), 1)
    replacement = SimpleNamespace(engine=Engine())
    entry.runtime_data = replacement
    hass.data[DOMAIN]["entries"][entry.entry_id] = replacement
    second_result = {"type": "create_entry", "result": entry}
    second = asyncio.create_task(module.async_post_create_handoff(hass, second_result, context))
    await asyncio.sleep(0)
    assert not second.done()
    release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    assert "next_flow" not in first_result
    assert options.aborted == ["flow-1"]
    assert second_result["next_flow"] == (module.FlowType.OPTIONS_FLOW, "flow-2")
    assert list(options.flows) == ["flow-2"]


@pytest.mark.asyncio
async def test_unmarked_manual_flow_is_never_attached_or_aborted(module):
    hass, entry, _runtime, options, user = environment(module)
    manual = options.add_flow(
        entry.entry_id,
        {"source": "user", "user_id": user.id},
        None,
        step_id="init",
    )
    result = {"type": "create_entry", "result": entry}

    returned = await module.async_post_create_handoff(
        hass, result, {"source": "user", "user_id": user.id}
    )

    assert returned is result and "next_flow" not in result
    assert options.init_calls == [] and options.aborted == []
    assert list(options.flows) == [manual]


@pytest.mark.asyncio
async def test_entry_is_rechecked_after_ha_user_lookup_await(module):
    hass, entry, _runtime, options, user = environment(module)
    replacement = module.ConfigEntry()

    class ReplacingAuth:
        async def async_get_user(self, _user_id):
            hass.config_entries.entries[entry.entry_id] = replacement
            return user

    hass.auth = ReplacingAuth()
    result = {"type": "create_entry", "result": entry}

    returned = await module.async_post_create_handoff(
        hass, result, {"source": "user", "user_id": user.id}
    )

    assert returned is result and "next_flow" not in result
    assert options.init_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "wrong_source",
        "missing_user",
        "deleted_user",
        "inactive_user",
        "demoted_admin",
        "parent_role",
        "replaced_entry",
        "replaced_runtime",
        "existing_next_flow",
    ],
)
async def test_ineligible_context_or_current_scope_never_starts_flow(module, change):
    hass, entry, _runtime, options, user = environment(module)
    context = {"source": "user", "user_id": user.id}
    result = {"type": "create_entry", "result": entry}
    if change == "wrong_source":
        context["source"] = "import"
    elif change == "missing_user":
        context.pop("user_id")
    elif change == "deleted_user":

        async def deleted(_user_id):
            return None

        hass.auth.async_get_user = deleted
    elif change == "inactive_user":
        user.is_active = False
    elif change == "demoted_admin":
        user.is_admin = False
    elif change == "parent_role":
        entry.runtime_data.engine.role = "parent"
    elif change == "replaced_entry":
        hass.config_entries.entries[entry.entry_id] = module.ConfigEntry()
    elif change == "replaced_runtime":
        hass.data[DOMAIN]["entries"][entry.entry_id] = SimpleNamespace(engine=Engine())
    elif change == "existing_next_flow":
        result["next_flow"] = (module.FlowType.OPTIONS_FLOW, "already")

    returned = await module.async_post_create_handoff(hass, result, context)

    assert returned is result
    assert options.init_calls == [] and options.aborted == []
    if change != "existing_next_flow":
        assert "next_flow" not in result
