"""Actual encrypted Home Assistant archive acceptance in the synthetic HA lab."""

from __future__ import annotations

import asyncio
import json
import secrets
import tarfile
import tempfile
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path, PurePosixPath

from aiohttp import ClientSession

LOCAL_AGENT = "backup.local"
MANAGER_TIMEOUT = 120


@asynccontextmanager
async def _token(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/encrypted-archive-smoke"
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


async def _backup_config(hass, owner, identifier):
    response = await _websocket(
        hass,
        owner,
        {"id": identifier, "type": "backup/config/info"},
    )
    assert response["success"], response.get("error", {}).get("code")
    return response["result"]["config"]


async def _set_local_protected(hass, owner, identifier, protected):
    response = await _websocket(
        hass,
        owner,
        {
            "id": identifier,
            "type": "backup/config/update",
            "agents": {LOCAL_AGENT: {"protected": protected}},
        },
    )
    assert response["success"], response.get("error", {}).get("code")
    await hass.async_block_till_done()


def _manifest(root: Path):
    result = {}
    for path in sorted(root.rglob("*")):
        assert not path.is_symlink()
        if path.is_file():
            content = path.read_bytes()
            result[path.relative_to(root).as_posix()] = (
                len(content),
                sha256(content).hexdigest(),
            )
    return result


def _config_fingerprint(config):
    """Compare backup configuration without exposing credential-bearing values."""
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).digest()


def _family_member(member, store_name, media_prefix, seen):
    """Classify one exact Family Assistant member and reject unsafe collisions."""
    name = member.name.removeprefix("./")
    candidate = name == store_name or name.startswith("/".join(media_prefix) + "/")
    candidate |= name.rstrip("/") == "/".join(media_prefix)
    if not candidate:
        return None

    assert name and not name.startswith("/") and "\\" not in name
    canonical = name.rstrip("/")
    parts = canonical.split("/")
    assert all(part not in {"", ".", ".."} for part in parts)
    assert canonical not in seen
    seen.add(canonical)

    if canonical == store_name:
        assert member.isfile() and not member.issym() and not member.islnk()
        return "store"
    assert tuple(parts[:3]) == media_prefix
    if member.isdir():
        return "directory"
    assert member.isfile() and not member.issym() and not member.islnk()
    relative = PurePosixPath(*parts[3:])
    assert relative.parts
    return relative


def _read_family_files(archive, password, entry_id, output):
    """Read only exact regular Family Assistant files from the encrypted inner tar."""
    from securetar import SecureTarFile

    store_name = f"data/.storage/family_assistant.{entry_id}"
    media_prefix = (
        "data",
        "family_assistant_data",
        sha256(entry_id.encode()).hexdigest(),
    )
    store_content = None
    media_manifest = {}
    seen = set()

    with tarfile.open(archive, mode="r:") as outer:
        matches = [item for item in outer.getmembers() if item.name == "homeassistant.tar.gz"]
        assert len(matches) == 1 and matches[0].isfile() and not matches[0].islnk()
        encrypted_inner = outer.extractfile(matches[0])
        assert encrypted_inner is not None
        with SecureTarFile(fileobj=encrypted_inner, gzip=True, password=password) as inner:
            # SecureTarFile's decrypted gzip reader is forward-only. Enumerate
            # and consume each member before advancing; getmembers() exhausts
            # the stream and makes subsequent extractfile() seek backwards.
            for member in inner:
                destination_kind = _family_member(member, store_name, media_prefix, seen)
                if destination_kind is None or destination_kind == "directory":
                    continue
                source = inner.extractfile(member)
                assert source is not None
                content = source.read()
                if destination_kind == "store":
                    store_content = content
                    continue
                relative_name = destination_kind.as_posix()
                media_manifest[relative_name] = (
                    len(content),
                    sha256(content).hexdigest(),
                )
                destination = output.joinpath(*destination_kind.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)

    assert store_content is not None
    return store_content, media_manifest


async def verify_encrypted_archive(hass, entry, owner, media_expected) -> None:
    """Create, decrypt, read, and delete one real synthetic encrypted HA archive."""
    from ha_backup_smoke import _restored_copy_reads
    from homeassistant.components.backup import async_get_manager
    from homeassistant.components.backup.util import read_backup, validate_password

    from custom_components.family_assistant.const import DOMAIN

    assert owner.is_admin
    assert isinstance(media_expected, dict) and media_expected.get("records")
    manager = async_get_manager(hass)
    assert manager.state.value == "idle"
    assert LOCAL_AGENT in manager.local_backup_agents

    existing, agent_errors = await manager.async_get_backups()
    assert not agent_errors and not existing

    runtime = entry.runtime_data
    state_before = runtime.engine.snapshot()
    store_path = Path(hass.config.path(".storage", f"{DOMAIN}.{entry.entry_id}"))
    media_root = runtime.media.root
    assert store_path.is_file() and not store_path.is_symlink()
    assert media_root.is_dir() and not media_root.is_symlink()
    store_before = store_path.read_bytes()
    media_before = _manifest(media_root)
    assert media_before

    original_config = await _backup_config(hass, owner, 2100)
    original_config_fingerprint = _config_fingerprint(original_config)
    original_local = original_config["agents"].get(LOCAL_AGENT)
    original_protected = original_local["protected"] if original_local else None
    protection_changed = original_protected is False
    backup_id = None
    archive = None
    synthetic_password = secrets.token_urlsafe(32)

    try:
        if protection_changed:
            await _set_local_protected(hass, owner, 2101, True)
        effective = await _backup_config(hass, owner, 2102)
        assert effective["agents"].get(LOCAL_AGENT, {}).get("protected", True) is True

        created = await manager.async_initiate_backup(
            agent_ids=[LOCAL_AGENT],
            include_addons=None,
            include_all_addons=False,
            include_database=False,
            include_folders=None,
            include_homeassistant=True,
            name="Family Assistant encrypted acceptance",
            password=synthetic_password,
            raise_task_error=True,
        )
        backup_id = created.backup_job_id
        # HA 2026.8.2 exposes no public await-by-job-id API. Retain its exact owned
        # task so timeout cancellation is settled instead of leaving work detached.
        finish_task = manager._backup_finish_task
        assert finish_task is not None
        await asyncio.wait_for(finish_task, MANAGER_TIMEOUT)
        assert manager._backup_finish_task is None
        assert manager._backup_task is None
        assert manager.state.value == "idle"
        assert not hass.data[DOMAIN].get("backup")

        local_agent = manager.local_backup_agents[LOCAL_AGENT]
        archive = Path(local_agent.get_backup_path(backup_id)).resolve()
        assert archive.is_relative_to(Path(hass.config.path()).resolve())
        assert archive.is_file() and not archive.is_symlink()
        assert synthetic_password.encode() not in archive.read_bytes()

        effective_after = await _backup_config(hass, owner, 2105)
        assert synthetic_password not in json.dumps(
            effective_after, sort_keys=True, separators=(",", ":")
        )

        parsed = read_backup(archive)
        assert parsed.backup_id == backup_id
        assert parsed.protected is True
        assert parsed.homeassistant_included is True
        assert parsed.database_included is False
        details, detail_errors = await manager.async_get_backup(backup_id)
        assert not detail_errors and details is not None
        assert details.agents[LOCAL_AGENT].protected is True

        assert validate_password(archive, None) is False
        assert validate_password(archive, synthetic_password + "-wrong") is False
        assert validate_password(archive, synthetic_password) is True

        with tempfile.TemporaryDirectory(prefix="family-encrypted-archive-") as temporary:
            extracted = Path(temporary)
            media_copy = extracted / "private-media"
            media_copy.mkdir()
            archived_store, archived_media = _read_family_files(
                archive,
                synthetic_password,
                entry.entry_id,
                media_copy,
            )
            assert archived_store == store_before
            assert archived_media == media_before
            envelope = json.loads(archived_store)
            assert envelope["data"] == state_before

            store_copy = extracted / "family-store.json"
            store_copy.write_bytes(archived_store)
            restored = extracted / "restored-ha"
            await _restored_copy_reads(
                restored,
                entry,
                owner,
                media_expected,
                store_copy,
                media_copy,
                state_before,
            )
    finally:
        cleanup_failure = None
        try:
            if backup_id is not None:
                errors = await asyncio.wait_for(
                    manager.async_delete_backup(backup_id, agent_ids=[LOCAL_AGENT]),
                    MANAGER_TIMEOUT,
                )
                assert errors == {}
                if archive is not None:
                    assert not archive.exists()
        except BaseException as err:
            cleanup_failure = err
        try:
            if protection_changed:
                await _set_local_protected(hass, owner, 2103, False)
        except BaseException as err:
            if cleanup_failure is None:
                cleanup_failure = err
        try:
            restored_config = await _backup_config(hass, owner, 2104)
            assert _config_fingerprint(restored_config) == original_config_fingerprint
            assert manager.state.value == "idle"
            assert manager._backup_finish_task is None
            assert manager._backup_task is None
            assert not hass.data[DOMAIN].get("backup")
        except BaseException as err:
            if cleanup_failure is None:
                cleanup_failure = err
        if cleanup_failure is not None:
            raise AssertionError(
                "synthetic encrypted backup cleanup or rollback failed"
            ) from cleanup_failure

    assert runtime.engine.snapshot() == state_before
    assert store_path.read_bytes() == store_before
    assert _manifest(media_root) == media_before
    token = await runtime.media.async_pause_backup()
    await runtime.media.async_resume_backup(token)
    print(
        "PASS: actual HA encrypted archive rejects wrong keys and rehydrates exact "
        "synthetic Family Assistant Store/media bytes"
    )
