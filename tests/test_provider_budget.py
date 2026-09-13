"""Finite ordered fallback budgets leave time for later configured providers."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from custom_components.family_assistant.assistant import provider
from custom_components.family_assistant.domain.validation import DomainError


@pytest.mark.asyncio
async def test_three_slow_sources_get_thirty_seconds_each(monkeypatch):
    elapsed, allocations = [0], []

    @asynccontextmanager
    async def timeout(seconds):
        allocations.append(seconds)
        yield

    class Slow:
        kind, timeout = "agy", 60

        async def generate(self, *_args):
            elapsed[0] += allocations[-1]
            raise DomainError("provider_timeout")

    monkeypatch.setattr(provider.asyncio, "timeout", timeout)
    cascade = provider.Cascade([Slow(), Slow(), Slow()], {}, budget=90, clock=lambda: elapsed[0])
    with pytest.raises(DomainError, match="provider_timeout"):
        await cascade.generate([], {}, lambda value: value)
    assert allocations == [30, 30, 30]


@pytest.mark.asyncio
async def test_agy_has_thirty_seconds_without_starving_seven_fallbacks(monkeypatch):
    elapsed, allocations = [0], []

    @asynccontextmanager
    async def timeout(seconds):
        allocations.append(seconds)
        yield

    class Slow:
        timeout = 60

        def __init__(self, kind):
            self.kind = kind

        async def generate(self, *_args):
            elapsed[0] += allocations[-1]
            raise DomainError("provider_timeout")

    monkeypatch.setattr(provider.asyncio, "timeout", timeout)
    cascade = provider.Cascade(
        [Slow("agy"), *[Slow("ollama") for _ in range(7)]],
        {},
        budget=90,
        clock=lambda: elapsed[0],
    )
    with pytest.raises(DomainError, match="provider_timeout"):
        await cascade.generate([], {}, lambda value: value)
    assert len(allocations) == 8 and allocations[0] == 30
    assert min(allocations) >= 5 and sum(allocations) == pytest.approx(90)


@pytest.mark.asyncio
async def test_real_attempt_timeout_reaches_fallback_and_external_cancel_does_not():
    calls = []

    class Hung:
        async def generate(self, *_args):
            calls.append("hung")
            await asyncio.Event().wait()

    class Good:
        async def generate(self, *_args):
            calls.append("good")
            return {"answer": "synthetic"}

    cascade = provider.Cascade([Hung(), Good()], {}, budget=0.1)
    assert await cascade.generate([], {}, lambda value: value) == {"answer": "synthetic"}
    assert calls == ["hung", "good"]
    calls.clear()
    cascade = provider.Cascade([Hung(), Good()], {}, budget=90)
    pending = asyncio.create_task(cascade.generate([], {}, lambda value: value))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert calls == ["hung"] and not cascade.failures and not cascade.health
