"""Opaque poll outbox descriptors are scoped again at claim and transport."""

import asyncio
from datetime import timedelta

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.notifications import DeliveryError, Notifications
from custom_components.family_assistant.telegram import polls
from custom_components.family_assistant.telegram.messages import render, targets
from custom_components.family_assistant.telegram.poll_delivery import KEY, current


async def setup(engine, store, now):
    state = engine.snapshot()
    state["settings"]["modules"].append("polls")
    state["telegram"]["group_id"] = -100
    state["members"]["child"]["telegram_id"] = 1002
    e = Engine(state, store.save)
    poll = await e.execute(
        "parent",
        "polls.create",
        {
            "actor_revision": 1,
            "question": "QUESTION-CANARY",
            "options": ["CHOICE-CANARY-ONE", "CHOICE-CANARY-TWO"],
            "eligible": [{"member": "child", "revision": 1}],
            "closes_at": (now + timedelta(hours=2)).isoformat(),
            "confirm_private_ballot_limits": True,
        },
        "create-poll",
        now,
    )
    return e, poll


async def queue(engine, now, descriptor, *, chat=1002):
    def change(ctx):
        ctx.notify(
            "child",
            KEY,
            {
                "actor": "child",
                "actor_revision": 1,
                "bot_id": 17,
                "chat_id": chat,
                "descriptor": descriptor,
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
            },
        )

    await engine.system_update("poll-reply", now, change)
    return next(iter(engine.snapshot()["outbox"].values()))


@pytest.mark.asyncio
async def test_opaque_storage_and_final_private_render(engine, store, now):
    e, _ = await setup(engine, store, now)
    descriptor = await polls.route(e, "child", "/polls", "list", now, private=True)
    event = await queue(e, now, descriptor)
    state = e.snapshot()
    for protected in ("outbox", "audit", "processed", "telegram", "assistant_jobs", "proposals"):
        assert "CANARY" not in repr(state[protected])
    assert "CANARY" not in repr(plans.messages(e.view("child"), "Hello", (), now))
    result = render(event, targets(event, state)[0], state, now=now)
    assert result["chat_id"] == 1002
    assert "QUESTION-CANARY" in result["text"]
    assert "CHOICE-CANARY-ONE" in result["text"]
    assert state == e.snapshot()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["epoch", "inactive", "relink", "module", "recipient", "group", "descriptor"]
)
async def test_revoked_event_is_superseded_without_send(engine, store, now, change):
    e, _ = await setup(engine, store, now)
    event = await queue(e, now, {"kind": "polls", "mode": "list"})

    def invalidate(ctx):
        if change == "epoch":
            ctx.state["members"]["child"]["revision"] += 1
        elif change == "inactive":
            ctx.state["members"]["child"]["active"] = False
        elif change == "relink":
            ctx.state["members"]["child"]["telegram_id"] = 2002
        elif change == "module":
            ctx.state["settings"]["modules"].remove("polls")
        elif change == "recipient":
            ctx.state["outbox"][event["id"]]["recipient"] = "sibling"
        elif change == "group":
            ctx.state["outbox"][event["id"]]["data"]["chat_id"] = -100
        else:
            ctx.state["outbox"][event["id"]]["data"]["descriptor"]["text"] = "FORGED"

    await e.system_update("revoke", now, invalidate)

    async def send(event, target):
        pytest.fail("Revoked content reached transport")

    assert await Notifications(e, targets, send).run(now) == 0
    assert e.snapshot()["outbox"][event["id"]]["state"] == "superseded"


@pytest.mark.asyncio
async def test_group_only_constant_redirect(engine, store, now):
    e, _ = await setup(engine, store, now)
    event = await queue(e, now, {"kind": "polls", "mode": "private"}, chat=-100)
    target = targets(event, e.snapshot())[0]
    message = render(event, target, e.snapshot(), now=now)
    assert message["chat_id"] == -100 and "direct chat" in message["text"]
    assert "CANARY" not in repr(message) and "reply_markup" not in message
    with pytest.raises(DeliveryError, match="delivery_revoked"):
        render(event, {**target, "id": -200}, e.snapshot(), now=now)


@pytest.mark.asyncio
async def test_expiry_and_stale_review_checked_on_live_clock(engine, store, now):
    e, poll = await setup(engine, store, now)
    descriptor = await polls.route(e, "child", f"ps:v:{poll['id']}:O1", "choose", now, private=True)
    event = await queue(e, now, descriptor)
    assert current(event, e.snapshot(), now)
    assert not current(event, e.snapshot(), now + timedelta(minutes=5))
    await e.execute(
        "child",
        "polls.vote",
        {
            "id": poll["id"],
            "definition_revision": 1,
            "voter_revision": 1,
            "option_id": "O2",
            "ballot_revision": None,
        },
        "card-vote",
        now,
    )
    assert not current(event, e.snapshot(), now)
    await e.tick(now + timedelta(minutes=5))
    assert not e.snapshot()["poll_reviews"]
    assert e.snapshot()["poll_ballots"][poll["id"]]["child"]["option_id"] == "O2"


@pytest.mark.asyncio
async def test_revocation_after_claim_prevents_private_dispatch(engine, store, now):
    e, _ = await setup(engine, store, now)
    event = await queue(e, now, {"kind": "polls", "mode": "list"})
    entered, release = asyncio.Event(), asyncio.Event()

    class Gate(Engine):
        async def system_update(self, kind, time, change):
            result = await super().system_update(kind, time, change)
            if kind == "outbox_claim" and result is not None:
                entered.set()
                await release.wait()
            return result

    e = Gate(e.snapshot(), store.save)

    async def send(event, target):
        pytest.fail("Revoked content reached transport")

    task = asyncio.create_task(Notifications(e, targets, send).run(now))
    try:
        await asyncio.wait_for(entered.wait(), 1)

        def revoke(ctx):
            ctx.state["members"]["child"]["revision"] += 1

        await e.system_update("revoke", now, revoke)
    finally:
        release.set()
    assert await asyncio.wait_for(task, 1) == 0
    assert e.snapshot()["outbox"][event["id"]]["state"] == "superseded"
