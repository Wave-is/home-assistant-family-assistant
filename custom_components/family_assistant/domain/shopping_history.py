"""Append-only local per-item history for shopping items."""

from __future__ import annotations

from typing import Any

from .context import Context
from .validation import DomainError, number, text

ACTIONS = frozenset({"add", "approve", "reject", "archive", "purchase", "merge"})
KNOWN_DETAIL_FIELDS = frozenset(
    {
        "quantity",
        "purchased",
        "remaining",
        "amount",
        "unit",
        "status",
        "sources",
        "merged_into",
    }
)


def record_event(
    ctx: Context,
    item_id: str,
    action: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a history entry to item['history'].

    Existing items without history work; do not fabricate past events.
    The event detail must contain bounded, local information only.
    No external operation IDs or raw channel IDs.
    """
    if action not in ACTIONS:
        raise DomainError("invalid_field", "action")

    shopping_bucket = ctx.state.setdefault("shopping", {})
    item = shopping_bucket.get(item_id)
    if item is None:
        raise DomainError("not_found")

    if "history" not in item:
        item["history"] = []
    elif not isinstance(item["history"], list):
        raise DomainError("invalid_field", "history")

    history: list[dict[str, Any]] = item["history"]

    entry: dict[str, Any] = {
        "at": ctx.now.isoformat(),
        "actor": ctx.actor_id,
        "action": action,
    }

    if detail:
        unknown = detail.keys() - KNOWN_DETAIL_FIELDS
        if unknown:
            raise DomainError("invalid_field", sorted(unknown)[0])

        clean_detail: dict[str, Any] = {}
        for k, v in detail.items():
            if k in {"quantity", "purchased", "remaining", "amount"}:
                clean_detail[k] = number(v, k, 0.0, 1000000.0)
            elif k == "unit":
                if not isinstance(v, str) or len(v) > 32:
                    raise DomainError("invalid_field", "unit")
                clean_detail[k] = v
            elif k == "status":
                if not isinstance(v, str) or len(v) > 32 or not v.strip():
                    raise DomainError("invalid_field", "status")
                clean_detail[k] = v.strip()
            elif k == "merged_into":
                clean_detail[k] = text(v, "merged_into", 80)
            elif k == "sources":
                if not isinstance(v, list) or not (1 <= len(v) <= 19):
                    raise DomainError("invalid_field", "sources")
                clean_sources: list[str] = []
                for idx, src_id in enumerate(v):
                    clean_sources.append(text(src_id, f"sources[{idx}]", 80))
                clean_detail[k] = clean_sources

        entry["detail"] = clean_detail

    history.append(entry)
    return entry
