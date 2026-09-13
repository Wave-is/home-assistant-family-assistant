"""School privacy and rc.5 image/provider paths share the actual Telegram adapter."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_online_school_messages import connected_school as connected_school
from test_telegram_command_scope import BOT, NOW, fixture, update
from test_telegram_command_scope import manager_module as manager_module

from custom_components.family_assistant.assistant.chat_service import conversation_digest
from custom_components.family_assistant.telegram.context import reply_quote
from custom_components.family_assistant.telegram.reply_delivery import current
from custom_components.family_assistant.telegram.router import route


async def test_manager_keeps_school_queries_private_with_text_and_image_providers_enabled(
    connected_school, manager_module
):
    engine, _store, entry, runtime, manager, _client = fixture(manager_module)
    state = connected_school.snapshot()
    state["settings"]["modules"].append("conversation")
    state["members"]["owner"]["telegram_id"] = 101
    state["telegram"]["group_id"] = -101
    await engine.system_update(
        "synthetic-school-bindings", NOW, lambda ctx: ctx.state.update(state)
    )
    runtime.assistant = SimpleNamespace(cascade=object())
    runtime.assistant_config_digest = conversation_digest(entry.options["conversation"])

    async def forbidden_image(*args, **kwargs):
        pytest.fail("Reading school facts must not invoke image generation")

    runtime.image_generation = SimpleNamespace(config={"enabled": True}, enqueue=forbidden_image)
    await manager.process(update(text="/homework Child today"))
    result = next(iter(engine.snapshot()["outbox"].values()))
    assert "child private assignment" in result["data"]["text"]
    assert result["data"]["private_context"] is True and result["data"]["school_context"]
    assert not engine.snapshot()["assistant_jobs"]
    assert current(result, engine.snapshot(), NOW)

    # Match a real retained delivery receipt, then reply with an ordinary prompt.
    def delivered(ctx):
        ctx.state["outbox"][result["id"]]["deliveries"] = {
            "synthetic-receipt": {
                "target": {"channel": "telegram", "bot_id": BOT["id"], "id": 101},
                "receipt": "77",
            }
        }

    await engine.system_update("synthetic-delivery", NOW, delivered)
    incoming = update(11, text="Explain this in simple words")
    incoming["message"]["reply_to_message"] = {
        "message_id": 77,
        "from": {"id": BOT["id"]},
        "text": str(result["data"]["text"]),
    }
    assert reply_quote(engine.snapshot(), incoming["message"], BOT) == ""
    await manager.process(incoming)
    job = next(iter(engine.snapshot()["assistant_jobs"].values()))
    assert "private assignment" not in repr(job) and "school.example" not in repr(job)

    await manager.process(update(12, group=True, text="/grades Child"))
    group = list(engine.snapshot()["outbox"].values())[-1]
    assert group["data"]["chat_id"] == -101 and "private chat" in group["data"]["text"]
    assert "private mark" not in group["data"]["text"]


@pytest.mark.parametrize("kind", ["school", "image", "both"])
@pytest.mark.parametrize("revoked", ["school", "image", "actor"])
async def test_shared_reply_guard_preserves_independent_school_image_and_identity_fences(
    connected_school, now, kind, revoked
):
    response = await route(connected_school, "child", "/homework", "query", now, private=True)
    state = connected_school.snapshot()
    state["settings"]["modules"].append("conversation")
    state["members"]["child"]["telegram_id"] = 1002
    data = {
        "actor": "child",
        "actor_revision": 1,
        "bot_id": 17,
        "chat_id": 1002,
        "private_context": True,
    }
    if kind in {"school", "both"}:
        data["school_context"] = deepcopy(response.school_scope)
    if kind in {"image", "both"}:
        data.update(image_job_id="synthetic-image", image_provider_scope="image-scope")
    state["image_jobs"] = {
        "synthetic-image": {
            "status": "failed",
            "actor": "child",
            "actor_revision": 1,
            "provider_scope": "image-scope",
            "chat_id": 1002,
            "bot_id": 17,
        }
    }
    event = {"key": "telegram_reply", "recipient": "child", "data": data}
    assert current(event, state, now)
    if revoked == "school":
        source = state["school"]["online"]["sources"][response.school_scope[0]["id"]]
        source["generation"] = "replacement-source"
    elif revoked == "image":
        state["image_jobs"]["synthetic-image"]["provider_scope"] = "replacement-images"
    else:
        state["members"]["child"]["revision"] += 1
    assert current(event, state, now) is (revoked not in {kind, "actor"} and kind != "both")
