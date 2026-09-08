"""Owner-matched actual image bytes, exact source events and private whole copies."""

import asyncio
import io
import json
import sys
from copy import deepcopy
from datetime import timedelta

import pytest
from PIL import Image
from test_legacy_photo_requirement import photo_source
from test_legacy_reassignment import reassigned
from test_legacy_task_plan import wrapped
from test_legacy_text_report_history import BASE
from test_shadow_install import port as install_port

from custom_components.family_assistant.domain import media
from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.migration import photo_evidence as photos
from custom_components.family_assistant.migration.review import (
    ASSISTANT_KEY,
    COURT_KEY,
    read_store_pair,
)
from custom_components.family_assistant.migration.shadow import (
    ShadowError,
    async_reverify_shadow,
    build_shadow_candidate,
)
from custom_components.family_assistant.migration.task_plan import TaskPlanError, build_task_plan

NOW = BASE + timedelta(days=1)


@pytest.fixture
def port(monkeypatch, tmp_path):
    return install_port.__wrapped__(monkeypatch, tmp_path)


@pytest.fixture(autouse=True)
def windows_synthetic_decoder_port(monkeypatch):
    # HA runs on POSIX. Windows has no resource module, so production's bounded
    # subprocess correctly refuses it. Exercise the same image verifier on these
    # small generated fixtures locally; Linux CI/native HA use the actual helper.
    if sys.platform == "win32":
        from custom_components.family_assistant.media_validation import MediaValidationError, verify

        async def decode(path):
            try:
                return await asyncio.to_thread(verify, path)
            except MediaValidationError as error:
                raise DomainError(error.code) from None

        monkeypatch.setattr(photos, "decode_file", decode)


def image_bytes(color="red"):
    out = io.BytesIO()
    Image.new("RGB", (2, 3), color).save(out, format="PNG")
    return out.getvalue()


def inputs(rounds=2, terminal=None, assignment=False):
    args = (
        reassigned(new_report=True)
        if assignment
        else photo_source(rounds=rounds, terminal=terminal)
    )
    ledger, court, mapping, old = args
    ledger["tasks"]["T000001"]["report_type"] = "photo"
    ledger["history"][0]["details"]["report_type"] = "photo"
    target = new_state("fictional-ha-user", "Fictional household", modules=[])
    target["members"] = deepcopy(old["members"])
    for member in target["members"].values():
        member.setdefault("aliases", [])
        member.setdefault("ha_user_id", None)
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


async def prepare(args, **overrides):
    review, target, _, confirmations, attachments = args
    options = dict(
        members=target["members"],
        source_review_fingerprint=review.summary()["fingerprint"],
        confirmed_by="owner",
        prepared_at=NOW,
        confirmations=confirmations,
        attachments=attachments,
    )
    options.update(overrides)
    return await photos.async_prepare_photo_evidence(review, **options)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [None, "needs_changes", "completed", "cancelled", "archived"])
async def test_actual_decoder_whole_shadow_rounds_exact_replay_and_private_archive(terminal):
    args = inputs(terminal=terminal)
    review, target, policy, _, _ = args
    original = deepcopy((target, policy, review.private_data()))
    evidence = await prepare(args)
    with pytest.raises(ShadowError, match="shadow_complete_conversion_required"):
        build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)
    candidate = build_shadow_candidate(
        review, target, reviewer_policy=policy, prepared_at=NOW, photo_evidence=evidence
    )
    state = candidate.private_state()
    assert len(candidate.private_blobs()) == 2 and len(state["media"]) == 2
    task = state["tasks"]["T000001"]
    assert task["report"] is None and task["report_generation"] == 2
    previous = task["previous_reports"][0]
    assert previous["report"] is None and previous["report_generation"] == 1
    assert previous["review_note"] == "Review 0"
    assert previous["report_media"] != task["report_media"]
    assert (target, policy, review.private_data()) == original
    repeated = await prepare(args)
    assert repeated.private_data() == evidence.private_data()
    assert repeated.private_blobs() == evidence.private_blobs() == candidate.private_blobs()
    assert (
        candidate.private_state()
        == build_shadow_candidate(
            review, target, reviewer_policy=policy, prepared_at=NOW, photo_evidence=repeated
        ).private_state()
    )
    for key, record in state["media"].items():
        assert media.authorize_blob(state, state["members"]["owner"], key, NOW) == record
        assert record["size_bytes"] == len(candidate.private_blobs()[record["blob_key"]])
        with pytest.raises(DomainError, match="forbidden"):
            media.authorize_blob(state, state["members"]["child"], key, NOW)
    safe = (
        repr(evidence)
        + repr(candidate)
        + json.dumps(evidence.summary())
        + json.dumps(candidate.summary())
    )
    for secret in ("First report", "old-parent", "fictional-ha-user", "T000001"):
        assert secret not in safe
    assert evidence.summary()["image_identity_automatically_verified"] is False
    assert candidate.summary()["activation_available"] is False
    assert state["migration_archive"]["photo_evidence"] == evidence.private_data()
    engine = Engine(state, lambda value: pytest.fail("Unexpected Store write"))
    view = engine.view("owner", now=NOW)
    assert len(view["tasks"][0]["report_attachments"]) == 1
    assert len(view["tasks"][0]["previous_reports"][0]["report_attachments"]) == 1
    assert "blob_key" not in json.dumps(view) and "report_sha256" not in json.dumps(view)
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await engine.execute(
            "owner", "tasks.complete", {"id": task["id"], "revision": 1}, "forbidden", NOW
        )


@pytest.mark.asyncio
async def test_reassignment_keeps_media_with_original_person_and_global_generation():
    args = inputs(assignment=True)
    evidence = await prepare(args)
    state = build_shadow_candidate(
        args[0], args[1], reviewer_policy=args[2], prepared_at=NOW, photo_evidence=evidence
    ).private_state()
    task = state["tasks"]["T000001"]
    assert task["assignee"] == "sibling" and task["report_generation"] == 2
    previous = task["previous_reports"][0]
    assert previous["assignee"] == "child" and previous["report_generation"] == 1
    # Test the normal media ACL contract on a synthetic domain projection, NOT an
    # available activation operation or a real migration cutover.
    state.pop("migration_shadow")
    state["schema_version"] = 1
    state["settings"]["modules"] = ["tasks"]
    current_id, old_id = task["report_media"][0], previous["report_media"][0]
    media.authorize_blob(state, state["members"]["sibling"], current_id, NOW)
    for actor, reference in [("sibling", old_id), ("child", current_id), ("child", old_id)]:
        with pytest.raises(DomainError, match="forbidden"):
            media.authorize_blob(state, state["members"][actor], reference, NOW)
    state["members"]["sibling"]["revision"] += 1
    with pytest.raises(DomainError, match="forbidden"):
        media.authorize_blob(state, state["members"]["sibling"], current_id, NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "reference",
        "sequence",
        "task",
        "path",
        "raw_id",
        "owner",
        "fingerprint",
        "bool",
        "malformed",
    ],
)
async def test_unreviewed_ambiguous_partial_and_stale_choices_rejected_before_decoder(
    mutation, monkeypatch
):
    args = inputs()
    choices, data = args[3], args[4]
    overrides = {}
    if mutation == "missing":
        choices.pop()
    elif mutation == "extra":
        data["extra"] = image_bytes()
    elif mutation == "duplicate":
        choices[1] = deepcopy(choices[0])
    elif mutation == "reference":
        choices[0]["report_sha256"] = "0" * 64
    elif mutation == "sequence":
        choices[0]["event_sequence"] += 1
    elif mutation == "task":
        choices[0]["task_id"] = "T999999"
    elif mutation == "path":
        data["../escape"] = data.pop("selected_0")
    elif mutation == "raw_id":
        data["selected_0"] = "telegram_attachment:synthetic:1"
    elif mutation == "owner":
        overrides["confirmed_by"] = "child"
    elif mutation == "fingerprint":
        overrides["source_review_fingerprint"] = "0" * 64
    elif mutation == "bool":
        choices[0]["event_sequence"] = True
    else:
        choices[0] = []

    async def forbidden(_content):
        pytest.fail("Invalid choices reached decoder")

    monkeypatch.setattr(photos, "_verify_bytes", forbidden)
    with pytest.raises(photos.PhotoEvidenceError):
        await prepare(args, **overrides)


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"not an image", b"%PDF-1.4\n%%EOF", image_bytes() + b"extra"])
async def test_untrusted_bytes_rejected_by_real_bounded_decoder(content):
    args = inputs(rounds=1)
    args[4]["selected_0"] = content
    with pytest.raises(photos.PhotoEvidenceError, match="media_invalid"):
        await prepare(args)


@pytest.mark.asyncio
async def test_identity_change_while_decoder_runs_blocks_receipt(monkeypatch):
    args = inputs(rounds=1)
    original = photos._verify_bytes

    async def changed(content):
        result = await original(content)
        args[1]["members"]["owner"]["revision"] += 1
        return result

    monkeypatch.setattr(photos, "_verify_bytes", changed)
    with pytest.raises(photos.PhotoEvidenceError, match="review_changed"):
        await prepare(args)


@pytest.mark.asyncio
async def test_changed_review_rejects_prepared_evidence_and_raw_metadata_is_not_a_capability():
    args = inputs(rounds=1)
    evidence = await prepare(args)
    with pytest.raises(TaskPlanError, match="photo_evidence_invalid"):
        build_task_plan(args[0], members=args[1]["members"], photo_evidence=evidence.private_data())
    other = inputs(rounds=2)
    with pytest.raises(TaskPlanError, match="review_changed"):
        build_task_plan(other[0], members=other[1]["members"], photo_evidence=evidence)


@pytest.mark.asyncio
async def test_private_archive_replay_redecodes_every_blob_and_rejects_metadata_or_byte_changes():
    args = inputs()
    evidence = await prepare(args)
    archive, blobs = evidence.private_data(), evidence.private_blobs()

    async def restore(payload, contents):
        return await photos.async_restore_photo_evidence(
            args[0], members=args[1]["members"], archive=payload, blobs=contents
        )

    restored = await restore(archive, blobs)
    assert restored.private_data() == archive and restored.private_blobs() == blobs
    for field, value in [
        ("mime_type", "image/jpeg"),
        ("sha256", "0" * 64),
        ("assignee", "owner"),
        ("media_id", "M" + "0" * 32),
    ]:
        changed = deepcopy(archive)
        changed["records"][0][field] = value
        with pytest.raises(photos.PhotoEvidenceError, match="photo_evidence_archive_changed"):
            await restore(changed, blobs)
    for changed in (
        {},
        {**blobs, "extra": image_bytes()},
        {**blobs, next(iter(blobs)): image_bytes("green")},
    ):
        with pytest.raises(photos.PhotoEvidenceError):
            await restore(archive, changed)


@pytest.mark.asyncio
async def test_input_edits_during_decode_do_not_retarget_frozen_choices(monkeypatch):
    args = inputs()
    original = photos._verify_bytes
    expected = deepcopy((args[3], args[4]))

    async def changed(content):
        result = await original(content)
        args[3].clear()
        args[4].clear()
        return result

    monkeypatch.setattr(photos, "_verify_bytes", changed)
    evidence = await prepare(args)
    assert len(evidence.private_data()["records"]) == 2
    assert sorted(evidence.private_blobs().values()) == sorted(expected[1].values())


@pytest.mark.asyncio
async def test_cancellation_settles_decoder_and_cleans_private_temporary_file(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    paths = []

    async def delayed(path):
        paths.append(path)
        started.set()
        try:
            await release.wait()
        finally:
            assert path.exists()

    monkeypatch.setattr(photos, "decode_file", delayed)
    work = asyncio.create_task(prepare(inputs(rounds=1)))
    await started.wait()
    work.cancel()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert paths and not paths[0].exists() and not paths[0].parent.exists()


@pytest.mark.asyncio
async def test_complete_photo_copy_stages_blobs_before_store_and_retries_exactly(port, monkeypatch):
    import hashlib
    from pathlib import Path

    args = inputs()
    review, target, policy, _, _ = args
    evidence = await prepare(args)
    candidate = build_shadow_candidate(
        review, target, reviewer_policy=policy, prepared_at=NOW, photo_evidence=evidence
    )
    port.user.id = target["members"]["owner"]["ha_user_id"]
    root = Path(
        port.hass.config.path(
            "family_assistant_data", hashlib.sha256(b"synthetic-shadow-entry-0001").hexdigest()
        )
    )
    seen = []

    async def before_save(key):
        if key == "family_assistant.synthetic-shadow-entry-0001":
            assert {p.name: p.read_bytes() for p in root.iterdir()} == candidate.private_blobs()
            seen.append(key)

    port.options.before_save = before_save
    opts = {
        "candidate": candidate,
        "target": target,
        "expected_fingerprint": candidate.summary()["fingerprint"],
    }
    receipt = await port.stage(**opts)
    assert await port.stage(**opts) == receipt
    assert len(seen) == 1
    assert await async_reverify_shadow(candidate, target) == candidate


@pytest.mark.asyncio
async def test_second_blob_failure_leaves_no_store_and_retry_keeps_first_blob(port, monkeypatch):
    import hashlib
    from pathlib import Path

    args = inputs()
    review, target, policy, _, _ = args
    evidence = await prepare(args)
    candidate = build_shadow_candidate(
        review, target, reviewer_policy=policy, prepared_at=NOW, photo_evidence=evidence
    )
    port.user.id = target["members"]["owner"]["ha_user_id"]
    real = port.module._put_blob
    count = 0

    def fail(root, key, content, metadata):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("PRIVATE synthetic I/O path")
        real(root, key, content, metadata)

    monkeypatch.setattr(port.module, "_put_blob", fail)
    opts = {
        "candidate": candidate,
        "target": target,
        "expected_fingerprint": candidate.summary()["fingerprint"],
    }
    with pytest.raises(port.module.ShadowInstallError, match="retry_required"):
        await port.stage(**opts)
    assert "family_assistant.synthetic-shadow-entry-0001" not in port.values
    root = Path(
        port.hass.config.path(
            "family_assistant_data", hashlib.sha256(b"synthetic-shadow-entry-0001").hexdigest()
        )
    )
    assert len(list(root.iterdir())) == 1
    monkeypatch.setattr(port.module, "_put_blob", real)
    await port.stage(**opts)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == candidate.private_blobs()
