"""Deterministic in-memory packaging of explicitly supplied private source bytes.

No filesystem, providers, permission grant, image verification or coherent-source
claim. A caller must obtain the exports and associations through a reviewed flow.
"""

from __future__ import annotations

import base64
import io
import json
import stat
import zipfile

from . import copy_bundle as bundle_format
from .preflight import MAX_BYTES, _bounded_json
from .review import read_store_pair


class CopyPackageError(ValueError):
    """Fixed code only, without private field values or nested errors."""


def build_copy_bundle(
    *, assistant_store, court_store, member_mapping, reviewer_sets, photos, attachments
):
    """Return stable ZIP bytes, so identical selected input keeps its retry identity."""
    try:
        for source in (assistant_store, court_store):
            if type(source) is not bytes or not 0 < len(source) <= MAX_BYTES:
                raise ValueError
        if (
            type(member_mapping) is not dict
            or type(reviewer_sets) is not dict
            or type(photos) is not list
            or type(attachments) is not dict
            or len(photos) >= bundle_format.MAX_FILES
            or len(attachments) != len(photos)
        ):
            raise ValueError
        metadata = {
            "member_mapping": member_mapping,
            "reviewer_sets": reviewer_sets,
            "photos": photos,
        }
        if not _bounded_json(metadata):
            raise ValueError
        keys = set()
        if any(type(key) is not str for key in attachments):
            raise ValueError
        for row in photos:
            if type(row) is not dict or set(row) != {
                "task_id",
                "event_sequence",
                "report_sha256",
                "attachment_key",
            }:
                raise ValueError
            key = row["attachment_key"]
            if type(key) is not str or not bundle_format._KEY.fullmatch(key) or key in keys:
                raise ValueError
            if (
                type(row["task_id"]) is not str
                or not row["task_id"].strip()
                or not 0 < len(row["task_id"]) <= 128
                or type(row["event_sequence"]) is not int
                or not 1 <= row["event_sequence"] <= 2**53 - 1
                or type(row["report_sha256"]) is not str
                or not bundle_format._SHA.fullmatch(row["report_sha256"])
            ):
                raise ValueError
            keys.add(key)
        if keys != attachments.keys():
            raise ValueError
        used = 0
        for content in attachments.values():
            if type(content) is not bytes or not 0 < len(content) <= bundle_format.MAX_PHOTO_BYTES:
                raise ValueError
            used += len(content)
            if used > bundle_format.MAX_PHOTOS_BYTES:
                raise ValueError
        # Validate bounded Store wrappers before constructing their base64 payload.
        read_store_pair(assistant_store, court_store)
        manifest = json.dumps(
            {
                "version": 1,
                "kind": "family_assistant_legacy_shadow",
                "assistant_store": base64.b64encode(assistant_store).decode("ascii"),
                "court_store": base64.b64encode(court_store).decode("ascii"),
                **metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        if len(manifest) > bundle_format.MAX_MANIFEST_BYTES:
            raise ValueError
        files = {
            "manifest.json": manifest,
            **{f"photos/{key}": value for key, value in attachments.items()},
        }
        # Stored members with ASCII names and no extras/comments have exact header
        # overhead. Bound the complete allocation before opening the output stream.
        expected_size = 22 + sum(76 + 2 * len(name) + len(value) for name, value in files.items())
        if expected_size > bundle_format.MAX_BUNDLE_BYTES:
            raise ValueError
        output = io.BytesIO()
        with zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_STORED, allowZip64=False
        ) as archive:
            for name, content in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, content)
        result = output.getvalue()
        if len(result) != expected_size:
            raise ValueError
        bundle_format.parse_copy_bundle(result)
        return result
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        OverflowError,
        UnicodeError,
        RecursionError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ):
        raise CopyPackageError("migration_copy_package_invalid") from None
