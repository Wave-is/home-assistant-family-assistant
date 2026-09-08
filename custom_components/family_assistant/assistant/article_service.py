"""Answer-only synthesis over one explicitly fetched public article."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime

from ..domain.validation import DomainError, revision, text, timestamp
from . import article, plans
from .provider import bind_actor

MAX_ACTIVE_HOUSEHOLD = 2
MAX_COMPLETED = 32
MAX_SEEN = 64
CACHE_TTL = 300
TOTAL_TIMEOUT = 60

_MARKDOWN_LINK = re.compile(r"\[([^\]]{0,500})\]\([^)]{0,2048}\)")
_RAW_URL = re.compile(r"(?i)(?:\b[a-z][a-z0-9+.-]{1,20}://|\bwww\.)[^\s<>]+")
_BARE_DOMAIN = re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,63}(?:/[^\s<>]*)?")
_WHITESPACE = re.compile(r"[^\S\n]+")
_BLANKS = re.compile(r"\n{3,}")


class ArticleService:
    """Coordinate bounded fetch, provider inference, concurrency, and transient replay."""

    def __init__(self, cascade, *, fetcher=article.fetch, clock=time.monotonic):
        self.cascade = cascade
        self._fetcher = fetcher
        self._clock = clock
        self._guard = asyncio.Lock()
        self._active: dict[str, tuple[str, str]] = {}
        self._active_actors: set[str] = set()
        self._seen: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._completed: OrderedDict[str, tuple[str, float, dict]] = OrderedDict()
        self._workers: set[asyncio.Task] = set()
        self._closed = False

    def close(self) -> None:
        """Invalidate transient state and request cancellation of owned work."""
        self._closed = True
        self._seen.clear()
        self._completed.clear()
        for task in tuple(self._workers):
            task.cancel()

    async def async_stop(self) -> None:
        """Cancel and settle only work owned by this service instance."""
        self.close()
        workers = tuple(self._workers)
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    def _prune(self, now: float) -> None:
        for records in (self._seen, self._completed):
            for operation_id in list(records):
                if records[operation_id][1] > now:
                    continue
                records.pop(operation_id, None)

    @staticmethod
    def _signature(actor, actor_revision, language, url, operation_id, scope_revision):
        return hashlib.sha256(
            json.dumps(
                [actor, actor_revision, language, url, operation_id, scope_revision],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    async def _reserve(self, actor: str, operation_id: str, signature: str):
        now = self._clock()
        async with self._guard:
            if self._closed:
                raise DomainError("article_unavailable")
            self._prune(now)
            completed = self._completed.get(operation_id)
            if completed is not None:
                if completed[0] != signature:
                    raise DomainError("idempotency_conflict")
                self._completed.move_to_end(operation_id)
                return deepcopy(completed[2])
            seen = self._seen.get(operation_id)
            if seen is not None and seen[0] != signature:
                raise DomainError("idempotency_conflict")
            active = self._active.get(operation_id)
            if active is not None:
                if active[1] != signature:
                    raise DomainError("idempotency_conflict")
                raise DomainError("assistant_busy")
            if actor in self._active_actors or len(self._active) >= MAX_ACTIVE_HOUSEHOLD:
                raise DomainError("assistant_busy")
            self._active[operation_id] = (actor, signature)
            self._active_actors.add(actor)
            self._seen[operation_id] = (signature, now + CACHE_TTL)
            self._seen.move_to_end(operation_id)
            while len(self._seen) > MAX_SEEN:
                self._seen.popitem(last=False)
            return None

    async def _release(self, actor: str, operation_id: str, signature: str) -> None:
        async with self._guard:
            if self._active.get(operation_id) == (actor, signature):
                self._active.pop(operation_id, None)
                self._active_actors.discard(actor)

    async def _store(self, operation_id: str, signature: str, response: dict) -> None:
        now = self._clock()
        async with self._guard:
            self._prune(now)
            self._completed[operation_id] = (
                signature,
                now + CACHE_TTL,
                deepcopy(response),
            )
            self._completed.move_to_end(operation_id)
            while len(self._completed) > MAX_COMPLETED:
                self._completed.popitem(last=False)

    @staticmethod
    def _verified(value) -> dict:
        if not isinstance(value, dict) or set(value) != {
            "title",
            "text",
            "requested_url",
            "final_url",
        }:
            raise DomainError("article_invalid_content")
        title = value["title"]
        body = value["text"]
        if (
            not isinstance(title, str)
            or len(title) > article.MAX_TITLE_CHARS
            or article._clean_text(title) != title
            or not isinstance(body, str)
            or not body
            or len(body) > article.MAX_TEXT_CHARS
        ):
            raise DomainError("article_invalid_content")
        urls = []
        for key in ("requested_url", "final_url"):
            url = value[key]
            if not isinstance(url, str) or article._normalize_url(url)[0] != url:
                raise DomainError("article_invalid_url")
            urls.append(url)
        return {"title": title, "text": body, "requested_url": urls[0], "final_url": urls[1]}

    @staticmethod
    def _answer(value) -> str:
        answer = _MARKDOWN_LINK.sub(r"\1", value)
        answer = _RAW_URL.sub("", answer)
        answer = _BARE_DOMAIN.sub("", answer)
        answer = _WHITESPACE.sub(" ", answer)
        answer = "\n".join(line.strip() for line in answer.splitlines())
        answer = _BLANKS.sub("\n\n", answer).strip()
        if not answer or not any(character.isalnum() for character in answer):
            raise DomainError("provider_bad_response")
        return answer

    async def _execute(
        self,
        actor: str,
        actor_revision: int,
        language: str,
        url: str,
        operation_id: str,
        now: datetime,
        *,
        scope_revision: str,
        scope_check,
    ) -> dict:
        signature = self._signature(
            actor,
            actor_revision,
            language,
            url,
            operation_id,
            scope_revision,
        )
        reserved = False
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT):
                await self.cascade.check_scope(scope_check)
                cached = await self._reserve(actor, operation_id, signature)
                if cached is not None:
                    await self.cascade.check_scope(scope_check)
                    return cached
                reserved = True
                fetched = self._verified(await self._fetcher(url, scope_check=scope_check))
                await self.cascade.check_scope(scope_check)
                messages = plans.article_messages(
                    language,
                    {"title": fetched["title"], "text": fetched["text"]},
                    now,
                )
                result = await bind_actor(self.cascade, actor, actor_revision, language).generate(
                    messages,
                    plans.ARTICLE_SCHEMA,
                    plans.validate_article_answer,
                    scope_check=scope_check,
                )
                await self.cascade.check_scope(scope_check)
                answer = self._answer(result["text"])
                response = {
                    "answer": answer,
                    "sources": [
                        {
                            "title": fetched["title"],
                            "url": fetched["final_url"],
                            "requested_url": fetched["requested_url"],
                            "retrieved_at": now.isoformat(),
                        }
                    ],
                }
                await self._store(operation_id, signature, response)
                await self.cascade.check_scope(scope_check)
                return deepcopy(response)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise DomainError("provider_timeout") from None
        finally:
            if reserved:
                await asyncio.shield(self._release(actor, operation_id, signature))

    async def answer(
        self,
        actor: str,
        actor_revision: int,
        language: str,
        url: str,
        operation_id: str,
        now: datetime,
        *,
        scope_revision: str,
        scope_check,
    ) -> dict:
        """Return a scoped answer and only transport-verified structured citations."""
        selected_actor = text(actor, "actor", 100)
        selected_revision = revision(actor_revision)
        if language not in {"en", "ru", "uk"}:
            raise DomainError("invalid_field", "language")
        if not isinstance(url, str) or not url:
            raise DomainError("invalid_field", "url")
        operation = text(operation_id, "operation_id", 100)
        selected_scope = text(scope_revision, "scope_revision", 128)
        requested_at = timestamp(now, "now")
        if not callable(scope_check):
            raise DomainError("invalid_field", "scope")
        if self._closed:
            raise DomainError("article_unavailable")
        # Scope lookup can itself await HA authorization. Bound workers before
        # spawning, not only after their eventual reservation reaches the lock.
        if len(self._workers) >= MAX_ACTIVE_HOUSEHOLD:
            raise DomainError("assistant_busy")
        worker = asyncio.create_task(
            self._execute(
                selected_actor,
                selected_revision,
                language,
                url,
                operation,
                requested_at,
                scope_revision=selected_scope,
                scope_check=scope_check,
            )
        )
        self._workers.add(worker)
        worker.add_done_callback(self._workers.discard)
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            caller = asyncio.current_task()
            if caller is not None and caller.cancelling():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
                raise
            raise DomainError("article_unavailable") from None


__all__ = ["ArticleService"]
