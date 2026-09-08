"""Exact registration retries with shaped Core ports; native HA also tests this API."""

import asyncio
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_shadow_install import ENTRY, JOURNAL, STORE
from test_shadow_install import port as stage_port

from custom_components.family_assistant.domain.engine import Engine


@pytest.fixture
def port(monkeypatch, tmp_path):
    p = stage_port.__wrapped__(monkeypatch, tmp_path)
    module_name = "custom_components.family_assistant.migration.shadow_install"
    monkeypatch.setitem(sys.modules, module_name, p.module)
    added = []
    p.options.before_setup = p.options.after_add = None

    class ConfigEntryState:
        LOADED = "loaded"
        NOT_LOADED = "not_loaded"

    class ConfigEntry:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.state = ConfigEntryState.NOT_LOADED

    entries_module = ModuleType("homeassistant.config_entries")
    entries_module.ConfigEntry, entries_module.ConfigEntryState = ConfigEntry, ConfigEntryState
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", entries_module)

    async def add(entry):
        assert entry.entry_id not in p.entries
        p.entries[entry.entry_id] = entry
        added.append(entry.entry_id)
        if p.options.before_setup:
            await p.options.before_setup(entry)

        async def unexpected_save(_state):
            raise AssertionError("Shadow Engine must not write")

        engine = Engine(deepcopy(p.values[STORE]), unexpected_save)
        p.hass.data["family_assistant"]["entries"][entry.entry_id] = SimpleNamespace(engine=engine)
        entry.state = ConfigEntryState.LOADED
        if p.options.after_add:
            await p.options.after_add(entry)

    p.hass.config_entries.async_add = add
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_registration",
        Path(__file__).parents[1]
        / "custom_components/family_assistant/migration/shadow_registration.py",
    )
    registration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registration)

    async def register(**overrides):
        args = dict(
            entry_id=ENTRY,
            user_id=p.user.id,
            candidate=p.candidate,
            target=p.target,
            expected_fingerprint=p.candidate.summary()["fingerprint"],
        )
        return await registration.async_register_shadow(p.hass, **(args | overrides))

    p.registration, p.register, p.added = registration, register, added
    return p


@pytest.mark.asyncio
async def test_staging_then_registration_and_concurrent_replay_create_one_sealed_entry(port):
    first, second = await asyncio.gather(port.register(), port.register())
    assert (
        first
        == second
        == {
            "mode": "read_only_shadow_registered",
            "entry_id": ENTRY,
            "fingerprint": port.candidate.summary()["fingerprint"],
            "loaded": True,
            "activation_available": False,
        }
    )
    assert port.added == [ENTRY] and port.writes == [JOURNAL, STORE]
    assert port.entries[ENTRY].data["migration_shadow"]["fingerprint"] == first["fingerprint"]
    before = deepcopy(port.values)
    assert await port.register() == first
    assert before == port.values and port.added == [ENTRY] and len(port.writes) == 2


@pytest.mark.asyncio
async def test_uncertain_add_result_keeps_original_entry_and_exact_retry_recognizes_it(port):
    async def lost(_entry):
        raise OSError("PRIVATE SYNTHETIC CORE EXCEPTION")

    port.options.after_add = lost
    with pytest.raises(
        port.registration.ShadowRegistrationError, match="^shadow_registration_retry_required$"
    ):
        await port.register()
    assert port.added == [ENTRY]
    port.options.after_add = None
    assert (await port.register())["loaded"]
    assert port.added == [ENTRY] and port.writes == [JOURNAL, STORE]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["admin", "active", "owner", "backup", "id", "fingerprint"])
async def test_denied_registration_has_no_store_or_entry_effects(port, fault):
    args = {}
    if fault == "admin":
        port.user.is_admin = False
    if fault == "active":
        port.user.is_active = False
    if fault == "owner":
        port.user.id = "another-user"
    if fault == "backup":
        port.hass.data["family_assistant"] = {"backup": object()}
    if fault == "id":
        args["entry_id"] = "../../outside"
    if fault == "fingerprint":
        args["expected_fingerprint"] = "0" * 64
    with pytest.raises(port.registration.ShadowRegistrationError):
        await port.register(**args)
    assert not port.values and not port.added and not port.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    ["domain", "source", "unique", "data", "options", "title", "store", "missing", "runtime"],
)
async def test_existing_different_entry_or_state_is_never_overwritten(port, fault):
    await port.register()
    entry = port.entries[ENTRY]
    if fault in {"domain", "source", "title"}:
        setattr(entry, fault, "different")
    if fault == "unique":
        entry.unique_id = "different"
    if fault == "data":
        entry.data["owner_user_id"] = "different"
    if fault == "options":
        entry.options = {"telegram": {"enabled": True}}
    if fault == "store":
        port.values[STORE]["tasks"]["T000004"]["title"] = "Private changed record"
    if fault == "missing":
        port.values.pop(STORE)
    if fault == "runtime":
        port.hass.data["family_assistant"]["entries"][ENTRY].engine = SimpleNamespace(
            shadow_mode=False
        )
    before = deepcopy(port.values)
    with pytest.raises(
        port.registration.ShadowRegistrationError, match="^shadow_registration_conflict$"
    ):
        await port.register()
    assert port.values == before and port.added == [ENTRY] and len(port.writes) == 2


@pytest.mark.asyncio
async def test_unloaded_entry_retry_reports_registered_not_loaded_and_does_not_start_it(port):
    await port.register()
    port.entries[ENTRY].state = "not_loaded"
    port.hass.data["family_assistant"]["entries"].pop(ENTRY)
    assert (await port.register())["loaded"] is False
    assert port.added == [ENTRY] and len(port.writes) == 2


@pytest.mark.asyncio
async def test_revocation_after_staging_blocks_registration_but_preserves_exact_copy(port):
    async def revoke(key):
        if key == STORE:
            port.user.is_active = False

    port.options.after_save = revoke
    with pytest.raises(port.registration.ShadowRegistrationError):
        await port.register()
    assert not port.entries and not port.added
    assert port.values[STORE] == port.candidate.private_state()
    port.options.after_save = None
    port.user.is_active = True
    assert (await port.register())["loaded"]
    assert len(port.writes) == 2


@pytest.mark.asyncio
async def test_cancelled_registration_drains_owned_core_add_under_the_same_lock(port):
    reached, release = asyncio.Event(), asyncio.Event()

    async def pause(_entry):
        reached.set()
        await release.wait()

    port.options.before_setup = pause
    task = asyncio.create_task(port.register())
    await asyncio.wait_for(reached.wait(), 5)
    task.cancel()
    await asyncio.sleep(0)
    assert port.hass.data["family_assistant"]["shadow_registration_lock"].locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    port.options.before_setup = None
    assert (await port.register())["loaded"]
    assert port.added == [ENTRY] and len(port.writes) == 2


@pytest.mark.asyncio
async def test_revocation_while_reading_registered_store_cannot_return_success(port):
    await port.register()

    async def revoke(key):
        if key == STORE:
            port.user.is_admin = False

    port.options.before_load = revoke
    with pytest.raises(
        port.registration.ShadowRegistrationError, match="^shadow_registration_forbidden$"
    ):
        await port.register()
    assert port.added == [ENTRY] and len(port.writes) == 2


@pytest.mark.asyncio
async def test_changed_caller_target_after_native_staging_never_registers(port):
    async def change(key):
        if key == STORE:
            port.target["members"]["owner"]["name"] = "Changed private target"

    port.options.after_save = change
    with pytest.raises(
        port.registration.ShadowRegistrationError, match="^shadow_registration_forbidden$"
    ):
        await port.register()
    assert not port.added and port.values[STORE] == port.candidate.private_state()
