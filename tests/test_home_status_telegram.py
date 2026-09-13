"""Actual TelegramManager, Engine and Notifications descriptor contracts."""

# ruff: noqa: F811 -- imported pytest fixture intentionally shares argument names.

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_home_status import configured, observed
from test_telegram_command_scope import (
    BOT,
    NOW,
    fixture,
    manager_module,  # noqa: F401
    update,
)

from custom_components.family_assistant.home_status import config, delivery, observations
from custom_components.family_assistant.notifications import DeliveryError
from custom_components.family_assistant.telegram import context, messages


async def setup(manager_module, monkeypatch):
    engine, store, entry, runtime, manager, client = fixture(manager_module)
    await engine.system_update(
        "status-enable", NOW, lambda ctx: ctx.state["settings"]["modules"].append(config.MODULE)
    )
    entry.options[config.MODULE] = configured()
    calls, values = [], {"sensor.synthetic_power": observed(NOW, "2.567")}
    allowed = {"sensor.synthetic_power"}
    registry = {
        "sensor.synthetic_power": SimpleNamespace(
            entity_id="sensor.synthetic_power", id="registry-original"
        )
    }
    user = SimpleNamespace(
        id="owner-ha",
        is_active=True,
        permissions=SimpleNamespace(check_entity=lambda entity, policy: entity in allowed),
    )

    async def get_user(_user):
        return user

    def read(entity):
        calls.append(entity)
        return values.get(entity)

    manager.hass.auth = SimpleNamespace(async_get_user=get_user)
    manager.hass.states = SimpleNamespace(get=read)
    monkeypatch.setattr(
        observations, "ha_access", lambda _hass: (SimpleNamespace(async_get=registry.get), "read")
    )
    return engine, store, entry, runtime, manager, client, calls, values, allowed, user


def replies(engine):
    return [row for row in engine.snapshot()["outbox"].values() if row["key"] == "telegram_reply"]


async def test_request_retains_only_descriptor_late_reads_and_same_update_dedup(
    manager_module, monkeypatch
):
    engine, store, _, _, manager, client, calls, values, *_ = await setup(
        manager_module, monkeypatch
    )
    await manager.process(update(text="/home"))
    event = replies(engine)[0]
    assert calls == [] and client.calls == []
    assert event["data"]["text"] == "" and event["data"]["private_context"] is True
    assert set(event["data"]["home_status"]) == {"section", "group_id", "config_marker"}
    for canary in (
        "2.567",
        "Synthetic reading",
        "sensor.synthetic_power",
        "PRIVATE_URL_CANARY",
        "PRIVATE_TOKEN_CANARY",
    ):
        assert canary not in repr(store.value)
    values["sensor.synthetic_power"] = observed(NOW, "3.789")
    await manager.notifications.run(NOW)
    assert calls == ["sensor.synthetic_power"]
    assert len(client.calls) == 1 and "3789 W" in client.calls[0][1]["text"]
    assert "2567" not in client.calls[0][1]["text"]
    final = deepcopy(engine.snapshot())
    await manager.process(update(text="/home"))
    await manager.notifications.run(NOW)
    assert engine.snapshot() == final and len(client.calls) == 1
    assert "3789" not in repr(store.value)
    quoted = {
        "chat": {"id": 101},
        "reply_to_message": {
            "from": {"id": BOT["id"]},
            "message_id": 1,
            "text": client.calls[0][1]["text"],
        },
    }
    assert context.reply_quote(engine.snapshot(), quoted, BOT) == ""
    # Pure renderers have no HA identity or ACL evidence and must never render it.
    with pytest.raises(DeliveryError):
        messages.render(event, {"id": 101, "language": "en"}, engine.snapshot(), now=NOW)


@pytest.mark.parametrize(
    "change", ["options", "disabled", "actor_revision", "user_inactive", "expiry", "entry"]
)
async def test_queued_revocation_never_sends_or_reads_old_values(
    manager_module, monkeypatch, change
):
    engine, _, entry, _, manager, client, calls, _, _, user = await setup(
        manager_module, monkeypatch
    )
    await manager.process(update(text="/energy"))
    if change == "options":
        entry.options[config.MODULE]["revision"] += 1
    elif change == "user_inactive":
        user.is_active = False
    elif change == "expiry":
        monkeypatch.setattr(manager_module.dt_util, "utcnow", lambda: NOW + timedelta(minutes=6))
    elif change == "entry":
        manager.hass.config_entries.entry = None
    else:

        def revoke(ctx):
            if change == "disabled":
                ctx.state["settings"]["modules"].remove(config.MODULE)
            else:
                ctx.state["members"]["owner"]["revision"] += 1

        await engine.system_update("status-revoke", NOW, revoke)
    if change == "entry":
        manager.hass.config_entries.async_get_entry = lambda _id: None
    await manager.notifications.run(NOW)
    assert client.calls == [] and calls == []


async def test_acl_withdrawal_at_send_yields_no_label_or_state_read(manager_module, monkeypatch):
    engine, _, _, _, manager, client, calls, _, allowed, _ = await setup(
        manager_module, monkeypatch
    )
    await manager.process(update(text="/home"))
    allowed.clear()
    await manager.notifications.run(NOW)
    assert calls == []
    assert len(client.calls) == 1 and "No readable configured sources" in client.calls[0][1]["text"]
    assert "Synthetic reading" not in client.calls[0][1]["text"]
    assert len(replies(engine)) == 1


async def test_auth_await_options_drift_and_permission_recheck(manager_module, monkeypatch):
    _, _, entry, _, manager, client, calls, _, _, user = await setup(manager_module, monkeypatch)
    await manager.process(update(text="/home"))

    async def revoke(_id):
        entry.options[config.MODULE]["revision"] += 1
        return user

    manager.hass.auth.async_get_user = revoke
    await manager.notifications.run(NOW)
    assert client.calls == [] and calls == []


@pytest.mark.parametrize(
    ("text", "group"), [("/home", True), ("/status broken key", False), ("/energy extra", False)]
)
async def test_recognized_group_or_malformed_query_never_uses_llm(
    manager_module, monkeypatch, text, group
):
    engine, _, _, runtime, manager, client, calls, *_ = await setup(manager_module, monkeypatch)
    runtime.assistant = object()
    request = update(text=text, group=group)
    if group:
        request["message"]["text"] = text + "@" + BOT["username"]
    await manager.process(request)
    assert len(replies(engine)) == 1 and not engine.snapshot()["assistant_jobs"]
    assert calls == [] and client.calls == []
    assert "home_status" not in replies(engine)[0]["data"]


async def test_child_unknown_sender_and_unbound_ha_cannot_receive_values(
    manager_module, monkeypatch
):
    engine, _, _, runtime, manager, _, calls, *_ = await setup(manager_module, monkeypatch)
    runtime.assistant = object()
    request = update(text="/home")
    request["message"]["from"]["id"] = 999
    await manager.process(request)
    assert replies(engine) == [] and calls == []

    def child(ctx):
        ctx.state["members"]["owner"]["role"] = "child"
        ctx.state["members"]["owner"]["revision"] += 1

    await engine.system_update("status-child", NOW, child)
    await manager.process(update(11, text="/home"))
    assert "home_status" not in replies(engine)[0]["data"] and calls == []
    assert not engine.snapshot()["assistant_jobs"]


async def test_descriptor_lifetime_and_shape_are_strict(manager_module, monkeypatch):
    engine, _, _, _, manager, *_ = await setup(manager_module, monkeypatch)
    await manager.process(update(text="/home"))
    data = replies(engine)[0]["data"]
    assert delivery.current(engine.snapshot(), data, NOW)
    for changes in (
        {"expires_at": (NOW + timedelta(days=1)).isoformat()},
        {"actor_revision": True},
        {"private_context": False},
        {"chat_id": -101},
        {"text": "forbidden retained value"},
    ):
        assert not delivery.current(engine.snapshot(), {**data, **changes}, NOW)
