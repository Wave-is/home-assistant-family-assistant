"""Bounded, exact rational-answer validation; no HA or model dependency."""

import re
from dataclasses import dataclass
from fractions import Fraction
from math import gcd
from typing import Literal

_MAX_LENGTH = 80
_INTEGER = r"[+-]?[0-9]{1,12}"
_FRACTION = re.compile(rf"({_INTEGER})\s*/\s*([0-9]{{1,12}})")
_DECIMAL = re.compile(rf"{_INTEGER}(?:[.,][0-9]{{1,12}})?")


@dataclass(frozen=True, slots=True)
class RationalResult:
    """Feedback never includes the expected answer."""

    status: Literal["correct", "incorrect", "invalid"]
    code: str
    normalized: str | None = None


def check_rational(
    answer: str, expected: Fraction, *, require_reduced_fraction: bool = False
) -> RationalResult:
    """Check a typed answer exactly; optional reduced fraction syntax is explicit."""
    if not isinstance(expected, Fraction):
        raise TypeError("expected must be an exact Fraction")
    if not isinstance(answer, str) or len(answer) > _MAX_LENGTH:
        return RationalResult("invalid", "invalid_input")
    value = answer.strip().replace("−", "-")
    match = _FRACTION.fullmatch(value)
    if match:
        numerator, denominator = map(int, match.groups())
        if denominator == 0:
            return RationalResult("invalid", "zero_denominator")
        parsed = Fraction(numerator, denominator)
        reduced = gcd(numerator, denominator) == 1
    elif _DECIMAL.fullmatch(value):
        parsed = Fraction(value.replace(",", "."))
        reduced = False
    else:
        return RationalResult("invalid", "invalid_format")

    normalized = str(parsed)
    if parsed != expected:
        return RationalResult("incorrect", "different_value", normalized)
    if require_reduced_fraction and not reduced:
        return RationalResult("incorrect", "reduced_fraction_required", normalized)
    return RationalResult("correct", "equivalent_value", normalized)
