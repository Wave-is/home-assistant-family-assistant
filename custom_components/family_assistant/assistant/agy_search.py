"""Opt-in AGY tool-source evidence, independent from conversational model prose."""

import asyncio
import time

from ..domain.validation import DomainError, text
from .http import request_json
from .provider import AGY, Cascade
from .search import public_url


class AGYSearch:
    def __init__(self, session, config, *, resolve=None):
        self.client = AGY(session, config)
        self.resolve = resolve

    async def query(self, query, language, *, child=False):
        # The observed AGY web tool has no verified child-safe search switch.
        # A separately configured SearXNG source can still serve this caller.
        if child:
            raise DomainError("provider_search_unsupported")
        if language not in {"ru", "uk", "en"}:
            raise DomainError("invalid_field", "language")
        data = await request_json(
            self.client.session,
            "POST",
            self.client.url + "/v1/search",
            timeout=min(30, self.client.timeout),
            headers=self.client.headers,
            unsupported_statuses={404, 405, 501},
            json={"query": text(query, "query", 300), "limit": 5, "model": self.client.model},
        )
        entries = data.get("results")
        if not isinstance(entries, list):
            raise DomainError("provider_bad_response")
        results, seen = [], set()
        for entry in entries[:10]:
            if not isinstance(entry, dict) or not all(
                isinstance(entry.get(key), str) for key in ("url", "title", "snippet")
            ):
                continue
            url = entry["url"]
            if url in seen or not await public_url(url, self.resolve):
                continue
            seen.add(url)
            results.append(
                {"url": url, "title": entry["title"][:200], "snippet": entry["snippet"][:1200]}
            )
            if len(results) == 5:
                break
        return results


class SearchCascade:
    """Try configured evidence sources, never substituting a model answer."""

    def __init__(self, sources, *, budget=30, clock=time.monotonic):
        self.sources, self.budget, self.clock = sources, budget, clock

    async def query(self, query, language, *, child=False):
        return await self.query_for_scope(query, language, child=child)

    async def query_for_scope(self, query, language, *, child=False, scope_check=None):
        deadline = self.clock() + self.budget
        last, empty = "provider_search_unsupported", False
        for position, source in enumerate(self.sources):
            await Cascade.check_scope(scope_check)
            remaining = max(0, deadline - self.clock())
            attempt = remaining / (len(self.sources) - position)
            try:
                async with asyncio.timeout(attempt):
                    result = await source.query(query, language, child=child)
            except TimeoutError:
                await Cascade.check_scope(scope_check)
                last = "provider_timeout"
                continue
            except DomainError as err:
                await Cascade.check_scope(scope_check)
                if err.code in {"forbidden", "conflict", "ha_agent_changed"}:
                    raise
                last = err.code
                continue
            await Cascade.check_scope(scope_check)
            if result:
                return result
            empty = True
        if empty:
            return []
        await Cascade.check_scope(scope_check)
        raise DomainError(last)
