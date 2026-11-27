"""Engine transaction, replay, rollback and Telegram scope acceptance."""

import pytest

from custom_components.family_assistant.domain import academy, academy_curriculum
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.academy import reply_current, route


@pytest.fixture
def academy_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"].append("academy")
    return Engine(state, store.save)


@pytest.mark.asyncio
async def test_engine_replay_and_store_failure(academy_engine, store, now):
    engine = academy_engine
    assignment = {"member": "child", "member_revision": 1, "grade": 7, "language": "en"}
    receipt = await engine.execute("parent", "academy.assign", assignment, "assign", now)
    key = receipt["id"]
    _, answer = academy_curriculum.question("powers", key, 0, "en")
    payload = {"id": key, "revision": 1, "topic": "powers", "answer": str(answer)}
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("child", "academy.answer", payload, "answer", now)
    assert engine.snapshot() == before
    store.fail = False
    result = await engine.execute("child", "academy.answer", payload, "answer", now)
    restarted = Engine(store.value, store.save)
    assert await restarted.execute("child", "academy.answer", payload, "answer", now) == result
    state = restarted.snapshot()
    assert state["academy"][key]["sequence"] == 1
    assert "academy" not in restarted.view("child", now=now)
    assert "answer" not in state["processed"]["answer"]["result"]
    with pytest.raises(DomainError, match="forbidden"):
        await restarted.execute("sibling", "academy.answer", payload, "sibling", now)
    state["members"]["child"]["revision"] += 1
    revoked = Engine(state, store.save)
    with pytest.raises(DomainError, match="forbidden"):
        await revoked.execute("child", "academy.answer", payload, "answer", now)


@pytest.mark.asyncio
async def test_private_telegram_reply_revoked_on_archive(academy_engine, now):
    engine = academy_engine
    receipt = await engine.execute(
        "parent", "academy.assign",
        {"member": "child", "member_revision": 1, "grade": 6, "language": "uk"},
        "assign", now,
    )
    response = await route(
        engine, "child", "/academy", "read", now, private=True, language="uk"
    )
    assert receipt["id"] in response
    data = {"actor": "child", "academy_context": response.academy_scope}
    assert reply_current(engine.snapshot(), data, now)
    group = await route(
        engine, "child", "/academy", "group", now, private=False, language="uk"
    )
    assert receipt["id"] not in group
    await engine.execute("parent", "academy.archive", receipt, "archive", now)
    assert not reply_current(engine.snapshot(), data, now)
    state = engine.snapshot()
    assert not academy.project(state, state["members"]["child"], now)["assignments"]
