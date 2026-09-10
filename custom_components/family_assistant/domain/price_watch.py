"""Price watch: track product prices from URLs; no external services required.

Each watcher stores a URL, an optional display name, the last known price and
availability, and a sliding window of up to 30 price snapshots.  All parsing
happens outside this module — the domain only validates and persists results.

Constraints
-----------
* No I/O here: this module is pure-domain and must remain synchronously testable.
* Currency is a 3-letter ISO 4217 code (syntax only, not semantically validated).
* Price text is kept as a human-readable string (≤ 40 chars) to avoid lossy
  float conversion; callers may further parse it for display.
* SSRF protection lives in the fetcher (price_watch_fetcher.py).
"""

from __future__ import annotations

import re

from .context import Context
from .validation import DomainError, fields, text

# ── constants ─────────────────────────────────────────────────────────────────

MAX_WATCHERS = 200
MAX_HISTORY = 30
_URL_RE = re.compile(r"^https?://[^\s]{4,2000}$")
_PRICE_TEXT_RE = re.compile(r"^[0-9 .,·'\u00a0\u202f]{1,40}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

AVAILABILITY_VALUES = frozenset(
    {
        "in_stock",
        "out_of_stock",
        "preorder",
        "backorder",
        "discontinued",
        "unknown",
    }
)


# ── helpers ────────────────────────────────────────────────────────────────────


def _clean_url(url: str) -> str:
    """Reject non-http(s) or excessively long URLs."""
    url = url.strip()
    if not _URL_RE.match(url):
        raise DomainError("invalid_field", "url")
    return url


def _clean_price_text(value: str | None) -> str:
    """Normalise the price text; empty string means «not yet fetched»."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DomainError("invalid_field", "price_text")
    stripped = value.strip()
    if stripped and not _PRICE_TEXT_RE.match(stripped):
        raise DomainError("invalid_field", "price_text")
    return stripped


def _clean_currency(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or (value and not _CURRENCY_RE.match(value)):
        raise DomainError("invalid_field", "currency")
    return value.upper()


def _clean_availability(value: str | None) -> str:
    if value is None:
        return "unknown"
    if not isinstance(value, str) or value not in AVAILABILITY_VALUES:
        raise DomainError("invalid_field", "availability")
    return value


# ── public API ─────────────────────────────────────────────────────────────────


def handle(ctx: Context, action: str, payload: dict) -> dict:
    """Dispatch price-watch commands.

    Supported actions (all require parent/owner role):
      add      — register a new URL to watch
      edit     — change display name or URL for an existing watcher
      remove   — delete a watcher and its history
      record   — store a freshly fetched price snapshot (system-internal)
      list     — returns the list (convenience, engine already exposes snapshot)
    """
    ctx.require_parent()

    if action == "add":
        return _add(ctx, payload)
    if action == "edit":
        return _edit(ctx, payload)
    if action == "remove":
        return _remove(ctx, payload)
    if action == "record":
        return _record(ctx, payload)
    raise DomainError("unknown_action")


# ── add ────────────────────────────────────────────────────────────────────────


def _add(ctx: Context, payload: dict) -> dict:
    fields(
        payload,
        {"url", "name", "currency", "notify_drop", "notify_available"},
        {"url"},
    )
    watchers: dict = ctx.state.setdefault("price_watches", {})
    if len(watchers) >= MAX_WATCHERS:
        raise DomainError("limit_exceeded")

    url = _clean_url(text(payload["url"], "url", 2000))

    # Duplicate URL guard
    for existing in watchers.values():
        if existing.get("url") == url:
            raise DomainError("conflict")

    name = text(payload["name"], "name", 200) if "name" in payload else url[:200]
    currency = _clean_currency(payload.get("currency"))
    notify_drop = bool(payload.get("notify_drop", True))
    notify_available = bool(payload.get("notify_available", True))

    watcher = {
        "id": ctx.identifier("PW"),
        "url": url,
        "name": name,
        "currency": currency,
        "notify_drop": notify_drop,
        "notify_available": notify_available,
        "price_text": "",
        "availability": "unknown",
        "last_checked": None,
        "last_error": None,
        "history": [],
        "creator": ctx.actor_id,
        "created_at": ctx.now.isoformat(),
    }
    ctx.touch(watcher)
    ctx.state["price_watches"][watcher["id"]] = watcher
    return watcher


# ── edit ───────────────────────────────────────────────────────────────────────


def _edit(ctx: Context, payload: dict) -> dict:
    fields(
        payload,
        {"id", "revision", "url", "name", "currency", "notify_drop", "notify_available"},
        {"id", "revision"},
    )
    watchers: dict = ctx.state.get("price_watches", {})
    watcher_id = text(payload["id"], "id", 80)
    watcher = watchers.get(watcher_id)
    if watcher is None:
        raise DomainError("not_found")
    from .validation import revision as validate_revision

    if validate_revision(payload["revision"]) != watcher.get("revision"):
        raise DomainError("conflict")

    if "url" in payload:
        new_url = _clean_url(text(payload["url"], "url", 2000))
        for eid, existing in watchers.items():
            if eid != watcher_id and existing.get("url") == new_url:
                raise DomainError("conflict")
        watcher["url"] = new_url
    if "name" in payload:
        watcher["name"] = text(payload["name"], "name", 200)
    if "currency" in payload:
        watcher["currency"] = _clean_currency(payload["currency"])
    if "notify_drop" in payload:
        watcher["notify_drop"] = bool(payload["notify_drop"])
    if "notify_available" in payload:
        watcher["notify_available"] = bool(payload["notify_available"])

    ctx.touch(watcher)
    return watcher


# ── remove ─────────────────────────────────────────────────────────────────────


def _remove(ctx: Context, payload: dict) -> dict:
    fields(payload, {"id", "revision"}, {"id", "revision"})
    watchers: dict = ctx.state.get("price_watches", {})
    watcher_id = text(payload["id"], "id", 80)
    watcher = watchers.get(watcher_id)
    if watcher is None:
        raise DomainError("not_found")
    from .validation import revision as validate_revision

    if validate_revision(payload["revision"]) != watcher.get("revision"):
        raise DomainError("conflict")
    return watchers.pop(watcher_id)


# ── record (system-internal) ───────────────────────────────────────────────────


def _record(ctx: Context, payload: dict) -> dict:
    """Persist a fetcher result; emits a notification if price dropped or back-in-stock."""
    fields(
        payload,
        {"id", "price_text", "currency", "availability", "error"},
        {"id"},
    )
    watchers: dict = ctx.state.get("price_watches", {})
    watcher_id = text(payload["id"], "id", 80)
    watcher = watchers.get(watcher_id)
    if watcher is None:
        raise DomainError("not_found")

    now_iso = ctx.now.isoformat()

    if "error" in payload:
        err = payload["error"]
        if not isinstance(err, str) or len(err) > 200:
            raise DomainError("invalid_field", "error")
        watcher["last_error"] = err.strip()[:200]
        watcher["last_checked"] = now_iso
        ctx.touch(watcher)
        return watcher

    watcher["last_error"] = None
    price_text = _clean_price_text(payload.get("price_text"))
    currency = _clean_currency(payload.get("currency"))
    availability = _clean_availability(payload.get("availability"))

    previous_price = watcher.get("price_text", "")
    previous_avail = watcher.get("availability", "unknown")

    watcher["price_text"] = price_text
    watcher["currency"] = currency or watcher.get("currency", "")
    watcher["availability"] = availability
    watcher["last_checked"] = now_iso

    # Append snapshot to history (capped at MAX_HISTORY)
    snapshot = {
        "at": now_iso,
        "price_text": price_text,
        "availability": availability,
    }
    history: list = watcher.setdefault("history", [])
    history.append(snapshot)
    if len(history) > MAX_HISTORY:
        watcher["history"] = history[-MAX_HISTORY:]

    # Emit notifications
    price_dropped = (
        watcher.get("notify_drop")
        and price_text
        and previous_price
        and _price_dropped(previous_price, price_text)
    )
    came_available = (
        watcher.get("notify_available")
        and availability == "in_stock"
        and previous_avail not in {"in_stock", "unknown"}
    )

    if price_dropped:
        ctx.notify(
            "parents",
            "price_watch_drop",
            {
                "id": watcher_id,
                "name": watcher["name"],
                "old_price": previous_price,
                "new_price": price_text,
                "currency": watcher["currency"],
            },
        )
    if came_available:
        ctx.notify(
            "parents",
            "price_watch_available",
            {
                "id": watcher_id,
                "name": watcher["name"],
                "price_text": price_text,
            },
        )

    ctx.touch(watcher)
    return watcher


# ── price comparison ───────────────────────────────────────────────────────────


def _parse_price_float(text_val: str) -> float | None:
    """Best-effort parse of a human price string to a float for comparison.

    Handles common Ukrainian/European formats: «1 234,56», «1.234,56», «1234.56».
    Returns None if unparseable — the caller skips drop notification.
    """
    if not text_val:
        return None
    # Remove thousands-separators (space, non-breaking space, dot when followed by 3 digits)
    cleaned = re.sub(r"[\s\u00a0\u202f]", "", text_val)
    # If comma is used as decimal separator (e.g. «1234,56»)
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        # European «1.234,56» — dot is thousands, comma is decimal
        cleaned = cleaned.replace(".", "").replace(",", ".")
    # Strip any remaining non-numeric chars except dot and leading minus
    cleaned = re.sub(r"[^0-9.]", "", cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _price_dropped(old: str, new: str) -> bool:
    old_f = _parse_price_float(old)
    new_f = _parse_price_float(new)
    if old_f is None or new_f is None:
        return False
    # Consider a drop only if strictly less and not trivially zero
    return new_f < old_f and old_f > 0
