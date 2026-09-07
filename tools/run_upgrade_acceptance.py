"""Run the two-process packaged upgrade gate inside an isolated HA container."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

if __package__:
    from .build_release import DOMAIN_PATH, VERSION, build
else:
    from build_release import DOMAIN_PATH, VERSION, build

DEFAULT_TIMEOUT = 300
MAX_TIMEOUT = 900
MARKER = ".family-assistant-upgrade-owned"
PREFIX = "family-assistant-upgrade-"
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class UpgradeAcceptanceError(ValueError):
    """Fixed, non-sensitive upgrade runner failure."""


@dataclass(frozen=True)
class Artifact:
    version: str
    content: bytes


def _reparse(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0) & REPARSE_POINT
    )


def _repository(value: Path, label: str) -> Path:
    if not value.is_absolute():
        raise UpgradeAcceptanceError(f"{label}_path_not_absolute")
    try:
        source = os.stat(value, follow_symlinks=False)
        absolute = value.absolute()
        resolved = value.resolve(strict=True)
    except OSError as error:
        raise UpgradeAcceptanceError(f"{label}_unavailable") from error
    if absolute != resolved or _reparse(source) or not stat.S_ISDIR(source.st_mode):
        raise UpgradeAcceptanceError(f"{label}_unsafe")
    return resolved


def _manifest_version(root: Path, label: str) -> str:
    manifest = root / DOMAIN_PATH / "manifest.json"
    try:
        value = os.stat(manifest, follow_symlinks=False)
        resolved = manifest.resolve(strict=True)
        if (
            _reparse(value)
            or not stat.S_ISREG(value.st_mode)
            or not resolved.is_relative_to(root)
            or value.st_size > 64 * 1024
        ):
            raise UpgradeAcceptanceError(f"{label}_manifest_unsafe")
        parsed = json.loads(manifest.read_bytes())
    except UpgradeAcceptanceError:
        raise
    except (OSError, TypeError, ValueError) as error:
        raise UpgradeAcceptanceError(f"{label}_manifest_invalid") from error
    version = parsed.get("version") if isinstance(parsed, dict) else None
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        raise UpgradeAcceptanceError(f"{label}_manifest_invalid")
    return version


def _artifact(root: Path, label: str) -> Artifact:
    version = _manifest_version(root, label)
    try:
        content, report = build(root, version)
    except (OSError, TypeError, ValueError) as error:
        raise UpgradeAcceptanceError(f"{label}_artifact_invalid") from error
    if report.get("version") != version or not content:
        raise UpgradeAcceptanceError(f"{label}_artifact_invalid")
    return Artifact(version, content)


def _owned_root(path: Path, token: str) -> Path:
    temporary = Path(tempfile.gettempdir()).resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
        marker = resolved / MARKER
        marker_value = marker.read_text(encoding="ascii")
    except OSError as error:
        raise UpgradeAcceptanceError("temporary_directory_unowned") from error
    if (
        resolved.parent != temporary
        or not resolved.name.startswith(PREFIX)
        or marker_value != token
        or marker.is_symlink()
    ):
        raise UpgradeAcceptanceError("temporary_directory_unowned")
    return resolved


def _safe_target(root: Path, target: Path) -> Path:
    root = root.resolve(strict=True)
    expected = root / "config" / DOMAIN_PATH
    try:
        parent = target.parent.resolve(strict=True)
    except OSError as error:
        raise UpgradeAcceptanceError("runtime_target_unsafe") from error
    if target.absolute() != expected or not parent.is_relative_to(root):
        raise UpgradeAcceptanceError("runtime_target_unsafe")
    return target


def _install(content: bytes, config: Path) -> None:
    """Install only the validated runtime root from an in-memory artifact."""
    prefix = f"{DOMAIN_PATH.as_posix()}/"
    runtime = config / DOMAIN_PATH
    runtime.parent.mkdir(parents=True, exist_ok=True)
    if runtime.exists() or runtime.is_symlink():
        raise UpgradeAcceptanceError("runtime_target_exists")
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if archive.testzip() is not None:
                raise UpgradeAcceptanceError("artifact_corrupt")
            for info in archive.infolist():
                name = info.filename
                relative = PurePosixPath(name)
                if (
                    info.is_dir()
                    or name in seen
                    or "\\" in name
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or not name.startswith(prefix)
                ):
                    raise UpgradeAcceptanceError("artifact_structure_invalid")
                seen.add(name)
                target = config.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.parent.resolve(strict=True).is_relative_to(config):
                    raise UpgradeAcceptanceError("artifact_structure_invalid")
                with target.open("xb") as stream:
                    stream.write(archive.read(info))
    except UpgradeAcceptanceError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise UpgradeAcceptanceError("artifact_install_failed") from error
    if not seen:
        raise UpgradeAcceptanceError("artifact_structure_invalid")


def _remove_runtime(owned: Path, config: Path) -> None:
    target = _safe_target(owned, config / DOMAIN_PATH)
    try:
        value = os.stat(target, follow_symlinks=False)
        resolved = target.resolve(strict=True)
    except OSError as error:
        raise UpgradeAcceptanceError("runtime_target_unsafe") from error
    if _reparse(value) or not stat.S_ISDIR(value.st_mode) or not resolved.is_relative_to(owned):
        raise UpgradeAcceptanceError("runtime_target_unsafe")
    shutil.rmtree(resolved)


def _helper(candidate: Path) -> Path:
    helper = candidate / "tests" / "ha_upgrade_acceptance.py"
    try:
        value = os.stat(helper, follow_symlinks=False)
        resolved = helper.resolve(strict=True)
    except OSError as error:
        raise UpgradeAcceptanceError("candidate_helper_unavailable") from error
    if _reparse(value) or not stat.S_ISREG(value.st_mode) or not resolved.is_relative_to(candidate):
        raise UpgradeAcceptanceError("candidate_helper_unsafe")
    return resolved


def _phase(
    phase: str,
    helper: Path,
    config: Path,
    contract: Path,
    version: str,
    timeout: int,
) -> None:
    command = [
        sys.executable,
        str(helper),
        phase,
        "--config",
        str(config),
        "--contract",
        str(contract),
        "--expected-version",
        version,
    ]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        result = subprocess.run(  # noqa: S603 -- fixed interpreter and reviewed helper
            command,
            cwd=config,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise UpgradeAcceptanceError(f"{phase}_timeout") from error
    except OSError as error:
        raise UpgradeAcceptanceError(f"{phase}_unavailable") from error
    if result.returncode:
        raise UpgradeAcceptanceError(f"{phase}_failed")


def _cleanup(path: Path, token: str) -> None:
    owned = _owned_root(path, token)
    shutil.rmtree(owned)


def run(baseline: Path, candidate: Path, timeout: int = DEFAULT_TIMEOUT) -> dict[str, str]:
    """Run baseline and candidate helpers without importing either integration."""
    if type(timeout) is not int or not 30 <= timeout <= MAX_TIMEOUT:
        raise UpgradeAcceptanceError("invalid_timeout")
    baseline = _repository(baseline, "baseline")
    candidate = _repository(candidate, "candidate")
    baseline_artifact = _artifact(baseline, "baseline")
    candidate_artifact = _artifact(candidate, "candidate")
    if baseline_artifact.version == candidate_artifact.version:
        raise UpgradeAcceptanceError("versions_not_distinct")
    helper = _helper(candidate)

    directory = Path(tempfile.mkdtemp(prefix=PREFIX)).resolve(strict=True)
    token = uuid.uuid4().hex
    (directory / MARKER).write_text(token, encoding="ascii", newline="\n")
    try:
        owned = _owned_root(directory, token)
        config = owned / "config"
        config.mkdir()
        contract = owned / "contract.json"
        _install(baseline_artifact.content, config)
        _phase(
            "prepare",
            helper,
            config,
            contract,
            baseline_artifact.version,
            timeout,
        )
        _remove_runtime(owned, config)
        _install(candidate_artifact.content, config)
        _phase(
            "verify",
            helper,
            config,
            contract,
            candidate_artifact.version,
            timeout,
        )
        return {
            "baseline_version": baseline_artifact.version,
            "candidate_version": candidate_artifact.version,
            "baseline_sha256": hashlib.sha256(baseline_artifact.content).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate_artifact.content).hexdigest(),
        }
    finally:
        _cleanup(directory, token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT)
    arguments = parser.parse_args()
    report = run(arguments.baseline, arguments.candidate, arguments.timeout_seconds)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
