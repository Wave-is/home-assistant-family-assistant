"""Actual FamilyOptionsFlow delegates and Engine, using existing native contracts."""

import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest
import voluptuous as vol
from test_provider_options import config_flow, native  # noqa: F401

from custom_components.family_assistant.home_status import config, observations


@pytest.fixture
def flow_setup(native, monkeypatch):  # noqa: F811
    flow, entry, runtime, user = native
    selector = sys.modules["homeassistant.helpers.selector"]

    class Select:
        def __init__(self, configured):
            self.config = configured

        def __call__(self, value):
            choices = [
                item["value"] if isinstance(item, dict) else item for item in self.config["options"]
            ]
            values = value if self.config.get("multiple") else [value]
            if not isinstance(values, list) or any(item not in choices for item in values):
                raise vol.Invalid("selection")
            return value

    monkeypatch.setattr(selector, "SelectSelector", Select)
    monkeypatch.setattr(selector, "EntitySelectorConfig", dict, raising=False)
    monkeypatch.setattr(selector, "EntitySelector", lambda config: str, raising=False)
    monkeypatch.setattr(
        selector, "SelectSelectorMode", SimpleNamespace(DROPDOWN="dropdown"), raising=False
    )
    registry = {
        "sensor.synthetic_power": SimpleNamespace(
            entity_id="sensor.synthetic_power", id="synthetic-registry"
        )
    }
    allowed = set(registry)
    user.permissions = SimpleNamespace(check_entity=lambda entity, policy: entity in allowed)

    def access(_hass):
        return SimpleNamespace(async_get=registry.get), "read"

    monkeypatch.setattr(observations, "ha_access", access)
    sys.modules.pop("custom_components.family_assistant.home_status.options", None)
    from custom_components.family_assistant.home_status import options

    monkeypatch.setattr(options, "ha_access", access)
    yield flow, entry, runtime, user, registry, allowed
    sys.modules.pop("custom_components.family_assistant.home_status.options", None)


def source_input(**changes):
    return {
        "label": "Synthetic power",
        "entity_id": "sensor.synthetic_power",
        "mode": "energy:load_power",
        "roles": ["owner", "parent"],
        "active_states": [],
        "remove": False,
        **changes,
    }


async def source_editor(flow):
    selected = await flow.async_step_home_status_source({"record": "new"})
    assert selected["step_id"] == "home_status_source_edit", selected
    return selected


async def test_native_form_save_preserves_unrelated_options_and_never_reads_states(flow_setup):
    flow, entry, runtime, _, _, _ = flow_setup
    entry.options = {"conversation": {"providers": []}, "online_school": {"keep": True}}
    before = runtime.engine.snapshot()
    menu = await flow.async_step_home_status()
    assert menu["type"] == "menu" and "home_status_source" in menu["menu_options"]
    editor = await source_editor(flow)
    values = editor["data_schema"](source_input())
    reviewed = await flow.async_step_home_status_source_edit(values)
    assert reviewed["step_id"] == "home_status_review"
    result = await flow.async_step_home_status_review({"confirmed": True})
    assert result["type"] == "create_entry", result
    assert result["data"]["conversation"] == entry.options["conversation"]
    assert result["data"]["online_school"] == entry.options["online_school"]
    stored = config.from_options(result["data"])
    assert stored["revision"] == 1 and stored["sources"][0]["registry_id"] == "synthetic-registry"
    assert runtime.engine.snapshot() == before
    assert config.MODULE not in before["settings"]["modules"]


@pytest.mark.parametrize(
    "change", ["options", "role", "inactive_user", "registry", "acl", "backup", "runtime"]
)
async def test_review_revalidates_before_disclosing_or_saving(flow_setup, now, change):
    flow, entry, runtime, user, registry, allowed = flow_setup
    await source_editor(flow)
    assert (await flow.async_step_home_status_source_edit(source_input()))[
        "step_id"
    ] == "home_status_review"
    if change == "options":
        entry.options = {"unrelated": "newer"}
    elif change == "role":
        await runtime.engine.system_update(
            "revoke",
            now,
            lambda ctx: ctx.state["members"]["owner"].update(role="parent", revision=2),
        )
    elif change == "inactive_user":
        user.is_active = False
    elif change == "registry":
        registry["sensor.synthetic_power"].id = "replacement"
    elif change == "acl":
        allowed.clear()
    elif change == "backup":
        flow.hass.data["family_assistant"]["backup"] = object()
    else:
        entry.runtime_data = SimpleNamespace(engine=runtime.engine)
    result = await flow.async_step_home_status_review({"confirmed": True})
    assert result["type"] == "abort", result
    assert "description_placeholders" not in result and "data" not in result
    assert config.MODULE not in entry.options


async def test_group_create_move_source_and_explicit_remove(flow_setup):
    flow, entry, _, _, _, _ = flow_setup
    await flow.async_step_home_status_group({"record": "new"})
    review = await flow.async_step_home_status_group_edit(
        {"key": "synthetic_room", "title": "Synthetic group", "roles": ["owner"], "remove": False}
    )
    assert review["step_id"] == "home_status_review"
    saved = await flow.async_step_home_status_review({"confirmed": True})
    entry.options = saved["data"]
    group = entry.options[config.MODULE]["groups"][0]
    await source_editor(flow)
    await flow.async_step_home_status_source_edit(source_input(mode="group:" + group["id"]))
    saved = await flow.async_step_home_status_review({"confirmed": True})
    entry.options = saved["data"]
    await flow.async_step_home_status_group({"record": group["id"]})
    refused = await flow.async_step_home_status_group_edit(
        {"key": group["id"], "title": group["title"], "roles": group["roles"], "remove": True}
    )
    assert refused["errors"]["base"] == "home_status_group_in_use"
    item = entry.options[config.MODULE]["sources"][0]
    await flow.async_step_home_status_source({"record": item["id"]})
    await flow.async_step_home_status_source_edit(
        source_input(mode="group:" + group["id"], remove=True)
    )
    saved = await flow.async_step_home_status_review({"confirmed": True})
    assert saved["data"][config.MODULE]["sources"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "active:ignore", "active_states": ["on"]},
        {"mode": "active"},
        {"roles": ["guest"]},
        {"extra": "bad"},
        {"remove": 1},
    ],
)
async def test_malformed_direct_input_cannot_bypass_native_form_validation(flow_setup, changes):
    flow, entry, *_ = flow_setup
    await source_editor(flow)
    result = await flow.async_step_home_status_source_edit(source_input(**changes))
    assert result["errors"]["base"] == "invalid_field"
    assert entry.options == {}


async def test_cancel_and_stale_edit_do_not_write(flow_setup):
    flow, entry, *_ = flow_setup
    await source_editor(flow)
    await flow.async_step_home_status_source_edit(source_input())
    result = await flow.async_step_home_status_review({"confirmed": False})
    assert result["type"] == "menu" and entry.options == {}
    await source_editor(flow)
    entry.options = {"newer": True}
    result = await flow.async_step_home_status_source_edit(source_input())
    assert result == {"type": "abort", "reason": "conflict"}


@pytest.mark.parametrize("age", [True, 0, 29, 86401, "300"])
async def test_age_is_strict_native_and_server_side(flow_setup, age):
    flow, entry, *_ = flow_setup
    form = await flow.async_step_home_status_settings()
    with pytest.raises(vol.Invalid):
        form["data_schema"]({"max_age_seconds": age})
    result = await flow.async_step_home_status_settings({"max_age_seconds": age})
    assert result["errors"]["base"] == "invalid_field" and entry.options == {}


async def test_scope_rechecks_auth_await_and_keeps_options_frozen(flow_setup):
    flow, entry, _, user, *_ = flow_setup
    before = deepcopy(entry.options)

    async def changed(_id):
        entry.options = {"concurrent": True}
        return user

    flow.hass.auth.async_get_user = changed
    result = await flow.async_step_home_status_settings()
    assert result == {"type": "abort", "reason": "conflict"}
    assert before == {} and entry.options == {"concurrent": True}


async def test_age_editor_cannot_rebase_options_changed_while_form_was_open(flow_setup):
    flow, entry, *_ = flow_setup
    await flow.async_step_home_status_settings()
    entry.options = {"concurrent": True}
    result = await flow.async_step_home_status_settings({"max_age_seconds": 600})
    assert result == {"type": "abort", "reason": "conflict"}


async def test_default_and_existing_noops_preserve_exact_options_and_source_order(flow_setup):
    flow, entry, *_ = flow_setup
    entry.options = {"unrelated": {"exact": True}}
    await flow.async_step_home_status_settings()
    await flow.async_step_home_status_settings({"max_age_seconds": 300})
    result = await flow.async_step_home_status_review({"confirmed": True})
    assert result["data"] == entry.options
    await source_editor(flow)
    await flow.async_step_home_status_source_edit(source_input())
    entry.options = (await flow.async_step_home_status_review({"confirmed": True}))["data"]
    before = deepcopy(entry.options)
    item = entry.options[config.MODULE]["sources"][0]
    await flow.async_step_home_status_source({"record": item["id"]})
    await flow.async_step_home_status_source_edit(source_input())
    result = await flow.async_step_home_status_review({"confirmed": True})
    assert result["data"] == before
