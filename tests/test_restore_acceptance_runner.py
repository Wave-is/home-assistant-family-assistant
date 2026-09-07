"""Guard and process orchestration tests, not substitutes for actual HA."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from test_upgrade_acceptance_runner import _repository

from tools.build_release import DOMAIN_PATH, build
from tools.run_restore_acceptance import (
    MARKER,
    PHASES,
    PREFIX,
    RestoreAcceptanceError,
    owned_config,
    run,
)


@pytest.fixture
def source(tmp_path):
    source = _repository(tmp_path / "source", "1.1.0")
    (source / "tests" / "ha_restore_acceptance.py").write_text(
        '"""Synthetic test helper, never real HA."""\n', encoding="utf-8"
    )
    return source.resolve()


class Child:
    def __init__(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        self.pid = 123456789
        self.killed = False
        self.waits = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return 0


def test_exact_artifact_four_fresh_processes_owned_directory_and_cleanup(source, monkeypatch):
    calls = []
    before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}

    def process(command, **kwargs):
        config = Path(command[command.index("--config") + 1])
        token = command[command.index("--ownership-token") + 1]
        assert owned_config(config, token) == config
        assert (
            json.loads((config / DOMAIN_PATH / "manifest.json").read_bytes())["version"] == "1.1.0"
        )
        calls.append(Child(command, **kwargs))
        return calls[-1]

    monkeypatch.setattr("tools.run_restore_acceptance.subprocess.Popen", process)
    result = run(source, timeout=37)
    assert result == {
        "version": "1.1.0",
        "sha256": hashlib.sha256(build(source, "1.1.0")[0]).hexdigest(),
        "phases": list(PHASES),
        "native_encrypted_restore": True,
    }
    assert [c.command[2] for c in calls] == list(PHASES)
    config = calls[0].kwargs["cwd"]
    assert not config.parent.exists()
    for child in calls:
        assert child.waits == [37]
        assert child.kwargs["cwd"] == config
        assert child.kwargs["stdin"] is subprocess.DEVNULL
        assert child.kwargs["stdout"] is subprocess.DEVNULL
        assert child.kwargs["stderr"] is subprocess.DEVNULL
        assert child.kwargs["start_new_session"] == (os.name == "posix")
        assert child.kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert "password" not in " ".join(child.command).lower()
    assert before == {
        str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("failure", PHASES)
def test_failure_stops_later_phases_and_cleans_owned_config(source, monkeypatch, failure):
    calls = []

    class Failed(Child):
        def wait(self, timeout=None):
            return 1 if self.command[2] == failure else 0

    def process(command, **kwargs):
        calls.append(Failed(command, **kwargs))
        return calls[-1]

    monkeypatch.setattr("tools.run_restore_acceptance.subprocess.Popen", process)
    with pytest.raises(RestoreAcceptanceError, match=f"^{failure}_failed$"):
        run(source)
    assert [c.command[2] for c in calls] == list(PHASES[: PHASES.index(failure) + 1])
    assert not calls[0].kwargs["cwd"].parent.exists()


def test_timeout_settles_owned_process_and_never_restores(source, monkeypatch):
    calls, killed_groups = [], []

    class Timeout(Child):
        def wait(self, timeout=None):
            self.waits.append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired(self.command, timeout)
            return -9

    def process(command, **kwargs):
        calls.append(Timeout(command, **kwargs))
        return calls[-1]

    monkeypatch.setattr("tools.run_restore_acceptance.subprocess.Popen", process)
    monkeypatch.setattr(
        "tools.run_restore_acceptance.os.killpg", lambda *v: killed_groups.append(v), raising=False
    )
    with pytest.raises(RestoreAcceptanceError, match="^prepare_timeout$"):
        run(source, timeout=30)
    assert len(calls) == 1 and calls[0].waits == [30, None]
    assert bool(killed_groups) if os.name == "posix" else calls[0].killed
    assert not calls[0].kwargs["cwd"].parent.exists()


@pytest.mark.parametrize("timeout", [True, None, "300", 0, 29, 901])
def test_timeout_validation_before_child(source, monkeypatch, timeout):
    monkeypatch.setattr(
        "tools.run_restore_acceptance.subprocess.Popen", lambda *_a, **_k: pytest.fail("child")
    )
    with pytest.raises(RestoreAcceptanceError, match="^invalid_timeout$"):
        run(source, timeout)


def test_arbitrary_config_and_relative_config_refused(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (tmp_path / MARKER).write_text("a" * 32, encoding="ascii")
    for target in (config, Path("config")):
        with pytest.raises(RestoreAcceptanceError, match="^config_unowned$"):
            owned_config(target, "a" * 32)


def test_exact_ownership_token_and_marker_required():
    root = Path(tempfile.mkdtemp(prefix=PREFIX)).resolve()
    config = root / "config"
    config.mkdir()
    marker = root / MARKER
    try:
        marker.write_text("a" * 32, encoding="ascii")
        assert owned_config(config, "a" * 32) == config
        for token in ("b" * 32, "a", "../", "", None, True):
            with pytest.raises(RestoreAcceptanceError, match="^config_unowned$"):
                owned_config(config, token)
        marker.write_text("x" * 200, encoding="ascii")
        with pytest.raises(RestoreAcceptanceError, match="^config_unowned$"):
            owned_config(config, "a" * 32)
    finally:
        assert root.resolve().parent == Path(tempfile.gettempdir()).resolve()
        assert root.name.startswith(PREFIX)
        shutil.rmtree(root)


def test_missing_helper_rejected_before_temporary_creation(source, monkeypatch):
    (source / "tests" / "ha_restore_acceptance.py").unlink()
    monkeypatch.setattr(
        "tools.run_restore_acceptance.tempfile.mkdtemp", lambda **_k: pytest.fail("temp")
    )
    with pytest.raises(RestoreAcceptanceError, match="^helper_unavailable$"):
        run(source)
