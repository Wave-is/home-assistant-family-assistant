"""Small bounded Telegram API client. Never surface token-bearing URLs/errors."""

from __future__ import annotations

import json
import re

import aiohttp

from ..domain.validation import DomainError
from ..notifications import DeliveryError

READ_METHODS = {"getMe", "getWebhookInfo", "getUpdates", "getChat", "getChatMember", "getFile"}
WRITE_METHODS = {"sendMessage", "answerCallbackQuery", "editMessageReplyMarkup", "setMyCommands"}


class TelegramClient:
    def __init__(self, session: aiohttp.ClientSession, token: str):
        if not isinstance(token, str) or not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{30,100}", token):
            raise DomainError("telegram_invalid_token")
        self._session, self._token = session, token

    def __repr__(self):
        return "TelegramClient(<redacted>)"

    async def call(self, method: str, data: dict | None = None):
        if method not in READ_METHODS | WRITE_METHODS:
            raise DomainError("unknown_action")
        data = data or {}
        timeout = aiohttp.ClientTimeout(total=40 if method == "getUpdates" else 15, connect=5)
        try:
            async with self._session.post(
                f"https://api.telegram.org/bot{self._token}/{method}",
                json=data,
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
