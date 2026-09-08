"""Native-Store-shaped ports plus real temporary private blob I/O; no running HA."""

import asyncio
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_shadow_reverify import candidate

ROOT = Path(__file__).parents[1]
ENTRY = "synthetic-shadow-entry-0001"
STORE = f"family_assistant.{ENTRY}"
JOURNAL = f"family_assistant.shadow_intent.{ENTRY}"


@pytest.fixture
def port(monkeypatch, tmp_path):
    values, writes = {}, []
    user = SimpleNamespace(id="synthetic-owner", is_active=True, is_admin=True)
    options = SimpleNamespace(before_save=None, after_save=None, before_load=None, before_auth=None)

    class Store:
        def __init__(self, hass, version, key):
            self.key = key

        async def async_load(self):
            if options.before_load:
                await options.before_load(self.key)
            return deepcopy(values.get(self.key))

        async def async_save(self, value):
            if options.before_save:
                await options.before_save(self.key)
            writes.append(self.key)
            values[self.key] = deepcopy(value)
            if options.after_save:
                await options.after_save(self.key)

    storage = ModuleType("homeassistant.helpers.storage")
    storage.Store = Store
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_install",
        ROOT / "custom_components/family_assistant/migration/shadow_install.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def get_user(_id):
        if options.before_auth:
            await options.before_auth()
        return user

    entries = {}
    hass = SimpleNamespace(
        data={},
        auth=SimpleNamespace(async_get_user=get_user),
        config=SimpleNamespace(path=lambda *parts: str(tmp_path.joinpath(*parts))),
        config_entries=SimpleNamespace(async_get_entry=lambda entry_id: entries.get(entry_id)),
    )
    original, target = candidate()

    async def stage(**overrides):
        args = dict(
            entry_id=ENTRY,
            user_id=user.id,
            candidate=original,
            target=target,
            expected_fingerprint=original.summary()["fingerprint"],
        )
        return await module.async_stage_shadow(hass, **(args | overrides))

    return SimpleNamespace(
        module=module,
        hass=hass,
        user=user,
        target=target,
        candidate=original,
        values=values,
        writes=writes,
        options=options,
        entries=entries,
        stage=stage,
        root=tmp_path,
    )


@pytest.mark.asyncio
async def test_new_shadow_is_committed_last_exact_replay_does_not_write(port):
    receipt = await port.stage()
    assert receipt["mode"] == "read_only_shadow_staged"
    assert port.writes == [JOURNAL, STORE]
    assert port.values[STORE] == port.candidate.private_state()
    assert not port.entries and not port.hass.data["family_assistant"]["entries"]
    assert await port.stage() == receipt
    assert port.writes == [JOURNAL, STORE]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "inactive",
        "admin",
        "owner",
        "entry",
        "runtime",
        "backup",
        "fingerprint",
        "existing",
        "intent",
        "path",
    ],
)
async def test_staging_refuses_wrong_authority_or_nonfresh_target(port, reason):
    kwargs = {}
    if reason == "inactive":
        port.user.is_active = False
    if reason == "admin":
        port.user.is_admin = False
    if reason == "owner":
        port.user.id = "another-owner"
    if reason == "entry":
        port.entries[ENTRY] = object()
    if reason == "runtime":
        port.hass.data["family_assistant"] = {"entries": {ENTRY: object()}}
    if reason == "backup":
        port.hass.data["family_assistant"] = {"entries": {}, "backup": object()}
    if reason == "fingerprint":
        kwargs["expected_fingerprint"] = "0" * 64
    if reason == "existing":
        port.values[STORE] = {"private": "unrelated household"}
    if reason == "intent":
        port.values[JOURNAL] = {"version": 1, "fingerprint": "0" * 64}
    if reason == "path":
        kwargs["entry_id"] = "../outside-target"
    before = deepcopy(port.values)
    with pytest.raises(port.module.ShadowInstallError):
        await port.stage(**kwargs)
    assert port.values == before and not port.writes


@pytest.mark.asyncio
async def test_existing_private_directory_is_not_claimed_even_when_empty(port):
    import hashlib

    root = port.root / "family_assistant_data" / hashlib.sha256(ENTRY.encode()).hexdigest()
    root.mkdir(parents=True)
    with pytest.raises(port.module.ShadowInstallError, match="conflict"):
        await port.stage()
    assert root.is_dir() and not port.writes


@pytest.mark.asyncio
async def test_exact_replay_refuses_foreign_residue_without_deleting_it(port):
    import hashlib

    await port.stage()
    root = port.root / "family_assistant_data" / hashlib.sha256(ENTRY.encode()).hexdigest()
    root.mkdir(parents=True)
    residue = root / "unrelated-private-file"
    residue.write_bytes(b"private residue")
    before = deepcopy(port.values)
    with pytest.raises(port.module.ShadowInstallError, match="conflict"):
        await port.stage()
    assert residue.read_bytes() == b"private residue" and port.values == before


@pytest.mark.asyncio
@pytest.mark.parametrize("committed", [False, True])
async def test_store_failure_retries_exact_intent_without_deletion(port, committed):
    async def fail(key):
        if key == STORE:
            raise OSError("PRIVATE path and data")

    if committed:
        port.options.after_save = fail
    else:
        port.options.before_save = fail
    with pytest.raises(port.module.ShadowInstallError, match="retry_required") as caught:
        await port.stage()
    assert "PRIVATE" not in str(caught.value)
    assert JOURNAL in port.values
    assert (STORE in port.values) == committed
    port.options.after_save = port.options.before_save = None
    port.hass.data.clear()  # New process-local coordination; native Store values survive.
    await port.stage()
    assert port.values[STORE] == port.candidate.private_state()
    assert port.writes.count(STORE) == 1


@pytest.mark.asyncio
async def test_boolean_journal_version_is_not_integer_one(port):
    async def fail(key):
        if key == STORE:
            raise OSError("synthetic final-write failure")

    port.options.before_save = fail
    with pytest.raises(port.module.ShadowInstallError):
        await port.stage()
    port.values[JOURNAL]["version"] = True
    port.options.before_save = None
    with pytest.raises(port.module.ShadowInstallError, match="conflict"):
        await port.stage()
    assert STORE not in port.values


@pytest.mark.asyncio
async def test_concurrent_exact_requests_publish_only_one_state(port):
    one, two = await asyncio.gather(port.stage(), port.stage())
    assert one == two and port.writes == [JOURNAL, STORE]


@pytest.mark.asyncio
async def test_revocation_while_waiting_for_store_prevents_commit(port):
    async def revoke(key):
        if key == JOURNAL:
            port.user.is_active = False

    port.options.before_load = revoke
    with pytest.raises(port.module.ShadowInstallError, match="forbidden"):
        await port.stage()
    assert not port.values


@pytest.mark.asyncio
async def test_cancellation_drains_owned_store_write_before_releasing_setup_lock(port):
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed(key):
        if key == STORE:
            started.set()
            await release.wait()

    port.options.before_save = delayed
    task = asyncio.create_task(port.stage())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and port.hass.data["family_assistant"]["setup_lock"].locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert port.values[STORE] == port.candidate.private_state()
    port.options.before_save = None
    await port.stage()
    assert port.writes.count(STORE) == 1


@pytest.mark.asyncio
async def test_target_edit_during_wait_is_not_silently_adopted(port):
    async def change(key):
        if key == JOURNAL:
            port.target["members"]["owner"]["revision"] += 1

    port.options.before_load = change
    with pytest.raises(port.module.ShadowInstallError, match="forbidden"):
        await port.stage()
    assert not port.values
