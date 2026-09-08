"""Test the disposable acceptance helper without operating any container."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "dependency_guard", Path(__file__).with_name("ha_dependency_smoke.py")
)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    marker = tmp_path / "marker"
    marker.touch()
    status = tmp_path / "status"
    status.write_text("CapEff:\t0000000000000000\n")
    network = tmp_path / "network"
    network.mkdir()
    (network / "lo").mkdir()
    wheel = tmp_path / guard.PDF_WHEEL
    wheel.write_bytes(b"synthetic wheel")
    monkeypatch.setattr(guard, "PDF_SHA256", guard.hashlib.sha256(wheel.read_bytes()).hexdigest())
    paths = {"/.dockerenv": marker, "/proc/self/status": status, "/sys/class/net": network}
    monkeypatch.setattr(guard, "Path", lambda path: paths.get(str(path), Path(path)))
    return wheel, marker, status, network


def test_loopback_and_kernel_control_file_are_offline(isolated):
    wheel, _, _, network = isolated
    (network / "bonding_masters").touch()
    guard.validate(wheel)


@pytest.mark.parametrize("failure", ["marker", "caps", "network", "wheel"])
def test_no_relaxation_of_isolation_or_pinned_dependency(isolated, failure):
    wheel, marker, status, network = isolated
    if failure == "marker":
        marker.unlink()
    elif failure == "caps":
        status.write_text("CapEff:\t0000000000000001\n")
    elif failure == "network":
        (network / "eth0").mkdir()
    else:
        wheel.write_bytes(b"wrong wheel")
    with pytest.raises(RuntimeError):
        guard.validate(wheel)
