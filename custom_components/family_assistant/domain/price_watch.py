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
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from .context import Context
from .validation import DomainError, fields, text, timestamp

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
EVENTS = {"price_watch_drop", "price_watch_available"}
NOTICE_MAX_AGE = timedelta(minutes=60)
FAILURES = {
    "invalid_url",
    "timeout",
    "response_too_large",
    "unsupported_response",
    "unavailable",
    "invalid_response",
    "review_required",
}


# ── helpers ────────────────────────────────────────────────────────────────────


def _clean_url(url: str) -> str:
    """Require HTTPS without URL credentials, fragments or custom ports."""
    url = url.strip()
    if not _URL_RE.match(url):
        raise DomainError("invalid_field", "url")
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or "\\" in url
            or "%" in parsed.netloc
        ):
            raise ValueError
    except ValueError:
        raise DomainError("invalid_field", "url") from None
    return url


def _clean_price_text(value: str | None) -> str:
    """Normalise the price text; empty string means «not yet fetched»."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DomainError("invalid_field", "price_text")
    stripped = value.strip()
    if stripped and (not _PRICE_TEXT_RE.match(stripped) or _price_decimal(stripped) is None):
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


def validate_observation(price_text, currency):
    _clean_price_text(price_text)
    _clean_currency(currency)


def _approve(ctx, watcher):
    watcher.update(
        policy_actor=ctx.actor_id,
        policy_actor_revision=ctx.actor["revision"],
        policy_generation=watcher.get("policy_generation", 0) + 1,
    )


def _approval_revision(ctx, payload):
    if "actor_revision" in payload:
        from .validation import revision

        if revision(payload["actor_revision"]) != ctx.actor["revision"]:
            raise DomainError("conflict")


def source_scope(state, watcher_id):
    """Current durable consent, independent from unrelated family mutations."""
    watcher = state.get("price_watches", {}).get(watcher_id)
    if watcher is None or "price_watch" not in state["settings"]["modules"]:
        return None
    actor = state["members"].get(watcher.get("policy_actor"), {})
    if (
        not actor.get("active")
        or actor.get("role") not in {"owner", "parent"}
        or not watcher.get("policy_generation")
        or actor.get("revision") != watcher.get("policy_actor_revision")
    ):
        return None
    return {
        "id": watcher_id,
        "url": watcher["url"],
        "policy_generation": watcher["policy_generation"],
        "policy_actor": actor["id"],
        "policy_actor_revision": actor["revision"],
        "module_epoch": state.get("price_watch_epoch", 0),
    }


def observation_scope(state, watcher_id):
    source = source_scope(state, watcher_id)
    if source is None:
        return None
    return {**source, "revision": state["price_watches"][watcher_id]["revision"]}


def record_observation(ctx, scope, result):
    """Adapter-only system update: no impersonated owner and no unguarded write."""
    if observation_scope(ctx.state, scope.get("id")) != scope:
        raise DomainError("observation_revoked")
    payload = {"id": scope["id"], **result}
    if payload.get("error"):
        payload = {"id": scope["id"], "error": payload["error"]}
    else:
        payload.pop("error", None)
    return _record(ctx, payload)


def current_event(state, event, now):
    data = event.get("data", {})
    scope = data.get("price_watch_scope")
    if not isinstance(scope, dict) or source_scope(state, data.get("id")) != scope:
        return False
    watcher = state["price_watches"][data["id"]]
    observation = data.get("price_watch_observation", {})
    if (
        watcher.get("last_error")
        or not isinstance(observation, dict)
        or observation.get("sequence") != watcher.get("observation_sequence")
        or observation.get("at") != watcher.get("last_checked")
    ):
        return False
    try:
        observed = timestamp(observation.get("at"), "observed_at")
        current = timestamp(now, "now")
        if not observed <= current < observed + NOTICE_MAX_AGE:
            return False
    except DomainError:
        return False
    recipients = data.get("price_watch_recipients")
    return isinstance(recipients, list) and recipients == _recipients(state)


def _recipients(state):
    return sorted(
        (
            {"id": m["id"], "revision": m["revision"], "telegram_id": m.get("telegram_id")}
            for m in state["members"].values()
            if m.get("active") and m.get("role") in {"owner", "parent"}
        ),
        key=lambda m: m["id"],
    )


def project(state, watcher):
    result = dict(watcher)
    result["policy_status"] = "ready" if source_scope(state, watcher["id"]) else "review_required"
    if result.get("last_error") and result["last_error"] not in FAILURES:
        result["last_error"] = "unavailable"

    # Old versions accepted URL userinfo. Retain the original in Store for
    # recovery, but never disclose those credentials in a shared family view.
    def redacted(url):
        try:
            parsed = urlsplit(url)
            return parsed._replace(netloc=parsed.netloc.rsplit("@", 1)[-1]).geturl()
        except (TypeError, ValueError):
            return ""

    result["url"] = redacted(watcher.get("url", ""))
    if watcher.get("name") == watcher.get("url", "")[:200]:
        result["name"] = result["url"][:200]
    result["history"] = [
        {**item, **({"url": redacted(item["url"])} if "url" in item else {})}
        for item in watcher.get("history", [])
    ]
    return result


def authorize_replay(state, actor, action, result):
    if actor["role"] not in {"owner", "parent"}:
        raise DomainError("forbidden")
    if action == "remove":
        return
    current = state.get("price_watches", {}).get(result.get("id"))
    if (
        current is None
        or current.get("policy_generation") != result.get("policy_generation")
        or source_scope(state, current["id"]) is None
    ):
        raise DomainError("conflict")


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
        {"url", "name", "currency", "notify_drop", "notify_available", "actor_revision"},
        {"url"},
    )
    _approval_revision(ctx, payload)
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
    if any(
        type(payload[key]) is not bool
        for key in ("notify_drop", "notify_available")
        if key in payload
    ):
        raise DomainError("invalid_field", "notify_drop")

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
    _approve(ctx, watcher)
    ctx.touch(watcher)
    ctx.state["price_watches"][watcher["id"]] = watcher
    return watcher


# ── edit ───────────────────────────────────────────────────────────────────────


def _edit(ctx: Context, payload: dict) -> dict:
    fields(
        payload,
        {
            "id",
            "revision",
            "url",
            "name",
            "currency",
            "notify_drop",
            "notify_available",
            "actor_revision",
        },
        {"id", "revision"},
    )
    _approval_revision(ctx, payload)
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
        if new_url != watcher["url"]:
            # Preserve old evidence, but never compare two different products.
            for item in watcher.get("history", []):
                item.setdefault("url", watcher["url"])
            if watcher.get("name") == watcher["url"][:200]:
                watcher["name"] = new_url[:200]
            watcher.update(
                price_text="", availability="unknown", last_checked=None, last_error=None
            )
            watcher["baseline_pending"] = True
        watcher["url"] = new_url
    if "name" in payload:
        watcher["name"] = text(payload["name"], "name", 200)
    if "currency" in payload:
        if payload["currency"] != watcher.get("currency"):
            watcher["baseline_pending"] = True
        watcher["currency"] = _clean_currency(payload["currency"])
    if any(
        type(payload[key]) is not bool
        for key in ("notify_drop", "notify_available")
        if key in payload
    ):
        raise DomainError("invalid_field", "notify_drop")
    if "notify_drop" in payload:
        watcher["notify_drop"] = bool(payload["notify_drop"])
    if "notify_available" in payload:
        watcher["notify_available"] = bool(payload["notify_available"])

    if source_scope(ctx.state, watcher_id) is None:
        watcher["baseline_pending"] = True
    _clean_url(watcher["url"])
    _approve(ctx, watcher)
    ctx.touch(watcher)
    return watcher


# ── remove ─────────────────────────────────────────────────────────────────────


def _remove(ctx: Context, payload: dict) -> dict:
    fields(payload, {"id", "revision"}, {"id"})
    watchers: dict = ctx.state.get("price_watches", {})
    watcher_id = text(payload["id"], "id", 80)
    watcher = watchers.get(watcher_id)
    if watcher is None:
        raise DomainError("not_found")
    if "revision" in payload:
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
    watcher["observation_sequence"] = watcher.get("observation_sequence", 0) + 1

    if "error" in payload:
        err = payload["error"]
        if not isinstance(err, str) or len(err) > 200:
            raise DomainError("invalid_field", "error")
        watcher["last_error"] = err if err in FAILURES else "unavailable"
        watcher["last_checked"] = now_iso
        ctx.touch(watcher)
        return watcher

    watcher["last_error"] = None
    price_text = _clean_price_text(payload.get("price_text"))
    currency = _clean_currency(payload.get("currency"))
    availability = _clean_availability(payload.get("availability"))

    previous_price = watcher.get("price_text", "")
    previous_avail = watcher.get("availability", "unknown")
    previous_currency = watcher.get("observed_currency", watcher.get("currency", ""))

    watcher["price_text"] = price_text
    watcher["currency"] = currency or watcher.get("currency", "")
    watcher["observed_currency"] = currency
    watcher["availability"] = availability
    watcher["last_checked"] = now_iso

    # Append snapshot to history (capped at MAX_HISTORY)
    snapshot = {
        "at": now_iso,
        "price_text": price_text,
        "availability": availability,
        "currency": currency,
        "url": watcher["url"],
    }
    history: list = watcher.setdefault("history", [])
    history.append(snapshot)
    if len(history) > MAX_HISTORY:
        watcher["history"] = history[-MAX_HISTORY:]

    # Emit notifications
    price_dropped = (
        watcher.get("notify_drop")
        and not watcher.get("baseline_pending")
        and currency
        and currency == previous_currency
        and price_text
        and previous_price
        and _price_dropped(previous_price, price_text)
    )
    came_available = (
        watcher.get("notify_available")
        and not watcher.get("baseline_pending")
        and availability == "in_stock"
        and previous_avail not in {"in_stock", "unknown"}
    )

    scope = source_scope(ctx.state, watcher_id)
    notice_scope = {
        "price_watch_scope": scope,
        "price_watch_recipients": _recipients(ctx.state),
        "price_watch_observation": {"sequence": watcher["observation_sequence"], "at": now_iso},
    }
    if price_dropped and scope is not None:
        ctx.notify(
            "parents",
            "price_watch_drop",
            {
                "id": watcher_id,
                "name": watcher["name"],
                "old_price": previous_price,
                "new_price": price_text,
                "currency": watcher["currency"],
                **notice_scope,
            },
        )
    if came_available and scope is not None:
        ctx.notify(
            "parents",
            "price_watch_available",
            {
                "id": watcher_id,
                "name": watcher["name"],
                "price_text": price_text,
                **notice_scope,
            },
        )

    watcher.pop("baseline_pending", None)
    ctx.touch(watcher)
    return watcher


# ── price comparison ───────────────────────────────────────────────────────────


def _parse_price_float(text_val: str) -> float | None:
    """Best-effort parse of a human price string to a float for comparison.

    Handles common Ukrainian/European formats: «1 234,56», «1.234,56», «1234.56».
    Returns None if unparseable — the caller skips drop notification.
    """
    value = _price_decimal(text_val)
    return float(value) if value is not None else None


def _price_decimal(value):
    if not isinstance(value, str) or not value or len(value) > 40:
        return None
    if re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3})+,[0-9]+", value):
        value = value.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+\.[0-9]+", value):
        value = value.replace(",", "")
    elif re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:[ '\u00a0\u202f][0-9]{3})+)(?:[.,][0-9]+)?", value):
        value = re.sub(r"[ '\u00a0\u202f]", "", value).replace(",", ".")
    else:
        return None
    try:
        parsed = Decimal(value)
        return parsed if parsed.is_finite() and parsed >= 0 else None
    except InvalidOperation:
        return None


def _price_dropped(old: str, new: str) -> bool:
    old_f = _price_decimal(old)
    new_f = _price_decimal(new)
    if old_f is None or new_f is None:
        return False
    # Zero is a legitimate new price; comparisons never use lossy float coercion.
    return new_f < old_f and old_f > 0
