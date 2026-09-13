"""Synthetic aiohttp wire contracts; never contact a real school or use live accounts."""

import asyncio
import json
from datetime import datetime

import aiohttp
import pytest
from test_online_school_parsing import BASE, NOW, diary, header, journal

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.online_school import RespublikaClient, parsing
from custom_components.family_assistant.online_school.provider import ERROR_CODES

FORM = '<form method="POST" action="/auth"><input name="_token" value="synthetic-csrf"></form>'


class Response:
    def __init__(self, value="", *, status=200, headers=None, chunks=None, content_length=None):
        self.body = (
            json.dumps(value).encode() if isinstance(value, (dict, list)) else value.encode()
        )
        self.status = status
        self.headers = headers or {}
        self.content = self
        self.chunks = chunks
        self.content_length = content_length
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.exited = True

    async def iter_chunked(self, limit):
        if self.chunks is not None:
            for chunk in self.chunks:
                yield chunk
            return
        for start in range(0, len(self.body), limit):
            yield self.body[start : start + limit]


class Session:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.closed = False
        self.settings = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        assert not self.closed
        assert kwargs["allow_redirects"] is False
        assert isinstance(kwargs["timeout"], aiohttp.ClientTimeout)
        assert kwargs["timeout"].total == 20
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self):
        self.closed = True


def client(script, *, base_url=BASE):
    session = Session(script)

    def factory(**kwargs):
        session.settings = kwargs
        return session

    return RespublikaClient(
        base_url, "synthetic-parent@example.invalid", "synthetic-secret", session_factory=factory
    ), session


def login(*, children=None):
    return [Response(FORM), Response("<html>Logged in</html>"), Response(header(children))]


def pages(*, student=101):
    return [
        Response(diary(student=student)),
        Response(diary(2, student=student)),
        Response(diary(4, student=student)),
        Response(journal(student=student)),
    ]


async def test_discover_fetch_pins_every_route_and_never_exports_private_header_fields():
    provider, session = client(login() + pages())
    try:
        assert await provider.discover() == [{"id": "101", "name": "Synthetic Learner"}]
        result = await provider.fetch("101", "Europe/Kyiv", NOW)
        assert result["student_id"] == "101" and len(result["lessons"]) == 3
        assert result["coverage_start"] == "2026-09-07" and result["coverage_end"] == "2026-09-27"
        assert [url for _method, url, _kwargs in session.calls] == [
            BASE + "/auth",
            BASE + "/auth",
            BASE + "/daybook",
            BASE + "/daybook/get/101",
            BASE + "/daybook/get/101/2",
            BASE + "/daybook/get/101/4",
            BASE + "/studentparent/journal/get/101",
        ]
        post = session.calls[1]
        assert post[0] == "POST"
        assert post[2]["data"] == {
            "_token": "synthetic-csrf",
            "email": "synthetic-parent@example.invalid",
            "password": "synthetic-secret",
            "login": "",
        }
        assert all(method == "GET" for method, _url, _kwargs in session.calls[2:])
        assert "SYNTHETIC-NOT-FOR-EXPORT" not in json.dumps(result)
        assert "synthetic-secret" not in json.dumps(result)
        assert session.settings["trust_env"] is False
    finally:
        await provider.close()
    assert session.closed and provider._password == provider._username == ""


async def test_sessions_isolate_cookies_and_discovery_results_cannot_mutate_internal_identity():
    first, first_session = client(login())
    second, second_session = client(login(children={"202": "Second learner"}))
    try:
        discovered = await first.discover()
        discovered[0]["id"] = "202"
        assert await first.discover() == [{"id": "101", "name": "Synthetic Learner"}]
        assert await second.discover() == [{"id": "202", "name": "Second learner"}]
        assert first_session.settings["cookie_jar"] is not second_session.settings["cookie_jar"]
        with pytest.raises(DomainError, match="online_school_student_mismatch"):
            await first.fetch("202", "UTC", NOW)
        assert len(first_session.calls) == 3
    finally:
        await first.close()
        await second.close()


async def test_same_origin_login_redirect_changes_post_to_get_without_credentials():
    provider, session = client(
        [
            Response(FORM),
            Response(status=302, headers={"Location": "/daybook"}),
            Response(header()),
            Response(header()),
        ]
    )
    try:
        assert len(await provider.discover()) == 1
        assert session.calls[2][0] == "GET" and session.calls[2][2]["data"] is None
    finally:
        await provider.close()


async def test_login_redirect_to_bare_configured_origin_uses_root_without_forwarding_credentials():
    provider, session = client(
        [
            Response(FORM),
            Response(status=302, headers={"Location": BASE}),
            Response(header()),
            Response(header()),
        ]
    )
    try:
        assert len(await provider.discover()) == 1
        assert session.calls[2][0:2] == ("GET", BASE + "/")
        assert session.calls[2][2]["data"] is None
    finally:
        await provider.close()


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example.invalid/daybook",
        "http://school.example.invalid/daybook",
        "//evil.example.invalid/daybook",
        "https://user:pass@school.example.invalid/daybook",
        "/admin/delete",
        "/daybook?token=secret",
        "/daybook#secret",
    ],
)
async def test_unsafe_login_redirect_never_receives_post_or_cookies(target):
    provider, session = client([Response(FORM), Response(status=302, headers={"Location": target})])
    try:
        with pytest.raises(DomainError, match="online_school_invalid_response"):
            await provider.discover()
        assert len(session.calls) == 2
        assert all(url.startswith(BASE + "/") for _method, url, _kwargs in session.calls)
    finally:
        await provider.close()


@pytest.mark.parametrize("status", [307, 308])
async def test_preserved_post_redirect_does_not_replay_login_credentials(status):
    provider, session = client(
        [Response(FORM), Response(status=status, headers={"Location": "/daybook"})]
    )
    try:
        with pytest.raises(DomainError, match="online_school_auth_failed"):
            await provider.discover()
        assert len(session.calls) == 2
    finally:
        await provider.close()


@pytest.mark.parametrize("status", [401, 403, 419])
async def test_expired_auth_invalidates_discovery_without_infinite_retry(status):
    provider, session = client(login() + [Response(status=status)] + login())
    try:
        await provider.discover()
        with pytest.raises(DomainError, match="online_school_auth_failed"):
            await provider.fetch("101", "UTC", NOW)
        assert len(session.calls) == 4 and provider._students is None
        assert len(await provider.discover()) == 1
        assert len(session.calls) == 7
    finally:
        await provider.close()


async def test_json_redirect_to_login_is_auth_failure_and_does_not_follow():
    provider, session = client(login() + [Response(status=302, headers={"Location": "/auth"})])
    try:
        with pytest.raises(DomainError, match="online_school_auth_failed"):
            await provider.fetch("101", "UTC", NOW)
        assert len(session.calls) == 4
    finally:
        await provider.close()


@pytest.mark.parametrize("where", ["default", "adjacent", "journal", "redirect"])
async def test_student_mismatch_never_returns_a_partial_snapshot(where):
    responses = pages()
    if where == "default":
        responses[0] = Response(diary(student=202))
    elif where == "adjacent":
        responses[1] = Response(diary(2, student=202))
    elif where == "journal":
        responses[3] = Response(journal(student=202))
    else:
        responses[0] = Response(status=302, headers={"Location": "/daybook/get/202"})
    provider, session = client(login() + responses)
    try:
        with pytest.raises(DomainError) as error:
            await provider.fetch("101", "UTC", NOW)
        assert error.value.code in {
            "online_school_student_mismatch",
            "online_school_invalid_response",
        }
        assert not any("/202" in url for _method, url, _kwargs in session.calls)
    finally:
        await provider.close()


@pytest.mark.parametrize(
    "header_value,delay", [("120", 120), ("99999999", 3600), ("not-a-number", 60)]
)
async def test_rate_limit_is_bounded_and_prevents_immediate_retry(header_value, delay):
    provider, session = client([Response(status=429, headers={"Retry-After": header_value})])
    try:
        with pytest.raises(DomainError, match="online_school_rate_limited") as error:
            await provider.discover()
        assert error.value.retry_after == delay
        with pytest.raises(DomainError, match="online_school_rate_limited"):
            await provider.discover()
        assert len(session.calls) == 1
    finally:
        await provider.close()


@pytest.mark.parametrize(
    "response",
    [
        Response(""),
        Response("{}"),
        Response("<html>Login</html>"),
        Response('{"student": NaN}'),
        Response("[]"),
    ],
)
async def test_blank_html_or_malformed_data_is_never_empty_school_success(response):
    provider, _session = client(login() + [response])
    try:
        with pytest.raises(DomainError) as error:
            await provider.fetch("101", "UTC", NOW)
        assert error.value.code in {"online_school_auth_failed", "online_school_invalid_response"}
    finally:
        await provider.close()


@pytest.mark.parametrize("kind", ["declared", "streamed"])
async def test_response_size_is_bounded_even_without_content_length(kind):
    response = (
        Response(content_length=parsing.MAX_BODY + 1)
        if kind == "declared"
        else Response(chunks=[b"x" * 65536] * 33)
    )
    provider, _session = client([response])
    try:
        with pytest.raises(DomainError, match="online_school_invalid_response"):
            await provider.discover()
        assert response.exited
    finally:
        await provider.close()


@pytest.mark.parametrize(
    "exception,code",
    [
        (TimeoutError("synthetic-secret"), "online_school_timeout"),
        (aiohttp.ClientConnectionError("synthetic-secret"), "online_school_unavailable"),
    ],
)
async def test_transport_errors_do_not_expose_secret_exception_messages(exception, code, caplog):
    provider, _session = client([exception])
    try:
        with pytest.raises(DomainError, match=code) as error:
            await provider.discover()
        assert str(error.value) == code and error.value.code in ERROR_CODES
        assert "synthetic-secret" not in repr(error.value) + caplog.text
    finally:
        await provider.close()


async def test_cancellation_propagates_and_close_retires_pending_client():
    started = asyncio.Event()

    class BlockingResponse(Response):
        async def iter_chunked(self, _limit):
            started.set()
            await asyncio.Event().wait()
            yield b"unreachable"

    response = BlockingResponse()
    provider, session = client([response])
    task = asyncio.create_task(provider.discover())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert response.exited
    await provider.close()
    assert session.closed
    with pytest.raises(DomainError, match="online_school_unavailable"):
        await provider.discover()


@pytest.mark.parametrize(
    "base",
    [
        "http://school.example.invalid",
        "https://school.example.invalid/path",
        "https://school.example.invalid?token=x",
        "https://user:pass@school.example.invalid",
        "https://127.0.0.1",
        "https://localhost",
    ],
)
def test_invalid_base_url_never_creates_a_session(base):
    with pytest.raises(DomainError, match="online_school_invalid_config"):
        client([], base_url=base)


@pytest.mark.parametrize(
    "student,zone,now",
    [
        ("../202", "UTC", NOW),
        (True, "UTC", NOW),
        ("101", "invalid/zone", NOW),
        ("101", "UTC", datetime(2026, 9, 14)),
    ],
)
async def test_invalid_fetch_scope_never_authenticates(student, zone, now):
    provider, session = client([])
    try:
        with pytest.raises(DomainError, match="online_school_invalid_config"):
            await provider.fetch(student, zone, now)
        assert not session.calls
    finally:
        await provider.close()
