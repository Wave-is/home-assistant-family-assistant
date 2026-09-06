"""Ollama JSON plans with an independent, explicitly configured fallback."""

import asyncio
import json
import time

from ..domain.validation import DomainError, text
from .http import endpoint, request_json


class Ollama:
    def __init__(self, session, config):
        self.session = session
        self.url = endpoint(config["url"], allow_http=config.get("allow_http", False))
        self.model = text(config.get("model", ""), "model", 128)
        self.timeout = config.get("timeout", 15)
        if type(self.timeout) is not int or not 5 <= self.timeout <= 45:
            raise DomainError("invalid_field", "timeout")
        self.headers = (
            {"Authorization": f"Bearer {config['api_key']}"} if config.get("api_key") else {}
        )

    async def models(self):
        data = await request_json(self.session, "GET", self.url + "/api/tags", headers=self.headers)
        models = data.get("models")
        if not isinstance(models, list):
            raise DomainError("provider_bad_response")
        return sorted(
            {
                m["name"]
                for m in models[:128]
                if isinstance(m, dict) and isinstance(m.get("name"), str) and len(m["name"]) <= 128
            }
        )

    async def inspect(self):
        if self.model not in await self.models():
            raise DomainError("provider_model_missing")

    async def generate(self, messages, schema):
        data = await request_json(
            self.session,
            "POST",
            self.url + "/api/chat",
            timeout=self.timeout,
            headers=self.headers,
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "think": False,
                "options": {"temperature": 0, "num_predict": 1500, "num_ctx": 8192},
                "keep_alive": "5m",
            },
        )
        content = data.get("message", {})
        content = content.get("content") if isinstance(content, dict) else None
        if not isinstance(content, str) or not content or len(content) > 20000:
            raise DomainError("provider_bad_response")
        try:
            result = json.loads(content)
        except (ValueError, RecursionError):
            raise DomainError("provider_bad_response") from None
        if not isinstance(result, dict):
            raise DomainError("provider_bad_response")
        return result


class Cascade:
    def __init__(self, providers, health, *, clock=time.monotonic):
        self.providers, self.health, self.clock = providers, health, clock
        self.cooldown = {}
        self.lock = asyncio.Lock()

    async def generate(self, messages, schema, validate):
        # One inference per household; the Telegram polling task never waits here.
        async with self.lock:
            last = "provider_unreachable"
            for index, provider in enumerate(self.providers):
                if self.clock() < self.cooldown.get(index, 0):
                    continue
                try:
                    result = validate(await provider.generate(messages, schema))
                except DomainError as err:
                    last = err.code
                    self.cooldown[index] = self.clock() + 30
                    continue
                self.health["conversation"] = "fallback" if index else "connected"
                self.cooldown.pop(index, None)
                return result
            self.health["conversation"] = last
            raise DomainError(last)
