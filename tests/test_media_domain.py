"""Pure metadata and authority tests for the first task-report media slice."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import media, tasks
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

DIGEST = "a" * 64


def test_new_identifiers_do_not_alias_another_records_private_blob(monkeypatch):
    existing = {"M" + "b" * 32: {"blob_key": "c" * 64}}
    values = iter(["d" * 32, "c" * 64, "e" * 32, "f" * 64])
    monkeypatch.setattr(media.secrets, "token_hex", lambda _length: next(values))
    assert media._new_identifiers(existing) == ("M" + "e" * 32, "f" * 64)


def test_exhausted_blob_collisions_fail_without_modifying_existing(monkeypatch):
    existing = {"M" + "b" * 32: {"blob_key": "c" * 64}}
    before = deepcopy(existing)
    monkeypatch.setattr(media.secrets, "token_hex", lambda length: "c" * (length * 2))
    with pytest.raises(DomainError, match="quota_exceeded"):
        media._new_identifiers(existing)
    assert existing == before


def ctx(state, actor_id, now, operation="media-test"):
    return Context(state, state["members"][actor_id], now, operation)


def system_ctx(state, now, operation="media-finalize"):
    return Context(state, {"id": "system", "role": "system"}, now, operation)


def photo_task(state, now, *, assignee="child"):
    task = tasks.handle(
        ctx(state, "parent", now, "create-photo-task"),
        "create",
        {"title": "Synthetic photo report", "assignee": assignee, "report_type": "photo"},
    )
    state["outbox"].clear()
    return state["tasks"][task["id"]]


def reserve(state, now, task, *, actor="child"):
    return media.handle(
        ctx(state, actor, now, f"reserve-{actor}"),
        "reserve",
        {
            "purpose": "task_report",
            "task_id": task["id"],
            "task_revision": task["revision"],
            "uploader_revision": state["members"][actor]["revision"],
        },
    )


def finalize(state, now, receipt, *, actor="child", **overrides):
    values = {
        "verifiedmime": "image/jpeg",
        "size": 1234,
        "sha256": DIGEST,
        **overrides,
    }
    return media.finalize(
        system_ctx(state, now),
        actor,
        receipt["id"],
        receipt["revision"],
        values["verifiedmime"],
        values["size"],
        values["sha256"],
    )


def test_reserve_is_opaque_epoch_bound_and_has_no_task_or_effect_mutation(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    task_before = deepcopy(task)
    effects_before = {key: deepcopy(state[key]) for key in ("outbox", "audit")}

    receipt = reserve(state, now, task)

    assert set(receipt) == {"id", "revision", "status"}
    assert receipt["revision"] == 1 and receipt["status"] == "reserved"
    assert media._OPAQUE_ID.fullmatch(receipt["id"])
    record = state["media"][receipt["id"]]
    assert media._BLOB_KEY.fullmatch(record["blob_key"])
    assert record["blob_key"] not in receipt["id"]
    assert record["uploader"] == "child" and record["uploader_revision"] == 1
    assert record["scope"] == {
        "kind": "uploader_private",
        "member": "child",
        "member_revision": 1,
        "intended_target": {
            "task_id": task["id"],
            "task_revision": task["revision"],
            "assignee": "child",
            "assignee_revision": 1,
        },
    }
    assert record["expires_at"] == (now + timedelta(hours=1)).isoformat()
    assert task == task_before
    assert {key: state[key] for key in effects_before} == effects_before


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            {
                "purpose": "maintenance_fault",
                "task_id": "T000001",
                "task_revision": 1,
                "uploader_revision": 1,
            },
            "invalid_field",
        ),
        (
            {"purpose": "task_report", "task_id": "T000001", "uploader_revision": 1},
            "invalid_field",
        ),
        (
            {
                "purpose": "task_report",
                "task_id": "T000001",
                "task_revision": True,
                "uploader_revision": 1,
            },
            "invalid_field",
        ),
        (
            {
                "purpose": "task_report",
                "task_id": "T000001",
                "task_revision": 1,
                "uploader_revision": 1,
                "path": "C:/private.jpg",
            },
            "invalid_field",
        ),
    ],
)
def test_reserve_exact_payload_and_strict_versions(engine, now, payload, code):
    state = engine.snapshot()
    photo_task(state, now)
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        media.handle(ctx(state, "child", now), "reserve", payload)
    assert caught.value.code == code
    assert state == before


@pytest.mark.parametrize("actor", ["adult", "sibling", "guest"])
def test_only_current_assignee_or_privileged_actor_can_reserve(engine, now, actor):
    state = engine.snapshot()
    task = photo_task(state, now)
    before = deepcopy(state)
    with pytest.raises(DomainError, match="forbidden"):
        reserve(state, now, task, actor=actor)
    assert state == before


def test_reserve_rechecks_module_photo_status_task_and_identity_epochs(engine, now):
    base = engine.snapshot()
    task = photo_task(base, now)
    payload = {
        "purpose": "task_report",
        "task_id": task["id"],
        "task_revision": task["revision"],
        "uploader_revision": 1,
    }
    cases = [
        lambda state: state["settings"].update(
            modules=[item for item in state["settings"]["modules"] if item != "tasks"]
        ),
        lambda state: state["tasks"][task["id"]].update(report_type="text"),
        lambda state: state["tasks"][task["id"]].update(status="submitted"),
        lambda state: state["members"]["child"].update(revision=2),
        lambda state: state["tasks"][task["id"]].update(revision=2),
    ]
    for mutate in cases:
        state = deepcopy(base)
        mutate(state)
        before = deepcopy(state)
        with pytest.raises(DomainError):
            media.handle(ctx(state, "child", now), "reserve", payload)
        assert state == before


def test_parent_may_reserve_only_own_upload_for_current_photo_task(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    receipt = reserve(state, now, task, actor="parent")
    record = state["media"][receipt["id"]]
    assert record["uploader"] == "parent"
    assert record["scope"]["intended_target"]["assignee"] == "child"
    available = finalize(state, now, receipt, actor="parent", verifiedmime="image/webp")
    assert (
        media.attach_task_report(
            ctx(state, "parent", now),
            task,
            {"id": available["id"], "revision": available["revision"]},
        )["status"]
        == "attached"
    )


def test_pending_quota_counts_reserved_and_unattached_available(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    receipts = [reserve(state, now, task) for _ in range(5)]
    finalize(state, now, receipts[0])
    before = deepcopy(state)

    with pytest.raises(DomainError, match="quota_exceeded"):
        reserve(state, now, task)
    assert state == before
    assert sum(item["status"] == "reserved" for item in state["media"].values()) == 4
    assert sum(item["status"] == "available" for item in state["media"].values()) == 1


def test_household_pending_and_storage_budget_are_bounded(engine, now):
    state = engine.snapshot()
    for index in range(20):
        member_id = f"uploader-{index}"
        state["members"][member_id] = {
            "id": member_id,
            "name": member_id,
            "role": "adult",
            "language": "en",
            "aliases": [],
            "active": True,
            "revision": 1,
        }
        task = photo_task(state, now, assignee=member_id)
        reserve(state, now, task, actor=member_id)
    task = photo_task(state, now)
    before = deepcopy(state)
    with pytest.raises(DomainError, match="quota_exceeded"):
        reserve(state, now, task)
    assert state == before

    budget_state = engine.snapshot()
    budget_task = photo_task(budget_state, now)
    budget_state["media"] = {
        f"M{index:032x}": {"status": "attached", "size_bytes": media.MAX_FILE_BYTES}
        for index in range(25)
    }
    before = deepcopy(budget_state)
    with pytest.raises(DomainError, match="quota_exceeded"):
        reserve(budget_state, now, budget_task)
    assert budget_state == before


def test_finalize_is_strict_and_exact_retry_is_stable(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    reserved = reserve(state, now, task)

    available = finalize(state, now, reserved)
    assert available == {"id": reserved["id"], "revision": 2, "status": "available"}
    assert finalize(state, now + timedelta(minutes=1), reserved) == available
    record = state["media"][reserved["id"]]
    assert record["expires_at"] == (now + timedelta(hours=24)).isoformat()

    for overrides in (
        {"verifiedmime": "application/pdf"},
        {"size": True},
        {"size": 0},
        {"size": media.MAX_FILE_BYTES + 1},
        {"sha256": "A" * 64},
        {"sha256": "../blob"},
    ):
        before = deepcopy(state)
        with pytest.raises(DomainError):
            finalize(state, now, reserved, **overrides)
        assert state == before
    with pytest.raises(DomainError, match="conflict"):
        finalize(state, now, reserved, size=1235)


@pytest.mark.parametrize("mime_type", sorted(media.IMAGE_MIME_TYPES))
def test_finalize_accepts_each_bounded_image_type_at_exact_size_limit(engine, now, mime_type):
    state = engine.snapshot()
    task = photo_task(state, now)
    reserved = reserve(state, now, task)
    receipt = finalize(
        state,
        now,
        reserved,
        verifiedmime=mime_type,
        size=media.MAX_FILE_BYTES,
    )
    assert receipt["status"] == "available"
    assert state["media"][receipt["id"]]["size_bytes"] == media.MAX_FILE_BYTES


def test_finalize_rechecks_uploader_task_and_expiry_without_partial_writes(engine, now):
    base = engine.snapshot()
    task = photo_task(base, now)
    reserved = reserve(base, now, task)
    cases = [
        lambda state: state["members"]["child"].update(revision=2),
        lambda state: state["tasks"][task["id"]].update(revision=2),
        lambda state: state["settings"]["modules"].remove("tasks"),
    ]
    for mutate in cases:
        state = deepcopy(base)
        mutate(state)
        before = deepcopy(state)
        with pytest.raises(DomainError):
            finalize(state, now, reserved)
        assert state == before
    expired = deepcopy(base)
    before = deepcopy(expired)
    with pytest.raises(DomainError, match="invalid_transition"):
        finalize(expired, now + timedelta(hours=1), reserved)
    assert expired == before


def test_attach_is_atomic_consumer_helper_and_public_metadata_is_redacted(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    reserved = reserve(state, now, task)
    available = finalize(state, now, reserved)
    task_revision = task["revision"]

    attached = media.attach_task_report(
        ctx(state, "child", now), task, {"id": available["id"], "revision": available["revision"]}
    )
    assert attached == {"id": available["id"], "revision": 3, "status": "attached"}
    assert task["revision"] == task_revision  # The consumer owns its final task touch.
    assert task["report_generation"] == 1 and task["report_media"] == [available["id"]]
    record = state["media"][available["id"]]
    assert record["scope"] == {
        "kind": "task_report",
        "task_id": task["id"],
        "report_generation": 1,
        "assignee": "child",
        "assignee_revision": 1,
    }
    projected = media.read_metadata(state, state["members"]["child"], available["id"], now)
    assert set(projected) == set(media.PUBLIC_FIELDS)
    assert projected["status"] == "attached"
    assert all(secret not in projected for secret in ("sha256", "blob_key", "uploader", "scope"))
    internal = media.authorize_blob(state, state["members"]["parent"], available["id"], now)
    assert internal["sha256"] == DIGEST and internal["blob_key"] == record["blob_key"]
    for actor in ("sibling", "adult", "guest"):
        with pytest.raises(DomainError, match="forbidden"):
            media.read_metadata(state, state["members"][actor], available["id"], now)


def test_attach_rejects_wrong_owner_revision_target_and_second_media(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    first = reserve(state, now, task)
    second = reserve(state, now, task)
    first = finalize(state, now, first)
    second = finalize(state, now, second)
    original = deepcopy(state)

    with pytest.raises(DomainError, match="forbidden"):
        media.attach_task_report(
            ctx(state, "parent", now), task, {"id": first["id"], "revision": first["revision"]}
        )
    assert state == original
    media.attach_task_report(
        ctx(state, "child", now), task, {"id": first["id"], "revision": first["revision"]}
    )
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_transition"):
        media.attach_task_report(
            ctx(state, "child", now), task, {"id": second["id"], "revision": second["revision"]}
        )
    assert state == before


def test_reassignment_retains_parent_historical_access_but_not_former_or_new_assignee(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    receipt = finalize(state, now, reserve(state, now, task))
    media.attach_task_report(
        ctx(state, "child", now),
        task,
        {"id": receipt["id"], "revision": receipt["revision"]},
    )
    record = state["media"][receipt["id"]]
    task["previous_reports"] = [
        {
            "assignee": "child",
            "assignee_revision": 1,
            "report_generation": 1,
            "report_media": [record["id"]],
        }
    ]
    task.update(
        assignee="sibling",
        assignee_revision=1,
        report_generation=2,
        report_media=[],
        revision=task["revision"] + 1,
    )

    assert (
        media.read_metadata(state, state["members"]["parent"], record["id"], now)["status"]
        == "attached"
    )
    for actor in ("child", "sibling"):
        with pytest.raises(DomainError, match="forbidden"):
            media.read_metadata(state, state["members"][actor], record["id"], now)


def test_read_and_replay_fail_after_epoch_module_or_source_change(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    payload = {
        "purpose": "task_report",
        "task_id": task["id"],
        "task_revision": task["revision"],
        "uploader_revision": 1,
    }
    receipt = media.handle(ctx(state, "child", now), "reserve", payload)
    media.authorize_replay(ctx(state, "child", now), "reserve", payload, receipt)
    assert (
        media.read_metadata(state, state["members"]["child"], receipt["id"], now)["status"]
        == "reserved"
    )

    for mutate in (
        lambda value: value["members"]["child"].update(revision=2),
        lambda value: value["tasks"][task["id"]].update(revision=2),
        lambda value: value["settings"].update(
            modules=[item for item in value["settings"]["modules"] if item != "tasks"]
        ),
    ):
        changed = deepcopy(state)
        mutate(changed)
        with pytest.raises(DomainError):
            media.authorize_replay(ctx(changed, "child", now), "reserve", payload, receipt)
        with pytest.raises(DomainError):
            media.read_metadata(changed, changed["members"]["child"], receipt["id"], now)


def test_missing_media_is_a_uniform_denial_and_available_expires(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    reserved = reserve(state, now, task)
    available = finalize(state, now, reserved)

    with pytest.raises(DomainError, match="forbidden"):
        media.read_metadata(state, state["members"]["child"], f"M{'f' * 32}", now)
    with pytest.raises(DomainError, match="forbidden"):
        media.read_metadata(
            state,
            state["members"]["child"],
            available["id"],
            now + timedelta(hours=24),
        )


def test_expire_and_finish_delete_are_two_phase_minimal_and_exactly_idempotent(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    reserved = reserve(state, now, task)
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_transition"):
        media.expire_pending(system_ctx(state, now), reserved["id"], reserved["revision"])
    assert state == before

    deleting = media.expire_pending(
        system_ctx(state, now + timedelta(hours=1)), reserved["id"], reserved["revision"]
    )
    assert deleting == {"id": reserved["id"], "revision": 2, "status": "deleting"}
    private = state["media"][reserved["id"]]
    assert private["blob_key"] and private["scope"] and private["size_bytes"] is None
    assert media.deleting_blob(state, deleting["id"], deleting["revision"]) == private["blob_key"]
    assert (
        media.expire_pending(
            system_ctx(state, now + timedelta(hours=1)), reserved["id"], reserved["revision"]
        )
        == deleting
    )

    deleted = media.finish_delete(
        system_ctx(state, now + timedelta(hours=1, seconds=1)),
        reserved["id"],
        deleting["revision"],
    )
    assert deleted == {"id": reserved["id"], "revision": 3, "status": "deleted"}
    assert set(state["media"][reserved["id"]]) == {
        "id",
        "revision",
        "status",
        "created_at",
        "updated_at",
        "deleted_at",
    }
    assert (
        media.finish_delete(
            system_ctx(state, now + timedelta(hours=2)), reserved["id"], deleting["revision"]
        )
        == deleted
    )


def test_gc_never_deletes_attached_media_and_errors_do_not_partially_mutate(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    receipt = finalize(state, now, reserve(state, now, task))
    attached = media.attach_task_report(
        ctx(state, "child", now),
        task,
        {"id": receipt["id"], "revision": receipt["revision"]},
    )
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_transition"):
        media.expire_pending(
            system_ctx(state, now + timedelta(days=365)), attached["id"], attached["revision"]
        )
    assert state == before
    with pytest.raises(DomainError, match="invalid_transition"):
        media.finish_delete(system_ctx(state, now), attached["id"], attached["revision"])
    assert state == before


def test_parent_retains_current_reference_after_child_epoch_change_but_child_is_denied(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    receipt = finalize(state, now, reserve(state, now, task))
    media.attach_task_report(
        ctx(state, "child", now),
        task,
        {"id": receipt["id"], "revision": receipt["revision"]},
    )
    state["members"]["child"]["revision"] = 2

    assert (
        media.read_metadata(state, state["members"]["parent"], receipt["id"], now)["status"]
        == "attached"
    )
    with pytest.raises(DomainError, match="forbidden"):
        media.read_metadata(state, state["members"]["child"], receipt["id"], now)


def test_deleting_reserved_upload_keeps_full_budget_until_unlink_finishes(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    reserved = reserve(state, now, task)
    media.expire_pending(
        system_ctx(state, now + timedelta(hours=1)), reserved["id"], reserved["revision"]
    )
    state["media"].update(
        {
            f"M{index:032x}": {"status": "attached", "size_bytes": media.MAX_FILE_BYTES}
            for index in range(24)
        }
    )
    before = deepcopy(state)
    with pytest.raises(DomainError, match="quota_exceeded"):
        reserve(state, now + timedelta(hours=1), task)
    assert state == before


def test_metadata_record_count_is_hard_bounded(engine, now):
    state = engine.snapshot()
    task = photo_task(state, now)
    state["media"] = {f"M{index:032x}": {"status": "deleted"} for index in range(media.MAX_RECORDS)}
    before = deepcopy(state)
    with pytest.raises(DomainError, match="quota_exceeded"):
        reserve(state, now, task)
    assert state == before
