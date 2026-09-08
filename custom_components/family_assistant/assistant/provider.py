"""Ollama JSON plans with an independent, explicitly configured fallback."""

import asyncio
import inspect
import json
import time
from dataclasses import dataclass

from ..domain.validation import DomainError, text
from ..domain.validation import revision as strict_revision
from .http import endpoint, request_json


class ActorProviderUnavailable(DomainError):
    """This caller cannot use a provider; do not disable it for other callers."""


@dataclass(frozen=True)
class ActorRequest:
    """Server-supplied family identity, never derived from model/prompt content."""

    actor: str
    revision: int
    language: str

    def __post_init__(self):
        text(self.actor, "actor", 180)
        strict_revision(self.revision)
        if not isinstance(self.language, str) or self.language not in {"en", "ru", "uk"}:
            raise DomainError("invalid_field", "language")


def bind_actor(cascade, actor, revision, language):
    """Preserve the existing custom/test cascade contract without ambient identity."""
    if isinstance(cascade, Cascade):
        return _ActorCascade(cascade, ActorRequest(actor, revision, language))
    return cascade


@dataclass(frozen=True)
class _ActorCascade:
    parent: object
    request: ActorRequest

    async def generate(self, messages, schema, validate, *, scope_check=None):
        return await self.parent.generate(
            messages, schema, validate, scope_check=scope_check, actor_request=self.request
        )


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

    @staticmethod
    async def check_scope(scope_check):
        if scope_check is None:
            return
        result = scope_check()
        if inspect.isawaitable(result):
            await result

    async def generate(self, messages, schema, validate, *, scope_check=None, actor_request=None):
        # One inference per household; the Telegram polling task never waits here.
        async with self.lock:
            await self.check_scope(scope_check)
            last = "provider_unreachable"
            for index, provider in enumerate(self.providers):
                await self.check_scope(scope_check)
                if self.clock() < self.cooldown.get(index, 0):
                    continue
                try:
                    scoped_generate = getattr(provider, "generate_for_actor", None)
                    if scoped_generate is not None:
                        value = await scoped_generate(messages, schema, actor_request)
                    else:
                        value = await provider.generate(messages, schema)
                except ActorProviderUnavailable as err:
                    await self.check_scope(scope_check)
                    last = err.code
                    continue
                except DomainError as err:
                    # A revoked request may not alter provider health/cooldown or
                    # continue to a fallback based on its stale provider error.
                    await self.check_scope(scope_check)
                    if err.code in {"forbidden", "conflict", "ha_agent_changed"}:
                        raise
                    last = err.code
                    self.cooldown[index] = self.clock() + 30
                    continue
                await self.check_scope(scope_check)
                try:
                    result = validate(value)
                except DomainError as err:
                    await self.check_scope(scope_check)
                    last = err.code
                    self.cooldown[index] = self.clock() + 30
                    continue
                self.health["conversation"] = "fallback" if index else "connected"
                self.cooldown.pop(index, None)
                return result
            await self.check_scope(scope_check)
            self.health["conversation"] = last
            raise DomainError(last)
