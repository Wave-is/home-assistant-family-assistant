"""Point reservations and family promises survive concurrency and disk faults."""

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.rewards import wallet
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.messages import render
from custom_components.family_assistant.telegram.router import route


async def setup(engine, now, **extra):
    await engine.execute(
        "parent",
        "court.award",
        {"member": "child", "points": 10, "reason": "Synthetic initiative"},
        "points",
        now,
    )
    return await engine.execute(
        "owner",
        "court.reward_save",
        {"name": "Choose a family game", "cost": 7, **extra},
        "catalog",
        now,
    )


async def request(engine, now, item, **extra):
    return await engine.execute(
        "child",
        "court.reward_request",
        {"id": item["id"], "revision": item["revision"], **extra},
        "request",
        now,
    )


async def transition(engine, now, item, decision, actor="parent", **extra):
    return await engine.execute(
        actor,
        "court.reward_transition",
        {
            "id": item["id"],
            "revision": item["revision"],
            "decision": decision,
            "reason": "Synthetic decision",
            **extra,
        },
        "transition-" + decision,
        now,
    )


@pytest.mark.asyncio
async def test_request_approve_fulfill_refund_preserves_score_and_history(engine, store, now):
    catalog = await setup(engine, now)
    score = deepcopy(engine.snapshot()["court"])
    item = await request(engine, now, catalog)
    assert wallet(engine.snapshot(), "child")["reserved"] == 7
    assert await request(engine, now, catalog) == item
    item = await transition(engine, now, item, "approve")
    assert item["status"] == "approved"
    item = await transition(engine, now, item, "fulfill")
    assert wallet(engine.snapshot(), "child")["spent"] == 7
    item = await transition(engine, now, item, "refund")
    assert wallet(engine.snapshot(), "child")["available"] == 10
    assert engine.snapshot()["court"] == score
    assert [e["status"] for e in item["history"]] == [
        "requested",
        "approved",
        "fulfilled",
        "refunded",
    ]
    assert len(Engine(store.value, store.save).view("child")["rewards"]["requests"]) == 1
    assert not engine.view("sibling")["rewards"]["requests"]
    assert "rewards" not in engine.view("guest")
    assert [b["member"] for b in engine.view("child")["rewards"]["balances"]] == ["child"]


@pytest.mark.asyncio
async def test_concurrent_requests_cannot_double_spend_and_storage_failure_reserves_nothing(
    engine, store, now
):
    catalog = await setup(engine, now)
    payload = {"id": catalog["id"], "revision": catalog["revision"]}
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("child", "court.reward_request", payload, "failed", now)
    assert engine.snapshot() == before
    store.fail = False
    results = await asyncio.gather(
        *(
            engine.execute("child", "court.reward_request", payload, f"race-{i}", now)
            for i in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert next(r for r in results if isinstance(r, DomainError)).code == "insufficient_points"
    assert wallet(engine.snapshot(), "child")["available"] == 3


@pytest.mark.asyncio
async def test_catalog_edits_do_not_reprice_pending_promise_or_destroy_metadata(engine, now):
    catalog = await setup(
        engine, now, eligible=["child"], request_ttl_hours=2, description="Original description"
    )
    item = await request(engine, now, catalog)
    changed = await engine.execute(
        "parent",
        "court.reward_save",
        {
            "id": " " + catalog["id"] + " ",
            "revision": 1,
            "name": "New label",
            "cost": 8,
            "enabled": False,
        },
        "edit",
        now,
    )
    assert changed["id"] == catalog["id"] and len(engine.snapshot()["rewards"]) == 1
    assert (
        changed["creator"] == "owner"
        and changed["eligible"] == ["child"]
        and changed["request_ttl_hours"] == 2
    )
    assert (
        item["name"] == "Choose a family game"
        and item["cost"] == 7
        and item["description"] == "Original description"
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "court.reward_save",
            {"id": catalog["id"], "revision": 1, "name": "Stale", "cost": 1},
            "stale",
            now,
        )
    await transition(engine, now, item, "approve")


@pytest.mark.asyncio
async def test_expiry_releases_once_even_disabled_and_approval_cannot_race_deadline(engine, now):
    catalog = await setup(engine, now, request_ttl_hours=1)
    item = await request(engine, now, catalog)
    with pytest.raises(DomainError, match="reward_expired"):
        await transition(engine, now + timedelta(hours=1), item, "approve")
    await engine.tick(now + timedelta(hours=1))
    assert wallet(engine.snapshot(), "child")["reserved"] == 0
    assert engine.snapshot()["reward_requests"][item["id"]]["status"] == "expired"
    notifications = [
        e for e in engine.snapshot()["outbox"].values() if e["key"] == "reward_expired"
    ]
    assert len(notifications) == 1
    await engine.tick(now + timedelta(hours=2))
    assert (
        len([e for e in engine.snapshot()["outbox"].values() if e["key"] == "reward_expired"]) == 1
    )
    state = engine.snapshot()
    state["settings"]["modules"].remove("court")
    state["reward_requests"][item["id"]]["status"] = "requested"
    state["outbox"] = {}

    async def save(_):
        pass

    disabled = Engine(state, save)
    await disabled.tick(now + timedelta(hours=3))
    assert wallet(disabled.snapshot(), "child")["reserved"] == 0
    assert not disabled.snapshot()["outbox"]


@pytest.mark.asyncio
async def test_authority_eligibility_and_transitions(engine, now):
    catalog = await setup(engine, now, eligible=["child"])
    for actor in ("guest", "child", "adult"):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(
                actor, "court.reward_save", {"name": "Unauthorized", "cost": 1}, "denied", now
            )
    assert not engine.view("sibling")["rewards"]["catalog"]
    with pytest.raises(DomainError, match="forbidden"):
        await request(engine, now, catalog, member="sibling")
    item = await request(engine, now, catalog)
    for decision in ("approve", "fulfill", "refund", "reject"):
        with pytest.raises(DomainError, match="forbidden"):
            await transition(engine, now, item, decision, actor="child")
    with pytest.raises(DomainError, match="forbidden"):
        await transition(engine, now, item, "cancel", actor="sibling")
    with pytest.raises(DomainError, match="invalid_transition"):
        await transition(engine, now, item, "fulfill")
    cancelled = await transition(engine, now, item, "cancel", actor="child")
    assert (
        cancelled["status"] == "cancelled" and wallet(engine.snapshot(), "child")["available"] == 10
    )


@pytest.mark.asyncio
async def test_reversed_earnings_are_real_debt_not_free_points(engine, now):
    catalog = await setup(engine, now)
    item = await request(engine, now, catalog)
    await engine.execute(
        "owner", "court.reverse", {"id": "C000001", "reason": "Corrected score"}, "reverse", now
    )
    assert wallet(engine.snapshot(), "child")["net"] == -7
    with pytest.raises(DomainError, match="insufficient_points"):
        await transition(engine, now, item, "approve")
    await transition(engine, now, item, "reject")
    assert wallet(engine.snapshot(), "child")["net"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"cost": True},
        {"cost": 1.5},
        {"cost": 0},
        {"cost": 10001},
        {"enabled": "yes"},
        {"eligible": ["guest"]},
        {"eligible": ["child", "child"]},
        {"request_ttl_hours": 0},
        {"revision": 0},
    ],
)
async def test_catalog_strict_values(engine, now, bad):
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner",
            "court.reward_save",
            {"name": "Synthetic privilege", "cost": 1, **bad},
            "bad",
            now,
        )
    assert not engine.snapshot()["rewards"]


@pytest.mark.asyncio
async def test_notification_render_and_superseded_requests(engine, now):
    item = await request(engine, now, await setup(engine, now))
    state = engine.snapshot()
    event = next(e for e in state["outbox"].values() if e["key"] == "reward_requested")
    for lang in ("en", "ru", "uk"):
        text = render(event, {"id": 123, "language": lang}, state)["text"]
        assert "Choose a family game" in text and "7" in text and "Child" in text
    item = await transition(engine, now, item, "approve")
    item = await transition(engine, now, item, "fulfill")
    state = engine.snapshot()
    assert state["outbox"][event["id"]]["state"] == "superseded"
    active = [
        e
        for e in state["outbox"].values()
        if e["key"] == "reward_changed" and e["state"] == "pending"
    ]
    assert len(active) == 1 and active[0]["data"]["status"] == "fulfilled"
    for lang in ("en", "ru", "uk"):
        assert (
            "Synthetic decision" in render(active[0], {"id": 123, "language": lang}, state)["text"]
        )


@pytest.mark.asyncio
async def test_telegram_wallet_request_parent_review_and_exact_replay(engine, now):
    await engine.execute(
        "parent",
        "court.award",
        {"member": "child", "points": 9, "reason": "Synthetic initiative"},
        "score",
        now,
    )
    await route(engine, "parent", "/rewardadd Choose dinner | 5", "catalog-chat", now)
    assert "R000001" in await route(engine, "child", "/rewards", "list", now)
    first = await route(engine, "child", "/reward r000001 | Friday", "request-chat", now)
    assert "V000001" in first and "awaiting parent approval" in first
    assert first == await route(engine, "child", "/reward r000001 | Friday", "request-chat", now)
    assert "reserved 5" in await route(engine, "child", "/wallet", "wallet", now)
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/rewarddecide V000001 | approve | Mine", "bad-approve", now)
    with pytest.raises(DomainError, match="not_found"):
        await route(
            engine, "sibling", "/rewarddecide V000001 | cancel | Not mine", "bad-cancel", now
        )
    await route(engine, "parent", "/rewarddecide V000001 | approve | Agreed", "approve-chat", now)
    await route(engine, "parent", "/rewarddecide V000001 | fulfill | Provided", "fulfill-chat", now)
    reply = await route(engine, "child", "/wallet", "wallet-after", now)
    assert "spent 5" in reply and "available 4" in reply
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "guest", "/rewards", "guest-list", now)
