"""Run native encrypted HA restore in a disposable, owned configuration only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

if __package__:
    from .run_upgrade_acceptance import _artifact, _install, _reparse, _repository
else:
    from run_upgrade_acceptance import _artifact, _install, _reparse, _repository

PREFIX = "family-assistant-restore-"
MARKER = ".family-assistant-restore-owned"
PHASES = ("prepare", "backup", "restore", "verify")


class RestoreAcceptanceError(ValueError):
    """Fixed failure code; never expose backup keys or child output."""


def owned_config(config: Path, token: str) -> Path:
    """Reject existing/user configuration paths before any destructive restore."""
    if (
        not config.is_absolute()
        or not isinstance(token, str)
        or re.fullmatch(r"[0-9a-f]{32}", token) is None
    ):
        raise RestoreAcceptanceError("config_unowned")
    try:
        resolved = config.resolve(strict=True)
        root = resolved.parent
        marker = root / MARKER
        marker_stat = marker.stat(follow_symlinks=False)
        if (
            config.absolute() != resolved
            or resolved.name != "config"
            or root.parent != Path(tempfile.gettempdir()).resolve(strict=True)
            or not root.name.startswith(PREFIX)
            or _reparse(marker_stat)
            or not stat.S_ISREG(marker_stat.st_mode)
            or marker_stat.st_size != len(token)
            or marker.read_text(encoding="ascii") != token
            or not resolved.is_dir()
        ):
            raise RestoreAcceptanceError("config_unowned")
    except (OSError, UnicodeError) as error:
        raise RestoreAcceptanceError("config_unowned") from error
    return resolved


def _helper(source: Path) -> Path:
    path = source / "tests" / "ha_restore_acceptance.py"
    try:
        value = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
        if (
            _reparse(value)
            or not stat.S_ISREG(value.st_mode)
            or not resolved.is_relative_to(source)
        ):
            raise RestoreAcceptanceError("helper_unsafe")
        return resolved
    except OSError as error:
        raise RestoreAcceptanceError("helper_unavailable") from error


def _phase(phase: str, helper: Path, config: Path, token: str, version: str, timeout: int):
    command = [
        sys.executable,
        str(helper),
        phase,
        "--config",
        str(config),
        "--ownership-token",
        token,
        "--expected-version",
        version,
    ]
    try:
        with subprocess.Popen(  # noqa: S603 -- fixed interpreter and reviewed helper
            command,
            cwd=config,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            start_new_session=os.name == "posix",
        ) as process:
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait()
                raise
    except subprocess.TimeoutExpired as error:
        raise RestoreAcceptanceError(f"{phase}_timeout") from error
    except OSError as error:
        raise RestoreAcceptanceError(f"{phase}_unavailable") from error
    if code:
        raise RestoreAcceptanceError(f"{phase}_failed")


def run(source: Path, timeout: int = 300) -> dict:
    if type(timeout) is not int or not 30 <= timeout <= 900:
        raise RestoreAcceptanceError("invalid_timeout")
    source = _repository(source, "source")
    artifact = _artifact(source, "source")
    helper = _helper(source)
    root = Path(tempfile.mkdtemp(prefix=PREFIX)).resolve(strict=True)
    token = uuid.uuid4().hex
    (root / MARKER).write_text(token, encoding="ascii")
    config = root / "config"
    config.mkdir()
    try:
        owned_config(config, token)
        _install(artifact.content, config)
        for phase in PHASES:
            owned_config(config, token)
            _phase(phase, helper, config, token, artifact.version, timeout)
        return {
            "version": artifact.version,
            "sha256": hashlib.sha256(artifact.content).hexdigest(),
            "phases": list(PHASES),
            "native_encrypted_restore": True,
        }
    finally:
        owned_config(config, token)
        shutil.rmtree(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.source, arguments.timeout_seconds), sort_keys=True))


if __name__ == "__main__":
    main()
