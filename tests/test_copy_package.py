"""Deterministic actual ZIP output from exclusively synthetic private exports."""

import io
import json
import stat
import zipfile
from copy import deepcopy

import pytest
from ha_legacy_archive_smoke import synthetic_source
from test_copy_bundle import photo

from custom_components.family_assistant.migration import copy_package as module


@pytest.fixture
def inputs():
    assistant, court, mapping, _ = synthetic_source()
    return dict(
        assistant_store=assistant,
        court_store=court,
        member_mapping=mapping,
        reviewer_sets={"T000004": ["old-parent"]},
        photos=[photo("z"), photo("a")],
        attachments={"z": b"private synthetic z", "a": b"private synthetic a"},
    )


def test_real_roundtrip_determinism_and_no_input_mutation(inputs):
    before = deepcopy(inputs)
    value = module.build_copy_bundle(**inputs)
    reordered = deepcopy(inputs)
    reordered["member_mapping"] = dict(reversed(list(inputs["member_mapping"].items())))
    reordered["attachments"] = dict(reversed(list(inputs["attachments"].items())))
    assert value == module.build_copy_bundle(**reordered)
    assert inputs == before
    bundle = module.bundle_format.parse_copy_bundle(value)
    source, mapping, reviewers, photos, blobs = bundle.private_inputs()
    assert (source._assistant, source._court) == (inputs["assistant_store"], inputs["court_store"])
    assert (mapping, reviewers, photos, blobs) == tuple(
        inputs[key] for key in ("member_mapping", "reviewer_sets", "photos", "attachments")
    )
    with zipfile.ZipFile(io.BytesIO(value)) as archive:
        assert archive.namelist() == ["manifest.json", "photos/a", "photos/z"]
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.external_attr >> 16 == stat.S_IFREG | 0o600
    assert bundle.summary()["coherence_verified"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "source_type",
        "source_wrapper",
        "mapping_type",
        "reviewers_type",
        "photos_type",
        "blobs_type",
        "missing",
        "extra",
        "duplicate",
        "path",
        "blob_type",
        "empty",
        "bool_sequence",
        "sha",
        "bad_task",
        "extra_photo_field",
        "nan",
        "cycle",
    ],
)
def test_rejects_invalid_inputs_without_printing_private_values(inputs, fault):
    if fault == "source_type":
        inputs["assistant_store"] = "private-canary"
    elif fault == "source_wrapper":
        inputs["court_store"] = b'{"private-canary":1}'
    elif fault == "mapping_type":
        inputs["member_mapping"] = []
    elif fault == "reviewers_type":
        inputs["reviewer_sets"] = []
    elif fault == "photos_type":
        inputs["photos"] = ()
    elif fault == "blobs_type":
        inputs["attachments"] = []
    elif fault == "missing":
        inputs["attachments"].pop("a")
    elif fault == "extra":
        inputs["attachments"]["other"] = b"private-canary"
    elif fault == "duplicate":
        inputs["photos"][1] = inputs["photos"][0]
    elif fault == "path":
        inputs["photos"][0]["attachment_key"] = "../private-canary"
    elif fault == "blob_type":
        inputs["attachments"]["a"] = bytearray(b"private-canary")
    elif fault == "empty":
        inputs["attachments"]["a"] = b""
    elif fault == "bool_sequence":
        inputs["photos"][0]["event_sequence"] = True
    elif fault == "sha":
        inputs["photos"][0]["report_sha256"] = "private-canary"
    elif fault == "bad_task":
        inputs["photos"][0]["task_id"] = " "
    elif fault == "extra_photo_field":
        inputs["photos"][0]["untrusted"] = "private-canary"
    elif fault == "nan":
        inputs["member_mapping"]["bad"] = float("nan")
    else:
        inputs["member_mapping"]["loop"] = inputs["member_mapping"]
    with pytest.raises(module.CopyPackageError, match="^migration_copy_package_invalid$") as error:
        module.build_copy_bundle(**inputs)
    assert "private-canary" not in str(error.value)


@pytest.mark.parametrize(
    "limit,value",
    [
        ("MAX_FILES", 2),
        ("MAX_PHOTO_BYTES", 2),
        ("MAX_PHOTOS_BYTES", 30),
        ("MAX_MANIFEST_BYTES", 1),
        ("MAX_BUNDLE_BYTES", 1),
    ],
)
def test_bounds_are_checked_without_writing_oversized_zip(inputs, monkeypatch, limit, value):
    monkeypatch.setattr(module.bundle_format, limit, value)
    monkeypatch.setattr(
        module.zipfile,
        "ZipFile",
        lambda *_args, **_kwargs: pytest.fail("ZIP allocated before bound check"),
    )
    with pytest.raises(module.CopyPackageError):
        module.build_copy_bundle(**inputs)


def test_source_size_and_future_wrapper_version_are_rejected(inputs, monkeypatch):
    monkeypatch.setattr(module, "MAX_BYTES", 2)
    with pytest.raises(module.CopyPackageError):
        module.build_copy_bundle(**inputs)
    monkeypatch.undo()
    raw = json.loads(inputs["assistant_store"])
    raw["version"] = True
    inputs["assistant_store"] = json.dumps(raw).encode()
    with pytest.raises(module.CopyPackageError):
        module.build_copy_bundle(**inputs)
