"""Actual isolated HA/WS/Store task settlements; fictional family, no devices."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch


async def verify_task_settlements(hass, owner):
    from ha_digests_smoke import _execute
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant import websocket
    from custom_components.family_assistant.const import DOMAIN, SCHEMA_VERSION
    from custom_components.family_assistant.domain.task_delivery import current_task_event

    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user", "user_id": owner.id}
    )
    form = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            "name": "Synthetic settlement family",
            "owner_name": "Parent",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"tasks": True, "court": True}
    )
    assert created["type"] == "create_entry", created
    entry = created["result"]
    await hass.async_block_till_done()
    await entry.runtime_data.scheduler.stop()
    clock = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    child_user = await hass.auth.async_create_user("Synthetic settlement child")
    counter = 0

    async def request(action, payload, *, user=owner, operation=None, success=True):
        nonlocal counter
        counter += 1
        with patch.object(websocket, "dt_util", SimpleNamespace(utcnow=lambda: clock)):
            answer = await _execute(
                hass,
                entry,
                user,
                counter,
                action,
                payload,
                operation or f"settlement-native-{counter}",
            )
        assert answer["success"] is success, answer
        return answer.get("result")

    def task_state(task):
        return entry.runtime_data.engine.snapshot()["tasks"][task["id"]]

    try:
        assert entry.state is ConfigEntryState.LOADED
        child = await request(
            "members.save",
            {"name": "Synthetic child", "role": "child", "ha_user_id": child_user.id},
        )
        settings = entry.runtime_data.engine.snapshot()["settings"]
        await request(
            "settings.save",
            {
                "name": settings["name"],
                "language": "en",
                "modules": settings["modules"],
                "automatic_penalties": True,
                "daily_penalty_cap": 10,
            },
        )
        configuration = {
            "title": "Synthetic settled chore",
            "assignee": child["id"],
            "assignee_revision": child["revision"],
            "due_at": clock.replace(hour=19).isoformat(),
            "penalty": -1,
            "missed_actor_revision": 1,
            "missed_policy": {
                "daily_rollover": True,
                "settle_time": "20:00",
                "repeat_penalty": True,
                "same_day_correction": True,
            },
        }
        before = entry.runtime_data.engine.snapshot()
        await request(
            "tasks.create",
            {**configuration, "missed_actor_revision": child["revision"]},
            user=child_user,
            success=False,
        )
        assert entry.runtime_data.engine.snapshot() == before
        chore = await request("tasks.create", configuration)
        assert "missed_scope" not in chore
        submitted = await request(
            "tasks.create", {**configuration, "title": "Synthetic submitted chore"}
        )
        await request(
            "tasks.submit",
            {
                "id": submitted["id"],
                "revision": submitted["revision"],
                "report": "Finished, awaiting parent",
            },
            user=child_user,
        )
        await entry.runtime_data.engine.tick(clock.replace(hour=19, minute=59))
        assert not entry.runtime_data.engine.snapshot()["court"]
        clock = clock.replace(hour=20)
        await entry.runtime_data.engine.tick(clock)
        row = task_state(chore)
        receipt = deepcopy(row["missed_receipt"])
        assert row["missed_receipts"] == {receipt["id"]: receipt}
        assert receipt["ledger_id"] == f"task:{chore['id']}:missed:{clock.date().isoformat()}"
        assert receipt["outcome"] == "applied" and receipt["from_due_at"] == configuration["due_at"]
        assert row["due_at"] == (clock + timedelta(days=1)).replace(hour=19).isoformat()
        assert task_state(submitted)[
            "status"
        ] == "submitted" and "missed_receipt" not in task_state(submitted)
        event = entry.runtime_data.engine.snapshot()["outbox"][receipt["event_id"]]
        assert event["recipient"] == "parents" and current_task_event(
            entry.runtime_data.engine.snapshot(), event
        )
        manual = await request(
            "court.award",
            {"member": child["id"], "points": -2, "reason": "Unrelated synthetic assessment"},
        )
        store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}")
        assert (await store.async_load())["tasks"][chore["id"]] == row
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
        assert task_state(chore) == row
        await entry.runtime_data.engine.tick(clock + timedelta(minutes=1))
        assert task_state(chore) == row
        clock = clock.replace(hour=21)
        complete_payload = {"id": chore["id"], "revision": row["revision"]}
        completed = await request(
            "tasks.complete", complete_payload, operation="settlement-native-complete"
        )
        assert completed["status"] == "completed" and completed["correction_status"] == "reversed"
        state = entry.runtime_data.engine.snapshot()
        assert state["court"][receipt["ledger_id"]]["status"] == "reversed"
        assert state["court"][manual["id"]]["status"] == "active"
        assert task_state(chore)["missed_receipt"] == receipt
        assert task_state(chore)["missed_receipts"] == {receipt["id"]: receipt}
        assert not current_task_event(state, event)
        assert (await store.async_load())["court"] == state["court"]
        clock += timedelta(days=1)
        assert (
            await request(
                "tasks.complete", complete_payload, operation="settlement-native-complete"
            )
            == completed
        )
        overdue = await request(
            "tasks.create",
            {
                **configuration,
                "title": "Synthetic offline chore",
                "due_at": (clock + timedelta(days=1)).replace(hour=19).isoformat(),
            },
        )
        clock += timedelta(days=30)
        await entry.runtime_data.engine.tick(clock)
        assert task_state(overdue)["missed_receipt"]["outcome"] == "skipped_outage"
        court = deepcopy(entry.runtime_data.engine.snapshot()["court"])
        await entry.runtime_data.engine.tick(clock + timedelta(minutes=1))
        assert entry.runtime_data.engine.snapshot()["court"] == court
        assert task_state(submitted)[
            "status"
        ] == "submitted" and "missed_receipt" not in task_state(submitted)
        revoked = await request(
            "tasks.create",
            {
                **configuration,
                "title": "Synthetic revoked chore",
                "due_at": (clock + timedelta(days=1)).replace(hour=19).isoformat(),
            },
        )
        await request(
            "members.save",
            {
                "id": child["id"],
                "revision": child["revision"],
                "name": "Reviewed synthetic child",
                "role": "child",
            },
        )
        await entry.runtime_data.engine.tick(clock + timedelta(days=2))
        assert task_state(revoked)["missed_scope"]["state"] == "revoked"
        assert entry.runtime_data.engine.snapshot()["court"] == court
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
        assert (await store.async_load())["tasks"] == entry.runtime_data.engine.snapshot()["tasks"]
        assert entry.runtime_data.engine.snapshot()["court"] == court
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)
    print(
        "PASS: actual HA opt-in task settlements, exact score correction, cutoff/outage, "
        "submitted exemption, authority revocation and Store/replay"
    )
