"""Search snippets are untrusted evidence, never executable tool instructions."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from ..domain.validation import DomainError, text
from .http import endpoint, request_json


async def public_url(value, resolve=None):
    """Filter literal AND DNS private addresses before presenting a result link.

    This function does not fetch the result. Any future page-fetch adapter must
    pin the validated addresses at connection time to prevent DNS rebinding.
    """
    try:
        endpoint(value, allow_http=True, allow_query=True)
        parsed = urlsplit(value)
        if parsed.port not in {None, 80, 443} or "." not in parsed.hostname:
            return False
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname.endswith((".local", ".localhost", ".internal", ".home", ".lan")):
            return False
        try:
            addresses = [ipaddress.ip_address(hostname)]
        except ValueError:
            resolver = resolve or asyncio.get_running_loop().getaddrinfo
            async with asyncio.timeout(3):
                entries = await resolver(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(entry[4][0]) for entry in entries]
        return bool(addresses) and all(address.is_global for address in addresses)
    except (DomainError, ValueError, OSError, TimeoutError):
        return False


class Search:
    def __init__(self, session, config, *, resolve=None):
        self.session, self.resolve = session, resolve
        self.url = endpoint(config["url"], allow_http=config.get("allow_http", False))
        self.headers = (
            {"Authorization": f"Bearer {config['api_key']}"} if config.get("api_key") else {}
        )

    async def query(self, query, language, *, child=False):
        data = await request_json(
            self.session,
            "POST",
            self.url + "/search",
            timeout=10,
            headers=self.headers,
            data={
                "q": text(query, "query", 300),
                "format": "json",
                "language": language,
                "safesearch": 2 if child else 1,
            },
        )
        entries = data.get("results")
        if not isinstance(entries, list):
            raise DomainError("provider_bad_response")
        result, seen = [], set()
        for item in entries[:10]:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or url in seen or not await public_url(url, self.resolve):
                continue
            seen.add(url)
            if not all(isinstance(item.get(k, ""), str) for k in ("title", "content")):
                continue
            result.append(
                {
                    "url": url,
                    "title": item.get("title", "")[:200],
                    "snippet": item.get("content", "")[:1200],
                }
            )
            if len(result) == 5:
                break
        return result
