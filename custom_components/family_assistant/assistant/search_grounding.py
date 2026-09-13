"""Lexical query provenance, not permission to paraphrase private model context."""

import re
import unicodedata
from collections import Counter

from ..domain.validation import DomainError

_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
_SENSITIVE = re.compile(
    r"(?:\b[a-z]\s*[-_]?\s*\d{4,}\b|https?\s*:\s*/|@|"
    r"\b\d{1,3}(?:[.\s]+\d{1,3}){3}\b|(?:[0-9a-f]{0,4}:){2,}[0-9a-f]{0,4})",
    re.I,
)


def _words(value):
    value = unicodedata.normalize("NFC", value).casefold().replace("ё", "е").replace("’", "'")
    return _WORD.findall(value)


def grounded_query(query, content, members=()):
    """Allow source-word reordering/case/separators; never add or translate words.

    Multiplicity matters: a model cannot repeat a word to build a new identifier.
    The outgoing query has plain word separators, not model-added search operators.
    Quotes, history, images and family record fields are not provenance sources.
    """
    if (
        not isinstance(query, str)
        or not 0 < len(query) <= 300
        or not isinstance(content, str)
        or not 0 < len(content) <= 12000
        or any(unicodedata.category(char).startswith("C") and not char.isspace() for char in query)
    ):
        raise DomainError("search_query_not_grounded")
    words = _words(query)
    selected = Counter(words)
    if not selected or selected - Counter(_words(content)):
        raise DomainError("search_query_not_grounded")
    normalized = " ".join(words)
    if _SENSITIVE.search(unicodedata.normalize("NFKC", query)) or _SENSITIVE.search(normalized):
        raise DomainError("search_query_not_grounded")
    for member in members:
        # Compare complete names without depending on the model's word order.
        # Optional explicit aliases get the same protection when supplied.
        names = [member.get("name", ""), *member.get("aliases", [])]
        for name in names:
            if not isinstance(name, str):
                continue
            tokens = Counter(_words(name))
            if tokens and not tokens - selected:
                raise DomainError("search_query_not_grounded")
    return normalized
