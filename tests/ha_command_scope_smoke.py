"""Actual Home Assistant acceptance helper for generic scoped commands."""

from __future__ import annotations

from datetime import UTC, datetime


async def verify_command_scope(hass, entry, owner):
    """Exercise current HA users, runtime reload and exact Engine replay."""
    from custom_components.family_assistant.command_scope import capture
    from custom_components.family_assistant.domain.validation import DomainError

    scope = await capture(hass, entry.entry_id, owner.id, owner)
    operation = "ha-generic-command-scope-replay"
    item_name = "Synthetic generic scoped command"
    before = set(scope.engine.snapshot()["shopping"])
    result = await scope.engine.execute(
        scope.actor,
        "shopping.add",
        {"name": item_name},
        operation,
        datetime.now(UTC),
        guard=scope.guard,
    )
    await scope.check()
    scope.notify()
    replay = await scope.engine.execute(
        scope.actor,
        "shopping.add",
        {"name": item_name},
        operation,
        datetime.now(UTC),
        guard=scope.guard,
    )
    assert replay == result
    created = set(scope.engine.snapshot()["shopping"]) - before
    assert len(created) == 1

    child_record = next(
        member
        for member in scope.engine.snapshot()["members"].values()
        if member.get("role") == "child" and member.get("ha_user_id")
    )
    child_user = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child_user is not None and child_user.is_active
    child_scope = await capture(hass, entry.entry_id, child_user.id, child_user)
    try:
        await hass.auth.async_update_user(child_user, is_active=False)
        try:
            await child_scope.check()
        except DomainError as error:
            assert error.code == "forbidden"
        else:
            raise AssertionError("deactivated HA user retained command scope")
    finally:
        await hass.auth.async_update_user(child_user, is_active=True)

    old_scope = await capture(hass, entry.entry_id, owner.id, owner)
    old_runtime = entry.runtime_data
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data is not old_runtime
    try:
        await old_scope.check()
    except DomainError as error:
        assert error.code == "conflict"
    else:
        raise AssertionError("replaced runtime retained command scope")

    fresh = await capture(hass, entry.entry_id, owner.id, owner)
    assert (
        await fresh.engine.execute(
            fresh.actor,
            "shopping.add",
            {"name": item_name},
            operation,
            datetime.now(UTC),
            guard=fresh.guard,
        )
        == result
    )
    assert set(fresh.engine.snapshot()["shopping"]) - before == created
    print("PASS: actual HA generic command identity scope, revocation, reload and replay")


__all__ = ["verify_command_scope"]
