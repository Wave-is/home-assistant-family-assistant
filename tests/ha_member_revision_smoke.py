"""Actual HA Options Flow acceptance for concurrent member edits."""

from copy import deepcopy


def _defaults(form):
    """Apply the real voluptuous form schema so selector defaults are exercised."""
    return dict(form["data_schema"]({}))


async def _open_member_edit(hass, entry, owner, member_id):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": owner.id}
    )
    assert flow["type"] == "menu" and flow["step_id"] == "init", flow
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "member"}
    )
    assert flow["type"] == "form" and flow["step_id"] == "member", flow
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"member_id": member_id}
    )
    assert flow["type"] == "form" and flow["step_id"] == "edit_member", flow
    return flow


async def verify_member_revision_options(hass, entry, owner, member_id):
    """A stale member form must conflict, refresh, then allow an intentional retry."""
    engine = entry.runtime_data.engine
    before = engine.snapshot()
    original = deepcopy(before["members"][member_id])
    assert original["role"] == "child" and original["active"] is True
    bindings = {
        key: deepcopy(original.get(key)) for key in ("ha_user_id", "telegram_id", "aliases")
    }
    alarm_devices = deepcopy(entry.options.get("alarm_devices", {}))
    schedules = {
        key: deepcopy(before[key])
        for key in ("alarms", "task_series", "shopping_series", "routines")
    }
    timezone = before["settings"]["timezone"]

    first = await _open_member_edit(hass, entry, owner, member_id)
    stale = await _open_member_edit(hass, entry, owner, member_id)
    assert first["flow_id"] != stale["flow_id"]
    first_defaults = _defaults(first)
    stale_defaults = _defaults(stale)
    assert first_defaults == stale_defaults
    assert first_defaults["name"] == original["name"]
    assert first_defaults["role"] == original["role"]
    assert first_defaults["active"] == original["active"]

    committed_name = "Child committed revision"
    first_result = await hass.config_entries.options.async_configure(
        first["flow_id"], {**first_defaults, "name": committed_name}
    )
    assert first_result["type"] == "create_entry", first_result
    committed = engine.snapshot()["members"][member_id]
    assert committed["name"] == committed_name
    assert committed["role"] == original["role"] and committed["active"] is True
    assert committed["revision"] == original["revision"] + 1

    conflict = await hass.config_entries.options.async_configure(
        stale["flow_id"],
        {
            **stale_defaults,
            "name": "Stale privilege overwrite",
            "role": "parent",
            "active": False,
        },
    )
    assert conflict["type"] == "form" and conflict["step_id"] == "edit_member", conflict
    assert conflict["errors"]["base"] == "conflict", conflict
    after_conflict = engine.snapshot()["members"][member_id]
    assert after_conflict == committed

    fresh_defaults = _defaults(conflict)
    assert fresh_defaults["name"] == committed_name
    assert fresh_defaults["role"] == original["role"]
    assert fresh_defaults["active"] == original["active"]
    intentional_name = "Child intentional retry"
    retried = await hass.config_entries.options.async_configure(
        conflict["flow_id"],
        {
            **fresh_defaults,
            "name": intentional_name,
            "role": original["role"],
            "active": original["active"],
        },
    )
    assert retried["type"] == "create_entry", retried

    final = engine.snapshot()
    member = final["members"][member_id]
    assert member["name"] == intentional_name
    assert member["role"] == original["role"] and member["active"] == original["active"]
    assert member["revision"] == original["revision"] + 2
    assert {key: member.get(key) for key in bindings} == bindings
    assert entry.options.get("alarm_devices", {}) == alarm_devices
    assert final["settings"]["timezone"] == timezone
    assert all(final[key] == value for key, value in schedules.items())
    print("PASS: actual HA concurrent member options reject stale revisions and preserve bindings")
