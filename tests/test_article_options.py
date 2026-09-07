"""Owner-reviewed and provider-bound article policy Options contract."""

import sys
from copy import deepcopy
from enum import Enum
from types import ModuleType, SimpleNamespace

import pytest
import voluptuous as vol

from custom_components.family_assistant.assistant.article_options import (
    options_step,
    review_step,
)
from custom_components.family_assistant.const import DOMAIN
from custom_components.family_assistant.domain.validation import DomainError


class ConfigEntryState(Enum):
    LOADED = "loaded"
    UNLOAD_IN_PROGRESS = "unload_in_progress"


@pytest.fixture(autouse=True)
def home_assistant_config_entries(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntryState = ConfigEntryState
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    translation = ModuleType("homeassistant.helpers.translation")

    async def async_get_translations(hass, language, category, integrations):
        assert language == "en" and category == "selector"
        assert integrations == {DOMAIN}
        flow = hass.flow
        if flow.after_translation:
            callback, flow.after_translation = flow.after_translation, None
            callback()
        prefix = "component.family_assistant.selector.article_policy_state.options."
        return {
            prefix + "enabled": "On",
            prefix + "disabled": "Off",
            prefix + "allowed": "Children allowed",
            prefix + "not_allowed": "Children not allowed",
        }

    translation.async_get_translations = async_get_translations
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.translation", translation)


def state():
    return {
        "settings": {"modules": ["conversation"]},
        "members": {
            "owner": {
                "id": "owner",
                "revision": 4,
                "active": True,
                "role": "owner",
                "ha_user_id": "ha-owner",
                "language": "en",
            }
        },
    }


def configured_options(**extra):
    return {
        "unrelated": {"keep": True},
        "conversation": {
            "enabled": True,
            "primary": {
                "url": "https://model.invalid",
                "model": "synthetic-model",
                "api_key": "opaque-provider-value",
            },
        },
        **extra,
    }


class Engine:
    def __init__(self):
        self.state = state()

    def snapshot(self):
        return deepcopy(self.state)


class Flow:
    def __init__(self, options=None):
        self.engine = Engine()
        self.runtime = SimpleNamespace(engine=self.engine, assistant=object())
        self.config_entry = SimpleNamespace(
            entry_id="entry",
            domain=DOMAIN,
            state=ConfigEntryState.LOADED,
            options=deepcopy(options if options is not None else configured_options()),
            runtime_data=self.runtime,
        )
        self.user = SimpleNamespace(id="ha-owner", is_admin=True, is_active=True)
        self.context = {"user_id": self.user.id}
        self.hass = SimpleNamespace(
            auth=SimpleNamespace(async_get_user=self._get_user),
            config_entries=SimpleNamespace(async_get_entry=lambda _id: self.config_entry),
        )
        self.hass.flow = self
        self.created = []
        self.abort_commit = None
        self.after_user_lookup = None
        self.after_translation = None

    async def _get_user(self, _user_id):
        if self.after_user_lookup:
            callback, self.after_user_lookup = self.after_user_lookup, None
            callback()
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
        if self.abort_commit:
            return {"type": "abort", "reason": self.abort_commit}
        self.created.append(deepcopy(data))
        self.config_entry.options = deepcopy(data)
        return {"type": "create_entry", "title": title, "data": deepcopy(data)}


async def begin(flow, values):
    form = await options_step(flow)
    assert form["step_id"] == "articles"
    return await options_step(flow, values)


@pytest.mark.asyncio
async def test_defaults_are_disabled_strict_booleans_and_no_private_settings_render():
    flow = Flow()
    form = await options_step(flow)
    assert form["data_schema"]({}) == {"enabled": False, "allow_children": False}
    for field in ("enabled", "allow_children"):
        with pytest.raises(vol.Invalid):
            form["data_schema"]({field: "false"})
    rendered = repr(form)
    assert "opaque-provider-value" not in rendered
    assert "model.invalid" not in rendered


@pytest.mark.asyncio
async def test_named_review_then_commit_preserves_options_and_adds_fresh_revision():
    flow = Flow()
    review = await begin(flow, {"enabled": True, "allow_children": True})
    assert review["step_id"] == "article_policy_review"
    assert review["description_placeholders"] == {
        "enabled": "On",
        "children": "Children allowed",
    }
    assert "opaque-provider-value" not in repr(review)
    assert "model.invalid" not in repr(review)
    assert "opaque-provider-value" not in repr(flow._article_policy_review)
    assert "model.invalid" not in repr(flow._article_policy_review)
    assert flow.created == []
    result = await review_step(flow, {"confirmed": True})
    assert result["type"] == "create_entry"
    assert result["data"]["unrelated"] == {"keep": True}
    assert result["data"]["conversation"] == configured_options()["conversation"]
    policy = result["data"]["articles"]
    assert policy["enabled"] is True and policy["allow_children"] is True
    assert len(policy["revision"]) == 32
    assert set(policy["revision"]) <= set("0123456789abcdef")


@pytest.mark.asyncio
async def test_cancel_returns_to_fresh_editor_without_write():
    flow = Flow()
    await begin(flow, {"enabled": True, "allow_children": False})
    result = await review_step(flow, {"confirmed": False})
    assert result["step_id"] == "articles"
    assert flow.created == [] and flow._article_policy_review is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"enabled": True},
        {"enabled": True, "allow_children": False, "extra": False},
        {"enabled": 1, "allow_children": False},
        {"enabled": True, "allow_children": "false"},
    ],
)
async def test_input_is_exact_and_strict(value):
    flow = Flow()
    await options_step(flow)
    result = await options_step(flow, value)
    if value is None:
        assert result["errors"] == {}
    else:
        assert result["errors"] == {"base": "invalid_field"}
    assert flow.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["module", "config", "runtime"])
async def test_enabling_requires_current_conversation_module_model_and_runtime(failure):
    flow = Flow()
    await options_step(flow)
    if failure == "module":
        flow.engine.state["settings"]["modules"] = []
    elif failure == "config":
        flow.config_entry.options["conversation"].pop("primary")
    else:
        flow.runtime.assistant = None
    result = await options_step(flow, {"enabled": True, "allow_children": False})
    # Every readiness change also invalidates the displayed source scope.
    assert result["errors"]["base"] in {"conflict", "provider_model_missing"}
    assert flow.created == []


@pytest.mark.asyncio
async def test_disabled_policy_is_available_without_provider_or_module():
    options = configured_options(
        articles={"enabled": True, "allow_children": True, "revision": "a" * 32}
    )
    flow = Flow(options)
    flow.runtime.assistant = None
    flow.engine.state["settings"]["modules"] = []
    review = await begin(flow, {"enabled": False, "allow_children": False})
    assert review["step_id"] == "article_policy_review"
    result = await review_step(flow, {"confirmed": True})
    assert result["data"]["articles"]["enabled"] is False
    assert result["data"]["articles"]["revision"] != "a" * 32


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["options", "provider", "assistant", "owner_revision", "owner_role", "admin", "entry"],
)
async def test_displayed_scope_drift_never_rebases_or_writes(change):
    flow = Flow()
    await options_step(flow)
    if change == "options":
        flow.config_entry.options["unrelated"] = {"keep": False}
    elif change == "provider":
        flow.config_entry.options["conversation"]["primary"]["model"] = "changed"
    elif change == "assistant":
        flow.runtime.assistant = object()
    elif change == "owner_revision":
        flow.engine.state["members"]["owner"]["revision"] += 1
    elif change == "owner_role":
        flow.engine.state["members"]["owner"]["role"] = "parent"
    elif change == "admin":
        flow.user.is_admin = False
    else:
        flow.hass.config_entries.async_get_entry = lambda _id: SimpleNamespace()
    result = await options_step(flow, {"enabled": True, "allow_children": False})
    if change in {"owner_role", "admin"}:
        assert result == {"type": "abort", "reason": "forbidden"}
    elif change == "entry":
        assert result == {"type": "abort", "reason": "conflict"}
    else:
        assert result["errors"] == {"base": "conflict"}
    assert flow.created == []


@pytest.mark.asyncio
async def test_review_rechecks_scope_and_never_renders_after_revocation():
    flow = Flow()
    await begin(flow, {"enabled": True, "allow_children": False})
    flow.user.is_active = False
    result = await review_step(flow)
    assert result == {"type": "abort", "reason": "forbidden"}
    assert flow._article_policy_review is None and flow.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unloading", "missing_runtime", "wrong_domain"])
async def test_entry_must_be_loaded_family_entry_with_exact_runtime_before_render(failure):
    flow = Flow()
    if failure == "unloading":
        flow.config_entry.state = ConfigEntryState.UNLOAD_IN_PROGRESS
    elif failure == "missing_runtime":
        del flow.config_entry.runtime_data
    else:
        flow.config_entry.domain = "other"
    result = await options_step(flow)
    assert result == {"type": "abort", "reason": "conflict"}
    assert flow.created == []


@pytest.mark.asyncio
async def test_entry_loading_state_or_runtime_change_during_user_lookup_conflicts():
    for mutation in (
        lambda flow: setattr(flow.config_entry, "state", ConfigEntryState.UNLOAD_IN_PROGRESS),
        lambda flow: setattr(flow.config_entry, "runtime_data", SimpleNamespace()),
    ):
        flow = Flow()
        flow.after_user_lookup = lambda flow=flow, mutation=mutation: mutation(flow)
        result = await options_step(flow)
        assert result == {"type": "abort", "reason": "conflict"}
        assert flow.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["member", "options", "assistant", "entry"])
async def test_review_localization_await_rechecks_complete_scope(change):
    flow = Flow()
    # Build the frozen review directly through the normal editor submission,
    # but arrange the change only for the subsequent localization await.
    await options_step(flow)
    if change == "member":
        flow.after_translation = lambda: flow.engine.state["members"]["owner"].update(revision=5)
    elif change == "options":
        flow.after_translation = lambda: flow.config_entry.options.update(newer=True)
    elif change == "assistant":
        flow.after_translation = lambda: setattr(flow.runtime, "assistant", object())
    else:
        flow.after_translation = lambda: setattr(
            flow.config_entry, "state", ConfigEntryState.UNLOAD_IN_PROGRESS
        )
    result = await options_step(flow, {"enabled": True, "allow_children": False})
    assert result == {"type": "abort", "reason": "conflict"}
    assert flow.created == []


@pytest.mark.asyncio
async def test_missing_selector_translation_fails_closed_without_raw_placeholder():
    flow = Flow()

    async def incomplete(*_args):
        return {}

    sys.modules["homeassistant.helpers.translation"].async_get_translations = incomplete
    await options_step(flow)
    result = await options_step(flow, {"enabled": True, "allow_children": False})
    assert result == {"type": "abort", "reason": "not_ready"}
    assert flow.created == []


@pytest.mark.asyncio
async def test_identity_is_rechecked_after_user_lookup_await():
    flow = Flow()
    flow.after_user_lookup = lambda: flow.engine.state["members"]["owner"].update(revision=5)
    result = await options_step(flow)
    assert result == {"type": "abort", "reason": "conflict"}


@pytest.mark.asyncio
async def test_concurrent_review_and_backup_abort_leave_original_options_unchanged():
    flow = Flow()
    original = deepcopy(flow.config_entry.options)
    await begin(flow, {"enabled": True, "allow_children": False})
    flow.config_entry.options["newer"] = True
    stale = await review_step(flow, {"confirmed": True})
    assert stale == {"type": "abort", "reason": "conflict"}
    assert flow.created == []

    flow = Flow(original)
    await begin(flow, {"enabled": True, "allow_children": False})
    flow.abort_commit = "backup_in_progress"
    blocked = await review_step(flow, {"confirmed": True})
    assert blocked == {"type": "abort", "reason": "backup_in_progress"}
    assert flow.config_entry.options == original and flow.created == []


@pytest.mark.asyncio
async def test_malformed_stored_policy_fails_closed_without_overwrite():
    flow = Flow(configured_options(articles={"enabled": False, "allow_children": False}))
    result = await options_step(flow)
    assert result == {"type": "abort", "reason": "invalid_field"}
    assert flow.created == []


@pytest.mark.asyncio
async def test_unchanged_selection_does_not_rotate_revision():
    options = configured_options(
        articles={"enabled": False, "allow_children": False, "revision": "b" * 32}
    )
    flow = Flow(options)
    result = await begin(flow, {"enabled": False, "allow_children": False})
    assert result["errors"] == {"base": "invalid_transition"}
    assert flow.config_entry.options == options and flow.created == []
