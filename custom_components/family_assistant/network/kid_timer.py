"""Fixed-template, scoped RouterOS expiry and startup guards; never a shell API."""

import re
from zoneinfo import ZoneInfo

from ..domain.validation import DomainError, timestamp
from .kids import digest
from .leases import identifier


def quote(value):
    if not isinstance(value, str) or len(value) > 128 or any(ord(c) < 32 for c in value):
        raise DomainError("invalid_field", "profile_name")
    # RouterOS quoted strings interpolate $ and commands; encode every byte.
    try:
        return '"' + "".join(f"\\{b:02X}" for b in value.encode("utf-8")) + '"'
    except UnicodeError:
        raise DomainError("invalid_field", "profile_name") from None


def timer_name(plan, kind):
    if kind not in {"expiry", "boot"}:
        raise DomainError("network_operation")
    return "fa-kid-" + digest([plan["backend"], plan["id"], plan["member"]])[:24] + "-" + kind


def name(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"fa-kid-[0-9a-f]{24}-(?:expiry|boot)", value
    ):
        raise DomainError("network_operation")
    return value


def specifications(plan):
    target = identifier(plan["binding"]["profile_id"])
    end = timestamp(plan["until"], "until")
    epoch_ns = int(end.timestamp()) * 1_000_000_000
    local = end.astimezone(ZoneInfo(plan["timezone"]))
    before, after = plan["before"], plan["after"]
    # Only the temporary mode is restored, preserving any independently edited
    # schedule/rate. A recreated, renamed or manually retoggled profile is not touched.
    expected = (
        f"([/ip kid-control get $p disabled] = {after['disabled']}) && "
        f"([/ip kid-control get $p paused] = {after['paused']})"
    )
    restore = (
        f":local p [/ip kid-control find where name={quote(before['name'])}]; "
        f':if (([:len $p] = 1) && ([:tostr $p] = "{target}")) do={{ '
        f":if ({expected}) do={{ "
        f"/ip kid-control set $p disabled={'yes' if before['disabled'] == 'true' else 'no'}; "
        f"/ip kid-control {'pause' if before['paused'] == 'true' else 'resume'} $p; "
        "} }; "
    )
    cleanup = " ".join(
        f'/system scheduler remove [find where name="{timer_name(plan, kind)}"];'
        for kind in ("expiry", "boot")
    )
    result = []
    for kind in ("expiry", "boot"):
        source = restore + cleanup
        if kind == "expiry":
            source = f":if ([:tonsec [:timestamp]] >= {epoch_ns}) do={{ " + source + " }"
        result.append(
            {
                "name": timer_name(plan, kind),
                "on-event": source,
                "start-date": local.strftime("%Y-%m-%d") if kind == "expiry" else "1970-01-01",
                "start-time": local.strftime("%H:%M:%S") if kind == "expiry" else "startup",
                "interval": "5s" if kind == "expiry" else "0s",
                "policy": "read,write",
                "disabled": "false",
                "comment": "Family Assistant temporary Kid Control expiry",
            }
        )
    return result


def matches(row, spec):
    if row.get("name") != spec["name"] or row.get("on-event") != spec["on-event"]:
        return False
    if row.get("disabled") not in {"false", "no"} or set(row.get("policy", "").split(",")) != {
        "read",
        "write",
    }:
        return False
    if row.get("start-time") != spec["start-time"]:
        return False
    if spec["start-time"] != "startup" and row.get("start-date") != spec["start-date"]:
        return False
    interval = row.get("interval")
    return interval in ({"5s", "00:00:05"} if spec["interval"] == "5s" else {"0s", "00:00:00"})
