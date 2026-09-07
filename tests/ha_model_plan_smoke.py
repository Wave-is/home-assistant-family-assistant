"""Actual HA Store and authenticated confirmation for constrained model alarm plans."""

from copy import deepcopy
from datetime import UTC, datetime


async def verify_model_plans(hass, entry, owner, child_id):
    from custom_components.family_assistant.assistant import plans
    from custom_components.family_assistant.assistant.provider import Cascade
    from custom_components.family_assistant.assistant.service import Assistant

    request = "Поставь будильники по будням на 09:30, а по выходным на 10:30"
    wire = {
        "kind": "commands",
        "operations": [
            {
                "action": "alarms.save",
                "payload": {
                    "member": child_id,
                    "time": clock,
                    "days_expression": expression,
                    "timezone": "UTC",
                    # Never ring during this persistence/confirmation acceptance.
                    "enabled": False,
                },
            }
            for clock, expression in [("09:30", "по будням"), ("10:30", "по выходным")]
        ],
    }

    class Provider:
        calls = 0

        async def generate(self, messages, schema):
            self.calls += 1
            assert schema == plans.request_schema(request)
            assert "alarm_day_expressions" in messages[-1]["content"]
            return deepcopy(wire)

    engine = entry.runtime_data.engine
    before = deepcopy(engine.snapshot()["alarms"])
    provider = Provider()
    assistant = Assistant(engine, Cascade([provider], {}))
    await assistant.respond("owner", request, "ha-model-two-alarms", datetime.now(UTC))
    assert engine.snapshot()["alarms"] == before
    proposal = next(
        row
        for row in engine.snapshot()["proposals"].values()
        if row["operation_id"] == "ha-model-two-alarms"
    )
    assert "operations" not in proposal
    assert [c["payload"]["days"] for c in proposal["commands"]] == [[0, 1, 2, 3, 4], [5, 6]]
    await assistant.respond("owner", request, "ha-model-two-alarms", datetime.now(UTC))
    assert provider.calls == 1
    return {"proposal": deepcopy(proposal), "alarms": before}


async def verify_model_plan_reload(hass, entry, owner, expected):
    from ha_media_smoke import _command

    engine = entry.runtime_data.engine
    proposal = expected["proposal"]
    assert engine.snapshot()["proposals"][proposal["id"]] == proposal
    assert engine.snapshot()["alarms"] == expected["alarms"]
    result = await _command(
        hass, entry, owner, 971, "conversation.confirm", {"id": proposal["id"]}, "ha-model-confirm"
    )
    assert len(engine.snapshot()["alarms"]) == len(expected["alarms"]) + 2
    assert (
        await _command(
            hass,
            entry,
            owner,
            972,
            "conversation.confirm",
            {"id": proposal["id"]},
            "ha-model-confirm",
        )
        == result
    )
    assert len(engine.snapshot()["alarms"]) == len(expected["alarms"]) + 2
    assert engine.snapshot()["proposals"][proposal["id"]]["status"] == "applied"
    print(
        "PASS: actual HA wire plan normalization, atomic two-alarm preview, "
        "Store reload and authenticated confirmation/replay"
    )
