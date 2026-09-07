"""Small deterministic weekday expression grammar, Monday=0; no model arithmetic."""

import re

from .validation import DomainError

GROUPS = (
    (
        tuple(range(5)),
        {
            "weekdays",
            "on weekdays",
            "будни",
            "в будни",
            "по будням",
            "будние дни",
            "будні",
            "у будні",
            "в будні",
            "по буднях",
        },
    ),
    (
        (5, 6),
        {
            "weekends",
            "on weekends",
            "weekend",
            "выходные",
            "по выходным",
            "в выходные",
            "выходные дни",
            "вихідні",
            "у вихідні",
            "на вихідних",
        },
    ),
    (
        tuple(range(7)),
        {"daily", "every day", "everyday", "ежедневно", "каждый день", "щодня", "кожен день"},
    ),
)
DAYS = (
    {"monday", "mon", "понедельник", "понедельникам", "пн", "понеділок", "понеділках"},
    {"tuesday", "tue", "вторник", "вторникам", "вт", "вівторок", "вівторках"},
    {"wednesday", "wed", "среда", "среду", "средам", "ср", "середа", "середу", "середах"},
    {"thursday", "thu", "четверг", "четвергам", "чт", "четвер", "четвергах"},
    {"friday", "fri", "пятница", "пятницу", "пятницам", "пт", "п'ятниця", "п'ятницю", "п'ятницях"},
    {"saturday", "sat", "суббота", "субботу", "субботам", "сб", "субота", "суботу", "суботах"},
    {"sunday", "sun", "воскресенье", "воскресеньям", "вс", "неділя", "неділю", "неділях"},
)


def parse_days(expression):
    if not isinstance(expression, str) or not 1 <= len(expression) <= 160:
        raise DomainError("invalid_alarm_days")
    value = " ".join(expression.casefold().replace("’", "'").split()).strip(" .!")
    for days, aliases in GROUPS:
        if value in aliases:
            return list(days)
    result = set()
    for part in re.split(r"\s*(?:[,;/]|\s+(?:and|и|та|і)\s+)\s*", value):
        part = re.sub(r"^(?:on|every|в|у|по|каждый|каждую|каждое|кожен|кожну)\s+", "", part)
        match = [index for index, aliases in enumerate(DAYS) if part in aliases]
        if not match:
            raise DomainError("invalid_alarm_days")
        result.update(match)
    if not result:
        raise DomainError("invalid_alarm_days")
    return sorted(result)


def grounded_days(expression, content):
    """Recognize typography, but never a translated or embedded-in-word phrase."""
    days = parse_days(expression)
    if not isinstance(content, str) or len(content) > 4096:
        raise DomainError("invalid_alarm_days")
    literal = r"\s+".join(re.escape(word) for word in expression.replace("’", "'").split())
    if not re.search(r"(?<!\w)" + literal + r"(?!\w)", content.replace("’", "'"), re.I):
        raise DomainError("invalid_alarm_days")
    return days


def day_expressions(content):
    """Bounded literal candidates, not intents: the model still selects the requested group.

    Never inspect a quote or history here. Only expressions this grammar can parse
    are offered; a candidate is not permission to execute an alarm command.
    """
    if not isinstance(content, str) or len(content) > 4096:
        return []
    aliases = set().union(*(aliases for _, aliases in GROUPS), *DAYS)
    alternatives = [re.escape(alias).replace(r"\ ", r"\s+") for alias in aliases]
    pattern = (
        r"(?<!\w)(?:" + "|".join(sorted(alternatives, key=lambda s: (-len(s), s))) + r")(?!\w)"
    )
    spans = []
    for match in re.finditer(pattern, content.replace("’", "'"), re.I):
        spans.append(match.span())
        if len(spans) > 64:
            return []
    result = []
    for start, _ in spans:
        for _, end in spans:
            if not 1 <= end - start <= 160:
                continue
            candidate = content[start:end]
            try:
                parse_days(candidate)
            except DomainError:
                continue
            if candidate not in result:
                result.append(candidate)
                if len(result) > 64:
                    return []
    return result
