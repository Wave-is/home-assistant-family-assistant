"""Historical routine receipts do not resurrect revoked execution scope."""

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def started(engine, store, now, *, batch=False):
    state = engine.snapshot()
    state["settings"]["modules"].append("routines")
    engine = Engine(state, store.save)
    template = await engine.execute(
        "parent",
        "routines.save",
        {
            "title": "Shared preparation",
            "assignees": ["child"],
            "steps": [
                {"title": "Child step", "confirmation": "manual"},
                {"title": "Adult step", "confirmation": "manual", "assignee": "adult"},
            ],
        },
        "template",
        now,
    )
    payload = {"id": template["id"], "revision": template["revision"], "member": "child"}
    action = "routines.start"
    if batch:
        payload = {"commands": [{"action": action, "payload": payload}]}
        action = "batch"
    result = await engine.execute("child", action, payload, "start", now)
    return engine, action, payload, result


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("revocation", ["participant", "source", "module"])
async def test_replay_denies_changed_authority(engine, store, now, batch, revocation):
    engine, action, payload, result = await started(engine, store, now, batch=batch)
    run = result["items"][0] if batch else result
    assert run["steps"][0]["nonce"]
    assert await engine.execute("child", action, payload, "start", now) == result
    if revocation == "module":
        settings = engine.snapshot()["settings"]
        await engine.execute(
            "owner",
            "settings.save",
            {
                "name": settings["name"],
                "language": settings["language"],
                "modules": [m for m in settings["modules"] if m != "routines"],
            },
            "disable",
            now,
        )
        expected = "module_disabled"
    else:
        member = "adult" if revocation == "participant" else "parent"
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": member,
                "revision": engine.snapshot()["members"][member]["revision"],
                "name": "Revoked",
                "role": "guest",
                "active": True,
            },
            "revoke",
            now,
        )
        expected = "forbidden"
    current = engine.snapshot()["routine_runs"][run["id"]]
    assert current["status"] == "cancelled"
    assert all("nonce" not in step for step in current["steps"])
    before, writes = engine.snapshot(), store.calls
    with pytest.raises(DomainError) as caught:
        await engine.execute("child", action, payload, "start", now)
    assert caught.value.code == expected
    assert engine.snapshot() == before and store.calls == writes


@pytest.mark.asyncio
async def test_reenabled_module_does_not_revive_cancelled_receipt(engine, store, now):
    engine, action, payload, _ = await started(engine, store, now)
    settings = engine.snapshot()["settings"]
    for suffix, modules in [
        ("off", [m for m in settings["modules"] if m != "routines"]),
        ("on", settings["modules"]),
    ]:
        await engine.execute(
            "owner",
            "settings.save",
            {
                "name": settings["name"],
                "language": settings["language"],
                "modules": modules,
            },
            suffix,
            now,
        )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("child", action, payload, "start", now)


@pytest.mark.asyncio
async def test_completed_confirmation_replays_exactly_without_effect(engine, store, now):
    engine, _, _, run = await started(engine, store, now)
    payload = {
        "id": run["id"],
        "revision": run["revision"],
        "step": 0,
        "nonce": run["steps"][0]["nonce"],
    }
    result = await engine.execute("child", "routines.confirm", payload, "confirmed", now)
    assert "nonce" not in result["steps"][1]
    before, writes = engine.snapshot(), store.calls
    assert await engine.execute("child", "routines.confirm", payload, "confirmed", now) == result
    assert engine.snapshot() == before and store.calls == writes


@pytest.mark.asyncio
async def test_manual_reason_is_not_an_authorization_code(engine, store, now):
    engine, _, _, run = await started(engine, store, now)
    payload = {"id": run["id"], "revision": run["revision"], "reason": "authorization_removed"}
    cancelled = await engine.execute("parent", "routines.cancel", payload, "cancel", now)
    assert cancelled["cancellation_cause"] == "manual"
    before, writes = engine.snapshot(), store.calls
    assert await engine.execute("parent", "routines.cancel", payload, "cancel", now) == cancelled
    assert engine.snapshot() == before and store.calls == writes
