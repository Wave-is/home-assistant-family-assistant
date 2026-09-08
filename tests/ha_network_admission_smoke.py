"""Actual HA authenticated local device approvals; no router or Telegram transport."""

from copy import deepcopy
from datetime import UTC, datetime

from ha_presence_smoke import _request


async def verify_network_admission(hass, owner_user):
    from custom_components.family_assistant.network.inventory import build
    from custom_components.family_assistant.telegram.admission import current, read

    created = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner_user.id}
    )
    created = await hass.config_entries.flow.async_configure(
        created["flow_id"],
        {
            "name": "Synthetic network audit",
            "owner_name": "Example owner",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(created["flow_id"], {"mikrotik": True})
    entry = created["result"]
    await hass.async_block_till_done()
    try:
        await entry.runtime_data.scheduler.stop()
        engine = entry.runtime_data.engine
        now = datetime.now(UTC)
        client, protected = "02:11:22:33:44:55", "02:11:22:33:44:66"

        def seed(ctx):
            ctx.state["members"]["owner"]["telegram_id"] = 840001
            tables = {
                "leases": [
                    {
                        "mac-address": client,
                        "active-address": "198.51.100.10",
                        "host-name": "Example but not approval",
                        "status": "bound",
                    }
                ],
                "interfaces": [{"mac-address": protected}],
            }
            ctx.state["network"].update(
                backend="a" * 64,
                tables=tables,
                inventory=build(tables, [], now),
                protected_macs=[protected],
                writable=False,
                kid_writable=False,
            )

        await engine.system_update("synthetic-network-audit", now, seed)
        response = await _request(hass, entry, owner_user, 701)
        assert response["success"], response
        view = response["result"]
        admission = view["network"]["admission"]
        assert admission["mode"] == "audit_only" and admission["enforcement"] is False
        assert admission["counts"]["unreviewed"] == 1
        actor_revision = engine.snapshot()["members"]["owner"]["revision"]
        payload = {
            "actor_revision": actor_revision,
            "observation_token": admission["token"],
            "policy_revision": None,
            "changes": [{"mac": client, "approved": True, "label": "Reviewed synthetic laptop"}],
        }
        before = engine.snapshot()
        preview = await _request(
            hass,
            entry,
            owner_user,
            702,
            "mikrotik.admission_preview",
            payload,
            "ha-admission-preview",
        )
        assert preview["success"], preview
        plan = preview["result"]
        snapshot = engine.snapshot()
        replay = await _request(
            hass,
            entry,
            owner_user,
            703,
            "mikrotik.admission_preview",
            payload,
            "ha-admission-preview",
        )
        assert replay["success"] and replay["result"] == plan and engine.snapshot() == snapshot
        apply = {"id": plan["id"], "actor_revision": actor_revision, "confirmed": True}
        result = await _request(
            hass, entry, owner_user, 704, "mikrotik.admission_apply", apply, "ha-admission-apply"
        )
        assert result["success"] and result["result"]["revision"] == 1, result
        applied = engine.snapshot()
        for key in ("tables", "inventory", "plans", "kid_plans"):
            assert applied["network"].get(key) == before["network"].get(key)
        assert applied["outbox"] == before["outbox"]
        # Direct private read is based on the owner ledger and guarded at delivery.
        reply = read(engine.view("owner", now=now), now, private=True)
        data = {
            "actor": "owner",
            "chat_id": 840001,
            "private_context": True,
            "admission_context": reply.scope,
        }
        assert current(applied, data, now)
        changed = deepcopy(applied)
        changed["network"]["backend"] = "b" * 64
        assert not current(changed, data, now)
        # Store rehydration is tested through the supported entry reload.
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
        restored = entry.runtime_data.engine.snapshot()
        assert restored["network"]["admission"] == applied["network"]["admission"]
        assert restored["network"]["admission_plans"] == applied["network"]["admission_plans"]
        outsider = await hass.auth.async_create_user("Synthetic network outsider")
        denied = await _request(
            hass, entry, outsider, 705, "mikrotik.admission_apply", apply, "ha-outsider-apply"
        )
        assert denied["success"] is False, denied
        print(
            "PASS: actual HA authenticated local network approval/replay, zero router effects, "
            "private reply source guard, Store reload and outsider denial"
        )
        from ha_network_watch_smoke import verify_network_watch

        await verify_network_watch(hass, entry, owner_user)
    finally:
        await hass.config_entries.async_remove(entry.entry_id)
