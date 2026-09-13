"""Small bounded Telegram API client. Never surface token-bearing URLs/errors."""

from __future__ import annotations

import json
import re

import aiohttp

from ..domain.validation import DomainError
from ..notifications import DeliveryError

READ_METHODS = {"getMe", "getWebhookInfo", "getUpdates", "getChat", "getChatMember", "getFile"}
WRITE_METHODS = {
    "sendMessage",
    "sendPhoto",
    "answerCallbackQuery",
    "editMessageReplyMarkup",
    "setMyCommands",
    "sendChatAction",
    "setMessageReaction",
}


class TelegramClient:
    def __init__(self, session: aiohttp.ClientSession, token: str):
        if not isinstance(token, str) or not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{30,100}", token):
            raise DomainError("telegram_invalid_token")
        self._session, self._token = session, token

    def __repr__(self):
        return "TelegramClient(<redacted>)"

    async def call(self, method: str, data: dict | None = None, *, _multipart=False):
        if method not in READ_METHODS | WRITE_METHODS:
            raise DomainError("unknown_action")
        data = data or {}
        timeout = aiohttp.ClientTimeout(total=40 if method == "getUpdates" else 15, connect=5)
        try:
            async with self._session.post(
                f"https://api.telegram.org/bot{self._token}/{method}",
                **({"data": data} if _multipart else {"json": data}),
                timeout=timeout,
                allow_redirects=False,
            ) as response:
                # Bound a malicious or broken proxy response before parsing it.
                if 300 <= response.status < 400:
                    raise DeliveryError("telegram_bad_response", uncertain=method in WRITE_METHODS)
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > 2_000_000:
                        raise DeliveryError(
                            "telegram_bad_response", uncertain=method in WRITE_METHODS
                        )
                    chunks.append(chunk)
                raw = b"".join(chunks)
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise DeliveryError(
                        "telegram_bad_response", uncertain=method in WRITE_METHODS
                    ) from None
                if not isinstance(body, dict):
                    raise DeliveryError("telegram_bad_response", uncertain=method in WRITE_METHODS)
                if response.status == 200 and body.get("ok") is True:
                    if "result" not in body:
                        raise DeliveryError(
                            "telegram_bad_response", uncertain=method in WRITE_METHODS
                        )
                    return body["result"]
                code = body.get("error_code", response.status)
                if type(code) is not int:
                    raise DeliveryError("telegram_bad_response", uncertain=method in WRITE_METHODS)
                if code == 401:
                    raise DeliveryError("telegram_invalid_token")
                if code == 409:
                    raise DeliveryError("telegram_polling_conflict")
                if code == 429:
                    retry = body.get("parameters", {}).get("retry_after", 30)
                    if not isinstance(retry, int):
                        retry = 30
                    raise DeliveryError("telegram_rate_limited", retryable=True, retry_after=retry)
                if code == 403:
                    raise DeliveryError("telegram_chat_blocked")
                raise DeliveryError(
                    "telegram_api_error",
                    retryable=method in READ_METHODS and code >= 500,
                    uncertain=method in WRITE_METHODS and code >= 500,
                )
        except aiohttp.ClientConnectorError:
            raise DeliveryError("telegram_unreachable", retryable=True) from None
        except (aiohttp.ClientError, TimeoutError):
            raise DeliveryError(
                "telegram_timeout",
                retryable=method in READ_METHODS,
                uncertain=method in WRITE_METHODS,
            ) from None

    async def send_photo(self, chat_id, content, mime, caption):
        """Upload verified private bytes, never ask Telegram to fetch a URL."""
        if (
            type(chat_id) is not int
            or chat_id <= 0
            or not isinstance(content, bytes)
            or not 0 < len(content) <= 6_000_000
            or mime not in {"image/png", "image/jpeg", "image/webp"}
            or not isinstance(caption, str)
            or len(caption) > 1024
        ):
            raise DomainError("invalid_field", "photo")
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("caption", caption)
        form.add_field("protect_content", "true")
        form.add_field(
            "photo",
            content,
            filename="generated."
            + {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime],
            content_type=mime,
        )
        result = await self.call("sendPhoto", form, _multipart=True)
        if (
            not isinstance(result, dict)
            or type(result.get("message_id")) is not int
            or result["message_id"] <= 0
        ):
            raise DeliveryError("telegram_bad_response", uncertain=True)
        return str(result["message_id"])

    async def inspect(self) -> dict:
        me = await self.call("getMe")
        hook = await self.call("getWebhookInfo")
        if hook.get("url"):
            raise DeliveryError("telegram_webhook_conflict")
        return {
            "id": me["id"],
            "username": me["username"],
            "can_read_all_group_messages": me.get("can_read_all_group_messages", False),
        }

    async def updates(self, offset: int | None = None, *, wait: int = 25) -> list[dict]:
        payload = {
            "timeout": min(max(wait, 0), 25),
            "limit": 50,
            "allowed_updates": ["message", "callback_query", "my_chat_member"],
        }
        if offset is not None:
            payload["offset"] = offset
        return await self.call("getUpdates", payload)

    async def download_file(self, file_id: str, *, max_bytes: int = 6_000_000) -> bytes:
        if not isinstance(file_id, str) or not file_id.strip() or len(file_id) > 512:
            raise DomainError("invalid_field", "file_id")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 6_000_000:
            raise DomainError("invalid_field", "max_bytes")
        file_info = await self.call("getFile", {"file_id": file_id.strip()})
        if not isinstance(file_info, dict):
            raise DeliveryError("telegram_bad_response")
        file_path = file_info.get("file_path")
        if (
            not isinstance(file_path, str)
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", file_path)
            or file_path.startswith("/")
            or any(part in {".", "..", ""} for part in file_path.split("/"))
            or len(file_path) > 512
        ):
            raise DeliveryError("telegram_bad_response")
        file_size = file_info.get("file_size", 0)
        if type(file_size) is not int or file_size < 0:
            raise DeliveryError("telegram_bad_response")
        if file_size > max_bytes:
            raise DomainError("file_too_large")
        timeout = aiohttp.ClientTimeout(total=30, connect=5)
        try:
            async with self._session.get(
                f"https://api.telegram.org/file/bot{self._token}/{file_path}",
                timeout=timeout,
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise DeliveryError("telegram_bad_response")
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > max_bytes:
                        raise DomainError("file_too_large")
                    chunks.append(chunk)
                if not size:
                    raise DeliveryError("telegram_bad_response")
                return b"".join(chunks)
        except aiohttp.ClientConnectorError:
            raise DeliveryError("telegram_unreachable", retryable=True) from None
        except (aiohttp.ClientError, TimeoutError):
            raise DeliveryError("telegram_timeout", retryable=True) from None
