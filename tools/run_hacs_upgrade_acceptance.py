"""Run a pinned, offline HACS install and upgrade acceptance gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

if __package__:
    from .run_upgrade_acceptance import (
        DEFAULT_TIMEOUT,
        MAX_TIMEOUT,
        Artifact,
        UpgradeAcceptanceError,
        _artifact,
        _repository,
    )
else:
    from run_upgrade_acceptance import (  # type: ignore[no-redef]
        DEFAULT_TIMEOUT,
        MAX_TIMEOUT,
        Artifact,
        UpgradeAcceptanceError,
        _artifact,
        _repository,
    )

HACS_VERSION = "2.0.5"
HACS_COMMIT = "c0dfd8b44297c3673c21973e2539375a53687a9c"
HACS_SHA256 = "97be6b824a4f38e683728cc6dd72367f6b8bad0a43428b1b3b987a3087adf413"
AIOGITHUBAPI_VERSION = "22.10.1"
AIOGITHUBAPI_SHA256 = "d5f722090545d033e022692fbe09d72c68a86b53e4de69cca1d500abd1388252"
MARKER = ".family-assistant-hacs-lab-owned"
PREFIX = "family-assistant-hacs-lab-"
MAX_HACS_ARCHIVE = 64 * 1024 * 1024
MAX_HACS_EXPANDED = 256 * 1024 * 1024
MAX_HACS_FILES = 20_000
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
MAX_FAILURE_REPORT = 8 * 1024


def _reparse(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0) & REPARSE_POINT
    )


def _input_file(path: Path, label: str, maximum: int, expected_hash: str) -> Path:
    if not path.is_absolute():
        raise UpgradeAcceptanceError(f"{label}_path_not_absolute")
    try:
        value = os.stat(path, follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise UpgradeAcceptanceError(f"{label}_unavailable") from error
    if (
        path.absolute() != resolved
        or _reparse(value)
        or not stat.S_ISREG(value.st_mode)
        or not 0 < value.st_size <= maximum
    ):
        raise UpgradeAcceptanceError(f"{label}_unsafe")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if digest != expected_hash:
        raise UpgradeAcceptanceError(f"{label}_hash_mismatch")
    return resolved


def _members(archive: zipfile.ZipFile, *, flat: bool) -> list[zipfile.ZipInfo]:
    result: list[zipfile.ZipInfo] = []
    names: set[str] = set()
    total = 0
    for info in archive.infolist():
        name = info.filename
        path = PurePosixPath(name)
        mode = info.external_attr >> 16
        if (
            not name
            or name in names
            or "\\" in name
            or path.is_absolute()
            or ".." in path.parts
            or (mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})
        ):
            raise UpgradeAcceptanceError("dependency_archive_unsafe")
        names.add(name)
        if info.is_dir():
            continue
        if flat and len(path.parts) != 1 and path.parts[0] in {"custom_components", "hacs"}:
            raise UpgradeAcceptanceError("hacs_archive_layout_invalid")
        total += info.file_size
        result.append(info)
        if len(result) > MAX_HACS_FILES or total > MAX_HACS_EXPANDED:
            raise UpgradeAcceptanceError("dependency_archive_too_large")
    if archive.testzip() is not None:
        raise UpgradeAcceptanceError("dependency_archive_corrupt")
    return result


def _validate_hacs(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            files = _members(archive, flat=True)
            names = {item.filename for item in files}
            if not {"__init__.py", "manifest.json"} <= names:
                raise UpgradeAcceptanceError("hacs_archive_layout_invalid")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("domain") != "hacs":
                raise UpgradeAcceptanceError("hacs_archive_layout_invalid")
    except UpgradeAcceptanceError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise UpgradeAcceptanceError("hacs_archive_invalid") from error


def _validate_wheel(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            files = _members(archive, flat=False)
            metadata = [item for item in files if item.filename.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise UpgradeAcceptanceError("wheel_layout_invalid")
            headers = archive.read(metadata[0]).decode("utf-8", "strict").splitlines()
            if "Name: aiogithubapi" not in headers or (
                f"Version: {AIOGITHUBAPI_VERSION}" not in headers
            ):
                raise UpgradeAcceptanceError("wheel_version_invalid")
    except UpgradeAcceptanceError:
        raise
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
        raise UpgradeAcceptanceError("wheel_invalid") from error


def _owned(path: Path, token: str) -> Path:
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
        or marker.is_symlink()
        or marker_value != token
    ):
        raise UpgradeAcceptanceError("temporary_directory_unowned")
    return resolved


def _extract_hacs(source: Path, owned: Path) -> None:
    target = owned / "config" / "custom_components" / "hacs"
    target.mkdir(parents=True)
    try:
        with zipfile.ZipFile(source) as archive:
            for info in _members(archive, flat=True):
                relative = PurePosixPath(info.filename)
                destination = target.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.parent.resolve(strict=True).is_relative_to(target):
                    raise UpgradeAcceptanceError("hacs_archive_layout_invalid")
                with destination.open("xb") as stream:
                    stream.write(archive.read(info))
    except UpgradeAcceptanceError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise UpgradeAcceptanceError("hacs_install_failed") from error


def _write_artifact(owned: Path, name: str, artifact: Artifact) -> Path:
    target = owned / name
    try:
        with target.open("xb") as stream:
            stream.write(artifact.content)
    except OSError as error:
        raise UpgradeAcceptanceError("artifact_install_failed") from error
    return target


def _phase(
    helper: Path,
    phase: str,
    config: Path,
    contract: Path,
    artifact: Path,
    version: str,
    wheel: Path,
    timeout: int,
) -> None:
    failure_report = config.parent / f"failure-{phase}.json"
    command = [
        sys.executable,
        str(helper),
        phase,
        "--config",
        str(config),
        "--contract",
        str(contract),
        "--artifact",
        str(artifact),
        "--expected-version",
        version,
        "--failure-report",
        str(failure_report),
    ]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join([str(wheel), *([existing] if existing else [])])
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
        raise UpgradeAcceptanceError(f"hacs_{phase}_timeout") from error
    except OSError as error:
        raise UpgradeAcceptanceError(f"hacs_{phase}_unavailable") from error
    if result.returncode:
        raise UpgradeAcceptanceError(f"hacs_{phase}_failed{_failure_detail(failure_report)}")


def _failure_detail(path: Path) -> str:
    """Return only the helper's bounded structural traceback marker."""
    try:
        value = os.stat(path, follow_symlinks=False)
        if _reparse(value) or not stat.S_ISREG(value.st_mode) or value.st_size > MAX_FAILURE_REPORT:
            return ""
        report = json.loads(path.read_bytes())
    except (OSError, TypeError, ValueError):
        return ""
    if not isinstance(report, dict) or set(report) != {"class", "frames"}:
        return ""
    error_class = report.get("class")
    frames = report.get("frames")
    if (
        not isinstance(error_class, str)
        or not error_class.isidentifier()
        or not isinstance(frames, list)
        or not 1 <= len(frames) <= 8
    ):
        return ""
    rendered = []
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"file", "function", "line"}:
            return ""
        filename = frame.get("file")
        function = frame.get("function")
        line = frame.get("line")
        if (
            not isinstance(filename, str)
            or not filename
            or len(filename) > 80
            or "/" in filename
            or "\\" in filename
            or not isinstance(function, str)
            or not function
            or len(function) > 80
            or not all(character.isalnum() or character == "_" for character in function)
            or type(line) is not int
            or not 1 <= line <= 1_000_000
        ):
            return ""
        rendered.append(f"{filename}:{function}:{line}")
    return f"[{error_class}@{'|'.join(rendered)}]"


def run(
    baseline: Path,
    candidate: Path,
    hacs_archive: Path,
    aiogithubapi_wheel: Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, str]:
    """Exercise real HACS installer code against exact validated runtime bytes."""
    if type(timeout) is not int or not 30 <= timeout <= MAX_TIMEOUT:
        raise UpgradeAcceptanceError("invalid_timeout")
    baseline = _repository(baseline, "baseline")
    candidate = _repository(candidate, "candidate")
    hacs_archive = _input_file(hacs_archive, "hacs_archive", MAX_HACS_ARCHIVE, HACS_SHA256)
    wheel = _input_file(
        aiogithubapi_wheel,
        "aiogithubapi_wheel",
        4 * 1024 * 1024,
        AIOGITHUBAPI_SHA256,
    )
    _validate_hacs(hacs_archive)
    _validate_wheel(wheel)
    baseline_artifact = _artifact(baseline, "baseline")
    candidate_artifact = _artifact(candidate, "candidate")
    if baseline_artifact.version == candidate_artifact.version:
        raise UpgradeAcceptanceError("versions_not_distinct")
    helper = candidate / "tests" / "ha_hacs_upgrade_acceptance.py"
    if (
        not helper.is_file()
        or helper.is_symlink()
        or not helper.resolve().is_relative_to(candidate)
    ):
        raise UpgradeAcceptanceError("candidate_helper_unsafe")

    directory = Path(tempfile.mkdtemp(prefix=PREFIX)).resolve(strict=True)
    token = uuid.uuid4().hex
    (directory / MARKER).write_text(token, encoding="ascii", newline="\n")
    try:
        owned = _owned(directory, token)
        config = owned / "config"
        config.mkdir()
        _extract_hacs(hacs_archive, owned)
        baseline_zip = _write_artifact(owned, "baseline-runtime.zip", baseline_artifact)
        candidate_zip = _write_artifact(owned, "candidate-runtime.zip", candidate_artifact)
        contract = owned / "contract.json"
        for phase, artifact, version in (
            ("install", baseline_zip, baseline_artifact.version),
            ("prepare", baseline_zip, baseline_artifact.version),
            ("rollback", candidate_zip, candidate_artifact.version),
            ("upgrade", candidate_zip, candidate_artifact.version),
            ("verify", candidate_zip, candidate_artifact.version),
        ):
            _phase(helper, phase, config, contract, artifact, version, wheel, timeout)
            print(f"PASS: offline HACS phase {phase}", flush=True)
        return {
            "baseline_version": baseline_artifact.version,
            "candidate_version": candidate_artifact.version,
            "baseline_sha256": hashlib.sha256(baseline_artifact.content).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate_artifact.content).hexdigest(),
            "hacs_version": HACS_VERSION,
            "hacs_commit": HACS_COMMIT,
            "hacs_sha256": HACS_SHA256,
            "aiogithubapi_version": AIOGITHUBAPI_VERSION,
            "aiogithubapi_sha256": AIOGITHUBAPI_SHA256,
        }
    finally:
        shutil.rmtree(_owned(directory, token))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--hacs-archive", required=True, type=Path)
    parser.add_argument("--aiogithubapi-wheel", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT)
    arguments = parser.parse_args()
    report = run(
        arguments.baseline,
        arguments.candidate,
        arguments.hacs_archive,
        arguments.aiogithubapi_wheel,
        arguments.timeout_seconds,
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
