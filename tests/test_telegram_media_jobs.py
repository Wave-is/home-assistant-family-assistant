"""Synthetic Telegram photo work uses the real manager, durable jobs and engine."""

import asyncio
import base64
from contextlib import suppress
from copy import deepcopy

import pytest
from test_telegram_command_scope import BOT, NOW, fixture, update
from test_telegram_command_scope import manager_module as manager_module

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import DeliveryError


class Cascade:
    def __init__(self):
        self.calls = []

    async def generate(self, messages, schema, validate, *, scope_check=None):
        if scope_check:
            scope_check()
        self.calls.append(deepcopy(messages))
        return validate({"kind": "answer", "text": "Synthetic image description"})


def configure(module):
    engine, store, entry, runtime, manager, client = fixture(module)
    cascade = Cascade()
    runtime.assistant_revision = "a" * 32
    runtime.assistant_config_digest = module.conversation_digest(entry.options["conversation"])
    runtime.assistant = module.Assistant(engine, cascade)
    return engine, store, entry, runtime, manager, client, cascade


def photo_update():
    message = update(text="Describe this photo")
    message["message"]["photo"] = [{"file_id": "synthetic-photo", "file_size": 100}]
    return message


async def complete_one(manager, engine, job_id):
    worker = asyncio.create_task(manager._conversations())
    try:
        async with asyncio.timeout(3):
            while engine.snapshot()["assistant_jobs"][job_id]["status"] == "pending":
                await asyncio.sleep(0.01)
    finally:
        manager._stopped = True
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


async def test_photo_reference_survives_restart_and_polling_never_downloads(manager_module):
    engine, store, entry, runtime, manager, client, cascade = configure(manager_module)
    downloads = []

    async def download(file_id):
        downloads.append(file_id)
        return b"synthetic-image"

    client.download_file = download
    await asyncio.wait_for(manager.process(photo_update()), 0.5)
    assert not downloads and not cascade.calls and not client.calls
    job_id = f"tg:{BOT['id']}:10:action"
    assert store.value["assistant_jobs"][job_id]["image_file_id"] == "synthetic-photo"
    await manager.process(update(11, text="/ping"))
    assert not downloads
    restarted = Engine(store.value, store.save)
    runtime.engine = restarted
    runtime.assistant = manager_module.Assistant(restarted, cascade)
    manager = manager_module.TelegramManager(manager.hass, entry, runtime, client, BOT)
    runtime.telegram = manager
    await complete_one(manager, restarted, job_id)
    assert downloads == ["synthetic-photo"]
    assert len(cascade.calls) == 2
    assert "images" not in cascade.calls[0][-1]
    assert cascade.calls[1][-1]["images"] == [base64.b64encode(b"synthetic-image").decode()]
    assert not restarted.snapshot()["proposals"]
    assert base64.b64encode(b"synthetic-image").decode() not in str(store.value)


async def test_photo_failure_is_honest_and_never_calls_provider(manager_module):
    engine, _store, _entry, _runtime, manager, client, cascade = configure(manager_module)

    async def unavailable(_file_id):
        raise DeliveryError("telegram_timeout", retryable=True)

    client.download_file = unavailable
    await manager.process(photo_update())
    job_id = f"tg:{BOT['id']}:10:action"
    await complete_one(manager, engine, job_id)
    result = next(
        event
        for event in engine.snapshot()["outbox"].values()
        if event["id"].startswith(job_id + ":model-result")
    )
    assert "Synthetic image description" not in result["data"]["text"]
    assert not cascade.calls


async def test_attachment_cannot_change_on_job_replay_or_authorization(manager_module):
    engine, _store, _entry, _runtime, manager, _client, _cascade = configure(manager_module)
    await manager.process(photo_update())
    job = manager.jobs.next(BOT["id"])
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await manager.jobs.enqueue(
            "owner",
            job["content"],
            job["id"],
            NOW,
            job["refs"],
            bot_id=BOT["id"],
            chat_id=101,
            reply_to=10,
            image_file_id="different-photo",
        )
    job["image_file_id"] = "different-photo"
    with pytest.raises(DomainError, match="forbidden"):
        manager.jobs.authorize(job, NOW)
    assert engine.snapshot()["assistant_jobs"][job["id"]]["image_file_id"] == "synthetic-photo"


@pytest.mark.parametrize("kind", ["unknown_actor", "forward", "unaddressed", "other_bot"])
async def test_observations_require_authorized_addressed_message(manager_module, kind):
    engine, _store, _entry, _runtime, manager, _client, _cascade = configure(manager_module)
    incoming = update(group=True, text="@synthetic_family_bot hello")
    if kind == "unknown_actor":
        incoming["message"]["from"]["id"] = 999
    elif kind == "forward":
        incoming["message"]["forward_origin"] = {"type": "hidden_user"}
    elif kind == "unaddressed":
        incoming["message"]["text"] = "hello family"
    else:
        incoming["message"]["text"] = "/help@different_bot"
    await manager.process(incoming)
    assert not engine.snapshot()["telegram"].get("observations")


async def test_observations_record_commands_and_text_without_content(manager_module):
    engine, _store, _entry, _runtime, manager, _client, _cascade = configure(manager_module)
    await manager.process(update(text="/ping"))
    await manager.process(update(11, group=True, text="@synthetic_family_bot hello"))
    assert engine.snapshot()["telegram"]["observations"] == {
        str(BOT["id"]): {
            "command_received_at": NOW.isoformat(),
            "text_received_at": NOW.isoformat(),
            "config_digest": manager._telegram_options_digest,
        }
    }


async def test_observation_epoch_does_not_revalidate_old_text_delivery(manager_module):
    engine, _store, _entry, _runtime, manager, _client, _cascade = configure(manager_module)
    await engine.system_update(
        "old_observation",
        NOW,
        lambda ctx: ctx.state["telegram"].update(
            observations={
                str(BOT["id"]): {"config_digest": "old", "text_received_at": NOW.isoformat()}
            }
        ),
    )
    await manager.process(update(text="/ping"))
    observed = engine.snapshot()["telegram"]["observations"][str(BOT["id"])]
    assert observed == {
        "config_digest": manager._telegram_options_digest,
        "command_received_at": NOW.isoformat(),
    }


async def test_native_menu_has_real_commands_without_sending_chat_messages(manager_module):
    _engine, _store, _entry, runtime, manager, client, _cascade = configure(manager_module)
    calls = []

    async def call(method, payload):
        calls.append((method, payload))
        return True

    client.call = call
    await manager._install_menu()
    assert len(calls) == 4 and all(method == "setMyCommands" for method, _ in calls)
    assert {payload["language_code"] for _, payload in calls} == {"", "en", "ru", "uk"}
    assert all(
        {"ask", "commands", "alarm", "approvebuy"}
        <= {row["command"] for row in payload["commands"]}
        for _, payload in calls
    )
    assert "telegram_menu" not in runtime.health


async def test_native_menu_false_result_never_claims_success(manager_module):
    _engine, _store, _entry, runtime, manager, client, _cascade = configure(manager_module)

    async def call(_method, _payload):
        return False

    client.call = call
    await manager._install_menu()
    assert runtime.health["telegram_menu"] == "telegram_bad_response"


async def test_replacement_start_resets_only_current_transport_evidence(manager_module):
    engine, _store, entry, runtime, old, client, _cascade = configure(manager_module)
    launched = []

    def background(coroutine, name):
        launched.append(name)
        coroutine.close()
        return name

    old.hass.async_create_background_task = background
    runtime.health["telegram"] = "connected"
    replacement = manager_module.TelegramManager(old.hass, entry, runtime, client, BOT)
    runtime.telegram = replacement
    with pytest.raises(DomainError, match="forbidden"):
        old.start()
    assert runtime.health["telegram"] == "connected" and not launched
    # Native setup has not yet marked the current entry loaded.
    entry.state = "setup_in_progress"
    replacement.start()
    assert "telegram" not in runtime.health and len(launched) == 5
    assert not engine.snapshot()["telegram"].get("observations")
    entry.state = manager_module.ConfigEntryState.LOADED
    runtime.health["telegram"] = "connected"  # a successful new poll

    async def failed_menu(_method, _payload):
        return False

    client.call = failed_menu
    await replacement._install_menu()
    assert runtime.health["telegram_menu"] == "telegram_bad_response"
    assert runtime.health["telegram"] == "connected"
