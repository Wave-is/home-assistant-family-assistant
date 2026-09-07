"""Proposal confirmations stay bound to one exact member identity epoch."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.validation import DomainError

MISSING = object()


async def enable_conversation(engine, now) -> None:
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "enable-conversation-for-proposals",
        now,
    )


async def set_parent(engine, now, *, name: str, role: str, operation: str) -> int:
    current = engine.snapshot()["members"]["parent"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": current["revision"],
            "name": name,
            "role": role,
        },
        operation,
        now,
    )
    return engine.snapshot()["members"]["parent"]["revision"]


async def seed_proposal(
    engine,
    now,
    proposal_id: str,
    *,
    actor_revision=MISSING,
) -> None:
    if actor_revision is MISSING:
        actor_revision = engine.snapshot()["members"]["parent"]["revision"]
    proposal = {
        "id": proposal_id,
        "operation_id": f"model-{proposal_id}",
        "source_hash": "a" * 64,
        "signature": "b" * 64,
        "actor": "parent",
        "role": "parent",
        "commands": [
            {
                "action": "shopping.add",
                "payload": {"name": f"Proposal item {proposal_id}"},
            }
        ],
        "preview": f"Review {proposal_id}",
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "revision": 1,
    }
    if actor_revision is not None:
        proposal["actor_revision"] = actor_revision

    def save(ctx) -> None:
        ctx.state["proposals"][proposal_id] = deepcopy(proposal)

    await engine.system_update(f"seed-{proposal_id}", now, save)


@pytest.mark.asyncio
async def test_projection_exposes_only_exact_current_member_epoch(engine, now) -> None:
    await enable_conversation(engine, now)
    await seed_proposal(engine, now, "Pcurrent")
    await seed_proposal(engine, now, "Plegacy", actor_revision=None)

    assert engine.view("parent")["proposals"] == [
        {
            "id": "Pcurrent",
            "status": "pending",
            "preview": "Review Pcurrent",
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }
    ]

    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            **settings,
            "modules": [module for module in settings["modules"] if module != "conversation"],
        },
        "disable-conversation-for-projection",
        now,
    )
    assert engine.view("parent")["proposals"] == []
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "reenable-conversation-for-projection",
        now,
    )
    assert [row["id"] for row in engine.view("parent")["proposals"]] == ["Pcurrent"]

    await set_parent(engine, now, name="Parent renamed", role="parent", operation="epoch-two")
    assert engine.view("parent")["proposals"] == []
    assert set(engine.snapshot()["proposals"]) == {"Pcurrent", "Plegacy"}


@pytest.mark.parametrize("action", ["confirm", "reject"])
@pytest.mark.parametrize(
    "actor_revision",
    [None, True, 1.0, "1", 0, 2**53],
    ids=["missing", "bool", "float", "string", "zero", "too-large"],
)
@pytest.mark.asyncio
async def test_legacy_or_malformed_epoch_cannot_transition_without_writes(
    engine, store, now, action, actor_revision
) -> None:
    await enable_conversation(engine, now)
    proposal_id = f"Plegacy-{action}-{type(actor_revision).__name__}-{actor_revision}"
    await seed_proposal(engine, now, proposal_id, actor_revision=actor_revision)
    before = engine.snapshot()
    calls = store.calls

    with pytest.raises(DomainError) as caught:
        await engine.execute(
            "parent",
            f"conversation.{action}",
            {"id": proposal_id},
            f"transition-{proposal_id}",
            now,
        )

    assert caught.value.code == "conflict"
    assert engine.snapshot() == before
    assert store.calls == calls
    assert proposal_id in engine.snapshot()["proposals"]


@pytest.mark.parametrize("action", ["confirm", "reject"])
@pytest.mark.asyncio
async def test_current_proposal_cannot_transition_after_same_role_epoch_change(
    engine, store, now, action
) -> None:
    await enable_conversation(engine, now)
    proposal_id = f"Pstale-{action}"
    await seed_proposal(engine, now, proposal_id)
    await set_parent(
        engine,
        now,
        name="Same ID, later epoch",
        role="parent",
        operation=f"advance-before-{action}",
    )
    before = engine.snapshot()
    calls = store.calls

    with pytest.raises(DomainError) as caught:
        await engine.execute(
            "parent",
            f"conversation.{action}",
            {"id": proposal_id},
            f"first-{action}-after-epoch-change",
            now,
        )

    assert caught.value.code == "conflict"
    assert engine.snapshot() == before
    assert store.calls == calls
    assert not engine.snapshot()["shopping"]


@pytest.mark.parametrize("action", ["confirm", "reject"])
@pytest.mark.asyncio
async def test_cached_transition_rechecks_module_and_same_id_epoch_after_role_aba(
    engine, store, now, action
) -> None:
    await enable_conversation(engine, now)
    proposal_id = f"Pcached-{action}"
    operation_id = f"cached-{action}"
    await seed_proposal(engine, now, proposal_id)
    payload = {"id": proposal_id}

    receipt = await engine.execute("parent", f"conversation.{action}", payload, operation_id, now)
    expected_status = "applied" if action == "confirm" else "rejected"
    assert receipt["status"] == expected_status
    created = len(engine.snapshot()["shopping"])
    calls = store.calls
    assert (
        await engine.execute("parent", f"conversation.{action}", payload, operation_id, now)
        == receipt
    )
    assert store.calls == calls
    assert len(engine.snapshot()["shopping"]) == created

    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            **settings,
            "modules": [module for module in settings["modules"] if module != "conversation"],
        },
        f"disable-conversation-{action}",
        now,
    )
    before = engine.snapshot()
    calls = store.calls
    with pytest.raises(DomainError) as caught:
        await engine.execute("parent", f"conversation.{action}", payload, operation_id, now)
    assert caught.value.code == "module_disabled"
    assert engine.snapshot() == before and store.calls == calls

    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        f"reenable-conversation-{action}",
        now,
    )
    assert (
        await engine.execute("parent", f"conversation.{action}", payload, operation_id, now)
        == receipt
    )

    await set_parent(
        engine,
        now,
        name="Same role, new epoch",
        role="parent",
        operation=f"same-role-epoch-{action}",
    )
    before = engine.snapshot()
    calls = store.calls
    with pytest.raises(DomainError) as caught:
        await engine.execute("parent", f"conversation.{action}", payload, operation_id, now)
    assert caught.value.code == "conflict"
    assert engine.snapshot() == before and store.calls == calls

    await set_parent(
        engine,
        now,
        name="Temporary adult",
        role="adult",
        operation=f"role-away-{action}",
    )
    with pytest.raises(DomainError) as caught:
        await engine.execute("parent", f"conversation.{action}", payload, operation_id, now)
    assert caught.value.code == "forbidden"
    await set_parent(
        engine,
        now,
        name="Parent rebound",
        role="parent",
        operation=f"role-return-{action}",
    )
    before = engine.snapshot()
    calls = store.calls
    with pytest.raises(DomainError) as caught:
        await engine.execute("parent", f"conversation.{action}", payload, operation_id, now)
    assert caught.value.code == "conflict"
    assert engine.snapshot() == before and store.calls == calls


@pytest.mark.asyncio
async def test_cached_confirmation_requires_the_exact_stored_terminal_receipt(
    engine, store, now
) -> None:
    await enable_conversation(engine, now)
    await seed_proposal(engine, now, "Pterminal")
    payload = {"id": "Pterminal"}
    await engine.execute("parent", "conversation.confirm", payload, "confirm-terminal", now)

    def corrupt_terminal_receipt(ctx) -> None:
        ctx.state["proposals"]["Pterminal"]["result"] = []

    await engine.system_update("corrupt-terminal-receipt", now, corrupt_terminal_receipt)
    before = engine.snapshot()
    calls = store.calls
    with pytest.raises(DomainError) as caught:
        await engine.execute("parent", "conversation.confirm", payload, "confirm-terminal", now)
    assert caught.value.code == "conflict"
    assert engine.snapshot() == before and store.calls == calls


@pytest.mark.parametrize("action", ["confirm", "reject"])
@pytest.mark.asyncio
async def test_cached_batch_transition_rechecks_member_epoch(engine, store, now, action) -> None:
    await enable_conversation(engine, now)
    proposal_id = f"Pbatch-{action}"
    await seed_proposal(engine, now, proposal_id)
    payload = {"commands": [{"action": f"conversation.{action}", "payload": {"id": proposal_id}}]}
    operation_id = f"batch-{action}"
    receipt = await engine.execute("parent", "batch", payload, operation_id, now)
    calls = store.calls
    assert await engine.execute("parent", "batch", payload, operation_id, now) == receipt
    assert store.calls == calls

    await set_parent(
        engine,
        now,
        name="Batch actor rebound",
        role="parent",
        operation=f"batch-epoch-{action}",
    )
    before = engine.snapshot()
    calls = store.calls
    with pytest.raises(DomainError) as caught:
        await engine.execute("parent", "batch", payload, operation_id, now)
    assert caught.value.code == "conflict"
    assert engine.snapshot() == before and store.calls == calls
