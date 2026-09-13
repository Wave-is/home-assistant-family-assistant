"""Actual TelegramManager interpretation/outbox, synthetic transport only."""

import pytest

from tests.test_telegram_command_scope import NOW, fixture, update
from tests.test_telegram_command_scope import manager_module as manager_module  # noqa: F401


@pytest.mark.parametrize("group", [False, True])
async def test_manager_assignment_replay_and_buyer_listing(manager_module, group):
    engine, store, _entry, runtime, manager, client = fixture(manager_module)
    state = engine.snapshot()
    state["members"]["child"] = {
        "id": "child",
        "name": "Саша",
        "role": "child",
        "language": "ru",
        "active": True,
        "revision": 1,
        "aliases": [],
        "telegram_id": 102,
    }
    await engine.system_update(
        "synthetic_member", NOW, lambda ctx: ctx.state["members"].update(state["members"])
    )
    content = "поручи Саше купить 2 кг яблок"
    if group:
        content = "@synthetic_family_bot " + content
    request = update(text=content, group=group)
    await manager.process(request)
    await manager.process(request)
    rows = list(engine.snapshot()["shopping"].values())
    assert len(rows) == 1 and rows[0]["buyer"] == "child" and rows[0]["quantity"] == 2
    assert len(rows[0]["history"]) == 1 and not engine.snapshot()["tasks"]
    replies = [e for e in engine.snapshot()["outbox"].values() if e["key"] == "telegram_reply"]
    assert len(replies) == 1 and "Саша" in replies[0]["data"]["text"]
    assert replies[0]["data"]["chat_id"] == (-101 if group else 101)
    assert replies[0]["data"]["private_context"] is False
    await manager.process(update(11, text="/shopping Саша"))
    replies = [e for e in engine.snapshot()["outbox"].values() if e["key"] == "telegram_reply"]
    assert len(replies) == 2 and "яблок" in replies[-1]["data"]["text"]
    assert client.calls == []  # Queuing is not a claim of live Telegram delivery.


async def test_manager_stale_member_plan_does_not_adopt_new_buyer(manager_module):
    engine, store, _entry, runtime, manager, _client = fixture(manager_module)
    # The original interpretation was durably saved before an interrupted action.
    from custom_components.family_assistant.telegram.commands import signature

    content = "ask owner to buy bread"
    state = engine.snapshot()
    state["telegram"]["plans"] = {
        "tg:9001:10:action": {
            "signature": signature("owner", content, ()),
            "actor": "owner",
            "action": "shopping.add",
            "payload": {
                "name": "bread",
                "quantity": 1,
                "unit": "",
                "buyer": "owner",
                "buyer_revision": 1,
            },
            "created_at": NOW.isoformat(),
        }
    }
    state["members"]["owner"]["revision"] = 2

    def prepare(ctx):
        ctx.state["members"] = state["members"]
        ctx.state["telegram"]["plans"] = state["telegram"]["plans"]

    await engine.system_update("synthetic_interruption", NOW, prepare)
    await manager.process(update(text=content))
    assert not runtime.engine.snapshot()["shopping"]
