"""Actual HA Telegram-loop liveness across a synthetic backup freeze."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime


async def _cancel(task) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _wait_for_event_or_failure(
    event, task, health, *, label: str, timeout: float = 15
) -> None:
    waiting = asyncio.create_task(event.wait())
    try:
        done, _pending = await asyncio.wait(
            {waiting, task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            await task
            raise AssertionError(f"{label}: loop stopped without an error")
        if waiting not in done:
            raise AssertionError(
                f"{label}: timed out; loop_done={task.done()}, "
                f"health_codes={sorted(str(code) for code in health.values())}"
            )
    finally:
        if not waiting.done():
            waiting.cancel()
        with suppress(asyncio.CancelledError):
            await waiting


async def verify_background_backup_loops(hass, entry, owner_user) -> None:
    """Verify real Telegram poll/conversation loops wait and resume after backup."""
    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.telegram.manager import TelegramManager

    runtime = entry.runtime_data
    engine = runtime.engine
    actor = engine.actor_for_ha(owner_user.id)
    state = engine.snapshot()
    telegram_id = state["members"][actor].get("telegram_id")
    assert type(telegram_id) is int, "run after the Telegram enrollment smoke"
    assert "conversation" in state["settings"]["modules"]

    bot = {"id": 900001, "username": "synthetic_backup_bot"}
    update_id = 910001
    update = {
        "update_id": update_id,
        "callback_query": {
            "id": "synthetic-backup-callback",
            "from": {"id": telegram_id, "is_bot": False},
            "message": {
                "message_id": update_id,
                "chat": {"id": telegram_id, "type": "private"},
                "from": {"id": bot["id"], "is_bot": True},
            },
            # A missing alarm is deliberate: the first attempt must be rejected
            # by the backup gate, while the post-thaw attempt returns a bounded
            # domain error and durably advances this exact update.
            "data": "fa:ARACE:nonce:1",
        },
    }

    class PollClient:
        def __init__(self):
            self.fetched = asyncio.Event()
            self.release_first = asyncio.Event()
            self.advanced = asyncio.Event()
            self.offsets = []
            self.calls = []

        async def inspect(self):
            return deepcopy(bot)

        async def updates(self, offset):
            self.offsets.append(offset)
            if offset is None or offset <= update_id:
                if len(self.offsets) == 1:
                    self.fetched.set()
                    await self.release_first.wait()
                return [deepcopy(update)]
            self.advanced.set()
            await asyncio.Event().wait()

        async def call(self, method, payload):
            self.calls.append((method, deepcopy(payload)))
            return True

    health_before = deepcopy(runtime.health)
    poll_client = PollClient()
    poll_manager = TelegramManager(hass, entry, runtime, poll_client, bot)
    execute_before = engine.execute
    execute_attempts = 0
    backup_rejected = asyncio.Event()

    async def observed_execute(*args, **kwargs):
        nonlocal execute_attempts
        execute_attempts += 1
        try:
            return await execute_before(*args, **kwargs)
        except DomainError as error:
            if error.code == "backup_in_progress":
                backup_rejected.set()
            raise

    engine.execute = observed_execute
    poll_task = asyncio.create_task(poll_manager._poll())
    poll_token = None
    try:
        await asyncio.wait_for(poll_client.fetched.wait(), timeout=4)
        poll_token = await engine.async_begin_backup()
        poll_client.release_first.set()
        await asyncio.wait_for(backup_rejected.wait(), timeout=4)

        assert engine.snapshot()["telegram"].get("offsets", {}).get(str(bot["id"])) is None
        assert poll_client.calls == []
        assert len(poll_client.offsets) == 1
        assert execute_attempts == 1

        await engine.async_end_backup(poll_token)
        poll_token = None
        await asyncio.wait_for(poll_client.advanced.wait(), timeout=4)

        assert poll_client.offsets[:2] == [None, None]
        assert execute_attempts == 2
        assert engine.snapshot()["telegram"]["offsets"][str(bot["id"])] == update_id + 1
        assert [method for method, _payload in poll_client.calls] == ["answerCallbackQuery"]
        replies = [
            event
            for event in engine.snapshot()["outbox"].values()
            if event["id"].startswith(f"tg:{bot['id']}:{update_id}:reply:")
        ]
        assert len(replies) == 1
    finally:
        poll_client.release_first.set()
        if poll_token is not None:
            await engine.async_end_backup(poll_token)
        await _cancel(poll_task)
        poll_manager._stopped = True
        engine.execute = execute_before

    job_id = "synthetic-background-backup-conversation"
    manager = TelegramManager(hass, entry, runtime, poll_client, bot)
    await manager.jobs.enqueue(
        actor,
        "Synthetic private request",
        job_id,
        datetime.now(UTC),
        [],
        bot_id=bot["id"],
        chat_id=telegram_id,
        reply_to=None,
    )

    provider_started = asyncio.Event()
    provider_release = asyncio.Event()
    provider_returned = asyncio.Event()

    class Provider:
        def __init__(self):
            self.calls = 0

        async def respond(self, selected_actor, content, operation_id, *_args, **_kwargs):
            self.calls += 1
            assert (selected_actor, content, operation_id) == (
                actor,
                "Synthetic private request",
                job_id,
            )
            provider_started.set()
            await provider_release.wait()
            provider_returned.set()
            return "Synthetic completion"

    provider = Provider()
    assistant_before = runtime.assistant
    runtime.assistant = provider
    background_update_before = engine.background_update
    finish_waiting = asyncio.Event()
    finish_persisted = asyncio.Event()

    async def observed_background_update(kind, now, change):
        if kind == "assistant_finished":
            finish_waiting.set()
        result = await background_update_before(kind, now, change)
        if kind == "assistant_finished":
            finish_persisted.set()
        return result

    engine.background_update = observed_background_update
    conversation_task = asyncio.create_task(manager._conversations())
    conversation_token = None
    try:
        await asyncio.wait_for(provider_started.wait(), timeout=4)
        conversation_token = await engine.async_begin_backup()
        provider_release.set()
        await asyncio.wait_for(provider_returned.wait(), timeout=4)
        await asyncio.wait_for(finish_waiting.wait(), timeout=4)

        frozen = engine.snapshot()
        assert frozen["assistant_jobs"][job_id]["status"] == "pending"
        assert not any(
            event["id"].startswith(job_id + ":model-result:") for event in frozen["outbox"].values()
        )
        assert provider.calls == 1
        assert not conversation_task.done()

        await engine.async_end_backup(conversation_token)
        conversation_token = None
        await _wait_for_event_or_failure(
            finish_persisted,
            conversation_task,
            runtime.health,
            label="assistant completion persistence after backup thaw",
        )

        completed = engine.snapshot()
        assert completed["assistant_jobs"][job_id]["status"] == "complete"
        assert provider.calls == 1
        results = [
            event
            for event in completed["outbox"].values()
            if event["id"].startswith(job_id + ":model-result:")
        ]
        assert len(results) == 1
        assert results[0]["data"]["text"] == "Synthetic completion"
    finally:
        provider_release.set()
        if conversation_token is not None:
            await engine.async_end_backup(conversation_token)
        await _cancel(conversation_task)
        manager._stopped = True
        engine.background_update = background_update_before
        runtime.assistant = assistant_before
        runtime.health.clear()
        runtime.health.update(health_before)

    retry_ids = (
        "synthetic-storage-retry-completes",
        "synthetic-storage-retry-revoked",
    )

    class RetryProvider:
        def __init__(self):
            self.calls = []

        async def respond(self, selected_actor, _content, operation_id, *_args, **_kwargs):
            assert selected_actor == actor and operation_id in retry_ids
            self.calls.append(operation_id)
            return "Frozen completion " + operation_id

    retry_provider = RetryProvider()
    retry_manager = TelegramManager(hass, entry, runtime, poll_client, bot)
    await retry_manager.jobs.enqueue(
        actor,
        "Synthetic persisted completion",
        retry_ids[0],
        datetime.now(UTC),
        [],
        bot_id=bot["id"],
        chat_id=telegram_id,
        reply_to=None,
    )
    assistant_before = runtime.assistant
    health_before_retry = deepcopy(runtime.health)
    runtime.assistant = retry_provider
    persist_before = engine._persist
    background_update_before = engine.background_update
    failed_once = dict.fromkeys(retry_ids, False)
    failure_events = {retry_id: asyncio.Event() for retry_id in retry_ids}
    completion_events = {retry_id: asyncio.Event() for retry_id in retry_ids}

    async def fail_one_completion(candidate):
        for retry_id in retry_ids:
            job = candidate["assistant_jobs"].get(retry_id)
            if job and job["status"] != "pending" and not failed_once[retry_id]:
                failed_once[retry_id] = True
                failure_events[retry_id].set()
                raise OSError("synthetic one-shot completion persistence failure")
        await persist_before(candidate)

    async def observe_completion(kind, now, change):
        result = await background_update_before(kind, now, change)
        if kind == "assistant_finished":
            current = engine.snapshot()["assistant_jobs"]
            for retry_id in retry_ids:
                if current.get(retry_id, {}).get("status") in {"complete", "cancelled"}:
                    completion_events[retry_id].set()
        return result

    engine._persist = fail_one_completion
    engine.background_update = observe_completion
    retry_task = asyncio.create_task(retry_manager._conversations())
    original_revision = None
    try:
        first = retry_ids[0]
        await _wait_for_event_or_failure(
            failure_events[first],
            retry_task,
            runtime.health,
            label="first synthetic Store completion failure",
        )
        failed_state = engine.snapshot()
        assert failed_state["assistant_jobs"][first]["status"] == "pending"
        assert not any(
            event["id"].startswith(first + ":model-result:")
            for event in failed_state["outbox"].values()
        )
        assert retry_provider.calls == [first]

        await _wait_for_event_or_failure(
            completion_events[first],
            retry_task,
            runtime.health,
            label="frozen completion retry after Store recovery",
        )
        completed_state = engine.snapshot()
        assert completed_state["assistant_jobs"][first]["status"] == "complete"
        assert retry_provider.calls == [first]
        assert (
            len(
                [
                    event
                    for event in completed_state["outbox"].values()
                    if event["id"].startswith(first + ":model-result:")
                ]
            )
            == 1
        )

        second = retry_ids[1]
        await retry_manager.jobs.enqueue(
            actor,
            "Synthetic persisted completion",
            second,
            datetime.now(UTC),
            [],
            bot_id=bot["id"],
            chat_id=telegram_id,
            reply_to=None,
        )
        await _wait_for_event_or_failure(
            failure_events[second],
            retry_task,
            runtime.health,
            label="revoked synthetic Store completion failure",
        )
        assert retry_provider.calls == [first, second]

        def revoke_binding(ctx):
            nonlocal original_revision
            member = ctx.state["members"][actor]
            original_revision = member["revision"]
            member.update(telegram_id=telegram_id + 1, revision=original_revision + 1)

        await engine.system_update("revoke-storage-retry-actor", datetime.now(UTC), revoke_binding)
        await _wait_for_event_or_failure(
            completion_events[second],
            retry_task,
            runtime.health,
            label="revoked frozen completion cancellation",
        )
        revoked_state = engine.snapshot()
        assert revoked_state["assistant_jobs"][second]["status"] == "cancelled"
        assert retry_provider.calls == [first, second]
        assert not any(
            event["id"].startswith(second + ":model-result:")
            for event in revoked_state["outbox"].values()
        )
    finally:
        await _cancel(retry_task)
        retry_manager._stopped = True
        engine.background_update = background_update_before
        engine._persist = persist_before
        runtime.assistant = assistant_before
        if original_revision is not None:

            def restore_binding(ctx):
                member = ctx.state["members"][actor]
                member.update(telegram_id=telegram_id, revision=member["revision"] + 1)

            await engine.system_update(
                "restore-storage-retry-actor", datetime.now(UTC), restore_binding
            )
        runtime.health.clear()
        runtime.health.update(health_before_retry)

    print(
        "PASS: real Telegram poll and conversation loops survive backup races "
        "and Store completion retries without duplicate update consumption, "
        "provider execution or stale replies"
    )
