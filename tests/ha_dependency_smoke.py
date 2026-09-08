"""Seed a pinned wheel only in an offline, capability-free disposable HA container.

Developer acceptance helper, not integration runtime or a production installer.
The caller stages the public wheel before starting the network-none container.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

PDF_WHEEL = "pypdf-6.17.0-py3-none-any.whl"
PDF_SHA256 = "5bd827266a21553b74d910e350131a6227b72f2ab4209bf372814b8195fa11c5"
CASES = {
    "smoke": "tests/ha_smoke.py",
    "restore": "tools/run_restore_acceptance.py",
    "upgrade": "tools/run_upgrade_acceptance.py",
    "hacs": "tools/run_hacs_upgrade_acceptance.py",
}


def validate(wheel: Path) -> None:
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("disposable_container_required")
    status = Path("/proc/self/status").read_text()
    capability = next(
        (line.split()[1] for line in status.splitlines() if line.startswith("CapEff:")), None
    )
    if capability is None or int(capability, 16) != 0:
        raise RuntimeError("capability_free_container_required")
    # Some QNAP kernels expose a bonding_masters control *file* here. It is
    # not an interface; real interface entries resolve to directories.
    if {path.name for path in Path("/sys/class/net").iterdir() if path.is_dir()} != {"lo"}:
        raise RuntimeError("network_none_required")
    if (
        wheel.name != PDF_WHEEL
        or not wheel.is_file()
        or not 0 < wheel.stat().st_size <= 1024 * 1024
    ):
        raise RuntimeError("pinned_wheel_required")
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != PDF_SHA256:
        raise RuntimeError("pinned_wheel_hash_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        validate(args.wheel)
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--no-cache-dir",
                "--disable-pip-version-check",
                str(args.wheel),
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("offline_dependency_install_failed")
        import pypdf

        if pypdf.__version__ != "6.17.0":
            raise RuntimeError("dependency_version_mismatch")
        target = Path(__file__).resolve().parents[1] / CASES[args.case]
        if not target.is_file():
            raise RuntimeError("acceptance_script_missing")
        remaining = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        print("PASS: pinned PDF wheel installed in offline disposable HA container", flush=True)
        # Fixed Python interpreter and one of the four shipped acceptance scripts.
        os.execv(sys.executable, [sys.executable, str(target), *remaining])  # noqa: S606
    except Exception as err:
        # No pip logs, environment, paths or parser output in failure messages.
        safe_codes = {
            "disposable_container_required",
            "capability_free_container_required",
            "network_none_required",
            "pinned_wheel_required",
            "pinned_wheel_hash_mismatch",
            "offline_dependency_install_failed",
            "dependency_version_mismatch",
            "acceptance_script_missing",
        }
        code = (
            str(err) if isinstance(err, RuntimeError) and str(err) in safe_codes else "unexpected"
        )
        print(f"FAIL: isolated dependency bootstrap ({code})", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
