"""Own-bot isolation, enrollment approval and HTTP fault classification."""

import json
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram.client import TelegramClient
from custom_components.family_assistant.telegram.enrollment import Enrollment
from custom_components.family_assistant.telegram.router import addressed, route


def message(code, now, *, group=False, **extra):
    return {
        "from": {"id": 1001, "first_name": "Synthetic child", "is_bot": False},
        "chat": {
            "id": -10001 if group else 1001,
            "type": "supergroup" if group else "private",
            "title": "Synthetic group",
        },
        "text": f"{'/family_setup' if group else '/start'} {code}",
        "date": int(now.timestamp()),
        **extra,
    }


@pytest.mark.asyncio
async def test_link_requires_owner_confirmation_and_restricts_other_groups(engine, now):
    enrollment = Enrollment(engine)
    invite = await enrollment.issue("owner", "member", now, "child")
    assert invite["code"] not in json.dumps(engine.snapshot())
    assert await enrollment.capture(message(invite["code"], now), "synthetic_bot", now)
    with pytest.raises(DomainError, match="forbidden"):
        engine.actor_for_telegram(1001, 1001, private=True)
    with pytest.raises(DomainError, match="forbidden"):
        await enrollment.confirm("child", invite["id"], now)
    await enrollment.confirm("owner", invite["id"], now)
    assert engine.actor_for_telegram(1001, 1001, private=True) == "child"
    with pytest.raises(DomainError, match="forbidden"):
        engine.actor_for_telegram(1001, -10001, private=False)
    group = await enrollment.issue("owner", "group", now)
    assert await enrollment.capture(message(group["code"], now, group=True), "synthetic_bot", now)
    await enrollment.confirm("owner", group["id"], now)
    assert engine.actor_for_telegram(1001, -10001, private=False) == "child"
    with pytest.raises(DomainError, match="forbidden"):
        engine.actor_for_telegram(1001, -10002, private=False)
    with pytest.raises(DomainError, match="forbidden"):
        engine.actor_for_telegram(1001, 1002, private=True)


@pytest.mark.asyncio
async def test_expired_reused_forwarded_and_wrong_kind_codes_rejected(engine, now):
    enrollment = Enrollment(engine)
    invite = await enrollment.issue("owner", "member", now, "child")
    assert not await enrollment.capture(
        message(invite["code"], now, group=True), "synthetic_bot", now
    )
    assert not await enrollment.capture(
        message(invite["code"], now, forward_origin={"type": "user"}), "synthetic_bot", now
    )
    assert not await enrollment.capture(
        message(invite["code"], now, sender_chat={"id": 1002}), "synthetic_bot", now
    )
    assert not await enrollment.capture(
        message(invite["code"], now - timedelta(minutes=1)), "synthetic_bot", now
    )
    assert not await enrollment.capture(
        message(invite["code"], now), "synthetic_bot", now + timedelta(minutes=15)
    )
    assert await enrollment.capture(message(invite["code"], now), "synthetic_bot", now)
    assert not await enrollment.capture(message(invite["code"], now), "synthetic_bot", now)
    await enrollment.confirm("owner", invite["id"], now)
    with pytest.raises(DomainError, match="telegram_enrollment_expired"):
        await enrollment.confirm("owner", invite["id"], now)


@pytest.mark.asyncio
async def test_member_identity_cannot_be_shared_and_enrollment_is_private(engine, now):
    enrollment = Enrollment(engine)
    for target in ("child", "sibling"):
        invite = await enrollment.issue("owner", "member", now, target)
        await enrollment.capture(message(invite["code"], now), "synthetic_bot", now)
        if target == "child":
            await enrollment.confirm("owner", invite["id"], now)
        else:
            with pytest.raises(DomainError, match="duplicate_identity"):
                await enrollment.confirm("owner", invite["id"], now)
    public = json.dumps(engine.view("parent"))
    assert "telegram_id" not in public and "digest" not in public
    with pytest.raises(DomainError, match="forbidden"):
        enrollment.status("parent", invite["id"])


class Response:
    def __init__(self, status, body):
        self.status, self.body = status, body
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def iter_chunked(self, _size):
        raw = json.dumps(self.body).encode() if not isinstance(self.body, bytes) else self.body
        for index in range(0, len(raw), 7):
            yield raw[index : index + 7]


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def client(session):
    return TelegramClient(session, "1" * 8 + ":" + "x" * 35)


@pytest.mark.asyncio
async def test_webhook_conflict_is_read_only_and_token_repr_is_redacted():
    session = Session(
        Response(200, {"ok": True, "result": {"id": 1001, "username": "synthetic_bot"}}),
        Response(200, {"ok": True, "result": {"url": "https://example.invalid/hook"}}),
    )
    bot = client(session)
    with pytest.raises(DeliveryError, match="telegram_webhook_conflict"):
        await bot.inspect()
    assert "xxxxx" not in repr(bot)
    assert len(session.calls) == 2
    assert all(call["allow_redirects"] is False for call in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,key,uncertain,retryable",
    [
        (401, {"error_code": 401}, "telegram_invalid_token", False, False),
        (409, {"error_code": 409}, "telegram_polling_conflict", False, False),
        (
            429,
            {"error_code": 429, "parameters": {"retry_after": 2}},
            "telegram_rate_limited",
            False,
            True,
        ),
        (403, {"error_code": 403}, "telegram_chat_blocked", False, False),
        (500, {"error_code": 500}, "telegram_api_error", True, False),
        (200, b"bad json", "telegram_bad_response", True, False),
        (200, {"ok": True}, "telegram_bad_response", True, False),
        (302, {}, "telegram_bad_response", True, False),
    ],
)
async def test_send_errors_are_classified_without_token_or_provider_body(
    status, body, key, uncertain, retryable
):
    bot = client(Session(Response(status, body)))
    with pytest.raises(DeliveryError) as failure:
        await bot.call("sendMessage", {"text": "Synthetic", "chat_id": 1001})
    assert failure.value.code == key
    assert failure.value.uncertain == uncertain
    assert failure.value.retryable == retryable
    assert "xxxxx" not in str(failure.value)


@pytest.mark.asyncio
async def test_chunked_read_and_update_filter():
    session = Session(Response(200, {"ok": True, "result": []}))
    assert await client(session).updates(42) == []
    assert session.calls[0]["json"]["offset"] == 42
    assert session.calls[0]["json"]["allowed_updates"] == [
        "message",
        "callback_query",
        "my_chat_member",
    ]


@pytest.mark.parametrize(
    "content,expected",
    [
        ("@synthetic_bot тут?", "тут?"),
        ("/ping@synthetic_bot", "/ping"),
        ("@SYNTHETIC_BOT жив?", "жив?"),
        ("/ping@some_other_bot", None),
        ("plain group conversation", None),
        ("someone@synthetic_bot.example", None),
    ],
)
def test_addressed_mentions_and_commands(content, expected):
    envelope = {"text": content, "from": {"id": 1001}, "chat": {"type": "supergroup"}}
    assert addressed(envelope, {"id": 1000, "username": "synthetic_bot"}) == expected


@pytest.mark.asyncio
async def test_alive_never_needs_llm_and_commands_keep_authority(engine, now):
    assert "here" in await route(engine, "parent", "тут?", "ping", now)
    await route(engine, "parent", "/task Child | Pack bag", "new-task", now)
    await route(engine, "parent", "/task Child | Pack bag", "new-task", now)
    assert len(engine.snapshot()["tasks"]) == 1
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/approve T000001", "approve", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "assigned"


@pytest.mark.asyncio
async def test_expanded_liveness(engine, now):
    for phrase in ["ты тут?", "ти тут", "на связи", "жив", "пинг", "ns nen"]:
        res = await route(engine, "parent", phrase, f"op-{phrase}", now)
        assert "here" in res.lower(), f"Failed for {phrase}: {res}"


@pytest.mark.asyncio
async def test_expanded_read_and_aliases(engine, now):
    for phrase in [
        "/дела",
        "/задачи",
        "/покупки",
        "/будильники",
        "какие задачи",
        "список покупок",
        "що купити",
        "за что минусы",
        "статистика",
        "будильники",
        "cnfnec pflfx",
        "задааачи",
        "покууупки",
    ]:
        res = await route(engine, "parent", phrase, f"op-{phrase}", now)
        assert res is not None and len(res) > 0, f"Failed for {phrase}"


@pytest.mark.asyncio
async def test_expanded_actions(engine, now):
    # 1. Natural shopping add
    res_buy = await route(engine, "parent", "купить молоко", "buy-milk", now)
    assert "S000001" in res_buy
    assert engine.snapshot()["shopping"]["S000001"]["name"] == "молоко"

    # 2. Natural shopping purchase
    res_bought = await route(engine, "parent", "купил S000001", "bought-milk", now)
    assert "S000001" in res_bought
    assert engine.snapshot()["shopping"]["S000001"]["status"] == "purchased"

    # 3. Natural task create
    res_task = await route(engine, "parent", "задача для Child: Clean room", "task-clean", now)
    assert "T000001" in res_task
    assert engine.snapshot()["tasks"]["T000001"]["title"] == "Clean room"

    # 4. Natural task complete by parent
    res_done = await route(engine, "parent", "T000001 готово", "done-clean", now)
    assert "T000001" in res_done
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "completed"


def test_addressed_photo_handling():
    bot = {"id": 12345, "username": "family_bot"}

    # 1. Photo in private chat with no caption -> default prompt
    msg_private_photo = {
        "chat": {"type": "private"},
        "photo": [{"file_id": "p1", "file_size": 100}],
    }
    assert addressed(msg_private_photo, bot) == "Опиши, что изображено на фото."

    # 2. Photo in group with mention in caption -> stripped mention
    msg_group_caption = {
        "chat": {"type": "supergroup"},
        "caption": "@family_bot что на этом фото?",
        "photo": [{"file_id": "p1", "file_size": 100}],
    }
    assert addressed(msg_group_caption, bot) == "что на этом фото?"

    # 3. Reply to photo in group with mention
    msg_group_reply_photo = {
        "chat": {"type": "supergroup"},
        "text": "@family_bot опиши картинку",
        "reply_to_message": {
            "photo": [{"file_id": "p_old", "file_size": 200}],
        },
    }
    assert addressed(msg_group_reply_photo, bot) == "опиши картинку"

    # 4. Photo in group without mention or reply -> ignored for privacy
    msg_group_unaddressed = {
        "chat": {"type": "supergroup"},
        "caption": "просто фото",
        "photo": [{"file_id": "p1", "file_size": 100}],
    }
    assert addressed(msg_group_unaddressed, bot) is None

    # 5. Reply to bot with a photo (no caption) -> default prompt
    msg_reply_to_bot = {
        "chat": {"type": "supergroup"},
        "photo": [{"file_id": "p1", "file_size": 100}],
        "reply_to_message": {"from": {"id": 12345}},
    }
    assert addressed(msg_reply_to_bot, bot) == "Опиши, что изображено на фото."


@pytest.mark.asyncio
async def test_client_download_file():
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.telegram.client import TelegramClient

    session = MagicMock()
    client = TelegramClient(session, "1" * 8 + ":" + "x" * 35)

    # Mock getFile
    client.call = AsyncMock(return_value={"file_path": "photos/test.jpg", "file_size": 1024})

    # Mock response
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.content.iter_chunked = MagicMock(return_value=_async_iter([b"fake_image_bytes"]))
    session.get.return_value.__aenter__.return_value = mock_resp

    data = await client.download_file("file_id_123")
    assert data == b"fake_image_bytes"

    # Oversized file check
    client.call = AsyncMock(return_value={"file_path": "photos/big.jpg", "file_size": 7_000_000})
    with pytest.raises(DomainError):
        await client.download_file("file_id_big")


async def _async_iter(items):
    for item in items:
        yield item


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["купить молоко | несколько", "buy milk | 2 | l | extra"])
async def test_natural_shopping_never_silently_changes_bad_fields(engine, now, content):
    with pytest.raises(DomainError, match="invalid_field"):
        await route(engine, "parent", content, "bad-shopping", now)
    assert not engine.snapshot()["shopping"]


def test_declined_member_names_keep_ambiguity(engine):
    from custom_components.family_assistant.telegram.intents import find_member

    state = engine.snapshot()
    state["members"]["child"]["name"] = "Саша"
    state["members"]["sibling"]["name"] = "Саше"
    assert find_member(state, "Саша") == "child"
    with pytest.raises(DomainError, match="ambiguous_member"):
        find_member(state, "Сашу")


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/старт", "/хелп", "/помощь", "/допомога"])
async def test_help_aliases_return_actual_help(engine, now, command):
    assert "/buy" in await route(engine, "parent", command, command, now)


@pytest.mark.asyncio
async def test_ukrainian_tasks_alias_remains_read_command(engine, now):
    assert await route(engine, "parent", "/завдання", "uk-tasks", now) == "No records yet."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "../file.jpg",
        "https://example.org/image",
        "/abs.jpg",
        "photos/test.jpg?token=x",
        "photos//test.jpg",
    ],
)
async def test_download_rejects_untrusted_file_paths(path):
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.family_assistant.notifications import DeliveryError
    from custom_components.family_assistant.telegram.client import TelegramClient

    session = MagicMock()
    client = TelegramClient(session, "1" * 8 + ":" + "x" * 35)
    client.call = AsyncMock(return_value={"file_path": path})
    with pytest.raises(DeliveryError):
        await client.download_file("synthetic-photo")
    session.get.assert_not_called()
