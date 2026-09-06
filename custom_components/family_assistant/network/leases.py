"""Pure, expiring lease-change previews with selected targets and live fingerprints."""

import hashlib
import ipaddress
import json
import re
from copy import deepcopy
from datetime import timedelta

from ..domain.validation import DomainError, fields
from .inventory import mac, yes

CONFIG_FIELDS = (
    "address",
    "mac-address",
    "server",
    "client-id",
    "comment",
    "dynamic",
    "disabled",
    "blocked",
)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"\*[0-9A-Fa-f]{1,16}", value):
        raise DomainError("network_target")
    return value.upper()


def fingerprint(row):
    return hashlib.sha256(
        json.dumps({key: row.get(key, "") for key in CONFIG_FIELDS}, sort_keys=True).encode()
    ).hexdigest()


def _subnet(row, tables):
    try:
        ip = ipaddress.IPv4Address(row["address"])
        networks = [ipaddress.IPv4Network(n["address"], strict=False) for n in tables["networks"]]
        server = [s for s in tables["servers"] if s["name"] == row["server"]]
        if len(server) != 1 or yes(server[0].get("disabled")) or yes(server[0].get("invalid")):
            raise ValueError
        interfaces = [
            ipaddress.IPv4Interface(a["address"]).network
            for a in tables["addresses"]
            if a.get("interface") == server[0]["interface"]
            and not yes(a.get("disabled"))
            and not yes(a.get("invalid"))
        ]
        if not any(
            ip in n and ip not in {n.network_address, n.broadcast_address} for n in networks
        ):
            raise ValueError
        if not any(ip in n for n in interfaces):
            raise ValueError
        if any(ip == ipaddress.IPv4Interface(a["address"]).ip for a in tables["addresses"]):
            raise ValueError
    except (ValueError, KeyError):
        raise DomainError("network_subnet") from None


def preview(tables, selection, now, *, protected_macs=()):
    """No device IO. Empty comments are preserved unless explicitly replaced."""
    if not isinstance(selection, list) or not 1 <= len(selection) <= 100:
        raise DomainError("invalid_field", "leases")
    rows = tables.get("leases", [])
    selected_ids = set()
    changes = []
    protected = {mac(value) for value in protected_macs}
    protected.update(mac(row.get("mac-address")) for row in tables.get("interfaces", []))
    for selected in selection:
        if not isinstance(selected, dict):
            raise DomainError("invalid_field", "leases")
        fields(selected, {"id", "comment", "replace_comment"}, {"id"})
        target = identifier(selected["id"])
        if target in selected_ids:
            raise DomainError("network_conflict")
        selected_ids.add(target)
        matches = [row for row in rows if row.get(".id", "").upper() == target]
        if len(matches) != 1:
            raise DomainError("network_target")
        before = deepcopy(matches[0])
        if before.get("dynamic") not in {"true", "false"}:
            raise DomainError("network_target")
        identity = mac(before.get("mac-address"))
        if not identity or identity in protected:
            raise DomainError("network_protected")
        if yes(before.get("disabled")) or yes(before.get("blocked")):
            raise DomainError("network_target")
        if yes(before.get("dynamic")) and before.get("status") != "bound":
            raise DomainError("network_target")
        if before.get("active-address") and before["active-address"] != before.get("address"):
            raise DomainError("network_conflict")
        if before.get("active-mac-address") and mac(before["active-mac-address"]) != identity:
            raise DomainError("network_conflict")
        if before.get("active-server") and before["active-server"] != before.get("server"):
            raise DomainError("network_conflict")
        for other in rows:
            if other is matches[0]:
                continue
            # Ambiguous duplicate identity or IP requires explicit cleanup first.
            if mac(other.get("mac-address")) == identity or other.get("address") == before.get(
                "address"
            ):
                raise DomainError("network_conflict")
        _subnet(before, tables)
        replace = selected.get("replace_comment", False)
        if type(replace) is not bool:
            raise DomainError("invalid_field", "replace_comment")
        comment = selected.get("comment", before.get("comment", ""))
        if not isinstance(comment, str) or len(comment) > 255 or any(ord(c) < 32 for c in comment):
            raise DomainError("invalid_field", "comment")
        comment = comment.strip()
        if before.get("comment") and not replace:
            comment = before["comment"]
        changed = yes(before.get("dynamic")) or comment != before.get("comment", "")
        changes.append(
            {
                "id": target,
                "mac": identity,
                "address": before["address"],
                "server": before["server"],
                "before": before,
                "fingerprint": fingerprint(before),
                "comment": comment,
                "convert": yes(before.get("dynamic")),
                "changed": changed,
                "warnings": ["locally_administered"] if int(identity[:2], 16) & 2 else [],
            }
        )
    return {
        "kind": "leases",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "targets": changes,
        "requires_dhcp_recovery_consent": any(c["convert"] for c in changes),
    }


def readback_match(target, rows):
    """Router IDs may change during make-static: resolve one exact selected identity."""
    matches = [
        row
        for row in rows
        if (
            mac(row.get("mac-address")) == target["mac"]
            and row.get("address") == target["address"]
            and row.get("server") == target["server"]
        )
    ]
    if len(matches) != 1:
        raise DomainError("network_conflict")
    return matches[0]
