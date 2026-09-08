"""Bounded private migration ZIP decoding; no extraction, writes or authority."""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
import stat
import struct
import zipfile
import zlib
from dataclasses import dataclass, field

from .preflight import MAX_BYTES, _bounded_json
from .review import LegacySource, read_store_pair

MAX_BUNDLE_BYTES = 96 * 1024 * 1024
MAX_MANIFEST_BYTES = 24 * 1024 * 1024
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTOS_BYTES = 64 * 1024 * 1024
MAX_FILES = 513
_KEY = re.compile(r"[a-zA-Z0-9_]{1,64}")
_SHA = re.compile(r"[a-f0-9]{64}")


class CopyBundleError(ValueError):
    """Fixed code only; never source fields, paths or decoder diagnostics."""


def _fail():
    raise CopyBundleError("migration_copy_bundle_invalid")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _constant(_value):
    _fail()


def _central_directory(content):
    """Bound entry allocation before ZipFile parses untrusted central records.

    Only classic single-volume ZIP is needed for this sub-100 MiB format. Reject
    ZIP64, concatenation, trailing bytes and inconsistent counts/lengths.
    """
    offset = content.rfind(b"PK\x05\x06", max(0, len(content) - 65557))
    if offset < 0 or len(content) < offset + 22 or not content.startswith(b"PK\x03\x04"):
        _fail()
    _, disk, directory_disk, count, total, size, start, comment = struct.unpack_from(
        "<4s4H2IH", content, offset
    )
    if (
        disk != 0
        or directory_disk != 0
        or count != total
        or not 1 <= count <= MAX_FILES
        or size > 1024 * 1024
        or start + size != offset
        or offset + 22 + comment != len(content)
    ):
        _fail()
    cursor, seen = start, 0
    while cursor < offset:
        if cursor + 46 > offset or content[cursor : cursor + 4] != b"PK\x01\x02":
            _fail()
        name, extra, annotation = struct.unpack_from("<3H", content, cursor + 28)
        cursor += 46 + name + extra + annotation
        seen += 1
        if seen > MAX_FILES or cursor > offset:
            _fail()
    if seen != count or cursor != offset:
        _fail()


def _read(archive, info, limit):
    if not 0 < info.file_size <= limit:
        _fail()
    with archive.open(info, "r") as stream:
        content = stream.read(limit + 1)
    if len(content) != info.file_size or len(content) > limit:
        _fail()
    return content


def _source_bytes(value):
    if type(value) is not str or not 0 < len(value) <= 4 * ((MAX_BYTES + 2) // 3):
        _fail()
    raw = base64.b64decode(value.encode("ascii"), validate=True)
    if not 0 < len(raw) <= MAX_BYTES or base64.b64encode(raw).decode("ascii") != value:
        _fail()
    return raw


@dataclass(frozen=True, repr=False)
class LegacyCopyBundle:
    _source: LegacySource = field(repr=False)
    _metadata: bytes = field(repr=False)
    _blobs: tuple[tuple[str, bytes], ...] = field(repr=False)
    _source_bytes: int

    def __repr__(self):
        return "LegacyCopyBundle(private=True, activation_available=False)"

    def private_inputs(self):
        data = json.loads(self._metadata)
        return (
            self._source,
            data["member_mapping"],
            data["reviewer_sets"],
            data["photos"],
            dict(self._blobs),
        )

    def summary(self):
        return {
            "mode": "legacy_copy_bundle",
            "source_bytes": self._source_bytes,
            "photos": len(self._blobs),
            "photo_bytes": sum(len(content) for _, content in self._blobs),
            "coherence_verified": False,
        }


def parse_copy_bundle(content: bytes) -> LegacyCopyBundle:
    """Parse exact declared files only; later converters validate mappings/images."""
    try:
        if type(content) is not bytes or not 0 < len(content) <= MAX_BUNDLE_BYTES:
            _fail()
        _central_directory(content)
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            infos = archive.infolist()
            entries = {info.filename: info for info in infos}
            if (
                not 1 <= len(infos) <= MAX_FILES
                or len(entries) != len(infos)
                or "manifest.json" not in entries
            ):
                _fail()
            for info in infos:
                if (
                    info.is_dir()
                    or info.orig_filename != info.filename
                    or info.flag_bits & 0x41
                    or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or stat.S_IFMT(info.external_attr >> 16) not in {0, stat.S_IFREG}
                ):
                    _fail()
                # Reject a local-header/central-directory interpretation split.
                # Filename bytes are also checked by ZipFile.open; flags and
                # compression must match before any member is consumed.
                offset = info.header_offset
                if offset < 0 or offset + 30 > len(content):
                    _fail()
                if content[offset : offset + 4] != b"PK\x03\x04":
                    _fail()
                flags, compression = struct.unpack_from("<2H", content, offset + 6)
                if flags != info.flag_bits or compression != info.compress_type:
                    _fail()
            manifest = json.loads(
                _read(archive, entries["manifest.json"], MAX_MANIFEST_BYTES).decode("utf-8"),
                object_pairs_hook=_object,
                parse_constant=_constant,
            )
            if (
                type(manifest) is not dict
                or set(manifest)
                != {
                    "version",
                    "kind",
                    "assistant_store",
                    "court_store",
                    "member_mapping",
                    "reviewer_sets",
                    "photos",
                }
                or type(manifest["version"]) is not int
                or manifest["version"] != 1
                or manifest["kind"] != "family_assistant_legacy_shadow"
                or type(manifest["member_mapping"]) is not dict
                or type(manifest["reviewer_sets"]) is not dict
                or type(manifest["photos"]) is not list
                or len(manifest["photos"]) >= MAX_FILES
            ):
                _fail()
            assistant = _source_bytes(manifest.pop("assistant_store"))
            court = _source_bytes(manifest.pop("court_store"))
            if not _bounded_json(manifest):
                _fail()
            expected = {"manifest.json"}
            for row in manifest["photos"]:
                if (
                    type(row) is not dict
                    or set(row) != {"task_id", "event_sequence", "report_sha256", "attachment_key"}
                    or type(row["task_id"]) is not str
                    or not row["task_id"].strip()
                    or not 0 < len(row["task_id"]) <= 128
                    or type(row["event_sequence"]) is not int
                    or not 1 <= row["event_sequence"] <= 2**53 - 1
                    or type(row["report_sha256"]) is not str
                    or not _SHA.fullmatch(row["report_sha256"])
                    or type(row["attachment_key"]) is not str
                    or not _KEY.fullmatch(row["attachment_key"])
                ):
                    _fail()
                name = f"photos/{row['attachment_key']}"
                if name in expected:
                    _fail()
                expected.add(name)
            if set(entries) != expected:
                _fail()
            blobs, used = [], 0
            for row in manifest["photos"]:
                key = row["attachment_key"]
                blob = _read(
                    archive, entries[f"photos/{key}"], min(MAX_PHOTO_BYTES, MAX_PHOTOS_BYTES - used)
                )
                used += len(blob)
                blobs.append((key, blob))
            source = read_store_pair(assistant, court)
            return LegacyCopyBundle(
                source,
                json.dumps(
                    manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode(),
                tuple(blobs),
                len(assistant) + len(court),
            )
    except CopyBundleError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        RecursionError,
        binascii.Error,
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
        struct.error,
        zlib.error,
    ):
        raise CopyBundleError("migration_copy_bundle_invalid") from None
