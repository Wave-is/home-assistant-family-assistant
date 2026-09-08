"""Actual HA Options, authenticated consent, ACL, outbox and Store restoration.

Only an isolated synthetic entry and an in-memory transport are used. No Telegram
request, real sensor, household data or production configuration is involved.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from ha_presence_smoke import _general_presence, _presence_source, _request, _state_reads


async def verify_presence_notifications(hass, owner_user):
    from homeassistant.helpers import entity_registry

    from custom_components.family_assistant import presence_notification_adapter
    from custom_components.family_assistant.notifications import Notifications
    from custom_components.family_assistant.telegram.messages import targets

    created = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner_user.id}
    )
    created = await hass.config_entries.flow.async_configure(
        created["flow_id"],
        {
            "name": "Synthetic presence delivery household",
            "owner_name": "Synthetic consenting owner",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(created["flow_id"], {"tasks": True})
    entry = created["result"]
    await hass.async_block_till_done()
    try:
        await _general_presence(hass, entry, owner_user, True)
        child = await _request(
            hass,
            entry,
            owner_user,
            501,
            "members.save",
            {"name": "Synthetic reminder child", "role": "child"},
        )
        assert child["success"], child
        child_id = child["result"]["id"]
        registry = entity_registry.async_get(hass)
        source = registry.async_get_or_create(
            "person",
            "family_assistant",
            "synthetic-delivery-child",
            suggested_object_id="synthetic_delivery_child",
        )
        hass.states.async_set(source.entity_id, "not_home", {"latitude": "DELIVERY_PRIVATE_CANARY"})
        await _presence_source(hass, entry, owner_user, child_id, True, source.entity_id)
        await entry.runtime_data.scheduler.stop()
        engine = entry.runtime_data.engine
        base = datetime.now(UTC)
        owner = engine.snapshot()["members"]["owner"]
        payload = {
            "member": child_id,
            "member_revision": 1,
            "binding_revision": 1,
            "preference_revision": None,
            "enabled": True,
            "max_wait_minutes": 15,
            "actor_member_revision": owner["revision"],
        }
        action = "presence.guardian_notification_access_set"
        enabled = await _request(
            hass, entry, owner_user, 502, action, payload, "ha-delivery-consent"
        )
        assert enabled["success"] and enabled["result"]["revision"] == 1, enabled
        before = engine.snapshot()
        replay = await _request(
            hass, entry, owner_user, 503, action, payload, "ha-delivery-consent"
        )
        assert replay["success"] and replay["result"] == enabled["result"]
        assert engine.snapshot() == before
        assert engine.snapshot()["presence"]["subscriptions"] == {}
        view = await _request(hass, entry, owner_user, 504)
        preferences = view["result"]["presence"]["notifications"]["managed"]
        row = next(row for row in preferences if row["member"] == child_id)
        assert row["enabled"] and row["effective"] and row["max_wait_minutes"] == 15
        assert source.entity_id not in repr(preferences) and "DELIVERY_PRIVATE_CANARY" not in repr(
            view
        )

        def seed(ctx):
            ctx.state["members"][child_id]["telegram_id"] = 830001
            ctx.state["telegram"]["group_id"] = -830099

        await engine.system_update("synthetic-delivery-route", base, seed)
        for index in range(2):
            task = await _request(
                hass,
                entry,
                owner_user,
                510 + index,
                "tasks.create",
                {"title": f"Synthetic return reminder {index}", "assignee": child_id},
            )
            assert task["success"], task
        sent = []

        async def send(event, target):
            sent.append((deepcopy(event), deepcopy(target)))
            return str(len(sent))

        def worker():
            runtime = entry.runtime_data

            def guard():
                assert hass.config_entries.async_get_entry(entry.entry_id) is entry
                assert entry.runtime_data is runtime

            async def prepare(state):
                return await presence_notification_adapter.prepare(
                    hass, entry, runtime, state, guard
                )

            return Notifications(runtime.engine, targets, send, presence_prepare=prepare)

        with _state_reads(hass) as reads:
            assert await worker().run(base) == 0
        assert reads and set(reads) == {source.entity_id} and not sent
        held = entry.runtime_data.engine.snapshot()
        assert all(event["state"] == "pending" for event in held["outbox"].values())
        assert all(event["attempts"] == 0 for event in held["outbox"].values())
        assert "DELIVERY_PRIVATE_CANARY" not in repr(held)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
        engine = entry.runtime_data.engine
        assert engine.snapshot()["presence"] == held["presence"]
        assert engine.snapshot()["outbox"] == held["outbox"]

        hass.states.async_set(source.entity_id, "home", {"latitude": "DELIVERY_PRIVATE_CANARY"})
        with patch.object(type(owner_user.permissions), "check_entity", return_value=False):
            with _state_reads(hass) as reads:
                assert await worker().run(base + timedelta(seconds=61)) == 0
            assert reads == [] and not sent
        assert await worker().run(base + timedelta(seconds=122), 20) == 1
        assert len(sent) == 1 and sent[0][1]["id"] == 830001
        assert await worker().run(base + timedelta(seconds=123), 20) == 0
        # The second held notification expires rather than sending obsolete data.
        assert await worker().run(base + timedelta(minutes=16), 20) == 0
        events = engine.snapshot()["outbox"].values()
        assert sorted(event["state"] for event in events) == ["sent", "superseded"]
        expired = next(event for event in events if event["state"] == "superseded")
        assert next(iter(expired["deliveries"].values()))["error"] == "presence_wait_expired"

        disabled = await _request(
            hass,
            entry,
            owner_user,
            520,
            action,
            {**payload, "preference_revision": 1, "enabled": False},
            "ha-delivery-disable",
        )
        assert disabled["success"], disabled
        task = await _request(
            hass,
            entry,
            owner_user,
            521,
            "tasks.create",
            {"title": "Ordinary reminder after withdrawal", "assignee": child_id},
        )
        assert task["success"], task
        hass.states.async_set(source.entity_id, "not_home")
        with _state_reads(hass) as reads:
            assert await worker().run(base + timedelta(minutes=17)) == 1
        assert not reads and len(sent) == 2
        assert all("DELIVERY_PRIVATE_CANARY" not in repr(item) for item in sent)
        print(
            "PASS: actual HA independent reminder consent, ACL-denied zero reads, durable "
            "return-home hold/reload, paced delivery, expiry and withdrawal"
        )
    finally:
        await hass.config_entries.async_remove(entry.entry_id)
