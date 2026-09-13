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
COUNT = r"(?:\d{1,3}|один|одна|одну|два|две|три|четыре|чотири|дві|one|two|three|four|a|an)"
UNIT = (
    r"(?:день|дня|дней|дні|днів|неделя|недели|неделю|недель|"
    r"тиждень|тижні|тижня|тижнів|days?|weeks?)"
)
DURATION = rf"(?:(?P<count>{COUNT})\s+)?(?P<unit>{UNIT})(?:\s+(?P<clock>{CLOCK}))?"
DURATION_MARKER = (
    r"(?:срок(?:\s+(?:на\s+выполнение|выполнения))?\s*:?\s*|"
    r"термін(?:\s+виконання)?\s*:?\s*|deadline\s*:?\s*|"
    r"на\s+выполнение\s*:?\s*|в\s+течение\s+|протягом\s+|через\s+|in\s+|within\s+)"
)
SUFFIX = re.compile(
    rf"(?:^|[,;]\s*|\s+)(?:(?:срок|термін|deadline)\s*:?\s*)?"
    rf"(?P<due>{WEEK}|{DAY}(?:\s+{CLOCK})?|{CLOCK}|{DURATION_MARKER}{DURATION})\s*[.!]?\s*$",
    re.I,
)


EXPLICIT_MARKER = re.compile(
    r"\b(?:срок(?:\s+(?:на\s+выполнение|выполнения))?|термін(?:\s+виконання)?|deadline)\b\s*:?\s*",
    re.I,
)
RELATIVE_MARKER = re.compile(
    # Detection is deliberately broader than accepted count syntax. A fraction,
    # malformed sign or long number phrase must reach validation, not allow a
    # later clock to be interpreted as an independent deadline for today.
    rf"\b{DURATION_MARKER}(?=(?:[^,.;:!?\n]|(?<=\d)[.,](?=\d))*\b{UNIT}\b)",
    re.I,
)
NEGATED_SLOT = re.compile(r"\b(?:не|ні|not|never|without|don't|do\s+not)\s*$", re.I)


def parse_due(expression: str, now: datetime, timezone: str) -> str:
    local = now.astimezone(ZoneInfo(timezone))
    value = expression.casefold().strip(" .!")
    day = local.date()
    week = re.fullmatch(WEEK, value)
    clock = ""
    duration = re.fullmatch(rf"(?:{DURATION_MARKER})?(?:(?:на|for)\s+)?{DURATION}", value)
    if duration:
        # Legacy relative edits count from the received local calendar day,
        # not from the task's old deadline. The exact resolved date is replayed.
        words = {
            "один": 1,
            "одна": 1,
            "одну": 1,
            "one": 1,
            "a": 1,
            "an": 1,
            "два": 2,
            "две": 2,
            "дві": 2,
            "two": 2,
            "три": 3,
            "three": 3,
            "четыре": 4,
            "чотири": 4,
            "four": 4,
        }
        raw = duration["count"]
        count = int(raw) if raw and raw.isdigit() else words.get(raw or "", 1)
        days = count * (7 if duration["unit"].startswith(("недел", "тиж", "week")) else 1)
        if not 1 <= days <= 365:
            raise DomainError("invalid_deadline")
        try:
            day += timedelta(days=days)
        except OverflowError:
            raise DomainError("invalid_deadline") from None
        clock = duration["clock"] or ""
    elif week:
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
    # Read an explicit deadline as one complete slot before trying a clock
    # suffix. Otherwise an invalid "in 1000 days at 17:30" silently becomes
    # today's 17:30, or "not within a week" loses its negation into the title.
    explicit = EXPLICIT_MARKER.search(title)
    relative = RELATIVE_MARKER.search(title)
    marked = min((m for m in (explicit, relative) if m), key=lambda m: m.start(), default=None)
    if marked:
        prefix = title[: marked.start()]
        if NEGATED_SLOT.search(prefix.rstrip(" ,;:")):
            raise DomainError("invalid_deadline")
        value = title[marked.end() :] if marked is explicit else title[marked.start() :]
        return prefix.strip(" ,;.:"), parse_due(value, now, timezone)
    match = SUFFIX.search(title)
    if match:
        if NEGATED_SLOT.search(title[: match.start()].rstrip(" ,;:")):
            raise DomainError("invalid_deadline")
        return title[: match.start()].strip(" ,;."), parse_due(match["due"], now, timezone)
    # A deadline marker is not silently swallowed into the title.
    if re.search(r"\b(?:срок|термін|deadline)\b", title, re.I):
        raise DomainError("invalid_deadline")
    return title.strip(), None
