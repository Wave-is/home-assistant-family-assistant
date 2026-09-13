"""Actual Home Assistant backup-platform checks without creating a real backup."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePath

from aiohttp import ClientSession
from ha_options_menu import select_option
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component


@asynccontextmanager
async def _token(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/backup-smoke"
    )
    try:
        yield hass.auth.async_create_access_token(refresh)
    finally:
        hass.auth.async_remove_refresh_token(refresh)


async def _websocket(hass, user, message):
    async with _token(hass, user) as token, ClientSession() as session:
        ws = await session.ws_connect("http://127.0.0.1:8123/api/websocket")
        try:
            assert (await ws.receive_json())["type"] == "auth_required"
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"
            await ws.send_json(message)
            return await ws.receive_json()
        finally:
            await ws.close()


async def _media_get(session, token, entry_id, media_id, revision):
    url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry_id}/{media_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Family-Media-Revision": str(revision),
    }
    async with session.get(url, headers=headers) as response:
        return response.status, await response.read()


async def _options_form(hass, entry, user, step):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    assert flow["type"] == "menu", flow
    return await select_option(hass, flow, step)


def _digest_tree(root: Path) -> dict[str, tuple[int, str]]:
    result = {}
    for path in sorted(root.rglob("*")):
        assert not path.is_symlink()
        if path.is_file():
            content = path.read_bytes()
            result[path.relative_to(root).as_posix()] = (len(content), sha256(content).hexdigest())
    return result


def _assert_core_backup_includes(path: PurePath, excludes) -> None:
    archived = PurePath("data") / path
    assert not any(archived.full_match(f"data/{pattern}") for pattern in excludes)


async def _restored_copy_reads(
    directory: Path,
    entry,
    owner,
    expected,
    store_copy: Path,
    media_copy: Path,
    expected_state: dict,
) -> None:
    """Load the copied HA Store and bytes through fresh Engine/MediaStorage objects."""
    from homeassistant import loader

    from custom_components.family_assistant.const import DOMAIN, SCHEMA_VERSION
    from custom_components.family_assistant.domain.engine import Engine
    from custom_components.family_assistant.media_storage import MediaStorage

    restored_hass = HomeAssistant(str(directory))
    loader.async_setup(restored_hass)
    store = Store(restored_hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}")
    restored_store_path = Path(store.path)
    restored_store_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(store_copy, restored_store_path)
    restored_root = Path(
        restored_hass.config.path(
            "family_assistant_data", sha256(entry.entry_id.encode()).hexdigest()
        )
    )
    shutil.copytree(media_copy, restored_root)

    storage = None
    try:
        state = await store.async_load()
        assert isinstance(state, dict)
        assert state == expected_state
        engine = Engine(state, store.async_save)
        storage = MediaStorage(engine, restored_root, lambda: datetime.now(UTC))

        async def allowed():
            return None

        for item in expected["records"]:
            record = engine.snapshot()["media"][item["media_id"]]
            metadata, content = await storage.get(
                owner.id,
                item["media_id"],
                record["revision"],
                guard=allowed,
            )
            assert metadata["status"] == "attached" and metadata["revision"] == 3
            assert len(content) == item["size_bytes"]
            assert sha256(content).hexdigest() == item["sha256"]
    finally:
        if storage is not None:
            await storage.stop()
        await restored_hass.async_stop(force=True)


async def verify_backup(hass, entry, owner, media_expected) -> None:
    """Verify real backup callbacks, coherent copies, and reversible quiescing."""
    from homeassistant import config_entries
    from homeassistant.components.backup import async_get_manager
    from homeassistant.components.backup.const import EXCLUDE_FROM_BACKUP
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.family_assistant import backup as family_backup
    from custom_components.family_assistant.const import DOMAIN
    from custom_components.family_assistant.domain.validation import DomainError

    async def expect_domain_error(awaitable, code):
        try:
            await awaitable
        except DomainError as error:
            assert error.code == code
        else:
            raise AssertionError(f"expected fixed domain error {code}")

    assert isinstance(media_expected, dict) and media_expected.get("records")
    assert await async_setup_component(hass, "backup", {})
    await hass.async_block_till_done()
    manager = async_get_manager(hass)
    assert manager.platforms.get(DOMAIN) is family_backup

    data = hass.data[DOMAIN]
    runtimes = dict(data["entries"])
    assert runtimes and runtimes[entry.entry_id] is entry.runtime_data
    runtime = entry.runtime_data
    initial = runtime.engine.snapshot()
    initial_view = runtime.engine.view("owner")
    processed = initial["processed"]["smoke-add"]
    assert set(processed) == {"fingerprint", "result", "role"}
    replay_message = {
        "id": 1901,
        "type": "family_assistant/execute",
        "entry_id": entry.entry_id,
        "action": "shopping.add",
        "payload": {"name": "Milk"},
        "operation_id": "smoke-add",
    }
    options_before = dict(entry.options)
    # Capture a legitimate form before the backup marker exists. Its eventual
    # submit must still pass the current commit-time gate.
    begun_options = await _options_form(hass, entry, owner, "alarm_device")
    assert begun_options["type"] == "form" and begun_options["step_id"] == "alarm_device"
    begun_options = await hass.config_entries.options.async_configure(
        begun_options["flow_id"], {"member": "owner"}
    )
    assert begun_options["type"] == "form" and begun_options["step_id"] == "alarm_device_settings"

    store_path = Path(hass.config.path(".storage", f"{DOMAIN}.{entry.entry_id}"))
    assert store_path.is_file() and not store_path.is_symlink()
    media_root = runtime.media.root
    assert media_root.is_dir() and media_root.is_relative_to(Path(hass.config.path()))
    integration_root = Path(family_backup.__file__).resolve().parent
    assert not media_root.is_relative_to(integration_root)
    _assert_core_backup_includes(PurePath(".storage") / store_path.name, EXCLUDE_FROM_BACKUP)
    for relative in _digest_tree(media_root):
        _assert_core_backup_includes(
            PurePath("family_assistant_data") / media_root.name / relative,
            EXCLUDE_FROM_BACKUP,
        )

    with tempfile.TemporaryDirectory(prefix="family-backup-smoke-") as temporary:
        copied = Path(temporary)
        store_copy = copied / "family-store.json"
        media_copy = copied / "private-media"
        pre_attempted = False
        frozen = False
        reload_task = None
        try:
            pre_attempted = True
            await manager.async_pre_backup_actions()
            frozen = True
            assert data.get("backup")
            coordinator = data["backup"]
            frozen_state = runtime.engine.snapshot()
            assert frozen_state == initial
            assert runtime.engine.view("owner") == initial_view

            try:
                await family_backup.async_pre_backup(hass)
            except HomeAssistantError as error:
                assert str(error) == "backup_unavailable"
            else:
                raise AssertionError("overlapping pre-backup unexpectedly succeeded")
            assert data["backup"] is coordinator

            blocked_begun = await hass.config_entries.options.async_configure(
                begun_options["flow_id"],
                {
                    "volume": 0.5,
                    "enabled": False,
                    "confirmed": False,
                },
            )
            assert blocked_begun["type"] == "abort"
            assert blocked_begun["reason"] == "backup_in_progress"

            blocked_new = await _options_form(hass, entry, owner, "alarm_device")
            assert blocked_new["type"] == "abort"
            assert blocked_new["reason"] == "backup_in_progress"
            assert dict(entry.options) == options_before

            for selected in runtimes.values():
                await expect_domain_error(
                    selected.engine.system_update(
                        "backup_smoke",
                        datetime.now(UTC),
                        lambda ctx: {"unexpected": True},
                    ),
                    "backup_in_progress",
                )
                await expect_domain_error(selected.media.async_pause_backup(), "media_unavailable")

            view_response = await _websocket(
                hass,
                owner,
                {
                    "id": 1900,
                    "type": "family_assistant/view",
                    "entry_id": entry.entry_id,
                },
            )
            assert view_response["success"] and view_response["result"]["role"] == "owner"

            denied = await _websocket(hass, owner, replay_message)
            assert denied["success"] is False
            assert denied["error"]["code"] == "backup_in_progress"

            first = media_expected["records"][0]
            async with _token(hass, owner) as owner_token, ClientSession() as session:
                status, content = await _media_get(
                    session,
                    owner_token,
                    entry.entry_id,
                    first["media_id"],
                    3,
                )
            assert status == 503 and json.loads(content) == {"code": "media_unavailable"}

            reload_task = asyncio.create_task(hass.config_entries.async_reload(entry.entry_id))
            await asyncio.sleep(0.05)
            assert not reload_task.done()
            assert entry.state is config_entries.ConfigEntryState.UNLOAD_IN_PROGRESS
            assert data["entries"][entry.entry_id] is runtime

            shutil.copy2(store_path, store_copy)
            shutil.copytree(media_root, media_copy)
            assert store_path.read_bytes() == store_copy.read_bytes()
            assert _digest_tree(media_root) == _digest_tree(media_copy)
            assert runtime.engine.snapshot() == frozen_state
        finally:
            if frozen:
                try:
                    await manager.async_post_backup_actions()
                finally:
                    await family_backup.async_post_backup(hass)
            elif pre_attempted and data.get("backup"):
                # Another platform may abort the manager's pre phase after this
                # integration acquired its lease.  Release only our coordinator;
                # the manager owns cleanup for the other platforms.
                await family_backup.async_post_backup(hass)
            if reload_task is not None:
                assert await asyncio.wait_for(reload_task, 30)

        assert "backup" not in data
        assert entry.state is config_entries.ConfigEntryState.LOADED
        runtime = entry.runtime_data
        await runtime.scheduler.stop()
        token = await runtime.media.async_pause_backup()
        await runtime.media.async_resume_backup(token)

        before_replay = runtime.engine.snapshot()
        # Normal unload persists alarm-output shutdown leases. This happens
        # after thaw, not inside the copied backup. All durable household data
        # and receipts must otherwise survive that actual Core reload unchanged.
        for key in set(before_replay) | set(initial):
            if key not in {"revision", "alarm_outputs"}:
                assert before_replay.get(key) == initial.get(key), key
        assert before_replay["revision"] >= initial["revision"]
        replayed = await _websocket(hass, owner, replay_message)
        assert replayed["success"] and replayed["result"] == processed["result"]
        assert runtime.engine.snapshot() == before_replay

        restored = copied / "restored-ha"
        await _restored_copy_reads(
            restored,
            entry,
            owner,
            media_expected,
            store_copy,
            media_copy,
            frozen_state,
        )

    print(
        "PASS: actual HA backup platform quiescing, coherent synthetic Store/media copy, "
        "authenticated denial and exact replay"
    )
