"""Adversarial source boundaries and alias revocation at the real commit boundary."""

import asyncio

import pytest

from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.router import route
from tests.test_name_learning import model_for, setup


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["forget", "actor", "target", "new_candidate"])
async def test_resolved_alias_is_rechecked_after_interpretation_commit(
    engine, store, now, monkeypatch, revocation
):
    engine = await setup(engine, store, now)
    assistant = Assistant(engine, Cascade([model_for()], {}))
    await route(engine, "parent", "Alxe task Buy bread", "learn", now, fallback=assistant.respond)
    before = engine.snapshot()["tasks"]
    recorded = asyncio.Event()
    resume = asyncio.Event()
    original_update = engine.system_update

    async def pause_after_plan(reason, timestamp, mutate):
        result = await original_update(reason, timestamp, mutate)
        if reason == "command_interpretation":
            recorded.set()
            await resume.wait()
        return result

    monkeypatch.setattr(engine, "system_update", pause_after_plan)
    pending = asyncio.create_task(
        route(engine, "parent", "Alxe task Wash dishes", "racing-alias", now)
    )
    try:
        await asyncio.wait_for(recorded.wait(), 2)
        if revocation == "forget":
            rule = next(iter(engine.snapshot()["memory"]["phrases"].values()))
            await engine.execute("parent", "conversation.forget", {"id": rule["id"]}, "revoke", now)
        else:
            identifier = {"actor": "parent", "target": "child", "new_candidate": "sibling"}[
                revocation
            ]
            member = engine.snapshot()["members"][identifier]
            await engine.execute(
                "owner",
                "members.save",
                {
                    "id": identifier,
                    "revision": member["revision"],
                    "name": "Alce" if revocation == "new_candidate" else member["name"],
                    "role": member["role"],
                },
                "revoke",
                now,
            )
        resume.set()
        with pytest.raises(DomainError, match="conflict"):
            await asyncio.wait_for(pending, 2)
    finally:
        resume.set()
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    assert engine.snapshot()["tasks"] == before
    assert "racing-alias" not in engine.snapshot()["processed"]
    assert (
        engine.snapshot()["telegram"]["plans"]["racing-alias"]["action"]
        == "conversation.apply_name_repair"
    )
    # The durable rejected interpretation cannot bypass the guard on redelivery.
    with pytest.raises(DomainError, match="conflict"):
        await route(engine, "parent", "Alxe task Wash dishes", "racing-alias", now)
    assert engine.snapshot()["tasks"] == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,quoted",
    [
        ("What does this request mean?", "Alxe task Buy bread"),
        ('My friend said "Alxe task Buy bread".', ""),
        ("Do not assign task Alxe - Buy bread", ""),
        ("Don't give Alxe a task", ""),
    ],
)
async def test_model_cannot_autocreate_from_quote_or_negated_source(
    engine, store, now, source, quoted
):
    engine = await setup(engine, store, now)
    assistant = Assistant(engine, Cascade([model_for()], {}))
    reply = await assistant.respond("parent", source, "untrusted-command", now, quoted_text=quoted)
    assert "/confirm" in reply
    assert not engine.snapshot()["tasks"]
    assert not engine.snapshot()["memory"].get("phrases")
