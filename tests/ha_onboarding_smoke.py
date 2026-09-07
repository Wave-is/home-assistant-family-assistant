"""Actual Home Assistant guided Options-flow acceptance helper."""

from __future__ import annotations

from copy import deepcopy


async def _guide(hass, entry, owner):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": owner.id}
    )
    assert flow["type"] == "menu" and flow["step_id"] == "init", flow
    assert "guided_onboarding" in flow["menu_options"], flow
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "guided_onboarding"}
    )
    assert result["type"] == "menu" and result["step_id"] == "guided_onboarding", result
    return result


async def verify_onboarding(hass, entry, owner):
    """Verify read-only open/finish/resume against a real loaded ConfigEntry."""
    runtime = entry.runtime_data
    before_state = runtime.engine.snapshot()
    before_options = deepcopy(dict(entry.options))
    before_modified = entry.modified_at

    guide = await _guide(hass, entry, owner)
    placeholders = guide["description_placeholders"]
    assert set(placeholders) == {
        "household_status",
        "members_status",
        "modules_status",
        "telegram_status",
        "models_status",
        "siren_status",
        "active_members",
        "ha_linked_members",
        "telegram_linked_members",
        "enabled_modules",
        "private_chats",
        "group_links",
        "search_enabled",
        "siren_bindings",
    }
    assert not {"ready", "attention", "optional", "off"} & set(placeholders.values())
    assert all(
        value.isdecimal()
        for key, value in placeholders.items()
        if key
        in {
            "active_members",
            "ha_linked_members",
            "telegram_linked_members",
            "enabled_modules",
            "private_chats",
            "group_links",
            "search_enabled",
            "siren_bindings",
        }
    )
    assert guide["menu_options"][-1] == "guided_finish"

    finished = await hass.config_entries.options.async_configure(
        guide["flow_id"], {"next_step_id": "guided_finish"}
    )
    assert finished["type"] == "abort" and finished["reason"] == "guided_finished", finished
    await hass.async_block_till_done()
    assert entry.runtime_data is runtime
    assert runtime.engine.snapshot() == before_state
    assert dict(entry.options) == before_options
    assert entry.modified_at == before_modified

    resumed = await _guide(hass, entry, owner)
    member = await hass.config_entries.options.async_configure(
        resumed["flow_id"], {"next_step_id": "member"}
    )
    assert member["type"] == "form" and member["step_id"] == "member", member
    assert runtime.engine.snapshot() == before_state
    assert dict(entry.options) == before_options

    print(
        "PASS: guided onboarding is same-entry, localized, resumable and read-only "
        "until an existing Options step is submitted"
    )
