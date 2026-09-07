"""Fresh-process native HA encrypted restore; fictional data and owned temp only.

No HA Store/auth/config-entry files are edited by this helper. Native HA backup
restore owns their replacement. The restore key is never a CLI argument, output,
or fixture-contract field; only HA's own disposable restart instruction holds it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_restore_acceptance import owned_config  # noqa: E402


def _write(path: Path, content: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(content, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read(config: Path, name: str) -> dict:
    result = json.loads((config.parent / name).read_bytes())
    assert type(result) is dict
    return result


async def _boot(config: Path):
    from homeassistant import bootstrap, loader
    from homeassistant import config as ha_config
    from homeassistant.const import EVENT_CALL_SERVICE
    from homeassistant.core import CoreState, HomeAssistant

    hass = HomeAssistant(str(config))
    hass.config.skip_pip = True
    loader.async_setup(hass)
    service_calls = []
    hass.data["synthetic_restore_service_calls"] = service_calls
    hass.bus.async_listen(
        EVENT_CALL_SERVICE,
        lambda event: service_calls.append((event.data.get("domain"), event.data.get("service"))),
    )
    configuration = await ha_config.async_hass_config_yaml(hass)
    assert await bootstrap.async_from_config_dict(configuration, hass) is hass
    await hass.async_start()
    await hass.async_block_till_done()
    assert hass.state is CoreState.running and not hass.config.recovery_mode
    return hass


def _entry(hass, contract):
    from homeassistant.config_entries import ConfigEntryState

    entries = hass.config_entries.async_entries("family_assistant")
    assert len(entries) == 1 and entries[0].entry_id == contract["entry_id"]
    entry = entries[0]
    assert entry.state is ConfigEntryState.LOADED
    assert dict(entry.data) == contract["entry_data"]
    assert dict(entry.options) == contract["entry_options"]
    runtime = entry.runtime_data
    assert runtime.telegram is None and runtime.assistant is None
    assert runtime.network is None and runtime.recipes is None
    assert not runtime.engine.snapshot()["alarm_runs"]
    return entry


async def _photo(hass, entry, owner):
    from aiohttp import ClientSession
    from ha_media_smoke import _http, _image, _token

    engine = entry.runtime_data.engine
    now = datetime.now(UTC)
    task = await engine.execute(
        "owner",
        "tasks.create",
        {
            "title": "Synthetic restored private photograph",
            "assignee": "owner",
            "report_type": "photo",
            "due_at": "2099-12-01T09:00:00+00:00",
        },
        "restore-photo-task",
        now,
    )
    member = engine.snapshot()["members"]["owner"]
    reserved = await engine.execute(
        "owner",
        "media.reserve",
        {
            "purpose": "task_report",
            "task_id": task["id"],
            "task_revision": task["revision"],
            "uploader_revision": member["revision"],
        },
        "restore-photo-reserve",
        now,
    )
    body = _image("PNG")
    url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{reserved['id']}"
    async with _token(hass, owner) as token, ClientSession() as session:
        status, _, _ = await _http(
            session, "PUT", url, token, 1, body=body, content_type="image/png"
        )
        assert status == 200
    submitted = await engine.execute(
        "owner",
        "tasks.submit",
        {
            "id": task["id"],
            "revision": task["revision"],
            "media": {"id": reserved["id"], "revision": 2},
        },
        "restore-photo-submit",
        now,
    )
    assert submitted["status"] == "submitted"
    return {
        "id": reserved["id"],
        "revision": 3,
        "sha256": sha256(body).hexdigest(),
        "size": len(body),
    }


async def seed(config: Path) -> None:
    """Persist media and authentication through an orderly HA shutdown first."""
    contract = _read(config, "contract.json")
    hass = await _boot(config)
    try:
        entry = _entry(hass, contract)
        owner = await hass.auth.async_get_user(contract["owner_user_id"])
        assert owner is not None
        media = await _photo(hass, entry, owner)
        refresh = await hass.auth.async_create_refresh_token(
            owner, client_id="https://example.invalid/restore"
        )
        _write(
            config.parent / "seed.json",
            {
                "media": media,
                "access_token": hass.auth.async_create_access_token(refresh),
            },
        )
    finally:
        await hass.async_stop(force=True)


async def backup(config: Path, version: str) -> None:
    from ha_encrypted_archive_smoke import LOCAL_AGENT, _manifest
    from ha_upgrade_acceptance import _add_siren, _runtime_version, _selected
    from homeassistant.backup_restore import RESTORE_BACKUP_FILE
    from homeassistant.components.backup import async_get_manager
    from homeassistant.components.backup.util import read_backup, validate_password
    from homeassistant.const import RESTART_EXIT_CODE
    from homeassistant.core import CoreState

    assert _runtime_version(config) == version
    contract = _read(config, "contract.json")
    hass = await _boot(config)
    try:
        entry = _entry(hass, contract)
        runtime = entry.runtime_data
        assert _selected(runtime.engine.snapshot(), contract["ids"]) == contract["selected_state"]
        owner = await hass.auth.async_get_user(contract["owner_user_id"])
        assert owner is not None and owner.is_admin and owner.is_active
        siren = await _add_siren(hass)
        seeded = _read(config, "seed.json")
        media, access = seeded["media"], seeded["access_token"]
        await hass.async_block_till_done()
        state = runtime.engine.snapshot()
        store = config / ".storage" / f"family_assistant.{entry.entry_id}"
        store_bytes = store.read_bytes()
        assert json.loads(store_bytes)["data"] == state
        media_files = _manifest(runtime.media.root)
        manager = async_get_manager(hass)
        assert manager.state.value == "idle"
        existing, errors = await manager.async_get_backups()
        assert not errors and not existing
        password = secrets.token_urlsafe(32)
        created = await manager.async_initiate_backup(
            agent_ids=[LOCAL_AGENT],
            include_addons=None,
            include_all_addons=False,
            include_database=False,
            include_folders=None,
            include_homeassistant=True,
            name="Synthetic full Core restore acceptance",
            password=password,
            raise_task_error=True,
        )
        # Exact owned task: HA 2026.8.2 has no public wait-by-backup-job API.
        finish = manager._backup_finish_task
        assert finish is not None
        await asyncio.wait_for(finish, 120)
        assert manager.state.value == "idle" and manager._backup_finish_task is None
        archive = Path(
            manager.local_backup_agents[LOCAL_AGENT].get_backup_path(created.backup_job_id)
        )
        assert archive.resolve().is_relative_to(config / "backups") and not archive.is_symlink()
        assert read_backup(archive).protected and validate_password(archive, password)
        assert not validate_password(archive, password + "-wrong")
        assert password.encode() not in archive.read_bytes()
        # Keep synthetic authentication private, outside the restored config and
        # never in test output. This temp contract is deleted by the orchestrator.
        expected = {
            "state": state,
            "store_sha256": sha256(store_bytes).hexdigest(),
            "media": media,
            "media_files": media_files,
            "access_token": access,
            "owner_name": owner.name,
            "configuration_sha256": sha256(
                (config / "configuration.yaml").read_bytes()
            ).hexdigest(),
            "runtime_files": _manifest(config / "custom_components" / "family_assistant"),
        }
        _write(config.parent / "expected.json", expected)
        restore_args = {
            "agent_id": LOCAL_AGENT,
            "restore_addons": None,
            "restore_database": False,
            "restore_folders": None,
            "restore_homeassistant": True,
        }
        try:
            await manager.async_restore_backup(
                created.backup_job_id, password=password + "-wrong", **restore_args
            )
        except Exception as error:
            assert type(error).__name__ == "IncorrectPasswordError"
        else:
            raise AssertionError("incorrect key was accepted")
        assert hass.state is CoreState.running and manager.state.value == "idle"
        assert not (config / RESTORE_BACKUP_FILE).exists()
        assert store.read_bytes() == store_bytes and _manifest(runtime.media.root) == media_files
        assert runtime.engine.snapshot() == state and not siren.calls

        # Prove restoration is not simply reopening unchanged current data.
        changed = await runtime.engine.execute(
            "owner",
            "tasks.create",
            {
                "title": "Synthetic task created AFTER the backup",
                "assignee": "owner",
                "due_at": "2099-12-01T09:00:00+00:00",
            },
            "restore-after-backup-task",
            datetime.now(UTC),
        )
        assert changed["id"] not in state["tasks"]
        await hass.auth.async_update_user(owner, name="Synthetic changed AFTER backup")
        hass.config_entries.async_update_entry(
            entry, options={**dict(entry.options), "restore_test_marker": "after"}
        )
        _write(config / "after-backup-marker.json", {"synthetic": True})
        await hass.async_block_till_done()
        assert runtime.engine.snapshot() != state and store.read_bytes() != store_bytes
        assert owner.name != expected["owner_name"]
        await manager.async_restore_backup(created.backup_job_id, password=password, **restore_args)
        async with asyncio.timeout(90):
            while hass.state is not CoreState.stopped:
                await asyncio.sleep(0.05)
        assert hass.exit_code == RESTART_EXIT_CODE
        assert (config / RESTORE_BACKUP_FILE).is_file() and not siren.calls
    finally:
        if hass.state is not CoreState.stopped:
            await hass.async_stop(force=True)


def restore(config: Path) -> None:
    """Use the real startup restore implementation, never manual Store writes."""
    from homeassistant.backup_restore import (
        RESTORE_BACKUP_FILE,
        RESTORE_BACKUP_RESULT_FILE,
        restore_backup,
    )

    instruction = json.loads((config / RESTORE_BACKUP_FILE).read_bytes())
    archive = Path(instruction["path"])
    assert archive.is_absolute() and archive.resolve(strict=True).is_relative_to(config / "backups")
    assert not archive.is_symlink() and archive.is_file()
    assert instruction["restore_homeassistant"] is True and instruction["restore_database"] is False
    assert instruction["remove_after_restore"] is False
    assert (config / "after-backup-marker.json").is_file()
    expected = _read(config, "expected.json")
    contract = _read(config, "contract.json")
    # Dirty only owned synthetic blobs AFTER HA stopped. Unchanged source files
    # must not let an incomplete restore accidentally pass the checksum checks.
    media_root = (
        config / "family_assistant_data" / sha256(contract["entry_id"].encode()).hexdigest()
    )
    for name in expected["media_files"]:
        path = media_root / name
        assert path.resolve(strict=True).parent == media_root and not path.is_symlink()
        path.write_bytes(b"synthetic post-backup damage")
    assert restore_backup(str(config)) is True
    assert not (config / RESTORE_BACKUP_FILE).exists()
    assert not (config / "after-backup-marker.json").exists()
    result = json.loads((config / RESTORE_BACKUP_RESULT_FILE).read_bytes())
    assert result == {"success": True, "error": None, "error_type": None}
    store = config / ".storage" / f"family_assistant.{contract['entry_id']}"
    assert sha256(store.read_bytes()).hexdigest() == expected["store_sha256"]
    assert (
        sha256((config / "configuration.yaml").read_bytes()).hexdigest()
        == expected["configuration_sha256"]
    )
    # A second startup cannot reapply the same restore instruction.
    assert restore_backup(str(config)) is False


async def verify(config: Path, version: str) -> None:
    from aiohttp import ClientSession
    from ha_encrypted_archive_smoke import _manifest
    from ha_upgrade_acceptance import _add_siren, _runtime_version, _selected
    from homeassistant.backup_restore import RESTORE_BACKUP_FILE, RESTORE_BACKUP_RESULT_FILE
    from homeassistant.components.backup import async_get_manager

    expected = _read(config, "expected.json")
    contract = _read(config, "contract.json")
    assert _runtime_version(config) == version
    assert (
        json.loads(json.dumps(_manifest(config / "custom_components" / "family_assistant")))
        == expected["runtime_files"]
    )
    hass = await _boot(config)
    try:
        entry = _entry(hass, contract)
        owner = await hass.auth.async_get_user(contract["owner_user_id"])
        assert (
            owner is not None
            and owner.name == expected["owner_name"]
            and owner.is_admin
            and owner.is_active
        )
        runtime = entry.runtime_data
        assert runtime.engine.snapshot() == expected["state"]
        assert json.loads(json.dumps(_manifest(runtime.media.root))) == expected["media_files"]
        assert _selected(runtime.engine.snapshot(), contract["ids"]) == contract["selected_state"]
        siren = await _add_siren(hass)
        assert siren.entity_id == contract["siren_entity_id"]
        # Pre-backup credentials, real HTTP, and private attachment authorization.
        async with ClientSession() as session:
            headers = {"Authorization": f"Bearer {expected['access_token']}"}
            async with session.get("http://127.0.0.1:8123/api/", headers=headers) as response:
                assert response.status == 200
            media = expected["media"]
            url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{media['id']}"
            headers["X-Family-Media-Revision"] = str(media["revision"])
            async with session.get(url, headers=headers) as response:
                assert response.status == 200
                body = await response.read()
                assert len(body) == media["size"] and sha256(body).hexdigest() == media["sha256"]
                assert "no-store" in response.headers["Cache-Control"]
            async with session.get(url) as response:
                assert response.status == 401
            async with session.get(
                "http://127.0.0.1:8123/family_assistant/frontend/family-assistant.js"
            ) as response:
                assert response.status == 200
                assert await response.read()
        before = runtime.engine.snapshot()
        for command in contract["commands"]:
            receipt = await runtime.engine.execute(
                "owner",
                command["action"],
                command["payload"],
                command["operation_id"],
                datetime.now(UTC),
            )
            assert receipt == before["processed"][command["operation_id"]]["result"]
        assert runtime.engine.snapshot() == before and not siren.calls
        assert not any(
            domain in {"siren", "switch", "light", "notify", "telegram_bot"}
            for domain, _service in hass.data["synthetic_restore_service_calls"]
        )
        assert not hass.data["family_assistant"].get("backup")
        assert async_get_manager(hass).state.value == "idle"
        assert not (config / RESTORE_BACKUP_FILE).exists()
        assert not (config / RESTORE_BACKUP_RESULT_FILE).exists()
    finally:
        await hass.async_stop(force=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "backup", "restore", "verify"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ownership-token", required=True)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    config = owned_config(args.config, args.ownership_token)
    if args.phase == "prepare":
        from ha_upgrade_acceptance import _core_config, prepare

        # JSON is valid YAML, generated solely in the owned synthetic config.
        _write(config / "configuration.yaml", _core_config())
        contract = asyncio.run(prepare(config, args.expected_version))
        _write(config.parent / "contract.json", contract)
        asyncio.run(seed(config))
    elif args.phase == "restore":
        restore(config)
    else:
        asyncio.run((backup if args.phase == "backup" else verify)(config, args.expected_version))
    print(f"PASS: isolated encrypted restore {args.phase}")


if __name__ == "__main__":
    main()
