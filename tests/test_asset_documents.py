"""Equipment document authority, immutable append and atomic Store boundaries."""

from copy import deepcopy

import pytest
from test_maintenance_engine import asset_payload

from custom_components.family_assistant.assistant.plans import projection
from custom_components.family_assistant.domain import media
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def setup(engine, store, now):
    state = engine.snapshot()
    state["settings"]["modules"] = ["maintenance"]
    e = Engine(state, store.save)
    asset = await e.execute(
        "parent", "maintenance.asset_save", asset_payload(e, reportable=True), "asset", now
    )
    return e, asset


def reservation(e, asset, actor="parent"):
    return {
        "purpose": "equipment_document",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "uploader_revision": e.snapshot()["members"][actor]["revision"],
    }


async def upload(e, asset, now, *, operation="upload", mime="application/pdf"):
    reserved = await e.execute("parent", "media.reserve", reservation(e, asset), operation, now)
    return await e.system_update(
        operation + "-verified",
        now,
        lambda ctx: media.finalize(
            ctx, "parent", reserved["id"], reserved["revision"], mime, 100, "a" * 64
        ),
    )


def payload(e, asset, uploaded, *, actor="parent"):
    return {
        "id": asset["id"],
        "revision": asset["revision"],
        "actor_member_revision": e.snapshot()["members"][actor]["revision"],
        "media": {"id": uploaded["id"], "revision": uploaded["revision"]},
        "title": "Synthetic warranty",
        "kind": "warranty",
        "note": "DOCUMENT-PRIVATE-CANARY",
    }


def metadata(e, actor, identifier, now):
    state = e.snapshot()
    return media.read_metadata(state, state["members"][actor], identifier, now)


@pytest.mark.asyncio
@pytest.mark.parametrize("mime", sorted(media.MIME_TYPES))
async def test_documents_private_until_attached_parent_only_then_persist_exactly(
    engine, store, now, mime
):
    e, asset = await setup(engine, store, now)
    before = e.snapshot()
    uploaded = await upload(e, asset, now, mime=mime)
    assert metadata(e, "parent", uploaded["id"], now)["status"] == "available"
    with pytest.raises(DomainError):
        metadata(e, "owner", uploaded["id"], now)
    command = payload(e, asset, uploaded)
    attached = await e.execute("parent", "maintenance.document_attach", command, "attach", now)
    assert attached["status"] == "attached"
    for actor in ("owner", "parent"):
        assert metadata(e, actor, uploaded["id"], now)["status"] == "attached"
        row = e.view(actor, now=now)["maintenance"]["documents"][0]
        assert row["note"] == "DOCUMENT-PRIVATE-CANARY"
        assert row["attachment"]["mime_type"] == mime
        assert "blob_key" not in repr(row) and "sha256" not in repr(row)
    for actor in ("adult", "child", "sibling", "guest"):
        with pytest.raises(DomainError):
            metadata(e, actor, uploaded["id"], now)
        assert "DOCUMENT-PRIVATE-CANARY" not in repr(e.view(actor, now=now))
    assert "DOCUMENT-PRIVATE-CANARY" not in repr(projection(e.view("parent", now=now)))
    for bucket in ("tasks", "task_series", "outbox", "court", "alarm_runs", "routine_runs"):
        assert e.snapshot()[bucket] == before[bucket]
    assert e.snapshot()["maintenance"]["assets"] == before["maintenance"]["assets"], (
        "Document append must not suspend service rules by changing equipment revisions"
    )
    restored = Engine(deepcopy(store.value), store.save)
    state, writes = restored.snapshot(), store.calls
    assert (
        await restored.execute("parent", "maintenance.document_attach", command, "attach", now)
        == attached
    )
    assert restored.snapshot() == state and store.calls == writes


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["adult", "child", "sibling", "guest"])
async def test_reportable_asset_does_not_grant_document_upload(engine, store, now, actor):
    e, asset = await setup(engine, store, now)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(actor, "media.reserve", reservation(e, asset, actor), "denied", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_attachment_store_failure_keeps_upload_unattached(engine, store, now):
    e, asset = await setup(engine, store, now)
    uploaded = await upload(e, asset, now)
    command, before = payload(e, asset, uploaded), e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("parent", "maintenance.document_attach", command, "attach", now)
    assert e.snapshot() == before
    store.fail = False
    await e.execute("parent", "maintenance.document_attach", command, "attach", now)


@pytest.mark.asyncio
async def test_owner_purge_revokes_bytes_and_replays_after_collector(engine, store, now):
    e, asset = await setup(engine, store, now)
    uploaded = await upload(e, asset, now)
    attached = await e.execute(
        "parent", "maintenance.document_attach", payload(e, asset, uploaded), "attach", now
    )
    attachment = metadata(e, "owner", uploaded["id"], now)
    command = {
        "id": asset["id"],
        "revision": asset["revision"],
        "actor_member_revision": 1,
        "media": {"id": attachment["id"], "revision": attachment["revision"]},
        "document": {"id": attached["id"], "revision": attached["revision"]},
        "reason": "Synthetic explicit purge",
    }
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute("parent", "maintenance.document_purge", command, "parent-denied", now)
    assert e.snapshot() == before
    result = await e.execute("owner", "maintenance.document_purge", command, "purge", now)
    for actor in ("owner", "parent"):
        with pytest.raises(DomainError):
            metadata(e, actor, uploaded["id"], now)
    record = e.snapshot()["media"][uploaded["id"]]
    await e.system_update(
        "synthetic-collector",
        now,
        lambda ctx: media.finish_delete(ctx, record["id"], record["revision"]),
    )
    before = e.snapshot()
    assert await e.execute("owner", "maintenance.document_purge", command, "purge", now) == result
    assert e.snapshot() == before
    assert e.view("parent", now=now)["maintenance"]["documents"][0]["status"] == "deleted"


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["member", "role", "module", "asset"])
async def test_changed_upload_source_cannot_attach(engine, store, now, drift):
    e, asset = await setup(engine, store, now)
    uploaded = await upload(e, asset, now)
    command = payload(e, asset, uploaded)
    state = e.snapshot()
    if drift == "member":
        state["members"]["parent"]["revision"] += 1
    if drift == "role":
        state["members"]["parent"]["role"] = "child"
    if drift == "module":
        state["settings"]["modules"] = []
    if drift == "asset":
        state["maintenance"]["assets"][asset["id"]]["revision"] += 1
    e = Engine(state, store.save)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute("parent", "maintenance.document_attach", command, "attach", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_tenth_document_limit_and_reverse_reference(engine, store, now):
    e, asset = await setup(engine, store, now)
    for index in range(10):
        uploaded = await upload(e, asset, now, operation=f"upload-{index}")
        await e.execute(
            "parent",
            "maintenance.document_attach",
            payload(e, asset, uploaded),
            f"attach-{index}",
            now,
        )
    before = e.snapshot()
    with pytest.raises(DomainError, match="quota_exceeded"):
        await upload(e, asset, now, operation="eleventh")
    assert e.snapshot() == before
    first = next(iter(before["maintenance"]["documents"].values()))
    first["asset_id"] = "missing"
    e = Engine(before, store.save)
    with pytest.raises(DomainError):
        metadata(e, "owner", first["media_id"], now)
