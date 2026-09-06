"""Routine adapter, authorization, notification and transition regression checks."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.routine_observations import collect
from custom_components.family_assistant.telegram.messages import render, targets
from custom_components.family_assistant.telegram.router import route
from custom_components.family_assistant.telegram.routines import COPY, callback


def enabled(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"].append("routines")
    return Engine(state, store.save)


async def setup_run(engine, now, **extra):
    item = await engine.execute(
        "parent",
        "routines.save",
        {
            "title": "Synthetic routine",
            "assignees": ["child"],
            "steps": [{"title": "First"}, {"title": "Second"}],
            **extra,
        },
        "routine-save",
        now,
    )
    return await engine.execute(
        "child",
        "routines.start",
        {
            "id": item["id"],
            "revision": item["revision"],
            "member": "child",
        },
        "routine-start",
        now,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "ru", "uk"])
async def test_telegram_private_commands_and_bound_callbacks(engine, store, now, language):
    engine = enabled(engine, store)
    await engine.system_update(
        "test_language", now, lambda ctx: ctx.state["members"]["parent"].update(language=language)
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "parent", "/routine morning | Child", "group-save", now)
    assert engine.snapshot() == before
    result = await route(
        engine, "parent", "/routine morning | Child", "private-save", now, private=True
    )
    assert "U000001" in result
    assert (
        await route(engine, "parent", "/routine morning | Child", "private-save", now, private=True)
        == result
    )
    result = await route(
        engine, "child", "/routinestart U000001 | Child", "tg-start", now, private=True
    )
    assert "J000001" in result
    assert (
        await route(engine, "parent", "/routines", "tg-list-group", now)
        == COPY[language]["private"]
    )
    assert "J000001" in await route(engine, "child", "/routines", "tg-list-self", now, private=True)
    assert "J000001" not in await route(
        engine, "sibling", "/routines", "tg-list-sibling", now, private=True
    )
    state = engine.snapshot()
    event = next(e for e in state["outbox"].values() if e["key"] == "routine_step")
    message = render(event, {"id": 12345, "language": language}, state)
    encoded = message["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert len(encoded.encode()) <= 64
    payload = callback(encoded)
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("sibling", "routines.confirm", payload, "other-confirm", now)
    result = await engine.execute("child", "routines.confirm", payload, "own-confirm", now)
    assert result["steps"][0]["status"] == "completed"
    assert result["steps"][1]["status"] == "active"
    assert result["steps"][1]["nonce"] != payload["nonce"]
    assert await engine.execute("child", "routines.confirm", payload, "own-confirm", now) == result
    with pytest.raises(DomainError):
        await engine.execute("child", "routines.confirm", payload, "old-confirm", now)


def test_observation_adapter_does_not_read_disabled_or_unapproved_entities(engine, now):
    state = engine.snapshot()
    state["settings"]["routines"] = {"entity_allowlist": ["sensor.example", "sensor.missing"]}
    calls = []

    def read(entity_id):
        calls.append(entity_id)
        if entity_id == "sensor.missing":
            return None
        return SimpleNamespace(
            state="on",
            last_reported=now,
            last_updated=now - timedelta(days=1),
            last_changed=now - timedelta(days=2),
        )

    assert collect(state, read) == {} and calls == []
    state["settings"]["modules"].append("routines")
    assert collect(state, read) == {"sensor.example": {"state": "on", "observed_at": now}}
    assert calls == ["sensor.example", "sensor.missing"]
    assert (
        collect(state, lambda _: SimpleNamespace(state="on", last_updated=now))["sensor.example"][
            "observed_at"
        ]
        == now
    )
    assert (
        collect(state, lambda _: SimpleNamespace(state="on"))["sensor.example"]["observed_at"]
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [[], {}, True, 1, "bad"])
async def test_malformed_confirmation_is_domain_error_and_atomic(engine, store, now, value):
    engine = enabled(engine, store)
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await setup_run(engine, now, steps=[{"title": "Test", "confirmation": value}])
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_restarted_tick_keeps_nonce_and_store_failure_does_not_lose_confirmation(
    engine, store, now
):
    engine = enabled(engine, store)
    run = await setup_run(engine, now)
    engine = Engine(store.value, store.save)
    before = engine.snapshot()
    assert not await engine.tick(now + timedelta(seconds=1))
    assert before == engine.snapshot()
    payload = {
        "id": run["id"],
        "revision": run["revision"],
        "step": 0,
        "nonce": run["steps"][0]["nonce"],
    }
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("child", "routines.confirm", payload, "disk-confirm", now)
    assert engine.snapshot() == before
    store.fail = False
    result = await engine.execute("child", "routines.confirm", payload, "disk-confirm", now)
    assert result["steps"][1]["status"] == "active"


@pytest.mark.asyncio
async def test_each_step_escalation_starts_at_activation_not_planned_start(engine, store, now):
    engine = enabled(engine, store)
    run = await setup_run(engine, now)
    later = now + timedelta(hours=1)
    await engine.tick(later)
    result = await engine.execute(
        "child",
        "routines.confirm",
        {
            "id": run["id"],
            "revision": run["revision"],
            "step": 0,
            "nonce": run["steps"][0]["nonce"],
        },
        "late-confirm",
        later,
    )
    assert result["steps"][1]["activated_at"] == later.isoformat()
    assert not await engine.tick(later + timedelta(minutes=14))
    await engine.tick(later + timedelta(minutes=15))
    alerts = [e for e in engine.snapshot()["outbox"].values() if e["key"] == "routine_overdue"]
    assert [e["data"]["step"] for e in alerts] == [0, 1]
    assert all(e["recipient"] == "parents" for e in alerts)
    state = engine.snapshot()
    state["telegram"]["group_id"] = -1234
    state["members"]["parent"]["telegram_id"] = 2345
    assert [t["id"] for t in targets(alerts[1], state)] == [2345]


@pytest.mark.asyncio
async def test_revoked_template_creator_cancels_and_cannot_start_new_runs(engine, store, now):
    engine = enabled(engine, store)
    run = await setup_run(engine, now)
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "name": "Parent",
            "role": "adult",
        },
        "demote-creator",
        now,
    )
    assert engine.snapshot()["routine_runs"][run["id"]]["status"] == "cancelled"
    with pytest.raises(DomainError):
        await engine.execute(
            "child",
            "routines.start",
            {
                "id": "U000001",
                "revision": 1,
                "member": "child",
            },
            "start-demoted",
            now,
        )


def test_callback_parser_rejects_unbounded_and_malformed_tokens():
    for value in (
        "fr:J000001:0:1:short",
        "fr:J000001:-1:1:" + "x" * 24,
        "fr:J000001:0:true:" + "x" * 24,
        "fr:J000001:0:1:" + "x" * 500,
    ):
        with pytest.raises(DomainError):
            callback(value)


@pytest.mark.asyncio
async def test_unicode_nonce_is_rejected_without_unhandled_type_error(engine, store, now):
    engine = enabled(engine, store)
    run = await setup_run(engine, now)
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "child",
            "routines.confirm",
            {
                "id": run["id"],
                "revision": run["revision"],
                "step": 0,
                "nonce": "🔑",
            },
            "unicode-nonce",
            now,
        )
