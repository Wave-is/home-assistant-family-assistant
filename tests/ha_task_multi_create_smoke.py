"""Authenticated HA multi-member creation uses the real atomic command route."""

from types import MappingProxyType

from ha_media_smoke import _websocket
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers.storage import Store


async def verify_task_multi_create(hass, owner):
    child = await hass.auth.async_create_user("Synthetic multi-task child")
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="family_assistant",
        source="user",
        title="Synthetic independent assignments",
        unique_id=None,
        data={
            "owner_user_id": owner.id,
            "owner_name": "Synthetic parent",
            "modules": ["tasks"],
            "initial_members": [
                {
                    "id": name,
                    "name": f"Synthetic {name}",
                    "role": role,
                    "language": "en",
                    "revision": 1,
                    "active": True,
                    "aliases": [],
                    **({"ha_user_id": child.id} if name == "first" else {}),
                }
                for name, role in [("first", "child"), ("second", "child"), ("guest", "guest")]
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

        async def execute(user, action, payload, operation):
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

        def chore(member, revision=1):
            return {
                "action": "tasks.create",
                "payload": {
                    "title": "Synthetic separate chore",
                    "assignee": member,
                    "assignee_revision": revision,
                    "report_type": "text",
                    "due_at": "2099-12-01T09:00:00+00:00",
                    "penalty": 0,
                    "checklist": ["Prepare", "Complete"],
                },
            }

        original = entry.runtime_data.engine.snapshot()
        # Creating the first valid subcommand must leave no partial task/outbox
        # if another target was rebound, is a guest, or is outside child rights.
        for name, user, commands in [
            ("stale", owner, [chore("first"), chore("second", 2)]),
            ("guest", owner, [chore("first"), chore("guest")]),
            ("child", child, [chore("first"), chore("second")]),
        ]:
            result = await execute(user, "batch", {"commands": commands}, f"multi-{name}")
            assert not result["success"], name
            assert entry.runtime_data.engine.snapshot() == original
            assert await store.async_load() == original

        payload = {"commands": [chore("first"), chore("second")]}
        result = await execute(owner, "batch", payload, "multi-create")
        assert result["success"], result
        first, second = result["result"]["items"]
        assert first["id"] != second["id"]
        assert (first["assignee"], second["assignee"]) == ("first", "second")
        saved = entry.runtime_data.engine.snapshot()
        assert saved["revision"] == original["revision"] + 1
        assert len(saved["audit"]) == len(original["audit"]) + 1
        assert await store.async_load() == saved
        assert await execute(owner, "batch", payload, "multi-create") == result
        assert await store.async_load() == saved

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert await execute(owner, "batch", payload, "multi-create") == result
        assert await store.async_load() == saved

        report = await execute(
            child,
            "tasks.submit",
            {
                "id": first["id"],
                "revision": first["revision"],
                "report": "Synthetic first-person report",
            },
            "multi-report",
        )
        assert report["success"], report
        completed = await execute(
            owner,
            "tasks.complete",
            {
                "id": first["id"],
                "revision": report["result"]["revision"],
            },
            "multi-approve",
        )
        assert completed["success"] and completed["result"]["status"] == "completed"
        after = entry.runtime_data.engine.snapshot()
        assert after["tasks"][second["id"]] == saved["tasks"][second["id"]]
        assert len(after["tasks"]) == 2
        assert entry.runtime_data.telegram is None and entry.runtime_data.network is None
        print(
            "PASS: actual HA independent multi-assignment, reviewed member revisions, "
            "atomic rollback, child denial, separate reports, exact replay and Store reload"
        )
    finally:
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
