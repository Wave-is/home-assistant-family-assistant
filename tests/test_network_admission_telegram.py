"""Deterministic private network review reads and source-bound outbox revocation."""

import json
from copy import deepcopy
from datetime import timedelta

import pytest
from test_network_admission import CLIENT, PROTECTED, setup

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.admission import COPY, AdmissionReply
from custom_components.family_assistant.telegram.network import parsed
from custom_components.family_assistant.telegram.reply_delivery import current
from custom_components.family_assistant.telegram.router import route


async def prepared(engine, now, language="en"):
    await setup(engine, now)

    def seed(ctx):
        ctx.state["members"]["parent"].update(telegram_id=830001, language=language)
        ctx.state["telegram"]["group_id"] = -830099

    await engine.system_update("synthetic-private-parent", now, seed)
    return engine


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language,command",
    [
        ("en", "/unknown_devices"),
        ("ru", "покажи неизвестные устройства"),
        ("uk", "покажи невідомі пристрої"),
    ],
)
async def test_private_reply_has_bounded_inventory_but_group_reply_has_no_details(
    engine, now, language, command
):
    e = await prepared(engine, now, language)
    before = e.snapshot()
    private = await route(e, "parent", command, "read", now, private=True)
    assert isinstance(private, AdmissionReply)
    assert CLIENT in private and "198.51.100.10" in private and PROTECTED not in private
    assert COPY[language]["notice"] in private
    copied = deepcopy(private)
    assert copied.scope == private.scope and copied.scope is not private.scope
    group = await route(e, "parent", command, "group-read", now, private=False)
    assert group == COPY[language]["private"] and not isinstance(group, AdmissionReply)
    assert CLIENT not in group and "198.51.100.10" not in group
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["adult", "child", "guest"])
async def test_unknown_device_list_forbidden_to_nonparents(engine, now, role):
    e = await prepared(engine, now)
    before = e.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await route(e, role, "/unknown_devices", "read", now, private=True)
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "module",
        "role",
        "backend",
        "observation",
        "protection",
        "policy",
        "expired",
        "group",
        "boolean",
        "extra",
    ],
)
async def test_queued_reply_is_revoked_on_permission_or_source_drift(engine, now, change):
    e = await prepared(engine, now)
    reply = await route(e, "parent", "/unknown_devices", "read", now, private=True)
    event = {
        "recipient": "parent",
        "key": "telegram_reply",
        "data": {
            "text": str(reply),
            "private_context": True,
            "admission_context": reply.scope,
            "actor": "parent",
            "actor_revision": 1,
            "chat_id": 830001,
        },
    }
    event = json.loads(json.dumps(event))
    state = e.snapshot()
    assert current(event, state, now) is True
    at = now
    if change == "module":
        state["settings"]["modules"].remove("mikrotik")
    if change == "role":
        state["members"]["parent"]["role"] = "adult"
    if change == "backend":
        state["network"]["backend"] = "b" * 64
    if change == "observation":
        state["network"]["inventory"]["observed_at"] = (now - timedelta(seconds=1)).isoformat()
    if change == "protection":
        state["network"]["protected_macs"].append(CLIENT)
    if change == "policy":
        state["network"]["admission"] = {
            "revision": 1,
            "backend": "a" * 64,
            "entries": {},
            "updated_at": now.isoformat(),
        }
    if change == "expired":
        at += timedelta(minutes=2)
    if change == "group":
        event["data"]["chat_id"] = -830099
    if change == "boolean":
        event["data"]["admission_context"]["actor_revision"] = True
    if change == "extra":
        event["data"]["admission_context"]["extra"] = True
    assert current(event, state, at) is False


def test_parser_does_not_guess_negative_or_compound_requests(engine, now):
    for content in [
        "не показывай неизвестные устройства",
        "show unknown devices and block them",
        "/unknown_devices delete",
        "покажи неизвестные устройства и отключи их",
    ]:
        assert parsed(engine.snapshot(), content, now) is None
    for command in [
        "/неизвестные",
        "/невідомі",
        "SHOW UNKNOWN DEVICES?",
        "  покажи   невідомі пристрої  ",
    ]:
        assert parsed(engine.snapshot(), command, now) == ("read.network_admission", {})
    assert all(set(value) == set(COPY["en"]) for value in COPY.values())
