"""Authenticated HTTP boundary for private Family Assistant image bytes."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .domain import media
from .domain.validation import DomainError

MEDIA_URL = "/api/family_assistant/media/{entry_id}/{media_id}"
MEDIA_VIEW_NAME = "api:family_assistant:media"
REVISION_HEADER = "X-Family-Media-Revision"
MAX_CHUNK_BYTES = 256 * 1024

_SEGMENT = re.compile(r"[A-Za-z0-9_-]{1,128}")
_REVISION = re.compile(r"[1-9][0-9]*")
_MIME_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Cross-Origin-Resource-Policy": "same-origin",
}
_ERROR_STATUS = {
    "media_invalid": HTTPStatus.BAD_REQUEST,
    "media_too_large": HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    "forbidden": HTTPStatus.FORBIDDEN,
    "conflict": HTTPStatus.CONFLICT,
    "media_unavailable": HTTPStatus.SERVICE_UNAVAILABLE,
}


def _error(code: str) -> web.Response:
    """Return one fixed code without provider, state or exception details."""
    status = _ERROR_STATUS[code]
    return web.json_response({"code": code}, status=status, headers=_PRIVATE_HEADERS)


def _domain_code(error: DomainError) -> str:
    if error.code in _ERROR_STATUS:
        return error.code
    # Unknown records, membership failures and module state are all private
    # authorization details at this byte endpoint.
    return "forbidden"


def _single_header(request: web.Request, name: str) -> str:
    try:
        values = request.headers.getall(name, [])
    except (AttributeError, KeyError, TypeError):
        raise DomainError("media_invalid") from None
    if len(values) != 1 or not isinstance(values[0], str):
        raise DomainError("media_invalid")
    return values[0]


def _revision(request: web.Request) -> int:
    value = _single_header(request, REVISION_HEADER)
    if not _REVISION.fullmatch(value) or len(value) > 16:
        raise DomainError("media_invalid")
    revision = int(value)
    if revision > 2**53 - 1:
        raise DomainError("media_invalid")
    return revision


def _segments(entry_id: str, media_id: str) -> None:
    if (
        not isinstance(entry_id, str)
        or not isinstance(media_id, str)
        or not _SEGMENT.fullmatch(entry_id)
        or not _SEGMENT.fullmatch(media_id)
    ):
        raise DomainError("media_invalid")


def _reject_transfer_features(request: web.Request) -> None:
    for name in ("Range", "Content-Range", "Content-Encoding"):
        try:
            if request.headers.getall(name, []):
                raise DomainError("media_invalid")
        except AttributeError:
            raise DomainError("media_invalid") from None


def _content_type(request: web.Request) -> str:
    value = _single_header(request, "Content-Type")
    if value not in media.MIME_TYPES:
        raise DomainError("media_invalid")
    return value


def _content_length(request: web.Request) -> int | None:
    try:
        values = request.headers.getall("Content-Length", [])
    except (AttributeError, KeyError, TypeError):
        raise DomainError("media_invalid") from None
    if not values:
        return None
    if len(values) != 1 or not isinstance(values[0], str) or not values[0].isdigit():
        raise DomainError("media_invalid")
    length = int(values[0])
    if length == 0:
        raise DomainError("media_invalid")
    if length > media.MAX_FILE_BYTES:
        raise DomainError("media_too_large")
    return length


def _get_runtime(hass: Any, entry_id: str) -> Any:
    # Local import avoids a runtime/media_http cycle during integration setup.
    from .runtime import get_runtime

    return get_runtime(hass, entry_id)


async def _scope(
    request: web.Request, entry_id: str, media_id: str
) -> tuple[Any, Any, str, Callable[[], Awaitable[None]]]:
    _segments(entry_id, media_id)
    hass = request.app[KEY_HASS]
    try:
        request_user = request["hass_user"]
        user_id = request_user.id
        if not isinstance(user_id, str) or not user_id:
            raise DomainError("forbidden")
        runtime = _get_runtime(hass, entry_id)
        storage = runtime.media
        if storage is None:
            raise DomainError("forbidden")
    except DomainError:
        raise
    except (AttributeError, KeyError, TypeError):
        raise DomainError("forbidden") from None

    async def guard() -> None:
        try:
            current_user = await hass.auth.async_get_user(user_id)
            current_runtime = _get_runtime(hass, entry_id)
            if (
                current_user is None
                or current_user.id != user_id
                or current_user.is_active is not True
                or current_runtime is not runtime
                or current_runtime.media is not storage
            ):
                raise DomainError("forbidden")
        except DomainError:
            raise
        except (AttributeError, KeyError, TypeError):
            raise DomainError("forbidden") from None

    await guard()
    return hass, storage, user_id, guard


async def _chunks(request: web.Request) -> AsyncIterator[bytes]:
    total = 0
    try:
        async for chunk in request.content.iter_chunked(MAX_CHUNK_BYTES):
            if not isinstance(chunk, bytes) or len(chunk) > MAX_CHUNK_BYTES:
                raise DomainError("media_invalid")
            total += len(chunk)
            if total > media.MAX_FILE_BYTES:
                raise DomainError("media_too_large")
            if chunk:
                yield chunk
    except DomainError:
        raise
    except (OSError, TimeoutError, ValueError, TypeError):
        raise DomainError("media_unavailable") from None


def _valid_receipt(receipt: Any, media_id: str, revision: int) -> bool:
    return (
        isinstance(receipt, dict)
        and set(receipt) == {"id", "revision", "status"}
        and receipt.get("id") == media_id
        and receipt.get("revision") == revision + 1
        and receipt.get("status") == "available"
    )


def _valid_download(metadata: Any, content: Any, media_id: str, revision: int) -> bool:
    return (
        isinstance(metadata, dict)
        and set(metadata) == set(media.PUBLIC_FIELDS)
        and metadata.get("id") == media_id
        and metadata.get("revision") == revision
        and isinstance(metadata.get("purpose"), str)
        and metadata["purpose"] in media.PURPOSES
        and metadata.get("status") in {"available", "attached"}
        and metadata.get("mime_type") in media.MIME_TYPES
        and type(metadata.get("size_bytes")) is int
        and 1 <= metadata["size_bytes"] <= media.MAX_FILE_BYTES
        and isinstance(content, bytes)
        and len(content) == metadata["size_bytes"]
    )


class FamilyAssistantMediaView(HomeAssistantView):
    """Serve one authorized, entry-private image without stable public URLs."""

    url = MEDIA_URL
    name = MEDIA_VIEW_NAME
    requires_auth = True

    async def put(self, request: web.Request, entry_id: str, media_id: str) -> web.Response:
        try:
            _reject_transfer_features(request)
            revision = _revision(request)
            _content_type(request)  # A hint only; MediaStorage verifies bytes.
            _content_length(request)
            _, storage, user_id, guard = await _scope(request, entry_id, media_id)
            receipt = await storage.put(user_id, media_id, revision, _chunks(request), guard=guard)
            if not _valid_receipt(receipt, media_id, revision):
                return _error("media_unavailable")
            return web.json_response(receipt, headers=_PRIVATE_HEADERS)
        except DomainError as error:
            return _error(_domain_code(error))
        except (OSError, TimeoutError):
            return _error("media_unavailable")
        except Exception:
            return _error("media_unavailable")

    async def get(self, request: web.Request, entry_id: str, media_id: str) -> web.Response:
        try:
            _reject_transfer_features(request)
            revision = _revision(request)
            _, storage, user_id, guard = await _scope(request, entry_id, media_id)
            metadata, content = await storage.get(user_id, media_id, revision, guard=guard)
            if not _valid_download(metadata, content, media_id, revision):
                return _error("media_unavailable")
            mime_type = metadata["mime_type"]
            headers = {
                **_PRIVATE_HEADERS,
                "Content-Disposition": (
                    f'attachment; filename="family-assistant-image.{_MIME_EXTENSION[mime_type]}"'
                ),
            }
            return web.Response(body=content, content_type=mime_type, headers=headers)
        except DomainError as error:
            return _error(_domain_code(error))
        except (OSError, TimeoutError):
            return _error("media_unavailable")
        except Exception:
            return _error("media_unavailable")


def async_register_media(hass: Any) -> None:
    """Register the single authenticated media resource view."""
    hass.http.register_view(FamilyAssistantMediaView())
