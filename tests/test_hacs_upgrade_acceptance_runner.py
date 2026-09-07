"""Pure orchestration tests for the offline real-HACS acceptance runner."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import traceback
import zipfile
from pathlib import Path

import pytest

from tools import run_hacs_upgrade_acceptance as runner
from tools.run_upgrade_acceptance import UpgradeAcceptanceError


def _repository(path: Path, version: str) -> Path:
    runtime = path / "custom_components" / "family_assistant"
    (runtime / "frontend").mkdir(parents=True)
    (runtime / "translations").mkdir()
    files = {
        "__init__.py": '"""Synthetic runtime."""\n',
        "manifest.json": json.dumps({"domain": "family_assistant", "version": version}),
        "strings.json": "{}",
        "frontend/family-assistant.js": 'import "./child.js";\n',
        "frontend/child.js": "export const child = true;\n",
        **{f"translations/{language}.json": "{}" for language in ("en", "ru", "uk")},
    }
    for name, content in files.items():
        (runtime / name).write_text(content, encoding="utf-8")
    (path / "tests").mkdir()
    (path / "tests" / "ha_hacs_upgrade_acceptance.py").write_text(
        '"""Synthetic phase helper."""\n', encoding="utf-8"
    )
    return path


def _dependencies(path: Path) -> tuple[Path, Path]:
    hacs = path / "hacs.zip"
    with zipfile.ZipFile(hacs, "w") as archive:
        archive.writestr("__init__.py", "")
        archive.writestr("manifest.json", json.dumps({"domain": "hacs"}))
        archive.writestr("repositories/base.py", "")
    wheel = path / "aiogithubapi-22.10.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("aiogithubapi/__init__.py", "")
        archive.writestr(
            "aiogithubapi-22.10.1.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: aiogithubapi\nVersion: 22.10.1\n",
        )
    return hacs, wheel


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    baseline = _repository(tmp_path / "baseline", "1.0.0")
    candidate = _repository(tmp_path / "candidate", "1.1.0")
    hacs, wheel = _dependencies(tmp_path)
    monkeypatch.setattr(runner, "HACS_SHA256", hashlib.sha256(hacs.read_bytes()).hexdigest())
    monkeypatch.setattr(
        runner, "AIOGITHUBAPI_SHA256", hashlib.sha256(wheel.read_bytes()).hexdigest()
    )
    return baseline, candidate, hacs, wheel


def test_real_hacs_phases_share_owned_config_and_pinned_dependencies(inputs, monkeypatch):
    baseline, candidate, hacs, wheel = inputs
    calls = []

    def child(command, **kwargs):
        phase = command[2]
        config = Path(command[command.index("--config") + 1])
        artifact = Path(command[command.index("--artifact") + 1])
        calls.append((phase, config, artifact, artifact.is_file(), kwargs))
        if phase == "prepare":
            Path(command[command.index("--contract") + 1]).write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    report = runner.run(
        baseline.resolve(), candidate.resolve(), hacs.resolve(), wheel.resolve(), timeout=45
    )

    assert [value[0] for value in calls] == [
        "install",
        "prepare",
        "rollback",
        "upgrade",
        "verify",
    ]
    assert len({value[1] for value in calls}) == 1
    assert all(value[3] for value in calls)
    assert all(value[4]["timeout"] == 45 for value in calls)
    assert all(str(wheel.resolve()) in value[4]["env"]["PYTHONPATH"] for value in calls)
    assert not calls[0][1].parent.exists()
    assert report["hacs_version"] == "2.0.5"
    assert report["hacs_commit"] == runner.HACS_COMMIT
    assert report["baseline_version"] == "1.0.0"
    assert report["candidate_version"] == "1.1.0"


def test_dependency_hash_mismatch_starts_no_child(inputs, monkeypatch):
    baseline, candidate, hacs, wheel = inputs
    monkeypatch.setattr(runner, "HACS_SHA256", "0" * 64)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("child process must not start"),
    )
    with pytest.raises(UpgradeAcceptanceError, match="hacs_archive_hash_mismatch"):
        runner.run(baseline.resolve(), candidate.resolve(), hacs.resolve(), wheel.resolve())


def test_nested_hacs_release_layout_is_rejected(inputs):
    baseline, candidate, _hacs, wheel = inputs
    nested = wheel.parent / "nested-hacs.zip"
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("custom_components/hacs/__init__.py", "")
        archive.writestr("custom_components/hacs/manifest.json", json.dumps({"domain": "hacs"}))
    original = runner.HACS_SHA256
    try:
        runner.HACS_SHA256 = hashlib.sha256(nested.read_bytes()).hexdigest()
        with pytest.raises(UpgradeAcceptanceError, match="hacs_archive_layout_invalid"):
            runner.run(baseline.resolve(), candidate.resolve(), nested.resolve(), wheel.resolve())
    finally:
        runner.HACS_SHA256 = original


def test_failed_rollback_phase_stops_before_candidate_install(inputs, monkeypatch):
    baseline, candidate, hacs, wheel = inputs
    phases = []

    def child(command, **_kwargs):
        phase = command[2]
        phases.append(phase)
        return subprocess.CompletedProcess(command, 9 if phase == "rollback" else 0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    with pytest.raises(UpgradeAcceptanceError, match="hacs_rollback_failed"):
        runner.run(baseline.resolve(), candidate.resolve(), hacs.resolve(), wheel.resolve())
    assert phases == ["install", "prepare", "rollback"]


def test_failure_surfaces_only_bounded_structural_marker(inputs, monkeypatch):
    baseline, candidate, hacs, wheel = inputs

    def child(command, **_kwargs):
        report = Path(command[command.index("--failure-report") + 1])
        report.write_text(
            json.dumps(
                {
                    "class": "AssertionError",
                    "frames": [
                        {
                            "file": "ha_hacs_upgrade_acceptance.py",
                            "function": "_install_or_update",
                            "line": 321,
                        }
                    ],
                }
            ),
            encoding="ascii",
        )
        return subprocess.CompletedProcess(command, 7, stderr="secret-provider-message")

    monkeypatch.setattr(runner.subprocess, "run", child)
    with pytest.raises(UpgradeAcceptanceError) as error:
        runner.run(baseline.resolve(), candidate.resolve(), hacs.resolve(), wheel.resolve())
    rendered = str(error.value)
    assert rendered == (
        "hacs_install_failed[AssertionError@ha_hacs_upgrade_acceptance.py:_install_or_update:321]"
    )
    assert "secret" not in rendered and "provider" not in rendered


def test_malformed_failure_report_cannot_surface_raw_text(tmp_path):
    report = tmp_path / "failure.json"
    report.write_text(
        json.dumps(
            {
                "class": "AssertionError",
                "frames": [],
                "message": "private raw failure",
            }
        ),
        encoding="utf-8",
    )
    assert runner._failure_detail(report) == ""


def test_relative_dependency_paths_are_rejected(inputs):
    baseline, candidate, _hacs, wheel = inputs
    with pytest.raises(UpgradeAcceptanceError, match="hacs_archive_path_not_absolute"):
        runner.run(baseline.resolve(), candidate.resolve(), Path("hacs.zip"), wheel.resolve())


def test_helper_exception_marker_accepts_lambda_frames_without_messages(tmp_path):
    helper = Path(__file__).with_name("ha_hacs_upgrade_acceptance.py")
    tree = ast.parse(helper.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_write_failure"
    )
    scope = {"Path": Path, "traceback": traceback, "json": json, "__file__": str(helper)}
    # Extract only this checked-in function; its HA imports cannot run on the host.
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(helper), "exec"), scope)  # noqa: S102
    report = tmp_path / "exception.json"
    try:
        (lambda: 1 / 0)()
    except ZeroDivisionError as error:
        scope["_write_failure"](report, error)
    detail = runner._failure_detail(report)
    assert detail.startswith("[ZeroDivisionError@")
    assert "_lambda_" in detail
    assert "division by zero" not in detail
