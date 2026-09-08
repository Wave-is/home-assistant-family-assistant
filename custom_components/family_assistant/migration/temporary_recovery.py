"""Bounded filesystem recovery helpers for orphan staging uploads.

Internal recovery helpers for orphan temporary upload files (.upload-*) in an
unregistered staged root. This module is NOT an authorization API; the caller
(such as an owner-authenticated Home Assistant wrapper or wizard) must verify
matching HA intent, ensure the target is non-registered, hold the necessary
setup and registration locks, obtain fresh owner approval, and invoke these
helpers within a drained thread executor.

Limitations:
This implementation operates strictly within filesystem boundaries and relies
on OS-level invariants (such as canonical paths, link counts, and file identities).
It does NOT and cannot protect against a host administrator, root user, or any
process with arbitrary filesystem rewrite access to Home Assistant state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain import media
from ..media_storage import BLOB_KEY, _sync_directory

# Bounded capacity constants
MAX_CANDIDATE_COUNT = 64
MAX_CANDIDATE_AGGREGATE_BYTES = 96 * 1024 * 1024  # 96 MiB
MAX_TEMP_COUNT = 16
MAX_TEMP_AGGREGATE_BYTES = 32 * 1024 * 1024  # 32 MiB
MAX_FILE_BYTES = media.MAX_FILE_BYTES  # 10 MiB
MAX_TOTAL_ROOT_ENTRIES = MAX_CANDIDATE_COUNT + MAX_TEMP_COUNT  # 80
MAX_TOTAL_ARCHIVE_ENTRIES = MAX_CANDIDATE_COUNT + MAX_TEMP_COUNT  # 80

# Filename specifications
TEMP_NAME = re.compile(r"^\.upload-[a-z0-9_]{8}$")
ARCHIVE_TEMP_PREFIX = ".archive-tmp-"
ARCHIVE_TEMP_NAME = re.compile(r"^\.archive-tmp-[a-z0-9_]{8}$")


class RecoveryError(ValueError):
    """Fixed codes only; never expose paths, identities, or raw file content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _encode(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True)
class PinnedFile:
    name: str
    sha256: str
    size: int
    device: int
    inode: int
    mtime_ns: int
    mode: int
    links: int


@dataclass(frozen=True, repr=False)
class ResiduePlan:
    """Immutable plan for preserving reviewed staging upload residues."""

    _manifest: bytes = field(repr=False)
    _temp_files: tuple[PinnedFile, ...] = field(repr=False)
    _known_blobs: tuple[PinnedFile, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if type(self._manifest) is not bytes:
            raise RecoveryError("recovery_invalid")
        if not isinstance(self._temp_files, tuple) or not all(
            isinstance(t, PinnedFile) for t in self._temp_files
        ):
            raise RecoveryError("recovery_invalid")
        if not isinstance(self._known_blobs, tuple) or not all(
            isinstance(b, PinnedFile) for b in self._known_blobs
        ):
            raise RecoveryError("recovery_invalid")

    def __repr__(self) -> str:
        s = self.summary()
        return (
            f"ResiduePlan(fingerprint={s['fingerprint']!r}, "
            f"temp_count={s['temp_count']}, temp_bytes={s['temp_bytes']})"
        )

    def summary(self) -> dict[str, Any]:
        try:
            data = json.loads(self._manifest.decode("utf-8"))
            return {
                "fingerprint": data["fingerprint"],
                "temp_count": data["temp_count"],
                "temp_bytes": data["temp_bytes"],
            }
        except (ValueError, KeyError, UnicodeDecodeError):
            raise RecoveryError("recovery_invalid") from None

    def private_manifest(self) -> dict[str, Any]:
        """Deep-copy local-only JSON representation."""
        try:
            return json.loads(self._manifest.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise RecoveryError("recovery_invalid") from None


def _canonical_directory(path: Path) -> Path:
    if not isinstance(path, Path):
        raise RecoveryError("recovery_invalid")
    if not path.is_absolute():
        raise RecoveryError("recovery_invalid")
    if path.is_symlink():
        raise RecoveryError("recovery_invalid")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, ValueError):
        raise RecoveryError("recovery_invalid") from None
    if resolved != path:
        raise RecoveryError("recovery_invalid")
    if not resolved.is_dir():
        raise RecoveryError("recovery_invalid")

    # Verify no ancestor is a symlink
    cur = resolved
    while cur != cur.parent:
        if cur.is_symlink() or cur.resolve() != cur:
            raise RecoveryError("recovery_invalid")
        cur = cur.parent
    return resolved


def _prepare_archive_directory(path: Path, active_root: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise RecoveryError("recovery_invalid")

    # Find the deepest existing ancestor
    cur = path
    while not cur.exists():
        if cur.is_symlink() or cur == cur.parent:
            raise RecoveryError("recovery_invalid")
        cur = cur.parent

    # Deepest existing ancestor must be canonical directory with no symlink ancestors
    _canonical_directory(cur)

    # Ensure archive_root is outside active_root
    resolved_cur = cur.resolve(strict=True)
    if resolved_cur == active_root or active_root in resolved_cur.parents:
        raise RecoveryError("recovery_invalid")

    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        raise RecoveryError("recovery_retry_required") from None

    canonical = _canonical_directory(path)

    # Ensure canonical archive root is outside active_root and vice versa
    if (
        canonical == active_root
        or active_root in canonical.parents
        or canonical in active_root.parents
    ):
        raise RecoveryError("recovery_invalid")

    return canonical


def _safe_read_file(path: Path, max_bytes: int = MAX_FILE_BYTES) -> tuple[os.stat_result, bytes]:
    if path.is_symlink():
        raise RecoveryError("recovery_conflict")
    try:
        lstat_info = path.lstat()
    except (OSError, ValueError):
        raise RecoveryError("recovery_conflict") from None
    if not stat.S_ISREG(lstat_info.st_mode) or stat.S_ISLNK(lstat_info.st_mode):
        raise RecoveryError("recovery_conflict")
    if lstat_info.st_size > max_bytes or lstat_info.st_size < 0:
        raise RecoveryError("recovery_conflict")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise RecoveryError("recovery_conflict") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise RecoveryError("recovery_conflict")
        # Compare lstat and open fstat identity
        if (
            info.st_dev != lstat_info.st_dev
            or info.st_ino != lstat_info.st_ino
            or info.st_mode != lstat_info.st_mode
            or info.st_size != lstat_info.st_size
            or info.st_mtime_ns != lstat_info.st_mtime_ns
            or info.st_nlink != lstat_info.st_nlink
        ):
            raise RecoveryError("recovery_conflict")
        if info.st_size > max_bytes or info.st_size < 0:
            raise RecoveryError("recovery_conflict")
        with os.fdopen(fd, "rb") as stream:
            fd = None  # fd ownership transferred to stream
            content = stream.read(max_bytes + 1)
            if len(content) != info.st_size or len(content) > max_bytes:
                raise RecoveryError("recovery_conflict")
            post_info = os.fstat(stream.fileno())
            if not stat.S_ISREG(post_info.st_mode) or stat.S_ISLNK(post_info.st_mode):
                raise RecoveryError("recovery_conflict")
            if (
                post_info.st_dev != info.st_dev
                or post_info.st_ino != info.st_ino
                or post_info.st_mode != info.st_mode
                or post_info.st_size != info.st_size
                or post_info.st_mtime_ns != info.st_mtime_ns
                or post_info.st_nlink != info.st_nlink
            ):
                raise RecoveryError("recovery_conflict")
            return post_info, content
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _validate_blobs(blobs: dict[str, bytes]) -> None:
    if type(blobs) is not dict:
        raise RecoveryError("recovery_invalid")
    if len(blobs) > MAX_CANDIDATE_COUNT:
        raise RecoveryError("recovery_invalid")
    total_bytes = 0
    for key, val in blobs.items():
        if type(key) is not str or not BLOB_KEY.fullmatch(key):
            raise RecoveryError("recovery_invalid")
        if type(val) is not bytes:
            raise RecoveryError("recovery_invalid")
        if len(val) > MAX_FILE_BYTES:
            raise RecoveryError("recovery_invalid")
        total_bytes += len(val)
    if total_bytes > MAX_CANDIDATE_AGGREGATE_BYTES:
        raise RecoveryError("recovery_invalid")


def inspect_residue(root: Path, blobs: dict[str, bytes]) -> ResiduePlan | None:
    """Inspect an unregistered staging root for orphan temporary upload files.

    Returns an immutable ResiduePlan if temporary residues are found and all
    directory safety constraints are satisfied. Returns None if there are no
    residues and the directory is otherwise completely valid.
    Raises RecoveryError with a fixed code on any unknown, malformed, or unsafe state.
    """
    canonical_root = _canonical_directory(root)
    _validate_blobs(blobs)

    root_stat = canonical_root.stat(follow_symlinks=False)
    root_dev = root_stat.st_dev
    root_ino = root_stat.st_ino

    # Read and bound directory enumeration BEFORE reading any file contents
    try:
        scandir_iter = os.scandir(canonical_root)
    except OSError:
        raise RecoveryError("recovery_conflict") from None

    entry_count = 0
    candidate_entries: list[tuple[os.DirEntry[str], bool, bool]] = []
    early_temp_count = 0
    early_temp_bytes = 0
    early_blob_count = 0
    early_blob_bytes = 0

    with scandir_iter:
        for entry in scandir_iter:
            name = entry.name
            if name in (".", ".."):
                continue

            entry_count += 1
            if entry_count > MAX_TOTAL_ROOT_ENTRIES:
                raise RecoveryError("recovery_conflict")

            try:
                if entry.is_symlink() or entry.is_dir():
                    raise RecoveryError("recovery_conflict")
            except OSError:
                raise RecoveryError("recovery_conflict") from None

            is_blob = bool(BLOB_KEY.fullmatch(name))
            is_temp = bool(TEMP_NAME.fullmatch(name))

            if not is_blob and not is_temp:
                raise RecoveryError("recovery_conflict")

            if is_blob and name not in blobs:
                raise RecoveryError("recovery_conflict")

            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                raise RecoveryError("recovery_conflict") from None

            if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise RecoveryError("recovery_conflict")
            if st.st_size > MAX_FILE_BYTES or st.st_size < 0:
                raise RecoveryError("recovery_conflict")

            if is_temp:
                early_temp_count += 1
                if early_temp_count > MAX_TEMP_COUNT:
                    raise RecoveryError("recovery_conflict")
                early_temp_bytes += st.st_size
                if early_temp_bytes > MAX_TEMP_AGGREGATE_BYTES:
                    raise RecoveryError("recovery_conflict")
            else:
                early_blob_count += 1
                if early_blob_count > MAX_CANDIDATE_COUNT:
                    raise RecoveryError("recovery_conflict")
                early_blob_bytes += st.st_size
                if early_blob_bytes > MAX_CANDIDATE_AGGREGATE_BYTES:
                    raise RecoveryError("recovery_conflict")

            if (
                early_temp_bytes + early_blob_bytes
                > MAX_CANDIDATE_AGGREGATE_BYTES + MAX_TEMP_AGGREGATE_BYTES
            ):
                raise RecoveryError("recovery_conflict")

            candidate_entries.append((entry, is_blob, is_temp))

    scanned_blobs: dict[str, tuple[os.stat_result, bytes]] = {}
    scanned_temps: dict[str, tuple[os.stat_result, bytes]] = {}
    inode_map: dict[tuple[int, int], list[str]] = {}

    for entry, is_blob, _ in candidate_entries:
        name = entry.name
        entry_path = canonical_root / name
        info, content = _safe_read_file(entry_path, MAX_FILE_BYTES)

        dev_ino = (info.st_dev, info.st_ino)
        inode_map.setdefault(dev_ino, []).append(name)

        if is_blob:
            if content != blobs[name]:
                raise RecoveryError("recovery_conflict")
            scanned_blobs[name] = (info, content)
        else:
            if not any(cand.startswith(content) for cand in blobs.values()):
                raise RecoveryError("recovery_conflict")
            scanned_temps[name] = (info, content)

    temp_count = len(scanned_temps)
    if temp_count > MAX_TEMP_COUNT:
        raise RecoveryError("recovery_conflict")

    temp_bytes = sum(info.st_size for info, _ in scanned_temps.values())
    if temp_bytes > MAX_TEMP_AGGREGATE_BYTES:
        raise RecoveryError("recovery_conflict")

    # Hardlink accounting and crash-publication window checks:
    # Two or more in-directory aliases permitted ONLY if all hardlinks to that inode
    # are accounted for inside reviewed root and candidate bytes match; outside links refuse.
    for names in inode_map.values():
        local_count = len(names)
        for name in names:
            info = scanned_blobs[name][0] if name in scanned_blobs else scanned_temps[name][0]
            if info.st_nlink != local_count:
                raise RecoveryError("recovery_conflict")

        if local_count >= 2:
            content = (
                scanned_blobs[names[0]][1]
                if names[0] in scanned_blobs
                else scanned_temps[names[0]][1]
            )
            blob_names = [n for n in names if n in scanned_blobs]
            if not blob_names and not any(content == cand for cand in blobs.values()):
                raise RecoveryError("recovery_conflict")

    if temp_count == 0:
        return None

    pinned_temps = tuple(
        PinnedFile(
            name=name,
            sha256=hashlib.sha256(content).hexdigest(),
            size=info.st_size,
            device=info.st_dev,
            inode=info.st_ino,
            mtime_ns=info.st_mtime_ns,
            mode=info.st_mode,
            links=info.st_nlink,
        )
        for name, (info, content) in sorted(scanned_temps.items())
    )

    pinned_blobs = tuple(
        PinnedFile(
            name=name,
            sha256=hashlib.sha256(content).hexdigest(),
            size=info.st_size,
            device=info.st_dev,
            inode=info.st_ino,
            mtime_ns=info.st_mtime_ns,
            mode=info.st_mode,
            links=info.st_nlink,
        )
        for name, (info, content) in sorted(scanned_blobs.items())
    )

    stamp = {
        "version": 1,
        "root_device": root_dev,
        "root_inode": root_ino,
        "temp_count": temp_count,
        "temp_bytes": temp_bytes,
        "temp_files": [
            {
                "name": t.name,
                "sha256": t.sha256,
                "size": t.size,
                "device": t.device,
                "inode": t.inode,
                "mtime_ns": t.mtime_ns,
                "mode": t.mode,
                "links": t.links,
            }
            for t in pinned_temps
        ],
        "known_blobs": [
            {
                "name": b.name,
                "sha256": b.sha256,
                "size": b.size,
                "device": b.device,
                "inode": b.inode,
                "mtime_ns": b.mtime_ns,
                "mode": b.mode,
                "links": b.links,
            }
            for b in pinned_blobs
        ],
    }
    fingerprint = hashlib.sha256(_encode(stamp)).hexdigest()
    manifest = {"fingerprint": fingerprint, **stamp}
    manifest_bytes = _encode(manifest)

    return ResiduePlan(manifest_bytes, pinned_temps, pinned_blobs)


def restore_plan(manifest: dict[str, Any]) -> ResiduePlan:
    """Reconstruct an immutable ResiduePlan from a verified private manifest."""
    if type(manifest) is not dict:
        raise RecoveryError("recovery_invalid")

    expected_keys = {
        "version",
        "fingerprint",
        "root_device",
        "root_inode",
        "temp_count",
        "temp_bytes",
        "temp_files",
        "known_blobs",
    }
    if set(manifest) != expected_keys:
        raise RecoveryError("recovery_invalid")

    if (
        type(manifest["version"]) is not int
        or type(manifest["version"]) is bool
        or manifest["version"] != 1
    ):
        raise RecoveryError("recovery_invalid")

    fingerprint = manifest["fingerprint"]
    if type(fingerprint) is not str or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise RecoveryError("recovery_invalid")

    if (
        type(manifest["root_device"]) is not int
        or type(manifest["root_device"]) is bool
        or manifest["root_device"] < 0
    ):
        raise RecoveryError("recovery_invalid")
    if (
        type(manifest["root_inode"]) is not int
        or type(manifest["root_inode"]) is bool
        or manifest["root_inode"] < 0
    ):
        raise RecoveryError("recovery_invalid")

    temp_count = manifest["temp_count"]
    temp_bytes = manifest["temp_bytes"]
    if (
        type(temp_count) is not int
        or type(temp_count) is bool
        or not (0 < temp_count <= MAX_TEMP_COUNT)
    ):
        raise RecoveryError("recovery_invalid")
    if (
        type(temp_bytes) is not int
        or type(temp_bytes) is bool
        or not (0 <= temp_bytes <= MAX_TEMP_AGGREGATE_BYTES)
    ):
        raise RecoveryError("recovery_invalid")

    raw_temps = manifest["temp_files"]
    raw_blobs = manifest["known_blobs"]
    if type(raw_temps) is not list or type(raw_blobs) is not list:
        raise RecoveryError("recovery_invalid")

    if len(raw_temps) != temp_count:
        raise RecoveryError("recovery_invalid")

    if len(raw_blobs) > MAX_CANDIDATE_COUNT:
        raise RecoveryError("recovery_invalid")

    file_keys = {"name", "sha256", "size", "device", "inode", "mtime_ns", "mode", "links"}
    seen_names: set[str] = set()

    calc_temp_bytes = 0
    pinned_temps_list: list[PinnedFile] = []

    for item in raw_temps:
        if type(item) is not dict or set(item) != file_keys:
            raise RecoveryError("recovery_invalid")
        name = item["name"]
        if type(name) is not str or not TEMP_NAME.fullmatch(name):
            raise RecoveryError("recovery_invalid")
        if name in seen_names:
            raise RecoveryError("recovery_invalid")
        seen_names.add(name)

        if type(item["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise RecoveryError("recovery_invalid")

        for k in ("size", "device", "inode", "mtime_ns", "mode", "links"):
            if type(item[k]) is not int or type(item[k]) is bool:
                raise RecoveryError("recovery_invalid")

        if not (0 <= item["size"] <= MAX_FILE_BYTES):
            raise RecoveryError("recovery_invalid")
        if item["device"] < 0 or item["inode"] < 0:
            raise RecoveryError("recovery_invalid")
        if item["mtime_ns"] < 0:
            raise RecoveryError("recovery_invalid")
        if item["mode"] < 0 or not stat.S_ISREG(item["mode"]) or stat.S_ISLNK(item["mode"]):
            raise RecoveryError("recovery_invalid")
        if item["links"] <= 0:
            raise RecoveryError("recovery_invalid")

        calc_temp_bytes += item["size"]
        pinned_temps_list.append(PinnedFile(**item))

    if calc_temp_bytes != temp_bytes:
        raise RecoveryError("recovery_invalid")

    calc_blob_bytes = 0
    pinned_blobs_list: list[PinnedFile] = []

    for item in raw_blobs:
        if type(item) is not dict or set(item) != file_keys:
            raise RecoveryError("recovery_invalid")
        name = item["name"]
        if type(name) is not str or not BLOB_KEY.fullmatch(name):
            raise RecoveryError("recovery_invalid")
        if name in seen_names:
            raise RecoveryError("recovery_invalid")
        seen_names.add(name)

        if type(item["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise RecoveryError("recovery_invalid")

        for k in ("size", "device", "inode", "mtime_ns", "mode", "links"):
            if type(item[k]) is not int or type(item[k]) is bool:
                raise RecoveryError("recovery_invalid")

        if not (0 <= item["size"] <= MAX_FILE_BYTES):
            raise RecoveryError("recovery_invalid")
        if item["device"] < 0 or item["inode"] < 0:
            raise RecoveryError("recovery_invalid")
        if item["mtime_ns"] < 0:
            raise RecoveryError("recovery_invalid")
        if item["mode"] < 0 or not stat.S_ISREG(item["mode"]) or stat.S_ISLNK(item["mode"]):
            raise RecoveryError("recovery_invalid")
        if item["links"] <= 0:
            raise RecoveryError("recovery_invalid")

        calc_blob_bytes += item["size"]
        pinned_blobs_list.append(PinnedFile(**item))

    if calc_blob_bytes > MAX_CANDIDATE_AGGREGATE_BYTES:
        raise RecoveryError("recovery_invalid")

    # Inconsistent link counts and shared inode consistency check
    inode_groups: dict[tuple[int, int], list[PinnedFile]] = {}
    for pf in pinned_temps_list + pinned_blobs_list:
        inode_groups.setdefault((pf.device, pf.inode), []).append(pf)

    for group in inode_groups.values():
        local_count = len(group)
        first = group[0]
        for pf in group:
            if pf.links != local_count:
                raise RecoveryError("recovery_invalid")
            if pf.size != first.size or pf.mode != first.mode or pf.sha256 != first.sha256:
                raise RecoveryError("recovery_invalid")

    sorted_temps = sorted(pinned_temps_list, key=lambda x: x.name)
    sorted_blobs = sorted(pinned_blobs_list, key=lambda x: x.name)

    stamp = {
        "version": 1,
        "root_device": manifest["root_device"],
        "root_inode": manifest["root_inode"],
        "temp_count": temp_count,
        "temp_bytes": temp_bytes,
        "temp_files": [
            {
                "name": t.name,
                "sha256": t.sha256,
                "size": t.size,
                "device": t.device,
                "inode": t.inode,
                "mtime_ns": t.mtime_ns,
                "mode": t.mode,
                "links": t.links,
            }
            for t in sorted_temps
        ],
        "known_blobs": [
            {
                "name": b.name,
                "sha256": b.sha256,
                "size": b.size,
                "device": b.device,
                "inode": b.inode,
                "mtime_ns": b.mtime_ns,
                "mode": b.mode,
                "links": b.links,
            }
            for b in sorted_blobs
        ],
    }
    if hashlib.sha256(_encode(stamp)).hexdigest() != fingerprint:
        raise RecoveryError("recovery_invalid")

    manifest_copy = {"fingerprint": fingerprint, **stamp}
    manifest_bytes = _encode(manifest_copy)
    return ResiduePlan(
        manifest_bytes,
        tuple(sorted_temps),
        tuple(sorted_blobs),
    )


def apply_residue(
    root: Path,
    archive_root: Path,
    plan: ResiduePlan,
    blobs: dict[str, bytes],
) -> dict[str, Any]:
    """Preserve reviewed staging upload residues into a private archive root.

    Preserves each reviewed temporary file into caller-supplied archive_root via
    exclusive atomic publication, verifies durable byte equality, and only then
    unlinks the source temporary name from root.

    Returns a receipt summary with fingerprint, preserved_count, and preserved_bytes.
    Raises RecoveryError on any deviation or failure, preserving unverified originals.
    """
    if not isinstance(plan, ResiduePlan):
        raise RecoveryError("recovery_invalid")

    # Validate plan against canonical manifest bytes
    try:
        manifest_data = json.loads(plan._manifest.decode("utf-8"))
    except Exception:
        raise RecoveryError("recovery_invalid") from None

    validated_plan = restore_plan(manifest_data)
    if (
        validated_plan._manifest != plan._manifest
        or validated_plan._temp_files != plan._temp_files
        or validated_plan._known_blobs != plan._known_blobs
    ):
        raise RecoveryError("recovery_invalid")

    _validate_blobs(blobs)

    canonical_root = _canonical_directory(root)
    root_stat = canonical_root.stat(follow_symlinks=False)
    if (root_stat.st_dev, root_stat.st_ino) != (
        manifest_data["root_device"],
        manifest_data["root_inode"],
    ):
        raise RecoveryError("recovery_conflict")

    canonical_archive = _prepare_archive_directory(archive_root, canonical_root)

    plan_temp_map = {t.name: t for t in plan._temp_files}

    # Early bound enumeration of archive directory
    try:
        archive_scandir = os.scandir(canonical_archive)
    except OSError:
        raise RecoveryError("recovery_conflict") from None

    archive_count = 0
    raw_archive_entries: list[os.DirEntry[str]] = []
    early_archive_temp_count = 0
    early_archive_temp_bytes = 0
    early_archive_dest_count = 0
    early_archive_dest_bytes = 0

    with archive_scandir:
        for a_entry in archive_scandir:
            name = a_entry.name
            if name in (".", ".."):
                continue
            archive_count += 1
            if archive_count > MAX_TOTAL_ARCHIVE_ENTRIES:
                raise RecoveryError("recovery_conflict")
            try:
                if a_entry.is_symlink() or a_entry.is_dir():
                    raise RecoveryError("recovery_conflict")
            except OSError:
                raise RecoveryError("recovery_conflict") from None

            is_plan_temp = name in plan_temp_map
            is_archive_tmp = bool(ARCHIVE_TEMP_NAME.fullmatch(name))
            if not is_plan_temp and not is_archive_tmp:
                raise RecoveryError("recovery_conflict")

            try:
                st = a_entry.stat(follow_symlinks=False)
            except OSError:
                raise RecoveryError("recovery_conflict") from None

            if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise RecoveryError("recovery_conflict")
            if st.st_size > MAX_FILE_BYTES or st.st_size < 0:
                raise RecoveryError("recovery_conflict")

            if is_plan_temp:
                early_archive_dest_count += 1
                if early_archive_dest_count > MAX_TEMP_COUNT:
                    raise RecoveryError("recovery_conflict")
                early_archive_dest_bytes += st.st_size
                if early_archive_dest_bytes > MAX_TEMP_AGGREGATE_BYTES:
                    raise RecoveryError("recovery_conflict")
            else:
                early_archive_temp_count += 1
                if early_archive_temp_count > MAX_TEMP_COUNT:
                    raise RecoveryError("recovery_conflict")
                early_archive_temp_bytes += st.st_size
                if early_archive_temp_bytes > MAX_TEMP_AGGREGATE_BYTES:
                    raise RecoveryError("recovery_conflict")

            raw_archive_entries.append(a_entry)

    archive_dest_entries: dict[str, tuple[os.stat_result, bytes]] = {}
    archive_tmp_entries: dict[str, tuple[os.stat_result, bytes]] = {}
    archive_inode_map: dict[tuple[int, int], list[str]] = {}

    for a_entry in raw_archive_entries:
        name = a_entry.name
        a_info, a_content = _safe_read_file(Path(a_entry.path), MAX_FILE_BYTES)
        dev_ino = (a_info.st_dev, a_info.st_ino)
        archive_inode_map.setdefault(dev_ino, []).append(name)

        if name in plan_temp_map:
            target_t = plan_temp_map[name]
            if (
                a_info.st_size != target_t.size
                or hashlib.sha256(a_content).hexdigest() != target_t.sha256
            ):
                raise RecoveryError("recovery_conflict")
            archive_dest_entries[name] = (a_info, a_content)
        else:
            if not any(cand.startswith(a_content) for cand in blobs.values()):
                raise RecoveryError("recovery_conflict")
            archive_tmp_entries[name] = (a_info, a_content)

    # Validate hardlinks in archive directory:
    # Any inode:
    # 1 entry: st_nlink must be 1.
    # 2 entries: allowed ONLY if one is dest and one is archive temp, both st_nlink==2,
    #            identical bytes, matching target_t!
    # Otherwise: recovery_conflict.
    for names in archive_inode_map.values():
        local_count = len(names)
        if local_count == 1:
            name = names[0]
            info = (
                archive_dest_entries[name][0]
                if name in archive_dest_entries
                else archive_tmp_entries[name][0]
            )
            if info.st_nlink != 1:
                raise RecoveryError("recovery_conflict")
        elif local_count == 2:
            n1, n2 = names[0], names[1]
            dest_name = (
                n1 if n1 in archive_dest_entries else (n2 if n2 in archive_dest_entries else None)
            )
            tmp_name = (
                n1 if n1 in archive_tmp_entries else (n2 if n2 in archive_tmp_entries else None)
            )
            if dest_name is None or tmp_name is None:
                raise RecoveryError("recovery_conflict")
            d_info, d_content = archive_dest_entries[dest_name]
            t_info, t_content = archive_tmp_entries[tmp_name]
            if d_info.st_nlink != 2 or t_info.st_nlink != 2:
                raise RecoveryError("recovery_conflict")
            if d_info.st_size != t_info.st_size or d_content != t_content:
                raise RecoveryError("recovery_conflict")
            target_t = plan_temp_map[dest_name]
            if (
                d_info.st_size != target_t.size
                or hashlib.sha256(d_content).hexdigest() != target_t.sha256
            ):
                raise RecoveryError("recovery_conflict")
        else:
            raise RecoveryError("recovery_conflict")

    # Early bound enumeration of current root
    try:
        current_scandir = os.scandir(canonical_root)
    except OSError:
        raise RecoveryError("recovery_conflict") from None

    current_count = 0
    raw_current_entries: list[os.DirEntry[str]] = []
    early_cur_temp_count = 0
    early_cur_temp_bytes = 0
    early_cur_blob_count = 0
    early_cur_blob_bytes = 0

    plan_blob_map = {b.name: b for b in plan._known_blobs}

    with current_scandir:
        for entry in current_scandir:
            name = entry.name
            if name in (".", ".."):
                continue
            current_count += 1
            if current_count > MAX_TOTAL_ROOT_ENTRIES:
                raise RecoveryError("recovery_conflict")
            try:
                if entry.is_symlink() or entry.is_dir():
                    raise RecoveryError("recovery_conflict")
            except OSError:
                raise RecoveryError("recovery_conflict") from None

            is_blob = name in plan_blob_map
            is_temp = name in plan_temp_map
            if not is_blob and not is_temp:
                raise RecoveryError("recovery_conflict")

            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                raise RecoveryError("recovery_conflict") from None

            if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise RecoveryError("recovery_conflict")
            if st.st_size > MAX_FILE_BYTES or st.st_size < 0:
                raise RecoveryError("recovery_conflict")

            if is_temp:
                early_cur_temp_count += 1
                if early_cur_temp_count > MAX_TEMP_COUNT:
                    raise RecoveryError("recovery_conflict")
                early_cur_temp_bytes += st.st_size
                if early_cur_temp_bytes > MAX_TEMP_AGGREGATE_BYTES:
                    raise RecoveryError("recovery_conflict")
            else:
                early_cur_blob_count += 1
                if early_cur_blob_count > MAX_CANDIDATE_COUNT:
                    raise RecoveryError("recovery_conflict")
                early_cur_blob_bytes += st.st_size
                if early_cur_blob_bytes > MAX_CANDIDATE_AGGREGATE_BYTES:
                    raise RecoveryError("recovery_conflict")

            raw_current_entries.append(entry)

    current_names = {e.name for e in raw_current_entries}
    current_inode_map: dict[tuple[int, int], list[str]] = {}

    for b in plan._known_blobs:
        if b.name not in current_names:
            raise RecoveryError("recovery_conflict")
        p = canonical_root / b.name
        b_info, b_content = _safe_read_file(p, MAX_FILE_BYTES)
        if (
            b_info.st_dev != b.device
            or b_info.st_ino != b.inode
            or b_info.st_size != b.size
            or b_info.st_mtime_ns != b.mtime_ns
            or b_info.st_mode != b.mode
        ):
            raise RecoveryError("recovery_conflict")
        if b_content != blobs.get(b.name):
            raise RecoveryError("recovery_conflict")
        current_inode_map.setdefault((b_info.st_dev, b_info.st_ino), []).append(b.name)

    temps_to_preserve: list[tuple[PinnedFile, bytes]] = []

    for t in plan._temp_files:
        if t.name in current_names:
            p = canonical_root / t.name
            t_info, t_content = _safe_read_file(p, MAX_FILE_BYTES)
            if (
                t_info.st_dev != t.device
                or t_info.st_ino != t.inode
                or t_info.st_size != t.size
                or t_info.st_mtime_ns != t.mtime_ns
                or t_info.st_mode != t.mode
            ):
                raise RecoveryError("recovery_conflict")
            if hashlib.sha256(t_content).hexdigest() != t.sha256:
                raise RecoveryError("recovery_conflict")
            if not any(cand.startswith(t_content) for cand in blobs.values()):
                raise RecoveryError("recovery_conflict")
            current_inode_map.setdefault((t_info.st_dev, t_info.st_ino), []).append(t.name)
            temps_to_preserve.append((t, t_content))
        else:
            archived_p = canonical_archive / t.name
            try:
                if not archived_p.is_file() or archived_p.is_symlink():
                    raise RecoveryError("recovery_conflict")
            except OSError:
                raise RecoveryError("recovery_conflict") from None
            a_info, a_content = _safe_read_file(archived_p, MAX_FILE_BYTES)
            if a_info.st_size != t.size or hashlib.sha256(a_content).hexdigest() != t.sha256:
                raise RecoveryError("recovery_conflict")

    for names in current_inode_map.values():
        local_count = len(names)
        for name in names:
            p = canonical_root / name
            st = p.stat(follow_symlinks=False)
            if st.st_nlink != local_count:
                raise RecoveryError("recovery_conflict")
        if local_count >= 2:
            first_p = canonical_root / names[0]
            _, first_content = _safe_read_file(first_p, MAX_FILE_BYTES)
            if not any(first_content == cand for cand in blobs.values()):
                raise RecoveryError("recovery_conflict")

    # PHASE 1: Verify / publish durable archive copies of ALL selected temporaries
    for t, content in temps_to_preserve:
        dest = canonical_archive / t.name
        dest_verified = False
        if dest.exists():
            if dest.is_symlink() or not dest.is_file():
                raise RecoveryError("recovery_conflict")
            d_info, d_content = _safe_read_file(dest, MAX_FILE_BYTES)
            if (
                d_info.st_size == t.size
                and hashlib.sha256(d_content).hexdigest() == t.sha256
                and d_content == content
            ):
                # Clean up paired crash-publication archive temp if it exists
                dev_ino = (d_info.st_dev, d_info.st_ino)
                for tmp_name in archive_inode_map.get(dev_ino, []):
                    if tmp_name != t.name and ARCHIVE_TEMP_NAME.fullmatch(tmp_name):
                        try:
                            (canonical_archive / tmp_name).unlink(missing_ok=True)
                        except OSError:
                            raise RecoveryError("recovery_retry_required") from None
                        _sync_directory(canonical_archive)

                # Re-verify dest link count is 1
                try:
                    d_stat = dest.stat(follow_symlinks=False)
                except OSError:
                    raise RecoveryError("recovery_retry_required") from None
                if d_stat.st_nlink != 1:
                    raise RecoveryError("recovery_conflict")

                dest_verified = True
            else:
                raise RecoveryError("recovery_conflict")

        if not dest_verified:
            descriptor, tmp_name = tempfile.mkstemp(
                prefix=ARCHIVE_TEMP_PREFIX, dir=canonical_archive
            )
            tmp_path = Path(tmp_name)
            if not ARCHIVE_TEMP_NAME.fullmatch(tmp_path.name):
                try:
                    os.close(descriptor)
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise RecoveryError("recovery_conflict")

            published = False
            try:
                with os.fdopen(descriptor, "wb") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())

                tmp_info, tmp_content = _safe_read_file(tmp_path, MAX_FILE_BYTES)
                if (
                    tmp_info.st_size != t.size
                    or hashlib.sha256(tmp_content).hexdigest() != t.sha256
                    or tmp_content != content
                ):
                    raise RecoveryError("recovery_retry_required")

                try:
                    os.link(tmp_path, dest, follow_symlinks=False)
                except FileExistsError:
                    d_info, d_content = _safe_read_file(dest, MAX_FILE_BYTES)
                    if (
                        d_info.st_size != t.size
                        or hashlib.sha256(d_content).hexdigest() != t.sha256
                        or d_content != content
                    ):
                        raise RecoveryError("recovery_conflict") from None
                else:
                    tmp_path.unlink(missing_ok=True)

                _sync_directory(canonical_archive)

                d_info, d_content = _safe_read_file(dest, MAX_FILE_BYTES)
                if (
                    d_info.st_size != t.size
                    or hashlib.sha256(d_content).hexdigest() != t.sha256
                    or d_content != content
                ):
                    raise RecoveryError("recovery_retry_required")

                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                    _sync_directory(canonical_archive)

                d_stat = dest.stat(follow_symlinks=False)
                if d_stat.st_nlink != 1:
                    raise RecoveryError("recovery_retry_required")

                published = True
            except OSError:
                raise RecoveryError("recovery_retry_required") from None
            finally:
                if not published and tmp_path.exists():
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass

    # PHASE 2: Revalidate pinned source before unlink; never touch live blob.
    # Only runs after ALL selected temporaries are verified in archive.
    removed_links: dict[tuple[int, int], int] = {}
    for t, _ in temps_to_preserve:
        if not TEMP_NAME.fullmatch(t.name) or BLOB_KEY.fullmatch(t.name):
            raise RecoveryError("recovery_conflict")
        if t.name in blobs or t.name in plan_blob_map:
            raise RecoveryError("recovery_conflict")

        source_p = canonical_root / t.name
        if not source_p.exists() or source_p.is_symlink():
            raise RecoveryError("recovery_conflict")

        s_stat, source_content = _safe_read_file(source_p)
        inode_key = (t.device, t.inode)
        # The reviewed original link count changes when an earlier source name
        # was preserved/unlinked, including by a previous interrupted attempt.
        expected_links = len(current_inode_map[inode_key]) - removed_links.get(inode_key, 0)

        if not stat.S_ISREG(s_stat.st_mode) or stat.S_ISLNK(s_stat.st_mode):
            raise RecoveryError("recovery_conflict")

        if (
            s_stat.st_dev != t.device
            or s_stat.st_ino != t.inode
            or s_stat.st_size != t.size
            or s_stat.st_mtime_ns != t.mtime_ns
            or s_stat.st_mode != t.mode
            or s_stat.st_nlink != expected_links
            or hashlib.sha256(source_content).hexdigest() != t.sha256
        ):
            raise RecoveryError("recovery_conflict")

        try:
            source_p.unlink()
        except OSError:
            raise RecoveryError("recovery_retry_required") from None
        removed_links[inode_key] = removed_links.get(inode_key, 0) + 1

    _sync_directory(canonical_root)

    return {
        "fingerprint": plan.summary()["fingerprint"],
        "preserved_count": plan.summary()["temp_count"],
        "preserved_bytes": plan.summary()["temp_bytes"],
    }
