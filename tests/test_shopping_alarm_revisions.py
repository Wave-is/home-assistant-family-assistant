"""Strict optimistic-revision contracts for shopping items and alarm schedules."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.validation import DomainError

INVALID_REVISIONS = [None, True, False, 1.0, "1", 0, -1, 2**53]


async def shopping_item(engine, now, action):
    actor = "child" if action in {"approve", "reject", "archive"} else "parent"
    return await engine.execute(
        actor,
        "shopping.add",
        {"name": f"Revision item {action}", "quantity": 2, "unit": "piece"},
        f"add-{action}",
        now,
    )


def shopping_payload(action, item, revision_marker=...):
    payload = {"id": item["id"]}
    if revision_marker is not ...:
        payload["revision"] = revision_marker
    if action == "purchase":
        payload["quantity"] = 1
    return payload


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve", "reject", "archive", "purchase"])
async def test_shopping_mutations_require_strict_revision_without_writes(
    engine, store, now, action
):
    item = await shopping_item(engine, now, action)
    actor = "parent"

    for index, candidate in enumerate([..., *INVALID_REVISIONS]):
        before = engine.snapshot()
        writes = store.calls
        with pytest.raises(DomainError) as caught:
            await engine.execute(
                actor,
                f"shopping.{action}",
                shopping_payload(action, item, candidate),
                f"invalid-{action}-{index}",
                now,
            )
        assert caught.value.code == "invalid_field"
        assert caught.value.field == "revision"
        assert engine.snapshot() == before
        assert store.calls == writes


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve", "reject", "archive", "purchase"])
async def test_shopping_stale_revision_conflicts_and_current_revision_succeeds(engine, now, action):
    item = await shopping_item(engine, now, action)
    before = engine.snapshot()
    with pytest.raises(DomainError) as caught:
        await engine.execute(
            "parent",
            f"shopping.{action}",
            shopping_payload(action, item, item["revision"] + 1),
            f"stale-{action}",
            now,
        )
    assert caught.value.code == "conflict"
    assert engine.snapshot() == before

    changed = await engine.execute(
        "parent",
        f"shopping.{action}",
        shopping_payload(action, item, item["revision"]),
        f"current-{action}",
        now,
    )
    assert changed["revision"] == item["revision"] + 1


async def alarm_schedule(engine, now, operation="new-alarm"):
    return await engine.execute(
        "owner",
        "alarms.save",
        {
            "member": "child",
            "name": "Revision alarm",
            "time": "08:00",
            "days": list(range(7)),
            "timezone": "UTC",
            "profile": "strict",
        },
        operation,
        now,
    )


def alarm_edit_payload(alarm, revision_marker=...):
    payload = {
        "id": alarm["id"],
        "member": alarm["member"],
        "name": "Edited alarm",
        "time": alarm["time"],
        "days": alarm["days"],
        "timezone": alarm["timezone"],
        "profile": alarm["profile"],
    }
    if revision_marker is not ...:
        payload["revision"] = revision_marker
    return payload


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["save", "enable"])
async def test_existing_alarm_mutations_require_strict_revision_without_writes(
    engine, store, now, command
):
    alarm = await alarm_schedule(engine, now, f"new-for-{command}")
    for index, candidate in enumerate([..., *INVALID_REVISIONS]):
        payload = (
            alarm_edit_payload(alarm, candidate)
            if command == "save"
            else {
                "id": alarm["id"],
                "enabled": False,
                **({} if candidate is ... else {"revision": candidate}),
            }
        )
        before = engine.snapshot()
        writes = store.calls
        with pytest.raises(DomainError) as caught:
            await engine.execute(
                "owner",
                f"alarms.{command}",
                payload,
                f"invalid-alarm-{command}-{index}",
                now,
            )
        assert caught.value.code == "invalid_field"
        assert caught.value.field == "revision"
        assert engine.snapshot() == before
        assert store.calls == writes


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["save", "enable"])
async def test_existing_alarm_stale_conflicts_and_current_revision_succeeds(engine, now, command):
    alarm = await alarm_schedule(engine, now, f"new-stale-{command}")
    stale_payload = (
        alarm_edit_payload(alarm, alarm["revision"] + 1)
        if command == "save"
        else {"id": alarm["id"], "revision": alarm["revision"] + 1, "enabled": False}
    )
    before = engine.snapshot()
    with pytest.raises(DomainError) as caught:
        await engine.execute(
            "owner", f"alarms.{command}", stale_payload, f"stale-alarm-{command}", now
        )
    assert caught.value.code == "conflict"
    assert engine.snapshot() == before

    payload = (
        alarm_edit_payload(alarm, alarm["revision"])
        if command == "save"
        else {"id": alarm["id"], "revision": alarm["revision"], "enabled": False}
    )
    changed = await engine.execute(
        "owner", f"alarms.{command}", payload, f"current-alarm-{command}", now
    )
    assert changed["revision"] == alarm["revision"] + 1


@pytest.mark.asyncio
async def test_new_alarm_save_and_alarm_test_remain_revisionless(engine, now):
    alarm = await alarm_schedule(engine, now)
    assert alarm["revision"] == 1

    run = await engine.execute(
        "owner", "alarms.test", {"id": alarm["id"]}, "revisionless-alarm-test", now
    )
    assert run["alarm_id"] == alarm["id"]
    assert run["test"] is True


@pytest.mark.asyncio
async def test_new_alarm_rejects_meaningless_revision_without_id(engine, now):
    before = deepcopy(engine.snapshot())
    with pytest.raises(DomainError) as caught:
        await engine.execute(
            "owner",
            "alarms.save",
            {
                "member": "child",
                "time": "08:00",
                "days": list(range(7)),
                "timezone": "UTC",
                "revision": 1,
            },
            "new-alarm-with-revision",
            now,
        )
    assert caught.value.code == "invalid_field"
    assert caught.value.field == "revision"
    assert engine.snapshot() == before
