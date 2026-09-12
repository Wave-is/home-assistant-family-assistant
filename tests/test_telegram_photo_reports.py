"""Actual Engine, real MediaStorage files and Pillow decoder; synthetic Telegram only."""

import asyncio
import io
import os
from copy import deepcopy
from datetime import timedelta

import pytest
from ha_telegram_smoke import next_synthetic_update_id
from PIL import Image
from test_telegram_command_scope import BOT, NOW, fixture, update
from test_telegram_command_scope import manager_module as manager_module

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.media_storage import MediaStorage
from custom_components.family_assistant.media_validation import MediaValidationError, verify
from custom_components.family_assistant.notifications import DeliveryError


def png():
    output = io.BytesIO()
    Image.new("RGB", (7, 5), (21, 42, 84)).save(output, format="PNG")
    return output.getvalue()


async def verify_synthetic_image(path):
    # Windows lacks POSIX rlimits; exercise the actual validator, not a fake
    # metadata decoder. Real-HA Linux acceptance uses the default isolated process.
    try:
        return await asyncio.to_thread(verify, path)
    except MediaValidationError as error:
        raise DomainError(error.code) from None


def storage(engine, root):
    options = {"decoder": verify_synthetic_image} if os.name == "nt" else {}
    return MediaStorage(engine, root, clock=lambda: NOW, **options)


async def configure(module, tmp_path):
    engine, store, entry, runtime, manager, client = fixture(module)

    def prepare(ctx):
        ctx.state["settings"]["modules"].remove("conversation")
        for member_id, telegram_id in (("child", 202), ("other", 303)):
            ctx.state["members"][member_id] = {
                "id": member_id,
                "name": member_id,
                "role": "child",
                "language": "en",
                "telegram_id": telegram_id,
                "revision": 1,
                "active": True,
                "aliases": [],
            }

    await engine.system_update("synthetic_members", NOW, prepare)
    created = await engine.execute(
        "owner",
        "tasks.create",
        {
            "title": "Synthetic photo evidence",
            "assignee": "child",
            "report_type": "photo",
        },
        "synthetic-create",
        NOW,
    )
    runtime.media = storage(engine, tmp_path / "private-media")
    client.downloads = []

    async def download(file_id):
        client.downloads.append(file_id)
        return png()

    client.download_file = download
    return engine, store, entry, runtime, manager, client, created["id"]


def incoming(task_id, *, update_id=10, user_id=202, caption=None, reply_to=None):
    value = update(update_id)
    message = value["message"]
    message.pop("text")
    message["from"]["id"] = message["chat"]["id"] = user_id
    message["photo"] = [{"file_id": "synthetic-evidence", "file_size": len(png())}]
    if task_id is not None:
        message["caption"] = caption if caption is not None else f"/report {task_id}"
    if reply_to is not None:
        message["reply_to_message"] = {
            "message_id": reply_to,
            "from": {"id": BOT["id"], "is_bot": True},
            "text": "Untrusted task text T999999",
        }
    return value


def job(engine):
    return next(iter(engine.snapshot()["telegram"]["photo_jobs"].values()))


async def test_photo_report_real_blob_survives_restart_without_ha_account_or_model(
    manager_module,
    tmp_path,
):
    engine, store, entry, runtime, manager, client, task_id = await configure(
        manager_module, tmp_path
    )
    message = incoming(task_id)
    await asyncio.wait_for(manager.process(message), 0.5)
    assert not client.downloads and not engine.snapshot()["assistant_jobs"]
    assert job(engine)["status"] == "pending"
    await manager.process(update(11, text="/ping"))
    assert not client.downloads
    restarted = Engine(store.value, store.save)
    await runtime.media.stop()
    runtime.engine = restarted
    runtime.media = storage(restarted, tmp_path / "private-media")
    replacement = manager_module.TelegramManager(manager.hass, entry, runtime, client, BOT)
    runtime.telegram = replacement
    try:
        await replacement.photo_reports.run_one()
        result = job(restarted)
        state = restarted.snapshot()
        assert result["status"] == "complete", state["outbox"]
        assert state["tasks"][task_id]["status"] == "submitted"
        assert state["tasks"][task_id]["report_media"] == [result["media_id"]]
        media = state["media"][result["media_id"]]
        assert media["status"] == "attached" and media["uploader"] == "child"
        assert (tmp_path / "private-media" / media["blob_key"]).read_bytes() == png()
        assert state["tasks"][task_id]["report"] is None
        assert not state["assistant_jobs"] and not state["proposals"]
        assert client.downloads == ["synthetic-evidence"]
        await replacement.process(message)
        assert await replacement.photo_reports.run_one() is False
        assert len(restarted.snapshot()["media"]) == 1
    finally:
        await runtime.media.stop()


@pytest.mark.parametrize(
    "kind", ["cross_user", "unknown", "forward", "album", "note", "quoted_only", "private_group"]
)
async def test_report_rejects_unauthorized_or_ambiguous_input_before_download(
    manager_module,
    tmp_path,
    kind,
):
    engine, _store, _entry, runtime, manager, client, task_id = await configure(
        manager_module, tmp_path
    )
    value = incoming(task_id)
    message = value["message"]
    if kind in {"cross_user", "unknown"}:
        message["from"]["id"] = message["chat"]["id"] = 303 if kind == "cross_user" else 404
    elif kind == "forward":
        message["forward_origin"] = {"type": "hidden_user"}
    elif kind == "album":
        message["media_group_id"] = "synthetic-album"
    elif kind == "note":
        message["caption"] += " done all work"
    elif kind == "quoted_only":
        message["reply_to_message"] = {"from": {"id": 202}, "photo": message.pop("photo")}
    else:
        await engine.system_update(
            "synthetic_private",
            NOW,
            lambda ctx: ctx.state["tasks"][task_id].update(delivery_scope="private"),
        )
        message["chat"] = {"id": -101, "type": "supergroup"}
    try:
        await manager.process(value)
        assert not client.downloads
        assert not engine.snapshot()["telegram"].get("photo_jobs")
        assert not engine.snapshot().get("media")
        assert engine.snapshot()["tasks"][task_id]["status"] == "assigned"
    finally:
        await runtime.media.stop()


async def prompt_receipt(engine, task_id, *, duplicate=False, current=True):
    def stamp(ctx):
        event = next(
            row
            for row in ctx.state["outbox"].values()
            if row["key"] == "task_assigned" and row["data"]["id"] == task_id
        )
        event["state"] = "sent"
        event["deliveries"] = {
            "synthetic": {
                "state": "sent" if current else "uncertain",
                "receipt": "50",
                "sent_at": NOW.isoformat(),
                "target": {"channel": "telegram", "id": 202, "bot_id": BOT["id"]},
            }
        }
        if duplicate:
            duplicate_event = deepcopy(event)
            duplicate_event["id"] = "synthetic-duplicate"
            ctx.state["outbox"][duplicate_event["id"]] = duplicate_event

    await engine.system_update("synthetic_receipt", NOW, stamp)


@pytest.mark.parametrize("kind", ["bound", "forged", "duplicate", "uncertain", "wrong_chat"])
async def test_photo_reply_requires_exact_unique_sent_task_prompt(manager_module, tmp_path, kind):
    engine, _store, _entry, runtime, manager, client, task_id = await configure(
        manager_module, tmp_path
    )
    if kind != "forged":
        await prompt_receipt(
            engine, task_id, duplicate=kind == "duplicate", current=kind != "uncertain"
        )
    value = incoming(None, reply_to=50, user_id=303 if kind == "wrong_chat" else 202)
    try:
        await manager.process(value)
        if kind == "bound":
            assert job(engine)["task_id"] == task_id
            await manager.photo_reports.run_one()
            assert engine.snapshot()["tasks"][task_id]["status"] == "submitted"
        else:
            assert not engine.snapshot()["telegram"].get("photo_jobs")
            assert not client.downloads
    finally:
        await runtime.media.stop()


@pytest.mark.parametrize(
    "kind", ["rebind", "task_changed", "config_changed", "corrupt", "unavailable", "expired"]
)
async def test_stale_or_invalid_photo_never_submits_or_reports_success(
    manager_module, tmp_path, kind
):
    engine, _store, entry, runtime, manager, client, task_id = await configure(
        manager_module, tmp_path
    )
    await manager.process(incoming(task_id))
    if kind == "expired":
        manager.photo_reports.now = lambda: NOW + timedelta(minutes=11)

    async def download(_file_id):
        if kind == "rebind":
            await engine.system_update(
                "synthetic_rebind",
                NOW,
                lambda ctx: ctx.state["members"]["child"].update(revision=2),
            )
        elif kind == "task_changed":
            await engine.execute(
                "owner",
                "tasks.revise",
                {"id": task_id, "revision": 1, "title": "Changed task"},
                "synthetic-revise",
                NOW,
            )
        elif kind == "config_changed":
            entry.options = {**entry.options, "telegram": {"bots": []}}
        elif kind == "corrupt":
            return b"not-an-image"
        elif kind == "unavailable":
            raise DeliveryError("telegram_timeout", retryable=True)
        return png()

    client.download_file = download
    try:
        if kind == "config_changed":
            with pytest.raises(DomainError, match="forbidden"):
                await manager.photo_reports.run_one()
        else:
            await manager.photo_reports.run_one()
        assert engine.snapshot()["tasks"][task_id]["status"] == "assigned"
        responses = [
            row["data"].get("text", "")
            for row in engine.snapshot()["outbox"].values()
            if ":photo-result:" in row["id"]
        ]
        assert not any("saved and submitted" in response for response in responses)
    finally:
        await runtime.media.stop()


async def test_successful_submission_recovers_after_queue_finish_store_failure(
    manager_module, tmp_path
):
    engine, store, _entry, runtime, manager, client, task_id = await configure(
        manager_module, tmp_path
    )
    await manager.process(incoming(task_id))
    save = engine._persist
    failed = False

    async def fail_completion(state):
        nonlocal failed
        if (
            not failed
            and next(iter(state["telegram"]["photo_jobs"].values()))["status"] == "complete"
        ):
            failed = True
            raise OSError("synthetic store failure")
        await save(state)

    engine._persist = fail_completion
    try:
        with pytest.raises(OSError):
            await manager.photo_reports.run_one()
        assert engine.snapshot()["tasks"][task_id]["status"] == "submitted"
        assert job(engine)["status"] == "pending"
        manager.photo_reports.now = lambda: NOW + timedelta(minutes=11)
        await manager.photo_reports.run_one()
        assert job(engine)["status"] == "complete"
        assert client.downloads == ["synthetic-evidence"]
        assert len(engine.snapshot()["media"]) == 1
    finally:
        await runtime.media.stop()


async def test_actor_upload_rechecks_identity_after_decoder_and_locked_wait(
    manager_module, tmp_path
):
    engine, store, _entry, runtime, manager, _client, task_id = await configure(
        manager_module, tmp_path
    )
    await manager.process(incoming(task_id))
    started, release = asyncio.Event(), asyncio.Event()

    async def paused_decoder(path):
        result = await verify_synthetic_image(path)
        started.set()
        await release.wait()
        return result

    runtime.media.decoder = paused_decoder
    worker = asyncio.create_task(manager.photo_reports.run_one())
    try:
        await asyncio.wait_for(started.wait(), 3)
        store.block = True
        rebind = asyncio.create_task(
            engine.system_update(
                "synthetic_locked_rebind",
                NOW,
                lambda ctx: ctx.state["members"]["child"].update(revision=2),
            )
        )
        await asyncio.wait_for(store.started.wait(), 1)
        release.set()
        await asyncio.sleep(0.03)
        store.release.set()
        await rebind
        await asyncio.wait_for(worker, 3)
        state = engine.snapshot()
        assert state["tasks"][task_id]["status"] == "assigned"
        assert state["media"][job(engine)["media_id"]]["status"] == "reserved"
        assert job(engine)["status"] == "cancelled"
    finally:
        release.set()
        store.release.set()
        await runtime.media.stop()


async def test_actor_upload_cannot_borrow_another_members_reservation(manager_module, tmp_path):
    engine, _store, _entry, runtime, manager, _client, task_id = await configure(
        manager_module, tmp_path
    )
    await manager.process(incoming(task_id))
    row = job(engine)

    async def chunks():
        yield png()

    async def allowed():
        return None

    try:
        with pytest.raises(DomainError, match="forbidden"):
            await runtime.media.put_for_actor(
                "other",
                1,
                row["media_id"],
                row["media_revision"],
                chunks(),
                guard=allowed,
                state_guard=lambda _state: None,
            )
        assert engine.snapshot()["media"][row["media_id"]]["status"] == "reserved"
    finally:
        await runtime.media.stop()


async def test_native_synthetic_receiver_does_not_reuse_a_direct_callback_id(
    manager_module, tmp_path
):
    engine, _store, _entry, runtime, manager, _client, task_id = await configure(
        manager_module, tmp_path
    )
    callback = {
        "update_id": 12,
        "callback_query": {
            "id": "synthetic-callback",
            "from": {"id": 202, "is_bot": False},
            "message": {"message_id": 1, "chat": {"id": 202, "type": "private"}},
            "data": "synthetic-invalid-button",
        },
    }
    try:
        await manager.process(callback)
        next_id = next_synthetic_update_id(runtime, 11)
        assert next_id == 13
        await manager.process(incoming(task_id, update_id=next_id))
        assert job(engine)["status"] == "pending"
        assert engine.snapshot()["telegram"]["offsets"][str(BOT["id"])] == 14
    finally:
        await runtime.media.stop()
