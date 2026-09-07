"""Generation-bound Repairs flow for a failed backup unwind."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


class _HomeAssistantError(Exception):
    pass


class _UnknownStep(Exception):
    pass


class _RepairsFlow:
    hass = None

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


@pytest.fixture
def recovery(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    data_entry_flow = ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.UnknownStep = _UnknownStep
    homeassistant.data_entry_flow = data_entry_flow
    components = ModuleType("homeassistant.components")
    repairs_component = ModuleType("homeassistant.components.repairs")
    repairs_component.RepairsFlow = _RepairsFlow
    repairs_component.RepairsFlowResult = dict
    components.repairs = repairs_component
    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = _HomeAssistantError
    helpers = ModuleType("homeassistant.helpers")
    issue_registry = ModuleType("homeassistant.helpers.issue_registry")
    issues = {}

    class IssueSeverity:
        ERROR = "error"

    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.async_create_issue = lambda _hass, domain, issue_id, **kwargs: (
        issues.__setitem__((domain, issue_id), kwargs)
    )
    issue_registry.async_delete_issue = lambda _hass, domain, issue_id: issues.pop(
        (domain, issue_id), None
    )
    helpers.issue_registry = issue_registry
    modules = {
        "homeassistant": homeassistant,
        "homeassistant.data_entry_flow": data_entry_flow,
        "homeassistant.components": components,
        "homeassistant.components.repairs": repairs_component,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.issue_registry": issue_registry,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name in (
        "custom_components.family_assistant.backup",
        "custom_components.family_assistant.backup_recovery",
        "custom_components.family_assistant.repairs",
    ):
        sys.modules.pop(name, None)
    backup = importlib.import_module("custom_components.family_assistant.backup")
    repairs = importlib.import_module("custom_components.family_assistant.repairs")
    yield SimpleNamespace(backup=backup, repairs=repairs, issues=issues)
    for name in (
        "custom_components.family_assistant.backup",
        "custom_components.family_assistant.backup_recovery",
        "custom_components.family_assistant.repairs",
    ):
        sys.modules.pop(name, None)


def recoverable(recovery):
    coordinator = recovery.backup._Coordinator()
    coordinator.phase = recovery.backup.PHASE_RECOVERY
    hass = SimpleNamespace(data={"family_assistant": {"entries": {}, "backup": coordinator}})
    return hass, coordinator


@pytest.mark.asyncio
async def test_issue_is_content_free_and_flow_releases_captured_generation(recovery):
    hass, coordinator = recoverable(recovery)
    recovery.backup._show_recovery(hass, coordinator)
    assert recovery.issues == {
        ("family_assistant", "backup_recovery"): {
            "is_fixable": True,
            "is_persistent": False,
            "severity": "error",
            "translation_key": "backup_recovery",
        }
    }
    flow = await recovery.repairs.async_create_fix_flow(hass, "backup_recovery", None)
    flow.hass = hass
    form = await flow.async_step_init()
    assert form["type"] == "form" and form["step_id"] == "confirm"
    metadata_form = await flow.async_step_init({"issue_id": "backup_recovery"})
    assert metadata_form["type"] == "form" and metadata_form["step_id"] == "confirm"
    assert hass.data["family_assistant"]["backup"] is coordinator
    assert not coordinator.released.is_set()
    result = await flow.async_step_confirm({})
    assert result == {"type": "create_entry", "title": "", "data": {}}
    assert coordinator.released.is_set()
    assert "backup" not in hass.data["family_assistant"]
    assert recovery.issues == {}


@pytest.mark.asyncio
async def test_flow_captured_for_old_generation_cannot_release_new_one(recovery):
    hass, old = recoverable(recovery)
    flow = await recovery.repairs.async_create_fix_flow(hass, "backup_recovery", None)
    flow.hass = hass
    current = recovery.backup._Coordinator()
    current.phase = recovery.backup.PHASE_RECOVERY
    hass.data["family_assistant"]["backup"] = current

    assert await flow.async_step_confirm({}) == {
        "type": "abort",
        "reason": "stale_recovery",
    }
    assert not old.released.is_set() and not current.released.is_set()
    assert hass.data["family_assistant"]["backup"] is current


@pytest.mark.asyncio
async def test_failed_confirmation_keeps_same_generation_actionable(recovery):
    hass, coordinator = recoverable(recovery)

    class Engine:
        async def async_end_backup(self, _token):
            raise RuntimeError("synthetic private failure")

    runtime = SimpleNamespace(engine=Engine(), media=SimpleNamespace())
    coordinator.leases.append(
        recovery.backup._Lease(
            runtime=runtime,
            engine_token=object(),
            engine_acquired=True,
        )
    )
    recovery.backup._show_recovery(hass, coordinator)
    flow = await recovery.repairs.async_create_fix_flow(hass, "backup_recovery", None)
    flow.hass = hass

    result = await flow.async_step_confirm({})
    assert result["type"] == "form"
    assert result["errors"] == {"base": "backup_unavailable"}
    assert "synthetic private failure" not in repr(result)
    assert recovery.backup.recovery_identity(hass) == (
        coordinator,
        coordinator.generation,
    )
    assert coordinator.leases[0].engine_acquired is True
    assert not coordinator.released.is_set()


@pytest.mark.asyncio
async def test_unknown_or_data_bearing_issue_never_creates_recovery_flow(recovery):
    hass, _coordinator = recoverable(recovery)
    with pytest.raises(_UnknownStep):
        await recovery.repairs.async_create_fix_flow(hass, "other", None)
    with pytest.raises(_UnknownStep):
        await recovery.repairs.async_create_fix_flow(
            hass, "backup_recovery", {"generation": "must-not-be-accepted"}
        )
