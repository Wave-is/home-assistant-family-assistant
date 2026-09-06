"""Strict input validation shared by every entry point."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


class DomainError(ValueError):
    """A stable localization key, never a raw provider exception."""

    def __init__(self, code: str, field: str = "") -> None:
        self.code = code
        self.field = field
        super().__init__(code)


def text(value: Any, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DomainError("invalid_field", field)
    return value.strip()


def number(value: Any, field: str, minimum: float = 0, maximum: float = 1000000) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainError("invalid_field", field)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise DomainError("invalid_field", field)
    return float(value)


def revision(value: Any) -> int:
    """A JSON-safe record version, never a boolean or an optional wildcard."""
    if type(value) is not int or not 1 <= value <= 2**53 - 1:
        raise DomainError("invalid_field", "revision")
    return value


def timestamp(value: Any, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(result, datetime) or result.tzinfo is None:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise DomainError("invalid_field", field) from None


def fields(payload: dict, allowed: set[str], required: set[str] | None = None) -> None:
    unknown = payload.keys() - allowed
    missing = (required or set()) - payload.keys()
    if unknown or missing:
        raise DomainError("invalid_field", sorted(unknown or missing)[0])


def enum(value: Any, choices: tuple | set | frozenset, field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise DomainError("invalid_field", field)
    return value
