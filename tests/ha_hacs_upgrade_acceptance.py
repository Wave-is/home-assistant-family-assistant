"""Actual-HA helper for the pinned, offline HACS upgrade acceptance gate."""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import logging
import traceback
import zipfile
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from aiohttp import ClientSession
from awesomeversion import AwesomeVersion
from ha_upgrade_acceptance import prepare as prepare_family
from ha_upgrade_acceptance import verify as verify_family
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.setup import async_setup_component

# HACS normalizes GitHub repository names to lowercase at registration.
REPOSITORY = "wave-is/home-assistant-family-assistant"
REPOSITORY_ID = "987654321"
HACS_VERSION = "2.0.5"
HACS_JSON = {"name": "Family Assistant", "homeassistant": "2026.8.0"}


class _TreeItem:
    def __init__(self, full_path: str, directory: bool, content: bytes | None = None):
        path = PurePosixPath(full_path)
        self.full_path = full_path
        self.filename = path.name
        self.path = path.parent.as_posix() if len(path.parts) > 1 else ""
        self.is_directory = directory
        self.download_url = f"https://download.invalid/{full_path}"
        self.content = content


def _artifact(path: Path) -> tuple[dict[str, bytes], str]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise AssertionError("runtime artifact is corrupt")
            names = archive.namelist()
            prefix = "custom_components/family_assistant/"
            if not names or any(
                name.endswith("/") or not name.startswith(prefix) for name in names
            ):
                raise AssertionError("runtime artifact layout is invalid")
            files = {name: archive.read(name) for name in names}
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise AssertionError("runtime artifact is unavailable") from error
    try:
        manifest = json.loads(files[prefix + "manifest.json"])
        version = manifest["version"]
    except (KeyError, TypeError, ValueError) as error:
        raise AssertionError("runtime manifest is invalid") from error
    if not isinstance(version, str) or not version:
        raise AssertionError("runtime version is invalid")
    return files, version


def _repository_tree(files: dict[str, bytes]) -> list[_TreeItem]:
    directories = {"custom_components", "custom_components/family_assistant"}
    for name in files:
        parts = PurePosixPath(name).parts
        for index in range(1, len(parts)):
            directories.add(PurePosixPath(*parts[:index]).as_posix())
    result = [_TreeItem("hacs.json", False, json.dumps(HACS_JSON).encode())]
    result.append(_TreeItem("README.md", False, b"Synthetic offline HACS lab"))
    result.extend(_TreeItem(name, True) for name in sorted(directories))
    result.extend(_TreeItem(name, False, content) for name, content in sorted(files.items()))
    return result


def _tag_archive(files: dict[str, bytes], version: str) -> bytes:
    target = io.BytesIO()
    root = f"home-assistant-family-assistant-{version}/"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(root + "hacs.json", json.dumps(HACS_JSON))
        archive.writestr(root + "README.md", "Synthetic offline HACS lab")
        for name, content in sorted(files.items()):
            archive.writestr(root + name, content)
    return target.getvalue()


class _RepositoryObject:
    def __init__(self, version: str, tree: list[_TreeItem]):
        self.full_name = REPOSITORY
        self.last_commit = version
        self._tree = tree
        self.attributes = {
            "id": REPOSITORY_ID,
            "full_name": REPOSITORY,
            "default_branch": "main",
            "description": "Synthetic offline Family Assistant repository",
            "pushed_at": "2026-09-07T00:00:00Z",
            "archived": False,
            "fork": False,
        }

    async def get_tree(self, _ref):
        return self._tree

    async def set_last_commit(self):
        return None


class _LegacyGitHub:
    def __init__(self, repository: _RepositoryObject, version: str):
        self.repository = repository
        self.client = SimpleNamespace(last_response=SimpleNamespace(etag=version))

    async def get_repo(self, full_name, _etag=None):
        if full_name != REPOSITORY:
            raise AssertionError("unexpected repository lookup")
        return self.repository


class _Contents:
    def __init__(self, files: dict[str, bytes]):
        self.files = files

    async def get(self, *, repository, path, **_kwargs):
        if repository != REPOSITORY:
            raise AssertionError("unexpected repository content lookup")
        if path == "hacs.json":
            content = json.dumps(HACS_JSON).encode()
        else:
            try:
                content = self.files[path]
            except KeyError as error:
                raise AssertionError("unexpected repository content path") from error
        encoded = base64.b64encode(content).decode("ascii")
        return SimpleNamespace(data=SimpleNamespace(content=encoded))


class _Releases:
    def __init__(self, version: str):
        self.version = version

    async def list(self, *, repository, **_kwargs):
        if repository != REPOSITORY:
            raise AssertionError("unexpected releases lookup")
        release = SimpleNamespace(
            tag_name=self.version,
            name=self.version,
            body="",
            draft=False,
            prerelease=True,
            assets=[],
        )
        return SimpleNamespace(data=[release])


class _GitHubAPI:
    def __init__(self, files: dict[str, bytes], version: str):
        self.repos = SimpleNamespace(
            contents=_Contents(files),
            releases=_Releases(version),
        )


class _Transport:
    def __init__(self, files: dict[str, bytes], version: str, *, fail: bool):
        self.files = files
        self.version = version
        self.fail = fail
        self.tree = _repository_tree(files)
        self.archive = _tag_archive(files, version)
        self.urls: list[str] = []

    async def download(self, url, **_kwargs):
        self.urls.append(url)
        tag = f"https://github.com/{REPOSITORY}/archive/refs/tags/{self.version}.zip"
        head = f"https://github.com/{REPOSITORY}/archive/refs/heads/{self.version}.zip"
        if url == tag:
            return None if self.fail else self.archive
        if url == head:
            return None
        if url.startswith("https://raw.githubusercontent.com/"):
            if url.endswith("/hacs.json"):
                return json.dumps(HACS_JSON).encode()
            if url.endswith("/README.md"):
                return b"Synthetic offline HACS lab"
        if url.startswith("https://download.invalid/"):
            if self.fail:
                return None
            name = url.removeprefix("https://download.invalid/")
            if name in self.files:
                return self.files[name]
        raise AssertionError("unexpected external transport URL")


class _ExceptionObserver(logging.Handler):
    """Retain only exception objects, never log messages or authentication data."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.errors = []

    def emit(self, record):
        if record.exc_info and isinstance(record.exc_info[1], Exception):
            self.errors.append(record.exc_info[1])


async def _start(config: Path):
    from ha_upgrade_acceptance import _start as start

    return await start(config)


async def _hacs(hass, transport: _Transport):
    from custom_components.hacs.base import HacsBase
    from custom_components.hacs.enums import HacsCategory
    from custom_components.hacs.utils.data import HacsData
    from custom_components.hacs.utils.queue_manager import QueueManager
    from custom_components.hacs.websocket import async_register_websocket_commands

    if not await async_setup_component(hass, "websocket_api", {}):
        raise AssertionError("websocket_api setup failed")
    hacs = HacsBase()
    hacs.hass = hass
    hacs.core.config_path = hass.config.path()
    hacs.core.ha_version = AwesomeVersion(HA_VERSION)
    hacs.version = AwesomeVersion(HACS_VERSION)
    hacs.queue = QueueManager(hass=hass)
    hacs.github = _LegacyGitHub(
        _RepositoryObject(transport.version, transport.tree), transport.version
    )
    hacs.githubapi = _GitHubAPI(transport.files, transport.version)
    hacs.async_download_file = transport.download
    # OAuth/config-entry bootstrap is intentionally outside this offline gate.
    # The installer invokes this unrelated HACS update-entity refresh after a
    # first download; record it instead of forwarding a nonexistent HACS entry.
    # Family Assistant's own loaded entities/resources are checked in later phases.
    hacs.lab_update_entity_refreshes = 0

    async def record_update_entity_refresh():
        hacs.lab_update_entity_refreshes += 1

    hacs.async_recreate_entities = record_update_entity_refresh
    hacs.enable_hacs_category(HacsCategory.INTEGRATION)
    hacs.status.startup = False
    hacs.system.running = True
    hacs.data = HacsData(hacs)
    if not await hacs.data.restore():
        raise AssertionError("HACS repository state restore failed")
    hass.data["hacs"] = hacs
    async_register_websocket_commands(hass)
    return hacs


async def _admin_command(hass, command: dict) -> dict:
    user = await hass.auth.async_create_user("Synthetic HACS lab admin", group_ids=[GROUP_ID_ADMIN])
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://hacs-lab.invalid/client"
    )
    token = hass.auth.async_create_access_token(refresh)
    try:
        async with ClientSession() as client:
            async with client.ws_connect("http://127.0.0.1:8123/api/websocket") as socket:
                if (await socket.receive_json()).get("type") != "auth_required":
                    raise AssertionError("HA WebSocket did not request authentication")
                await socket.send_json({"type": "auth", "access_token": token})
                if (await socket.receive_json()).get("type") != "auth_ok":
                    raise AssertionError("HA WebSocket admin authentication failed")
                await socket.send_json({"id": 1, **command})
                return await socket.receive_json()
    finally:
        hass.auth.async_remove_refresh_token(refresh)


def _installed(config: Path) -> dict[str, bytes]:
    root = config / "custom_components" / "family_assistant"
    if root.is_symlink() or not root.is_dir():
        raise AssertionError("Family Assistant runtime is not installed")
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AssertionError("HACS-installed runtime contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise AssertionError("HACS-installed runtime contains a special file")
        result[f"custom_components/family_assistant/{path.relative_to(root).as_posix()}"] = (
            path.read_bytes()
        )
    return result


def _verify_runtime(actual: dict[str, bytes], expected: dict[str, bytes]) -> None:
    # Separate structural failures without disclosing contents in lab output.
    if expected.keys() - actual.keys():
        raise AssertionError("validated runtime files are missing")
    if actual.keys() - expected.keys():
        raise AssertionError("unvalidated runtime files were installed")
    manifest = "custom_components/family_assistant/manifest.json"
    if actual[manifest] != expected[manifest]:
        raise AssertionError("installed manifest bytes changed")
    if actual != expected:
        raise AssertionError("installed runtime bytes changed")


async def _install_or_update(
    config: Path, artifact: Path, expected_version: str, *, fail: bool, first: bool
) -> None:
    files, version = _artifact(artifact)
    if version != expected_version:
        raise AssertionError("artifact version does not match requested HACS version")
    before = _installed(config) if not first else None
    hass = await _start(config)
    try:
        transport = _Transport(files, version, fail=fail)
        hacs = await _hacs(hass, transport)
        if first:
            registration_errors = []
            register = hacs.async_register_repository

            async def observe_registration(*args, **kwargs):
                try:
                    return await register(*args, **kwargs)
                except Exception as error:
                    # HACS reports registration exceptions through its event
                    # dispatcher but still returns WS success. Observe without
                    # changing its real registration behavior or error handling.
                    registration_errors.append(error)
                    raise

            hacs.async_register_repository = observe_registration
            added = await _admin_command(
                hass,
                {
                    "type": "hacs/repositories/add",
                    "repository": REPOSITORY,
                    "category": "integration",
                },
            )
            hacs.async_register_repository = register
            if registration_errors:
                raise registration_errors[0]
            if not added.get("success"):
                raise AssertionError("HACS custom repository registration failed")
        repository = hacs.repositories.get_by_full_name(REPOSITORY)
        if repository is None:
            raise AssertionError("HACS custom repository is unavailable")
        download_errors = []
        download = repository.async_download_repository

        async def observe_download(*args, **kwargs):
            try:
                return await download(*args, **kwargs)
            except Exception as error:
                download_errors.append(error)
                raise

        repository.async_download_repository = observe_download
        observer = _ExceptionObserver()
        websocket_logger = logging.getLogger("homeassistant.components.websocket_api")
        websocket_logger.addHandler(observer)
        try:
            response = await _admin_command(
                hass,
                {
                    "type": "hacs/repository/download",
                    "repository": str(repository.data.id),
                    "version": version,
                },
            )
        finally:
            websocket_logger.removeHandler(observer)
        repository.async_download_repository = download
        if download_errors and not fail:
            raise download_errors[0]
        if not response.get("success") and observer.errors:
            raise observer.errors[-1]
        if fail:
            if response.get("success") is not False:
                raise AssertionError("failed HACS update unexpectedly succeeded")
            if _installed(config) != before:
                raise AssertionError("HACS did not restore the exact baseline runtime")
            if repository.data.installed_version == version:
                raise AssertionError("failed HACS update advanced installed version")
        else:
            if not response.get("success"):
                raise AssertionError("HACS repository download failed")
            _verify_runtime(_installed(config), files)
            if repository.data.installed_version != version:
                raise AssertionError("HACS installed-version state did not advance")
            if first and hacs.lab_update_entity_refreshes != 1:
                raise AssertionError("HACS first-install update-entity refresh was not requested")
            await hacs.data.async_write(force=True)
        if not transport.urls or any("test.invalid" in value for value in transport.urls):
            raise AssertionError("HACS transport evidence is incomplete")
    finally:
        await hass.async_stop(force=True)


async def _run(arguments: argparse.Namespace) -> None:
    config = arguments.config.resolve(strict=True)
    artifact = arguments.artifact.resolve(strict=True)
    if arguments.phase == "install":
        await _install_or_update(
            config, artifact, arguments.expected_version, fail=False, first=True
        )
        return
    if arguments.phase == "prepare":
        contract = await prepare_family(config, arguments.expected_version)
        with arguments.contract.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(contract, target, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            target.write("\n")
        return
    if arguments.phase == "rollback":
        await _install_or_update(
            config, artifact, arguments.expected_version, fail=True, first=False
        )
        return
    if arguments.phase == "upgrade":
        await _install_or_update(
            config, artifact, arguments.expected_version, fail=False, first=False
        )
        return
    try:
        contract = json.loads(arguments.contract.read_bytes())
    except (OSError, TypeError, ValueError) as error:
        raise AssertionError("upgrade contract could not be read") from error
    await verify_family(config, arguments.expected_version, contract)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("install", "prepare", "rollback", "upgrade", "verify"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--failure-report", required=True, type=Path)
    return parser.parse_args()


def _write_failure(path: Path, error: BaseException) -> None:
    # Wrapped transport errors otherwise erase the original failing frame.
    # Follow only a bounded explicit cause chain, still without any messages.
    seen = set()
    for _ in range(4):
        if error.__cause__ is None or id(error) in seen:
            break
        seen.add(id(error))
        error = error.__cause__
    frames = [
        {
            "file": Path(frame.filename).name[:80],
            "function": "".join(
                character if character.isalnum() or character == "_" else "_"
                for character in frame.name[:80]
            ),
            "line": frame.lineno,
        }
        for frame in traceback.extract_tb(error.__traceback__)[-8:]
    ]
    report = {
        "class": type(error).__name__,
        "frames": frames or [{"file": Path(__file__).name, "function": "main", "line": 1}],
    }
    try:
        with path.open("x", encoding="ascii", newline="\n") as target:
            json.dump(report, target, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            target.write("\n")
    except OSError:
        pass


def main() -> None:
    arguments = _arguments()
    try:
        asyncio.run(_run(arguments))
    except BaseException as error:
        _write_failure(arguments.failure_report, error)
        raise


if __name__ == "__main__":
    main()
