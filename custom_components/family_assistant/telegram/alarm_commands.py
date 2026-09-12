"""Explicit member and weekday-group alarm edits without model inference."""

import re

from ..domain.validation import DomainError
from ..domain.weekdays import parse_days
from .intents import find_member

_REQUEST = re.compile(
    r"^(поставь|установи|заведи|включи|выключи|отключи|увімкни|вимкни|"
    r"встанови|постав|set|enable|disable|turn\s+on|turn\s+off)\s+"
    r"(?:(.+?)\s+)?(?:будильник|alarm)\s*(.*)$",
    re.I,
)
_PERIOD = re.compile(
    r"(?<!\w)(?:(?P<weekdays>будние\s+дни|будни|будням|будні|буднях|weekdays)|"
    r"(?P<weekends>выходные\s+дни|выходные|выходным|вихідні|вихідних|weekends?)|"
    r"(?P<daily>каждый\s+день|кожен\s+день|ежедневно|щодня|every\s+day|daily))(?!\w)",
    re.I,
)
_DAYS = {"weekdays": list(range(5)), "weekends": [5, 6], "daily": list(range(7))}
_OFF = {"выключи", "отключи", "вимкни", "disable", "turn off"}
_CONNECTORS = re.compile(r"^(?:(?:и|та|і|and|на|в|у|по|on)\s*|[,;]\s*)*$", re.I)


def _clock(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,2}[:.]\d{2}", value):
        raise DomainError("invalid_field", "time")
    hour, minute = (int(part) for part in re.split(r"[:.]", value))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise DomainError("invalid_field", "time")
    return f"{hour:02d}:{minute:02d}"


def _operations(state, view, member, groups, *, enabled):
    operations, seen = [], set()
    for days, clock in groups:
        key = tuple(days)
        if key in seen or any(set(days) & set(previous) for previous in seen):
            raise DomainError("ambiguous_command")
        seen.add(key)
        candidates = [
            row for row in view["alarms"] if row["member"] == member and row["days"] == days
        ]
        if len(candidates) > 1:
            raise DomainError("ambiguous_command")
        existing = candidates[0] if candidates else None
        if clock is None:
            if existing is None:
                raise DomainError("not_found" if not enabled else "context_required")
            action = "alarms.enable"
            payload = {"id": existing["id"], "revision": existing["revision"], "enabled": enabled}
        else:
            if not enabled:
                raise DomainError("ambiguous_command")
            action = "alarms.save"
            payload = {
                "member": member,
                "days": days,
                "time": clock,
                "enabled": True,
                "timezone": existing["timezone"] if existing else state["settings"]["timezone"],
            }
            if existing:
                payload.update(id=existing["id"], revision=existing["revision"])
        operations.append({"action": action, "payload": payload})
    return operations


def parsed(state, view, content):
    """Return a bounded atomic command list, or None for unrelated discussion."""
    if content.casefold().startswith("/alarm "):
        fields = [part.strip() for part in content.partition(" ")[2].split("|")]
        if len(fields) != 3:
            raise DomainError("ambiguous_command")
        member = find_member(state, fields[0])
        days = parse_days(fields[1])
        control = fields[2].casefold()
        enabled = control not in {"off", "выкл", "вимк"}
        clock = (
            None if control in {"on", "off", "вкл", "выкл", "увімк", "вимк"} else _clock(control)
        )
        return _operations(state, view, member, [(days, clock)], enabled=enabled)
    match = _REQUEST.fullmatch(content.strip(" .!"))
    if not match:
        return None
    verb, before, remainder = match.groups()
    periods = list(_PERIOD.finditer(remainder))
    if not periods or len(periods) > 2:
        raise DomainError("invalid_alarm_days")
    leading = remainder[: periods[0].start()].strip()
    if before:
        if not _CONNECTORS.fullmatch(leading):
            raise DomainError("ambiguous_command")
        member_text = before
    else:
        member_text = re.sub(r"\s+(?:на|в|у|по|on)$", "", leading, flags=re.I)
    member = find_member(state, member_text)
    enabled = verb.casefold() not in _OFF
    groups = []
    for index, period in enumerate(periods):
        end = periods[index + 1].start() if index + 1 < len(periods) else len(remainder)
        segment = remainder[period.end() : end].strip()
        clock_match = re.match(r"^(?:(?:на|в|о|at)\s+)?(\d{1,2}[:.]\d{2})", segment, re.I)
        clock = _clock(clock_match[1]) if clock_match else None
        trailing = segment[clock_match.end() :].strip() if clock_match else segment
        if not _CONNECTORS.fullmatch(trailing):
            raise DomainError("ambiguous_command")
        groups.append((_DAYS[period.lastgroup].copy(), clock))
    if len(groups) == 2 and groups[0][1] is None and groups[1][1] is not None:
        groups[0] = (groups[0][0], groups[1][1])
    return _operations(state, view, member, groups, enabled=enabled)
