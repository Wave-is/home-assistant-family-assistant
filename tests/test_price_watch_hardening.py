"""Real Engine/dispatcher contracts and synthetic transport; never external I/O."""

import asyncio
import sys
from copy import deepcopy
from datetime import timedelta
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant import price_watch_fetcher as fetcher
from custom_components.family_assistant.assistant import article
from custom_components.family_assistant.domain import price_watch as domain
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import DeliveryError, Notifications
from custom_components.family_assistant.telegram.messages import targets


async def add(engine, now, name="Product"):
    return await engine.execute(
        "parent",
        "price_watch.add",
        {"url": f"https://merchant.example/{name}", "name": name},
        f"add-{name}",
        now,
    )


async def toggle(engine, now, enabled):
    revision = engine.snapshot().get("settings_revision", 1)
    await engine.execute(
        "owner",
        "settings.module_toggle",
        {
            "revision": revision,
            "module": "price_watch",
            "enabled": enabled,
        },
        f"toggle-{revision}",
        now,
    )


async def revise(engine, now, watcher, **fields):
    current = engine.snapshot()["price_watches"][watcher["id"]]
    return await engine.execute(
        "parent",
        "price_watch.edit",
        {
            "id": current["id"],
            "revision": current["revision"],
            **fields,
        },
        f"edit-{current['revision']}",
        now,
    )


@pytest.fixture
def worker(engine, now, monkeypatch):
    util = ModuleType("homeassistant.util")
    util.dt = SimpleNamespace(utcnow=lambda: now)
    event = ModuleType("homeassistant.helpers.event")
    timers = []

    def track(hass, callback, interval):
        timers.append(callback)
        return lambda: timers.remove(callback)

    event.async_track_time_interval = track
    monkeypatch.setitem(sys.modules, util.__name__, util)
    monkeypatch.setitem(sys.modules, event.__name__, event)
    runtime = SimpleNamespace(engine=engine, health={}, updated=lambda: None)
    entry = SimpleNamespace(entry_id="synthetic-price", runtime_data=runtime)
    hass = SimpleNamespace(
        data={"family_assistant": {"entries": {entry.entry_id: runtime}}},
        async_create_background_task=lambda coro, name: asyncio.create_task(coro),
    )
    selected = fetcher.PriceWatchScheduler(hass, entry, runtime)
    selected._stopped = False
    selected.timers = timers
    return selected


async def test_disabled_module_and_old_timer_cannot_fetch(worker, engine, now, monkeypatch):
    await add(engine, now)
    calls = []

    async def fetch(url, **kwargs):
        calls.append(url)
        return fetcher.PriceFetchResult(price_text="1", currency="USD")

    monkeypatch.setattr(fetcher, "fetch_price", fetch)
    await toggle(engine, now, False)
    await worker._poll_all()
    worker.request()
    assert not calls and worker._task is None
    await toggle(engine, now, True)
    worker.start()
    worker.start()
    assert len(worker.timers) == 1
    await worker._task
    assert len(calls) == 1
    callback = worker.timers[0]
    await worker.stop()
    await callback(now)
    assert worker._task is None and not worker.timers and len(calls) == 1


async def test_stop_cancels_and_drains_inflight_initial_poll(worker, engine, now, monkeypatch):
    watcher = await add(engine, now)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def fetch(url, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(fetcher, "fetch_price", fetch)
    worker.start()
    await entered.wait()
    await worker.stop()
    assert cancelled.is_set() and worker._task is None
    assert engine.snapshot()["price_watches"][watcher["id"]]["last_checked"] is None


@pytest.mark.parametrize(
    "change", ["url", "policy", "module_epoch", "actor_epoch", "runtime", "backup"]
)
async def test_inflight_observation_revokes_exact_scope(worker, engine, now, monkeypatch, change):
    watcher = await add(engine, now)
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch(url, **kwargs):
        entered.set()
        await release.wait()
        return fetcher.PriceFetchResult(price_text="1", currency="USD")

    monkeypatch.setattr(fetcher, "fetch_price", fetch)
    task = asyncio.create_task(worker._poll_all())
    await entered.wait()
    if change == "url":
        await revise(engine, now, watcher, url="https://merchant.example/other")
    elif change == "policy":
        await revise(engine, now, watcher, notify_drop=False)
    elif change == "module_epoch":
        await toggle(engine, now, False)
        await toggle(engine, now, True)
    elif change == "actor_epoch":
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": "parent",
                "revision": 1,
                "name": "Changed parent",
                "role": "parent",
            },
            "parent-epoch",
            now,
        )
    elif change == "runtime":
        worker._entry.runtime_data = object()
    else:
        worker._hass.data["family_assistant"]["backup"] = object()
    release.set()
    await task
    current = engine.snapshot()["price_watches"][watcher["id"]]
    assert current["last_checked"] is None and current["history"] == []
    assert not engine.snapshot()["outbox"]


async def test_unrelated_task_write_does_not_revoke_observation(worker, engine, now, monkeypatch):
    watcher = await add(engine, now)

    async def fetch(url, *, scope_check):
        await engine.execute(
            "parent", "tasks.create", {"title": "Other", "assignee": "child"}, "task", now
        )
        scope_check()
        return fetcher.PriceFetchResult(price_text="1", currency="USD")

    monkeypatch.setattr(fetcher, "fetch_price", fetch)
    await worker._poll_all()
    assert engine.snapshot()["price_watches"][watcher["id"]]["price_text"] == "1"


async def test_worker_never_depends_on_the_original_owner_id(worker, engine, now, monkeypatch):
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": 1,
            "name": "Second owner",
            "role": "owner",
        },
        "second-owner",
        now,
    )
    watcher = await add(engine, now)
    await engine.execute(
        "parent",
        "members.save",
        {
            "id": "owner",
            "revision": 1,
            "name": "Retired owner",
            "role": "owner",
            "active": False,
        },
        "retire-original",
        now,
    )

    async def fetch(url, *, scope_check):
        scope_check()
        return fetcher.PriceFetchResult(price_text="1", currency="USD")

    monkeypatch.setattr(fetcher, "fetch_price", fetch)
    await worker._poll_all()
    assert engine.snapshot()["price_watches"][watcher["id"]]["price_text"] == "1"


async def test_legacy_history_retained_and_explicit_edit_reapproves(engine, store, now):
    watcher = await add(engine, now)
    await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "price_text": "5", "currency": "USD"},
        "baseline",
        now,
    )
    state = engine.snapshot()
    legacy = state["price_watches"][watcher["id"]]
    for key in ("policy_actor", "policy_actor_revision", "policy_generation"):
        legacy.pop(key)
    history = deepcopy(legacy["history"])
    engine = Engine(state, store.save)
    assert domain.observation_scope(state, watcher["id"]) is None
    assert engine.view("parent")["price_watches"][0]["policy_status"] == "review_required"
    reviewed = await revise(engine, now, watcher)
    assert reviewed["history"] == history and reviewed["baseline_pending"]
    engine = Engine(store.value, store.save)
    assert engine.view("parent")["price_watches"][0]["policy_status"] == "ready"
    await engine.execute(
        "parent",
        "price_watch.record",
        {"id": watcher["id"], "price_text": "1", "currency": "USD"},
        "after-review",
        now,
    )
    assert not engine.snapshot()["outbox"]


async def test_system_observation_store_failure_and_replay_are_atomic(engine, store, now):
    watcher = await add(engine, now)
    scope = domain.observation_scope(engine.snapshot(), watcher["id"])
    before = engine.snapshot()
    result = {"price_text": "1", "currency": "USD", "availability": "in_stock"}
    store.fail = True
    with pytest.raises(OSError):
        await engine.background_update(
            "price_watch_observation",
            now,
            lambda ctx: domain.record_observation(ctx, scope, result),
        )
    assert engine.snapshot() == before
    store.fail = False
    await engine.background_update(
        "price_watch_observation", now, lambda ctx: domain.record_observation(ctx, scope, result)
    )
    restored = Engine(store.value, store.save)
    with pytest.raises(DomainError, match="observation_revoked"):
        await restored.background_update(
            "price_watch_observation",
            now,
            lambda ctx: domain.record_observation(ctx, scope, result),
        )
    assert len(restored.snapshot()["price_watches"][watcher["id"]]["history"]) == 1
    assert not any(
        a["actor"] == "owner" and a["action"] == "price_watch.record"
        for a in restored.snapshot()["audit"]
    )


@pytest.mark.parametrize(
    "change", ["disabled", "removed", "policy", "actor_epoch", "recipient_epoch", "legacy"]
)
async def test_pending_notices_revoke_at_actual_dispatch(engine, store, now, change):
    state = engine.snapshot()
    state["members"]["parent"]["telegram_id"] = 123456
    engine = Engine(state, store.save)
    watcher = await add(engine, now)
    for label, price in (("high", "5"), ("low", "1")):
        await engine.execute(
            "parent",
            "price_watch.record",
            {"id": watcher["id"], "price_text": price, "currency": "USD"},
            label,
            now,
        )
    if change == "disabled":
        await toggle(engine, now, False)
        await toggle(engine, now, True)
    elif change == "removed":
        await engine.execute("parent", "price_watch.remove", {"id": watcher["id"]}, "remove", now)
    elif change == "policy":
        await revise(engine, now, watcher, notify_drop=False)
    elif change in {"actor_epoch", "recipient_epoch"}:
        member = "parent" if change == "actor_epoch" else "owner"
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": member,
                "revision": 1,
                "name": "New name",
                "role": "parent" if member == "parent" else "owner",
            },
            "epoch",
            now,
        )
    else:
        state = engine.snapshot()
        for event in state["outbox"].values():
            event["data"].pop("price_watch_scope")
        engine = Engine(state, store.save)
    calls = []

    async def send(event, target):
        calls.append(event)
        return "synthetic"

    await Notifications(engine, targets, send).run(now)
    assert calls == []
    assert {event["state"] for event in engine.snapshot()["outbox"].values()} == {"superseded"}


@pytest.mark.parametrize(
    "price", ["-1", "NaN", "Infinity", "USD 1", "1foo2", "1 23", "1e309", "1.2.3"]
)
def test_invalid_prices_never_invent_a_number(price):
    assert domain._parse_price_float(price) is None
    with pytest.raises(DomainError):
        domain.validate_observation(price, "USD")


async def test_currency_change_and_zero_price(engine, now):
    watcher = await add(engine, now)
    for operation, price, currency in (
        ("one", "100", "USD"),
        ("two", "1", "EUR"),
        ("three", "0", "EUR"),
    ):
        await engine.execute(
            "parent",
            "price_watch.record",
            {"id": watcher["id"], "price_text": price, "currency": currency},
            operation,
            now,
        )
    notices = list(engine.snapshot()["outbox"].values())
    assert len(notices) == 1 and notices[0]["data"]["new_price"] == "0"


async def queued(engine, store, now, *, availability=False):
    state = engine.snapshot()
    state["members"]["parent"]["telegram_id"] = 123456
    engine = Engine(state, store.save)
    watcher = await add(engine, now)
    for operation, price, stock in (("high", "100", "out_of_stock"), ("low", "80", "in_stock")):
        await engine.execute(
            "parent",
            "price_watch.record",
            {
                "id": watcher["id"],
                "price_text": price,
                "currency": "USD",
                "availability": stock,
            },
            operation,
            now,
        )
    key = "price_watch_available" if availability else "price_watch_drop"
    event = next(event for event in engine.snapshot()["outbox"].values() if event["key"] == key)
    assert domain.current_event(engine.snapshot(), event, now)
    return engine, watcher, event


@pytest.mark.parametrize("change", ["rebound", "stock_loss", "same_price", "error"])
async def test_latest_observation_supersedes_old_fact(engine, store, now, change):
    engine, watcher, event = await queued(engine, store, now, availability=change == "stock_loss")
    payload = {
        "id": watcher["id"],
        "price_text": "120" if change == "rebound" else "80",
        "currency": "USD",
        "availability": "out_of_stock" if change == "stock_loss" else "in_stock",
    }
    if change == "error":
        payload = {"id": watcher["id"], "error": "timeout"}
    await engine.execute("parent", "price_watch.record", payload, "latest", now)
    assert not domain.current_event(engine.snapshot(), event, now)
    calls = []

    async def send(event, target):
        calls.append(event)
        return "synthetic"

    await Notifications(engine, targets, send).run(now)
    assert not calls


@pytest.mark.parametrize("delta", [-1, 3600, 86400])
async def test_notice_age_and_clock_rollback_fail_closed(engine, store, now, delta):
    engine, watcher, event = await queued(engine, store, now)
    check_at = now + timedelta(seconds=delta)
    assert not domain.current_event(engine.snapshot(), event, check_at)
    calls = []

    async def send(event, target):
        calls.append(event)
        return "synthetic"

    await Notifications(Engine(store.value, store.save), targets, send).run(check_at)
    assert not calls


async def test_price_delivery_uncertain_is_not_blindly_retried(engine, store, now):
    engine, watcher, event = await queued(engine, store, now)
    calls = []

    async def uncertain(event, target):
        calls.append(event["id"])
        raise DeliveryError("delivery_uncertain", uncertain=True)

    dispatcher = Notifications(engine, targets, uncertain)
    await dispatcher.run(now, limit=1)
    first = deepcopy(calls)
    await Notifications(Engine(store.value, store.save), targets, uncertain).run(now, limit=1)
    assert calls == first  # The one-second rate also holds the independent availability event.
    assert engine.snapshot()["outbox"][first[0]]["state"] == "uncertain"
    restored = Engine(store.value, store.save)
    dispatcher = Notifications(restored, targets, uncertain)
    await dispatcher.run(now + timedelta(seconds=2))
    await dispatcher.run(now + timedelta(seconds=4))
    assert calls.count(first[0]) == 1 and len(calls) == len(set(calls)) == 2


@pytest.mark.parametrize("change", ["rebound", "module"])
async def test_price_revocation_after_claim_is_checked_before_transport(engine, store, now, change):
    from test_notification_dispatch_revocation import ClaimGateEngine

    engine, watcher, event = await queued(engine, store, now)
    gated = ClaimGateEngine(engine.snapshot(), store.save)
    sent = []

    async def send(event, target):
        sent.append(event["id"])
        return "unexpected"

    running = asyncio.create_task(Notifications(gated, targets, send).run(now))
    try:
        await asyncio.wait_for(gated.claim_persisted.wait(), 2)
        if change == "module":
            await toggle(gated, now, False)
        else:
            await gated.execute(
                "parent",
                "price_watch.record",
                {
                    "id": watcher["id"],
                    "price_text": "120",
                    "currency": "USD",
                },
                "rebound",
                now,
            )
    finally:
        gated.release_claim.set()
    assert await asyncio.wait_for(running, 2) == 0 and not sent


async def test_frozen_approval_actor_epoch_and_replay(engine, now):
    watcher = await add(engine, now)
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": 1,
            "name": "Updated parent",
            "role": "parent",
        },
        "parent-epoch",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await revise(engine, now, watcher, actor_revision=1)
    reviewed = await revise(engine, now, watcher, actor_revision=2)
    assert reviewed["policy_actor_revision"] == 2


async def test_legacy_userinfo_never_leaks_in_shared_view(engine, store, now):
    watcher = await add(engine, now)
    state = engine.snapshot()
    secret_url = "https://synthetic:never-disclose@merchant.example/item"
    state["price_watches"][watcher["id"]].update(
        url=secret_url, name=secret_url, history=[{"url": secret_url, "price_text": "1"}]
    )
    engine = Engine(state, store.save)
    assert "never-disclose" not in str(engine.view("child")["price_watches"])
    assert engine.snapshot()["price_watches"][watcher["id"]]["url"] == secret_url
    await revise(engine, now, watcher, url="https://merchant.example/item")
    assert "never-disclose" not in str(engine.view("child")["price_watches"])
    assert engine.snapshot()["price_watches"][watcher["id"]]["history"][0]["url"] == secret_url


@pytest.fixture
def public_transport(monkeypatch):
    calls = []

    async def resolve(host, port):
        calls.append((host, port))
        return ["93.184.216.34"]

    monkeypatch.setattr(article, "_system_resolve", resolve)
    return calls


@pytest.mark.parametrize(
    "location",
    [
        "http://merchant.example/item",
        "https://127.0.0.1/item",
        "https://user:secret@merchant.example/item",
        "https://merchant.example:8443/item",
    ],
)
async def test_redirect_cannot_escape_pinned_public_https(public_transport, monkeypatch, location):
    hops = []

    async def request(target, check):
        hops.append(target)
        return article._Hop(302, location=location)

    monkeypatch.setattr(article, "_request_hop", request)
    result = await fetcher.fetch_price("https://merchant.example/item")
    assert result.error == "invalid_url" and len(hops) == 1 and len(public_transport) == 1


async def test_dns_rebinding_mixed_answers_fail_closed(monkeypatch):
    async def resolve(host, port):
        return ["93.184.216.34", "127.0.0.1"]

    async def never(*args):
        pytest.fail("must fail before transport")

    monkeypatch.setattr(article, "_system_resolve", resolve)
    monkeypatch.setattr(article, "_request_hop", never)
    assert (await fetcher.fetch_price("https://merchant.example/item")).error == "invalid_url"


async def test_total_timeout_includes_dns(monkeypatch):
    async def resolve(host, port):
        await asyncio.Event().wait()

    monkeypatch.setattr(article, "_system_resolve", resolve)
    monkeypatch.setattr(fetcher, "_FETCH_TIMEOUT", 0.01)
    assert (await fetcher.fetch_price("https://merchant.example/item")).error == "timeout"


async def test_transport_errors_are_stable_and_revocation_propagates(public_transport, monkeypatch):
    async def unavailable(*args):
        raise DomainError("article_unavailable", "https://user:secret@merchant.example")

    monkeypatch.setattr(article, "_request_hop", unavailable)
    assert (await fetcher.fetch_price("https://merchant.example/item")).error == "unavailable"

    def revoked():
        raise DomainError("observation_revoked")

    with pytest.raises(DomainError, match="observation_revoked"):
        await fetcher.fetch_price("https://merchant.example/item", scope_check=revoked)


async def test_body_limit_and_zero_json_price(public_transport, monkeypatch):
    async def too_large(*args):
        return article._Hop(200, b"x" * (article.MAX_BODY_BYTES + 1), "text/html")

    monkeypatch.setattr(article, "_request_hop", too_large)
    assert (
        await fetcher.fetch_price("https://merchant.example/item")
    ).error == "response_too_large"

    async def zero(*args):
        return article._Hop(
            200,
            b'<script type="application/ld+json">{"@type":"Product",'
            b'"offers":{"price":0,"priceCurrency":"USD"}}</script>',
            "text/html",
        )

    monkeypatch.setattr(article, "_request_hop", zero)
    result = await fetcher.fetch_price("https://merchant.example/item")
    assert not result.error and result.price_text == "0"


async def test_numeric_prefix_is_never_truncated_into_a_valid_price(public_transport, monkeypatch):
    async def request(*args):
        return article._Hop(
            200,
            b'<script type="application/ld+json">{"@type":"Product",'
            b'"offers":{"price":"' + b"1" * 40 + b'HOSTILE"}}</script>',
            "text/html",
        )

    monkeypatch.setattr(article, "_request_hop", request)
    assert (await fetcher.fetch_price("https://merchant.example/item")).error == "invalid_response"


@pytest.mark.parametrize(
    "body", [b'{"@graph":1}', b'{"@type":"Product","offers":{"price":{},"availability":1}}']
)
async def test_malformed_merchant_json_is_not_an_unhandled_exception(
    public_transport, monkeypatch, body
):
    async def request(*args):
        return article._Hop(
            200, b'<script type="application/ld+json">' + body + b"</script>", "text/html"
        )

    monkeypatch.setattr(article, "_request_hop", request)
    result = await fetcher.fetch_price("https://merchant.example/item")
    assert result.error == "invalid_response"
