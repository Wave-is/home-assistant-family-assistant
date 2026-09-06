"""Evidence-based name suggestions. A hostname or private MAC is not an identity."""

import ipaddress
import re


def mac(value):
    if not isinstance(value, str):
        return None
    value = value.strip().replace("-", ":").upper()
    if re.fullmatch(r"[0-9A-F]{12}", value):
        value = ":".join(value[i : i + 2] for i in range(0, 12, 2))
    if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", value):
        return None
    if int(value[:2], 16) & 1 or value == "00:00:00:00:00:00":
        return None
    return value


def address(value):
    try:
        parsed = ipaddress.ip_address(value)
        return str(parsed) if not (parsed.is_multicast or parsed.is_unspecified) else None
    except (ValueError, TypeError):
        return None


def yes(value):
    return value in {"true", "yes"}


def build(tables, ha_devices, now):
    devices = {}
    for table in ("leases", "arp", "bridge", "wifi", "wireless", "kid_devices"):
        for row in tables.get(table, []):
            identity = mac(row.get("mac-address"))
            if not identity:
                continue
            item = devices.setdefault(
                identity,
                {
                    "mac": identity,
                    "addresses": [],
                    "hostnames": [],
                    "comments": [],
                    "sources": [],
                    "leases": [],
                    "current_addresses": [],
                    "warnings": [],
                    "protected": False,
                },
            )
            if table not in item["sources"]:
                item["sources"].append(table)
            ip = address(row.get("active-address") or row.get("address"))
            if ip and ip not in item["addresses"]:
                item["addresses"].append(ip)
            current = (
                table == "leases"
                and row.get("status") == "bound"
                and mac(row.get("active-mac-address") or identity) == identity
            ) or (table == "arp" and (yes(row.get("complete")) or row.get("status") == "reachable"))
            if current and ip and ip not in item["current_addresses"]:
                item["current_addresses"].append(ip)
            for field, target in (("host-name", "hostnames"), ("comment", "comments")):
                value = row.get(field, "")
                if value and value not in item[target]:
                    item[target].append(value)
            if table == "leases":
                item["leases"].append(
                    {
                        k: row.get(k, "")
                        for k in (
                            ".id",
                            "address",
                            "server",
                            "dynamic",
                            "disabled",
                            "status",
                            "comment",
                        )
                    }
                )
            if table == "bridge" and yes(row.get("local")):
                item["protected"] = True
    local_macs = {mac(row.get("mac-address")) for row in tables.get("interfaces", [])}
    for item in devices.values():
        if item["mac"] in local_macs:
            item["protected"] = True
        if int(item["mac"][:2], 16) & 2:
            item["warnings"].append("locally_administered")
        if len(item["current_addresses"]) > 1:
            item["warnings"].append("multiple_addresses")
        candidates = []
        for candidate in ha_devices:
            evidence, confidence = [], 0
            if item["mac"] in candidate.get("macs", []):
                confidence, evidence = 100, ["exact_mac"]
            elif candidate.get("current") and set(item["current_addresses"]) & set(
                candidate.get("ips", [])
            ):
                confidence, evidence = 80, ["current_tracker_ip"]
            elif {h.casefold() for h in item["hostnames"]} & {
                h.casefold() for h in candidate.get("hostnames", [])
            }:
                confidence, evidence = 40, ["hostname_only"]
            if confidence:
                candidates.append(
                    {
                        "id": candidate["id"],
                        "name": candidate["name"],
                        "area": candidate.get("area", ""),
                        "confidence": confidence,
                        "evidence": evidence,
                    }
                )
        item["suggestions"] = sorted(candidates, key=lambda c: (-c["confidence"], c["id"]))[:20]
        top = item["suggestions"]
        item["suggested_name"] = (
            top[0]["name"]
            if top
            and top[0]["confidence"] >= 80
            and (len(top) == 1 or top[0]["confidence"] > top[1]["confidence"])
            else None
        )
        if len(top) > 1 and top[0]["confidence"] == top[1]["confidence"]:
            item["warnings"].append("ambiguous_identity")
        if not top:
            item["warnings"].append("unknown_device")
    return {
        "observed_at": now.isoformat(),
        "devices": sorted(devices.values(), key=lambda d: d["mac"]),
        "capabilities": tables.get("capabilities", {}),
        "fasttrack": any(
            row.get("action") == "fasttrack-connection" and not yes(row.get("disabled"))
            for row in tables.get("filters", [])
        ),
        "ipv6": "disabled"
        if tables.get("ipv6") and yes(tables["ipv6"][0].get("disable-ipv6"))
        else "unknown_or_enabled",
    }
