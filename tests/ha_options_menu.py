"""Exercise the native grouped Options UI before opening an existing leaf step."""

GROUPS = {
    "menu_family": {"general", "member", "guided_onboarding"},
    "menu_telegram": {"telegram", "telegram_group", "telegram_member", "alarm_device"},
    "menu_ai": {"conversation", "ha_agent", "search", "articles"},
    "menu_services": {"mikrotik", "recipes", "presence_sources", "digests", "online_school"},
    "menu_maintenance": {"legacy_copy", "legacy_prepare", "legacy_resume", "developer_diagnostics"},
}


async def select_option(hass, result, step, *, technical=False, allow_flat=False):
    """Follow visible menus; only baseline upgrade tests may accept the old flat UI."""
    assert result["type"] == "menu", result
    if result["step_id"] == "init" and not (allow_flat and step in result["menu_options"]):
        assert set(result["menu_options"]) == {*GROUPS, "all_options"}, result
        group = (
            "all_options"
            if technical
            else next(name for name, members in GROUPS.items() if step in members)
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": group}
        )
        assert result["type"] == "menu" and result["step_id"] == group, result
        if not technical:
            assert set(result["menu_options"]) == GROUPS[group] | {"init"}, result
    assert step in result["menu_options"], result
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )
