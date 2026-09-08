"""Contract tests for exact EN/RU/UK spoken review phrases and proposal lifecycle."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.family_assistant.assistant.chat_service import ChatService
from custom_components.family_assistant.assistant.language import COPY as ASSISTANT_COPY
from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.proposal_reply import parse_reply
from custom_components.family_assistant.telegram.router import route


def _hash(*values: str) -> str:
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


async def enable_conversation(engine, now) -> None:
    settings = engine.snapshot()["settings"]
    if "conversation" not in settings["modules"]:
        await engine.execute(
            "owner",
            "settings.save",
            {**settings, "modules": [*settings["modules"], "conversation"]},
            "enable-conversation-module",
            now,
        )


async def set_member_language(engine, now, actor: str, language: str) -> None:
    member = engine.snapshot()["members"][actor]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": actor,
            "revision": member["revision"],
            "name": member["name"],
            "role": member["role"],
            "language": language,
        },
        f"set-lang-{actor}-{language}",
        now,
    )


def scope(engine, actor: str = "parent"):
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
    service: ChatService,
    runtime: Any,
    engine: Any,
    now: Any,
    content: str,
    operation: str,
    actor: str = "parent",
    session: str = "session",
    on_commit: Any = None,
) -> str:
    revision, guard, check = scope(engine, actor=actor)
    return await service.answer(
        runtime=runtime,
        actor=actor,
        actor_revision=revision,
        content=content,
        operation_id=operation,
        session_id=session,
        now=now,
        guard=guard,
        scope_check=check,
        on_commit=on_commit,
    )


class StaticProvider:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def generate(self, _messages, _schema):
        self.calls += 1
        return self.value


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


@pytest.mark.parametrize(
    ("phrase", "expected_action"),
    [
        ("confirm the proposal", "confirm"),
        ("cancel the proposal", "reject"),
        ("подтверждаю предложение", "confirm"),
        ("отмени предложение", "reject"),
        ("підтверджую пропозицію", "confirm"),
        ("скасуй пропозицію", "reject"),
    ],
)
def test_exact_phrases_and_normalization_in_proposal_reply(phrase, expected_action):
    valid_proposal_id = "P" + "f" * 20
    assert parse_reply(phrase, [valid_proposal_id]) == (
        f"conversation.{expected_action}",
        {"id": valid_proposal_id},
    )

    # Whitespace, punctuation and casing normalization
    noisy_phrase = f"  {phrase.upper()} .?!  "
    assert parse_reply(noisy_phrase, [valid_proposal_id]) == (
        f"conversation.{expected_action}",
        {"id": valid_proposal_id},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase",
    [
        "confirm the proposal",
        "cancel the proposal",
        "подтверждаю предложение",
        "отмени предложение",
        "підтверджую пропозицію",
        "скасуй пропозицію",
    ],
)
@pytest.mark.parametrize(
    "invalid_refs",
    [
        (),
        [],
        ("P" + "1" * 20, "P" + "2" * 20),
        ("S000001",),
        ("P" + "1" * 20, "S000001"),
        ("invalid-id",),
        ("P12345",),
        (12345,),
    ],
    ids=[
        "empty-tuple",
        "empty-list",
        "multiple-proposals",
        "shopping-ref-only",
        "mixed-proposal-and-shopping",
        "invalid-id",
        "short-proposal-id",
        "non-string-ref",
    ],
)
async def test_no_refs_and_mixed_refs_fail_context_required_with_zero_fallback(
    engine, now, phrase, invalid_refs
):
    await enable_conversation(engine, now)
    fallback_calls = 0

    async def fallback_spy(*_args, **_kwargs):
        nonlocal fallback_calls
        fallback_calls += 1
        return "fallback_called"

    with pytest.raises(DomainError) as caught:
        await route(
            engine,
            "parent",
            phrase,
            "op-check-refs",
            now,
            refs=invalid_refs,
            fallback=fallback_spy,
        )

    assert caught.value.code == "context_required"
    assert fallback_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "generic_phrase",
    [
        "yes",
        "yep",
        "yeah",
        "sure",
        "ok",
        "да",
        "ага",
        "конечно",
        "подтверждаю",
        "так",
        "звісно",
        "підтверджую",
        "no",
        "nope",
        "cancel",
        "reject",
        "нет",
        "не надо",
        "отмена",
        "ні",
        "не треба",
        "скасувати",
    ],
)
async def test_generic_yes_and_negation_not_parsed_as_proposal_reply(engine, now, generic_phrase):
    await enable_conversation(engine, now)
    valid_proposal_id = "P" + "a" * 20

    # 1. parse_reply returns None for generic yes/no even with valid proposal ref
    assert parse_reply(generic_phrase, [valid_proposal_id]) is None

    # 2. route falls through to fallback / generic handling rather than executing confirm/reject
    fallback_calls = 0

    async def fallback_spy(*_args, **_kwargs):
        nonlocal fallback_calls
        fallback_calls += 1
        return "fallback_handled"

    reply = await route(
        engine,
        "parent",
        generic_phrase,
        f"op-generic-{hashlib.sha256(generic_phrase.encode()).hexdigest()[:8]}",
        now,
        refs=(valid_proposal_id,),
        fallback=fallback_spy,
    )
    assert fallback_calls == 1
    assert reply == "fallback_handled"
    assert not engine.snapshot().get("proposals")


@pytest.mark.asyncio
async def test_actor_bound_proposal_gets_saved_into_chat_refs_after_model_plan(engine, now):
    await enable_conversation(engine, now)
    provider = StaticProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Test Milk"}}],
        }
    )
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    session_id = "parent-planning-session"
    operation_id = "chat-create-proposal"

    reply = await ask(
        service,
        runtime,
        engine,
        now,
        "Please add Test Milk",
        operation_id,
        actor="parent",
        session=session_id,
    )

    proposal_id = "P" + hashlib.sha256(operation_id.encode()).hexdigest()[:20]
    assert proposal_id in reply
    proposals = engine.snapshot()["proposals"]
    assert proposal_id in proposals
    proposal = proposals[proposal_id]
    assert proposal["actor"] == "parent"
    assert proposal["actor_revision"] == 1
    assert proposal["status"] == "pending"

    # Verify session has the actor-bound proposal ref
    parent_session_hash = _hash("parent", "1", session_id)
    sessions = engine.snapshot()["memory"]["dashboard_chat"]["sessions"]
    assert sessions[parent_session_hash]["refs"] == [proposal_id]
    assert sessions[parent_session_hash]["actor"] == "parent"

    # Another actor (e.g. child) has an isolated session without parent's proposal
    child_session_hash = _hash("child", "1", session_id)
    assert child_session_hash not in sessions
    await service.async_stop()


@pytest.mark.asyncio
async def test_new_inflight_turn_hides_older_proposal_from_concurrent_confirmation(engine, now):
    await enable_conversation(engine, now)
    provider = StaticProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "First milk"}}],
        }
    )
    runtime = SimpleNamespace(engine=engine, assistant=Assistant(engine, Cascade([provider], {})))
    service = ChatService()
    await ask(service, runtime, engine, now, "Please add First milk", "first-preview")
    blocked = BlockingProvider({"kind": "answer", "text": "A later answer"})
    runtime.assistant = Assistant(engine, Cascade([blocked], {}))
    running = asyncio.create_task(ask(service, runtime, engine, now, "A new question", "new-turn"))
    await blocked.started.wait()
    try:
        with pytest.raises(DomainError, match="context_required"):
            await ask(service, runtime, engine, now, "confirm the proposal", "parallel-confirm")
        assert not engine.snapshot()["shopping"]
    finally:
        blocked.release.set()
        await running
        await service.async_stop()


@pytest.mark.asyncio
async def test_failed_new_turn_does_not_leave_old_spoken_confirmation_target(engine, now):
    await enable_conversation(engine, now)
    provider = StaticProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Old milk"}}],
        }
    )
    runtime = SimpleNamespace(engine=engine, assistant=Assistant(engine, Cascade([provider], {})))
    service = ChatService()
    await ask(service, runtime, engine, now, "Please add Old milk", "old-preview")
    runtime.assistant = None
    with pytest.raises(DomainError, match="provider_not_configured"):
        await ask(service, runtime, engine, now, "A different question", "failed-new-turn")
    with pytest.raises(DomainError, match="context_required"):
        await ask(service, runtime, engine, now, "confirm the proposal", "after-failure-confirm")
    assert not engine.snapshot()["shopping"]
    await service.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "confirm_phrase", "action"),
    [
        ("en", "confirm the proposal", "confirm"),
        ("ru", "подтверждаю предложение", "confirm"),
        ("uk", "підтверджую пропозицію", "confirm"),
        ("en", "cancel the proposal", "reject"),
        ("ru", "отмени предложение", "reject"),
        ("uk", "скасуй пропозицію", "reject"),
    ],
)
async def test_same_session_explicit_phrase_applies_once_and_reload_retry_returns_exact_receipt(
    engine, now, language, confirm_phrase, action
):
    await enable_conversation(engine, now)
    await set_member_language(engine, now, "parent", language)

    item_name = f"Item {language} {action}"
    provider = StaticProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": item_name}}],
        }
    )
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    session_id = f"session-lifecycle-{language}-{action}"
    op_plan = f"plan-{language}-{action}"
    op_review = f"review-{language}-{action}"

    # Step 1: Model generates proposal plan
    plan_reply = await ask(
        service,
        runtime,
        engine,
        now,
        f"Add {item_name}",
        op_plan,
        session=session_id,
    )
    proposal_id = "P" + hashlib.sha256(op_plan.encode()).hexdigest()[:20]
    assert proposal_id in plan_reply

    # Step 2: In the same session, send exact review phrase
    receipt = await ask(
        service,
        runtime,
        engine,
        now,
        confirm_phrase,
        op_review,
        session=session_id,
    )

    expected_key = "confirmed" if action == "confirm" else "rejected"
    assert ASSISTANT_COPY[language][expected_key].split("\n")[0] in receipt

    proposal = engine.snapshot()["proposals"][proposal_id]
    if action == "confirm":
        assert proposal["status"] == "applied"
        assert any(row["name"] == item_name for row in engine.snapshot()["shopping"].values())
    else:
        assert proposal["status"] == "rejected"
        assert not any(row["name"] == item_name for row in engine.snapshot()["shopping"].values())

    # Step 3: In-memory retry on the same service returns exact receipt
    assert (
        await ask(
            service,
            runtime,
            engine,
            now,
            confirm_phrase,
            op_review,
            session=session_id,
        )
        == receipt
    )

    # Step 4: Reload service from durable state and retry
    await service.async_stop()
    reloaded = ChatService()
    reloaded_receipt = await ask(
        reloaded,
        runtime,
        engine,
        now,
        confirm_phrase,
        op_review,
        session=session_id,
    )
    assert reloaded_receipt == receipt

    # Shopping mutations remain applied once, no duplicate items
    if action == "confirm":
        matching = [
            row for row in engine.snapshot()["shopping"].values() if row["name"] == item_name
        ]
        assert len(matching) == 1

    # Step 5: A subsequent separate operation in the session cannot re-apply the proposal
    with pytest.raises(DomainError) as caught:
        await ask(
            reloaded,
            runtime,
            engine,
            now,
            confirm_phrase,
            f"new-operation-{language}-{action}",
            session=session_id,
        )
    # The proposal status is no longer 'pending' and/or refs were updated with completion receipt
    assert caught.value.code in {"context_required", "proposal_expired"}
    await reloaded.async_stop()


@pytest.mark.asyncio
async def test_another_session_or_actor_cannot_confirm(engine, now):
    await enable_conversation(engine, now)
    provider = StaticProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Private Milk"}}],
        }
    )
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    session_a = "parent-session-A"
    session_b = "parent-session-B"
    op_plan = "plan-actor-test"

    # Parent creates proposal in session A
    await ask(
        service,
        runtime,
        engine,
        now,
        "Add Private Milk",
        op_plan,
        actor="parent",
        session=session_a,
    )
    proposal_id = "P" + hashlib.sha256(op_plan.encode()).hexdigest()[:20]
    assert engine.snapshot()["proposals"][proposal_id]["status"] == "pending"

    # Case 1: Same actor in a DIFFERENT session cannot confirm
    with pytest.raises(DomainError) as caught_session:
        await ask(
            service,
            runtime,
            engine,
            now,
            "confirm the proposal",
            "confirm-session-b",
            actor="parent",
            session=session_b,
        )
    assert caught_session.value.code == "context_required"
    assert engine.snapshot()["proposals"][proposal_id]["status"] == "pending"

    # Case 2: Another actor (child) in the same session ID cannot confirm
    with pytest.raises(DomainError) as caught_child:
        await ask(
            service,
            runtime,
            engine,
            now,
            "confirm the proposal",
            "confirm-child",
            actor="child",
            session=session_a,
        )
    assert caught_child.value.code == "context_required"
    assert engine.snapshot()["proposals"][proposal_id]["status"] == "pending"

    # Case 3: Another actor cannot confirm even with direct proposal ref
    with pytest.raises(DomainError) as caught_direct:
        await engine.execute(
            "child",
            "conversation.confirm",
            {"id": proposal_id},
            "child-direct-confirm",
            now,
        )
    assert caught_direct.value.code == "forbidden"
    assert engine.snapshot()["proposals"][proposal_id]["status"] == "pending"
    await service.async_stop()


@pytest.mark.asyncio
async def test_spoken_confirmation_denied_on_expiry(engine, now):
    await enable_conversation(engine, now)
    provider = StaticProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Expiring Milk"}}],
        }
    )
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([provider], {})),
    )
    service = ChatService()
    session_id = "expiry-session"
    op_plan = "plan-expiring"

    await ask(
        service,
        runtime,
        engine,
        now,
        "Add Expiring Milk",
        op_plan,
        session=session_id,
    )
    proposal_id = "P" + hashlib.sha256(op_plan.encode()).hexdigest()[:20]
    assert engine.snapshot()["proposals"][proposal_id]["status"] == "pending"

    # Case 1: Proposal expiry (5 minutes limit exceeded)
    now_expired = now + timedelta(minutes=5, seconds=1)
    with pytest.raises(DomainError) as caught_proposal_expired:
        await ask(
            service,
            runtime,
            engine,
            now_expired,
            "confirm the proposal",
            "confirm-expired-proposal",
            session=session_id,
        )
    assert caught_proposal_expired.value.code == "proposal_expired"
    assert engine.snapshot()["proposals"][proposal_id]["status"] == "pending"
    assert not engine.snapshot()["shopping"]

    # Case 2: Chat context TTL expiry (15 minutes after last session activity)
    now_context_expired = now_expired + timedelta(minutes=16)
    with pytest.raises(DomainError) as caught_ctx:
        await ask(
            service,
            runtime,
            engine,
            now_context_expired,
            "confirm the proposal",
            "confirm-expired-ctx",
            session=session_id,
        )
    assert caught_ctx.value.code == "context_required"

    # Case 3: Retrying the operation itself after operation context TTL (15 minutes)
    with pytest.raises(DomainError) as caught_op_expired:
        await ask(
            service,
            runtime,
            engine,
            now_expired + timedelta(minutes=16),
            "confirm the proposal",
            "confirm-expired-proposal",
            session=session_id,
        )
    assert caught_op_expired.value.code == "chat_context_expired"

    await service.async_stop()


@pytest.mark.asyncio
async def test_intervening_answer_clears_old_refs(engine, now):
    await enable_conversation(engine, now)
    responses = [
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Intervened Milk"}}],
        },
        {
            "kind": "answer",
            "text": "The capital of France is Paris.",
        },
    ]

    class SequentialProvider:
        def __init__(self, items):
            self.items = list(items)

        async def generate(self, _messages, _schema):
            return self.items.pop(0)

    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([SequentialProvider(responses)], {})),
    )
    service = ChatService()
    session_id = "intervene-session"

    # 1. Create model proposal
    await ask(
        service,
        runtime,
        engine,
        now,
        "Add Intervened Milk",
        "op-proposal-step",
        session=session_id,
    )
    session_hash = _hash("parent", "1", session_id)
    sessions = engine.snapshot()["memory"]["dashboard_chat"]["sessions"]
    proposal_id = "P" + hashlib.sha256(b"op-proposal-step").hexdigest()[:20]
    assert sessions[session_hash]["refs"] == [proposal_id]

    # 2. Intervening answer
    answer_reply = await ask(
        service,
        runtime,
        engine,
        now,
        "What is the capital of France?",
        "op-intervening-question",
        session=session_id,
    )
    assert "Paris" in answer_reply

    # The intervening answer cleared session refs
    sessions_after = engine.snapshot()["memory"]["dashboard_chat"]["sessions"]
    assert sessions_after[session_hash]["refs"] == []

    # 3. Spoken confirm fails because refs were cleared
    with pytest.raises(DomainError) as caught:
        await ask(
            service,
            runtime,
            engine,
            now,
            "confirm the proposal",
            "op-spoken-after-intervene",
            session=session_id,
        )
    assert caught.value.code == "context_required"
    assert engine.snapshot()["proposals"][proposal_id]["status"] == "pending"
    assert not engine.snapshot()["shopping"]
    await service.async_stop()


@pytest.mark.asyncio
async def test_concurrent_earlier_slow_proposal_must_not_overwrite_later_session_operation_context(
    engine, now
):
    await enable_conversation(engine, now)
    slow_provider = BlockingProvider(
        {
            "kind": "commands",
            "commands": [{"action": "shopping.add", "payload": {"name": "Slow Milk"}}],
        }
    )
    runtime = SimpleNamespace(
        engine=engine,
        assistant=Assistant(engine, Cascade([slow_provider], {})),
    )
    service = ChatService()
    session_id = "concurrent-session"
    op_slow = "op-slow-proposal"
    op_later = "op-later-command"

    # Step 1: Start slow proposal request
    slow_task = asyncio.create_task(
        ask(
            service,
            runtime,
            engine,
            now,
            "Please add Slow Milk",
            op_slow,
            session=session_id,
        )
    )
    await slow_provider.started.wait()

    # A later deterministic request in the same session wins the context slot.
    later_reply = await ask(
        service,
        runtime,
        engine,
        now,
        "/buy Quick Bread",
        op_later,
        session=session_id,
    )
    assert "Quick Bread" in later_reply

    session_hash = _hash("parent", "1", session_id)
    sessions = engine.snapshot()["memory"]["dashboard_chat"]["sessions"]
    later_op_key = _hash("parent", "1", op_later)
    assert sessions[session_hash]["latest_operation"] == later_op_key
    bread_ref = next(iter(engine.snapshot()["shopping"]))
    assert sessions[session_hash]["refs"] == [bread_ref]

    # Step 3: Release the earlier slow proposal
    slow_provider.release.set()
    await slow_task

    # The earlier slow proposal must NOT overwrite the later session operation context
    sessions_post = engine.snapshot()["memory"]["dashboard_chat"]["sessions"]
    assert sessions_post[session_hash]["latest_operation"] == later_op_key
    assert sessions_post[session_hash]["refs"] == [bread_ref]

    # Confirmation receives bread_ref, not the earlier proposal, and fails closed.
    with pytest.raises(DomainError) as caught:
        await ask(
            service,
            runtime,
            engine,
            now,
            "confirm the proposal",
            "op-attempt-confirm",
            session=session_id,
        )
    assert caught.value.code == "context_required"

    # Slow milk was never confirmed or applied to the shopping list
    assert not any(row["name"] == "Slow Milk" for row in engine.snapshot()["shopping"].values())
    await service.async_stop()
