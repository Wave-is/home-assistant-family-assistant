"""Pure orchestration tests; child HA processes are synthetic at this layer."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from tools.build_release import DOMAIN_PATH, build
from tools.run_upgrade_acceptance import (
    UpgradeAcceptanceError,
    _install,
    run,
)


def _repository(path: Path, version: str) -> Path:
    runtime = path / DOMAIN_PATH
    (runtime / "frontend").mkdir(parents=True)
    (runtime / "translations").mkdir()
    files = {
        "__init__.py": '"""Synthetic packaged runtime."""\n',
        "manifest.json": json.dumps({"domain": "family_assistant", "version": version}),
        "strings.json": "{}",
        "frontend/family-assistant.js": 'import "./child.js";\n',
        "frontend/child.js": "export const child = true;\n",
        **{f"translations/{language}.json": "{}" for language in ("en", "ru", "uk")},
    }
    for name, content in files.items():
        (runtime / name).write_text(content, encoding="utf-8")
    (path / "tests").mkdir()
    (path / "tests" / "ha_upgrade_acceptance.py").write_text(
        '"""Synthetic child helper."""\n', encoding="utf-8"
    )
    return path


@pytest.fixture
def repositories(tmp_path):
    return (
        _repository(tmp_path / "baseline", "1.0.0"),
        _repository(tmp_path / "candidate", "1.1.0"),
    )


def test_two_phases_use_same_owned_config_and_exact_artifact_versions(repositories, monkeypatch):
    baseline, candidate = repositories
    calls = []

    def child(command, **kwargs):
        phase = command[2]
        config = Path(command[command.index("--config") + 1])
        contract = Path(command[command.index("--contract") + 1])
        version = command[command.index("--expected-version") + 1]
        installed = json.loads((config / DOMAIN_PATH / "manifest.json").read_bytes())
        calls.append((phase, config, contract, version, installed["version"], kwargs))
        if phase == "prepare":
            contract.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "PASS", "")

    monkeypatch.setattr("tools.run_upgrade_acceptance.subprocess.run", child)
    before = {
        root.name: {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }
        for root in (baseline, candidate)
    }
    report = run(baseline.resolve(), candidate.resolve(), timeout=45)

    assert report == {
        "baseline_version": "1.0.0",
        "candidate_version": "1.1.0",
        "baseline_sha256": hashlib.sha256(build(baseline, "1.0.0")[0]).hexdigest(),
        "candidate_sha256": hashlib.sha256(build(candidate, "1.1.0")[0]).hexdigest(),
    }
    assert [(call[0], call[3], call[4]) for call in calls] == [
        ("prepare", "1.0.0", "1.0.0"),
        ("verify", "1.1.0", "1.1.0"),
    ]
    assert calls[0][1] == calls[1][1] and calls[0][2] == calls[1][2]
    assert calls[0][5]["timeout"] == calls[1][5]["timeout"] == 45
    assert calls[0][5]["cwd"] == calls[0][1]
    assert calls[0][5]["stdout"] is subprocess.DEVNULL
    assert calls[0][5]["stderr"] is subprocess.DEVNULL
    assert not calls[0][1].parent.exists()
    assert before == {
        root.name: {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }
        for root in (baseline, candidate)
    }


def test_baseline_child_failure_never_starts_candidate_phase(repositories, monkeypatch):
    baseline, candidate = repositories
    phases = []

    def child(command, **_kwargs):
        phases.append(command[2])
        return subprocess.CompletedProcess(command, 4, "", "synthetic failure")

    monkeypatch.setattr("tools.run_upgrade_acceptance.subprocess.run", child)
    with pytest.raises(UpgradeAcceptanceError, match="prepare_failed"):
        run(baseline.resolve(), candidate.resolve())
    assert phases == ["prepare"]


def test_baseline_timeout_never_starts_candidate_phase(repositories, monkeypatch):
    baseline, candidate = repositories
    phases = []

    def child(command, **_kwargs):
        phases.append(command[2])
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr("tools.run_upgrade_acceptance.subprocess.run", child)
    with pytest.raises(UpgradeAcceptanceError, match="prepare_timeout"):
        run(baseline.resolve(), candidate.resolve(), timeout=30)
    assert phases == ["prepare"]


def test_candidate_failure_is_fixed_and_temp_config_is_cleaned(repositories, monkeypatch):
    baseline, candidate = repositories
    phases = []
    owned = None

    def child(command, **_kwargs):
        nonlocal owned
        phases.append(command[2])
        owned = Path(command[command.index("--config") + 1]).parent
        return subprocess.CompletedProcess(command, 0 if command[2] == "prepare" else 9)

    monkeypatch.setattr("tools.run_upgrade_acceptance.subprocess.run", child)
    with pytest.raises(UpgradeAcceptanceError, match="verify_failed"):
        run(baseline.resolve(), candidate.resolve())
    assert phases == ["prepare", "verify"]
    assert owned is not None and not owned.exists()


def test_equal_versions_fail_before_any_child_process(tmp_path, monkeypatch):
    baseline = _repository(tmp_path / "baseline", "1.0.0")
    candidate = _repository(tmp_path / "candidate", "1.0.0")
    monkeypatch.setattr(
        "tools.run_upgrade_acceptance.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("child process must not start"),
    )
    with pytest.raises(UpgradeAcceptanceError, match="versions_not_distinct"):
        run(baseline.resolve(), candidate.resolve())


def test_relative_repository_path_is_rejected(repositories):
    _baseline, candidate = repositories
    with pytest.raises(UpgradeAcceptanceError, match="baseline_path_not_absolute"):
        run(Path("baseline"), candidate.resolve())


def test_repository_symlink_is_rejected(repositories, tmp_path):
    baseline, candidate = repositories
    link = tmp_path / "baseline-link"
    try:
        link.symlink_to(baseline, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with pytest.raises(UpgradeAcceptanceError, match="baseline_unsafe"):
        run(link.absolute(), candidate.resolve())


@pytest.mark.skipif(os.name != "nt", reason="NTFS junction regression")
def test_repository_junction_is_rejected(repositories, tmp_path):
    baseline, candidate = repositories
    junction = tmp_path / "baseline-junction"
    command = shutil.which("cmd.exe")
    if command is None:
        pytest.skip("cmd.exe is unavailable")
    created = subprocess.run(  # noqa: S603 -- fixed executable and synthetic paths
        [command, "/d", "/c", "mklink", "/J", str(junction), str(baseline)],
        capture_output=True,
        check=False,
    )
    if created.returncode:
        pytest.skip("directory junctions are unavailable")
    try:
        with pytest.raises(UpgradeAcceptanceError, match="baseline_unsafe"):
            run(junction.absolute(), candidate.resolve())
    finally:
        os.rmdir(junction)


def test_unknown_runtime_file_fails_before_any_child_process(repositories, monkeypatch):
    baseline, candidate = repositories
    (baseline / DOMAIN_PATH / "unknown.txt").write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(
        "tools.run_upgrade_acceptance.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("child process must not start"),
    )
    with pytest.raises(UpgradeAcceptanceError, match="baseline_artifact_invalid"):
        run(baseline.resolve(), candidate.resolve())


def test_archive_traversal_is_rejected_without_writing_outside_config(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{DOMAIN_PATH.as_posix()}/../../escape.py", "synthetic")
    with pytest.raises(UpgradeAcceptanceError, match="artifact_structure_invalid"):
        _install(buffer.getvalue(), config)
    assert not (tmp_path / "escape.py").exists()


def test_install_refuses_an_existing_runtime_target(tmp_path):
    config = tmp_path / "config"
    runtime = config / DOMAIN_PATH
    runtime.mkdir(parents=True)
    with pytest.raises(UpgradeAcceptanceError, match="runtime_target_exists"):
        _install(b"not a zip", config)
