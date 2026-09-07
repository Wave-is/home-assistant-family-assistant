"""Answer-only article service, provider scope, concurrency, and transient replay."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.assistant import article_service, plans
from custom_components.family_assistant.assistant.article_service import ArticleService
from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)
ARTICLE = {
    "title": "Public title",
    "text": "Public evidence only.",
    "requested_url": "https://example.org/start?source=one",
    "final_url": "https://example.org/final",
}


class Scope:
    def __init__(self):
        self.current = True
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if not self.current:
            raise DomainError("forbidden")


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def generate(self, messages, schema):
        self.calls.append((deepcopy(messages), deepcopy(schema)))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)


class Fetcher:
    def __init__(self, result=ARTICLE):
        self.result = result
        self.calls = []

    async def __call__(self, url, *, scope_check):
        self.calls.append(url)
        await scope_check()
        if isinstance(self.result, Exception):
            raise self.result
        return deepcopy(self.result)


def service(provider, *, fetcher=None, health=None, clock=lambda: 1.0):
    cascade = Cascade([provider], {} if health is None else health, clock=clock)
    return ArticleService(cascade, fetcher=fetcher or Fetcher(), clock=clock)


async def answer(instance, scope, **changes):
    values = {
        "actor": "adult",
        "actor_revision": 7,
        "language": "en",
        "url": ARTICLE["requested_url"],
        "operation_id": "article-operation",
        "now": NOW,
        "scope_revision": "article-config-generation",
        "scope_check": scope,
    }
    values.update(changes)
    return await instance.answer(**values)


async def test_public_only_prompt_real_cascade_and_verified_citations_strip_invented_links():
    provider = Provider(
        {
            "kind": "answer",
            "text": (
                "Summary [bad](https://invented.invalid/path) and "
                "www.fake.invalid plus fake.example/path are omitted."
            ),
        }
    )
    fetcher = Fetcher()
    scope = Scope()
    result = await answer(service(provider, fetcher=fetcher), scope)
    assert result == {
        "answer": "Summary bad and plus are omitted.",
        "sources": [
            {
                "title": "Public title",
                "url": "https://example.org/final",
                "requested_url": "https://example.org/start?source=one",
                "retrieved_at": NOW.isoformat(),
            }
        ],
    }
    messages, schema = provider.calls[0]
    assert schema == plans.ARTICLE_SCHEMA
    serialized = json.dumps(messages, ensure_ascii=False)
    assert "Public evidence only." in serialized
    for excluded in (
        "https://example.org",
        "actor",
        "adult",
        "member",
        "view",
        "task",
        "receipt",
        "operation",
    ):
        assert excluded not in serialized
    assert fetcher.calls == [ARTICLE["requested_url"]]
    assert scope.calls >= 8


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"kind": "commands", "text": "No"},
        {"kind": "answer", "text": ""},
        {"kind": "answer", "text": "ok", "url": "https://invented.invalid"},
        {"kind": "answer", "text": 1},
    ],
)
def test_answer_schema_and_validator_are_exact(value):
    with pytest.raises(DomainError, match="provider_bad_response"):
        plans.validate_article_answer(value)


def test_article_messages_are_immutable_bounded_and_have_no_family_or_url_fields():
    source = {"title": "Title", "text": "Evidence"}
    before = deepcopy(source)
    messages = plans.article_messages("uk", source, NOW)
    assert source == before
    data = json.loads(messages[1]["content"])
    assert data == {
        "language": "uk",
        "now": NOW.isoformat(),
        "instruction": "Summarize the supplied article evidence.",
        "untrusted_article": {
            "source": "article-1",
            "title": "Title",
            "text": "Evidence",
        },
    }
    assert "view" not in data and "url" not in data and "refs" not in data


async def test_completed_exact_retry_is_current_scoped_immutable_and_does_not_refetch():
    provider = Provider({"kind": "answer", "text": "First answer"})
    fetcher = Fetcher()
    instance = service(provider, fetcher=fetcher)
    scope = Scope()
    first = await answer(instance, scope)
    first["answer"] = "caller mutation"
    first["sources"][0]["title"] = "caller mutation"
    assert (await answer(instance, scope))["answer"] == "First answer"
    assert (await answer(instance, scope))["sources"][0]["title"] == "Public title"
    assert len(fetcher.calls) == len(provider.calls) == 1
    scope.current = False
    with pytest.raises(DomainError, match="forbidden"):
        await answer(instance, scope)


@pytest.mark.parametrize(
    "change",
    [
        {"url": "https://example.org/different"},
        {"actor_revision": 8},
        {"language": "ru"},
        {"scope_revision": "new-generation"},
    ],
)
async def test_same_operation_with_different_input_or_scope_is_rejected(change):
    provider = Provider({"kind": "answer", "text": "First answer"})
    instance = service(provider)
    scope = Scope()
    await answer(instance, scope)
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await answer(instance, scope, **change)


async def test_cache_ttl_is_monotonic_bounded_and_expired_exact_operation_refetches():
    monotonic = [10.0]
    provider = Provider(
        {"kind": "answer", "text": "First"},
        {"kind": "answer", "text": "Second"},
    )
    fetcher = Fetcher()
    instance = service(provider, fetcher=fetcher, clock=lambda: monotonic[0])
    scope = Scope()
    assert (await answer(instance, scope))["answer"] == "First"
    monotonic[0] += article_service.CACHE_TTL + 0.01
    assert (await answer(instance, scope))["answer"] == "Second"
    assert len(fetcher.calls) == 2


async def test_successful_provider_revocation_changes_no_health_or_cooldown_and_returns_nothing():
    entered = asyncio.Event()
    release = asyncio.Event()

    class Delayed:
        async def generate(self, _messages, _schema):
            entered.set()
            await release.wait()
            return {"kind": "answer", "text": "stale success"}

    fallback = Provider({"kind": "answer", "text": "must not run"})
    health = {}
    cascade = Cascade([Delayed(), fallback], health, clock=lambda: 5)
    instance = ArticleService(cascade, fetcher=Fetcher(), clock=lambda: 5)
    scope = Scope()
    task = asyncio.create_task(answer(instance, scope))
    await entered.wait()
    scope.current = False
    release.set()
    with pytest.raises(DomainError, match="forbidden"):
        await task
    assert health == {} and cascade.cooldown == {} and fallback.calls == []


async def test_failed_provider_revocation_changes_no_health_or_cooldown_and_skips_fallback():
    entered = asyncio.Event()
    release = asyncio.Event()

    class DelayedFailure:
        async def generate(self, _messages, _schema):
            entered.set()
            await release.wait()
            raise DomainError("provider_timeout")

    fallback = Provider({"kind": "answer", "text": "must not run"})
    health = {}
    cascade = Cascade([DelayedFailure(), fallback], health, clock=lambda: 5)
    instance = ArticleService(cascade, fetcher=Fetcher(), clock=lambda: 5)
    scope = Scope()
    task = asyncio.create_task(answer(instance, scope))
    await entered.wait()
    scope.current = False
    release.set()
    with pytest.raises(DomainError, match="forbidden"):
        await task
    assert health == {} and cascade.cooldown == {} and fallback.calls == []


async def test_invalid_provider_result_revocation_changes_no_health_or_cooldown():
    entered = asyncio.Event()
    release = asyncio.Event()

    class DelayedInvalid:
        async def generate(self, _messages, _schema):
            entered.set()
            await release.wait()
            return {"kind": "answer", "text": ""}

    fallback = Provider({"kind": "answer", "text": "must not run"})
    cascade = Cascade([DelayedInvalid(), fallback], {}, clock=lambda: 5)
    instance = ArticleService(cascade, fetcher=Fetcher(), clock=lambda: 5)
    scope = Scope()
    task = asyncio.create_task(answer(instance, scope))
    await entered.wait()
    scope.current = False
    release.set()
    with pytest.raises(DomainError, match="forbidden"):
        await task
    assert cascade.health == {} and cascade.cooldown == {} and fallback.calls == []


async def test_unchanged_provider_failure_preserves_existing_fallback_and_health_behavior():
    primary = Provider(DomainError("provider_timeout"))
    fallback = Provider({"kind": "answer", "text": "Fallback answer"})
    health = {}
    cascade = Cascade([primary, fallback], health, clock=lambda: 5)
    instance = ArticleService(cascade, fetcher=Fetcher(), clock=lambda: 5)
    assert (await answer(instance, Scope()))["answer"] == "Fallback answer"
    assert health == {"conversation": "fallback"}
    assert cascade.cooldown == {0: 35}


async def test_scope_is_checked_after_waiting_for_shared_cascade_lock_before_provider():
    provider = Provider({"kind": "answer", "text": "must not run"})
    cascade = Cascade([provider], {}, clock=lambda: 5)
    instance = ArticleService(cascade, fetcher=Fetcher(), clock=lambda: 5)
    scope = Scope()
    await cascade.lock.acquire()
    task = asyncio.create_task(answer(instance, scope))
    await asyncio.sleep(0)
    scope.current = False
    cascade.lock.release()
    with pytest.raises(DomainError, match="forbidden"):
        await task
    assert provider.calls == [] and cascade.health == {} and cascade.cooldown == {}


async def test_per_actor_and_household_limits_fail_fast_and_cancellation_releases_slots():
    entered = [asyncio.Event(), asyncio.Event()]
    hold = asyncio.Event()
    call_count = 0

    async def blocked_fetch(url, *, scope_check):
        nonlocal call_count
        index = call_count
        call_count += 1
        entered[index].set()
        await hold.wait()
        await scope_check()
        return deepcopy(ARTICLE)

    provider = Provider(
        {"kind": "answer", "text": "one"},
        {"kind": "answer", "text": "two"},
    )
    instance = service(provider, fetcher=blocked_fetch)
    scopes = [Scope(), Scope()]
    first = asyncio.create_task(answer(instance, scopes[0], operation_id="one"))
    second = asyncio.create_task(
        answer(instance, scopes[1], actor="parent", actor_revision=3, operation_id="two")
    )
    await asyncio.gather(*(event.wait() for event in entered))
    with pytest.raises(DomainError, match="assistant_busy"):
        await answer(instance, Scope(), operation_id="same-actor")
    with pytest.raises(DomainError, match="assistant_busy"):
        await answer(instance, Scope(), actor="owner", actor_revision=2, operation_id="third")
    first.cancel()
    second.cancel()
    for task in (first, second):
        with pytest.raises(asyncio.CancelledError):
            await task
    assert instance._active == {} and instance._active_actors == set()


async def test_worker_count_is_bounded_while_authority_lookup_is_waiting():
    entered = 0
    both_entered = asyncio.Event()
    release = asyncio.Event()
    provider = Provider({"kind": "answer", "text": "Unused"})
    instance = service(provider)

    async def gated_scope():
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await release.wait()

    first = asyncio.create_task(answer(instance, gated_scope, operation_id="waiting-one"))
    second = asyncio.create_task(
        answer(instance, gated_scope, actor="parent", operation_id="waiting-two")
    )
    await asyncio.wait_for(both_entered.wait(), 1)
    for index in range(20):
        with pytest.raises(DomainError, match="assistant_busy"):
            await answer(instance, gated_scope, operation_id=f"extra-{index}")
    assert entered == 2 and len(instance._workers) == 2
    assert not provider.calls
    await instance.async_stop()
    for caller in (first, second):
        with pytest.raises(DomainError, match="article_unavailable"):
            await caller
    assert not instance._workers


async def test_same_active_operation_conflicts_on_body_and_busy_on_exact_retry():
    entered = asyncio.Event()
    hold = asyncio.Event()

    async def blocked_fetch(_url, *, scope_check):
        entered.set()
        await hold.wait()
        await scope_check()
        return deepcopy(ARTICLE)

    instance = service(Provider({"kind": "answer", "text": "done"}), fetcher=blocked_fetch)
    scope = Scope()
    task = asyncio.create_task(answer(instance, scope))
    await entered.wait()
    with pytest.raises(DomainError, match="assistant_busy"):
        await answer(instance, scope)
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await answer(instance, scope, url="https://example.org/other")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert instance._active == {}


async def test_total_timeout_includes_cascade_wait_and_clears_active_slot(monkeypatch):
    provider = Provider({"kind": "answer", "text": "must not run"})
    cascade = Cascade([provider], {}, clock=lambda: 5)
    instance = ArticleService(cascade, fetcher=Fetcher(), clock=lambda: 5)
    await cascade.lock.acquire()
    monkeypatch.setattr(article_service, "TOTAL_TIMEOUT", 0.01)
    try:
        with pytest.raises(DomainError, match="provider_timeout"):
            await answer(instance, Scope())
    finally:
        cascade.lock.release()
    assert instance._active == {} and provider.calls == []


async def test_close_cancels_only_owned_work_clears_evidence_and_async_stop_settles():
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked_fetch(_url, *, scope_check):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    instance = service(Provider({"kind": "answer", "text": "must not run"}), fetcher=blocked_fetch)
    caller = asyncio.create_task(answer(instance, Scope()))
    await entered.wait()
    instance.close()
    with pytest.raises(DomainError, match="article_unavailable"):
        await caller
    assert not caller.cancelled()
    await instance.async_stop()
    assert cancelled.is_set()
    assert instance._workers == set()
    assert instance._active == {} and instance._active_actors == set()
    assert instance._seen == {} and instance._completed == {}
    with pytest.raises(DomainError, match="article_unavailable"):
        await answer(instance, Scope(), operation_id="after-close")


async def test_completed_cache_retains_only_answer_and_verified_citation_not_article_body():
    instance = service(Provider({"kind": "answer", "text": "Safe summary"}))
    await answer(instance, Scope())
    serialized = json.dumps(instance._completed, ensure_ascii=False)
    assert "Public evidence only." not in serialized
    assert "Safe summary" in serialized
    assert len(instance._completed) <= article_service.MAX_COMPLETED
    assert len(instance._seen) <= article_service.MAX_SEEN


@pytest.mark.parametrize(
    "fetch_result,provider_result,code",
    [
        (
            {**ARTICLE, "canonical_url": "https://page-claimed.invalid"},
            None,
            "article_invalid_content",
        ),
        ({**ARTICLE, "final_url": "http://example.org"}, None, "article_invalid_url"),
        ({**ARTICLE, "title": "bad\x00title"}, None, "article_invalid_content"),
        (ARTICLE, {"kind": "answer", "text": "https://only-link.invalid"}, "provider_bad_response"),
    ],
)
async def test_unverified_fetch_fields_page_canonical_and_link_only_answers_never_escape(
    fetch_result, provider_result, code
):
    provider = Provider(provider_result) if provider_result is not None else Provider()
    instance = service(provider, fetcher=Fetcher(fetch_result))
    with pytest.raises(DomainError, match=code):
        await answer(instance, Scope())
    if provider_result is None:
        assert provider.calls == []
