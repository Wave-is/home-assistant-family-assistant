"""Pure archive-member safety checks for the encrypted HA acceptance helper."""

from __future__ import annotations

import io
import sys
import tarfile
from hashlib import sha256
from types import SimpleNamespace

import pytest

from tests.ha_encrypted_archive_smoke import _family_member, _read_family_files

STORE = "data/.storage/family_assistant.entry"
MEDIA = ("data", "family_assistant_data", "a" * 64)


def _member(name: str, member_type: bytes = tarfile.REGTYPE) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type = member_type
    return member


def _add_bytes(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(content)
    archive.addfile(member, io.BytesIO(content))


def _archive(path, entry_id: str, *, truncate_inner: bool = False):
    entry_hash = sha256(entry_id.encode()).hexdigest()
    inner_buffer = io.BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        for name in (
            "data",
            "data/.storage",
            "data/family_assistant_data",
            f"data/family_assistant_data/{entry_hash}",
            f"data/family_assistant_data/{entry_hash}/ab",
        ):
            inner.addfile(_member(name, tarfile.DIRTYPE))
        _add_bytes(inner, f"data/.storage/family_assistant.{entry_id}", b'{"data":{}}')
        _add_bytes(inner, "data/unrelated-large", b"x" * 8192)
        _add_bytes(inner, f"data/family_assistant_data/{entry_hash}/ab/photo.webp", b"webp")
    inner_content = inner_buffer.getvalue()
    if truncate_inner:
        inner_content = inner_content[: len(inner_content) // 2]
    with tarfile.open(path, mode="w:") as outer:
        _add_bytes(outer, "homeassistant.tar.gz", inner_content)


@pytest.fixture
def streaming_securetar(monkeypatch):
    def open_stream(*, fileobj, gzip, password):
        assert gzip is True and password == "synthetic"
        return tarfile.open(fileobj=fileobj, mode="r|gz")

    monkeypatch.setitem(sys.modules, "securetar", SimpleNamespace(SecureTarFile=open_stream))


def test_regular_files_and_directory_entries_are_classified() -> None:
    seen: set[str] = set()
    root = "/".join(MEDIA)

    assert _family_member(_member(root, tarfile.DIRTYPE), STORE, MEDIA, seen) == "directory"
    assert _family_member(_member(f"{root}/ab", tarfile.DIRTYPE), STORE, MEDIA, seen) == "directory"
    relative = _family_member(_member(f"{root}/ab/image.webp"), STORE, MEDIA, seen)
    assert relative.as_posix() == "ab/image.webp"
    assert _family_member(_member(STORE), STORE, MEDIA, seen) == "store"
    assert _family_member(_member("data/unrelated"), STORE, MEDIA, seen) is None


@pytest.mark.parametrize(
    ("name", "member_type"),
    [
        (f"{'/'.join(MEDIA)}/../escape", tarfile.REGTYPE),
        (f"{'/'.join(MEDIA)}/link", tarfile.SYMTYPE),
        (f"{'/'.join(MEDIA)}/device", tarfile.CHRTYPE),
        (f"{'/'.join(MEDIA)}/dir\\escape", tarfile.REGTYPE),
    ],
)
def test_unsafe_family_members_are_rejected(name: str, member_type: bytes) -> None:
    with pytest.raises(AssertionError):
        _family_member(_member(name, member_type), STORE, MEDIA, set())


def test_duplicate_or_file_directory_collision_is_rejected() -> None:
    seen: set[str] = set()
    name = f"{'/'.join(MEDIA)}/ab"
    assert _family_member(_member(name, tarfile.DIRTYPE), STORE, MEDIA, seen) == "directory"
    with pytest.raises(AssertionError):
        _family_member(_member(name), STORE, MEDIA, seen)


def test_family_reader_consumes_selected_members_in_forward_stream_order(
    tmp_path, streaming_securetar
) -> None:
    entry_id = "synthetic-entry"
    archive = tmp_path / "backup.tar"
    output = tmp_path / "media"
    output.mkdir()
    _archive(archive, entry_id)

    store, manifest = _read_family_files(archive, "synthetic", entry_id, output)

    assert store == b'{"data":{}}'
    assert manifest == {
        "ab/photo.webp": (4, sha256(b"webp").hexdigest()),
    }
    assert (output / "ab" / "photo.webp").read_bytes() == b"webp"


def test_family_reader_rejects_truncated_encrypted_inner_stream(
    tmp_path, streaming_securetar
) -> None:
    archive = tmp_path / "truncated.tar"
    output = tmp_path / "media"
    output.mkdir()
    _archive(archive, "synthetic-entry", truncate_inner=True)

    with pytest.raises((tarfile.TarError, EOFError, OSError, AssertionError)):
        _read_family_files(archive, "synthetic", "synthetic-entry", output)
