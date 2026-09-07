"""Actual-HA acceptance helper for Telegram command authority races."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime


def _ping(update_id, telegram_id):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": telegram_id, "is_bot": False},
            "chat": {"id": telegram_id, "type": "private"},
            "text": "/ping",
            "date": int(datetime.now(UTC).timestamp()),
        },
    }


async def verify_telegram_command_scope(hass, entry, owner_user):
    """Prove the loaded manager and member epoch are checked under Engine lock."""
    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.telegram.manager import TelegramManager

    runtime = entry.runtime_data
    engine = runtime.engine
    manager = runtime.telegram
    assert manager is not None and manager.runtime is runtime and manager.entry is entry
    actor = engine.actor_for_ha(owner_user.id)
    before = engine.snapshot()
    original_member = deepcopy(before["members"][actor])
    telegram_id = original_member.get("telegram_id")
    assert type(telegram_id) is int and telegram_id > 0
    offsets = before.get("telegram", {}).get("offsets", {})
    update_id = max([int(value) for value in offsets.values()] + [100_000]) + 100

    # A receiver object that is not the registered runtime manager is inert,
    # even when it carries the same bot and client objects.
    stale = TelegramManager(hass, entry, runtime, manager.client, manager.bot)
    stale_before = engine.snapshot()
    try:
        await stale.process(_ping(update_id, telegram_id))
    except DomainError as error:
        assert error.code == "forbidden"
    else:
        raise AssertionError("a non-current Telegram manager accepted a command")
    assert engine.snapshot() == stale_before

    original_persist = engine._persist
    original_system_update = engine.system_update
    persist_started = asyncio.Event()
    persist_release = asyncio.Event()
    command_waiting = asyncio.Event()
    marker_name = original_member["name"] + " (scope race)"

    async def gated_persist(state):
        candidate = state["members"][actor]
        if (
            candidate.get("name") == marker_name
            and candidate.get("revision") == original_member["revision"] + 1
        ):
            persist_started.set()
            await persist_release.wait()
        await original_persist(state)

    def rebind(ctx):
        member = ctx.state["members"][actor]
        member["name"] = marker_name
        member["revision"] += 1

    async def observed_system_update(kind, now, change, **kwargs):
        if kind == "telegram_reply":
            command_waiting.set()
        return await original_system_update(kind, now, change, **kwargs)

    engine._persist = gated_persist
    engine.system_update = observed_system_update
    rebind_task = asyncio.create_task(
        engine.system_update("telegram_scope_smoke_rebind", datetime.now(UTC), rebind)
    )
    command_task = None
    try:
        await asyncio.wait_for(persist_started.wait(), 5)
        command_task = asyncio.create_task(manager.process(_ping(update_id, telegram_id)))
        await asyncio.wait_for(command_waiting.wait(), 5)
        persist_release.set()
        await rebind_task
        try:
            await command_task
        except DomainError as error:
            assert error.code == "forbidden"
        else:
            raise AssertionError("a queued command crossed a committed member epoch")
        raced = engine.snapshot()
        assert raced["outbox"] == before["outbox"]
        assert raced["telegram"].get("offsets", {}) == offsets
        assert raced["shopping"] == before["shopping"]
        assert raced["tasks"] == before["tasks"]
    finally:
        persist_release.set()
        if not rebind_task.done():
            await rebind_task
        if command_task is not None and not command_task.done():
            command_task.cancel()
            try:
                await command_task
            except asyncio.CancelledError:
                pass
        engine._persist = original_persist
        engine.system_update = original_system_update

        def restore(ctx):
            restored_member = deepcopy(original_member)
            restored_member["revision"] = ctx.state["members"][actor]["revision"] + 1
            ctx.state["members"][actor] = restored_member

        if engine.snapshot()["members"][actor]["name"] == marker_name:
            await engine.system_update("telegram_scope_smoke_restore", datetime.now(UTC), restore)

    restored = engine.snapshot()
    assert restored["members"][actor] == {
        **original_member,
        "revision": original_member["revision"] + 2,
    }
    assert restored["outbox"] == before["outbox"]
    assert restored["telegram"].get("offsets", {}) == offsets
    print(
        "PASS: actual HA Telegram manager and locked member-epoch guards reject "
        "stale queued commands without replies or offset advancement"
    )


__all__ = ["verify_telegram_command_scope"]
