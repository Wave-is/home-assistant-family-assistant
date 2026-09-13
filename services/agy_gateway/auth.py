"""Constant-time bearer authentication for AGY gateway."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from aiohttp import web

PUBLIC_PATHS = {"/health"}


def verify_bearer_token(auth_header: str | None, expected_key: str) -> bool:
    """Verify authorization header using constant-time string comparison."""
    if not auth_header or not expected_key:
        return False
    parts = auth_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    token = parts[1].strip()
    return hmac.compare_digest(token.encode("utf-8"), expected_key.encode("utf-8"))


def create_auth_middleware(
    expected_key: str,
) -> Callable[
    [web.Request, Callable[[web.Request], Awaitable[web.StreamResponse]]],
    Awaitable[web.StreamResponse],
]:
    """Create an aiohttp middleware enforcing constant-time Bearer authentication."""

    @web.middleware
    async def auth_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        # Public status endpoints bypass authentication
        if request.path in PUBLIC_PATHS and request.method == "GET":
            return await handler(request)

        auth_header = request.headers.get("Authorization")
        if not verify_bearer_token(auth_header, expected_key):
            return web.json_response({"error": "unauthorized"}, status=401)

        return await handler(request)

    return auth_middleware
