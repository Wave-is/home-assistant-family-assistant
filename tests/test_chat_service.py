"""Dashboard chat owns work and freezes content-free command context."""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.family_assistant.assistant.chat_service import MAX_CONTEXTS, ChatService
from custom_components.family_assistant.assistant.language import COPY as ASSISTANT_COPY
from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.validation import DomainError


async def enable(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "chat-enable",
        now,
    )


def scope(engine, actor="parent"):
    revision = engine.snapshot()["members"][actor]["revision"]

    def guard(state):
        member = state["members"].get(actor, {})
        if (
            member.get("revision") != revision
            or member.get("active") is not True
            or "conversation" not in state["settings"]["modules"]
        ):
            raise DomainError("conflict")

    async def check():
        guard(engine.snapshot())

    return revision, guard, check


async def ask(
    service,
    runtime,
    engine,
    now,
    content,
    operation,
    session="session",
    on_commit=None,
):
    revision, guard, check = scope(engine)
    return await service.answer(
        runtime=runtime,
        actor="parent",
        actor_revision=revision,
        content=content,
        operation_id=operation,
        session_id=session,
        now=now,
        guard=guard,
        scope_check=check,
        on_commit=on_commit,
    )


@pytest.mark.asyncio
async def test_deterministic_retry_keeps_original_refs_across_service_reload(engine, now):
    await enable(engine, now)
    runtime = SimpleNamespace(engine=engine, assistant=None)
    service = ChatService()
    first = await ask(service, runtime, engine, now, "/buy Milk", "chat-buy-milk")
    await ask(service, runtime, engine, now, "/buy Bread", "chat-buy-bread")
    await service.async_stop()

    reloaded = ChatService()
    assert await ask(reloaded, runtime, engine, now, "/buy Milk", "chat-buy-milk") == first
    shopping = engine.snapshot()["shopping"]
    assert [row["name"] for row in shopping.values()] == ["Milk", "Bread"]
    context = engine.snapshot()["memory"]["dashboard_chat"]
    assert "Milk" not in json.dumps(context) and "Bread" not in json.dumps(context)
    expected = {
        "actor",
        "actor_revision",
        "session",
        "input_hash",
        "refs",
        "created_at",
        "expires_at",
    }
    assert all(set(row) == expected for row in context["operations"].values())


@pytest.mark.asyncio
async def test_expired_context_never_reinterprets_known_operation(engine, now):
    await enable(engine, now)
    runtime = SimpleNamespace(engine=engine, assistant=None)
    first = ChatService()
    await ask(first, runtime, engine, now, "/buy Milk", "chat-expired")
    await first.async_stop()
    with pytest.raises(DomainError, match="chat_context_expired"):
        await ask(
            ChatService(),
            runtime,
            engine,
            now + timedelta(minutes=16),
            "/buy Milk",
            "chat-expired",
        )
    assert len(engine.snapshot()["shopping"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("elapsed", [timedelta(minutes=16), timedelta(minutes=-1)])
async def test_stale_or_clock_rollback_session_refs_expire_before_new_operation(
    engine, now, elapsed
):
    await enable(engine, now)
    runtime = SimpleNamespace(engine=engine, assistant=None)
    service = ChatService()
    await ask(service, runtime, engine, now, "/buy Milk", "chat-old-session")
    old_context = engine.snapshot()["memory"]["dashboard_chat"]
    assert next(iter(old_context["sessions"].values()))["refs"]
    await ask(
        service,
        runtime,
        engine,
        now + elapsed,
        "/buy Bread",
        "chat-new-operation",
    )
    operations = engine.snapshot()["memory"]["dashboard_chat"]["operations"]
    new_row = next(
        value for value in operations.values() if value["created_at"] == (now + elapsed).isoformat()
    )
    assert new_row["refs"] == []


@pytest.mark.asyncio
async def test_durable_session_capacity_fails_closed(engine, now):
    await enable(engine, now)

    def fill(ctx):
        bucket = ctx.state["memory"].setdefault("dashboard_chat", {})
        bucket["operations"] = {}
        bucket["sessions"] = {
            f"session-{index}": {
                "actor": "parent",
                "actor_revision": 1,
                "refs": [],
                "updated_at": now.isoformat(),
            }
            for index in range(MAX_CONTEXTS)
        }

    await engine.system_update("fill_chat_sessions", now, fill)
    runtime = SimpleNamespace(engine=engine, assistant=None)
    with pytest.raises(DomainError, match="chat_context_full"):
        await ask(
            ChatService(),
            runtime,
            engine,
            now,
            "new contextual request",
            "chat-capacity",
        )


class BlockingProvider:
    def __init__(self, value):
        self.value = value
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.calls = 0

    async def generate(self, _messages, _schema):
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.value


@pytest.mark.asyncio
async def test_locked_guard_blocks_model_proposal_after_same_role_epoch_change(engine, now):
    await enable(engine, now)
    provider = BlockingProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Private milk"}}],
        }
    )
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    request = asyncio.create_task(
        ask(service, runtime, engine, now, "Please add Private milk", "chat-model")
    )
    await provider.started.wait()
    member = engine.snapshot()["members"]["parent"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": member["revision"],
            "name": "Renamed parent",
            "role": "parent",
            "language": "en",
        },
        "parent-new-epoch",
        now,
    )
    provider.release.set()
    with pytest.raises(DomainError, match="conflict"):
        await request
    assert not engine.snapshot()["proposals"]


@pytest.mark.asyncio
async def test_stop_cancels_owned_provider_work_and_returns_no_reply(engine, now):
    await enable(engine, now)
    provider = BlockingProvider({"kind": "answer", "text": "stale private answer"})
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    request = asyncio.create_task(ask(service, runtime, engine, now, "Question", "chat-stop"))
    await provider.started.wait()
    await service.async_stop()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert provider.cancelled is True


@pytest.mark.asyncio
async def test_response_loss_keeps_owned_model_work_and_transient_exact_reply(engine, now):
    await enable(engine, now)
    provider = BlockingProvider({"kind": "answer", "text": "bounded answer"})
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    lost = asyncio.create_task(ask(service, runtime, engine, now, "Question", "chat-lost"))
    await provider.started.wait()
    lost.cancel()
    with pytest.raises(asyncio.CancelledError):
        await lost
    provider.release.set()
    for _ in range(10):
        if not service._tasks:
            break
        await asyncio.sleep(0)
    reply = await ask(service, runtime, engine, now, "Question", "chat-lost")
    assert "bounded answer" in reply
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_response_loss_still_notifies_successful_owned_commits(engine, now):
    await enable(engine, now)
    provider = BlockingProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Detached milk"}}],
        }
    )
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    notifications = 0

    def updated():
        nonlocal notifications
        notifications += 1

    lost = asyncio.create_task(
        ask(
            service,
            runtime,
            engine,
            now,
            "Please add Detached milk",
            "chat-detached-commit",
            on_commit=updated,
        )
    )
    await provider.started.wait()
    lost.cancel()
    with pytest.raises(asyncio.CancelledError):
        await lost
    provider.release.set()
    for _ in range(30):
        if engine.snapshot()["proposals"]:
            break
        await asyncio.sleep(0)
    assert engine.snapshot()["proposals"]
    assert notifications >= 1


@pytest.mark.asyncio
async def test_guard_rechecks_before_even_content_free_context_write(engine, now):
    await enable(engine, now)
    runtime = SimpleNamespace(engine=engine, assistant=None)
    revision, _guard, check = scope(engine)

    def stale_guard(_state):
        raise DomainError("conflict")

    service = ChatService()
    with pytest.raises(DomainError, match="conflict"):
        await service.answer(
            runtime=runtime,
            actor="parent",
            actor_revision=revision,
            content="unknown request",
            operation_id="chat-stale",
            session_id="session",
            now=now,
            guard=stale_guard,
            scope_check=check,
        )
    assert "dashboard_chat" not in engine.snapshot()["memory"]


@pytest.mark.asyncio
async def test_service_admission_precedes_blocked_scope_checks(engine, now):
    await enable(engine, now)
    runtime = SimpleNamespace(engine=engine, assistant=None)
    service = ChatService()
    revision, guard, _check = scope(engine)
    started = 0
    both = asyncio.Event()
    release = asyncio.Event()

    async def blocked_check():
        nonlocal started
        started += 1
        if started == 2:
            both.set()
        await release.wait()

    async def call(operation):
        return await service.answer(
            runtime=runtime,
            actor="parent",
            actor_revision=revision,
            content="unknown request",
            operation_id=operation,
            session_id="session",
            now=now,
            guard=guard,
            scope_check=blocked_check,
        )

    first = asyncio.create_task(call("admission-one"))
    second = asyncio.create_task(call("admission-two"))
    await both.wait()
    with pytest.raises(DomainError, match="chat_busy"):
        await call("admission-three")
    assert started == 2
    first.cancel()
    second.cancel()
    release.set()
    await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.asyncio
async def test_ping_is_scoped_but_does_not_consume_durable_context(engine, now):
    await enable(engine, now)
    runtime = SimpleNamespace(engine=engine, assistant=None)
    assert "here" in (await ask(ChatService(), runtime, engine, now, "/ping", "chat-ping"))
    assert "dashboard_chat" not in engine.snapshot()["memory"]


@pytest.mark.asyncio
async def test_external_scope_callback_does_not_require_a_cascade_for_prepare(engine, now):
    await enable(engine, now)
    checks = 0

    async def check():
        nonlocal checks
        checks += 1

    assistant = Assistant(engine, None)
    reply = await assistant._propose(
        "parent",
        "Add scoped milk",
        "scope-without-cascade",
        "Pscopewithoutcascade",
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Scoped milk"}}],
        },
        engine.view("parent"),
        now,
        ASSISTANT_COPY["en"],
        scope_check=check,
    )
    assert "Pscopewithoutcascade" in reply
    assert checks >= 4
