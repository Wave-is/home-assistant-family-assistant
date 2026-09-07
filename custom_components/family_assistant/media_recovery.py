"""Bounded, private-directory-only inventory of abandoned media files.

This scanner never decides domain ownership. The caller supplies freshly
protected blob keys and runs it without concurrent upload publication. Unknown
names, symlinks, unusual hard links and recent files are retained, not guessed at.
All methods run in the storage executor, never the Home Assistant event loop.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .domain.validation import DomainError
from .media_storage import BLOB_KEY, _path, _sync_directory

SCAN_LIMIT = 256
LINK_LIMIT = 20_000
TEMP_GRACE_SECONDS = 3600
ORPHAN_GRACE_SECONDS = 86400
TEMP_NAME = re.compile(r"\.upload-[a-z0-9_]{8}")


@dataclass(frozen=True)
class FileStamp:
    name: str
    device: int
    inode: int
    size: int
    modified_ns: int
    links: int
    mode: int

    @classmethod
    def from_stat(cls, name, info):
        return cls(
            name,
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_nlink,
            info.st_mode,
        )

    @property
    def identity(self):
        return self.device, self.inode


def _root_identity(root: Path):
    _path(root, "0" * 64)  # Canonical root check, not an actual blob operation.
    try:
        info = root.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise DomainError("media_unavailable")
    return info.st_dev, info.st_ino


class DirectoryInventory:
    """Keep a bounded scandir cursor so large directories do not starve expiry."""

    def __init__(self, root: Path):
        self.root = root
        self._iterator = None
        self._identity = None
        self._links = {}
        self._next_links = {}

    def close(self):
        if self._iterator is not None:
            self._iterator.close()
        self._iterator = None
        self._identity = None
        self._links.clear()
        self._next_links.clear()

    def scan(self, limit=SCAN_LIMIT):
        identity = _root_identity(self.root)
        if identity is None:
            self.close()
            return [], True
        if self._iterator is not None and identity != self._identity:
            self.close()
            raise DomainError("media_unavailable")
        if self._iterator is None:
            self._identity = identity
            self._iterator = os.scandir(self.root)
            self._next_links = {}
        result = []
        for _ in range(limit):
            try:
                item = next(self._iterator)
            except StopIteration:
                self._iterator.close()
                self._iterator = None
                self._links = self._next_links
                self._next_links = {}
                return result, True
            try:
                # DirEntry.stat deliberately returns zero inode/device/link count
                # on Windows. Fresh os.stat is also required for recovery identity.
                info = os.stat(item.path, follow_symlinks=False)
            except FileNotFoundError:
                continue
            stamp = FileStamp.from_stat(item.name, info)
            result.append(stamp)
            if (
                BLOB_KEY.fullmatch(stamp.name)
                and stat.S_ISREG(stamp.mode)
                and len(self._next_links) < LINK_LIMIT
            ):
                self._next_links[stamp.identity] = stamp.name
        return result, False

    def linked_blob(self, stamp):
        return self._next_links.get(stamp.identity) or self._links.get(stamp.identity)


def remove_abandoned(root: Path, stamp: FileStamp, now: float, protected: set[str], *, linked=None):
    """Re-stat exact candidates immediately before scoped, nonrecursive unlink.

    Return false for recent/changed/protected files. Unsafe candidates raise a
    code-only error; a legitimate hard-link publication residue is recoverable
    only when the second name is independently verified inside this same root.
    """
    _root_identity(root)
    is_temp = TEMP_NAME.fullmatch(stamp.name) is not None
    is_blob = BLOB_KEY.fullmatch(stamp.name) is not None
    if not is_temp and not is_blob:
        raise DomainError("media_unavailable")
    if is_blob and stamp.name in protected:
        return False
    grace = TEMP_GRACE_SECONDS if is_temp else ORPHAN_GRACE_SECONDS
    if now - stamp.modified_ns / 1_000_000_000 < grace:
        return False
    path = root / stamp.name
    try:
        current = FileStamp.from_stat(stamp.name, path.stat(follow_symlinks=False))
    except FileNotFoundError:
        return False
    if current != stamp:
        return False
    if not stat.S_ISREG(current.mode):
        raise DomainError("media_unavailable")
    if current.links != 1:
        if not is_temp or current.links != 2 or not isinstance(linked, str):
            raise DomainError("media_unavailable")
        target = _path(root, linked)
        try:
            target_info = target.stat(follow_symlinks=False)
        except FileNotFoundError:
            raise DomainError("media_unavailable") from None
        if (
            not stat.S_ISREG(target_info.st_mode)
            or target_info.st_nlink != 2
            or (target_info.st_dev, target_info.st_ino) != current.identity
        ):
            raise DomainError("media_unavailable")
    path.unlink()
    _sync_directory(root)
    return True
