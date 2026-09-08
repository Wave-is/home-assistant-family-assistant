"""Real in-memory ZIP inputs; no extraction, source mutation or image decoding."""

import base64
import io
import json
import stat
import struct
import warnings
import zipfile
from copy import deepcopy

import pytest
from ha_legacy_archive_smoke import synthetic_source

from custom_components.family_assistant.migration import copy_bundle as module


def manifest():
    assistant, court, mapping, _ = synthetic_source(lifecycle=True)
    return {
        "version": 1,
        "kind": "family_assistant_legacy_shadow",
        "assistant_store": base64.b64encode(assistant).decode(),
        "court_store": base64.b64encode(court).decode(),
        "member_mapping": mapping,
        "reviewer_sets": {"T000004": ["old-parent"]},
        "photos": [],
    }


def zipped(data=None, *, raw_manifest=None, extras=(), compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with (
        warnings.catch_warnings(),
        zipfile.ZipFile(buffer, "w", compression=compression) as archive,
    ):
        warnings.simplefilter("ignore", UserWarning)
        archive.writestr(
            "manifest.json",
            raw_manifest if raw_manifest is not None else json.dumps(data or manifest()).encode(),
        )
        for name, content in extras:
            archive.writestr(name, content)
    return buffer.getvalue()


def photo(key="image_1"):
    return {
        "task_id": "T000004",
        "event_sequence": 6,
        "report_sha256": "a" * 64,
        "attachment_key": key,
    }


@pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_valid_pair_preserves_exact_source_and_defensive_metadata_copies(compression):
    source = manifest()
    original = deepcopy(source)
    bundle = module.parse_copy_bundle(zipped(source, compression=compression))
    legacy, mapping, reviewers, photos, blobs = bundle.private_inputs()
    assert legacy._assistant == base64.b64decode(source["assistant_store"])
    assert legacy._court == base64.b64decode(source["court_store"])
    assert mapping == source["member_mapping"] and reviewers == source["reviewer_sets"]
    assert photos == [] and blobs == {}
    mapping.clear()
    reviewers.clear()
    assert bundle.private_inputs()[1] == source["member_mapping"]
    assert bundle.summary() == {
        "mode": "legacy_copy_bundle",
        "source_bytes": len(legacy._assistant) + len(legacy._court),
        "photos": 0,
        "photo_bytes": 0,
        "coherence_verified": False,
    }
    assert source == original and "old-parent" not in repr(bundle)


def test_photo_bytes_are_preserved_without_claiming_a_valid_image_or_matching_event():
    source = manifest()
    source["photos"] = [photo()]
    bundle = module.parse_copy_bundle(zipped(source, extras=[("photos/image_1", b"not an image")]))
    assert bundle.private_inputs()[-1] == {"image_1": b"not an image"}
    assert bundle.summary()["photos"] == 1 and bundle.summary()["photo_bytes"] == 12
    assert "T000004" not in repr(bundle) and "old-parent" not in json.dumps(bundle.summary())


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "kind",
        "extra",
        "missing",
        "base64",
        "base64_newline",
        "base64_padding",
        "store_wrapper",
        "mapping",
        "reviewers",
        "photos",
        "missing_photo",
        "extra_photo",
        "duplicate_photo",
        "path",
        "task_length",
        "task_empty",
        "event_bool",
        "event_negative",
        "sha",
    ],
)
def test_malformed_manifest_or_file_set_has_fixed_private_error(fault):
    source, extras = manifest(), []
    if fault == "version":
        source["version"] = True
    elif fault == "kind":
        source["kind"] = "private unknown format"
    elif fault == "extra":
        source["unreviewed"] = "private hidden data"
    elif fault == "missing":
        source.pop("court_store")
    elif fault == "base64":
        source["court_store"] = "!!PRIVATE!!"
    elif fault == "base64_newline":
        source["court_store"] += "\n"
    elif fault == "base64_padding":
        source["court_store"] += "="
    elif fault == "store_wrapper":
        source["court_store"] = base64.b64encode(b'{"private":"wrong Store"}').decode()
    elif fault == "mapping":
        source["member_mapping"] = []
    elif fault == "reviewers":
        source["reviewer_sets"] = []
    elif fault == "photos":
        source["photos"] = {}
    else:
        source["photos"] = [photo()]
        extras = [("photos/image_1", b"content")]
        if fault == "missing_photo":
            extras = []
        elif fault == "extra_photo":
            extras.append(("photos/unselected", b"private"))
        elif fault == "duplicate_photo":
            source["photos"].append(photo())
        elif fault == "path":
            source["photos"][0]["attachment_key"] = "../secret"
        elif fault == "task_length":
            source["photos"][0]["task_id"] = " " * 129 + "T1"
        elif fault == "task_empty":
            source["photos"][0]["task_id"] = " "
        elif fault == "event_bool":
            source["photos"][0]["event_sequence"] = True
        elif fault == "event_negative":
            source["photos"][0]["event_sequence"] = -1
        elif fault == "sha":
            source["photos"][0]["report_sha256"] = "A" * 64
    with pytest.raises(module.CopyBundleError, match="^migration_copy_bundle_invalid$"):
        module.parse_copy_bundle(zipped(source, extras=extras))


@pytest.mark.parametrize(
    "raw", [b'{"version":1,"version":1}', b'{"value":NaN}', b"\xff", b"[]", b"[" * 1500]
)
def test_duplicate_nonfinite_unencodable_or_deep_json_is_rejected(raw):
    with pytest.raises(module.CopyBundleError, match="^migration_copy_bundle_invalid$"):
        module.parse_copy_bundle(zipped(raw_manifest=raw))


@pytest.mark.parametrize(
    "fault",
    [
        "trailing",
        "prefix",
        "duplicate",
        "directory",
        "symlink",
        "compression",
        "count",
        "directory_size",
        "encryption",
        "truncated",
    ],
)
def test_untrusted_zip_structure_is_checked_before_extracting_anything(fault):
    extras, compression = [], zipfile.ZIP_STORED
    if fault == "duplicate":
        extras = [("manifest.json", b"private duplicate")]
    if fault == "directory":
        extras = [("photos/", b"")]
    if fault == "symlink":
        info = zipfile.ZipInfo("photos/image_1")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        extras = [(info, b"../../private-file")]
    if fault == "compression":
        compression = zipfile.ZIP_BZIP2
    raw = zipped(extras=extras, compression=compression)
    if fault == "trailing":
        raw += b"private appendix"
    if fault == "prefix":
        raw = b"private prefix" + raw
    if fault == "count":
        raw = bytearray(raw)
        struct.pack_into("<2H", raw, len(raw) - 22 + 8, 60000, 60000)
        raw = bytes(raw)
    if fault == "directory_size":
        raw = bytearray(raw)
        struct.pack_into("<I", raw, len(raw) - 22 + 12, 2**31)
        raw = bytes(raw)
    if fault == "encryption":
        raw = bytearray(raw)
        central = raw.index(b"PK\x01\x02")
        struct.pack_into("<H", raw, central + 8, 1)
        raw = bytes(raw)
    if fault == "truncated":
        raw = raw[:-20]
    with pytest.raises(module.CopyBundleError, match="^migration_copy_bundle_invalid$"):
        module.parse_copy_bundle(raw)


@pytest.mark.parametrize(
    "bound",
    ["MAX_BUNDLE_BYTES", "MAX_MANIFEST_BYTES", "MAX_PHOTO_BYTES", "MAX_PHOTOS_BYTES", "MAX_FILES"],
)
def test_limits_are_enforced_without_allocating_large_input(monkeypatch, bound):
    source = manifest()
    source["photos"] = [photo("one"), photo("two")]
    raw = zipped(source, extras=[("photos/one", b"123456"), ("photos/two", b"123456")])
    limit = 1 if bound == "MAX_FILES" else (5 if bound == "MAX_PHOTO_BYTES" else 10)
    monkeypatch.setattr(module, bound, limit)
    with pytest.raises(module.CopyBundleError, match="^migration_copy_bundle_invalid$"):
        module.parse_copy_bundle(raw)


@pytest.mark.parametrize("fault", ["flags", "compression"])
def test_local_header_cannot_disagree_with_central_directory(fault):
    raw = bytearray(zipped(compression=zipfile.ZIP_STORED))
    struct.pack_into("<H", raw, 6 if fault == "flags" else 8, 1 if fault == "flags" else 8)
    with pytest.raises(module.CopyBundleError, match="^migration_copy_bundle_invalid$"):
        module.parse_copy_bundle(bytes(raw))
