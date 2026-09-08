"""Tests for copy_index: owner-scoped index, candidate reload, and authority guards."""

import asyncio
import hashlib
import importlib.util
import io
import json
import sys
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image
from test_legacy_reassignment import reassigned
from test_legacy_shadow import NOW
from test_legacy_task_plan import wrapped
from test_legacy_text_report_history import BASE
from test_shadow_install import port as stage_port

from custom_components.family_assistant.const import DOMAIN
from custom_components.family_assistant.domain.engine import new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.migration import photo_evidence as photos
from custom_components.family_assistant.migration.review import (
    ASSISTANT_KEY,
    COURT_KEY,
    read_store_pair,
)
from custom_components.family_assistant.migration.shadow import (
    build_shadow_candidate,
)
from custom_components.family_assistant.migration.shadow_entry import KEY, entry_marker

ROOT = Path(__file__).parents[1]
PHOTO_NOW = BASE + timedelta(days=1)


@pytest.fixture(autouse=True)
def windows_synthetic_decoder_port(monkeypatch):
    if sys.platform == "win32":
        from custom_components.family_assistant.media_validation import (
            MediaValidationError,
            verify,
        )

        async def decode(path):
            try:
                return await asyncio.to_thread(verify, path)
            except MediaValidationError as error:
                raise DomainError(error.code) from None

        monkeypatch.setattr(photos, "decode_file", decode)


def _encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def make_pins(state):
    return _encode(
        {
            "members": state["members"],
            "language": state["settings"]["language"],
            "timezone": state["settings"]["timezone"],
        }
    )


def image_bytes(color="red"):
    out = io.BytesIO()
    Image.new("RGB", (2, 3), color).save(out, format="PNG")
    return out.getvalue()


def photo_inputs():
    args = reassigned(new_report=True)
    ledger, court, mapping, old = args
    ledger["tasks"]["T000001"]["report_type"] = "photo"
    ledger["history"][0]["details"]["report_type"] = "photo"
    target = new_state("synthetic-owner", "Photo shadow", modules=[])
    target["members"] = deepcopy(old["members"])
    for member in target["members"].values():
        member.setdefault("aliases", [])
        member["ha_user_id"] = "synthetic-owner" if member["role"] == "owner" else None
    review = read_store_pair(
        wrapped({"ledger": ledger}, ASSISTANT_KEY), wrapped(court, COURT_KEY)
    ).review(mapping, target["members"], mapping_revision=1)
    policy = {
        "schema": 1,
        "revision": 1,
        "source_review_fingerprint": review.summary()["fingerprint"],
        "reviewers": {"T000001": ["old-parent"]},
    }
    inventory = photos.submission_inventory(review, members=target["members"])
    confirmations, attachments = [], {}
    for index, row in enumerate(inventory):
        key = f"selected_{index}"
        confirmations.append(
            {k: row[k] for k in ("task_id", "event_sequence", "report_sha256")}
            | {"attachment_key": key}
        )
        attachments[key] = image_bytes("red" if index % 2 else "blue")
    return review, target, policy, confirmations, attachments


async def make_photo_candidate():
    args = photo_inputs()
    review, target, policy, confirmations, attachments = args
    evidence = await photos.async_prepare_photo_evidence(
        review,
        members=target["members"],
        source_review_fingerprint=review.summary()["fingerprint"],
        confirmed_by="owner",
        prepared_at=PHOTO_NOW,
        confirmations=confirmations,
        attachments=attachments,
    )
    candidate = build_shadow_candidate(
        review,
        target,
        reviewer_policy=policy,
        prepared_at=PHOTO_NOW,
        photo_evidence=evidence,
    )
    return candidate, target


@pytest.fixture
def port(monkeypatch, tmp_path):
    p = stage_port.__wrapped__(monkeypatch, tmp_path)

    # ConfigEntry setup
    class ConfigEntryState:
        LOADED = "loaded"
        NOT_LOADED = "not_loaded"

    class ConfigEntry:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.state = ConfigEntryState.NOT_LOADED

    entries_module = ModuleType("homeassistant.config_entries")
    entries_module.ConfigEntry = ConfigEntry
    entries_module.ConfigEntryState = ConfigEntryState
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", entries_module)

    # Load copy_intent module
    spec_intent = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_copy_intent",
        ROOT / "custom_components/family_assistant/migration/copy_intent.py",
    )
    intent_module = importlib.util.module_from_spec(spec_intent)
    spec_intent.loader.exec_module(intent_module)

    # Load copy_index module
    spec_index = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_copy_index",
        ROOT / "custom_components/family_assistant/migration/copy_index.py",
    )
    index_module = importlib.util.module_from_spec(spec_index)
    monkeypatch.setitem(sys.modules, spec_index.name, index_module)
    monkeypatch.setitem(
        sys.modules,
        "custom_components.family_assistant.migration.copy_index",
        index_module,
    )
    spec_index.loader.exec_module(index_module)

    # Setup prototype
    prototype_entry_id = "prototype-entry-0001"
    prototype_state = deepcopy(p.target)
    prototype_state["settings"]["name"] = "Original Household"
    prototype_runtime = SimpleNamespace(
        engine=SimpleNamespace(snapshot=lambda: deepcopy(prototype_state))
    )
    prototype_entry = ConfigEntry(
        entry_id=prototype_entry_id,
        domain=DOMAIN,
        title="Original Household",
        data={},
        options={},
    )
    prototype_entry.runtime_data = prototype_runtime
    p.entries[prototype_entry_id] = prototype_entry
    p.hass.data.setdefault(DOMAIN, {}).setdefault("entries", {})[prototype_entry_id] = (
        prototype_runtime
    )

    async def authorize():
        if not p.user.is_active or not p.user.is_admin:
            raise DomainError("forbidden")

    package_fingerprint = "a" * 64
    prototype_pins = make_pins(prototype_state)

    async def prepare_and_stage(custom_candidate=None, custom_target=None, pkg_fp=None):
        cand = custom_candidate or p.candidate
        tgt = custom_target or p.target
        # As in the actual wizard, the reviewed target uses the prototype's
        # complete member/language/timezone set, not a different empty family.
        if custom_target is not None:
            prototype_state["members"] = deepcopy(tgt["members"])
            prototype_state["settings"]["language"] = tgt["settings"]["language"]
            prototype_state["settings"]["timezone"] = tgt["settings"]["timezone"]
            p.prototype_pins = make_pins(prototype_state)
        fp = pkg_fp or package_fingerprint
        target_fp = hashlib.sha256(_encode(tgt)).hexdigest()
        entry_id = hashlib.sha256(
            b"family_assistant_legacy_copy/v1\0" + fp.encode() + target_fp.encode()
        ).hexdigest()[:32]

        await p.stage(
            entry_id=entry_id,
            user_id=p.user.id,
            candidate=cand,
            target=tgt,
            expected_fingerprint=cand.summary()["fingerprint"],
        )

        intent = await intent_module.async_select_copy_intent(
            p.hass,
            package_fingerprint=fp,
            target=tgt,
            prepared_at=NOW,
            authorize=authorize,
        )
        await intent_module.async_commit_copy_intent(
            p.hass,
            record=intent,
            package_fingerprint=fp,
            target=tgt,
            authorize=authorize,
        )
        return entry_id, intent, fp, tgt, cand

    p.index_module = index_module
    p.intent_module = intent_module
    p.prototype_entry_id = prototype_entry_id
    p.prototype_state = prototype_state
    p.prototype_pins = prototype_pins
    p.authorize = authorize
    p.package_fingerprint = package_fingerprint
    p.prepare_and_stage = prepare_and_stage
    p.ConfigEntry = ConfigEntry
    p.ConfigEntryState = ConfigEntryState
    return p


@pytest.mark.asyncio
async def test_no_write_list_preview(port):
    """Listing copies before and after record performs zero Store writes and no disk reads."""
    empty_list = await port.index_module.async_list_copies(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        authorize=port.authorize,
    )
    assert empty_list == []
    assert len(port.writes) == 0

    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()

    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    assert isinstance(attempt, port.index_module.CopyAttempt)
    assert repr(attempt) == "CopyAttempt(private=True)"
    summary = attempt.summary()
    assert summary == {
        "entry_id": entry_id,
        "copy_name": target["settings"]["name"],
        "prepared_at": intent["prepared_at"],
        "fingerprint": candidate.summary()["fingerprint"],
        "compatible": True,
    }
    assert port.writes[-1] == f"{DOMAIN}.copy_index"
    writes_after_record = len(port.writes)

    # Listing now returns 1 attempt and performs ZERO additional writes
    listed = await port.index_module.async_list_copies(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        authorize=port.authorize,
    )
    assert len(listed) == 1
    assert listed[0].summary() == summary
    assert len(port.writes) == writes_after_record

    # Fresh private_record copy is independent
    rec1 = attempt.private_record()
    rec2 = attempt.private_record()
    assert rec1 == rec2
    assert rec1 is not rec2


@pytest.mark.asyncio
async def test_completed_candidate_reload(port):
    """Candidate reloads from Store, re-verifies converters and matches original state."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()
    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    before_load_writes = len(port.writes)
    loaded = await port.index_module.async_load_copy(
        port.hass,
        attempt=attempt,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        authorize=port.authorize,
    )

    assert set(loaded) == {
        "candidate",
        "target",
        "intent",
        "package_fingerprint",
    }
    assert loaded["candidate"]._state == candidate._state
    assert loaded["candidate"]._summary == candidate._summary
    assert loaded["candidate"].private_blobs() == candidate.private_blobs()
    assert loaded["target"] == target
    assert loaded["intent"] == intent
    assert loaded["package_fingerprint"] == pkg_fp
    # No writes during load
    assert len(port.writes) == before_load_writes


@pytest.mark.asyncio
async def test_completed_candidate_reload_with_photo_blobs(port):
    """Candidate with real photo blobs reloads from disk and re-verifies."""
    photo_candidate, photo_target = await make_photo_candidate()
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage(
        custom_candidate=photo_candidate,
        custom_target=photo_target,
        pkg_fp="b" * 64,
    )
    assert len(candidate.private_blobs()) == 2

    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    loaded = await port.index_module.async_load_copy(
        port.hass,
        attempt=attempt,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        authorize=port.authorize,
    )
    assert loaded["candidate"]._state == candidate._state
    assert loaded["candidate"]._summary == candidate._summary
    assert loaded["candidate"].private_blobs() == candidate.private_blobs()


@pytest.mark.asyncio
async def test_partial_and_missing_stores(port):
    """Missing candidate, copy_intent, or shadow_intent store raises partial bundle error."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()
    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    # 1. Missing candidate Store
    saved_candidate = port.values.pop(f"{DOMAIN}.{entry_id}")
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_partial_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )
    port.values[f"{DOMAIN}.{entry_id}"] = saved_candidate

    # 2. Missing copy_intent Store
    saved_intent = port.values.pop(f"{DOMAIN}.copy_intent.{entry_id}")
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_partial_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )
    port.values[f"{DOMAIN}.copy_intent.{entry_id}"] = saved_intent

    # 3. Missing shadow_intent Store
    port.values.pop(f"{DOMAIN}.shadow_intent.{entry_id}")
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_partial_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )


@pytest.mark.asyncio
async def test_tampered_and_corrupt_blobs(port):
    """Missing, foreign, or tampered blobs raise partial bundle error."""
    photo_candidate, photo_target = await make_photo_candidate()
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage(
        custom_candidate=photo_candidate,
        custom_target=photo_target,
        pkg_fp="c" * 64,
    )
    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    blob_dir = Path(
        port.hass.config.path(
            "family_assistant_data",
            hashlib.sha256(entry_id.encode()).hexdigest(),
        )
    )
    assert blob_dir.exists()
    blob_files = list(blob_dir.iterdir())
    assert len(blob_files) == 2

    # 1. Foreign file in blob directory
    foreign_file = blob_dir / "foreign_intruder.bin"
    foreign_file.write_bytes(b"malicious foreign entry")
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_partial_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )
    foreign_file.unlink()

    # 2. Tampered blob content (wrong bytes / wrong hash)
    target_blob = blob_files[0]
    original_blob_bytes = target_blob.read_bytes()
    target_blob.write_bytes(b"tampered content of same length!"[: len(original_blob_bytes)])
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_partial_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )
    target_blob.write_bytes(original_blob_bytes)

    # 3. Missing blob file
    target_blob.unlink()
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_partial_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )


@pytest.mark.asyncio
async def test_summary_and_fingerprint_mismatches(port):
    """Candidate Store hash mismatch is caught BEFORE any blob reads; archive mismatch refuses."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()
    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    # Tamper with candidate state in Store so sha256(canonical state) != indexed fingerprint
    saved_state = deepcopy(port.values[f"{DOMAIN}.{entry_id}"])
    saved_state["settings"]["name"] = "Tampered household name"
    port.values[f"{DOMAIN}.{entry_id}"] = saved_state

    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_incompatible_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )

    # Restore candidate state, then tamper target archive fingerprint
    port.values[f"{DOMAIN}.{entry_id}"] = candidate.private_state()
    saved_archive_tamper = deepcopy(port.values[f"{DOMAIN}.{entry_id}"])
    saved_archive_tamper["migration_archive"]["target_fingerprint"] = "f" * 64
    # Re-adjust indexed fingerprint to match the state fingerprint so state check passes
    new_fp = hashlib.sha256(_encode(saved_archive_tamper)).hexdigest()
    port.values[f"{DOMAIN}.{entry_id}"] = saved_archive_tamper
    index_data = port.values[f"{DOMAIN}.copy_index"]
    index_data["records"][entry_id]["candidate_summary"]["fingerprint"] = new_fp
    index_data["records"][entry_id]["fingerprint"] = new_fp
    tampered_attempt = port.index_module.CopyAttempt(
        _encode(index_data["records"][entry_id]), _compatible=True
    )

    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_incompatible_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=tampered_attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )


@pytest.mark.asyncio
async def test_wrong_prototype_user_and_authority(port):
    """Authority violations, wrong prototype, non-admin, non-owner, and pins drift refuse."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()

    # 1. Non-admin user
    port.user.is_admin = False
    with pytest.raises(port.index_module.CopyIndexError, match="^forbidden$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )
    port.user.is_admin = True

    # 2. Inactive user
    port.user.is_active = False
    with pytest.raises(port.index_module.CopyIndexError, match="^forbidden$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )
    port.user.is_active = True

    # 3. Wrong prototype entry ID
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_primary_owner_required$",
    ):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id="nonexistent-prototype",
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )

    # 4. Backup active
    port.hass.data[DOMAIN]["backup"] = True
    with pytest.raises(port.index_module.CopyIndexError, match="^migration_copy_busy$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )
    port.hass.data[DOMAIN]["backup"] = False

    # 5. Prototype pins mismatch
    drift_pins = b'{"drift": true}'
    with pytest.raises(port.index_module.CopyIndexError, match="^migration_copy_review_changed$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=drift_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )


@pytest.mark.asyncio
async def test_await_time_revocation(port):
    """Authority, runtime, or pins revoked during an await re-checks upon wake-up."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()

    # Revoke admin right during Store save await
    async def revoke_admin_before_save(_key):
        port.user.is_admin = False

    port.options.before_save = revoke_admin_before_save
    with pytest.raises(port.index_module.CopyIndexError, match="^forbidden$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )
    port.options.before_save = None
    port.user.is_admin = True
    port.values.pop(f"{DOMAIN}.copy_index", None)

    # Replaced runtime during Store save await
    async def vanish_runtime_before_save(_key):
        port.hass.data[DOMAIN]["entries"].pop(port.prototype_entry_id, None)

    port.options.before_save = vanish_runtime_before_save
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_primary_owner_required$",
    ):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )
    port.options.before_save = None


@pytest.mark.asyncio
async def test_capacity_and_corruption(port):
    """Index capacity caps at 16 records; corrupted index and conflicting records refuse."""
    # Test capacity cap at 16
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()
    dummy_records = {}
    for i in range(16):
        custom_pkg_fp = f"{i + 1:064x}"
        identity = port.intent_module._identity(custom_pkg_fp, target)
        eid = identity["entry_id"]
        custom_intent = identity | {"prepared_at": intent["prepared_at"]}
        dummy_records[eid] = {
            "entry_id": eid,
            "prototype_entry_id": port.prototype_entry_id,
            "owner_user_id": port.user.id,
            "prototype_pins_hash": hashlib.sha256(port.prototype_pins).hexdigest(),
            "package_fingerprint": custom_pkg_fp,
            "copy_intent": custom_intent,
            "target": target,
            "candidate_summary": candidate.summary(),
            "copy_name": target["settings"]["name"],
            "prepared_at": custom_intent["prepared_at"],
            "fingerprint": candidate.summary()["fingerprint"],
        }
    port.values[f"{DOMAIN}.copy_index"] = {
        "version": 1,
        "records": dummy_records,
    }

    # Attempting to insert a 17th record raises index_full
    with pytest.raises(port.index_module.CopyIndexError, match="^migration_copy_index_full$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )

    # Identical insert with already existing entry does not write and succeeds
    existing_eid = list(dummy_records.keys())[0]
    existing_record = dummy_records[existing_eid]
    port.values[f"{DOMAIN}.copy_intent.{existing_eid}"] = existing_record["copy_intent"]
    writes_before = len(port.writes)
    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=existing_record["copy_intent"],
        package_fingerprint=existing_record["package_fingerprint"],
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )
    assert isinstance(attempt, port.index_module.CopyAttempt)
    # Zero Store writes performed
    assert len(port.writes) == writes_before

    # Different record same ID refuses
    port.values[f"{DOMAIN}.copy_index"]["records"][entry_id] = {
        **dummy_records[existing_eid],
        "entry_id": entry_id,
        "package_fingerprint": pkg_fp,
        "copy_intent": intent,
        "prototype_pins_hash": "e" * 64,  # difference!
    }
    with pytest.raises(port.index_module.CopyIndexError, match="^migration_copy_index_invalid$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )

    # Corrupt Store: version = True (bool number!)
    port.values[f"{DOMAIN}.copy_index"] = {
        "version": True,
        "records": {},
    }
    with pytest.raises(port.index_module.CopyIndexError, match="^migration_copy_index_invalid$"):
        await port.index_module.async_list_copies(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )


@pytest.mark.asyncio
async def test_lost_store_ack_retry(port):
    """Store write failure leaves consistent state, retry succeeds without duplicate writes."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()

    async def lost_ack(_key):
        raise OSError("Lost Store write acknowledgement")

    port.options.after_save = lost_ack
    with pytest.raises(port.index_module.CopyIndexError, match="^migration_copy_index_invalid$"):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg_fp,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )

    # After-save error cleared: retry succeeds and finds identical entry without writing again
    port.options.after_save = None
    writes_before = len(port.writes)
    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )
    assert isinstance(attempt, port.index_module.CopyAttempt)
    assert len(port.writes) == writes_before


@pytest.mark.asyncio
async def test_registered_entry_validation_and_mismatch(port):
    """Registered entry in HA must match exact seal and data; mismatch refuses."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()
    attempt = await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    state = candidate.private_state()
    fp = candidate.summary()["fingerprint"]
    seal = entry_marker(state, fp)
    valid_entry_data = {
        "owner_user_id": port.user.id,
        "owner_name": target["members"]["owner"]["name"],
        "name": target["settings"]["name"],
        "language": target["settings"]["language"],
        "timezone": target["settings"]["timezone"],
        "modules": [],
        KEY: seal,
    }

    # 1. Valid registered entry (not loaded) -> load succeeds
    registered_entry = port.ConfigEntry(
        entry_id=entry_id,
        domain=DOMAIN,
        source="user",
        version=1,
        minor_version=1,
        unique_id=f"migration-shadow-{entry_id}",
        title=target["settings"]["name"],
        data=valid_entry_data,
        options={},
    )
    port.entries[entry_id] = registered_entry

    loaded = await port.index_module.async_load_copy(
        port.hass,
        attempt=attempt,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        authorize=port.authorize,
    )
    assert loaded["candidate"]._state == candidate._state

    # 2. Registered entry with tampered seal -> refuses
    registered_entry.data = {
        **valid_entry_data,
        KEY: {"version": 1, "mode": "read_only", "fingerprint": "0" * 64},
    }
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_incompatible_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )

    # 3. Registered entry with wrong owner -> refuses
    registered_entry.data = {
        **valid_entry_data,
        "owner_user_id": "different-owner-user-id",
    }
    with pytest.raises(
        port.index_module.CopyIndexError,
        match="^migration_copy_incompatible_bundle_required$",
    ):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )


@pytest.mark.asyncio
async def test_scope_isolation_in_listing(port):
    """List only returns records matching prototype_entry_id and owner_user_id."""
    entry_id, intent, pkg_fp, target, candidate = await port.prepare_and_stage()
    await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg_fp,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )

    # Create another prototype entry and owner
    other_proto_id = "prototype-other-0002"
    other_state = new_state("other-owner", "Other Household", modules=[])
    other_runtime = SimpleNamespace(engine=SimpleNamespace(snapshot=lambda: deepcopy(other_state)))
    other_entry = port.ConfigEntry(
        entry_id=other_proto_id,
        domain=DOMAIN,
        title="Other Household",
        data={},
        options={},
    )
    other_entry.runtime_data = other_runtime
    port.entries[other_proto_id] = other_entry
    port.hass.data[DOMAIN]["entries"][other_proto_id] = other_runtime

    other_user = SimpleNamespace(id="other-owner", is_active=True, is_admin=True)

    async def get_user(uid):
        if uid == "other-owner":
            return other_user
        return port.user

    port.hass.auth.async_get_user = get_user

    async def other_auth():
        pass

    # Listing for other prototype returns empty list
    other_list = await port.index_module.async_list_copies(
        port.hass,
        prototype_entry_id=other_proto_id,
        user_id="other-owner",
        prototype_pins=make_pins(other_state),
        authorize=other_auth,
    )
    assert other_list == []

    # Original prototype listing returns 1 copy
    original_list = await port.index_module.async_list_copies(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        authorize=port.authorize,
    )
    assert len(original_list) == 1
    assert original_list[0].summary()["entry_id"] == entry_id


async def _record_attempt(port):
    _, intent, pkg, target, candidate = await port.prepare_and_stage()
    return await port.index_module.async_record_copy(
        port.hass,
        prototype_entry_id=port.prototype_entry_id,
        user_id=port.user.id,
        prototype_pins=port.prototype_pins,
        intent=intent,
        package_fingerprint=pkg,
        target=target,
        candidate=candidate,
        authorize=port.authorize,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["admin", "member", "runtime"])
async def test_revocation_during_index_read_prevents_new_record_write(port, fault):
    _, intent, pkg, target, candidate = await port.prepare_and_stage()
    before, writes = deepcopy(port.values), list(port.writes)

    async def change(key):
        if key != f"{DOMAIN}.copy_index":
            return
        if fault == "admin":
            port.user.is_admin = False
        elif fault == "member":
            port.prototype_state["members"]["owner"]["revision"] += 1
        else:
            replacement = SimpleNamespace(
                engine=SimpleNamespace(snapshot=lambda: deepcopy(port.prototype_state))
            )
            port.entries[port.prototype_entry_id].runtime_data = replacement
            port.hass.data[DOMAIN]["entries"][port.prototype_entry_id] = replacement

    port.options.before_load = change
    with pytest.raises(port.index_module.CopyIndexError):
        await port.index_module.async_record_copy(
            port.hass,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            intent=intent,
            package_fingerprint=pkg,
            target=target,
            candidate=candidate,
            authorize=port.authorize,
        )
    assert port.values == before and port.writes == writes


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["admin", "member", "runtime"])
async def test_final_load_read_revocation_never_returns_private_candidate(port, fault):
    attempt = await _record_attempt(port)
    key = f"{DOMAIN}.shadow_intent.{attempt.summary()['entry_id']}"
    calls = 0
    before, writes = deepcopy(port.values), list(port.writes)

    async def change(loaded_key):
        nonlocal calls
        if loaded_key != key:
            return
        calls += 1
        if calls < 2:
            return
        if fault == "admin":
            port.user.is_admin = False
        elif fault == "member":
            port.prototype_state["members"]["owner"]["revision"] += 1
        else:
            replacement = SimpleNamespace(
                engine=SimpleNamespace(snapshot=lambda: deepcopy(port.prototype_state))
            )
            port.entries[port.prototype_entry_id].runtime_data = replacement
            port.hass.data[DOMAIN]["entries"][port.prototype_entry_id] = replacement

    port.options.before_load = change
    with pytest.raises(port.index_module.CopyIndexError):
        await port.index_module.async_load_copy(
            port.hass,
            attempt=attempt,
            prototype_entry_id=port.prototype_entry_id,
            user_id=port.user.id,
            prototype_pins=port.prototype_pins,
            authorize=port.authorize,
        )
    assert calls == 2 and port.values == before and port.writes == writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["owner", "pins", "count_bool", "flag", "extra", "missing", "unsafe_int", "photo"]
)
async def test_corrupted_index_record_is_not_a_valid_private_attempt(port, fault):
    attempt = await _record_attempt(port)
    record = attempt.private_record()
    if fault == "owner":
        record["owner_user_id"] = "different-user"
    elif fault == "pins":
        record["prototype_pins_hash"] = "f" * 64
    elif fault == "count_bool":
        record["candidate_summary"]["counts"]["members"] = True
    elif fault == "flag":
        record["candidate_summary"]["activation_available"] = 0
    elif fault == "extra":
        record["candidate_summary"]["PRIVATE_EXTRA"] = "must not pass"
    elif fault == "missing":
        record.pop("copy_name")
    elif fault == "unsafe_int":
        record["candidate_summary"]["counts"]["members"] = 2**60
    elif fault == "photo":
        record["candidate_summary"]["photo_evidence"] = {"PRIVATE_UNKNOWN": True}
    with pytest.raises(port.index_module.CopyIndexError) as caught:
        port.index_module.CopyAttempt(_encode(record), True)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.asyncio
async def test_attempt_encoding_is_canonical_immutable_and_bounded(port):
    attempt = await _record_attempt(port)
    raw = attempt._record
    for invalid in [raw + b" ", raw.decode(), b'{"x":1,"x":2}', b'{"x":NaN}', b'"\\ud800"']:
        with pytest.raises(port.index_module.CopyIndexError):
            port.index_module.CopyAttempt(invalid, True)
    for invalid in (1, "true", None):
        with pytest.raises(port.index_module.CopyIndexError):
            port.index_module.CopyAttempt(raw, invalid)
    copy = attempt.private_record()
    copy["copy_name"] = "PRIVATE_CHANGED"
    assert attempt._record == raw and "PRIVATE" not in repr(attempt)


def test_json_container_work_and_bytes_are_bounded_before_serialization(port, monkeypatch):
    module = port.index_module
    monkeypatch.setattr(module, "_MAX_ITEMS", 10)
    with pytest.raises(module.CopyIndexError):
        module._assert_bounded_finite_json([None] * 11)
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(module.CopyIndexError):
        module._assert_bounded_finite_json(cyclic)
    monkeypatch.setattr(module, "_MAX_INDEX_BYTES", 20)
    with pytest.raises(module.CopyIndexError):
        module._assert_bounded_finite_json("abcdefgh")
