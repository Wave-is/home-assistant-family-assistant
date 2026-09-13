"""Actual Telegram manager admission and bounded multipart image transport."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.assistant.image_files import ImageFiles
from custom_components.family_assistant.assistant.image_jobs import ImageJobs
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram import image_generation
from tests.test_image_generation import Session as ImageSession
from tests.test_image_generation import configuration, decode, png
from tests.test_telegram import Response, Session, client
from tests.test_telegram_command_scope import NOW, fixture, update
from tests.test_telegram_command_scope import manager_module as manager_module  # noqa: F401


def configured(module, tmp_path):
    engine, store, entry, runtime, manager, telegram = fixture(module)
    config, session = configuration("agy_gateway", "comfyui"), ImageSession()
    entry.options["image_generation"] = deepcopy(config)

    def scope():
        manager._manager_guard()
        if entry.options.get("image_generation") != config:
            raise DomainError("forbidden")

    jobs = ImageJobs(
        engine,
        session,
        ImageFiles(tmp_path / "images", decoder=decode),
        config,
        clock=lambda: NOW,
        scope_check=scope,
        scope_id=entry.entry_id,
    )
    runtime.image_generation = jobs
    return engine, store, entry, runtime, manager, telegram, session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content", ["/draw a blue robot", "нарисуй синего робота", "намалюй синього робота"]
)
async def test_manager_queues_explicit_draw_without_text_inference(
    manager_module, tmp_path, content
):  # noqa: F811
    engine, _store, _entry, runtime, manager, _telegram, session = configured(
        manager_module, tmp_path
    )
    assert runtime.assistant is None
    incoming = update(text=content)
    await manager.process(incoming)
    await manager.process(incoming)
    jobs = engine.snapshot()["image_jobs"]
    assert len(jobs) == 1
    row = next(iter(jobs.values()))
    assert row["chat_id"] == 101 and row["actor"] == "owner"
    assert row["status"] == "queued"
    assert not engine.snapshot()["assistant_jobs"]
    assert not session.calls
    messages = [event["data"]["text"] for event in engine.snapshot()["outbox"].values()]
    assert len(messages) == 1 and row["id"] in messages[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["group", "forwarded", "unbound", "disabled"])
async def test_manager_rejects_nonprivate_untrusted_or_disabled_draw(
    manager_module, tmp_path, mode
):  # noqa: F811
    engine, _store, _entry, runtime, manager, _telegram, session = configured(
        manager_module, tmp_path
    )
    incoming = update(text="/draw blue robot", group=mode == "group")
    if mode == "forwarded":
        incoming["message"]["forward_origin"] = {"type": "user"}
    if mode == "unbound":
        incoming["message"]["from"]["id"] = incoming["message"]["chat"]["id"] = 777
    if mode == "disabled":
        runtime.image_generation = None
    await manager.process(incoming)
    assert not engine.snapshot().get("image_jobs")
    assert not engine.snapshot()["assistant_jobs"]
    assert not session.calls


@pytest.mark.asyncio
async def test_manager_private_history_and_delivered_bytes(manager_module, tmp_path, monkeypatch):  # noqa: F811
    engine, _store, _entry, runtime, manager, telegram, _session = configured(
        manager_module, tmp_path
    )
    await manager.process(update(text="/draw a robot"))
    sent = []

    # Stop after one service step, not from inside the active transport guard.
    async def one_pause(_seconds):
        manager._stopped = True

    async def send_without_stop(chat_id, data, mime, caption):
        sent.append((chat_id, data, mime, caption))
        return "123"

    telegram.send_photo = send_without_stop
    monkeypatch.setattr(image_generation.asyncio, "sleep", one_pause)
    await image_generation.run(manager)
    assert len(sent) == 1 and sent[0][:3] == (101, png(), "image/png")
    assert next(iter(engine.snapshot()["image_jobs"].values()))["status"] == "complete"
    manager._stopped = False
    await manager.process(update(11, text="/images"))
    result = [event["data"]["text"] for event in engine.snapshot()["outbox"].values()][-1]
    assert "sent" in result and "a robot" not in result
    assert runtime.image_generation is not None


@pytest.mark.asyncio
async def test_real_client_uploads_bytes_as_multipart_never_url():
    session = Session(Response(200, {"ok": True, "result": {"message_id": 123}}))
    assert await client(session).send_photo(101, png(), "image/png", "Synthetic result") == "123"
    call = session.calls[0]
    assert "json" not in call
    fields = {field[0]["name"]: field[2] for field in call["data"]._fields}
    assert fields == {
        "chat_id": "101",
        "caption": "Synthetic result",
        "protect_content": "true",
        "photo": png(),
    }
    assert "parse_mode" not in fields


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,uncertain",
    [
        (429, {"error_code": 429}, False),
        (500, {"error_code": 500}, True),
        (200, {"ok": True, "result": {}}, True),
        (302, {}, True),
    ],
)
async def test_binary_send_faults_keep_existing_uncertainty_contract(status, body, uncertain):
    with pytest.raises(DeliveryError) as error:
        await client(Session(Response(status, body))).send_photo(
            101, png(), "image/png", "Synthetic"
        )
    assert error.value.uncertain is uncertain


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chat,content,mime",
    [
        (-101, png(), "image/png"),
        (101, "https://example.invalid/image", "image/png"),
        (True, png(), "image/png"),
        (101, b"", "image/png"),
        (101, png(), "image/svg+xml"),
    ],
    ids=["group", "url", "bool", "empty", "svg"],
)
async def test_binary_send_never_accepts_group_url_or_unsupported_media(chat, content, mime):
    session = Session()
    with pytest.raises(DomainError):
        await client(session).send_photo(chat, content, mime, "Synthetic")
    assert not session.calls


@pytest.mark.asyncio
async def test_replaced_image_options_cannot_crash_shared_outbox(manager_module, tmp_path):  # noqa: F811
    _engine, _store, entry, runtime, manager, telegram, _session = configured(
        manager_module, tmp_path
    )
    event = {
        "data": {
            "image_job_id": "synthetic-id",
            "image_provider_scope": runtime.image_generation.marker,
        }
    }
    entry.options["image_generation"]["width"] = 768
    with pytest.raises(DeliveryError, match="image_unavailable") as result:
        await manager._send_notification(event, {"chat_id": 101})
    assert not result.value.retryable and not result.value.uncertain
    assert not telegram.calls
