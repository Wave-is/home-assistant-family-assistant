"""Small deterministic deadline grammar; the calendar is never delegated to an LLM."""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .validation import DomainError

WEEK = (
    r"(?:до\s+конца\s+(?:(следующей)\s+)?нед(?:ели|е)|"
    r"до\s+кінця\s+(?:(наступного)\s+)?тижня|"
    r"(?:by\s+)?(?:the\s+)?end\s+of\s+(next\s+)?(?:the\s+)?week)"
)
DAY = r"(?:сегодня|сьогодні|today|завтра|tomorrow|\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}(?:\.\d{4})?)"
CLOCK = (
    r"(?:(?:до|к|на|о|в|at|by)\s+)?\d{1,2}(?:[:.]\d{2}|"
    r"\s+(?:часов?\s+)?(?:утра|вечера|ранку|вечора)|\s*(?:am|pm))"
)
SUFFIX = re.compile(
    rf"(?:^|[,;]\s*|\s+)(?:(?:срок|термін|deadline)\s*:?\s*)?"
    rf"(?P<due>{WEEK}|{DAY}(?:\s+{CLOCK})?|{CLOCK})\s*[.!]?\s*$",
    re.I,
)


def parse_due(expression: str, now: datetime, timezone: str) -> str:
    local = now.astimezone(ZoneInfo(timezone))
    value = expression.casefold().strip(" .!")
    day = local.date()
    week = re.fullmatch(WEEK, value)
    clock = ""
    if week:
        day += timedelta(days=6 - day.weekday() + (7 if any(week.groups()) else 0))
    else:
        match = re.fullmatch(rf"(?P<day>{DAY})(?:\s+(?P<clock>{CLOCK}))?", value)
        if match:
            d = match["day"]
            clock = match["clock"] or ""
            if d in {"завтра", "tomorrow"}:
                day += timedelta(days=1)
            elif d not in {"сегодня", "сьогодні", "today"}:
                try:
                    if "-" in d:
                        day = date.fromisoformat(d)
                    else:
                        parts = [int(p) for p in d.split(".")]
                        day = date(parts[2] if len(parts) == 3 else day.year, parts[1], parts[0])
                except ValueError:
                    raise DomainError("invalid_deadline") from None
        elif re.fullmatch(CLOCK, value):
            clock = value
        else:
            raise DomainError("invalid_deadline")
    hour, minute = 20, 0
    if clock:
        digits = re.search(r"(\d{1,2})(?:[:.](\d{2}))?", clock)
        hour, minute = int(digits[1]), int(digits[2] or 0)
        marker = re.search(r"утра|вечера|ранку|вечора|am|pm", clock)
        if marker:
            if not 1 <= hour <= 12:
                raise DomainError("invalid_deadline")
            hour = hour % 12 + (12 if marker[0] in {"вечера", "вечора", "pm"} else 0)
    try:
        result = datetime.combine(day, time(hour, minute), ZoneInfo(timezone))
    except ValueError:
        raise DomainError("invalid_deadline") from None
    # Reject nonexistent and ambiguous local clock readings, rather than picking a DST fold.
    if (
        result.astimezone(UTC).astimezone(result.tzinfo).replace(tzinfo=None)
        != result.replace(tzinfo=None)
        or result.utcoffset() != result.replace(fold=1).utcoffset()
        or result <= local
    ):
        raise DomainError("invalid_deadline")
    return result.isoformat()


def extract_due(title: str, now: datetime, timezone: str) -> tuple[str, str | None]:
    match = SUFFIX.search(title)
    if match:
        return title[: match.start()].strip(" ,;."), parse_due(match["due"], now, timezone)
    # A deadline marker is not silently swallowed into the title.
    if re.search(r"\b(?:срок|термін|deadline)\b", title, re.I):
        raise DomainError("invalid_deadline")
    return title.strip(), None
