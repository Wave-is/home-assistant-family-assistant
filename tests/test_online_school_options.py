"""Native school Options contracts with real domain authority and fictional discovery.

HA form/selector objects and network discovery are adapters here, not real-HA
acceptance. Native FamilyOptionsFlow and online_school/options.py are loaded from
the actual source; no invented configuration or provider interface is exercised.
"""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import voluptuous as vol
from test_school_reminder_options import config_flow as config_flow

from custom_components.family_assistant.const import DOMAIN
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError

PASSWORD = "SYNTHETIC-SCHOOL-PASSWORD"
OTHER_SECRET = "SYNTHETIC-OTHER-PROVIDER-SECRET"
SOURCE = "OSsynthetic"


class Select:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        choices = {
            item["value"] if isinstance(item, dict) else item for item in self.config["options"]
        }
        values = value if self.config.get("multiple") else [value]
        if not isinstance(values, list) or any(item not in choices for item in values):
            raise vol.Invalid("selection")
        return value


class Text:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        if not isinstance(value, str):
            raise vol.Invalid("text")
        return value


@pytest.fixture
def harness(config_flow, engine, store, monkeypatch):
    selector = sys.modules["homeassistant.helpers.selector"]
    monkeypatch.setattr(selector, "SelectSelector", Select)
    monkeypatch.setattr(selector, "TextSelector", Text, raising=False)
    monkeypatch.setattr(selector, "TextSelectorConfig", lambda **values: values, raising=False)
    monkeypatch.setattr(
        selector, "TextSelectorType", SimpleNamespace(PASSWORD="password"), raising=False
    )
    name = "custom_components.family_assistant.online_school.options"
    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components/family_assistant/online_school/options.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)

    state = engine.snapshot()
    state["settings"]["modules"].append("school")
    runtime = SimpleNamespace(engine=Engine(state, store.save))
    entry = SimpleNamespace(entry_id="synthetic-school-entry", domain=DOMAIN, options=options())
    flow = config_flow.FamilyOptionsFlow()
    flow.config_entry = entry
    flow.context = {"user_id": "synthetic-owner"}
    flow.hass = SimpleNamespace(
        data={DOMAIN: {"entries": {entry.entry_id: runtime}}},
        config_entries=SimpleNamespace(async_get_entry=lambda entry_id: entry),
    )
    runtime_module = ModuleType("custom_components.family_assistant.runtime")

    def get_runtime(hass, entry_id):
        current = hass.config_entries.async_get_entry(entry_id)
        found = hass.data[DOMAIN]["entries"].get(entry_id)
        if current is None or current.domain != DOMAIN or found is None:
            raise DomainError("not_ready")
        return found

    runtime_module.get_runtime = get_runtime
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    result = SimpleNamespace(
        flow=flow,
        runtime=runtime,
        entry=entry,
        module=module,
        clients=[],
        on_discover=None,
        on_close=None,
        discovery_error=None,
        students=[{"id": "101", "name": "Example Student"}],
    )
    actual_client = module.RespublikaClient

    class Client(actual_client):
        def __init__(self, url, username, password):
            # Keep the actual URL/credential validator; its constructor does no I/O.
            super().__init__(url, username, password)
            self.arguments = (url, username, password)
            self.closed = False
            result.clients.append(self)

        async def discover(self):
            if result.on_discover:
                result.on_discover()
            if result.discovery_error:
                raise DomainError(result.discovery_error)
            return deepcopy(result.students)

        async def close(self):
            self.closed = True
            if result.on_close:
                result.on_close()
            await super().close()

    monkeypatch.setattr(module, "RespublikaClient", Client)

    def change_state(change):
        updated = runtime.engine.snapshot()
        change(updated)
        runtime.engine = Engine(updated, store.save)

    result.change_state = change_state
    return result


def options():
    return {
        "unrelated": {"keep": True, "api_key": OTHER_SECRET},
        "online_school": {
            "revision": 4,
            "sources": {
                SOURCE: {
                    "id": SOURCE,
                    "provider": "respublika",
                    "enabled": True,
                    "url": "https://example.respublika.school",
                    "username": "synthetic-parent",
                    "password": PASSWORD,
                    "label": "Example school",
                    "member": "child",
                    "member_revision": 1,
                    "student_id": "101",
                    "timezone": "UTC",
                    "generation": "original-generation",
                    "rules": {"enabled": False, "recipients": [], "homework_time": "18:00"},
                }
            },
        },
    }


def account_values(**changes):
    return {
        "enabled": True,
        "url": "https://example.respublika.school",
        "username": "synthetic-parent",
        "password": "",
        "label": "Example school",
        "member": "child",
        **changes,
    }


def student_values(**changes):
    return {"student_id": "101", "notifications": False, "recipients": [], **changes}


async def begin(harness, source=SOURCE):
    flow = harness.flow
    selection = await flow.async_step_online_school()
    assert selection["step_id"] == "online_school"
    result = await flow.async_step_online_school({"source": source})
    assert result["step_id"] == "online_school_account"
    return result


def visible_form(form):
    visible = {key: value for key, value in form.items() if key != "data_schema"}
    for marker, validator in form.get("data_schema", vol.Schema({})).schema.items():
        visible[str(marker)] = {
            "default": None if marker.default is vol.UNDEFINED else marker.default(),
            "selector": getattr(validator, "config", None),
        }
    return json.dumps(visible, sort_keys=True)


async def test_native_routes_show_three_steps_and_commit_only_after_student_choice(harness):
    before = deepcopy(harness.entry.options)
    account = await begin(harness)
    assert "password" not in account["data_schema"]({})
    student = await harness.flow.async_step_online_school_account(account_values())
    assert student["step_id"] == "online_school_student"
    assert harness.entry.options == before
    assert harness.clients[0].arguments[2] == PASSWORD
    assert harness.clients[0].closed
    result = await harness.flow.async_step_online_school_student(student_values())
    assert result["type"] == "create_entry"
    assert result["data"]["unrelated"] == before["unrelated"]
    updated = result["data"]["online_school"]
    assert updated["revision"] == 5
    source = updated["sources"][SOURCE]
    assert source["password"] == PASSWORD
    assert source["member"] == "child" and source["student_id"] == "101"
    assert source["member_revision"] == 1
    assert source["generation"] != "original-generation"
    assert source["rules"] == {
        "enabled": False,
        "notify_changes": False,
        "homework_time": "18:00",
        "recipients": [],
    }
    assert harness.flow._school_pending is None
    assert harness.entry.options == before  # Fake HA returns data, it does not commit it.


async def test_password_has_no_default_and_no_other_connection_secret_is_rendered(harness):
    selection = await harness.flow.async_step_online_school()
    account = await harness.flow.async_step_online_school({"source": SOURCE})
    marker, validator = next(
        (key, value)
        for key, value in account["data_schema"].schema.items()
        if str(key) == "password"
    )
    assert marker.default is vol.UNDEFINED
    assert validator.config["type"] == "password"
    student = await harness.flow.async_step_online_school_account(account_values())
    for form in (selection, account, student):
        visible = visible_form(form)
        assert PASSWORD not in visible and OTHER_SECRET not in visible
        assert "original-generation" not in visible


@pytest.mark.parametrize("user", ["synthetic-parent", "synthetic-child", "unknown-user"])
async def test_current_owner_required_before_any_account_details_or_discovery(harness, user):
    harness.flow.context["user_id"] = user
    result = await harness.flow.async_step_online_school()
    assert result["type"] == "abort"
    assert result["reason"] in {"forbidden", "unknown_actor"}
    assert harness.clients == []
    assert PASSWORD not in visible_form(result)


@pytest.mark.parametrize("when", ["discover", "close"])
@pytest.mark.parametrize("change", ["owner", "child", "options", "module", "backup"])
async def test_authority_and_options_are_rechecked_after_every_network_await(harness, when, change):
    await begin(harness)

    def mutate():
        if change == "owner":
            harness.change_state(lambda state: state["members"]["owner"].update(role="parent"))
        elif change == "child":
            harness.change_state(lambda state: state["members"]["child"].update(active=False))
        elif change == "options":
            harness.entry.options["unrelated"]["keep"] = False
        elif change == "module":
            harness.change_state(lambda state: state["settings"]["modules"].remove("school"))
        else:
            harness.flow.hass.data[DOMAIN]["backup"] = object()

    setattr(harness, "on_" + when, mutate)
    result = await harness.flow.async_step_online_school_account(account_values())
    assert result["type"] == "abort"
    assert result["reason"] in {"forbidden", "conflict", "module_disabled", "backup_in_progress"}
    assert harness.flow._school_pending is None
    assert harness.clients[0].closed
    assert PASSWORD not in visible_form(result)
    assert harness.entry.options["online_school"]["revision"] == 4


@pytest.mark.parametrize("field", ["url", "username"])
async def test_blank_password_cannot_be_reused_at_a_different_account_scope(harness, field):
    await begin(harness)
    value = "https://other.respublika.school" if field == "url" else "different-parent"
    result = await harness.flow.async_step_online_school_account(account_values(**{field: value}))
    assert result["errors"] == {"base": "provider_key_scope"}
    assert harness.clients == []
    assert PASSWORD not in visible_form(result)


async def test_explicit_new_password_can_replace_credentials_after_student_review(harness):
    await begin(harness)
    result = await harness.flow.async_step_online_school_account(
        account_values(username="different-parent", password="NEW-SYNTHETIC-PASSWORD")
    )
    assert result["step_id"] == "online_school_student"
    assert "NEW-SYNTHETIC-PASSWORD" not in visible_form(result)
    result = await harness.flow.async_step_online_school_student(student_values())
    assert result["data"]["online_school"]["sources"][SOURCE]["password"] == (
        "NEW-SYNTHETIC-PASSWORD"
    )


async def test_disabling_preserves_exact_saved_account_without_contacting_provider(harness):
    before = deepcopy(harness.entry.options)
    await begin(harness)
    result = await harness.flow.async_step_online_school_account({"enabled": False})
    assert result["type"] == "create_entry"
    old = before["online_school"]["sources"][SOURCE]
    updated = result["data"]["online_school"]["sources"][SOURCE]
    assert {
        key: value for key, value in updated.items() if key not in {"generation", "enabled"}
    } == {key: value for key, value in old.items() if key not in {"generation", "enabled"}}
    assert updated["enabled"] is False and updated["generation"] != old["generation"]
    assert harness.clients == []


async def test_unrelated_options_change_before_final_review_cannot_be_overwritten(harness):
    await begin(harness)
    await harness.flow.async_step_online_school_account(account_values())
    harness.entry.options["new_other_provider"] = {"enabled": True}
    before = deepcopy(harness.entry.options)
    result = await harness.flow.async_step_online_school_student(student_values())
    assert result == {"type": "abort", "reason": "conflict"}
    assert harness.entry.options == before
    assert harness.flow._school_pending is None


@pytest.mark.parametrize("change", ["inactive", "role", "revision"])
async def test_child_revocation_or_rebinding_before_final_choice_requires_fresh_discovery(
    harness, change
):
    await begin(harness)
    await harness.flow.async_step_online_school_account(account_values())
    updates = {
        "inactive": {"active": False},
        "role": {"role": "adult"},
        "revision": {"revision": 2},
    }
    harness.change_state(lambda state: state["members"]["child"].update(updates[change]))
    result = await harness.flow.async_step_online_school_student(student_values())
    assert result == {"type": "abort", "reason": "conflict"}
    assert harness.flow._school_pending is None


@pytest.mark.parametrize("recipient", ["sibling", "adult", "guest", "missing"])
async def test_notifications_cannot_target_other_children_or_ineligible_members(harness, recipient):
    await begin(harness)
    form = await harness.flow.async_step_online_school_account(account_values())
    selector = next(
        value for key, value in form["data_schema"].schema.items() if str(key) == "recipients"
    )
    assert {item["value"] for item in selector.config["options"]} == {"owner", "parent", "child"}
    result = await harness.flow.async_step_online_school_student(
        student_values(notifications=True, recipients=[recipient])
    )
    assert result == {"type": "abort", "reason": "invalid_field"}


@pytest.mark.parametrize("error", ["online_school_auth_failed", "online_school_timeout"])
async def test_discovery_failure_closes_client_and_renders_only_a_stable_error(harness, error):
    await begin(harness)
    harness.discovery_error = error
    result = await harness.flow.async_step_online_school_account(account_values())
    assert result["errors"] == {"base": error}
    assert harness.clients[0].closed
    assert PASSWORD not in visible_form(result)


async def test_only_explicitly_discovered_student_can_be_selected(harness):
    await begin(harness, "new")
    await harness.flow.async_step_online_school_account(account_values(password=PASSWORD))
    result = await harness.flow.async_step_online_school_student(student_values(student_id="999"))
    assert result == {"type": "abort", "reason": "invalid_field"}
    assert harness.entry.options["online_school"]["revision"] == 4


async def test_missing_module_blocks_onboarding_before_provider_access(harness):
    harness.change_state(lambda state: state["settings"]["modules"].remove("school"))
    result = await harness.flow.async_step_online_school()
    assert result == {"type": "abort", "reason": "module_disabled"}
    assert harness.clients == []
