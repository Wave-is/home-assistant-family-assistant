"""Polls run through the real persistence, replay, clock and role boundaries."""

import asyncio
import json
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def enabled(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"].append("polls")
    return Engine(state, store.save)


def create_payload(engine, now):
    state = engine.snapshot()
    return {
        "actor_revision": state["members"]["parent"]["revision"],
        "question": "PRIVATE-POLL-QUESTION",
        "options": ["PRIVATE-FIRST-CHOICE", "PRIVATE-SECOND-CHOICE"],
        "eligible": [
            {"member": name, "revision": state["members"][name]["revision"]}
            for name in ("child", "sibling")
        ],
        "closes_at": (now + timedelta(hours=1)).isoformat(),
        "confirm_private_ballot_limits": True,
    }


async def create(engine, now):
    return await engine.execute(
        "parent", "polls.create", create_payload(engine, now), "create", now
    )


def ballot(poll, *, revision=None, option="O1"):
    return {
        "id": poll["id"],
        "definition_revision": 1,
        "voter_revision": 1,
        "option_id": option,
        "ballot_revision": revision,
    }


async def parent_action(engine, action, poll, now, *, actor="parent", **extra):
    return await engine.execute(
        actor,
        f"polls.{action}",
        {"id": poll["id"], "revision": poll["revision"], "actor_revision": 1, **extra},
        action,
        now,
    )


def test_additive_poll_buckets_preserve_existing_and_unknown_data(engine, store):
    state = engine.snapshot()
    for key in ("polls", "poll_ballots", "poll_reviews"):
        state.pop(key, None)
    state["future_extension"] = {"preserve": True}
    loaded = Engine(state, store.save).snapshot()
    assert loaded["future_extension"] == {"preserve": True}
    for key in ("polls", "poll_ballots", "poll_reviews"):
        assert loaded[key] == {}
    assert all(loaded[key] == value for key, value in state.items())


@pytest.mark.asyncio
async def test_concurrent_voters_do_not_conflict_or_expose_ballots(engine, store, now):
    engine = enabled(engine, store)
    before = engine.snapshot()
    poll = await create(engine, now)
    results = await asyncio.gather(
        engine.execute("child", "polls.vote", ballot(poll), "child-vote", now),
        engine.execute("sibling", "polls.vote", ballot(poll, option="O2"), "sibling-vote", now),
    )
    assert results == [{"id": poll["id"], "ballot_revision": 1}] * 2
    state = engine.snapshot()
    assert state["polls"][poll["id"]]["revision"] == 1
    parent = engine.view("parent", now=now)
    assert parent["polls"]["open"][0]["own_ballot"] is None
    assert "results" not in parent["polls"]["open"][0]
    assert "cast_count" not in parent["polls"]["open"][0]
    assert engine.view("child", now=now)["polls"]["open"][0]["own_ballot"] == {
        "option_id": "O1",
        "revision": 1,
    }
    assert engine.view("adult", now=now)["polls"] == {"open": [], "closed": [], "archived": []}
    assert "polls" not in engine.view("guest", now=now)
    for key in ("outbox", "tasks", "court", "alarms", "network"):
        assert state[key] == before[key]
    for key in ("audit", "processed", "outbox"):
        serialized = json.dumps(state[key])
        assert "PRIVATE-" not in serialized
        assert '"option_id"' not in serialized
        assert '"O1"' not in serialized and '"O2"' not in serialized


@pytest.mark.asyncio
async def test_clock_reload_and_exact_replay_never_recast_vote(engine, store, now):
    engine = enabled(engine, store)
    poll = await create(engine, now)
    result = await engine.execute("child", "polls.vote", ballot(poll), "vote", now)
    resumed = Engine(deepcopy(store.value), store.save)
    close_time = now + timedelta(hours=1)
    assert resumed.view("child", now=close_time)["polls"]["closed"][0]["cast_count"] == 1
    assert await resumed.tick(close_time)
    assert not await resumed.tick(close_time + timedelta(seconds=1))
    before = resumed.snapshot()
    assert await resumed.execute("child", "polls.vote", ballot(poll), "vote", close_time) == result
    assert resumed.snapshot() == before
    with pytest.raises(DomainError):
        await resumed.execute("sibling", "polls.vote", ballot(poll), "late", close_time)
    assert resumed.snapshot() == before


@pytest.mark.asyncio
async def test_archive_store_failure_is_atomic_then_compacts_ballots(engine, store, now):
    engine = enabled(engine, store)
    poll = await create(engine, now)
    await engine.execute("child", "polls.vote", ballot(poll), "vote", now)
    closed = await parent_action(engine, "close", poll, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await parent_action(engine, "archive", closed, now)
    assert engine.snapshot() == before
    store.fail = False
    archived = await parent_action(engine, "archive", closed, now)
    assert archived["status"] == "archived"
    assert poll["id"] not in engine.snapshot()["poll_ballots"]
    assert engine.view("child", now=now)["polls"] == {"open": [], "closed": [], "archived": []}
    row = engine.view("parent", now=now)["polls"]["archived"][0]
    assert row["results"] == [{"option_id": "O1", "count": 1}, {"option_id": "O2", "count": 0}]
    assert "eligible" not in row and row["own_ballot"] is None
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute("child", "polls.vote", ballot(poll), "vote", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_purge_replay_does_not_recreate_and_requires_current_owner(engine, store, now):
    engine = enabled(engine, store)
    poll = await create(engine, now)
    closed = await parent_action(engine, "close", poll, now)
    archived = await parent_action(engine, "archive", closed, now)
    with pytest.raises(DomainError, match="forbidden"):
        await parent_action(engine, "purge", archived, now, confirm_delete=True)
    deleted = await parent_action(
        engine, "purge", archived, now, actor="owner", confirm_delete=True
    )
    before = engine.snapshot()
    assert (
        await parent_action(engine, "purge", archived, now, actor="owner", confirm_delete=True)
        == deleted
    )
    assert engine.snapshot() == before
    assert before["polls"] == {}
    with pytest.raises(DomainError):
        await create(engine, now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_failed_batch_discards_poll_allocation_and_votes(engine, store, now):
    engine = enabled(engine, store)
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await engine.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "polls.create", "payload": create_payload(engine, now)},
                    {"action": "polls.vote", "payload": {"id": "missing"}},
                ]
            },
            "failed-batch",
            now,
        )
    assert engine.snapshot() == before
    assert store.calls == 0
