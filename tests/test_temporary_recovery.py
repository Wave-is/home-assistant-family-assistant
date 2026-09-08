"""Bounded filesystem recovery tests using real filesystem paths and actual APIs."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from custom_components.family_assistant.migration.temporary_recovery import (
    ARCHIVE_TEMP_PREFIX,
    MAX_CANDIDATE_AGGREGATE_BYTES,
    MAX_CANDIDATE_COUNT,
    MAX_FILE_BYTES,
    MAX_TEMP_AGGREGATE_BYTES,
    MAX_TEMP_COUNT,
    RecoveryError,
    ResiduePlan,
    _encode,
    _safe_read_file,
    apply_residue,
    inspect_residue,
    restore_plan,
)

CANDIDATE_1 = "1" * 64
CANDIDATE_2 = "2" * 64
BLOB_1 = b"photo-bytes-candidate-one-content"
BLOB_2 = b"photo-bytes-candidate-two-content"


def _make_blobs() -> dict[str, bytes]:
    return {
        CANDIDATE_1: BLOB_1,
        CANDIDATE_2: BLOB_2,
    }


def test_successful_incomplete_temp(tmp_path: Path) -> None:
    """Verify inspection and preservation of an incomplete upload temp file."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    (root / CANDIDATE_1).write_bytes(BLOB_1)
    temp_content = BLOB_2[:10]
    temp_name = ".upload-abcdef12"
    (root / temp_name).write_bytes(temp_content)

    plan = inspect_residue(root, blobs)
    assert isinstance(plan, ResiduePlan)
    summary = plan.summary()
    assert summary["temp_count"] == 1
    assert summary["temp_bytes"] == len(temp_content)
    assert isinstance(summary["fingerprint"], str)
    assert len(summary["fingerprint"]) == 64

    # Repr privacy: content-free
    plan_repr = repr(plan)
    assert "ResiduePlan" in plan_repr
    assert temp_name not in plan_repr
    assert CANDIDATE_1 not in plan_repr
    assert "photo-bytes" not in plan_repr

    # Manifest roundtrip and deep-copy verification
    manifest = plan.private_manifest()
    assert manifest["temp_count"] == 1
    manifest["temp_count"] = 999
    assert plan.summary()["temp_count"] == 1

    restored = restore_plan(plan.private_manifest())
    assert restored.summary() == plan.summary()

    # Apply recovery
    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["fingerprint"] == summary["fingerprint"]
    assert receipt["preserved_count"] == 1
    assert receipt["preserved_bytes"] == len(temp_content)

    assert not (root / temp_name).exists()
    assert (root / CANDIDATE_1).read_bytes() == BLOB_1
    assert (archive_root / temp_name).read_bytes() == temp_content

    # Re-inspect: root is now valid with 0 residues
    assert inspect_residue(root, blobs) is None


@pytest.mark.parametrize("interrupt", [False, True])
def test_multiple_reviewed_aliases_preserve_and_retry_after_one_unlink(
    tmp_path, monkeypatch, interrupt
):
    root, archive = tmp_path / "active", tmp_path / "archive"
    root.mkdir()
    key = "a" * 64
    blob = b"synthetic complete candidate"
    original = root / key
    original.write_bytes(blob)
    first, second = root / ".upload-alias001", root / ".upload-alias002"
    os.link(original, first)
    os.link(original, second)
    plan = inspect_residue(root, {key: blob})
    unlink = Path.unlink

    def fail_second(path, *args, **kwargs):
        if path == second:
            raise OSError("synthetic interrupted unlink")
        return unlink(path, *args, **kwargs)

    if interrupt:
        with monkeypatch.context() as local:
            local.setattr(Path, "unlink", fail_second)
            with pytest.raises(RecoveryError):
                apply_residue(root, archive, plan, {key: blob})
        assert not first.exists() and second.exists() and original.stat().st_nlink == 2
        plan = restore_plan(plan.private_manifest())
    receipt = apply_residue(root, archive, plan, {key: blob})
    assert receipt["preserved_count"] == 2
    assert original.read_bytes() == blob and original.stat().st_nlink == 1
    assert not first.exists() and not second.exists()
    assert (archive / first.name).read_bytes() == blob
    assert (archive / second.name).read_bytes() == blob
    assert apply_residue(root, archive, plan, {key: blob}) == receipt


def test_zero_length_temp_preservation(tmp_path: Path) -> None:
    """Verify zero-length upload temp file is inspected and preserved."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    temp_name = ".upload-00000000"
    (root / temp_name).write_bytes(b"")

    plan = inspect_residue(root, blobs)
    assert isinstance(plan, ResiduePlan)
    assert plan.summary()["temp_count"] == 1
    assert plan.summary()["temp_bytes"] == 0

    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 1
    assert receipt["preserved_bytes"] == 0

    assert not (root / temp_name).exists()
    archived_file = archive_root / temp_name
    assert archived_file.is_file()
    assert archived_file.stat().st_size == 0
    assert archived_file.read_bytes() == b""


def test_hardlink_publication_window(tmp_path: Path) -> None:
    """Verify crash after os.link before temp.unlink is safely resolved."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    temp_name = ".upload-hl123456"
    temp_path = root / temp_name
    temp_path.write_bytes(BLOB_1)

    blob_path = root / CANDIDATE_1
    os.link(temp_path, blob_path)

    assert temp_path.stat().st_nlink == 2
    assert blob_path.stat().st_nlink == 2

    plan = inspect_residue(root, blobs)
    assert isinstance(plan, ResiduePlan)
    assert plan.summary()["temp_count"] == 1
    assert plan.summary()["temp_bytes"] == len(BLOB_1)

    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 1

    assert not temp_path.exists()
    assert blob_path.exists()
    assert blob_path.stat().st_nlink == 1
    assert blob_path.read_bytes() == BLOB_1
    assert (archive_root / temp_name).read_bytes() == BLOB_1


def test_outside_hardlink_denial(tmp_path: Path) -> None:
    """Verify outside hardlinks to files in root are rejected."""
    root = tmp_path / "staged_root"
    root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    blobs = _make_blobs()
    temp_name = ".upload-out12345"
    temp_path = root / temp_name
    temp_path.write_bytes(BLOB_1[:5])

    os.link(temp_path, outside_dir / "outside_link")

    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"

    (outside_dir / "outside_link").unlink()
    temp_path.unlink()
    blob_path = root / CANDIDATE_1
    blob_path.write_bytes(BLOB_1)
    os.link(blob_path, outside_dir / "outside_blob_link")

    temp_path.write_bytes(BLOB_2[:5])
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"


def test_outside_hardlink_created_before_apply(tmp_path: Path) -> None:
    """Verify an outside hardlink created between inspect and apply is denied."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    blobs = _make_blobs()
    temp_name = ".upload-race1234"
    temp_path = root / temp_name
    temp_path.write_bytes(BLOB_1[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None

    os.link(temp_path, outside_dir / "race_link")

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"
    assert temp_path.exists()


def test_symlink_file_denial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify symlink file in root is denied."""
    root = tmp_path / "staged_root"
    root.mkdir()
    blobs = _make_blobs()

    target = tmp_path / "target_file"
    target.write_bytes(BLOB_1[:5])
    symlink_file = root / ".upload-sym12345"

    try:
        symlink_file.symlink_to(target)
    except OSError:
        # On Windows without unprivileged symlink permissions, test via monkeypatch
        (root / ".upload-sym12345").write_bytes(BLOB_1[:5])
        monkeypatch.setattr(Path, "is_symlink", lambda self: True)

    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code in ("recovery_conflict", "recovery_invalid")


def test_symlink_root_denial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify symlink root or ancestor is denied."""
    root = tmp_path / "staged_root"
    root.mkdir()
    blobs = _make_blobs()

    symlink_root = tmp_path / "symlink_root"
    try:
        symlink_root.symlink_to(root, target_is_directory=True)
        with pytest.raises(RecoveryError) as exc_info:
            inspect_residue(symlink_root, blobs)
        assert exc_info.value.code == "recovery_invalid"
    except OSError:
        # Test junction on Windows or monkeypatched is_symlink
        try:
            import _winapi

            _winapi.CreateJunction(str(root), str(symlink_root))
            with pytest.raises(RecoveryError) as exc_info:
                inspect_residue(symlink_root, blobs)
            assert exc_info.value.code == "recovery_invalid"
            symlink_root.rmdir()
        except (ImportError, OSError):
            monkeypatch.setattr(Path, "is_symlink", lambda self: True)
            with pytest.raises(RecoveryError) as exc_info:
                inspect_residue(root, blobs)
            assert exc_info.value.code == "recovery_invalid"


def test_archive_root_separation(tmp_path: Path) -> None:
    """Verify archive root cannot be equal to root or inside root."""
    root = tmp_path / "staged_root"
    root.mkdir()
    blobs = _make_blobs()
    (root / ".upload-valid123").write_bytes(BLOB_1[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None

    # Archive root == root
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, root, plan, blobs)
    assert exc_info.value.code == "recovery_invalid"

    # Archive root inside root
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, root / "sub_archive", plan, blobs)
    assert exc_info.value.code == "recovery_invalid"


def test_unknown_entries_and_limits(tmp_path: Path) -> None:
    """Verify unknown files, subdirs, and bounds are rejected."""
    root = tmp_path / "staged_root"
    root.mkdir()
    blobs = _make_blobs()

    (root / "subfolder").mkdir()
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"
    (root / "subfolder").rmdir()

    (root / "arbitrary.txt").write_bytes(b"data")
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"
    (root / "arbitrary.txt").unlink()

    invalid_names = [
        ".upload-short",
        ".upload-toolong123",
        ".upload-UPPER123",
        ".upload_12345678",
        "upload-12345678",
    ]
    for name in invalid_names:
        (root / name).write_bytes(b"data")
        with pytest.raises(RecoveryError) as exc_info:
            inspect_residue(root, blobs)
        assert exc_info.value.code == "recovery_conflict"
        (root / name).unlink()

    (root / ("f" * 64)).write_bytes(b"data")
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"
    (root / ("f" * 64)).unlink()

    (root / CANDIDATE_1).write_bytes(b"wrong bytes")
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"
    (root / CANDIDATE_1).unlink()

    (root / ".upload-nonpfx12").write_bytes(b"non-matching-prefix")
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"
    (root / ".upload-nonpfx12").unlink()


def test_capacity_and_size_bounds(tmp_path: Path) -> None:
    """Verify strict candidate and temp capacity bounds."""
    root = tmp_path / "staged_root"
    root.mkdir()

    too_many_candidates = {f"{i:064x}": b"a" for i in range(MAX_CANDIDATE_COUNT + 1)}
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, too_many_candidates)
    assert exc_info.value.code == "recovery_invalid"

    large_candidate = {"a" * 64: b"x" * (MAX_FILE_BYTES + 1)}
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, large_candidate)
    assert exc_info.value.code == "recovery_invalid"

    huge_blobs = {f"{i:064x}": b"x" * (2 * 1024 * 1024) for i in range(50)}
    assert sum(len(v) for v in huge_blobs.values()) > MAX_CANDIDATE_AGGREGATE_BYTES
    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, huge_blobs)
    assert exc_info.value.code == "recovery_invalid"

    blobs = _make_blobs()
    temp_names = [f".upload-tmp{i:05d}" for i in range(MAX_TEMP_COUNT + 1)]
    for name in temp_names:
        (root / name).write_bytes(BLOB_1[:1])

    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"

    for name in temp_names:
        (root / name).unlink()

    chunk_9mb = b"y" * (9 * 1024 * 1024)
    huge_blobs_for_temp = {"3" * 64: chunk_9mb}
    temp_4 = [f".upload-big{i:05d}" for i in range(4)]
    for name in temp_4:
        (root / name).write_bytes(chunk_9mb)

    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, huge_blobs_for_temp)
    assert exc_info.value.code == "recovery_conflict"

    for name in temp_4:
        (root / name).unlink()


def test_changed_identity_or_content_at_apply(tmp_path: Path) -> None:
    """Verify apply refuses if identity, content, or root state changed."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    (root / CANDIDATE_1).write_bytes(BLOB_1)
    temp_name = ".upload-change12"
    (root / temp_name).write_bytes(BLOB_2[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None

    (root / temp_name).write_bytes(BLOB_2[:6])
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"

    (root / temp_name).write_bytes(BLOB_2[:5])
    plan = inspect_residue(root, blobs)
    assert plan is not None

    (root / CANDIDATE_1).write_bytes(b"tampered blob content")
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"

    (root / CANDIDATE_1).write_bytes(BLOB_1)
    plan = inspect_residue(root, blobs)
    assert plan is not None

    (root / "surprise.txt").write_bytes(b"extra")
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"
    (root / "surprise.txt").unlink()

    tampered_blobs = {CANDIDATE_1: b"new blob data"}
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, tampered_blobs)
    assert exc_info.value.code == "recovery_conflict"


def test_archive_collision_and_unknown_content(tmp_path: Path) -> None:
    """Verify archive never overwrites unknown existing content."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"
    archive_root.mkdir()

    blobs = _make_blobs()
    temp_name = ".upload-collis12"
    (root / temp_name).write_bytes(BLOB_1[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None

    (archive_root / temp_name).write_bytes(b"different archived content")

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"
    assert (archive_root / temp_name).read_bytes() == b"different archived content"
    assert (root / temp_name).read_bytes() == BLOB_1[:5]

    (archive_root / temp_name).unlink()
    (archive_root / "unrelated_file.txt").write_bytes(b"foreign")

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"


def test_archive_retains_and_ignores_archive_temporary_artifacts(tmp_path: Path) -> None:
    """Verify known archive temporary artifacts (.archive-tmp-*) are safely tolerated."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"
    archive_root.mkdir()

    # Pre-existing leftover archive temporary file from an earlier crashed attempt
    leftover_archive_tmp = archive_root / f"{ARCHIVE_TEMP_PREFIX}old12345"
    leftover_archive_tmp.write_bytes(BLOB_1[:15])

    blobs = _make_blobs()
    temp_name = ".upload-safe1234"
    (root / temp_name).write_bytes(BLOB_1[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None

    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 1
    assert (archive_root / temp_name).read_bytes() == BLOB_1[:5]
    # Known archive temp artifact was safely ignored and tolerated
    assert leftover_archive_tmp.exists()


def test_fault_between_preserve_and_unlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify fault after archive publication but before source unlink is recoverable."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    temp_name = ".upload-fault123"
    temp_content = BLOB_1[:8]
    (root / temp_name).write_bytes(temp_content)

    plan = inspect_residue(root, blobs)
    assert plan is not None

    original_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self.name == temp_name and self.parent == root:
            raise OSError("simulated unlink fault")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_retry_required"

    assert (root / temp_name).read_bytes() == temp_content
    assert (archive_root / temp_name).read_bytes() == temp_content

    monkeypatch.undo()
    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 1
    assert receipt["preserved_bytes"] == len(temp_content)

    assert not (root / temp_name).exists()
    assert (archive_root / temp_name).read_bytes() == temp_content


def test_exact_retry_after_partial_completion(tmp_path: Path) -> None:
    """Verify retry after partial progress succeeds when missing temp is verified in archive."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    temp1 = ".upload-first123"
    temp2 = ".upload-second12"
    (root / temp1).write_bytes(BLOB_1[:4])
    (root / temp2).write_bytes(BLOB_2[:6])

    plan = inspect_residue(root, blobs)
    assert plan is not None
    assert plan.summary()["temp_count"] == 2

    archive_root.mkdir()
    (archive_root / temp1).write_bytes(BLOB_1[:4])
    (root / temp1).unlink()

    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 2
    assert receipt["preserved_bytes"] == len(BLOB_1[:4]) + len(BLOB_2[:6])

    assert not (root / temp1).exists()
    assert not (root / temp2).exists()
    assert (archive_root / temp1).read_bytes() == BLOB_1[:4]
    assert (archive_root / temp2).read_bytes() == BLOB_2[:6]

    (root / temp1).write_bytes(BLOB_1[:4])
    (root / temp2).write_bytes(BLOB_2[:6])
    plan2 = inspect_residue(root, blobs)
    assert plan2 is not None

    (root / temp1).unlink()
    (archive_root / temp1).unlink()

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan2, blobs)
    assert exc_info.value.code == "recovery_conflict"


def test_partial_archive_write_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify failure during archive writing leaves original intact and does not publish."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    temp_name = ".upload-partw123"
    temp_content = BLOB_1[:7]
    (root / temp_name).write_bytes(temp_content)

    plan = inspect_residue(root, blobs)
    assert plan is not None

    def failing_link(src, dst, **kwargs):
        raise OSError("simulated link failure")

    monkeypatch.setattr(os, "link", failing_link)

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_retry_required"

    assert (root / temp_name).read_bytes() == temp_content
    assert not (archive_root / temp_name).exists()

    monkeypatch.undo()


def test_no_candidate_blob_mutation(tmp_path: Path) -> None:
    """Verify candidate blobs dict is never mutated in any operation."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    frozen_keys = list(blobs.keys())
    frozen_values = list(blobs.values())

    (root / ".upload-nomut123").write_bytes(BLOB_1[:3])

    plan = inspect_residue(root, blobs)
    assert plan is not None
    assert list(blobs.keys()) == frozen_keys
    assert list(blobs.values()) == frozen_values
    assert blobs[CANDIDATE_1] is BLOB_1

    apply_residue(root, archive_root, plan, blobs)
    assert list(blobs.keys()) == frozen_keys
    assert list(blobs.values()) == frozen_values
    assert blobs[CANDIDATE_1] is BLOB_1


def test_restore_plan_validation() -> None:
    """Verify restore_plan strictly rejects corrupted or forged manifests."""
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan("not-a-dict")  # type: ignore[arg-type]
    assert exc_info.value.code == "recovery_invalid"

    with pytest.raises(RecoveryError) as exc_info:
        restore_plan({"version": 1})
    assert exc_info.value.code == "recovery_invalid"

    manifest = {
        "version": 1,
        "fingerprint": "0" * 64,
        "root_device": 1,
        "root_inode": 1,
        "temp_count": 1,
        "temp_bytes": 4,
        "temp_files": [
            {
                "name": ".upload-12345678",
                "sha256": hashlib.sha256(b"test").hexdigest(),
                "size": 4,
                "device": 1,
                "inode": 2,
                "mtime_ns": 100,
                "mode": stat.S_IFREG | 0o600,
                "links": 1,
            }
        ],
        "known_blobs": [],
    }
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"


def test_exception_privacy() -> None:
    """Verify RecoveryError only exposes fixed codes, never paths or data."""
    err = RecoveryError("recovery_conflict")
    assert str(err) == "recovery_conflict"
    assert err.code == "recovery_conflict"
    assert "upload" not in str(err)
    assert "Path" not in str(err)


def _make_valid_manifest(
    *,
    version: Any = 1,
    root_device: Any = 1,
    root_inode: Any = 1,
    temp_count: Any = 1,
    temp_bytes: Any = 4,
    temp_files: Any = None,
    known_blobs: Any = None,
) -> dict[str, Any]:
    if temp_files is None:
        temp_files = [
            {
                "name": ".upload-12345678",
                "sha256": hashlib.sha256(b"test").hexdigest(),
                "size": 4,
                "device": 1,
                "inode": 2,
                "mtime_ns": 100,
                "mode": stat.S_IFREG | 0o600,
                "links": 1,
            }
        ]
    if known_blobs is None:
        known_blobs = []

    stamp = {
        "version": version,
        "root_device": root_device,
        "root_inode": root_inode,
        "temp_count": temp_count,
        "temp_bytes": temp_bytes,
        "temp_files": temp_files,
        "known_blobs": known_blobs,
    }
    fingerprint = hashlib.sha256(_encode(stamp)).hexdigest()
    return {"fingerprint": fingerprint, **stamp}


def test_restore_plan_rejects_bool_version_and_types() -> None:
    """Verify restore_plan strictly rejects bool version, bool identities, and unexpected types."""
    manifest = _make_valid_manifest()
    manifest["version"] = True
    stamp = {k: v for k, v in manifest.items() if k != "fingerprint"}
    manifest["fingerprint"] = hashlib.sha256(_encode(stamp)).hexdigest()
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"

    manifest = _make_valid_manifest()
    manifest["version"] = False
    stamp = {k: v for k, v in manifest.items() if k != "fingerprint"}
    manifest["fingerprint"] = hashlib.sha256(_encode(stamp)).hexdigest()
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"

    manifest = _make_valid_manifest(root_device=True)
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"

    manifest = _make_valid_manifest(root_inode=True)
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"

    manifest = _make_valid_manifest(temp_count=True)
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"

    manifest = _make_valid_manifest(temp_bytes=True)
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"


def test_restore_plan_rejects_duplicate_names() -> None:
    """Verify restore_plan rejects duplicate names in temp_files and known_blobs."""
    t1 = {
        "name": ".upload-dup12345",
        "sha256": hashlib.sha256(b"t1").hexdigest(),
        "size": 2,
        "device": 1,
        "inode": 10,
        "mtime_ns": 100,
        "mode": stat.S_IFREG | 0o600,
        "links": 1,
    }
    t2 = {
        "name": ".upload-dup12345",
        "sha256": hashlib.sha256(b"t2").hexdigest(),
        "size": 2,
        "device": 1,
        "inode": 11,
        "mtime_ns": 100,
        "mode": stat.S_IFREG | 0o600,
        "links": 1,
    }
    manifest = _make_valid_manifest(temp_count=2, temp_bytes=4, temp_files=[t1, t2])
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"

    b1 = {
        "name": CANDIDATE_1,
        "sha256": hashlib.sha256(b"b1").hexdigest(),
        "size": 2,
        "device": 1,
        "inode": 20,
        "mtime_ns": 100,
        "mode": stat.S_IFREG | 0o600,
        "links": 1,
    }
    b2 = {
        "name": CANDIDATE_1,
        "sha256": hashlib.sha256(b"b2").hexdigest(),
        "size": 2,
        "device": 1,
        "inode": 21,
        "mtime_ns": 100,
        "mode": stat.S_IFREG | 0o600,
        "links": 1,
    }
    manifest_blobs = _make_valid_manifest(known_blobs=[b1, b2])
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest_blobs)
    assert exc_info.value.code == "recovery_invalid"


def test_restore_plan_rejects_more_than_64_known_blobs() -> None:
    """Verify restore_plan rejects more than 64 known blobs."""
    blobs_65 = [
        {
            "name": f"{i:064x}",
            "sha256": hashlib.sha256(b"b").hexdigest(),
            "size": 1,
            "device": 1,
            "inode": 100 + i,
            "mtime_ns": 100,
            "mode": stat.S_IFREG | 0o600,
            "links": 1,
        }
        for i in range(MAX_CANDIDATE_COUNT + 1)
    ]
    manifest = _make_valid_manifest(known_blobs=blobs_65)
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(manifest)
    assert exc_info.value.code == "recovery_invalid"


def test_restore_plan_rejects_invalid_modes_links_and_identities() -> None:
    """Verify restore_plan rejects invalid regular modes, links, and identities."""
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(_make_valid_manifest(root_device=-1))
    assert exc_info.value.code == "recovery_invalid"

    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(_make_valid_manifest(root_inode=-1))
    assert exc_info.value.code == "recovery_invalid"

    def make_temp_file_with(**kwargs: Any) -> dict[str, Any]:
        item = {
            "name": ".upload-12345678",
            "sha256": hashlib.sha256(b"test").hexdigest(),
            "size": 4,
            "device": 1,
            "inode": 2,
            "mtime_ns": 100,
            "mode": stat.S_IFREG | 0o600,
            "links": 1,
        }
        item.update(kwargs)
        return item

    for bad_mode in (stat.S_IFDIR | 0o755, stat.S_IFLNK | 0o777, 0, -1):
        m = _make_valid_manifest(temp_files=[make_temp_file_with(mode=bad_mode)])
        with pytest.raises(RecoveryError) as exc_info:
            restore_plan(m)
        assert exc_info.value.code == "recovery_invalid"

    for bad_links in (0, -1):
        m = _make_valid_manifest(temp_files=[make_temp_file_with(links=bad_links)])
        with pytest.raises(RecoveryError) as exc_info:
            restore_plan(m)
        assert exc_info.value.code == "recovery_invalid"

    for key in ("device", "inode", "mtime_ns", "size"):
        m = _make_valid_manifest(temp_files=[make_temp_file_with(**{key: -1})])
        with pytest.raises(RecoveryError) as exc_info:
            restore_plan(m)
        assert exc_info.value.code == "recovery_invalid"

    for key in ("device", "inode", "mtime_ns", "size", "mode", "links"):
        m = _make_valid_manifest(temp_files=[make_temp_file_with(**{key: True})])
        with pytest.raises(RecoveryError) as exc_info:
            restore_plan(m)
        assert exc_info.value.code == "recovery_invalid"


def test_restore_plan_rejects_inconsistent_link_counts_and_aggregate_limits() -> None:
    """Verify restore_plan rejects inconsistent link counts and aggregate limits."""
    t1 = {
        "name": ".upload-link1234",
        "sha256": hashlib.sha256(b"t1").hexdigest(),
        "size": 2,
        "device": 1,
        "inode": 50,
        "mtime_ns": 100,
        "mode": stat.S_IFREG | 0o600,
        "links": 2,
    }
    m = _make_valid_manifest(temp_count=1, temp_bytes=2, temp_files=[t1])
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(m)
    assert exc_info.value.code == "recovery_invalid"

    t2 = {
        "name": ".upload-link2345",
        "sha256": hashlib.sha256(b"t1").hexdigest(),
        "size": 2,
        "device": 1,
        "inode": 50,
        "mtime_ns": 100,
        "mode": stat.S_IFREG | 0o600,
        "links": 1,
    }
    t1_copy = dict(t1)
    t1_copy["links"] = 1
    m = _make_valid_manifest(temp_count=2, temp_bytes=4, temp_files=[t1_copy, t2])
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(m)
    assert exc_info.value.code == "recovery_invalid"

    t2_diff = {
        "name": ".upload-link2345",
        "sha256": hashlib.sha256(b"diff").hexdigest(),
        "size": 4,
        "device": 1,
        "inode": 50,
        "mtime_ns": 100,
        "mode": stat.S_IFREG | 0o600,
        "links": 2,
    }
    m = _make_valid_manifest(temp_count=2, temp_bytes=6, temp_files=[t1, t2_diff])
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(m)
    assert exc_info.value.code == "recovery_invalid"

    m = _make_valid_manifest(temp_count=1, temp_bytes=MAX_TEMP_AGGREGATE_BYTES + 1)
    with pytest.raises(RecoveryError) as exc_info:
        restore_plan(m)
    assert exc_info.value.code == "recovery_invalid"


def test_immutable_plan_and_validation_on_apply(tmp_path: Path) -> None:
    """Verify ResiduePlan holds immutable canonical bytes and apply_residue validates it."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    temp_name = ".upload-immut123"
    (root / temp_name).write_bytes(BLOB_1[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None
    assert isinstance(plan._manifest, bytes)

    with pytest.raises(RecoveryError) as exc_info:
        ResiduePlan({}, (), ())  # type: ignore[arg-type]
    assert exc_info.value.code == "recovery_invalid"

    with pytest.raises(RecoveryError) as exc_info:
        ResiduePlan("not-bytes", (), ())  # type: ignore[arg-type]
    assert exc_info.value.code == "recovery_invalid"

    manifest = plan.private_manifest()
    manifest["temp_count"] = 999
    assert plan.summary()["temp_count"] == 1
    assert plan.private_manifest()["temp_count"] == 1

    forged_plan = ResiduePlan(plan._manifest, (), ())
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, forged_plan, blobs)
    assert exc_info.value.code == "recovery_invalid"

    tampered_bytes_plan = ResiduePlan(b'{"fingerprint":"bad"}', plan._temp_files, plan._known_blobs)
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, tampered_bytes_plan, blobs)
    assert exc_info.value.code == "recovery_invalid"


def test_second_archive_failure_retains_both_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify failure during second archive preservation retains both originals in root."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    (root / CANDIDATE_1).write_bytes(BLOB_1)

    temp1 = ".upload-first123"
    temp2 = ".upload-second12"
    content1 = BLOB_2[:4]
    content2 = BLOB_2[:6]
    (root / temp1).write_bytes(content1)
    (root / temp2).write_bytes(content2)

    plan = inspect_residue(root, blobs)
    assert plan is not None
    assert plan.summary()["temp_count"] == 2

    original_link = os.link

    def failing_link(src, dst, **kwargs):
        if Path(dst).name == temp2:
            raise OSError("simulated second preserve error")
        return original_link(src, dst, **kwargs)

    monkeypatch.setattr(os, "link", failing_link)

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_retry_required"

    # Both originals MUST be retained and completely intact
    assert (root / temp1).exists()
    assert (root / temp1).read_bytes() == content1
    assert (root / temp2).exists()
    assert (root / temp2).read_bytes() == content2

    # Unpatch and verify retry succeeds
    monkeypatch.undo()
    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 2
    assert not (root / temp1).exists()
    assert not (root / temp2).exists()
    assert (archive_root / temp1).read_bytes() == content1
    assert (archive_root / temp2).read_bytes() == content2


def test_hardlink_publication_retry(tmp_path: Path) -> None:
    """Verify hardlink publication retry cleans up crash artifact and unlinks original."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"
    archive_root.mkdir()

    blobs = _make_blobs()
    temp_name = ".upload-hlretry1"
    temp_content = BLOB_1[:10]
    (root / temp_name).write_bytes(temp_content)

    plan = inspect_residue(root, blobs)
    assert plan is not None

    crash_tmp = archive_root / ".archive-tmp-hlpub123"
    crash_tmp.write_bytes(temp_content)
    dest_path = archive_root / temp_name
    os.link(crash_tmp, dest_path)

    assert crash_tmp.stat().st_nlink == 2
    assert dest_path.stat().st_nlink == 2

    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 1

    assert dest_path.exists()
    assert dest_path.stat().st_nlink == 1
    assert dest_path.read_bytes() == temp_content
    assert not crash_tmp.exists()
    assert not (root / temp_name).exists()


def test_hardlink_publication_crash_mismatch_denied(tmp_path: Path) -> None:
    """Verify archive hardlink publication with mismatched bytes is denied."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"
    archive_root.mkdir()

    blobs = _make_blobs()
    temp_name = ".upload-hlmis123"
    temp_content = BLOB_1[:25]
    (root / temp_name).write_bytes(temp_content)

    plan = inspect_residue(root, blobs)
    assert plan is not None

    crash_tmp = archive_root / ".archive-tmp-hlmis123"
    crash_tmp.write_bytes(BLOB_2[:25])
    dest_path = archive_root / temp_name
    os.link(crash_tmp, dest_path)

    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"


def test_archive_temp_prefix_strict_validation(tmp_path: Path) -> None:
    """Verify archive temp prefix requires exact regex and bounded candidate prefix."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"
    archive_root.mkdir()

    blobs = _make_blobs()
    temp_name = ".upload-pfx12345"
    (root / temp_name).write_bytes(BLOB_1[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None

    # Non-candidate prefix content in archive temp
    bad_content_tmp = archive_root / f"{ARCHIVE_TEMP_PREFIX}badcnt12"
    bad_content_tmp.write_bytes(b"completely unknown bytes")
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"
    bad_content_tmp.unlink()

    # Malformed names starting with prefix
    invalid_archive_names = [
        f"{ARCHIVE_TEMP_PREFIX}short",
        f"{ARCHIVE_TEMP_PREFIX}toolong123",
        f"{ARCHIVE_TEMP_PREFIX}UPPER123",
        f"{ARCHIVE_TEMP_PREFIX}special!",
    ]
    for inv_name in invalid_archive_names:
        p = archive_root / inv_name
        p.write_bytes(BLOB_1[:5])
        with pytest.raises(RecoveryError) as exc_info:
            apply_residue(root, archive_root, plan, blobs)
        assert exc_info.value.code == "recovery_conflict"
        p.unlink()

    # Directory starting with prefix
    dir_tmp = archive_root / f"{ARCHIVE_TEMP_PREFIX}12345678"
    dir_tmp.mkdir()
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"
    dir_tmp.rmdir()

    # Outside hardlink to archive temp
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    outside_hl_tmp = archive_root / f"{ARCHIVE_TEMP_PREFIX}outlink1"
    outside_hl_tmp.write_bytes(BLOB_1[:5])
    os.link(outside_hl_tmp, outside_dir / "hl")
    with pytest.raises(RecoveryError) as exc_info:
        apply_residue(root, archive_root, plan, blobs)
    assert exc_info.value.code == "recovery_conflict"


def test_early_bounds_before_reading_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify enumeration count and aggregate bytes are bounded BEFORE reading files."""
    root = tmp_path / "staged_root"
    root.mkdir()
    blobs = _make_blobs()

    # Directory with > 80 entries: must fail early before reading files
    for i in range(85):
        (root / f".upload-early{i:03d}").write_bytes(b"x")

    def failing_safe_read(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("_safe_read_file must NOT be called when bounds exceeded")

    monkeypatch.setattr(
        "custom_components.family_assistant.migration.temporary_recovery._safe_read_file",
        failing_safe_read,
    )

    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"

    monkeypatch.undo()
    for p in root.iterdir():
        p.unlink()

    # > 16 temp files: must fail before reading
    for i in range(17):
        (root / f".upload-t{i:07d}").write_bytes(b"x")

    monkeypatch.setattr(
        "custom_components.family_assistant.migration.temporary_recovery._safe_read_file",
        failing_safe_read,
    )

    with pytest.raises(RecoveryError) as exc_info:
        inspect_residue(root, blobs)
    assert exc_info.value.code == "recovery_conflict"

    monkeypatch.undo()


def test_safe_read_file_identity_and_post_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify _safe_read_file compares lstat/open/fstat identity and post-read fstat."""
    test_file = tmp_path / "test_read.bin"
    test_file.write_bytes(b"original content")

    real_fstat = os.fstat
    fstat_call_count = 0

    def tampered_fstat(fd: int) -> os.stat_result:
        nonlocal fstat_call_count
        fstat_call_count += 1
        st = real_fstat(fd)
        if fstat_call_count == 1:
            return os.stat_result(
                (
                    st.st_mode,
                    st.st_ino + 1,
                    st.st_dev,
                    st.st_nlink,
                    st.st_uid,
                    st.st_gid,
                    st.st_size,
                    st.st_atime,
                    st.st_mtime,
                    st.st_ctime,
                )
            )
        return st

    monkeypatch.setattr(os, "fstat", tampered_fstat)
    with pytest.raises(RecoveryError) as exc_info:
        _safe_read_file(test_file)
    assert exc_info.value.code == "recovery_conflict"

    monkeypatch.undo()

    fstat_call_count = 0

    def tampered_post_fstat(fd: int) -> os.stat_result:
        nonlocal fstat_call_count
        fstat_call_count += 1
        st = real_fstat(fd)
        if fstat_call_count == 2:
            return os.stat_result(
                (
                    st.st_mode,
                    st.st_ino,
                    st.st_dev,
                    st.st_nlink,
                    st.st_uid,
                    st.st_gid,
                    st.st_size + 1,
                    st.st_atime,
                    st.st_mtime,
                    st.st_ctime,
                )
            )
        return st

    monkeypatch.setattr(os, "fstat", tampered_post_fstat)
    with pytest.raises(RecoveryError) as exc_info:
        _safe_read_file(test_file)
    assert exc_info.value.code == "recovery_conflict"


def test_revalidate_pinned_source_and_never_touch_live_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify live blob is never touched and source is revalidated before unlink."""
    root = tmp_path / "staged_root"
    root.mkdir()
    archive_root = tmp_path / "archive_root"

    blobs = _make_blobs()
    blob_path = root / CANDIDATE_1
    blob_path.write_bytes(BLOB_1)

    temp_name = ".upload-reval123"
    temp_path = root / temp_name
    temp_path.write_bytes(BLOB_1[:5])

    plan = inspect_residue(root, blobs)
    assert plan is not None

    real_unlink = Path.unlink

    def unlink_tampering_source(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name == CANDIDATE_1:
            pytest.fail("Live blob must NEVER be unlinked!")
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink_tampering_source)

    receipt = apply_residue(root, archive_root, plan, blobs)
    assert receipt["preserved_count"] == 1
    assert blob_path.exists()
    assert blob_path.read_bytes() == BLOB_1
