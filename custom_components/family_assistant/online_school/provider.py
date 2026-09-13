"""Read-only A+ STEAM/Respublika session, pinned to one discovered student per fetch."""

from __future__ import annotations

import asyncio
import math
import re
import time
from copy import deepcopy
from datetime import datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from ..domain.validation import DomainError
from . import parsing

ERROR_CODES = frozenset(
    {
        "online_school_auth_failed",
        "online_school_unavailable",
        "online_school_rate_limited",
        "online_school_invalid_response",
        "online_school_student_mismatch",
        "online_school_invalid_config",
        "online_school_timeout",
    }
)
_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=5, sock_read=10)


class OnlineSchoolError(DomainError):
    """Only a stable code and bounded retry delay; never remote diagnostics."""

    def __init__(self, code, *, retry_after=0):
        super().__init__(code if code in ERROR_CODES else "online_school_unavailable")
        self.retry_after = min(3600, max(0, int(retry_after)))


def _base_url(value):
    normalized = parsing.https_url(value)
    if normalized is None:
        raise OnlineSchoolError("online_school_invalid_config")
    parts = urlsplit(normalized)
    if parts.path not in {"", "/"} or parts.query or parts.fragment or "#" in value:
        raise OnlineSchoolError("online_school_invalid_config")
    # An origin is intentionally the entire supported base, not a generic proxy
    # prefix or a caller-supplied route holding credentials/query parameters.
    return "https://" + parts.netloc.lower()


class RespublikaClient:
    """Isolated cookies and finite reads. Construction never performs network I/O."""

    def __init__(self, base_url, username, password, *, session_factory=None):
        self.base_url = _base_url(base_url)
        if (
            not isinstance(username, str)
            or not 1 <= len(username) <= 320
            or username != username.strip()
            or any(ord(char) < 32 for char in username)
            or not isinstance(password, str)
            or not 1 <= len(password) <= 1024
            or any(ord(char) < 32 for char in password)
        ):
            raise OnlineSchoolError("online_school_invalid_config")
        self._username, self._password = username, password
        self._session_factory = session_factory or aiohttp.ClientSession
        self._session = None
        self._students = None
        self._closed = False
        self._retry_at = 0.0
        self._lock = asyncio.Lock()

    def _ready(self):
        if self._closed:
            raise OnlineSchoolError("online_school_unavailable")
        remaining = math.ceil(self._retry_at - time.monotonic())
        if remaining > 0:
            raise OnlineSchoolError("online_school_rate_limited", retry_after=remaining)

    def _session_for_request(self):
        self._ready()
        if self._session is None:
            self._session = self._session_factory(
                cookie_jar=aiohttp.CookieJar(),
                timeout=_TIMEOUT,
                trust_env=False,
                headers={"User-Agent": "FamilyAssistant-online-school/1"},
                raise_for_status=False,
            )
        return self._session

    def _redirect(self, current, location, student_id):
        if not isinstance(location, str) or len(location) > 2048:
            raise OnlineSchoolError("online_school_invalid_response")
        candidate = parsing.https_url(urljoin(current, location))
        if (
            candidate is None
            or urlsplit(candidate).netloc.lower() != urlsplit(self.base_url).netloc
        ):
            raise OnlineSchoolError("online_school_invalid_response")
        parsed = urlsplit(candidate)
        redirect_path = parsed.path or "/"
        if parsed.query or parsed.fragment or "#" in location or "%" in parsed.path:
            raise OnlineSchoolError("online_school_invalid_response")
        paths = {"/auth", "/daybook", "/"}
        if student_id is not None:
            paths.add("/daybook/" + student_id)
            # Periods are built from validated numbers, not supplied server URLs.
            if re.fullmatch(
                rf"/(?:daybook/get|studentparent/journal/get)/{re.escape(student_id)}(?:/[1-9][0-9]?)?",
                redirect_path,
            ):
                paths.add(redirect_path)
        if redirect_path not in paths:
            raise OnlineSchoolError("online_school_invalid_response")
        return self.base_url + redirect_path

    async def _request(self, method, path, *, data=None, student_id=None, json_request=False):
        session = self._session_for_request()
        current = self.base_url + path
        try:
            for _ in range(4):
                self._ready()
                async with session.request(
                    method,
                    current,
                    data=data,
                    allow_redirects=False,
                    timeout=_TIMEOUT,
                    headers={"Accept": "application/json" if json_request else "text/html"},
                ) as response:
                    self._ready()
                    status = response.status
                    if status in {401, 403, 419}:
                        self._students = None
                        raise OnlineSchoolError("online_school_auth_failed")
                    if status == 429:
                        value = response.headers.get("Retry-After", "60")
                        seconds = (
                            min(3600, max(1, int(value)))
                            if isinstance(value, str) and re.fullmatch(r"[0-9]{1,8}", value)
                            else 60
                        )
                        self._retry_at = time.monotonic() + seconds
                        raise OnlineSchoolError("online_school_rate_limited", retry_after=seconds)
                    if status in {301, 302, 303, 307, 308}:
                        target = self._redirect(
                            current, response.headers.get("Location"), student_id
                        )
                        if json_request and urlsplit(target).path in {"/auth", "/"}:
                            self._students = None
                            raise OnlineSchoolError("online_school_auth_failed")
                        if method == "POST":
                            if status in {307, 308}:
                                raise OnlineSchoolError("online_school_auth_failed")
                            method, data = "GET", None
                        current = target
                        continue
                    if not 200 <= status < 300:
                        raise OnlineSchoolError("online_school_unavailable")
                    if (
                        response.content_length is not None
                        and response.content_length > parsing.MAX_BODY
                    ):
                        raise OnlineSchoolError("online_school_invalid_response")
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        self._ready()
                        if not isinstance(chunk, bytes):
                            raise OnlineSchoolError("online_school_invalid_response")
                        body.extend(chunk)
                        if len(body) > parsing.MAX_BODY:
                            raise OnlineSchoolError("online_school_invalid_response")
                    self._ready()
                    if not body:
                        raise OnlineSchoolError("online_school_invalid_response")
                    return body.decode("utf-8")
            raise OnlineSchoolError("online_school_invalid_response")
        except DomainError:
            raise
        except TimeoutError:
            raise OnlineSchoolError("online_school_timeout") from None
        except (aiohttp.ClientError, OSError):
            raise OnlineSchoolError("online_school_unavailable") from None
        except (ValueError, UnicodeError, RecursionError):
            raise OnlineSchoolError("online_school_invalid_response") from None

    async def _login(self):
        self._ready()
        if self._students is not None:
            return
        form = await self._request("GET", "/auth")
        token = parsing.csrf(form, self.base_url)
        await self._request(
            "POST",
            "/auth",
            data={
                "_token": token,
                "email": self._username,
                "password": self._password,
                "login": "",
            },
        )
        # Discovery is always based on the authenticated allowlisted header,
        # never a login success status, current-child hint or caller-supplied ID.
        header = await self._request("GET", "/daybook")
        self._students = parsing.students(header)

    async def discover(self):
        try:
            async with asyncio.timeout(60), self._lock:
                await self._login()
                self._ready()
                return deepcopy(self._students)
        except TimeoutError:
            raise OnlineSchoolError("online_school_timeout") from None

    async def _json(self, path, student_id):
        raw = await self._request("GET", path, student_id=student_id, json_request=True)
        if raw.lstrip().startswith("<"):
            self._students = None
            raise OnlineSchoolError("online_school_auth_failed")
        result = parsing.load_json(raw)
        parsing.identity(result, student_id)
        return result

    async def fetch(self, student_id, timezone, now):
        try:
            student_id = parsing.identifier(student_id)
            ZoneInfo(timezone)
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError
        except (DomainError, ValueError, TypeError, ZoneInfoNotFoundError):
            raise OnlineSchoolError("online_school_invalid_config") from None
        try:
            async with asyncio.timeout(90), self._lock:
                await self._login()
                if not any(row["id"] == student_id for row in self._students):
                    raise OnlineSchoolError("online_school_student_mismatch")
                default = await self._json("/daybook/get/" + student_id, student_id)
                parsing.diary(default, student_id, self.base_url)
                pages = [default]
                for week in parsing.adjacent(default):
                    page = await self._json(f"/daybook/get/{student_id}/{week}", student_id)
                    parsing.diary(page, student_id, self.base_url, expected_week=week)
                    pages.append(page)
                marks = await self._json("/studentparent/journal/get/" + student_id, student_id)
                result = parsing.snapshot(pages, marks, student_id, timezone, now, self.base_url)
                self._ready()
                return result
        except TimeoutError:
            raise OnlineSchoolError("online_school_timeout") from None

    async def close(self):
        self._closed = True
        self._students = None
        self._username = self._password = ""
        session, self._session = self._session, None
        if session is not None:
            await session.close()
