"""Private, bounded review intents used by Telegram poll callbacks."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import poll_reviews
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def poll_engine(engine):
    state = engine.snapshot()
    if "polls" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("polls")

    async def save(_state):
        return None

    return Engine(state, save)


async def create_poll(engine, now, *, operation="create", eligible=("child",)):
    state = engine.snapshot()
    return await engine.execute(
        "parent",
        "polls.create",
        {
            "actor_revision": state["members"]["parent"]["revision"],
            "question": "Synthetic private question canary",
            "options": ["Private choice alpha", "Private choice beta"],
            "eligible": [
                {"member": member, "revision": state["members"][member]["revision"]}
                for member in eligible
            ],
            "closes_at": (now + timedelta(hours=2)).isoformat(),
            "confirm_private_ballot_limits": True,
        },
        operation,
        now,
    )


def ctx(state, now, operation="review-system"):
    return Context(state, {"id": "system", "role": "system"}, now, operation)


def assert_code(code, call):
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_begin_is_opaque_idempotent_private_and_contains_no_plaintext(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    state = e.snapshot()

    first = poll_reviews.begin(ctx(state, now), "child", "vote", poll_id, "O1", "tg:1:10:action")
    again = poll_reviews.begin(ctx(state, now), "child", "vote", poll_id, "O1", "tg:1:10:action")
    assert first == again
    assert set(first) == {"review_id"}
    assert first["review_id"].startswith("PR")
    stored = state["poll_reviews"][first["review_id"]]
    assert stored["source"] == {
        "poll_id": poll_id,
        "definition_revision": 1,
        "ballot_revision": None,
        "option_id": "O1",
    }
    assert "Synthetic private question canary" not in repr(stored)
    assert "Private choice alpha" not in repr(stored)

    assert_code(
        "idempotency_conflict",
        lambda: poll_reviews.begin(
            ctx(state, now), "child", "vote", poll_id, "O2", "tg:1:10:action"
        ),
    )
    assert_code(
        "forbidden",
        lambda: poll_reviews.get_current(state, "sibling", first["review_id"], now),
    )


@pytest.mark.asyncio
async def test_claim_freezes_one_canonical_operation_across_new_updates(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    state = e.snapshot()
    review = poll_reviews.begin(ctx(state, now), "child", "vote", poll_id, "O1", "tg:1:10:action")
    action, payload, canonical = poll_reviews.claim(
        ctx(state, now), "child", review["review_id"], "tg:1:11:action"
    )
    retried = poll_reviews.claim(ctx(state, now), "child", review["review_id"], "tg:1:12:action")
    assert retried == (action, payload, canonical)
    assert canonical == "tg:1:11:action"
    assert action == "polls.vote"
    assert payload == {
        "id": poll_id,
        "definition_revision": 1,
        "voter_revision": 1,
        "option_id": "O1",
        "ballot_revision": None,
    }


@pytest.mark.asyncio
async def test_claim_rechecks_source_before_first_command_and_epoch_always(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    state = e.snapshot()
    review = poll_reviews.begin(ctx(state, now), "child", "vote", poll_id, "O1", "tg:1:10:action")
    state["polls"][poll_id]["definition_revision"] = 2
    before = deepcopy(state["poll_reviews"])
    assert_code(
        "conflict",
        lambda: poll_reviews.claim(ctx(state, now), "child", review["review_id"], "tg:1:11:action"),
    )
    assert state["poll_reviews"] == before

    state["polls"][poll_id]["definition_revision"] = 1
    state["members"]["child"]["revision"] = 2
    assert_code(
        "forbidden",
        lambda: poll_reviews.claim(ctx(state, now), "child", review["review_id"], "tg:1:11:action"),
    )


@pytest.mark.asyncio
async def test_claimed_retry_allows_only_precommit_or_its_exact_postcommit(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    state = e.snapshot()
    review = poll_reviews.begin(ctx(state, now), "child", "vote", poll_id, "O1", "tg:1:10:action")
    action, payload, canonical = poll_reviews.claim(
        ctx(state, now), "child", review["review_id"], "tg:1:11:action"
    )

    async def save(_state):
        return None

    committed = Engine(state, save)
    await committed.execute("child", action, payload, canonical, now)
    after = committed.snapshot()
    assert poll_reviews.claim(ctx(after, now), "child", review["review_id"], "tg:1:99:action") == (
        action,
        payload,
        canonical,
    )

    await committed.execute(
        "child",
        "polls.vote",
        {**payload, "option_id": "O2", "ballot_revision": 1},
        "other-vote",
        now,
    )
    changed = committed.snapshot()
    assert_code(
        "conflict",
        lambda: poll_reviews.claim(
            ctx(changed, now), "child", review["review_id"], "tg:1:100:action"
        ),
    )


@pytest.mark.asyncio
async def test_parent_lifecycle_review_requires_capability_and_current_revision(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    state = e.snapshot()
    close = poll_reviews.begin(ctx(state, now), "parent", "close", poll_id, None, "tg:1:20:action")
    action, payload, canonical = poll_reviews.claim(
        ctx(state, now), "parent", close["review_id"], "tg:1:21:action"
    )
    assert (action, payload, canonical) == (
        "polls.close",
        {"id": poll_id, "revision": 1, "actor_revision": 1},
        "tg:1:21:action",
    )
    assert_code(
        "forbidden",
        lambda: poll_reviews.begin(
            ctx(state, now), "child", "close", poll_id, None, "tg:1:22:action"
        ),
    )
    assert_code(
        "forbidden",
        lambda: poll_reviews.begin(
            ctx(state, now), "parent", "archive", poll_id, None, "tg:1:23:action"
        ),
    )


@pytest.mark.asyncio
async def test_cancel_expiry_prune_and_caps_never_touch_ballots(engine, now):
    e = await poll_engine(engine)
    poll_id = (await create_poll(e, now))["id"]
    state = e.snapshot()
    review = poll_reviews.begin(ctx(state, now), "child", "vote", poll_id, "O1", "tg:1:1:action")
    poll_reviews.cancel(ctx(state, now), "child", review["review_id"], "tg:1:2:action")
    poll_reviews.cancel(ctx(state, now), "child", review["review_id"], "tg:1:2:action")
    assert_code(
        "invalid_transition",
        lambda: poll_reviews.claim(ctx(state, now), "child", review["review_id"], "tg:1:3:action"),
    )

    for index in range(9):
        poll_reviews.begin(
            ctx(state, now),
            "child",
            "vote",
            poll_id,
            "O1" if index % 2 == 0 else "O2",
            f"tg:1:{index + 10}:action",
        )
    assert_code(
        "invalid_transition",
        lambda: poll_reviews.begin(
            ctx(state, now), "child", "vote", poll_id, "O1", "tg:1:99:action"
        ),
    )
    ballots = deepcopy(state["poll_ballots"])
    assert poll_reviews.prune(ctx(state, now + timedelta(minutes=5))) == 10
    assert state["poll_reviews"] == {}
    assert state["poll_ballots"] == ballots
