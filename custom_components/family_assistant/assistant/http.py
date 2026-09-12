"""Bounded requests to explicit owner-configured provider endpoints only."""

import asyncio
import ipaddress
import json
from urllib.parse import urlsplit

import aiohttp

from ..domain.validation import DomainError


def endpoint(value, *, allow_http=False, allow_query=False):
    if not isinstance(value, str) or len(value) > 512 or any(c.isspace() for c in value):
        raise DomainError("provider_invalid_url")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ({"https", "http"} if allow_http else {"https"})
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and (allow_query or not parsed.query)
            and not parsed.fragment
            and (parsed.port is None or 1 <= parsed.port <= 65535)
            and "\\" not in value
            and "%" not in parsed.netloc
        )
        if not valid:
            raise ValueError
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address and (address.is_link_local or address.is_multicast or address.is_unspecified):
            raise ValueError
    except ValueError:
        raise DomainError("provider_invalid_url") from None
    return value.rstrip("/")


async def request_json(session, method, url, *, timeout=15, limit=262144, **kwargs):
    try:
        async with session.request(
            method,
            url,
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=timeout, connect=min(15, timeout)),
            **kwargs,
        ) as response:
            if response.status in {401, 403}:
                raise DomainError("provider_authentication")
            if response.status == 429:
                raise DomainError("provider_quota_exceeded")
            if not 200 <= response.status < 300:
                raise DomainError("provider_unreachable")
            body = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                body.extend(chunk)
                if len(body) > limit:
                    raise DomainError("provider_bad_response")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise DomainError("provider_bad_response")
            return result
    except TimeoutError:
        raise DomainError("provider_timeout") from None
    except (aiohttp.ClientError, OSError):
        raise DomainError("provider_unreachable") from None
    except DomainError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise DomainError("provider_bad_response") from None
    except asyncio.CancelledError:
        raise
