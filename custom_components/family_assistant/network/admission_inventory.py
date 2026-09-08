"""Pure network admission and inventory classification."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..domain.validation import DomainError, timestamp
from .inventory import address, mac

ALLOWED_WARNINGS = frozenset(
    {"locally_administered", "multiple_addresses", "ambiguous_identity", "unknown_device"}
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _empty(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "backend": None,
        "observed_at": None,
        "token": None,
        "devices": [],
        "counts": {"protected": 0, "approved": 0, "unreviewed": 0},
    }


def classify(network: Any, now: Any) -> dict[str, Any]:
    """Pure classification of router inventory and owner admission allowlist."""
    if not isinstance(network, dict):
        return _empty("unavailable")
    backend = network.get("backend")
    if not isinstance(backend, str) or not SHA256_RE.fullmatch(backend):
        return _empty("unavailable")
    backend_hash = backend.lower()

    try:
        now_dt = timestamp(now, "now")
        inv = network.get("inventory")
        if not isinstance(inv, dict):
            return _empty("unavailable")
        seen_dt = timestamp(inv.get("observed_at"), "observed_at")
    except DomainError:
        return _empty("unavailable")

    raw_devices = inv.get("devices")
    if not isinstance(raw_devices, list) or len(raw_devices) > 1000:
        return _empty("unavailable")

    explicit_protected = set()
    if "protected_macs" in network:
        p_macs = network["protected_macs"]
        if not isinstance(p_macs, list) or len(p_macs) > 1000:
            return _empty("unavailable")
        for val in p_macs:
            canonical = mac(val) if isinstance(val, str) else None
            if canonical is None:
                return _empty("unavailable")
            explicit_protected.add(canonical)

    admission = network.get("admission")
    admission_entries: dict[str, dict[str, str]] = {}
    admission_matches = False
    if admission is not None:
        if not isinstance(admission, dict):
            return _empty("unavailable")
        adm_backend = admission.get("backend")
        if not isinstance(adm_backend, str) or not SHA256_RE.fullmatch(adm_backend):
            return _empty("unavailable")
        rev = admission.get("revision")
        if type(rev) is not int or not (1 <= rev <= 2**53 - 1):
            return _empty("unavailable")
        entries = admission.get("entries")
        if not isinstance(entries, dict) or len(entries) > 1000:
            return _empty("unavailable")
        for k, v in entries.items():
            if not isinstance(k, str) or mac(k) != k or not isinstance(v, dict):
                return _empty("unavailable")
            lbl = v.get("label")
            if not isinstance(lbl, str) or not lbl.strip() or len(lbl) > 160:
                return _empty("unavailable")
            admission_entries[k] = {"label": lbl.strip()}
        admission_matches = adm_backend.lower() == backend_hash

    parsed_devices: dict[str, dict[str, Any]] = {}
    for item in raw_devices:
        if not isinstance(item, dict):
            return _empty("unavailable")
        m = mac(item.get("mac"))
        if not m:
            return _empty("unavailable")

        raw_addrs = item.get("addresses")
        if not isinstance(raw_addrs, list) or len(raw_addrs) > 16:
            return _empty("unavailable")
        addrs: list[str] = []
        for a in raw_addrs:
            clean_ip = address(a) if isinstance(a, str) else None
            if clean_ip is None:
                return _empty("unavailable")
            if clean_ip not in addrs:
                addrs.append(clean_ip)
        if len(addrs) > 16:
            return _empty("unavailable")

        raw_prot = item.get("protected")
        if raw_prot is not None and type(raw_prot) is not bool:
            return _empty("unavailable")
        is_prot = (raw_prot is True) or (m in explicit_protected)

        cand = item.get("candidate_name")
        if cand is None:
            cand = item.get("suggested_name")
        if cand is not None:
            if not isinstance(cand, str) or len(cand) > 160:
                return _empty("unavailable")
            cand = cand.strip() or None

        raw_warn = item.get("warnings", [])
        if (
            not isinstance(raw_warn, list)
            or len(raw_warn) > 16
            or any(not isinstance(w, str) for w in raw_warn)
        ):
            return _empty("unavailable")
        warns = [w for w in dict.fromkeys(raw_warn) if w in ALLOWED_WARNINGS]

        if m in parsed_devices:
            existing = parsed_devices[m]
            if any(
                existing[k] != v
                for k, v in (
                    ("addresses", addrs),
                    ("protected", is_prot),
                    ("candidate_name", cand),
                    ("warnings", warns),
                )
            ):
                return _empty("unavailable")
            continue

        parsed_devices[m] = {
            "mac": m,
            "addresses": addrs,
            "candidate_name": cand,
            "warnings": warns,
            "protected": is_prot,
        }

    sorted_devs = [parsed_devices[k] for k in sorted(parsed_devices)]
    devices_out: list[dict[str, Any]] = []
    for dev in sorted_devs:
        m = dev["mac"]
        entry = admission_entries.get(m) if admission_matches else None
        status = "protected" if dev["protected"] else ("approved" if entry else "unreviewed")
        devices_out.append(
            {
                "mac": m,
                "addresses": list(dev["addresses"]),
                "candidate_name": dev["candidate_name"],
                "warnings": list(dev["warnings"]),
                "status": status,
                "label": entry["label"] if entry else None,
            }
        )

    age = (now_dt - seen_dt).total_seconds()
    is_fresh = 0 <= age <= 180
    token = None
    if is_fresh:
        token_payload = {
            "backend": backend_hash,
            "protected_macs": sorted(explicit_protected),
            "devices": [
                {"addresses": d["addresses"], "mac": d["mac"], "protected": d["protected"]}
                for d in sorted_devs
            ],
            "observed_at": seen_dt.isoformat(),
        }
        token = hashlib.sha256(
            json.dumps(token_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    final_devices = devices_out
    counts = {
        k: sum(1 for d in final_devices if d["status"] == k)
        for k in ("protected", "approved", "unreviewed")
    }

    return {
        "status": "fresh" if is_fresh else "stale",
        "backend": backend_hash,
        "observed_at": seen_dt.isoformat(),
        "token": token,
        "devices": final_devices,
        "counts": counts,
    }


def observation_token(network: Any, now: Any) -> str:
    """Return deterministic observation token for fresh valid inventory."""
    result = classify(network, now)
    if result["status"] == "fresh":
        return result["token"]
    if result["status"] == "stale":
        raise DomainError("network_stale")
    raise DomainError("network_response")
