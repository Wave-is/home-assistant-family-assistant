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
