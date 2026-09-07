"""A persisted private model reply cannot cross an identity or expiry boundary."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram.messages import render, targets
from custom_components.family_assistant.telegram.reply_delivery import current


def envelope(engine, now):
    state = engine.snapshot()
    state["members"]["child"]["telegram_id"] = 1002
    state["telegram"]["group_id"] = -100
    event = {
        "key": "telegram_reply",
        "recipient": "child",
        "created_at": now.isoformat(),
        "data": {
            "actor": "child",
            "actor_revision": 1,
            "bot_id": 17,
            "chat_id": 1002,
            "text": "PRIVATE-MODEL-REPLY",
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
    }
    return state, event


@pytest.mark.parametrize("change", ["epoch", "inactive", "relink", "recipient", "expiry", "target"])
def test_new_reply_denied_at_last_render_boundary(engine, now, change):
    state, event = envelope(engine, now)
    target = targets(event, state)[0]
    if change == "epoch":
        state["members"]["child"]["revision"] += 1
    elif change == "inactive":
        state["members"]["child"]["active"] = False
    elif change == "relink":
        state["members"]["child"]["telegram_id"] = 2002
    elif change == "recipient":
        event["recipient"] = "sibling"
    elif change == "expiry":
        now += timedelta(minutes=5)
    else:
        target["id"] = -100
    with pytest.raises(DeliveryError, match="delivery_revoked"):
        render(event, target, state, now=now)


def test_valid_reply_and_legacy_envelope_compatibility(engine, now):
    state, event = envelope(engine, now)
    target = targets(event, state)[0]
    assert current(event, state, now)
    result = render(event, target, state, now=now)
    assert result["text"] == "PRIVATE-MODEL-REPLY" and result["chat_id"] == 1002
    legacy = deepcopy(event)
    del legacy["data"]["actor_revision"]
    del legacy["data"]["expires_at"]
    assert render(legacy, target, state, now=now)["text"] == result["text"]
