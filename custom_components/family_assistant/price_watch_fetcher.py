"""Async price fetcher: HTTP fetch + schema.org/Product parsing for HA.

This module is the only place where network I/O happens for price watching.
It runs entirely on the HA event loop via aiohttp.

Security
--------
* Reuses the public-article transport's pinned DNS/socket peer checks.
* Public HTTPS:443 only, with bounded revalidated redirects; no credentials,
  proxies, cookies, decompression or embedded-resource requests.
* DNS and all redirects share a 10-second budget; bodies stream to a 512 KiB cap.
* Errors are stable codes, never provider exception text or URLs.

Algorithm
---------
1. Bounded public HTTPS GET through the pinned transport.
2. Parse <script type="application/ld+json"> tags for schema.org/Product.
3. Extract offers.price + offers.priceCurrency + offers.availability.
4. Fallback: regex search for "availability":"…" in raw HTML.
5. Return a PriceFetchResult dataclass.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from .domain import price_watch as domain
from .domain.validation import DomainError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .runtime import Runtime

_FETCH_TIMEOUT = 10  # seconds
_POLL_INTERVAL = timedelta(minutes=30)

# Tracking parameters to strip from URLs before storing / fetching
_TRACKING_PARAMS = frozenset(
    {
        "_gl",
        "_ga",
        "_gid",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "yclid",
        "msclkid",
        "ref",
        "referrer",
    }
)

# Availability mapping from schema.org slugs → our canonical values
_AVAILABILITY_MAP: dict[str, str] = {
    "instock": "in_stock",
    "instoreonly": "in_stock",
    "limitedavailability": "in_stock",
    "onlineonly": "in_stock",
    "preorder": "preorder",
    "presale": "preorder",
    "outofstock": "out_of_stock",
    "soldout": "out_of_stock",
    "discontinued": "discontinued",
    "backorder": "backorder",
}

_AVAILABILITY_REGEX = re.compile(r'"availability"\s*:\s*"([^"]{4,80})"', re.IGNORECASE)


def clean_url(url: str) -> str:
    """Strip known tracking parameters from a URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
    # Rebuild query string preserving order as much as possible
    new_query = urlencode({k: v[0] for k, v in cleaned.items()})
    return urlunparse(parsed._replace(query=new_query))


# ── HTML parser ────────────────────────────────────────────────────────────────


class _LdJsonCollector(HTMLParser):
    """Collect all <script type="application/ld+json"> contents."""

    def __init__(self) -> None:
        super().__init__()
        self._inside = False
        self.blocks: list[str] = []
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            attr_dict = dict(attrs)
            if (attr_dict.get("type") or "").lower() == "application/ld+json":
                self._inside = True
                self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._inside:
            self._inside = False
            self.blocks.append("".join(self._buf))

    def handle_data(self, data: str) -> None:
        if self._inside:
            self._buf.append(data)


# ── result dataclass ───────────────────────────────────────────────────────────


@dataclass
class PriceFetchResult:
    price_text: str = ""
    currency: str = ""
    availability: str = "unknown"
    error: str = ""


# ── parsing helpers ────────────────────────────────────────────────────────────


def _parse_availability(raw: str) -> str:
    if not isinstance(raw, str):
        return "unknown"
    slug = raw.rsplit("/", 1)[-1].lower().replace(" ", "")
    return _AVAILABILITY_MAP.get(slug, "unknown")


def _extract_from_ld_json(html: str) -> PriceFetchResult | None:
    parser = _LdJsonCollector()
    parser.feed(html)
    for block in parser.blocks:
        try:
            data: Any = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        # Handle both a single object and a @graph array
        items: list[Any] = []
        if isinstance(data, dict):
            items = data.get("@graph", [data])
        elif isinstance(data, list):
            items = data
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            type_val = item.get("@type", "")
            if not isinstance(type_val, (str, list)):
                continue
            types = [type_val] if isinstance(type_val, str) else type_val
            if not any(t in ("Product", "ProductGroup") for t in types):
                continue
            offers_raw = item.get("offers")
            if offers_raw is None:
                continue
            # «offers» can be a single dict or a list — take first available
            if isinstance(offers_raw, list):
                offers_list = offers_raw
            elif isinstance(offers_raw, dict):
                offers_list = [offers_raw]
            else:
                continue
            for offer in offers_list:
                if not isinstance(offer, dict):
                    continue
                price_val = offer.get("price")
                if price_val is None:
                    price_val = offer.get("lowPrice")
                avail_raw = offer.get("availability", "")
                availability = _parse_availability(avail_raw) if avail_raw else "unknown"
                price_str = str(price_val).strip() if price_val is not None else ""
                currency = str(offer.get("priceCurrency", "")).strip().upper()
                if len(price_str) > 40:
                    return PriceFetchResult(error="invalid_response")
                if price_str or availability != "unknown":
                    return PriceFetchResult(
                        # The domain rejects oversized/invalid values; truncating
                        # first could turn a hostile numeric prefix into a price.
                        price_text=price_str,
                        currency=currency[:3] if len(currency) == 3 else "",
                        availability=availability,
                    )
    return None


def _extract_fallback(html: str) -> PriceFetchResult | None:
    """Regex fallback when JSON-LD is absent."""
    match = _AVAILABILITY_REGEX.search(html)
    if match:
        avail = _parse_availability(match.group(1))
        return PriceFetchResult(availability=avail)
    return None


def parse_html(html: str) -> PriceFetchResult:
    result = _extract_from_ld_json(html)
    if result is None:
        result = _extract_fallback(html)
    return result or PriceFetchResult()


# ── async fetcher ──────────────────────────────────────────────────────────────


async def fetch_price(url: str, *, scope_check=lambda: None) -> PriceFetchResult:
    """Return bounded observations; cancellation and revoked authority propagate."""
    from .assistant import article

    current, visited = url, set()
    try:
        async with asyncio.timeout(_FETCH_TIMEOUT):
            for count in range(article.MAX_REDIRECTS + 1):
                target = await article._target(current, scope_check, article._system_resolve)
                if target.url in visited:
                    raise DomainError("article_invalid_url")
                visited.add(target.url)
                hop = await article._request_hop(target, scope_check)
                await article._check(scope_check)
                if hop.status in article._REDIRECTS:
                    if count == article.MAX_REDIRECTS or not hop.location:
                        raise DomainError("article_invalid_url")
                    current = urljoin(target.url, hop.location)
                    continue
                if len(hop.body) > article.MAX_BODY_BYTES:
                    raise DomainError("article_too_large")
                charset = article._CHARSETS.get((hop.charset or "utf-8").casefold())
                if charset is None:
                    raise DomainError("article_unsupported")
                result = parse_html(hop.body.decode(charset, errors="strict"))
                if result.error or not result.price_text and result.availability == "unknown":
                    raise DomainError("article_invalid_content")
                # Malformed prices cannot erase a good baseline or fabricate a drop.
                domain.validate_observation(result.price_text, result.currency)
                return result
    except DomainError as error:
        if error.code in {"observation_revoked", "backup_in_progress"}:
            raise
        codes = {
            "article_invalid_url": "invalid_url",
            "article_timeout": "timeout",
            "article_too_large": "response_too_large",
            "article_unsupported": "unsupported_response",
            "article_unavailable": "unavailable",
        }
        return PriceFetchResult(error=codes.get(error.code, "invalid_response"))
    except TimeoutError:
        return PriceFetchResult(error="timeout")
    except (ValueError, TypeError, AttributeError, RecursionError, OSError):
        return PriceFetchResult(error="invalid_response")
    return PriceFetchResult(error="unavailable")


# ── HA scheduler ──────────────────────────────────────────────────────────────


class PriceWatchScheduler:
    """Periodically poll all registered watchers and record results into the engine."""

    def __init__(self, hass: HomeAssistant, entry, runtime: Runtime) -> None:
        self._hass = hass
        self._entry = entry
        self._runtime = runtime
        self._unsub = None
        self._task = None
        self._stopped = True

    def start(self) -> None:
        from homeassistant.helpers.event import async_track_time_interval

        if self._unsub is not None:
            return
        self._stopped = False
        self._unsub = async_track_time_interval(self._hass, self._interval, _POLL_INTERVAL)
        self.request()

    async def stop(self) -> None:
        self._stopped = True
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _interval(self, _now) -> None:
        self.request()

    def request(self):
        if not self._active() or self._task is not None and not self._task.done():
            return
        self._task = self._hass.async_create_background_task(
            self._poll_all(), "Family Assistant price watch"
        )

    def _active(self):
        data = self._hass.data.get("family_assistant", {})
        return (
            not self._stopped
            and not data.get("backup")
            and data.get("entries", {}).get(self._entry.entry_id) is self._runtime
            and self._entry.runtime_data is self._runtime
            and not self._runtime.engine.shadow_mode
            and "price_watch" in self._runtime.engine.snapshot()["settings"]["modules"]
        )

    async def _poll_all(self) -> None:
        try:
            for watcher_id in self._runtime.engine.snapshot().get("price_watches", {}):
                if not self._active():
                    return
                await self._poll_one(watcher_id)
            self._runtime.health.pop("price_watch", None)
        except DomainError as error:
            if error.code not in {"observation_revoked", "backup_in_progress"}:
                self._runtime.health["price_watch"] = "unavailable"
        except Exception:  # noqa: BLE001 - never log provider or Store exception payloads
            self._runtime.health["price_watch"] = "unavailable"

    async def _poll_one(self, watcher_id: str) -> None:
        from homeassistant.util import dt as dt_util

        scope = domain.observation_scope(self._runtime.engine.snapshot(), watcher_id)
        if scope is None:
            return

        def check():
            if (
                not self._active()
                or domain.observation_scope(self._runtime.engine.snapshot(), watcher_id) != scope
            ):
                raise DomainError("observation_revoked")

        try:
            check()
            result = await fetch_price(scope["url"], scope_check=check)
            check()

            def commit(ctx):
                check()
                return domain.record_observation(ctx, scope, vars(result))

            await self._runtime.engine.background_update(
                "price_watch_observation", dt_util.utcnow(), commit
            )
            self._runtime.updated()
        except DomainError as error:
            if error.code not in {"observation_revoked", "backup_in_progress"}:
                raise
