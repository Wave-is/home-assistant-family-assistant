"""Version binding at human/model boundaries without weakening domain commands."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram import commands
from custom_components.family_assistant.telegram.router import route


@pytest.mark.parametrize("value", [None, True, 1.0, "1", 0, 2**53])
def test_context_distinguishes_omitted_lookup_from_invalid_explicit_version(engine, now, value):
    state = engine.snapshot()
    ctx = Context(state, state["members"]["owner"], now, "lookup")
    assert ctx.record("members", "owner") == state["members"]["owner"]
    with pytest.raises(DomainError, match="invalid_field"):
        ctx.record("members", "owner", value)


@pytest.mark.asyncio
async def test_human_command_freezes_revision_before_write_and_replay_does_not_rebase(engine, now):
    item = await engine.execute(
        "parent", "shopping.add", {"name": "Milk", "quantity": 3}, "milk", now
    )
    message = f"/bought {item['id']} | 1"
    await route(engine, "parent", message, "purchase-message", now)
    state = engine.snapshot()
    frozen = state["telegram"]["plans"]["purchase-message"]
    assert frozen["payload"]["revision"] == 1
    assert state["shopping"][item["id"]]["purchased"] == 1
    await engine.execute(
        "parent",
        "shopping.purchase",
        {"id": item["id"], "revision": 2, "quantity": 1},
        "other-message",
        now,
    )
    before = engine.snapshot()
    await route(engine, "parent", message, "purchase-message", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_stale_interpretation_is_not_rebound_after_persistence(engine, now):
    task = await engine.execute(
        "parent", "tasks.create", {"title": "Original", "assignee": "child"}, "task", now
    )
    content = "approve original task"

    def prepared(ctx):
        ctx.state["telegram"]["plans"] = {
            "frozen": {
                "signature": commands.signature("parent", content, ()),
                "actor": "parent",
                "action": "tasks.complete",
                "payload": {"id": task["id"], "revision": task["revision"]},
                "created_at": now.isoformat(),
            }
        }

    await engine.system_update("persisted-plan", now, prepared)
    await engine.execute(
        "parent",
        "tasks.revise",
        {"id": task["id"], "revision": task["revision"], "title": "Changed"},
        "change",
        now,
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await route(engine, "parent", content, "frozen", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_inference_does_not_rebase_stale_record_to_new_version(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "enable",
        now,
    )
    task = await engine.execute(
        "parent", "tasks.create", {"title": "Original", "assignee": "child"}, "task", now
    )

    class ChangingProvider:
        async def generate(self, messages, schema):
            await engine.execute(
                "parent",
                "tasks.revise",
                {"id": task["id"], "revision": task["revision"], "title": "New parent decision"},
                "concurrent",
                now,
            )
            return {
                "kind": "commands",
                "commands": [{"action": "tasks.complete", "payload": {"id": task["id"]}}],
            }

    assistant = Assistant(engine, Cascade([ChangingProvider()], {}))
    with pytest.raises(DomainError, match="conflict"):
        await assistant.respond("parent", "Complete original task", "model", now)
    state = engine.snapshot()
    assert state["tasks"][task["id"]]["title"] == "New parent decision"
    assert state["tasks"][task["id"]]["status"] == "assigned"
    assert not state["proposals"]


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", [None, "", False, 0])
async def test_malformed_member_id_never_creates_a_new_identity(engine, store, now, identifier):
    before, writes = engine.snapshot(), store.calls
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner",
            "members.save",
            {"id": identifier, "name": "Invalid edit", "role": "adult"},
            "bad-identity",
            now,
        )
    assert engine.snapshot() == before and store.calls == writes


def test_boundary_does_not_overwrite_supplied_bad_revision_or_mutate_input(engine):
    payload = {"id": "T000001", "revision": None}
    before = deepcopy(payload)
    assert commands.with_record_revision("tasks.complete", payload, engine.view("parent")) == before
    assert payload == before
