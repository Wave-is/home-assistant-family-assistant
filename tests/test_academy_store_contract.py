"""Canonical Engine/Store integration contract; uses the repository fixtures."""

import pytest

from custom_components.family_assistant.academy.household import mutate, project
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError

HOUSE = "synthetic-house"


@pytest.mark.asyncio
async def test_academy_uses_canonical_store(engine, store, now):
    assert "academy" not in engine.snapshot()["settings"]["modules"]
    await engine.execute("owner", "settings.module_toggle",
                         {"revision": 1, "module": "academy", "enabled": True},
                         "enable-academy", now)
    assert "academy" in engine.snapshot()["settings"]["modules"]
    await engine.system_update(
        "academy", now,
        lambda ctx: mutate(ctx.state, HOUSE, "parent", now, "enroll",
                           {"member_id": "child", "member_revision": 1,
                            "epoch": 0, "enabled": True}),
    )

    def start(ctx):
        return mutate(ctx.state, HOUSE, "child", now, "start",
                      {"epoch": 1, "operation_id": "start"})

    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.system_update("academy", now, start)
    assert engine.snapshot() == before
    store.fail = False
    started = await engine.system_update("academy", now, start)
    restarted = Engine(store.value, store.save)
    assert project(restarted.snapshot(), HOUSE, "child", now)["current"] == started
    assert "academy" not in restarted.view("child", now=now)
    assert "academy" not in restarted.view("parent", now=now)
    prior = restarted.snapshot()
    lease = await restarted.async_begin_backup()
    try:
        with pytest.raises(DomainError, match="backup_in_progress"):
            await restarted.system_update("academy", now, start)
    finally:
        await restarted.async_end_backup(lease)
    assert restarted.snapshot() == prior
