"""Private model rejection notes over authenticated native HA and actual Store."""

import json
from datetime import UTC, datetime


async def verify_semantic_feedback(hass, owner):
    from ha_digests_smoke import _execute, _view

    from custom_components.family_assistant.assistant.provider import Cascade
    from custom_components.family_assistant.assistant.service import Assistant
    from custom_components.family_assistant.domain.developer_diagnostics import build_report

    flow = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner.id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Synthetic private feedback",
            "owner_name": "Owner",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"conversation": True, "shopping": True}
    )
    entry = created["result"]
    await hass.async_block_till_done()
    child = await hass.auth.async_create_user("Synthetic private feedback child")
    try:
        await entry.runtime_data.scheduler.stop()
        engine = entry.runtime_data.engine
        result = await _execute(
            hass,
            entry,
            owner,
            1,
            "members.save",
            {
                "name": "Child",
                "role": "child",
                "language": "en",
                "ha_user_id": child.id,
            },
            "feedback-member",
        )
        assert result["success"], result
        actor = result["result"]["id"]

        class Provider:
            async def generate(self, *_args):
                return {
                    "kind": "commands",
                    "commands": [{"action": "shopping.add", "payload": {"name": "Synthetic milk"}}],
                }

        source = "PRIVATE_SOURCE_CANARY"
        assistant = Assistant(engine, Cascade([Provider()], {}))
        await assistant.respond(actor, source, "synthetic-feedback-model", datetime.now(UTC))
        proposal = next(iter(engine.snapshot()["proposals"].values()))
        payload = {
            "id": proposal["id"],
            "feedback": {
                "category": "wrong_target",
                "expected": "PRIVATE_EXPECTED_CANARY",
                "source": source,
            },
        }
        before = engine.snapshot()
        failed = await _execute(
            hass,
            entry,
            child,
            2,
            "conversation.reject",
            {
                **payload,
                "feedback": {**payload["feedback"], "source": "OTHER_SOURCE"},
            },
            "invalid-note",
        )
        assert not failed["success"] and failed["error"]["code"] == "invalid_field", failed
        assert engine.snapshot() == before
        result = await _execute(
            hass, entry, child, 3, "conversation.reject", payload, "native-note"
        )
        assert result["success"], result
        assert (
            await _execute(hass, entry, child, 4, "conversation.reject", payload, "native-note")
        )["result"] == result["result"]
        private = (await _view(hass, entry, child, 5))["result"]["semantic_feedback"]
        assert len(private["records"]) == 1 and private["records"][0]["source"] == source
        assert "PRIVATE_" not in json.dumps((await _view(hass, entry, owner, 6))["result"])
        assert "PRIVATE_" not in json.dumps(
            build_report(engine.snapshot(), version="0.1.0-alpha.29")
        )
        assert engine.snapshot()["shopping"] == before["shopping"]
        assert not engine.snapshot()["memory"].get("phrases")
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
        assert (await _view(hass, entry, child, 7))["result"]["semantic_feedback"] == private
        purge = {"id": result["result"]["feedback_id"], "confirmed": True}
        denied = await _execute(
            hass, entry, owner, 8, "conversation.feedback_purge", purge, "owner-denied"
        )
        assert not denied["success"] and denied["error"]["code"] == "forbidden", denied
        erased = await _execute(
            hass, entry, child, 9, "conversation.feedback_purge", purge, "child-purge"
        )
        assert erased["success"], erased
        assert not (await _view(hass, entry, child, 10))["result"]["semantic_feedback"]["records"]
        assert (
            entry.runtime_data.engine.snapshot()["proposals"][proposal["id"]]["status"]
            == "rejected"
        )
        print(
            "PASS: actual HA private proposal correction, exact source, child isolation, "
            "replay, Store reload and explicit scoped purge"
        )
    finally:
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.auth.async_remove_user(child)
