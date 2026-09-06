"""Pure domain validation and evaluation for routine execution conditions."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .household import timezone
from .validation import DomainError, fields

MODES = frozenset({"normal", "holidays", "guests", "ill", "vacation"})
ENTITY_REGEX = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
CLOCK_REGEX = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _clock(value: Any, field_name: str) -> time:
    if not isinstance(value, str) or not CLOCK_REGEX.fullmatch(value):
        raise DomainError("invalid_field", field_name)
    return time(int(value[:2]), int(value[3:5]))


def validate(condition: Any) -> dict:
    _, normalized = _validate_node(condition, 1, [20])
    return normalized


def _validate_node(cond: Any, depth: int, budget: list[int]) -> tuple[int, dict]:
    if not isinstance(cond, dict) or depth > 3 or budget[0] <= 0:
        raise DomainError("invalid_field", "conditions" if depth > 3 else "condition")
    budget[0] -= 1
    kind = cond.get("kind")
    if not isinstance(kind, str) or kind not in {
        "mode",
        "entity_state",
        "time_window",
        "all",
        "any",
    }:
        raise DomainError("invalid_field", "kind")
    negate = cond.get("negate", False)
    if type(negate) is not bool:
        raise DomainError("invalid_field", "negate")

    if kind == "mode":
        fields(cond, {"kind", "negate", "mode"}, {"kind", "mode"})
        mode = cond["mode"]
        if not isinstance(mode, str) or mode not in MODES:
            raise DomainError("invalid_field", "mode")
        return 1, {"kind": "mode", "mode": mode, "negate": negate}

    if kind == "entity_state":
        fields(
            cond,
            {"kind", "negate", "entity_id", "state", "max_age_seconds"},
            {"kind", "entity_id", "state"},
        )
        entity_id = cond["entity_id"]
        if (
            not isinstance(entity_id, str)
            or len(entity_id) > 255
            or not ENTITY_REGEX.fullmatch(entity_id)
        ):
            raise DomainError("invalid_field", "entity_id")
        state = cond["state"]
        if (
            not isinstance(state, str)
            or not state.strip()
            or len(state) > 100
            or state in {"unknown", "unavailable"}
        ):
            raise DomainError("invalid_field", "state")
        max_age = cond.get("max_age_seconds", 120)
        if type(max_age) is not int or not 1 <= max_age <= 3600:
            raise DomainError("invalid_field", "max_age_seconds")
        return 1, {
            "kind": "entity_state",
            "entity_id": entity_id,
            "state": state,
            "max_age_seconds": max_age,
            "negate": negate,
        }

    if kind == "time_window":
        fields(
            cond,
            {"kind", "negate", "start", "end", "timezone"},
            {"kind", "start", "end", "timezone"},
        )
        start_t, end_t = _clock(cond["start"], "start"), _clock(cond["end"], "end")
        if start_t == end_t:
            raise DomainError("invalid_field", "time_window")
        tz_name = timezone(cond["timezone"])
        return 1, {
            "kind": "time_window",
            "start": cond["start"],
            "end": cond["end"],
            "timezone": tz_name,
            "negate": negate,
        }

    # all / any
    fields(cond, {"kind", "negate", "conditions"}, {"kind", "conditions"})
    children = cond["conditions"]
    if not isinstance(children, list) or not 1 <= len(children) <= 19:
        raise DomainError("invalid_field", "conditions")
    total_nodes = 1
    normalized_children = []
    for c in children:
        sub_nodes, norm_c = _validate_node(c, depth + 1, budget)
        total_nodes += sub_nodes
        normalized_children.append(norm_c)
    return total_nodes, {"kind": kind, "conditions": normalized_children, "negate": negate}


def _eval_node(cond: dict, now: datetime, modes_set: set[str], obs: dict) -> bool | None:
    kind = cond["kind"]
    res: bool | None = None
    if kind == "mode":
        res = cond["mode"] in modes_set
    elif kind == "entity_state":
        entity_id = cond["entity_id"]
        entry = obs.get(entity_id) if isinstance(obs, dict) else None
        if not isinstance(entry, dict) or "state" not in entry or "observed_at" not in entry:
            res = None
        else:
            live_state = entry["state"]
            obs_at = entry["observed_at"]
            if (
                not isinstance(live_state, str)
                or not live_state.strip()
                or len(live_state) > 100
                or live_state in {"unknown", "unavailable"}
            ):
                res = None
            else:
                try:
                    dt = datetime.fromisoformat(obs_at) if isinstance(obs_at, str) else obs_at
                    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
                        res = None
                    else:
                        age = (now.astimezone(UTC) - dt.astimezone(UTC)).total_seconds()
                        if age < -5.0 or age > cond["max_age_seconds"]:
                            res = None
                        else:
                            res = live_state == cond["state"]
                except (ValueError, TypeError, OverflowError):
                    res = None
    elif kind == "time_window":
        local_now = now.astimezone(ZoneInfo(cond["timezone"]))
        cur = local_now.timetz().replace(tzinfo=None)
        start = _clock(cond["start"], "start")
        end = _clock(cond["end"], "end")
        res = cur >= start and cur < end if start < end else cur >= start or cur < end
    elif kind == "all":
        has_unknown = False
        res = True
        for c in cond["conditions"]:
            sub = _eval_node(c, now, modes_set, obs)
            if sub is False:
                res = False
                break
            if sub is None:
                has_unknown = True
        if res is not False and has_unknown:
            res = None
    elif kind == "any":
        has_unknown = False
        res = False
        for c in cond["conditions"]:
            sub = _eval_node(c, now, modes_set, obs)
            if sub is True:
                res = True
                break
            if sub is None:
                has_unknown = True
        if res is not True and has_unknown:
            res = None

    if res is not None and cond.get("negate", False):
        res = not res
    return res


def evaluate(condition: Any, now: datetime, modes: list | set, observations: dict) -> bool | None:
    norm = validate(condition)
    try:
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError
        now = now.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        raise DomainError("invalid_field", "now") from None
    if not isinstance(modes, (list, set, frozenset)):
        raise DomainError("invalid_field", "modes")
    for m in modes:
        if not isinstance(m, str) or m not in MODES:
            raise DomainError("invalid_field", "modes")
    if not isinstance(observations, dict):
        raise DomainError("invalid_field", "observations")
    try:
        return _eval_node(norm, now, set(modes), observations)
    except OverflowError:
        raise DomainError("command_too_large") from None
