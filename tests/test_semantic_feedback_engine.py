"""Real proposal -> private note transactions, transport, reload and privacy boundaries."""

import json
from datetime import timedelta

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.developer_diagnostics import build_report
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.router import route

SOURCE = "  PRIVATE_ORIGINAL_CANARY\n"
EXPECTED = "PRIVATE_EXPECTED_CANARY: different shopping item"


async def proposal(engine, now, actor="parent", operation="proposal-one"):
    settings = engine.snapshot()["settings"]
    if "conversation" not in settings["modules"]:
        await engine.execute(
            "owner",
            "settings.save",
            {**settings, "modules": [*settings["modules"], "conversation"]},
            "enable-feedback",
            now,
        )

    class Provider:
        async def generate(self, *_args):
            return {
                "kind": "commands",
                "commands": [{"action": "shopping.add", "payload": {"name": "Synthetic item"}}],
            }

    assistant = Assistant(engine, Cascade([Provider()], {}))
    await assistant.respond(actor, SOURCE, operation, now)
    return next(
        p for p in engine.snapshot()["proposals"].values() if p["operation_id"] == operation
    )


def feedback(row, **extra):
    return {
        "id": row["id"],
        "feedback": {
            "category": "wrong_action",
            "expected": EXPECTED,
            "source": SOURCE,
            **extra,
        },
    }


@pytest.mark.asyncio
async def test_atomic_failure_exact_retry_reload_no_action_or_learning(engine, store, now):
    row = await proposal(engine, now)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("parent", "conversation.reject", feedback(row), "note", now)
    assert engine.snapshot() == before
    store.fail = False
    result = await engine.execute("parent", "conversation.reject", feedback(row), "note", now)
    restarted = Engine(store.value, store.save)
    assert (
        await restarted.execute("parent", "conversation.reject", feedback(row), "note", now)
        == result
    )
    state = restarted.snapshot()
    assert state["shopping"] == before["shopping"]
    assert not state["memory"].get("phrases")
    assert state["proposals"][row["id"]]["status"] == "rejected"
    notes = restarted.view("parent")["semantic_feedback"]["records"]
    assert len(notes) == 1 and notes[0]["id"] == result["feedback_id"]
    assert notes[0]["source"] == SOURCE and notes[0]["expected"] == EXPECTED
    assert EXPECTED not in json.dumps(state["processed"])
    assert EXPECTED not in json.dumps(state["audit"])
    assert EXPECTED not in json.dumps(state["telegram"])
    for actor in ("owner", "child", "adult", "guest", "sibling"):
        assert EXPECTED not in json.dumps(restarted.view(actor))
    assert EXPECTED not in json.dumps(plans.projection(restarted.view("parent")))
    assert EXPECTED not in json.dumps(build_report(state, version="0.1.0-alpha.29"))


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "parent", "adult", "child"])
async def test_private_projection_has_no_parent_or_owner_bypass(engine, now, actor):
    row = await proposal(engine, now, actor)
    await engine.execute(actor, "conversation.reject", feedback(row), "note", now)
    for other in ("owner", "parent", "adult", "child", "sibling", "guest"):
        notes = engine.view(other)["semantic_feedback"]["records"]
        assert bool(notes) is (other == actor)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["feedback"].update(source=SOURCE.strip()),
        lambda p: p["feedback"].update(source="OTHER_PRIVATE_CANARY"),
        lambda p: p["feedback"].update(category=[]),
        lambda p: p["feedback"].update(expected=""),
        lambda p: p["feedback"].update(commands=[]),
    ],
)
async def test_invalid_feedback_neither_rejects_nor_changes_any_state(engine, now, mutate):
    row = await proposal(engine, now)
    payload = feedback(row)
    mutate(payload)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute("parent", "conversation.reject", payload, "note", now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_capacity_can_cancel_without_note_and_never_evicts(engine, now, monkeypatch):
    from custom_components.family_assistant.domain import semantic_feedback

    row = await proposal(engine, now)
    monkeypatch.setattr(semantic_feedback, "MAX_ACTIVE_RECORDS", 0)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="capacity_reached"):
        await engine.execute("parent", "conversation.reject", feedback(row), "note", now)
    assert engine.snapshot() == before
    await engine.execute("parent", "conversation.reject", {"id": row["id"]}, "cancel", now)
    assert not engine.snapshot()["memory"].get("semantic_feedback")


@pytest.mark.asyncio
async def test_confirm_cannot_smuggle_feedback_and_expired_cannot_reject(engine, now):
    row = await proposal(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute("parent", "conversation.confirm", feedback(row), "confirm", now)
    with pytest.raises(DomainError, match="proposal_expired"):
        await engine.execute(
            "parent", "conversation.reject", feedback(row), "expired", now + timedelta(minutes=5)
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_purge_requires_same_identity_and_never_resurrects(engine, store, now):
    row = await proposal(engine, now, "child")
    result = await engine.execute("child", "conversation.reject", feedback(row), "note", now)
    payload = {"id": result["feedback_id"], "confirmed": True}
    before = engine.snapshot()
    for actor in ("owner", "parent", "adult", "sibling"):
        with pytest.raises(DomainError, match="forbidden"):
            await engine.execute(
                actor, "conversation.feedback_purge", payload, actor + "-purge", now
            )
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "child", "conversation.feedback_purge", {**payload, "confirmed": 1}, "unconfirmed", now
        )
    assert engine.snapshot() == before
    purged = await engine.execute("child", "conversation.feedback_purge", payload, "purge", now)
    restarted = Engine(store.value, store.save)
    assert (
        await restarted.execute("child", "conversation.feedback_purge", payload, "purge", now)
        == purged
    )
    assert restarted.snapshot()["proposals"] == before["proposals"]
    assert not restarted.view("child")["semantic_feedback"]["records"]
    with pytest.raises(DomainError, match="conflict"):
        await restarted.execute("child", "conversation.reject", feedback(row), "note", now)
    changed = restarted.snapshot()
    changed["members"]["child"]["revision"] += 1
    with pytest.raises(DomainError, match="forbidden"):
        await Engine(changed, store.save).execute(
            "child", "conversation.feedback_purge", payload, "purge", now
        )


@pytest.mark.asyncio
async def test_telegram_private_only_exact_commit_without_raw_plan_copy(engine, now):
    row = await proposal(engine, now)
    content = f"/feedback {row['id']} | wrong_target | {EXPECTED}"
    before = engine.snapshot()
    reply = await route(engine, "parent", content, "group-note", now)
    assert "private chat" in reply
    assert engine.snapshot() == before
    reply = await route(engine, "parent", content, "note", now, private=True)
    assert "private note was saved" in reply and EXPECTED not in reply
    state = engine.snapshot()
    assert EXPECTED not in json.dumps(state["telegram"])
    assert await route(engine, "parent", content, "note", now, private=True) == reply
    assert engine.snapshot() == state
    notes = engine.view("parent")["semantic_feedback"]["records"]
    assert len(notes) == 1 and not notes[0]["source_available"] and notes[0]["source"] == ""
    assert state["shopping"] == before["shopping"]


@pytest.mark.parametrize("action", ["conversation.reject", "conversation.feedback_purge"])
def test_model_cannot_submit_feedback_as_a_tool(action):
    with pytest.raises(DomainError, match="provider_bad_response"):
        plans.validate({"kind": "commands", "commands": [{"action": action, "payload": {}}]})
