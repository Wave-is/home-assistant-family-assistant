"""Read explicitly selected registry metadata; never serialize arbitrary attributes."""

from homeassistant.helpers import area_registry, device_registry, entity_registry

from .inventory import address, mac


def collect(hass):
    devices = device_registry.async_get(hass)
    entities = entity_registry.async_get(hass)
    areas = area_registry.async_get(hass)
    result = {}
    for device in list(devices.devices.values())[:5000]:
        area = areas.async_get_area(device.area_id) if device.area_id else None
        result[device.id] = {
            "id": device.id,
            "name": device.name_by_user or device.name or device.model or "Device",
            "macs": [
                valid
                for kind, value in device.connections
                if kind == "mac" and (valid := mac(value))
            ],
            "ips": [],
            "hostnames": [],
            "current": False,
            "area": area.name if area else "",
        }
    for state in hass.states.async_all("device_tracker")[:5000]:
        entry = entities.async_get(state.entity_id)
        key = entry.device_id if entry and entry.device_id in result else state.entity_id
        item = result.setdefault(
            key,
            {
                "id": key,
                "name": state.name,
                "macs": [],
                "ips": [],
                "hostnames": [],
                "current": False,
                "area": "",
            },
        )
        attrs = state.attributes
        identity = mac(attrs.get("mac") or attrs.get("mac_address"))
        if identity and identity not in item["macs"]:
            item["macs"].append(identity)
        # Only an active router/network tracker corroborates a current IP. A GPS
        # home state does not establish that a stale address still belongs to it.
        current = state.state == "home" and attrs.get("source_type") in {"router", "bluetooth_le"}
        ip = address(attrs.get("ip") or attrs.get("ip_address"))
        if current and ip:
            item["current"] = True
            if ip not in item["ips"]:
                item["ips"].append(ip)
        hostname = attrs.get("host_name") or attrs.get("hostname")
        if isinstance(hostname, str) and hostname and len(hostname) <= 255:
            item["hostnames"].append(hostname)
    return list(result.values())
