"""Native Kid Control profiles, explicitly adopted membership and strict time windows."""

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..domain.validation import DomainError, fields, timestamp
from .inventory import mac, yes
from .leases import identifier

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
CONFIG = ("name", "disabled", "paused", "rate-limit", *DAYS, *("tur-" + d for d in DAYS))


def minute(value):
    if not isinstance(value, str):
        raise DomainError("invalid_field", "time")
    value = value.strip()
    # RouterOS renders whole days and fractional hours as durations, including
    # 0s, 7h30m, 1d and 1d00:00:00. They still represent minute-aligned times.
    if value in {"1d", "1d00:00:00"}:
        return 1440
    duration = re.fullmatch(r"(?:(\d{1,2})h)?(?:(\d{1,4})m)?(?:0s)?", value)
    if duration and value:
        hour, minutes = int(duration[1] or 0), int(duration[2] or 0)
        if (duration[1] and minutes >= 60) or hour * 60 + minutes > 1440:
            raise DomainError("invalid_field", "time")
        return hour * 60 + minutes
    match = re.fullmatch(r"(\d{1,2})(?:(?::(\d{2}))(?::(00))?|h)?", value)
    if not match:
        raise DomainError("invalid_field", "time")
    hour, minutes = int(match[1]), int(match[2] or 0)
    if minutes > 59 or hour > 24 or (hour == 24 and minutes):
        raise DomainError("invalid_field", "time")
    return hour * 60 + minutes


def windows(value):
    """Canonical RouterOS allowed intervals; no ambiguous crossing of midnight."""
    if not isinstance(value, str) or len(value) > 300:
        raise DomainError("invalid_field", "schedule")
    intervals = []
    for part in value.split(",") if value.strip() else []:
        ends = part.split("-")
        if len(ends) != 2:
            raise DomainError("invalid_field", "schedule")
        start, end = map(minute, ends)
        if start >= end:
            raise DomainError("network_time_window")
        intervals.append((start, end))
    intervals.sort()
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    if len(merged) > 4:
        raise DomainError("invalid_field", "schedule")
    return ",".join(f"{a // 60:02}:{a % 60:02}-{b // 60:02}:{b % 60:02}" for a, b in merged)


def rate(value):
    if not isinstance(value, str):
        raise DomainError("invalid_field", "rate_limit")
    if value in {"", "0", "0/0"}:
        return ""
    if not re.fullmatch(r"[1-9]\d{0,3}[kM]?(?:/[1-9]\d{0,3}[kM]?)?", value):
        raise DomainError("invalid_field", "rate_limit")
    return value


def profile(row):
    result = {"name": row.get("name", "")}
    if not result["name"] or len(result["name"]) > 128:
        raise DomainError("network_response")
    for key in ("disabled", "paused"):
        if row.get(key, "false") not in {"true", "false", "yes", "no"}:
            raise DomainError("network_response")
        result[key] = "true" if yes(row.get(key)) else "false"
    result["rate-limit"] = rate(row.get("rate-limit", ""))
    for key in (*DAYS, *("tur-" + d for d in DAYS)):
        result[key] = windows(row.get(key, ""))
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def router_clock(tables, now, timezone):
    try:
        rows = tables["clock"]
        if len(rows) != 1 or rows[0]["time-zone-name"] != timezone:
            raise ValueError
        clock = rows[0]
        value = datetime.fromisoformat(clock["date"] + "T" + clock["time"])
        local = value.replace(
            tzinfo=ZoneInfo(timezone), fold=now.astimezone(ZoneInfo(timezone)).fold
        )
        if abs((local.astimezone(now.tzinfo) - now).total_seconds()) > 120:
            raise ValueError
        return local
    except (KeyError, ValueError, ZoneInfoNotFoundError):
        raise DomainError("network_clock") from None


def bind(tables, profile_id, selected_devices, protected_macs=()):
    profile_id = identifier(profile_id)
    if not isinstance(selected_devices, list) or not 1 <= len(selected_devices) <= 20:
        raise DomainError("invalid_field", "devices")
    ids = [identifier(v) for v in selected_devices]
    if len(set(ids)) != len(ids):
        raise DomainError("network_conflict")
    rows = [r for r in tables.get("kids", []) if r.get(".id") == profile_id]
    if len(rows) != 1:
        raise DomainError("network_conflict")
    current = profile(rows[0])
    devices = [r for r in tables.get("kid_devices", []) if r.get("user") == current["name"]]
    if len(devices) != len(ids) or {r.get(".id") for r in devices} != set(ids):
        raise DomainError("network_kid_membership")
    protected = set(protected_macs) | {
        mac(r.get("mac-address")) for r in tables.get("interfaces", [])
    }
    members = []
    for row in devices:
        identity = mac(row.get("mac-address"))
        if not identity or identity in protected:
            raise DomainError("network_protected")
        if yes(row.get("disabled")) or yes(row.get("dynamic")):
            raise DomainError("network_kid_membership")
        duplicates = [
            r for r in tables.get("kid_devices", []) if mac(r.get("mac-address")) == identity
        ]
        if len(duplicates) != 1:
            raise DomainError("network_conflict")
        members.append({"id": row[".id"], "mac": identity, "name": row.get("name", "")})
    return {
        "profile_id": profile_id,
        "name": current["name"],
        "devices": sorted(members, key=lambda v: v["id"]),
    }


def validate_binding(tables, binding, protected_macs=()):
    actual = bind(
        tables, binding["profile_id"], [d["id"] for d in binding["devices"]], protected_macs
    )
    if actual != {k: binding[k] for k in ("profile_id", "name", "devices")}:
        raise DomainError("network_kid_membership")
    return profile(next(r for r in tables["kids"] if r[".id"] == binding["profile_id"]))


def prepare(tables, binding, payload, now, timezone, protected_macs=()):
    fields(
        payload,
        {"member", "mode", "schedule", "rate_limit", "minutes", "until", "reason"},
        {"member", "mode"},
    )
    before = validate_binding(tables, binding, protected_macs)
    router_clock(tables, now, timezone)
    after = deepcopy(before)
    mode = payload["mode"]
    extras = set(payload) - {"member", "mode", "reason"}
    allowed = (
        {"schedule"}
        if mode == "schedule"
        else {"rate_limit"}
        if mode == "rate"
        else {"minutes", "until"}
        if mode in {"grant", "timed_pause"}
        else set()
    )
    if extras - allowed:
        raise DomainError("invalid_field", sorted(extras - allowed)[0])
    end = None
    if mode in {"pause", "resume", "timed_pause"}:
        after.update(disabled="false", paused="false" if mode == "resume" else "true")
    elif mode == "grant":
        after["disabled"] = "true"
    elif mode == "schedule":
        values = payload.get("schedule")
        if not isinstance(values, dict) or not values or set(values) - set(DAYS):
            raise DomainError("invalid_field", "schedule")
        for key, value in values.items():
            after[key], after["tur-" + key] = windows(value), ""
    elif mode == "rate":
        after["rate-limit"] = rate(payload.get("rate_limit"))
    else:
        raise DomainError("invalid_field", "mode")
    if mode in {"grant", "timed_pause"}:
        if ("minutes" in payload) == ("until" in payload):
            raise DomainError("invalid_field", "minutes")
        if "minutes" in payload:
            minutes = payload["minutes"]
            if type(minutes) is not int or not 1 <= minutes <= 1440:
                raise DomainError("invalid_field", "minutes")
            end = now + timedelta(minutes=minutes)
        else:
            end = timestamp(payload["until"], "until")
            if not timedelta(minutes=1) <= end - now <= timedelta(hours=24):
                raise DomainError("invalid_field", "until")
    elif "minutes" in payload or "until" in payload:
        raise DomainError("invalid_field", "until")
    return {
        "binding": deepcopy(binding),
        "mode": mode,
        "before": before,
        "after": after,
        "member": binding["member"],
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "until": end.isoformat() if end else None,
        "timezone": timezone,
        "diff": {
            key: {"before": before[key], "after": after[key]}
            for key in CONFIG
            if before[key] != after[key]
        },
        "warnings": ["configuration_not_connectivity", "ipv6_and_fasttrack_require_verification"],
    }
