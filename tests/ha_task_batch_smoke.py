"""Actual authenticated atomic task batches, rollback and durable replay."""

from types import MappingProxyType

from ha_media_smoke import _websocket
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers.storage import Store


async def verify_task_batch(hass, owner):
    child = await hass.auth.async_create_user("Synthetic batch child")
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="family_assistant",
        source="user",
        title="Synthetic task batch family",
        unique_id=None,
        data={
            "owner_user_id": owner.id,
            "owner_name": "Synthetic batch parent",
            "modules": ["tasks", "maintenance"],
            "initial_members": [
                {
                    "id": "child",
                    "name": "Synthetic child",
                    "role": "child",
                    "language": "en",
                    "revision": 1,
                    "active": True,
                    "aliases": [],
                    "ha_user_id": child.id,
                }
            ],
        },
        options={},
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    await hass.config_entries.async_add(entry)
    try:
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED
        store = Store(hass, 1, f"family_assistant.{entry.entry_id}")

        async def command(user, action, payload, operation):
            return await _websocket(
                hass,
                entry,
                user,
                {
                    "id": 1,
                    "type": "family_assistant/execute",
                    "entry_id": entry.entry_id,
                    "action": action,
                    "payload": payload,
                    "operation_id": operation,
                },
            )

        items = []
        for index in range(3):
            result = await command(
                owner,
                "tasks.create",
                {
                    "title": f"Synthetic batch task {index}",
                    "assignee": "child",
                    "report_type": "none",
                    "due_at": "2099-12-01T09:00:00+00:00",
                    "penalty": 0,
                },
                f"task-batch-create-{index}",
            )
            assert result["success"]
            items.append(result["result"])

        def batch(action, targets):
            return {
                "commands": [
                    {
                        "action": f"tasks.{action}",
                        "payload": {
                            "id": item["id"],
                            "revision": item["revision"],
                        },
                    }
                    for item in targets
                ]
            }

        owner_revision = entry.runtime_data.engine.snapshot()["members"]["owner"]["revision"]
        asset = await command(
            owner,
            "maintenance.asset_save",
            {
                "name": "Synthetic batch sentinel appliance",
                "category": "Test",
                "location": "Test room",
                "responsible_member": "owner",
                "responsible_member_revision": owner_revision,
                "warranty": {"expires_on": None, "vendor": "", "reference": ""},
                "consumables": [],
                "note": "Synthetic private maintenance note",
            },
            "task-batch-asset",
        )
        assert asset["success"]
        fault = await command(
            owner,
            "maintenance.fault_report",
            {
                "asset_id": asset["result"]["id"],
                "asset_revision": asset["result"]["revision"],
                "reporter_member_revision": owner_revision,
                "summary": "Synthetic private fault",
                "details": "Synthetic observation",
                "attachment_ids": [],
            },
            "task-batch-fault",
        )
        assert fault["success"]
        fault_id = fault["result"]["task_id"]
        view = await _websocket(
            hass,
            entry,
            owner,
            {"id": 1, "type": "family_assistant/view", "entry_id": entry.entry_id},
        )
        assert view["success"]
        projected_fault = next(row for row in view["result"]["tasks"] if row["id"] == fault_id)
        assert projected_fault["delivery_scope"] == "private"
        assert projected_fault["source"]["kind"] == "maintenance_fault"
        assert not projected_fault.get("managed_by")
        original = entry.runtime_data.engine.snapshot()
        assert await store.async_load() == original
        invalid = batch("complete", [items[0], {**items[1], "revision": items[1]["revision"] + 1}])
        rejected = await command(owner, "batch", invalid, "task-batch-stale")
        assert not rejected["success"] and rejected["error"]["code"] == "conflict"
        assert entry.runtime_data.engine.snapshot() == original
        assert await store.async_load() == original
        denied = await command(child, "batch", batch("complete", items[:2]), "task-batch-child")
        assert not denied["success"] and denied["error"]["code"] == "forbidden"
        assert await store.async_load() == original

        payload = batch("complete", items[:2])
        completed = await command(owner, "batch", payload, "task-batch-complete")
        assert completed["success"] and len(completed["result"]["items"]) == 2
        after = entry.runtime_data.engine.snapshot()
        assert after["revision"] == original["revision"] + 1
        assert len(after["audit"]) == len(original["audit"]) + 1
        assert all(after["tasks"][item["id"]]["status"] == "completed" for item in items[:2])
        assert after["tasks"][items[2]["id"]] == original["tasks"][items[2]["id"]]
        assert after["tasks"][fault_id] == original["tasks"][fault_id]
        assert await store.async_load() == after
        assert await command(owner, "batch", payload, "task-batch-complete") == completed
        assert await store.async_load() == after

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert await command(owner, "batch", payload, "task-batch-complete") == completed
        assert await store.async_load() == after
        archive = batch("archive", [after["tasks"][item["id"]] for item in items[:2]])
        archived = await command(owner, "batch", archive, "task-batch-archive")
        assert archived["success"]
        assert all(row["status"] == "archived" for row in archived["result"]["items"])
        cancelled = await command(owner, "batch", batch("cancel", [items[2]]), "task-batch-cancel")
        assert cancelled["success"] and cancelled["result"]["items"][0]["status"] == "cancelled"
        assert (
            entry.runtime_data.engine.snapshot()["tasks"][fault_id] == original["tasks"][fault_id]
        )
        assert entry.runtime_data.telegram is None and entry.runtime_data.network is None
        print(
            "PASS: actual HA authenticated task batch atomic rollback, child denial, "
            "single commit, exact replay/reload, completion/archive/cancel and unchanged sentinel"
        )
    finally:
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
