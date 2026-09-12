"""Deterministic Russian parser for Family Court Telegram messages."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .patterns import (
    APPEAL_PATTERNS,
    CASE_PATTERNS,
    EXPLICIT_NEGATIVE_PATTERNS,
    EXPLICIT_POSITIVE_PATTERNS,
    HELP_PATTERNS,
    HISTORY_PATTERNS,
    NEGATION_WORDS,
    NEGATIVE_CONSTRUCTION_PATTERNS,
    NEGATIVE_PATTERNS,
    POSITIVE_PATTERNS,
    RULES_PATTERNS,
    STATS_ALL_PATTERNS,
    UNDO_PATTERNS,
)

# Explicit namespaces owned by the separate family assistant must never be
# interpreted as a score, even when their arguments contain a child's name or
# negative wording such as "не забыл". Keep this small guard in the Court
# parser itself because Home Assistant dispatches the same Telegram event to
# independent listeners without ordering guarantees.
ASSISTANT_COMMANDS = frozenset(
    {
        "/award",
        "/reverse",
        "/courtresolve",
        "/ai",
        "/ask",
        "/commands",
        "/home",
        "/energy",
        "/power",
        "/solar",
        "/temp",
        "/active",
        "/internet",
        "/music",
        "/tv",
        "/intercom",
        "/weather",
        "/phones",
        "/safety",
        "/climate",
        "/kettle",
        "/gate",
        "/tasks",
        "/mine",
        "/shopping",
        "/alarms",
        "/alarm",
        "/bought",
        "/approvebuy",
        "/rejectbuy",
        "/archive",
        "/edit",
        "/memory",
        "/remember",
        "/forgetmemory",
        "/forget_memory",
        "/дом",
        "/батарея",
        "/энергия",
        "/климат",
        "/чайник",
        "/вытяжка",
        "/калитка",
        "/температура",
        "/свет",
        "/электричество",
        "/включено",
        "/солнце",
        "/панели",
        "/насос",
        "/канализация",
        "/тв",
        "/музыка",
        "/теплыйпол",
        "/теплый_пол",
        "/авто",
        "/сеть",
        "/роутер",
        "/домофон",
        "/погода",
        "/телефоны",
        "/безопасность",
        "/дела",
        "/мои",
        "/задача",
        "/напомнить",
        "/покупки",
        "/будильники",
        "/будильник",
        "/куплено",
        "/одобритьпокупку",
        "/отклонитьпокупку",
        "/архив",
        "/изменитьзадачу",
        "/память",
        "/запомни",
        "/забудьпамять",
        "/забыть_память",
        "/готово",
        "/принял",
        "/принять",
        "/переделать",
        "/продлить",
        "/отменитьзадачу",
        "/подтвердить",
        "/forget",
        "/забыть",
        "/voice",
        "/команды",
        "/помощник",
        "/start",
    }
)

# Natural-language namespaces owned by Family Assistant.  These guards must
# precede all Court heuristics because the same Telegram event is delivered to
# two independent listeners with no ordering guarantee.  Requiring an explicit
# task/reminder verb keeps genuine free-form assessments available to Court.
ASSISTANT_TASK_PATTERNS: tuple[str, ...] = (
    r"^(?:поставь|поставить|создай|создать|назначь|назначить|задай|задать)\s+"
    r"(?:(?:\d+|две|два|три|четыре|пять|несколько)\s+)?задач(?:и)?\b",
    r"^(?:поставь|создай|назначь|задай)\s+"
    r"(?:[^\s:,-]+\s+){1,2}задачу\b",
    r"^(?:поставь|создай|назначь|задай)\s+задачу\s+"
    r"(?:для\s+)?[^:,-]{1,80}\s*[:,-]",
    r"^поручи\s+[^:,-]{1,80}\s*[:,-]",
    r"^напомни\b",
    r"^попроси\s+[^:,-]{1,80}\s+купить\b",
    r"^добавь\s+для\s+[^:,-]{1,80}\s+в\s+(?:список\s+)?покупок\b",
    r"^добавь\s+в\s+(?:список\s+)?покупок\b",
    r"^добавь\s+.+\s+в\s+(?:список\s+)?покупок\s*[.!?]*$",
)

# Contextual corrections belong to Family Assistant because only it has the
# verified Telegram reply metadata and task ID.  Court receives the same flat
# event independently and must not turn a pronoun such as "её" into a request
# for a child name.
ASSISTANT_CONTEXTUAL_CORRECTION_PATTERNS: tuple[str, ...] = (
    r"^(?:исправ\w*|поправ\w*|убер\w*|сним\w*|отмен\w*|верн\w*)\b"
    r"(?=.{0,100}\b(?:тогда|этот|эту|этого|его|ее|её|задач\w*)\b)"
    r"(?=.{0,100}\bминус\w*\b).{0,120}$",
)


@dataclass(frozen=True, slots=True)
class Assessment:
    """One unambiguous child assessment extracted from a clause."""

    child: str
    kind: str
    reason: str
    clause: str
    confidence: str


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    """Structured parser outcome."""

    action: str
    assessments: tuple[Assessment, ...] = ()
    child: str | None = None
    detail: str | None = None


def normalize_text(text: str) -> str:
    """Normalize punctuation/case while retaining Russian word boundaries."""

    value = (text or "").strip().lower().replace("ё", "е")
    value = value.replace("−", "-").replace("—", "-").replace("–", "-")
    value = re.sub(r"[\t\r\n]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def member_patterns(members: Iterable[dict] | None) -> dict[str, tuple[str, ...]]:
    """Match configured names/aliases without inferring family identities."""
    result = {}
    for member in members or ():
        if not member.get("active", True) or member.get("role") == "guest":
            continue
        names = (member["id"], member.get("name", ""), *member.get("aliases", []))
        result[member["id"]] = tuple(
            rf"(?<!\w){re.escape(normalize_text(name))}(?!\w)"
            for name in names
            if isinstance(name, str) and name.strip()
        )
    return result


def _children_in(text: str, child_patterns: dict[str, tuple[str, ...]]) -> list[str]:
    found: list[tuple[int, str]] = []
    for child, patterns in child_patterns.items():
        positions = [
            match.start()
            for pattern in patterns
            for match in re.finditer(pattern, text, flags=re.IGNORECASE)
        ]
        if positions:
            found.append((min(positions), child))
    return [child for _, child in sorted(found)]


def _is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 40) : start]
    words = re.findall(r"[a-zа-я0-9]+", prefix, flags=re.IGNORECASE)[-3:]
    return any(word in NEGATION_WORDS for word in words)


def _unnegated_matches(text: str, patterns: Iterable[str]) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if not _is_negated(text, match.start()):
                matches.append(match)
    return matches


def _raw_assessment_marker(text: str) -> bool:
    return _matches_any(
        text,
        (
            *EXPLICIT_POSITIVE_PATTERNS,
            *EXPLICIT_NEGATIVE_PATTERNS,
            *POSITIVE_PATTERNS,
            *NEGATIVE_CONSTRUCTION_PATTERNS,
            *NEGATIVE_PATTERNS,
        ),
    )


def _classify_clause(
    clause: str, child: str, child_patterns: dict[str, tuple[str, ...]]
) -> Assessment | None:
    explicit_positive = _unnegated_matches(clause, EXPLICIT_POSITIVE_PATTERNS)
    explicit_negative = _unnegated_matches(clause, EXPLICIT_NEGATIVE_PATTERNS)

    if explicit_positive and explicit_negative:
        return None
    if explicit_positive:
        return Assessment(
            child=child,
            kind="plus",
            reason=_extract_reason(clause, child, "plus", child_patterns),
            clause=clause,
            confidence="explicit",
        )
    if explicit_negative:
        return Assessment(
            child=child,
            kind="minus",
            reason=_extract_reason(clause, child, "minus", child_patterns),
            clause=clause,
            confidence="explicit",
        )

    positive = _unnegated_matches(clause, POSITIVE_PATTERNS)
    negative = [
        match
        for pattern in NEGATIVE_CONSTRUCTION_PATTERNS
        for match in re.finditer(pattern, clause, flags=re.IGNORECASE)
    ]
    negative.extend(_unnegated_matches(clause, NEGATIVE_PATTERNS))

    if positive and negative:
        return None
    if positive:
        return Assessment(
            child=child,
            kind="plus",
            reason=_extract_reason(clause, child, "plus", child_patterns),
            clause=clause,
            confidence="phrase",
        )
    if negative:
        return Assessment(
            child=child,
            kind="minus",
            reason=_extract_reason(clause, child, "minus", child_patterns),
            clause=clause,
            confidence="phrase",
        )
    return None


def _extract_reason(
    clause: str, child: str, kind: str, child_patterns: dict[str, tuple[str, ...]]
) -> str:
    original = clause.strip(" .,!?:;-")
    after_for = re.search(r"\bза(?:\s+то\s*,?\s*что)?\s+(.+)$", original, flags=re.IGNORECASE)
    if after_for:
        reason = after_for.group(1).strip(" .,!?:;-")
        if reason:
            return reason[:240]

    comma_parts = [part.strip(" .,!?:;-") for part in original.split(",")]
    if len(comma_parts) > 1 and len(comma_parts[-1].split()) >= 2:
        return comma_parts[-1][:240]

    cleaned = original
    for pattern in child_patterns[child]:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    patterns = (
        (*EXPLICIT_POSITIVE_PATTERNS, *POSITIVE_PATTERNS)
        if kind == "plus"
        else (
            *EXPLICIT_NEGATIVE_PATTERNS,
            *NEGATIVE_CONSTRUCTION_PATTERNS,
            *NEGATIVE_PATTERNS,
        )
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:сегодня|опять|пожалуйста|получает|добавь|давай|вот)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?:;-")
    return (cleaned or "причина не указана")[:240]


def _split_multi_child(text: str) -> list[str]:
    clauses = re.split(
        r"\s*(?:;|\n|,\s*(?:а|но)\s+|\s+(?:а|но)\s+)\s*",
        text,
        flags=re.IGNORECASE,
    )
    return [clause.strip(" ,;-") for clause in clauses if clause.strip(" ,;-")]


def _history_kind(text: str) -> str | None:
    """Return an explicit score filter without inventing one."""

    has_minus = bool(re.search(r"\b(?:минус\w*|косяк\w*)\b", text))
    has_plus = bool(re.search(r"\bплюс\w*\b", text))
    if has_minus and not has_plus:
        return "minus"
    if has_plus and not has_minus:
        return "plus"
    return None


def parse_message(text: str, *, members: Iterable[dict] | None = None) -> ParsedMessage:
    """Parse one Telegram message without any authorization assumptions."""

    if "|" in text:
        return ParsedMessage("ignore")

    normalized = normalize_text(text)
    if not normalized:
        return ParsedMessage("ignore")

    first_token = normalized.split(" ", 1)[0]
    command = first_token.split("@", 1)[0]
    # Existing slash commands own their complete payload/revision semantics.
    if command.startswith("/") and command not in {
        "/history",
        "/история",
        "/минусы",
        "/плюсы",
        "/дело",
        "/undo",
        "/отмена",
        "/откат",
        "/courthelp",
        "/court_help",
        "/rules",
        "/кодекс",
        "/правила",
    }:
        return ParsedMessage("ignore")
    if command in ASSISTANT_COMMANDS:
        return ParsedMessage("ignore")
    if _matches_any(normalized, ASSISTANT_TASK_PATTERNS):
        return ParsedMessage("ignore")
    if _matches_any(normalized, ASSISTANT_CONTEXTUAL_CORRECTION_PATTERNS):
        return ParsedMessage("ignore")

    child_patterns = member_patterns(members)
    if _matches_any(normalized, HELP_PATTERNS):
        return ParsedMessage("help")
    if _matches_any(normalized, RULES_PATTERNS):
        return ParsedMessage("rules")
    if _matches_any(normalized, UNDO_PATTERNS):
        return ParsedMessage("undo")
    if _matches_any(normalized, APPEAL_PATTERNS):
        return ParsedMessage("appeal")
    if _matches_any(normalized, HISTORY_PATTERNS):
        children = _children_in(normalized, child_patterns)
        return ParsedMessage(
            "history",
            child=children[0] if len(children) == 1 else None,
            detail=_history_kind(normalized),
        )
    if _matches_any(normalized, STATS_ALL_PATTERNS):
        return ParsedMessage("stats")

    children = _children_in(normalized, child_patterns)
    if _matches_any(normalized, CASE_PATTERNS):
        if len(children) == 1:
            return ParsedMessage("case", child=children[0])
        return ParsedMessage("stats" if not children else "ambiguous")

    if not children:
        if _raw_assessment_marker(normalized):
            return ParsedMessage("missing_child")
        return ParsedMessage("ignore")

    if len(children) == 1:
        assessment = _classify_clause(normalized, children[0], child_patterns)
        if assessment:
            return ParsedMessage("assessments", assessments=(assessment,))
        if _raw_assessment_marker(normalized):
            return ParsedMessage("ambiguous", child=children[0])
        return ParsedMessage("ignore")

    # Mentioning several children is not by itself a Court action.  Without a
    # score or assessment phrase this is ordinary family/task conversation and
    # must be left to the other routes of the single bot.
    if not _raw_assessment_marker(normalized):
        return ParsedMessage("ignore")

    assessments: list[Assessment] = []
    clauses = _split_multi_child(normalized)
    for clause in clauses:
        clause_children = _children_in(clause, child_patterns)
        if len(clause_children) != 1:
            continue
        assessment = _classify_clause(clause, clause_children[0], child_patterns)
        if assessment:
            assessments.append(assessment)

    assessed_children = {item.child for item in assessments}
    if len(assessments) == len(children) and assessed_children == set(children):
        return ParsedMessage("assessments", assessments=tuple(assessments))
    return ParsedMessage("ambiguous")


def display_child(child: str, names: dict[str, str] | None = None) -> str:
    """Return the configured display name or the supplied member identifier."""
    return (names or {}).get(child, child)
