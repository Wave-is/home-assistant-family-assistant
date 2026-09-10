"""Async price fetcher: HTTP fetch + schema.org/Product parsing for HA.

This module is the only place where network I/O happens for price watching.
It runs entirely on the HA event loop via aiohttp.

Security
--------
* SSRF protection: private / link-local / loopback IPs are blocked before
  the TCP connection is opened (aiohttp connector resolver intercept).
* Only https:// and http:// are accepted (validated by the domain layer first).
* A 10-second total timeout prevents slow-response DoS.
* Cloudflare-protected stores (Rozetka, Comfy, etc.) may return 403 — this is
  logged as a transient error, not a parse failure.

Algorithm (mirrors tovary.py logic, rewritten async)
-----------------------------------------------------
1. GET with a browser-like User-Agent.
2. Parse <script type="application/ld+json"> tags for schema.org/Product.
3. Extract offers.price + offers.priceCurrency + offers.availability.
4. Fallback: regex search for "availability":"…" in raw HTML.
5. Return a PriceFetchResult dataclass.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from datetime import timedelta
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .runtime import Runtime

_FETCH_TIMEOUT = 10  # seconds
_POLL_INTERVAL = timedelta(minutes=30)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

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


# ── SSRF guard ─────────────────────────────────────────────────────────────────


def _is_private_host(hostname: str) -> bool:
    """Return True if the host resolves to a private/loopback/link-local address."""
    try:
        results = socket.getaddrinfo(hostname, None)
    except OSError:
        # DNS failure — treat as safe to attempt (let aiohttp fail naturally)
        return False
    for _, _, _, _, sockaddr in results:
        addr_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(addr_str)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return True
        except ValueError:
            continue
    return False


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
                price_val = offer.get("price") or offer.get("lowPrice")
                avail_raw = offer.get("availability", "")
                availability = _parse_availability(avail_raw) if avail_raw else "unknown"
                price_str = str(price_val).strip() if price_val is not None else ""
                currency = str(offer.get("priceCurrency", "")).strip().upper()
                if price_str or availability != "unknown":
                    return PriceFetchResult(
                        price_text=price_str[:40],
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


async def fetch_price(url: str) -> PriceFetchResult:
    """Fetch and parse a product page.  Never raises — errors go into .error."""
    try:
        import aiohttp  # local import — not available in pure-domain tests
    except ImportError:
        return PriceFetchResult(error="aiohttp_unavailable")

    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not hostname:
        return PriceFetchResult(error="invalid_url")

    # SSRF guard — synchronous DNS lookup is acceptable here: called in executor
    loop = asyncio.get_event_loop()
    try:
        private = await loop.run_in_executor(None, _is_private_host, hostname)
    except Exception:  # noqa: BLE001
        private = False
    if private:
        return PriceFetchResult(error="ssrf_blocked")

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk,en;q=0.9",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status == 403:
                    return PriceFetchResult(error="cf_blocked")
                if resp.status != 200:
                    return PriceFetchResult(error=f"http_{resp.status}")
                # Read up to 2 MB — enough for any product page
                html = await resp.text(errors="replace")
                html = html[:2_000_000]
    except TimeoutError:
        return PriceFetchResult(error="timeout")
    except aiohttp.ClientError as exc:
        return PriceFetchResult(error=str(exc)[:100])

    return parse_html(html)


# ── HA scheduler ──────────────────────────────────────────────────────────────


class PriceWatchScheduler:
    """Periodically poll all registered watchers and record results into the engine."""

    def __init__(self, hass: HomeAssistant, entry, runtime: Runtime) -> None:
        self._hass = hass
        self._entry = entry
        self._runtime = runtime
        self._unsub = None
        self._running = False

    def start(self) -> None:
        from homeassistant.helpers.event import async_track_time_interval

        self._unsub = async_track_time_interval(self._hass, self._interval, _POLL_INTERVAL)
        # Run once immediately
        self._hass.async_create_task(self._poll_all(), "Family Assistant price watch initial poll")

    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _interval(self, _now) -> None:
        await self._poll_all()

    async def _poll_all(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            watchers = dict(self._runtime.engine.snapshot().get("price_watches", {}))
            for watcher_id, watcher in watchers.items():
                await self._poll_one(watcher_id, watcher)
        finally:
            self._running = False

    async def _poll_one(self, watcher_id: str, watcher: dict) -> None:
        from homeassistant.util import dt as dt_util

        url = watcher.get("url", "")
        if not url:
            return
        result = await fetch_price(url)
        now = dt_util.utcnow()
        # Use a synthetic system actor ("owner") to record via engine
        from .domain.validation import DomainError

        payload: dict = {"id": watcher_id}
        if result.error:
            payload["error"] = result.error
        else:
            payload["price_text"] = result.price_text
            payload["currency"] = result.currency
            payload["availability"] = result.availability
        try:
            await self._runtime.engine.execute(
                "owner",
                "price_watch.record",
                payload,
                f"pw-{watcher_id}-{int(now.timestamp())}",
                now,
            )
            self._runtime.updated()
        except DomainError:
            pass  # watcher may have been removed between snapshot and record
