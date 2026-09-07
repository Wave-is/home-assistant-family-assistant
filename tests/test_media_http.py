"""HTTP boundary tests for authenticated private media bytes."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from multidict import CIMultiDict

from custom_components.family_assistant.domain.validation import DomainError

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components" / "family_assistant" / "media_http.py"
IMAGE = b"\x89PNG\r\n\x1a\nsynthetic-image"


class _HomeAssistantView:
    pass


@pytest.fixture
def media_http(monkeypatch):
    homeassistant = ModuleType("homeassistant")
    components = ModuleType("homeassistant.components")
    http = ModuleType("homeassistant.components.http")
    http.KEY_HASS = "hass"
    http.HomeAssistantView = _HomeAssistantView
    components.http = http
    homeassistant.components = components
    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.http": http,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "custom_components.family_assistant._media_http_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _User:
    def __init__(self, identifier="ha-child", *, active=True, admin=False):
        self.id = identifier
        self.is_active = active
        self.is_admin = admin


class _Auth:
    def __init__(self, user):
        self.user = user
        self.calls = []

    async def async_get_user(self, identifier):
        self.calls.append(identifier)
        if self.user is None or self.user.id != identifier:
            return None
        return self.user


class _HTTP:
    def __init__(self):
        self.views = []

    def register_view(self, view):
        self.views.append(view)


class _Content:
    def __init__(self, parts=()):
        self.parts = list(parts)
        self.limit = None

    async def iter_chunked(self, limit):
        self.limit = limit
        for part in self.parts:
            for offset in range(0, len(part), limit):
                yield part[offset : offset + limit]


class _Request(dict):
    def __init__(self, hass, user, *, headers=(), parts=()):
        super().__init__(hass_user=user)
        self.app = {"hass": hass}
        self.headers = CIMultiDict(headers)
        self.content = _Content(parts)


class _Storage:
    def __init__(self):
        self.put_calls = []
        self.get_calls = []
        self.put_result = {"id": "M_1", "revision": 6, "status": "available"}
        self.get_result = (
            {
                "id": "M_1",
                "revision": 5,
                "purpose": "task_report",
                "mime_type": "image/png",
                "size_bytes": len(IMAGE),
                "status": "available",
            },
            IMAGE,
        )
        self.error = None

    async def put(self, user_id, media_id, revision, chunks, *, guard):
        await guard()
        body = b"".join([part async for part in chunks])
        await guard()
        self.put_calls.append((user_id, media_id, revision, body))
        if self.error:
            raise self.error
        return self.put_result

    async def get(self, user_id, media_id, revision, *, guard):
        await guard()
        self.get_calls.append((user_id, media_id, revision))
        if self.error:
            raise self.error
        await guard()
        return self.get_result


def _setup(module, monkeypatch, *, user=None, storage=None):
    user = user or _User()
    storage = storage or _Storage()
    hass = SimpleNamespace(auth=_Auth(user), http=_HTTP())
    runtime = SimpleNamespace(media=storage)
    current = {"runtime": runtime}
    monkeypatch.setattr(module, "_get_runtime", lambda _hass, _entry: current["runtime"])
    return hass, user, storage, runtime, current


def _headers(*extra, revision="5", mime="image/png", length=None):
    values = [("X-Family-Media-Revision", revision)]
    if mime is not None:
        values.append(("Content-Type", mime))
    if length is not None:
        values.append(("Content-Length", str(length)))
    return [*values, *extra]


def _data(response):
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_registers_one_authenticated_canonical_view(media_http):
    hass = SimpleNamespace(http=_HTTP())
    assert media_http.async_register_media(hass) is None
    assert len(hass.http.views) == 1
    view = hass.http.views[0]
    assert isinstance(view, _HomeAssistantView)
    assert view.url == "/api/family_assistant/media/{entry_id}/{media_id}"
    assert view.name == "api:family_assistant:media"
    assert view.requires_auth is True


@pytest.mark.asyncio
async def test_put_streams_bounded_chunks_and_returns_only_exact_receipt(media_http, monkeypatch):
    hass, user, storage, _, _ = _setup(media_http, monkeypatch)
    request = _Request(
        hass,
        user,
        headers=_headers(length=len(IMAGE)),
        parts=[IMAGE[:4], IMAGE[4:]],
    )
    response = await media_http.FamilyAssistantMediaView().put(request, "entry_1", "M_1")
    assert response.status == 200
    assert _data(response) == {"id": "M_1", "revision": 6, "status": "available"}
    assert storage.put_calls == [("ha-child", "M_1", 5, IMAGE)]
    assert request.content.limit == 256 * 1024
    assert hass.auth.calls == ["ha-child", "ha-child", "ha-child"]
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"


@pytest.mark.asyncio
async def test_get_requires_revision_and_returns_fixed_private_attachment(media_http, monkeypatch):
    hass, user, storage, _, _ = _setup(media_http, monkeypatch)
    request = _Request(hass, user, headers=_headers(mime=None))
    response = await media_http.FamilyAssistantMediaView().get(request, "entry_1", "M_1")
    assert response.status == 200
    assert response.body == IMAGE
    assert storage.get_calls == [("ha-child", "M_1", 5)]
    assert response.headers["Content-Type"] == "image/png"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="family-assistant-image.png"'
    )
    assert "M_1" not in response.headers["Content-Disposition"]
    assert "Accept-Ranges" not in response.headers
    assert "Content-Encoding" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ([], "media_invalid"),
        ([("X-Family-Media-Revision", "0")], "media_invalid"),
        ([("X-Family-Media-Revision", "01")], "media_invalid"),
        ([("X-Family-Media-Revision", "+5")], "media_invalid"),
        ([("X-Family-Media-Revision", "9007199254740992")], "media_invalid"),
        (
            [
                ("X-Family-Media-Revision", "5"),
                ("X-Family-Media-Revision", "5"),
            ],
            "media_invalid",
        ),
    ],
)
async def test_get_revision_header_is_one_exact_json_safe_decimal(
    media_http, monkeypatch, headers, expected
):
    hass, user, storage, _, _ = _setup(media_http, monkeypatch)
    response = await media_http.FamilyAssistantMediaView().get(
        _Request(hass, user, headers=headers), "entry_1", "M_1"
    )
    assert response.status == 400
    assert _data(response) == {"code": expected}
    assert storage.get_calls == []


@pytest.mark.asyncio
async def test_routes_mime_size_and_transfer_features_fail_before_storage(media_http, monkeypatch):
    hass, user, storage, _, _ = _setup(media_http, monkeypatch)
    cases = [
        ("../entry", "M_1", _headers(), "media_invalid", 400),
        ("entry_1", "M%2F1", _headers(), "media_invalid", 400),
        ("entry_1", "M_1", _headers(mime="image/svg+xml"), "media_invalid", 400),
        (
            "entry_1",
            "M_1",
            _headers(length=10 * 1024 * 1024 + 1),
            "media_too_large",
            413,
        ),
        (
            "entry_1",
            "M_1",
            _headers(("Content-Encoding", "gzip")),
            "media_invalid",
            400,
        ),
        (
            "entry_1",
            "M_1",
            _headers(("Content-Range", "bytes 0-1/2")),
            "media_invalid",
            400,
        ),
    ]
    view = media_http.FamilyAssistantMediaView()
    for entry_id, media_id, headers, code, status in cases:
        response = await view.put(
            _Request(hass, user, headers=headers, parts=[IMAGE]), entry_id, media_id
        )
        assert response.status == status
        assert _data(response) == {"code": code}
    range_response = await view.get(
        _Request(
            hass,
            user,
            headers=_headers(("Range", "bytes=0-1"), mime=None),
        ),
        "entry_1",
        "M_1",
    )
    assert range_response.status == 400
    assert _data(range_response) == {"code": "media_invalid"}
    assert storage.put_calls == []
    assert storage.get_calls == []


@pytest.mark.asyncio
async def test_streamed_body_limit_is_enforced_without_publishing_receipt(media_http, monkeypatch):
    hass, user, storage, _, _ = _setup(media_http, monkeypatch)
    request = _Request(
        hass,
        user,
        headers=_headers(),
        parts=[b"x" * (10 * 1024 * 1024), b"y"],
    )
    response = await media_http.FamilyAssistantMediaView().put(request, "entry_1", "M_1")
    assert response.status == 413
    assert _data(response) == {"code": "media_too_large"}
    assert storage.put_calls == []


@pytest.mark.asyncio
async def test_guard_rechecks_active_user_and_exact_runtime_during_io(media_http, monkeypatch):
    class DriftStorage(_Storage):
        async def get(self, user_id, media_id, revision, *, guard):
            await guard()
            current["runtime"] = SimpleNamespace(media=self)
            await guard()
            raise AssertionError("unreachable")

    storage = DriftStorage()
    hass, user, _, _, current = _setup(media_http, monkeypatch, storage=storage)
    response = await media_http.FamilyAssistantMediaView().get(
        _Request(hass, user, headers=_headers(mime=None)), "entry_1", "M_1"
    )
    assert response.status == 403
    assert _data(response) == {"code": "forbidden"}

    hass2, user2, storage2, _, _ = _setup(media_http, monkeypatch)

    class RevokeStorage(_Storage):
        async def put(self, user_id, media_id, revision, chunks, *, guard):
            await guard()
            user2.is_active = False
            await guard()
            raise AssertionError("unreachable")

    revoked = RevokeStorage()
    runtime2 = SimpleNamespace(media=revoked)
    monkeypatch.setattr(media_http, "_get_runtime", lambda _hass, _entry: runtime2)
    response = await media_http.FamilyAssistantMediaView().put(
        _Request(hass2, user2, headers=_headers(), parts=[IMAGE]),
        "entry_1",
        "M_1",
    )
    assert response.status == 403
    assert _data(response) == {"code": "forbidden"}
    assert storage2.put_calls == []


@pytest.mark.asyncio
async def test_ha_admin_bit_never_bypasses_storage_family_authority(media_http, monkeypatch):
    storage = _Storage()
    storage.error = DomainError("forbidden")
    hass, admin, _, _, _ = _setup(
        media_http, monkeypatch, user=_User("unlinked-admin", admin=True), storage=storage
    )
    response = await media_http.FamilyAssistantMediaView().get(
        _Request(hass, admin, headers=_headers(mime=None)), "entry_1", "M_1"
    )
    assert response.status == 403
    assert _data(response) == {"code": "forbidden"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (DomainError("conflict"), 409, "conflict"),
        (DomainError("media_invalid"), 400, "media_invalid"),
        (DomainError("media_too_large"), 413, "media_too_large"),
        (DomainError("not_found"), 403, "forbidden"),
        (DomainError("module_disabled"), 403, "forbidden"),
        (OSError("private path"), 503, "media_unavailable"),
        (RuntimeError("private internal detail"), 503, "media_unavailable"),
    ],
)
async def test_storage_errors_are_flattened_to_fixed_code_only_responses(
    media_http, monkeypatch, error, status, code
):
    storage = _Storage()
    storage.error = error
    hass, user, _, _, _ = _setup(media_http, monkeypatch, storage=storage)
    response = await media_http.FamilyAssistantMediaView().get(
        _Request(hass, user, headers=_headers(mime=None)), "entry_1", "M_1"
    )
    assert response.status == status
    assert _data(response) == {"code": code}
    assert response.headers["Cache-Control"] == "private, no-store"
    assert b"private" not in response.body


@pytest.mark.asyncio
async def test_untrusted_storage_results_never_become_receipts_or_image_bytes(
    media_http, monkeypatch
):
    storage = _Storage()
    hass, user, _, _, _ = _setup(media_http, monkeypatch, storage=storage)
    view = media_http.FamilyAssistantMediaView()
    for result in (
        {"id": "M_1", "revision": 5, "status": "available"},
        {"id": "OTHER", "revision": 6, "status": "available"},
        {"id": "M_1", "revision": 6, "status": "available", "extra": True},
    ):
        storage.put_result = result
        response = await view.put(
            _Request(hass, user, headers=_headers(), parts=[IMAGE]),
            "entry_1",
            "M_1",
        )
        assert response.status == 503
        assert _data(response) == {"code": "media_unavailable"}

    storage.get_result = (
        {
            "id": "M_1",
            "revision": 5,
            "mime_type": "text/html",
            "size_bytes": len(IMAGE),
            "status": "available",
        },
        b"PRIVATE HTML OR IMAGE BYTES",
    )
    response = await view.get(_Request(hass, user, headers=_headers(mime=None)), "entry_1", "M_1")
    assert response.status == 503
    assert _data(response) == {"code": "media_unavailable"}
    assert IMAGE not in response.body
