"""Russian language patterns for the Family Court parser.

Keep this module declarative: household vocabulary can be extended here without
changing the parser or the persistent ledger.
"""

from __future__ import annotations

# Compatibility exports only. Household names and aliases come from the Store.
CHILD_PATTERNS: dict[str, tuple[str, ...]] = {}
CHILD_NAMES: dict[str, str] = {}

# Explicit markers have priority over descriptive phrases.
EXPLICIT_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"(?<!\w)\+\s*1(?!\d)",
    r"\bплюсик\b",
    r"\bплюс\b",
    r"\bдобав(?:ь|ить|ьте)\s+(?:один\s+)?балл\b",
    r"\bзаслужил(?:а)?\s+плюс\b",
    r"\bпохвалить\b",
)

EXPLICIT_NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"(?<!\w)-\s*1(?!\d)",
    r"\bминус\b",
    r"\bкосяк\b",
    r"\bнакосячил(?:а)?\b",
    r"\bсня(?:ть|л|ла)\s+(?:один\s+)?балл\b",
    r"\bполучает\s+минус\b",
    r"\bнаказать\b",
)

POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bмолодец\b",
    r"\bмолодцы\b",
    r"\bумница\b",
    r"\bумницы\b",
    r"\bхорошо\s+себя\s+вел(?:а|и)?\b",
    r"\bпомог(?:ла|ли)?\b",
    r"\bсам(?:а|и)?\s+(?:все\s+)?сделал(?:а|и)?\b",
    r"\bсам(?:а|и)?\s+(?:все\s+)?убрал(?:а|и)?\b",
    r"\bсделал(?:а|и)?\s+уроки\b",
    r"\bвыполнил(?:а|и)?\s+просьбу\b",
    r"\bвыполнен(?:а|ы)?\s+просьб(?:а|у|ы)\b",
    r"\bзаслужил(?:а|и)?\s+похвалу\b",
    r"\bвел(?:а|и)?\s+себя\s+хорошо\b",
    r"\bпорадовал(?:а|и)?\b",
)

# Patterns that already contain a negative construction must not be suppressed
# by the generic negation detector.
NEGATIVE_CONSTRUCTION_PATTERNS: tuple[str, ...] = (
    r"\bплохо\s+себя\s+вел(?:а|и)?\b",
    r"\bне\s+слушал(?:ся|ась|ись)\b",
    r"\bне\s+сделал(?:а|и)?\b",
    r"\bне\s+убрал(?:а|и)?\b",
    r"\bне\s+выполнил(?:а|и)?\b",
    r"\bопять\s+не\b",
    r"\bотказал(?:ся|ась|ись)\b",
)

NEGATIVE_PATTERNS: tuple[str, ...] = (
    r"\bнагрубил(?:а|и)?\b",
    r"\bсоврал(?:а|и)?\b",
    r"\bобманул(?:а|и)?\b",
    r"\bзабыл(?:а|и)?\b",
    r"\bразбил(?:а|и)?\b",
    r"\bразбит(?:а|о|ы)?\b",
    r"\bсломал(?:а|и)?\b",
    r"\bсломан(?:а|о|ы)?\b",
    r"\bустроил(?:а|и)?\s+(?:скандал|истерику|бардак|драку)\b",
)

NEGATION_WORDS: frozenset[str] = frozenset(
    {"не", "ни", "нет", "никак", "никакого", "никогда", "без"}
)

STATS_ALL_PATTERNS: tuple[str, ...] = (
    r"^/(?:суд|баллы|бали|stats|стата|статистика|штрафы|штрафи|очки|рейтинг)(?:@\w+)?(?:\s|$)",
    r"\bчто\s+по\s+баллам\b",
    r"\bпокажи(?:те)?\s+статистик",
    r"\bкак\s+там\s+дела\s+у\s+детей\b",
    r"\bкакой\s+сч[её]т\b",
    r"\bтаблиц\w*\s+штраф",
    r"\bитоги\s+недели\b",
)

HISTORY_PATTERNS: tuple[str, ...] = (
    r"^/(?:история|history|минусы|плюсы)(?:@\w+)?(?:\s|$)",
    r"\b(?:какие|почему|откуда|что\s+за)\b.{0,50}\b(?:минус\w*|плюс\w*|балл\w*|косяк\w*)\b",
    r"\bза\s+что\s+(?:(?:у|для)\s+)?(?:эти\s+)?(?:минус\w*|плюс\w*|балл\w*|косяк\w*)\b",
    r"\bза\s+что\s+(?:у|для)\b.{0,50}\b(?:минус\w*|плюс\w*|балл\w*|косяк\w*)\b",
    r"\b(?:посмотри|посмотрите|проверь|проверьте)\s+(?:в\s+)?(?:базе|журнале|истории)\b.{0,80}\b(?:минус\w*|плюс\w*|балл\w*|косяк\w*)\b",
    r"\b(?:истори\w*|список|причин\w*)\b.{0,50}\b(?:минус\w*|плюс\w*|балл\w*|косяк\w*)\b",
)

CASE_PATTERNS: tuple[str, ...] = (
    r"^/дело(?:@\w+)?\s+",
    r"\bпокажи(?:те)?\s+дело\b",
    r"\bсколько\s+у\b.*\b(?:косяк|плюс|балл)",
    r"\bкак\s+там\b",
    r"\bза\s+что\s+у\b.*\b(?:минус|плюс|косяк)",
)

UNDO_PATTERNS: tuple[str, ...] = (
    r"^/(?:undo|отмена|откат)(?:@\w+)?(?:\s|$)",
    r"\bотмени\s+последнее\b",
    r"\bотменить\s+последнее\b",
    r"\bоткати\s+последнее\b",
    r"\bоткатить\s+последнее\b",
    r"\bотмени\s+последни(?:й|юю)\s+(?:балл|оценку|постановление)\b",
)

APPEAL_PATTERNS: tuple[str, ...] = (
    r"^/(?:appeal|апелляция|апеляція)(?:@\w+)?(?:\s|$)",
    r"\bапелляци",
    r"\bапеляці",
    r"\bобжалова",
    r"\bотмени\s+(?:мне\s+)?(?:минус|плюс)\b",
)

HELP_PATTERNS: tuple[str, ...] = (
    r"^/(?:courthelp|court_help)(?:@\w+)?(?:\s|$)",
    r"\bсуд\s+помощь\b",
    r"\bсправка\s+суда\b",
)
RULES_PATTERNS: tuple[str, ...] = (
    r"^/(?:rules|кодекс|правила)(?:@\w+)?(?:\s|$)",
    r"\bправила\s+суда\b",
    r"\bсемейный\s+кодекс\b",
    r"\bуголовно-процессуальный\b",
)
