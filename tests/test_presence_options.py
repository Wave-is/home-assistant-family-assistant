"""Owner-reviewed Options bindings against the real presence domain contract."""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import voluptuous as vol

from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.presence import sync_bindings
from custom_components.family_assistant.domain.validation import DomainError

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "family_assistant"
NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


class _Select:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        choices = {
            option["value"] if isinstance(option, dict) else option
            for option in self.config["options"]
        }
        if value not in choices:
            raise vol.Invalid("selection")
        return value


class _Entity:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        if not isinstance(value, str):
            raise vol.Invalid("entity")
        return value


@pytest.fixture
def module(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    helpers = ModuleType("homeassistant.helpers")
    selector = ModuleType("homeassistant.helpers.selector")
    selector.SelectSelectorConfig = lambda **kwargs: kwargs
    selector.SelectSelector = _Select
    selector.EntitySelectorConfig = lambda **kwargs: kwargs
    selector.EntitySelector = _Entity
    helpers.selector = selector
    permissions = ModuleType("homeassistant.auth.permissions.const")
    permissions.POLICY_READ = "read"
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = lambda hass: hass.registry
    util = ModuleType("homeassistant.util")
    dt_util = ModuleType("homeassistant.util.dt")
    dt_util.utcnow = lambda: NOW
    util.dt = dt_util
    homeassistant.helpers = helpers
    for name, value in {
        "homeassistant": homeassistant,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.selector": selector,
        "homeassistant.auth": ModuleType("homeassistant.auth"),
        "homeassistant.auth.permissions": ModuleType("homeassistant.auth.permissions"),
        "homeassistant.auth.permissions.const": permissions,
        "homeassistant.helpers.entity_registry": entity_registry,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_util,
    }.items():
        monkeypatch.setitem(sys.modules, name, value)
    name = "custom_components.family_assistant._presence_options_test"
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "presence_options.py")
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    assert spec.loader is not None
    spec.loader.exec_module(loaded)
    return loaded


def base_state():
    return {
        "settings": {"modules": ["presence"]},
        "members": {
            "owner": {
                "id": "owner",
                "name": "Owner",
                "role": "owner",
                "active": True,
                "revision": 1,
                "ha_user_id": "ha_owner",
            },
            "adult": {
                "id": "adult",
                "name": "Adult",
                "role": "adult",
                "active": True,
                "revision": 3,
                "ha_user_id": "ha_adult",
            },
            "child": {
                "id": "child",
                "name": "Child",
                "role": "child",
                "active": True,
                "revision": 4,
                "ha_user_id": "ha_child",
            },
        },
        "presence": {"bindings": {}, "subscriptions": {}},
        "outbox": {},
    }


class _Engine:
    def __init__(self, value, events):
        self.state = deepcopy(value)
        self.events = events
        self.fail_store = False
        self.before_update = None

    def snapshot(self):
        return deepcopy(self.state)

    async def system_update(self, kind, now, change):
        assert kind == "presence-bindings"
        assert now == NOW
        if self.before_update:
            self.before_update()
        working = deepcopy(self.state)
        result = change(Context(working, {"id": "system", "role": "system"}, now, kind))
        self.events.append("engine")
        if self.fail_store:
            raise OSError("private path must not escape")
        self.state = working
        return result


class _Permissions:
    def __init__(self, allowed):
        self.allowed = allowed

    def check_entity(self, entity_id, policy):
        assert policy == "read"
        return entity_id in self.allowed


class _Registry:
    def __init__(self, entities):
        self.entities = set(entities)

    def async_get(self, entity_id):
        return SimpleNamespace(entity_id=entity_id) if entity_id in self.entities else None


class _Flow:
    def __init__(self, value, *, options=None, entities=(), allowed=()):
        self.events = []
        self.engine = _Engine(value, self.events)
        self.runtime = SimpleNamespace(engine=self.engine)
        self.config_entry = SimpleNamespace(
            entry_id="entry_1",
            options=deepcopy(options or {}),
            runtime_data=self.runtime,
        )
        self.user = SimpleNamespace(id="ha_owner", permissions=_Permissions(set(allowed)))
        self.context = {"user_id": "ha_owner"}
        self.registry = _Registry(entities)
        self.fail_options = False
        self.hass = SimpleNamespace(
            auth=SimpleNamespace(async_get_user=self._get_user),
            registry=self.registry,
            config_entries=SimpleNamespace(async_get_entry=lambda _entry_id: self.config_entry),
        )

    async def _get_user(self, _user_id):
        return self.user

    def _authorized_runtime(self):
        member = self.engine.state["members"]["owner"]
        if member["active"] is not True or member["role"] != "owner":
            raise DomainError("forbidden")
        return self.runtime, "owner"

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}

    def async_create_entry(self, *, title, data):
        self.events.append("options")
        if self.fail_options:
            return {"type": "abort", "reason": "backup_in_progress"}
        self.config_entry.options = deepcopy(data)
        return {"type": "create_entry", "title": title, "data": deepcopy(data)}


def active_options(entity="person.adult", *, revision=1, member_revision=3, age=300):
    return {
        "unrelated": {"preserve": True},
        "presence_sources": {
            "adult": {
                "revision": revision,
                "status": "active",
                "member_revision": member_revision,
                "entity_id": entity,
            }
        },
        "presence_max_age_seconds": age,
    }


def sync_existing(flow):
    sync_bindings(
        Context(flow.engine.state, {"id": "system", "role": "system"}, NOW, "setup"),
        flow.config_entry.options,
    )


def edit(member="adult", *, enabled=True, entity="person.adult", age=300):
    return {
        "member": member,
        "enabled": enabled,
        "entity_id": entity,
        "presence_max_age_seconds": age,
    }


async def begin(module, flow, payload):
    first = await module.source_step(flow)
    assert first["type"] == "form" and first["step_id"] == "presence_sources"
    editor = await module.source_step(flow, {"member": payload["member"]})
    assert editor["type"] == "form" and editor["step_id"] == "presence_source_settings"
    return await module.source_settings_step(
        flow, {key: value for key, value in payload.items() if key != "member"}
    )


@pytest.mark.asyncio
async def test_form_uses_strict_age_and_current_plus_stale_bound_members(module):
    options = active_options()
    flow = _Flow(base_state(), options=options, entities={"person.adult"}, allowed={"person.adult"})
    sync_existing(flow)
    flow.engine.state["members"]["adult"]["active"] = False
    form = await module.source_step(flow)
    defaults = form["data_schema"]({})
    assert defaults["member"] == "owner"
    member_field = next(key for key in form["data_schema"].schema if key.schema == "member")
    member_values = {
        item["value"] for item in form["data_schema"].schema[member_field].config["options"]
    }
    assert member_values == {
        "owner",
        "child",
        "adult",
    }
    editor = await module.source_step(flow, {"member": "adult"})
    assert editor["step_id"] == "presence_source_settings"
    defaults = editor["data_schema"]({})
    assert defaults["entity_id"] == "person.adult" and defaults["enabled"] is True
    assert "member" not in defaults
    for invalid in (True, 29, 3601, 300.0, "300"):
        with pytest.raises(vol.Invalid):
            editor["data_schema"]({**defaults, "presence_max_age_seconds": invalid})


@pytest.mark.asyncio
async def test_new_binding_requires_review_then_syncs_engine_before_options(module):
    flow = _Flow(
        base_state(),
        entities={"device_tracker.adult_phone"},
        allowed={"device_tracker.adult_phone"},
    )
    review = await begin(module, flow, edit(entity="device_tracker.adult_phone", age=120))
    assert review["step_id"] == "presence_source_review"
    assert flow.events == [] and flow.config_entry.options == {}
    result = await module.review_step(flow, {"confirmed": True})
    assert result["type"] == "create_entry"
    assert flow.events == ["engine", "options"]
    source = result["data"]["presence_sources"]["adult"]
    assert source == {
        "revision": 1,
        "status": "active",
        "member_revision": 3,
        "entity_id": "device_tracker.adult_phone",
    }
    binding = flow.engine.state["presence"]["bindings"]["adult"]
    assert "entity_id" not in binding and "adult_phone" not in repr(binding)
    assert result["data"]["presence_max_age_seconds"] == 120


@pytest.mark.asyncio
async def test_review_cancel_returns_to_editor_without_writes(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await begin(module, flow, edit())
    result = await module.review_step(flow, {"confirmed": False})
    assert result["step_id"] == "presence_sources"
    assert flow.events == [] and flow._presence_review is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity", "registered", "allowed"),
    [
        ("sensor.adult", True, True),
        ("person.missing", False, True),
        ("person.denied", True, False),
    ],
)
async def test_wrong_domain_unregistered_or_ha_denied_source_never_reaches_review(
    module, entity, registered, allowed
):
    flow = _Flow(
        base_state(),
        entities={entity} if registered else set(),
        allowed={entity} if allowed else set(),
    )
    result = await begin(module, flow, edit(entity=entity))
    assert result["step_id"] == "presence_source_settings"
    assert result["errors"] == {"base": "forbidden"}
    assert flow.events == []


@pytest.mark.asyncio
async def test_owner_and_options_scope_are_rechecked_after_display(module):
    for drift in ("options", "owner_revision", "owner_role", "entry"):
        flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
        await module.source_step(flow)
        if drift == "options":
            flow.config_entry.options = {"unrelated": True}
        elif drift == "owner_revision":
            flow.engine.state["members"]["owner"]["revision"] += 1
        elif drift == "owner_role":
            flow.engine.state["members"]["owner"]["role"] = "parent"
        else:
            flow.hass.config_entries.async_get_entry = lambda _id: SimpleNamespace()
        result = await module.source_step(flow, {"member": "adult"})
        if drift in {"owner_role", "entry"}:
            assert result["type"] == "abort"
        else:
            assert result["errors"] == {"base": "conflict"}
        assert flow.events == []


@pytest.mark.asyncio
async def test_target_member_epoch_change_after_form_display_conflicts(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await module.source_step(flow)
    flow.engine.state["members"]["adult"]["revision"] += 1

    result = await module.source_step(flow, {"member": "adult"})
    assert result["type"] == "form"
    assert result["errors"] == {"base": "conflict"}
    assert flow.events == []
    assert flow.engine.state["presence"]["bindings"] == {}
    assert flow.config_entry.options == {}


@pytest.mark.asyncio
async def test_stale_member_binding_can_be_removed_and_tombstone_prevents_aba(module):
    options = active_options()
    flow = _Flow(base_state(), options=options, entities={"person.adult"}, allowed={"person.adult"})
    sync_existing(flow)
    flow.engine.state["members"]["adult"]["revision"] = 4
    review = await begin(module, flow, edit(enabled=False, entity="", age=450))
    assert review["description_placeholders"]["binding_revision"] == "2"
    result = await module.review_step(flow, {"confirmed": True})
    assert result["type"] == "create_entry"
    assert result["data"]["presence_sources"]["adult"] == {
        "revision": 2,
        "status": "removed",
        "member_revision": 3,
    }
    assert flow.engine.state["presence"]["bindings"]["adult"] == {
        "member": "adult",
        "revision": 2,
        "status": "removed",
        "member_revision": 3,
    }

    readd = await begin(module, flow, edit(entity="person.adult"))
    assert readd["description_placeholders"]["binding_revision"] == "3"


@pytest.mark.asyncio
async def test_unrelated_unchanged_stale_source_does_not_block_explicit_removal(module):
    options = active_options()
    options["presence_sources"]["child"] = {
        "revision": 1,
        "status": "active",
        "member_revision": 4,
        "entity_id": "person.child",
    }
    flow = _Flow(base_state(), options=options)
    sync_existing(flow)
    flow.engine.state["members"]["adult"]["revision"] = 4
    flow.engine.state["members"]["child"]["revision"] = 5

    await begin(module, flow, edit(enabled=False, entity=""))
    result = await module.review_step(flow, {"confirmed": True})
    assert result["type"] == "create_entry"
    assert result["data"]["presence_sources"]["adult"]["status"] == "removed"
    assert result["data"]["presence_sources"]["child"] == options["presence_sources"]["child"]
    assert flow.engine.state["presence"]["bindings"]["child"] == {
        "member": "child",
        "revision": 1,
        "status": "active",
        "member_revision": 4,
        "source_hash": module._hash("person.child"),
    }


@pytest.mark.asyncio
async def test_replacing_stale_member_binding_pins_current_member_epoch(module):
    options = active_options()
    flow = _Flow(
        base_state(),
        options=options,
        entities={"person.replacement"},
        allowed={"person.replacement"},
    )
    sync_existing(flow)
    flow.engine.state["members"]["adult"]["revision"] = 4
    review = await begin(module, flow, edit(entity="person.replacement"))
    summary = review["description_placeholders"]
    assert summary["binding_revision"] == "2" and summary["member_revision"] == "4"
    result = await module.review_step(flow, {"confirmed": True})
    assert result["data"]["presence_sources"]["adult"]["member_revision"] == 4


@pytest.mark.asyncio
async def test_concurrent_options_form_conflicts_without_second_engine_write(module):
    options = active_options()
    first = _Flow(
        base_state(),
        options=options,
        entities={"person.one"},
        allowed={"person.one"},
    )
    second = _Flow(
        base_state(),
        options=options,
        entities={"person.two"},
        allowed={"person.two"},
    )
    sync_existing(first)
    second.engine = first.engine
    second.runtime.engine = first.engine
    second.config_entry.runtime_data = second.runtime
    await begin(module, first, edit(entity="person.one"))
    await begin(module, second, edit(entity="person.two"))
    accepted = await module.review_step(first, {"confirmed": True})
    second.config_entry.options = deepcopy(accepted["data"])
    rejected = await module.review_step(second, {"confirmed": True})
    assert rejected == {"type": "abort", "reason": "conflict"}
    assert first.engine.events.count("engine") == 1


@pytest.mark.asyncio
async def test_store_failure_retains_frozen_review_and_retry_is_exact(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await begin(module, flow, edit())
    frozen = deepcopy(flow._presence_review["options"])
    flow.engine.fail_store = True
    failed = await module.review_step(flow, {"confirmed": True})
    assert failed["errors"] == {"base": "storage_error"}
    assert flow.config_entry.options == {}
    assert flow.engine.state["presence"]["bindings"] == {}
    assert flow._presence_review["options"] == frozen
    flow.engine.fail_store = False
    accepted = await module.review_step(flow, {"confirmed": True})
    assert accepted["data"] == frozen


@pytest.mark.asyncio
async def test_options_commit_failure_leaves_inert_pin_and_exact_retry_recovers(module):
    old = active_options()
    flow = _Flow(
        base_state(),
        options=old,
        entities={"device_tracker.new"},
        allowed={"device_tracker.new"},
    )
    sync_existing(flow)
    await begin(module, flow, edit(entity="device_tracker.new"))
    frozen = deepcopy(flow._presence_review["options"])
    flow.fail_options = True
    failed = await module.review_step(flow, {"confirmed": True})
    assert failed == {"type": "abort", "reason": "backup_in_progress"}
    assert flow.config_entry.options == old
    assert flow.engine.state["presence"]["bindings"]["adult"]["revision"] == 2
    flow.fail_options = False
    accepted = await module.review_step(flow, {"confirmed": True})
    assert accepted["data"] == frozen
    assert flow.events == ["engine", "options", "engine", "options"]


@pytest.mark.asyncio
async def test_new_flow_recovers_exact_pin_after_prior_options_commit_loss(module):
    old = active_options()
    flow = _Flow(
        base_state(),
        options=old,
        entities={"device_tracker.new"},
        allowed={"device_tracker.new"},
    )
    sync_existing(flow)
    await begin(module, flow, edit(entity="device_tracker.new"))
    proposed = deepcopy(flow._presence_review["options"])
    await flow.engine.system_update(
        "presence-bindings",
        NOW,
        lambda ctx: sync_bindings(ctx, proposed),
    )
    recovered = _Flow(
        flow.engine.state,
        options=old,
        entities={"device_tracker.new"},
        allowed={"device_tracker.new"},
    )
    review = await begin(module, recovered, edit(entity="device_tracker.new"))
    assert review["description_placeholders"]["binding_revision"] == "2"
    result = await module.review_step(recovered, {"confirmed": True})
    assert result["data"] == proposed


@pytest.mark.asyncio
async def test_deliberate_change_advances_a_newer_store_pin_instead_of_reverting_it(module):
    old = active_options()
    flow = _Flow(
        base_state(),
        options=old,
        entities={"device_tracker.committed", "person.replacement"},
        allowed={"device_tracker.committed", "person.replacement"},
    )
    sync_existing(flow)
    committed = deepcopy(old)
    committed["presence_sources"]["adult"] = {
        "revision": 2,
        "status": "active",
        "member_revision": 3,
        "entity_id": "device_tracker.committed",
    }
    await flow.engine.system_update(
        "presence-bindings",
        NOW,
        lambda ctx: sync_bindings(ctx, committed),
    )

    review = await begin(module, flow, edit(entity="person.replacement"))
    assert review["description_placeholders"]["binding_revision"] == "3"
    result = await module.review_step(flow, {"confirmed": True})
    assert result["data"]["presence_sources"]["adult"] == {
        "revision": 3,
        "status": "active",
        "member_revision": 3,
        "entity_id": "person.replacement",
    }


@pytest.mark.asyncio
async def test_permission_is_rechecked_after_review_and_after_engine_await(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await begin(module, flow, edit())
    flow.user.permissions.allowed.clear()
    denied = await module.review_step(flow, {"confirmed": True})
    assert denied == {"type": "abort", "reason": "forbidden"}
    assert flow.events == []

    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await begin(module, flow, edit())
    flow.engine.before_update = flow.user.permissions.allowed.clear
    denied = await module.review_step(flow, {"confirmed": True})
    assert denied == {"type": "abort", "reason": "forbidden"}
    assert flow.engine.state["presence"]["bindings"] == {}
    assert flow.config_entry.options == {}


@pytest.mark.asyncio
async def test_review_never_renders_private_source_after_owner_revocation(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    review = await begin(module, flow, edit())
    assert review["description_placeholders"]["entity"] == "person.adult"
    flow.engine.state["members"]["owner"]["role"] = "parent"

    denied = await module.review_step(flow)
    assert denied == {"type": "abort", "reason": "forbidden"}
    assert flow._presence_review is None


@pytest.mark.asyncio
async def test_actor_epoch_is_rechecked_inside_engine_transaction(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await begin(module, flow, edit())

    def advance_owner_epoch():
        flow.engine.state["members"]["owner"]["revision"] += 1

    flow.engine.before_update = advance_owner_epoch
    denied = await module.review_step(flow, {"confirmed": True})
    assert denied == {"type": "abort", "reason": "conflict"}
    assert flow.engine.state["presence"]["bindings"] == {}
    assert flow.config_entry.options == {}


@pytest.mark.asyncio
async def test_target_epoch_is_rechecked_at_review_and_transaction_boundaries(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await begin(module, flow, edit())
    flow.engine.state["members"]["adult"]["revision"] += 1
    denied = await module.review_step(flow)
    assert denied == {"type": "abort", "reason": "conflict"}
    assert flow.events == []

    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await begin(module, flow, edit())

    def advance_target_epoch():
        flow.engine.state["members"]["adult"]["revision"] += 1

    flow.engine.before_update = advance_target_epoch
    denied = await module.review_step(flow, {"confirmed": True})
    assert denied == {"type": "abort", "reason": "conflict"}
    assert flow.engine.state["presence"]["bindings"] == {}
    assert flow.config_entry.options == {}


@pytest.mark.asyncio
async def test_age_only_edit_preserves_binding_revision_and_unrelated_options(module):
    options = active_options(age=300)
    flow = _Flow(base_state(), options=options, entities={"person.adult"}, allowed={"person.adult"})
    sync_existing(flow)
    review = await begin(module, flow, edit(age=600))
    assert review["description_placeholders"]["binding_revision"] == "1"
    result = await module.review_step(flow, {"confirmed": True})
    assert result["data"]["presence_sources"] == options["presence_sources"]
    assert result["data"]["unrelated"] == {"preserve": True}
    assert result["data"]["presence_max_age_seconds"] == 600


@pytest.mark.asyncio
async def test_member_picker_hydrates_only_selected_saved_source_without_writes(module):
    options = active_options(age=450)
    options["presence_sources"]["owner"] = {
        "revision": 1,
        "status": "active",
        "member_revision": 1,
        "entity_id": "person.owner",
    }
    flow = _Flow(base_state(), options=options)
    for member, entity, enabled in (
        ("adult", "person.adult", True),
        ("owner", "person.owner", True),
        ("child", "", False),
    ):
        picker = await module.source_step(flow)
        assert set(picker["data_schema"]({})) == {"member"}
        assert "person." not in repr(picker)
        editor = await module.source_step(flow, {"member": member})
        assert editor["description_placeholders"] == {"member": member.title()}
        assert {"entity_id": "", **editor["data_schema"]({})} == {
            "enabled": enabled,
            "entity_id": entity,
            "presence_max_age_seconds": 450,
        }
        assert flow.events == [] and flow.config_entry.options == options


@pytest.mark.asyncio
async def test_editor_rejects_member_swap_and_old_combined_picker_payload(module):
    flow = _Flow(base_state(), entities={"person.adult"}, allowed={"person.adult"})
    await module.source_step(flow)
    rejected = await module.source_step(flow, edit())
    assert rejected["errors"] == {"base": "invalid_field"}
    assert flow._presence_editor is None
    await module.source_step(flow, {"member": "adult"})
    rejected = await module.source_settings_step(flow, edit("child"))
    assert rejected["errors"] == {"base": "invalid_field"}
    assert flow._presence_editor["member"] == "adult"
    assert flow._presence_review is None and not flow.events


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["options", "owner_epoch", "member_epoch", "owner_role"])
async def test_editor_rechecks_pinned_scope_before_rendering_or_review(module, drift):
    options = active_options()
    flow = _Flow(base_state(), options=options)
    await module.source_step(flow)
    await module.source_step(flow, {"member": "adult"})
    if drift == "options":
        flow.config_entry.options["unrelated"] = False
    elif drift == "owner_epoch":
        flow.engine.state["members"]["owner"]["revision"] += 1
    elif drift == "member_epoch":
        flow.engine.state["members"]["adult"]["revision"] += 1
    else:
        flow.engine.state["members"]["owner"]["role"] = "parent"
    result = await module.source_settings_step(flow)
    assert result == {
        "type": "abort",
        "reason": "forbidden" if drift == "owner_role" else "conflict",
    }
    assert "person.adult" not in repr(result)
    assert flow._presence_editor is None and not flow.events


@pytest.mark.asyncio
async def test_removal_can_omit_entity_and_affects_only_selected_member(module):
    options = active_options()
    options["presence_sources"]["child"] = {
        "revision": 1,
        "status": "active",
        "member_revision": 4,
        "entity_id": "person.child",
    }
    flow = _Flow(base_state(), options=options)
    sync_existing(flow)
    await module.source_step(flow)
    await module.source_step(flow, {"member": "adult"})
    review = await module.source_settings_step(
        flow, {"enabled": False, "presence_max_age_seconds": 300}
    )
    assert review["step_id"] == "presence_source_review"
    result = await module.review_step(flow, {"confirmed": True})
    assert result["data"]["presence_sources"]["adult"]["status"] == "removed"
    assert result["data"]["presence_sources"]["child"] == options["presence_sources"]["child"]


@pytest.mark.asyncio
async def test_editor_without_member_selection_returns_safe_picker(module):
    flow = _Flow(base_state(), options=active_options())
    result = await module.source_settings_step(flow, {"enabled": False})
    assert result["step_id"] == "presence_sources"
    assert set(result["data_schema"]({})) == {"member"}
    assert not flow.events


@pytest.mark.asyncio
@pytest.mark.parametrize("consent", [True, False])
async def test_native_projection_spy_excludes_timer_but_tracks_real_authorized_reads(
    engine, now, monkeypatch, consent
):
    import asyncio

    from ha_presence_smoke import _projection_reads, _state_reads
    from test_presence_observations import ReportedState, configured, harness

    from custom_components.family_assistant import presence_observations

    configured_engine, options = configured(engine, now, ("parent",))
    hass, entry, runtime, user, _ = harness(
        monkeypatch,
        configured_engine,
        options,
        {"person.parent": ReportedState("home", now)},
        {"person.parent"},
    )
    if not consent:
        await configured_engine.execute(
            "parent",
            "presence.access_set",
            {
                "member": "parent",
                "member_revision": 1,
                "binding_revision": 1,
                "subscription_revision": 1,
                "enabled": False,
            },
            "revoke-for-read-audit",
            now,
        )
    unrelated = "sensor.synthetic_unrelated_timer"
    with _state_reads(hass) as all_reads, _projection_reads(hass) as reads:
        asyncio.get_running_loop().call_soon(hass.states.get, unrelated)
        await asyncio.sleep(0)
        result = presence_observations.project(hass, entry, runtime, "parent", user, now)
    expected = ["person.parent"] if consent else []
    assert all_reads == [unrelated, *expected]
    assert reads == expected
    assert result["self"]["enabled"] is consent
    assert result["self"]["status"] == ("reported_home" if consent else "unknown")
