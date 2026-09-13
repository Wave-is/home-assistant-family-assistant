"""Synthetic end-to-end repair, durable learning, and zero-effect failure cases."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.router import route
from tests.test_assistant import Provider, enable


async def setup(engine, store, now, name="Alex"):
    await enable(engine, now)
    state = engine.snapshot()
    state["members"]["child"]["name"] = name
    return Engine(state, store.save)


def model_for(title="Buy bread", **extra):
    return Provider(
        {
            "kind": "commands",
            "operations": [
                {
                    "action": "tasks.create",
                    "payload": {"assignee": "child", "title": title, **extra},
                }
            ],
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,first,second",
    [
        ("Alex", "assign task Alxe - Buy bread", "assign task Alxe - Wash dishes"),
        ("Роман", "поставь задачу Ропану - Buy bread", "поставь задачу Ропана — Wash dishes"),
        ("Роман", "постав завдання Ропану — Buy bread", "Ропан завдання Wash dishes"),
    ],
)
async def test_repairs_once_then_different_task_works_offline_after_restart(
    engine, store, now, name, first, second
):
    engine = await setup(engine, store, now, name)
    before_members = engine.snapshot()["members"]
    provider = model_for()
    assistant = Assistant(engine, Cascade([provider], {}))
    reply = await route(engine, "parent", first, "typo-first", now, fallback=assistant.respond)
    assert "L000001" in reply and name in reply
    assert len(provider.calls) == 1
    assert len(engine.snapshot()["tasks"]) == 1
    assert not engine.snapshot()["proposals"]
    assert engine.snapshot()["members"] == before_members  # No identity/permission rewriting.
    row = engine.view("parent")["learned_phrases"][0]
    assert row["kind"] == "member_alias" and row["effective"]
    assert not engine.view("child")["learned_phrases"]
    restarted = Engine(engine.snapshot(), store.save)
    assert "Wash dishes" in await route(restarted, "parent", second, "typo-second", now)
    assert len(restarted.snapshot()["tasks"]) == 2
    assert len(restarted.view("parent")["learned_phrases"]) == 1
    assert "L000001" in await route(restarted, "parent", first, "typo-first", now)
    assert len(restarted.snapshot()["tasks"]) == 2
    replay = Assistant(restarted, Cascade([Provider()], {}))
    assert "L000001" in await replay.respond("parent", first, "typo-first", now)


@pytest.mark.asyncio
async def test_preserves_receipt_refs_for_replay(engine, store, now):
    engine = await setup(engine, store, now)
    assistant = Assistant(engine, Cascade([model_for()], {}))
    message = "Alxe task Buy bread"
    await route(engine, "parent", message, "refs", now, ("T123456",), fallback=assistant.respond)
    await route(engine, "parent", message, "refs", now, ("T123456",))
    assert len(engine.snapshot()["tasks"]) == 1
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await route(engine, "parent", message, "refs", now)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"title": "Something else"},
        {"report_type": "photo"},
        {"penalty": -1},
        {"due_expression": "tomorrow"},
        {"assignee": "sibling"},
    ],
)
async def test_model_cannot_autorun_extra_or_changed_payload(engine, store, now, change):
    engine = await setup(engine, store, now)
    change = dict(change)
    title = change.pop("title", "Buy bread")
    provider = model_for(title, **change)
    assistant = Assistant(engine, Cascade([provider], {}))
    content = "Alxe task Buy bread"
    if "due_expression" in change:
        with pytest.raises(DomainError, match="invalid_deadline"):
            await assistant.respond("parent", content, "extra", now)
    else:
        reply = await assistant.respond("parent", content, "extra", now)
        assert "/confirm" in reply
    assert not engine.snapshot()["tasks"]
    assert not engine.view("parent")["learned_phrases"]


@pytest.mark.asyncio
async def test_ambiguous_one_edit_candidate_stays_reviewed(engine, store, now):
    engine = await setup(engine, store, now)
    state = engine.snapshot()
    state["members"]["sibling"]["name"] = "Alce"
    engine = Engine(state, store.save)
    assistant = Assistant(engine, Cascade([model_for()], {}))
    assert "/confirm" in await assistant.respond("parent", "Alxe task Buy bread", "ambiguous", now)
    assert not engine.snapshot()["tasks"] and not engine.snapshot()["memory"].get("phrases")


@pytest.mark.asyncio
async def test_forget_blocks_automatic_relearning_and_never_shadows_other_names(engine, store, now):
    engine = await setup(engine, store, now)
    assistant = Assistant(
        engine, Cascade([Provider(*model_for().responses, *model_for().responses)], {})
    )
    await route(engine, "parent", "Alxe task Buy bread", "learn", now, fallback=assistant.respond)
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/forgetphrase L000001", "cross-forget", now)
    await route(engine, "parent", "/forgetphrase L000001", "forget", now)
    with pytest.raises(DomainError, match="unknown_member"):
        await route(engine, "parent", "Alxe task Wash dishes", "offline-forgotten", now)
    assert "/confirm" in await route(
        engine, "parent", "Alxe task Buy bread", "try-learn-again", now, fallback=assistant.respond
    )
    assert not engine.view("parent")["learned_phrases"][0]["active"]
    assert len(engine.snapshot()["tasks"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["parent", "child"])
async def test_identity_epoch_change_invalidates_rule_and_old_receipt(engine, store, now, target):
    engine = await setup(engine, store, now)
    assistant = Assistant(engine, Cascade([model_for()], {}))
    await route(engine, "parent", "Alxe task Buy bread", "learn", now, fallback=assistant.respond)
    member = engine.snapshot()["members"][target]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": target,
            "revision": member["revision"],
            "name": member["name"],
            "role": member["role"],
        },
        "identity-change",
        now,
    )
    assert not engine.view("parent")["learned_phrases"][0]["effective"]
    with pytest.raises(DomainError, match="unknown_member"):
        await route(engine, "parent", "Alxe task Wash dishes", "after-change", now)
    with pytest.raises(DomainError, match="conflict"):
        await route(engine, "parent", "Alxe task Buy bread", "learn", now)


@pytest.mark.asyncio
async def test_model_inflight_member_change_cannot_autorun(engine, store, now):
    engine = await setup(engine, store, now)

    class ChangingProvider(Provider):
        async def generate(self, messages, schema):
            member = engine.snapshot()["members"]["child"]
            await engine.execute(
                "owner",
                "members.save",
                {
                    "id": "child",
                    "revision": member["revision"],
                    "name": "Alex",
                    "role": "child",
                },
                "during-provider",
                now,
            )
            return await super().generate(messages, schema)

    provider = ChangingProvider(*model_for().responses)
    assistant = Assistant(engine, Cascade([provider], {}))
    # A stale provider view cannot silently bind a fresh target incarnation.
    with pytest.raises(DomainError, match="conflict"):
        await assistant.respond("parent", "Alxe task Buy bread", "inflight", now)
    assert not engine.snapshot()["tasks"]


@pytest.mark.asyncio
async def test_failed_atomic_commit_learns_nothing_and_exact_retry_works(engine, store, now):
    engine = await setup(engine, store, now)
    assistant = Assistant(engine, Cascade([model_for()], {}))
    original_save = store.save

    async def fail_repair_commit(state):
        if state["tasks"]:
            raise OSError("synthetic write failure")
        await original_save(state)

    failing = Engine(engine.snapshot(), fail_repair_commit)
    assistant.engine = failing
    with pytest.raises(OSError):
        await route(
            failing, "parent", "Alxe task Buy bread", "write-fail", now, fallback=assistant.respond
        )
    assert not failing.snapshot()["tasks"] and not failing.snapshot()["memory"].get("phrases")
    assert "write-fail" in failing.snapshot()["telegram"]["plans"]
    recovered = Engine(failing.snapshot(), store.save)
    await route(recovered, "parent", "Alxe task Buy bread", "write-fail", now)
    assert (
        len(recovered.snapshot()["tasks"]) == len(recovered.view("parent")["learned_phrases"]) == 1
    )


@pytest.mark.asyncio
async def test_dialogue_and_quotes_do_not_learn_or_execute(engine, store, now):
    engine = await setup(engine, store, now)
    provider = Provider({"kind": "answer", "text": "A pleasant conversation."})
    assistant = Assistant(engine, Cascade([provider], {}))
    reply = await route(engine, "parent", "How are you?", "chat", now, fallback=assistant.respond)
    assert "pleasant conversation" in reply
    assert not engine.snapshot()["tasks"] and not engine.snapshot()["memory"].get("phrases")


@pytest.mark.asyncio
async def test_learned_recipient_preserves_title_deadline_and_is_not_global_replace(
    engine, store, now
):
    engine = await setup(engine, store, now)
    assistant = Assistant(engine, Cascade([model_for()], {}))
    await route(engine, "parent", "Alxe task Buy bread", "learn", now, fallback=assistant.respond)
    await route(
        engine,
        "parent",
        "Alxe task Meet Alxe, deadline tomorrow",
        "tomorrow",
        now + timedelta(days=1),
    )
    task = list(engine.snapshot()["tasks"].values())[-1]
    assert task["title"] == "Meet Alxe" and task["due_at"].startswith("2026-09-08")
    with pytest.raises(DomainError, match="unknown_member"):
        await route(engine, "owner", "Alxe task Buy bread", "other-parent", now)
    before = deepcopy(engine.snapshot()["tasks"])
    assert "haven't understood" in await route(
        engine, "parent", "Don't give Alxe a task", "negative", now
    )
    assert engine.snapshot()["tasks"] == before
