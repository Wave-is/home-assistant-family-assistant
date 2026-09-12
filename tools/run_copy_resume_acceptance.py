"""Restart an exact packaged runtime in two isolated HA acceptance processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
import uuid
from pathlib import Path

if __package__:
    from . import run_upgrade_acceptance as sandbox
else:
    import run_upgrade_acceptance as sandbox

HELPER_FILES = (
    "tests/ha_copy_resume_acceptance.py",
    "tests/ha_upgrade_acceptance.py",
    "tests/ha_options_menu.py",
    "tests/ha_copy_wizard_smoke.py",
    "tests/ha_legacy_archive_smoke.py",
    "tests/ha_media_smoke.py",
)


def _helpers(repository: Path) -> dict[str, bytes]:
    result = {}
    for relative in HELPER_FILES:
        path = repository / relative
        try:
            before = os.stat(path, follow_symlinks=False)
            if (
                sandbox._reparse(before)
                or not stat.S_ISREG(before.st_mode)
                or not 0 < before.st_size <= 256 * 1024
                or path.resolve(strict=True) != path.absolute()
            ):
                raise sandbox.UpgradeAcceptanceError("resume_helper_unsafe")
            content = path.read_bytes()
            after = os.stat(path, follow_symlinks=False)

            def identity(item):
                return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)

            if identity(before) != identity(after) or len(content) != before.st_size:
                raise sandbox.UpgradeAcceptanceError("resume_helper_changed")
            result[relative] = content
        except sandbox.UpgradeAcceptanceError:
            raise
        except OSError:
            raise sandbox.UpgradeAcceptanceError("resume_helper_unavailable") from None
    return result


def run(repository: Path, timeout: int = sandbox.DEFAULT_TIMEOUT) -> dict:
    """Use one immutable runtime/helper snapshot, native Stores and fresh processes."""
    if type(timeout) is not int or not 30 <= timeout <= sandbox.MAX_TIMEOUT:
        raise sandbox.UpgradeAcceptanceError("invalid_timeout")
    repository = sandbox._repository(repository, "candidate")
    artifact = sandbox._artifact(repository, "candidate")
    helpers = _helpers(repository)
    directory = Path(tempfile.mkdtemp(prefix=sandbox.PREFIX)).resolve(strict=True)
    token = uuid.uuid4().hex
    (directory / sandbox.MARKER).write_text(token, encoding="ascii", newline="\n")
    try:
        owned = sandbox._owned_root(directory, token)
        config = owned / "config"
        config.mkdir()
        sandbox._install(artifact.content, config)
        for relative, content in helpers.items():
            path = owned / "helpers" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(content)
        helper = owned / "helpers" / HELPER_FILES[0]
        contract = owned / "contract.json"
        for phase in ("prepare", "verify"):
            sandbox._phase(phase, helper, config, contract, artifact.version, timeout)
        return {
            "version": artifact.version,
            "sha256": hashlib.sha256(artifact.content).hexdigest(),
            "phases": ["prepare", "verify"],
            "restart": "separate_processes_graceful_shutdown",
        }
    finally:
        sandbox._cleanup(directory, token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=sandbox.DEFAULT_TIMEOUT)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.repository, arguments.timeout_seconds), sort_keys=True))


if __name__ == "__main__":
    main()
