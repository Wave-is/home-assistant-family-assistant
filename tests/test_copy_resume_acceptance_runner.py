"""Pure orchestration checks; native process acceptance is a separate gate."""

import json
import subprocess
from pathlib import Path

import pytest

from tools import run_copy_resume_acceptance as runner
from tools.run_upgrade_acceptance import UpgradeAcceptanceError


@pytest.fixture
def repository(tmp_path):
    from test_upgrade_acceptance_runner import _repository

    source = _repository(tmp_path / "candidate", "0.1.0-alpha.31")
    for relative in runner.HELPER_FILES:
        (source / relative).write_text('"""Synthetic helper."""\n', encoding="utf-8")
    return source.resolve()


def test_two_fresh_processes_keep_exact_artifact_and_frozen_helpers(repository, monkeypatch):
    calls = []

    def child(command, **kwargs):
        phase = command[2]
        config = Path(command[command.index("--config") + 1])
        contract = Path(command[command.index("--contract") + 1])
        helper = Path(command[1])
        installed = json.loads(
            (config / "custom_components/family_assistant/manifest.json").read_bytes()
        )
        assert installed["version"] == "0.1.0-alpha.31"
        assert helper.read_text() == '"""Synthetic helper."""\n'
        assert helper.is_relative_to(config.parent)
        assert not helper.is_relative_to(repository)
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["timeout"] == 45
        assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        calls.append((phase, config, contract))
        if phase == "prepare":
            (repository / runner.HELPER_FILES[0]).write_text("changed after staging")
            contract.write_text("{}")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.sandbox.subprocess, "run", child)
    report = runner.run(repository, 45)
    assert report["phases"] == ["prepare", "verify"]
    assert report["restart"] == "separate_processes_graceful_shutdown"
    assert report["version"] == "0.1.0-alpha.31" and len(report["sha256"]) == 64
    assert [row[0] for row in calls] == ["prepare", "verify"]
    assert calls[0][1:] == calls[1][1:]
    assert not calls[0][1].parent.exists()


@pytest.mark.parametrize("bad_phase", ["prepare", "verify"])
@pytest.mark.parametrize("failure", ["nonzero", "timeout", "unavailable"])
def test_failure_has_fixed_code_and_owned_cleanup(repository, monkeypatch, bad_phase, failure):
    calls, owned = [], []

    def child(command, **_kwargs):
        phase = command[2]
        calls.append(phase)
        owned.append(Path(command[command.index("--config") + 1]).parent)
        if phase == bad_phase:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 30)
            if failure == "unavailable":
                raise OSError("synthetic private-like path must not surface")
            return subprocess.CompletedProcess(command, 2)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.sandbox.subprocess, "run", child)
    suffix = {"nonzero": "failed", "timeout": "timeout", "unavailable": "unavailable"}[failure]
    with pytest.raises(UpgradeAcceptanceError, match=f"^{bad_phase}_{suffix}$"):
        runner.run(repository)
    assert calls == (["prepare"] if bad_phase == "prepare" else ["prepare", "verify"])
    assert owned and all(not path.exists() for path in owned)


@pytest.mark.parametrize("timeout", [True, 29, 901, 30.0, "30"])
def test_invalid_timeouts_do_not_start_a_process(repository, monkeypatch, timeout):
    monkeypatch.setattr(runner.sandbox, "_phase", lambda *_: pytest.fail("unexpected process"))
    with pytest.raises(UpgradeAcceptanceError, match="^invalid_timeout$"):
        runner.run(repository, timeout)


@pytest.mark.parametrize("relative", runner.HELPER_FILES)
def test_every_helper_is_required_before_sandbox_creation(repository, monkeypatch, relative):
    (repository / relative).unlink()
    monkeypatch.setattr(runner.tempfile, "mkdtemp", lambda **_: pytest.fail("unexpected sandbox"))
    with pytest.raises(UpgradeAcceptanceError, match="^resume_helper_unavailable$"):
        runner.run(repository)


def test_helper_size_bound(repository):
    (repository / runner.HELPER_FILES[0]).write_bytes(b"x" * (256 * 1024 + 1))
    with pytest.raises(UpgradeAcceptanceError, match="^resume_helper_unsafe$"):
        runner.run(repository)


def test_relative_repository_denied(repository, monkeypatch):
    monkeypatch.chdir(repository.parent)
    with pytest.raises(UpgradeAcceptanceError, match="^candidate_path_not_absolute$"):
        runner.run(Path(repository.name))


def test_binary_dependencies_stay_outside_the_publishable_candidate(repository, monkeypatch):
    wheel = repository.parent / "dependencies" / "synthetic.whl"
    wheel.parent.mkdir()
    wheel.write_bytes(b"\xff\x00synthetic binary dependency")
    monkeypatch.setattr(runner.sandbox, "_phase", lambda *_: None)
    assert runner.run(repository)["version"] == "0.1.0-alpha.31"
    # Do not weaken the public scanner to accommodate an incorrectly staged wheel.
    (repository / "synthetic.whl").write_bytes(wheel.read_bytes())
    with pytest.raises(UpgradeAcceptanceError, match="^candidate_artifact_invalid$"):
        runner.run(repository)


def test_ci_stages_dependencies_as_sibling_not_inside_candidate():
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/checks.yml").read_text())
    steps = workflow["jobs"]["copy-resume-restart"]["steps"]
    checkout = next(step for step in steps if "actions/checkout@" in step.get("uses", ""))
    assert checkout["with"]["path"] == "candidate"
    execution = next(step["run"] for step in steps if "--case copy-resume" in step.get("run", ""))
    assert "--repository /work/candidate" in execution
    assert "--wheel /work/dependencies/" in execution
    assert "--network none" in execution and "--cap-drop ALL" in execution
