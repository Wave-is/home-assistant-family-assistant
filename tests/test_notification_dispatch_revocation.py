"""Notification dispatch rechecks revocation after a durable claim."""

import asyncio
from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.notifications import Notifications


class ClaimGateEngine(Engine):
    """Hold a completed durable claim before returning it to the worker."""

    def __init__(self, state, persist):
        super().__init__(state, persist)
        self.claim_persisted = asyncio.Event()
        self.release_claim = asyncio.Event()

    async def system_update(self, kind, now, change):
        result = await super().system_update(kind, now, change)
        if kind == "outbox_claim" and result is not None:
            self.claim_persisted.set()
            await self.release_claim.wait()
        return result


def resolve_member(event, state):
    member = state["members"].get(event["recipient"], {})
    if not member.get("active") or not member.get("telegram_id"):
        return []
    return [{"channel": "telegram", "id": member["telegram_id"], "language": "en"}]


@pytest.mark.asyncio
async def test_participant_revocation_after_claim_prevents_transport(engine, store, now):
    state = engine.snapshot()
    state["settings"]["modules"].append("routines")
    state["members"]["adult"]["telegram_id"] = 1003
    gated = ClaimGateEngine(state, store.save)

    template = await gated.execute(
        "parent",
        "routines.save",
        {
            "title": "Private handoff",
            "assignees": ["child"],
            "steps": [{"title": "Adult step", "assignee": "adult"}],
        },
        "save-handoff",
        now,
    )
    run = await gated.execute(
        "child",
        "routines.start",
        {"id": template["id"], "revision": template["revision"], "member": "child"},
        "start-handoff",
        now,
    )

    sent = []

    async def send(event, target):
        sent.append((deepcopy(event), deepcopy(target)))
        return "unexpected"

    worker = asyncio.create_task(Notifications(gated, resolve_member, send).run(now))
    try:
        await asyncio.wait_for(gated.claim_persisted.wait(), timeout=2)
        await asyncio.wait_for(
            gated.execute(
                "owner",
                "members.save",
                {"id": "adult", "name": "Adult", "role": "adult", "active": False},
                "revoke-adult",
                now,
            ),
            timeout=2,
        )
    finally:
        gated.release_claim.set()

    assert await asyncio.wait_for(worker, timeout=2) == 0
    assert sent == []
    snapshot = gated.snapshot()
    assert snapshot["routine_runs"][run["id"]]["status"] == "cancelled"
    event = next(event for event in snapshot["outbox"].values() if event["key"] == "routine_step")
    assert event["state"] == "superseded"


@pytest.mark.asyncio
async def test_changed_recipient_target_after_claim_supersedes_delivery(engine, store, now):
    state = engine.snapshot()
    state["members"]["child"]["telegram_id"] = 1002
    gated = ClaimGateEngine(state, store.save)
    await gated.execute(
        "owner", "tasks.create", {"title": "Private task", "assignee": "child"}, "task", now
    )

    sent = []

    async def send(event, target):
        sent.append((deepcopy(event), deepcopy(target)))
        return "unexpected"

    worker = asyncio.create_task(Notifications(gated, resolve_member, send).run(now))
    try:
        await asyncio.wait_for(gated.claim_persisted.wait(), timeout=2)

        def relink(ctx):
            ctx.state["members"]["child"]["telegram_id"] = 2002

        await asyncio.wait_for(
            gated.system_update("synthetic_identity_update", now, relink), timeout=2
        )
        claimed = next(iter(gated.snapshot()["outbox"].values()))
        assert claimed["state"] == "sending"
        assert next(iter(claimed["deliveries"].values()))["state"] == "sending"
    finally:
        gated.release_claim.set()

    assert await asyncio.wait_for(worker, timeout=2) == 0
    assert sent == []
    event = next(iter(gated.snapshot()["outbox"].values()))
    assert event["state"] == "superseded"
    assert next(iter(event["deliveries"].values()))["state"] == "superseded"
