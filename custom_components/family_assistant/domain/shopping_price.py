"""Optional exact purchase totals, not currency conversion or financial accounting."""

import re
from decimal import Decimal

from .validation import DomainError, fields


def price(value):
    """A total for this purchase delta; no guessed unit price or historical cost."""
    if not isinstance(value, dict):
        raise DomainError("invalid_field", "price")
    fields(value, {"total", "currency"}, {"total", "currency"})
    total, currency = value["total"], value["currency"]
    if (
        not isinstance(total, str)
        or re.fullmatch(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,4})?", total) is None
        or Decimal(total) > Decimal("999999999")
    ):
        raise DomainError("invalid_field", "price_total")
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise DomainError("invalid_field", "price_currency")
    # Canonicalize only after the bounded grammar has excluded exponent/NaN/Inf.
    canonical = total.rstrip("0").rstrip(".") if "." in total else total
    return {"total": canonical, "currency": currency}
