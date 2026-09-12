"""One shared panel for all households, without overwriting another integration."""

from .const import DOMAIN


def _owned(panel):
    config = getattr(panel, "config", None) or {}
    return config.get("_panel_custom", {}).get("name") == "family-assistant-panel"


def register(hass):
    from homeassistant.components.frontend import DATA_PANELS, async_register_built_in_panel

    data = hass.data[DOMAIN]
    resource = data.get("frontend_resource")
    if resource is None:
        return False
    current = hass.data.get(DATA_PANELS, {}).get("family")
    if current is not None and not _owned(current):
        return False
    config = {
        "_panel_custom": {
            "name": "family-assistant-panel",
            "embed_iframe": False,
            "trust_external": False,
            "module_url": resource.resource_url,
        }
    }
    if current is not None and current.config == config:
        return True
    language = getattr(hass.config, "language", "en")
    async_register_built_in_panel(
        hass,
        "custom",
        sidebar_title={"en": "Family", "ru": "Семья", "uk": "Сім’я"}.get(language, "Family"),
        sidebar_icon="mdi:account-group",
        frontend_url_path="family",
        config=config,
        require_admin=False,
        update=current is not None,
    )
    return True


def unregister_if_unused(hass):
    from homeassistant.components.frontend import DATA_PANELS, async_remove_panel

    if hass.data.get(DOMAIN, {}).get("entries"):
        return
    current = hass.data.get(DATA_PANELS, {}).get("family")
    if current is not None and _owned(current):
        async_remove_panel(hass, "family")
