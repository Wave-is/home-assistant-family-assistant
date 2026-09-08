"""GS1 Mod10 structure only, not registration or product-identity verification."""

import re

from .validation import DomainError


def normalize_gtin(value) -> str:
    """Accept GTIN-8/12/13/14 and store the zero-padded 14-digit representation."""
    if type(value) is not str:
        raise DomainError("invalid_field", "barcode")
    clean = value.strip()
    if not clean:
        return ""
    if (
        len(clean) not in {8, 12, 13, 14}
        or not re.fullmatch(r"[0-9]+", clean)
        or set(clean) == {"0"}
    ):
        raise DomainError("invalid_field", "barcode")
    total = sum(
        int(digit) * (3 if offset % 2 == 0 else 1)
        for offset, digit in enumerate(reversed(clean[:-1]))
    )
    if (10 - total % 10) % 10 != int(clean[-1]):
        raise DomainError("invalid_field", "barcode")
    return clean.zfill(14)
