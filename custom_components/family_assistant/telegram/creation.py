"""Bounded creation qualifiers; preserve the remaining user-authored title/name."""

import re

from ..domain.deadlines import CLOCK, DAY, NEGATED_SLOT, extract_due
from ..domain.validation import DomainError, number

REPORT_PHRASES = {
    "photo": (
        r"с\s+(?:фотоотч[её]том|фото\s*отч[её]том|фото)|"
        r"(?:нужен|требуется)\s+фото\s*отч[её]т|"
        r"(?:з|із|зі)\s+(?:фотозвітом|фото\s*звітом|фото)|"
        r"(?:потрібен|необхідний)\s+фото\s*звіт|"
        r"with\s+(?:a\s+)?photo(?:\s+report)?|photo\s+report\s+required"
    ),
    "text": (
        r"с\s+(?:текстовым\s+)?отч[её]том|(?:нужен|требуется)\s+(?:текстовый\s+)?отч[её]т|"
        r"(?:з|із|зі)\s+(?:текстовим\s+)?звітом|"
        r"(?:потрібен|необхідний)\s+(?:текстовий\s+)?звіт|"
        r"with\s+(?:a\s+)?(?:text\s+)?report|(?:text\s+)?report\s+required"
    ),
    "none": (
        r"без\s+отч[её]та|отч[её]т\s+не\s+нужен|"
        r"без\s+звіту|звіт\s+не\s+потрібен|"
        r"without\s+(?:a\s+)?report|no\s+report(?:\s+required)?|report\s+not\s+required"
    ),
}
REPORT_SUFFIXES = [
    (policy, re.compile(rf"(?:^|[\s,;]+)(?:{phrases})\s*[.!]?\s*$", re.I))
    for policy, phrases in REPORT_PHRASES.items()
]
# Explicit report words that do not fit a complete supported suffix must not
# silently become a title (e.g. "without photo report" or "with report maybe").
REPORT_SLOT = re.compile(
    r"\b(?:(?:с|без|з|із|зі|нужен|требуется|потрібен|необхідний|with|without|no)\s+"
    r"(?:a\s+)?(?:(?:текстов\w*|text|photo|фото)\s*)?"
    r"(?:фото)?(?:отч[её]т\w*|звіт\w*|report)\b|"
    r"(?:фото)?(?:отч[её]т|звіт|report)\s+(?:не|not|required)\b)",
    re.I,
)
PREFIXED_DAY = re.compile(
    rf"(?:^|[\s,;]+)(?:на|до|к|for|by|on)\s+(?:{DAY})(?:\s+{CLOCK})?\s*[.!]?\s*$",
    re.I,
)


def task_details(content, now, timezone):
    """Extract terminal report/deadline slots in either order, rejecting conflicts."""
    remaining = content.strip()
    policies = set()
    due = None

    def reports(value):
        while True:
            matched = min(
                (
                    (policy, match)
                    for policy, pattern in REPORT_SUFFIXES
                    if (match := pattern.search(value))
                ),
                key=lambda candidate: candidate[1].start(),
                default=None,
            )
            if matched is None:
                return value
            policy, match = matched
            value = value[: match.start()].rstrip(" ,;")
            if NEGATED_SLOT.search(value) or re.search(
                r"\b(?:no|with|without)(?:\s+a)?\s*$", value, re.I
            ):
                raise DomainError("invalid_field", "report_type")
            policies.add(policy)
            if len(policies) > 1:
                raise DomainError("invalid_field", "report_type")

    remaining = reports(remaining)
    title, due = extract_due(remaining, now, timezone)
    # Core deadline parsing already validates the whole explicit/relative slot.
    # Remove a bounded day preposition only after that validation succeeds.
    prefixed = PREFIXED_DAY.search(remaining) if due else None
    if prefixed:
        title = remaining[: prefixed.start()].rstrip(" ,;")
        if NEGATED_SLOT.search(title):
            raise DomainError("invalid_deadline")
    title = reports(title)
    if REPORT_SLOT.search(title):
        raise DomainError("invalid_field", "report_type")
    # "tomorrow with a report today" is two deadlines, not a longer title.
    checked_title, second_due = extract_due(title, now, timezone)
    if second_due:
        if due:
            raise DomainError("invalid_deadline")
        title, due = checked_title, second_due
    if not title.strip():
        raise DomainError("invalid_field", "title")
    payload = {"title": title, "due_at": due}
    if policies:
        payload["report_type"] = next(iter(policies))
    return payload


UNIT = (
    r"кг|килограмм(?:а|ов)?|кілограм(?:а|ів)?|kg|kilograms?|"
    r"г|гр|грамм(?:а|ов)?|грам(?:а|ів)?|g|grams?|"
    r"л|литр(?:а|ов)?|літр(?:а|ів)?|l|liters?|litres?|"
    r"мл|миллилитр(?:а|ов)?|мілілітр(?:а|ів)?|ml|milliliters?|millilitres?|"
    r"шт|штук(?:а|и)?|pcs?|pieces?|"
    r"уп|упак|упаков(?:ка|ки|ок)|пач(?:ка|ки|ек|ок)|packs?|"
    r"бутыл(?:ка|ки|ок)|пляш(?:ка|ки|ок)|bottles?|"
    r"бан(?:ка|ки|ок)|cans?"
)
QUANTITY = re.compile(rf"^(\d+(?:[.,]\d+)?)(?:\s+|(?=(?:{UNIT})\b))(.+)$", re.I)
UNIT_PREFIX = re.compile(rf"^({UNIT})\.?\s+(.+)$", re.I)


def shopping_details(content):
    """Keep pipe syntax exact; parse a leading decimal and optional known unit."""
    parts = [part.strip() for part in content.split("|")]
    if len(parts) > 3:
        raise DomainError("invalid_field", "shopping")
    name, quantity, unit = parts[0], 1.0, ""
    if len(parts) > 1:
        try:
            quantity = float(parts[1].replace(",", "."))
        except ValueError:
            raise DomainError("invalid_field", "quantity") from None
        if len(parts) == 3:
            unit = parts[2]
    elif match := QUANTITY.fullmatch(name):
        quantity = float(match[1].replace(",", "."))
        name = match[2].strip()
        if measured := UNIT_PREFIX.fullmatch(name):
            unit, name = measured[1], measured[2].strip()
        elif re.fullmatch(rf"(?:{UNIT})\.?", name, re.I):
            raise DomainError("invalid_field", "name")
        if re.match(r"^[\d+\-.,/]|^(?:and|и|та|і)\b", name, re.I):
            raise DomainError("invalid_field", "quantity")
    elif re.match(r"^[+\-.,\d]+(?:\s|$)|^[\d.,]+[eE/]|^(?:nan|inf(?:inity)?)\b", name, re.I):
        raise DomainError("invalid_field", "quantity")
    return {"name": name, "quantity": number(quantity, "quantity", 0.001), "unit": unit}
