"""Bounded retrieval and text extraction for explicitly requested public articles."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from yarl import URL

from ..domain.validation import DomainError

MAX_URL_CHARS = 2048
MAX_REDIRECTS = 3
MAX_BODY_BYTES = 512 * 1024
MAX_TITLE_CHARS = 200
MAX_TEXT_CHARS = 20_000
MAX_DNS_ADDRESSES = 16
DNS_TIMEOUT = 3
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 3
TOTAL_TIMEOUT = 10

_REDIRECTS = {301, 302, 303, 307, 308}
_CONTENT_TYPES = {"text/html", "text/plain"}
_CHARSETS = {
    "ascii": "ascii",
    "cp1251": "cp1251",
    "iso-8859-1": "iso-8859-1",
    "latin-1": "iso-8859-1",
    "us-ascii": "ascii",
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "windows-1251": "cp1251",
}
_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".home", ".lan")
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
_IGNORED_TAGS = {
    "button",
    "canvas",
    "form",
    "iframe",
    "input",
    "noscript",
    "object",
    "script",
    "select",
    "style",
    "svg",
    "template",
    "textarea",
}
_VOID_IGNORED_TAGS = {"input"}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE = re.compile(r"[^\S\n]+")
_BLANKS = re.compile(r"\n{3,}")

ScopeCheck = Callable[[], Awaitable[None] | None]
Resolve = Callable[[str, int], Awaitable[Sequence[str]]]


@dataclass(frozen=True)
class _PinnedTarget:
    url: str
    hostname: str
    port: int
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]


@dataclass(frozen=True)
class _Hop:
    status: int
    body: bytes = b""
    content_type: str = ""
    charset: str | None = None
    location: str | None = None


class _PinnedResolver(AbstractResolver):
    """Resolve exactly one original hostname to an immutable vetted address set."""

    def __init__(self, target: _PinnedTarget):
        self._target = target

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        if (
            host.casefold().rstrip(".") != self._target.hostname.casefold().rstrip(".")
            or type(port) is not int
            or port != self._target.port
            or family not in {socket.AF_UNSPEC, socket.AF_INET, socket.AF_INET6}
        ):
            raise OSError
        result = []
        for address in self._target.addresses:
            item_family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
            if family not in {socket.AF_UNSPEC, item_family}:
                continue
            result.append(
                ResolveResult(
                    hostname=host,
                    host=str(address),
                    port=self._target.port,
                    family=item_family,
                    proto=socket.IPPROTO_TCP,
                    flags=socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                )
            )
        if not result:
            raise OSError
        return result

    async def close(self) -> None:
        return None


def _pinned_socket_factory(target: _PinnedTarget):
    """Build sockets only for address tuples supplied by the pinned resolver."""
    allowed = set(target.addresses)

    def create(addr_info):
        family, type_, proto, _canonical_name, sockaddr = addr_info
        try:
            peer = ipaddress.ip_address(sockaddr[0])
            port = sockaddr[1]
        except (IndexError, TypeError, ValueError):
            raise OSError from None
        expected_family = socket.AF_INET6 if peer.version == 6 else socket.AF_INET
        if (
            peer not in allowed
            or family != expected_family
            or type_ != socket.SOCK_STREAM
            or proto != socket.IPPROTO_TCP
            or type(port) is not int
            or port != target.port
        ):
            raise OSError
        return socket.socket(family=family, type=type_, proto=proto)

    return create


class _ArticleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._ignored: list[str] = []
        self._in_head = False
        self._in_title = False
        self._title: list[str] = []
        self._title_chars = 0
        self._parts: list[str] = []
        self._text_chars = 0
        self.overflow = False

    def handle_starttag(self, tag: str, _attrs) -> None:
        tag = tag.casefold()
        if self._ignored:
            if tag in _IGNORED_TAGS and tag not in _VOID_IGNORED_TAGS:
                self._ignored.append(tag)
            return
        if tag == "head":
            self._in_head = True
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in _IGNORED_TAGS and tag not in _VOID_IGNORED_TAGS:
            self._ignored.append(tag)
            return
        if tag in _BLOCK_TAGS:
            self._separator()

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._ignored:
            if tag == self._ignored[-1]:
                self._ignored.pop()
            return
        if tag == "head":
            self._in_head = False
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in _BLOCK_TAGS:
            self._separator()

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        if self._in_title:
            remaining = MAX_TITLE_CHARS + 1 - self._title_chars
            if remaining > 0:
                selected = data[:remaining]
                self._title.append(selected)
                self._title_chars += len(selected)
            return
        if self._in_head:
            return
        self._append(data)

    def _separator(self) -> None:
        if self._parts and self._parts[-1] != "\n":
            self._parts.append("\n")

    def _append(self, value: str) -> None:
        if not value:
            return
        self._text_chars += len(value)
        if self._text_chars > MAX_TEXT_CHARS:
            self.overflow = True
            return
        self._parts.append(value)

    def result(self) -> tuple[str, str]:
        title = _clean_text(" ".join(self._title))[:MAX_TITLE_CHARS]
        text = _clean_text("".join(self._parts))
        if self.overflow or len(text) > MAX_TEXT_CHARS:
            raise DomainError("article_too_large")
        if not text:
            raise DomainError("article_invalid_content")
        return title, text


def _clean_text(value: str) -> str:
    value = _CONTROL.sub("", value).replace("\r\n", "\n").replace("\r", "\n")
    value = _SPACE.sub(" ", value)
    value = "\n".join(line.strip() for line in value.splitlines())
    return _BLANKS.sub("\n\n", value).strip()


def _safe_address(value: str):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise DomainError("article_invalid_url") from None
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            raise DomainError("article_invalid_url")
        # Translation mechanisms can obscure the effective IPv4 route. The public
        # first slice rejects them even when their outer IPv6 range is global.
        if address.sixtofour is not None or address.teredo is not None:
            raise DomainError("article_invalid_url")
    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise DomainError("article_invalid_url")
    return address


def _normalize_url(value: object) -> tuple[str, str, int]:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_URL_CHARS
        or "\\" in value
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise DomainError("article_invalid_url")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
        if (
            parsed.scheme.casefold() != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or port not in {None, 443}
            or "%" in parsed.netloc
        ):
            raise ValueError
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
            hostname = hostname.rstrip(".").encode("idna").decode("ascii").casefold()
            labels = hostname.split(".")
            if (
                len(labels) < 2
                or any(
                    not label
                    or len(label) > 63
                    or label.startswith("-")
                    or label.endswith("-")
                    or not re.fullmatch(r"[a-z0-9-]+", label)
                    for label in labels
                )
                or hostname.endswith(_LOCAL_SUFFIXES)
                or all(character in "0123456789." for character in hostname)
            ):
                raise ValueError from None
        else:
            hostname = str(_safe_address(str(literal)))
        normalized = str(URL(value).with_host(hostname).with_fragment(None))
        if len(normalized) > MAX_URL_CHARS:
            raise ValueError
        return normalized, hostname, 443
    except (UnicodeError, ValueError):
        raise DomainError("article_invalid_url") from None


async def _system_resolve(hostname: str, port: int) -> Sequence[str]:
    entries = await asyncio.get_running_loop().getaddrinfo(
        hostname,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return [entry[4][0] for entry in entries]


async def _check(scope_check: ScopeCheck) -> None:
    result = scope_check()
    if inspect.isawaitable(result):
        await result


async def _target(
    url: str,
    scope_check: ScopeCheck,
    resolve: Resolve,
) -> _PinnedTarget:
    normalized, hostname, port = _normalize_url(url)
    await _check(scope_check)
    try:
        async with asyncio.timeout(DNS_TIMEOUT):
            values = await resolve(hostname, port)
    except TimeoutError:
        raise DomainError("article_timeout") from None
    except (OSError, socket.gaierror):
        raise DomainError("article_unavailable") from None
    await _check(scope_check)
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise DomainError("article_invalid_url")
    if len(values) > MAX_DNS_ADDRESSES:
        raise DomainError("article_invalid_url")
    addresses = tuple(dict.fromkeys(_safe_address(value) for value in values))
    if not addresses:
        raise DomainError("article_invalid_url")
    return _PinnedTarget(normalized, hostname, port, addresses)


async def _request_hop(
    target: _PinnedTarget,
    scope_check: ScopeCheck,
    *,
    ssl_context=None,
) -> _Hop:
    """Request one already-vetted hop; tests may call this with a synthetic target."""
    connector = aiohttp.TCPConnector(
        resolver=_PinnedResolver(target),
        use_dns_cache=True,
        force_close=True,
        limit=1,
        limit_per_host=1,
        ssl=ssl_context if ssl_context is not None else True,
        socket_factory=_pinned_socket_factory(target),
    )
    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=CONNECT_TIMEOUT,
        sock_connect=CONNECT_TIMEOUT,
        sock_read=READ_TIMEOUT,
    )
    try:
        async with aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.DummyCookieJar(),
            trust_env=False,
            auto_decompress=False,
            timeout=timeout,
            read_bufsize=8192,
            max_headers=64,
        ) as session:
            await _check(scope_check)
            async with session.get(
                target.url,
                allow_redirects=False,
                headers={
                    "Accept": "text/html,text/plain",
                    "Accept-Encoding": "identity",
                    "User-Agent": "Home-Assistant-Family-Assistant/article-fetch",
                },
            ) as response:
                await _check(scope_check)
                locations = response.headers.getall("Location", [])
                if len(locations) > 1:
                    raise DomainError("article_invalid_content")
                if response.status in _REDIRECTS:
                    return _Hop(response.status, location=locations[0] if locations else None)
                if response.status != 200:
                    raise DomainError("article_unavailable")
                if response.headers.get("Content-Encoding", "identity").casefold() not in {
                    "",
                    "identity",
                }:
                    raise DomainError("article_unsupported")
                content_type = response.content_type.casefold()
                if content_type not in _CONTENT_TYPES:
                    raise DomainError("article_unsupported")
                if response.content_length is not None and response.content_length > MAX_BODY_BYTES:
                    raise DomainError("article_too_large")
                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    body.extend(chunk)
                    if len(body) > MAX_BODY_BYTES:
                        raise DomainError("article_too_large")
                    await _check(scope_check)
                return _Hop(
                    response.status,
                    bytes(body),
                    content_type,
                    response.charset,
                )
    except asyncio.CancelledError:
        raise
    except DomainError:
        raise
    except TimeoutError:
        raise DomainError("article_timeout") from None
    except (aiohttp.ClientError, OSError):
        raise DomainError("article_unavailable") from None


def extract(body: bytes, content_type: str, charset: str | None = None) -> dict:
    """Extract bounded visible text from one already bounded response body."""
    if not isinstance(body, bytes) or not body:
        raise DomainError("article_invalid_content")
    if len(body) > MAX_BODY_BYTES:
        raise DomainError("article_too_large")
    if content_type not in _CONTENT_TYPES:
        raise DomainError("article_unsupported")
    selected = "utf-8" if charset is None else _CHARSETS.get(charset.casefold())
    if selected is None:
        raise DomainError("article_unsupported")
    try:
        decoded = body.decode(selected, errors="strict")
        if content_type == "text/plain":
            text = _clean_text(decoded)
            if not text:
                raise DomainError("article_invalid_content")
            if len(text) > MAX_TEXT_CHARS:
                raise DomainError("article_too_large")
            return {"title": "", "text": text}
        parser = _ArticleHTMLParser()
        parser.feed(decoded)
        parser.close()
        title, text = parser.result()
        return {"title": title, "text": text}
    except UnicodeError:
        raise DomainError("article_invalid_content") from None
    except DomainError:
        raise
    except (ValueError, RecursionError):
        raise DomainError("article_invalid_content") from None


async def fetch(
    url: str,
    *,
    scope_check: ScopeCheck,
    resolve: Resolve | None = None,
    _test_request_hop: Callable[[_PinnedTarget, ScopeCheck], Awaitable[_Hop]] | None = None,
) -> dict:
    """Fetch one explicit public HTTPS article without following embedded resources."""
    resolver = resolve or _system_resolve
    request_hop = _test_request_hop or _request_hop
    requested, _, _ = _normalize_url(url)
    current = requested
    visited = set()
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            for redirect_count in range(MAX_REDIRECTS + 1):
                if current in visited:
                    raise DomainError("article_invalid_url")
                visited.add(current)
                target = await _target(current, scope_check, resolver)
                await _check(scope_check)
                hop = await request_hop(target, scope_check)
                await _check(scope_check)
                if hop.status in _REDIRECTS:
                    if redirect_count == MAX_REDIRECTS or not hop.location:
                        raise DomainError("article_invalid_url")
                    current = _normalize_url(urljoin(target.url, hop.location))[0]
                    continue
                if hop.status != 200 or len(hop.body) > MAX_BODY_BYTES:
                    raise DomainError(
                        "article_too_large"
                        if len(hop.body) > MAX_BODY_BYTES
                        else "article_unavailable"
                    )
                result = extract(hop.body, hop.content_type, hop.charset)
                await _check(scope_check)
                return {
                    **result,
                    "requested_url": requested,
                    "final_url": target.url,
                }
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        raise DomainError("article_timeout") from None
    raise DomainError("article_unavailable")


__all__ = ["extract", "fetch"]
