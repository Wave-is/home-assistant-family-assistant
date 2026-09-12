"""Real Engine/domain school polling and delivery with fictional provider transport."""

import asyncio
import importlib.util
import sys
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_online_school_domain import binding, snapshot

from custom_components.family_assistant.domain import online_school as domain
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.module_runtime import reconcile, signature
from custom_components.family_assistant.notifications import DeliveryError, Notifications
from custom_components.family_assistant.online_school import delivery, manager, messages
from custom_components.family_assistant.telegram.messages import render, targets

SOURCE = "OSruntime"
SECRET = "SYNTHETIC-RUNTIME-SCHOOL-PASSWORD"


async def prepared(engine, store, now, *, notifications=False, changes=False):
    state = engine.snapshot()
    state["settings"]["modules"] = sorted(set(state["settings"]["modules"]) | {"school"})
    for index, member in enumerate(("owner", "parent", "child", "sibling")):
        state["members"][member]["telegram_id"] = 987650001 + index
    state["telegram"]["group_id"] = -100999888777
    engine = Engine(state, store.save)
    config = binding(
        id=SOURCE,
        student_id="101",
        enabled=True,
        rules={
            "enabled": notifications,
            "notify_changes": changes,
            "homework_time": "18:00",
            "recipients": ["owner", "parent", "child"] if notifications else [],
        },
        url="https://school.example.invalid",
        username="synthetic-parent",
        password=SECRET,
    )
    options = {"revision": 1, "sources": {SOURCE: config}}
    await engine.system_update(
        "school_bindings", now, lambda ctx: domain.sync_bindings(ctx, {"online_school": options})
    )
    return engine, options


def source(engine):
    return engine.snapshot()["school"]["online"]["sources"][SOURCE]


def events(engine):
    return [event for event in engine.snapshot()["outbox"].values() if event["key"] == delivery.KEY]


class Provider:
    def __init__(self):
        self.value = snapshot(student_id="101")
        self.error = None
        self.on_fetch = None
        self.on_close = None
        self.created = []
        self.fetches = []
        self.closed = []

    def factory(self, url, username, password):
        assert (url, username, password) == (
            "https://school.example.invalid",
            "synthetic-parent",
            SECRET,
        )
        harness = self
        number = len(self.created)
        self.created.append(number)

        class Client:
            async def fetch(self, student_id, timezone, now):
                harness.fetches.append((student_id, timezone, now))
                if harness.on_fetch:
                    await harness.on_fetch()
                if harness.error:
                    raise harness.error
                return deepcopy(harness.value)

            async def close(self):
                harness.closed.append(number)
                if harness.on_close:
                    await harness.on_close()

        return Client()


async def poll(engine, options, now, provider, **kwargs):
    await manager.poll(
        engine,
        options,
        now,
        current=kwargs.pop("current", lambda: options),
        factory=provider.factory,
        **kwargs,
    )


async def test_baseline_is_silent_private_and_repeated_not_due_polls_do_not_write(
    engine, store, now
):
    engine, options = await prepared(engine, store, now, notifications=True, changes=True)
    provider = Provider()
    await poll(engine, options, now, provider)
    assert source(engine)["status"] == "ready"
    assert source(engine)["snapshot"] == domain.normalize_snapshot(provider.value)
    assert source(engine)["changes"] == [] and events(engine) == []
    assert provider.closed == [0]
    assert SECRET not in repr(engine.snapshot())
    before, writes = engine.snapshot(), store.calls
    for minutes in (-1, 0, 1, 14):
        await poll(engine, options, now + timedelta(minutes=minutes), provider)
    assert engine.snapshot() == before and store.calls == writes
    assert len(provider.fetches) == 1
    await poll(engine, options, now + timedelta(minutes=15), provider)
    assert len(provider.fetches) == 2 and store.calls == writes + 1


@pytest.mark.parametrize("when", ["fetch", "close"])
@pytest.mark.parametrize("revoked", ["child", "module", "options", "backup", "generation"])
async def test_inflight_fetch_rechecks_scope_after_io_before_any_cache_or_notice_write(
    engine, store, now, when, revoked
):
    engine, options = await prepared(engine, store, now, notifications=True, changes=True)
    provider, current_options, paused = Provider(), deepcopy(options), False
    after_mutation = None

    async def change():
        nonlocal paused, after_mutation
        if revoked == "options":
            current_options["revision"] += 1
        elif revoked == "backup":
            paused = True
        else:

            def mutate(ctx):
                if revoked == "child":
                    ctx.state["members"]["child"].update(active=False, revision=2)
                elif revoked == "module":
                    ctx.state["settings"]["modules"].remove("school")
                else:
                    ctx.state["school"]["online"]["sources"][SOURCE]["generation"] = "new-review"

            await engine.system_update("external-change", now, mutate)
        after_mutation = engine.snapshot(), store.calls

    setattr(provider, "on_" + when, change)
    await poll(
        engine, options, now, provider, current=lambda: current_options, paused=lambda: paused
    )
    assert engine.snapshot() == after_mutation[0] and store.calls == after_mutation[1]
    assert provider.closed == [0] and events(engine) == []


@pytest.mark.parametrize(
    "error,code",
    [
        (DomainError("online_school_auth_failed"), "online_school_auth_failed"),
        (DomainError("unknown_provider_detail"), "online_school_invalid_response"),
        (OSError("SYNTHETIC-PRIVATE-REMOTE-DETAIL"), "online_school_unavailable"),
        (TimeoutError(), "online_school_timeout"),
    ],
)
async def test_fetch_failure_closes_client_and_preserves_last_good_cache(
    engine, store, now, error, code
):
    engine, options = await prepared(engine, store, now)
    provider = Provider()
    await poll(engine, options, now, provider)
    before = source(engine)
    provider.error = error
    failed_at = now + timedelta(minutes=15)
    await poll(engine, options, failed_at, provider)
    current = source(engine)
    assert current["status"] == code
    assert current["last_attempt"] == failed_at.isoformat()
    assert (
        current["snapshot"] == before["snapshot"]
        and current["last_success"] == before["last_success"]
    )
    assert provider.closed == [0, 1]
    assert "SYNTHETIC-PRIVATE-REMOTE-DETAIL" not in repr(engine.snapshot())
    assert events(engine) == []


@pytest.mark.parametrize("code", ["online_school_auth_failed", "online_school_rate_limited"])
async def test_auth_failure_uses_hour_cadence_without_retrying_on_clock_rollback(
    engine, store, now, code
):
    engine, options = await prepared(engine, store, now)
    provider = Provider()
    provider.error = DomainError(code)
    await poll(engine, options, now, provider)
    writes = store.calls
    for minutes in (-15, 0, 15, 59):
        await poll(engine, options, now + timedelta(minutes=minutes), provider)
    assert store.calls == writes and len(provider.fetches) == 1
    provider.error = None
    await poll(engine, options, now + timedelta(hours=1), provider)
    assert len(provider.fetches) == 2 and source(engine)["status"] == "ready"


@pytest.mark.parametrize(
    "invalid,code",
    [
        ({"student_id": "202"}, "online_school_student_mismatch"),
        ({"timezone": "UTC"}, "online_school_invalid_response"),
        ({"lessons": [{"id": "malformed"}]}, "online_school_invalid_response"),
    ],
)
async def test_rejected_snapshot_records_bounded_failure_and_respects_retry_cadence(
    engine, store, now, invalid, code
):
    engine, options = await prepared(engine, store, now)
    provider = Provider()
    await poll(engine, options, now, provider)
    good = source(engine)
    provider.value.update(invalid)
    failed_at = now + timedelta(minutes=15)
    await poll(engine, options, failed_at, provider)
    current = source(engine)
    assert (
        current["snapshot"] == good["snapshot"] and current["last_success"] == good["last_success"]
    )
    assert current["status"] == code and current["last_attempt"] == failed_at.isoformat()
    writes = store.calls
    await poll(engine, options, failed_at + timedelta(minutes=1), provider)
    assert store.calls == writes and len(provider.fetches) == 2


async def test_cancelled_fetch_closes_transport_without_persisting_failure_or_cache(
    engine, store, now
):
    engine, options = await prepared(engine, store, now)
    provider, started, release = Provider(), asyncio.Event(), asyncio.Event()

    async def block():
        started.set()
        await release.wait()

    provider.on_fetch = block
    before, writes = engine.snapshot(), store.calls
    task = asyncio.create_task(poll(engine, options, now, provider))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.closed == [0]
    assert engine.snapshot() == before and store.calls == writes


async def test_changed_homework_enqueues_opted_in_private_targets_once_across_store_reload(
    engine, store, now
):
    engine, options = await prepared(engine, store, now, notifications=True, changes=True)
    provider = Provider()
    await poll(engine, options, now, provider)
    provider.value["lessons"][0]["homework"] = "Read a different fictional chapter."
    changed_at = now + timedelta(minutes=15)
    await poll(engine, options, changed_at, provider)
    notices = events(engine)
    assert len(notices) == 3 and {item["recipient"] for item in notices} == {
        "owner",
        "parent",
        "child",
    }
    state = engine.snapshot()
    for event in notices:
        assert event["data"]["kind"] == "changes" and event["data"]["private_context"]
        assert delivery.current(state, event, changed_at)
        selected = delivery.targets(state, event, changed_at)
        assert selected == [
            {
                "channel": "telegram",
                "id": state["members"][event["recipient"]]["telegram_id"],
                "language": "en",
            }
        ]
        assert selected[0]["id"] != state["telegram"]["group_id"]
        message = messages.render(event, selected[0], state, changed_at)
        assert message["chat_id"] == selected[0]["id"] and "School update" in message["text"]
        assert SECRET not in repr(event) + repr(message)
    reloaded = Engine(store.value, store.save)
    writes = store.calls
    await poll(reloaded, options, changed_at + timedelta(minutes=1), provider)
    assert events(reloaded) == notices and store.calls == writes


async def test_notifications_disabled_preserve_changes_without_queuing_messages(engine, store, now):
    engine, options = await prepared(engine, store, now)
    provider = Provider()
    await poll(engine, options, now, provider)
    provider.value["lessons"][0]["homework"] = "Changed private work."
    await poll(engine, options, now + timedelta(minutes=15), provider)
    assert source(engine)["changes"] and events(engine) == []


async def test_preparation_digest_uses_local_clock_and_one_durable_marker_per_day(
    engine, store, now
):
    engine, options = await prepared(engine, store, now, notifications=True)
    provider = Provider()
    before_time = now.replace(hour=14, minute=59)  # 17:59 in Europe/Kyiv.
    await poll(engine, options, before_time, provider)
    assert events(engine) == []
    due = before_time + timedelta(minutes=1)
    await poll(engine, options, due, provider)
    notices = events(engine)
    assert len(notices) == 3 and {item["data"]["date"] for item in notices} == {"2026-09-07"}
    assert len(provider.fetches) == 1  # Digest uses the fresh cache independently of polling.
    await poll(Engine(store.value, store.save), options, due + timedelta(minutes=1), provider)
    assert len(store.value["outbox"]) == 3
    assert not delivery.current(engine.snapshot(), notices[0], due + timedelta(days=1))


@pytest.mark.parametrize("revoke", ["child", "source", "rules", "recipient", "chat", "module"])
async def test_queued_notifications_recheck_source_identity_recipient_and_private_chat(
    engine, store, now, revoke
):
    due = now.replace(hour=15)
    engine, options = await prepared(engine, store, due, notifications=True)
    await poll(engine, options, due, Provider())
    event = next(item for item in events(engine) if item["recipient"] == "parent")
    state = engine.snapshot()
    original_target = delivery.targets(state, event, due)[0]
    if revoke == "child":
        state["members"]["child"]["revision"] += 1
    elif revoke == "source":
        state["school"]["online"]["sources"][SOURCE]["generation"] = "new-generation"
    elif revoke == "rules":
        state["school"]["online"]["sources"][SOURCE]["rules"]["enabled"] = False
    elif revoke == "recipient":
        state["members"]["parent"].update(role="adult", revision=2)
    elif revoke == "chat":
        state["members"]["parent"]["telegram_id"] = 987659999
    else:
        state["settings"]["modules"].remove("school")
    assert delivery.targets(state, event, due) == []
    with pytest.raises(DeliveryError):
        messages.render(event, original_target, state, due)


async def test_generic_notification_transport_routes_school_events_privately_and_deduplicates(
    engine, store, now
):
    due = now.replace(hour=15)
    engine, options = await prepared(engine, store, due, notifications=True)
    await poll(engine, options, due, Provider())
    sent = []

    async def send(event, target):
        message = render(event, target, engine.snapshot(), now=due)
        sent.append(message)
        return f"synthetic-{len(sent)}"

    transport = Notifications(
        engine, lambda event, state: targets(event, state), send, clock=lambda: due
    )
    await transport.run(due)
    await transport.run(due)
    assert len(sent) == 3
    assert {item["chat_id"] for item in sent} == {987650001, 987650002, 987650003}
    assert all(event["state"] == "sent" for event in events(engine))


async def test_native_telegram_bot_target_metadata_does_not_reject_a_current_private_notice(
    engine, store, now
):
    due = now.replace(hour=15)
    engine, options = await prepared(engine, store, due, notifications=True)
    await poll(engine, options, due, Provider())
    event = events(engine)[0]
    # TelegramManager._targets decorates each real targets() result with bot_id.
    # _send_notification then passes that same target to telegram.messages.render.
    target = {**targets(event, engine.snapshot())[0], "bot_id": 123456789}
    message = render(event, target, engine.snapshot(), now=due)
    assert message["chat_id"] == target["id"]
    assert "Preparation for lessons" in message["text"]


async def test_queued_preparation_survives_a_newer_successful_refresh_before_delivery(
    engine, store, now
):
    due = now.replace(hour=15)
    engine, options = await prepared(engine, store, due, notifications=True)
    provider = Provider()
    await poll(engine, options, due, provider)
    notices = events(engine)
    later = due + timedelta(minutes=15)
    await poll(engine, options, later, provider)
    assert events(engine) == notices  # The new snapshot is unchanged; no new notice is needed.
    assert all(delivery.current(engine.snapshot(), event, later) for event in notices)
    sent = []

    async def send(event, target):
        sent.append(render(event, target, engine.snapshot(), now=later))
        return f"synthetic-{len(sent)}"

    assert await Notifications(engine, targets, send, clock=lambda: later).run(later) == 3
    assert len(sent) == 3


@pytest.mark.parametrize("change", ["cancelled", "removed"])
async def test_queued_preparation_is_revoked_when_refresh_removes_last_active_lesson(
    engine, store, now, change
):
    due = now.replace(hour=15)
    engine, options = await prepared(engine, store, due, notifications=True)
    provider = Provider()
    await poll(engine, options, due, provider)
    notices = events(engine)
    assert len(notices) == 3
    original_targets = [targets(event, engine.snapshot())[0] for event in notices]
    if change == "cancelled":
        provider.value["lessons"][0]["cancelled"] = True
    else:
        provider.value["lessons"] = []
    later = due + timedelta(minutes=15)
    await poll(engine, options, later, provider)
    assert source(engine)["status"] == "ready" and events(engine) == notices
    state = engine.snapshot()
    for event, target in zip(notices, original_targets, strict=True):
        assert not delivery.current(state, event, later)
        assert targets(event, state) == []
        with pytest.raises(DeliveryError, match="delivery_revoked"):
            render(event, target, state, now=later)
    sent = []

    async def send(event, target):
        sent.append((event, target))
        return "synthetic-receipt"

    assert await Notifications(engine, targets, send, clock=lambda: later).run(later) == 0
    assert sent == [] and all(event["state"] == "superseded" for event in events(engine))


async def test_private_school_delivery_is_revoked_after_the_persisted_claim(engine, store, now):
    due = now.replace(hour=15)
    original, options = await prepared(engine, store, due, notifications=True)
    await poll(original, options, due, Provider())

    class ClaimGate(Engine):
        async def system_update(self, kind, when, change, **kwargs):
            result = await super().system_update(kind, when, change, **kwargs)
            if kind == "outbox_claim" and result is not None:
                claimed.set()
                await release.wait()
            return result

    claimed, release, sent = asyncio.Event(), asyncio.Event(), []
    engine = ClaimGate(original.snapshot(), store.save)

    async def send(event, target):
        sent.append((event, target))
        return "synthetic-receipt"

    running = asyncio.create_task(Notifications(engine, targets, send, clock=lambda: due).run(due))
    await asyncio.wait_for(claimed.wait(), timeout=2)
    await engine.system_update(
        "revoke-child", due, lambda ctx: ctx.state["members"]["child"].update(revision=2)
    )
    release.set()
    assert await asyncio.wait_for(running, timeout=2) == 0
    assert sent == [] and all(item["state"] == "superseded" for item in events(engine))


async def test_manager_does_not_overlap_requests_and_stop_cancels_its_pending_job(monkeypatch, now):
    started, release, calls = asyncio.Event(), asyncio.Event(), []

    async def blocked(engine, options, when, **kwargs):
        calls.append(when)
        started.set()
        await release.wait()

    monkeypatch.setattr(manager, "poll", blocked)
    runtime = SimpleNamespace(engine=object(), health={}, updated=lambda: None)
    entry = SimpleNamespace(options={"online_school": {"revision": 1, "sources": {}}})
    hass = SimpleNamespace(
        data={}, async_create_background_task=lambda coro, name: asyncio.create_task(coro)
    )
    worker = manager.SchoolManager(hass, entry, runtime)
    worker.request(now)
    await started.wait()
    first = worker.task
    worker.request(now + timedelta(minutes=1))
    assert worker.task is first and calls == [now]
    await worker.stop()
    assert first.cancelled() and worker.task is None
    assert runtime.health == {}


@pytest.fixture
def runtime_adapter(monkeypatch, now):
    """Import actual runtime.py; replace only its HA framework imports and timer worker."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    const, core = ModuleType("homeassistant.const"), ModuleType("homeassistant.core")
    const.Platform = SimpleNamespace(
        SENSOR="sensor", CONVERSATION="conversation", CALENDAR="calendar"
    )
    core.SupportsResponse = SimpleNamespace(OPTIONAL="optional", ONLY="only")
    core.callback = lambda value: value
    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    helpers, storage = (
        ModuleType("homeassistant.helpers"),
        ModuleType("homeassistant.helpers.storage"),
    )
    helpers.__path__ = []
    storage.Store = type("Store", (), {})
    util, dt = ModuleType("homeassistant.util"), ModuleType("homeassistant.util.dt")
    dt.utcnow = lambda: now
    util.dt = dt
    for module in (homeassistant, const, core, exceptions, helpers, storage, util, dt):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    name = "custom_components.family_assistant.runtime"
    path = Path(__file__).resolve().parents[1] / "custom_components/family_assistant/runtime.py"
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    spec.loader.exec_module(loaded)
    workers = []

    class Worker:
        def __init__(self, hass, entry, runtime):
            self.started = False
            self.stopped = False
            self.engine = runtime.engine
            workers.append(self)

        def start(self):
            self.started = True

        async def stop(self):
            self.stopped = True

    monkeypatch.setattr(manager, "SchoolManager", Worker)
    return loaded, workers


def wiring(engine, options):
    runtime = SimpleNamespace(
        engine=engine,
        online_school=None,
        options_lock=asyncio.Lock(),
        module_task=None,
        health={},
        updated=lambda: None,
    )
    runtime.module_signature = signature(runtime)
    entry = SimpleNamespace(
        entry_id="synthetic-school",
        runtime_data=runtime,
        options={"online_school": deepcopy(options)},
    )
    hass = SimpleNamespace(data={"family_assistant": {"entries": {entry.entry_id: runtime}}})
    return hass, entry, runtime


async def test_native_runtime_reconciles_reviewed_options_before_starting_worker(
    runtime_adapter, engine, store, now
):
    adapter, workers = runtime_adapter
    configured, options = await prepared(engine, store, now)
    state = configured.snapshot()
    state["school"].pop("online")
    engine = Engine(state, store.save)
    hass, entry, runtime = wiring(engine, options)
    await adapter.async_configure_online_school(hass, entry)
    assert len(workers) == 1 and workers[0].started
    assert runtime.online_school is workers[0]
    assert source(engine)["generation"] == options["sources"][SOURCE]["generation"]
    assert SECRET not in repr(engine.snapshot())
    writes = store.calls
    await adapter.async_configure_online_school(hass, entry)
    assert workers[0].stopped and workers[1].started and store.calls == writes


async def test_native_runtime_stops_worker_and_does_not_start_disabled_school(
    runtime_adapter, engine, store, now
):
    adapter, workers = runtime_adapter
    engine, options = await prepared(engine, store, now)
    hass, entry, runtime = wiring(engine, options)
    await adapter.async_configure_online_school(hass, entry)
    await engine.system_update(
        "disable-school", now, lambda ctx: ctx.state["settings"]["modules"].remove("school")
    )
    before, writes = engine.snapshot(), store.calls
    await adapter.async_configure_online_school(hass, entry)
    assert workers[0].stopped and len(workers) == 1 and runtime.online_school is None
    assert engine.snapshot() == before and store.calls == writes


async def test_canonical_module_switch_reconciles_school_worker_without_full_reload(
    runtime_adapter, engine, store, now
):
    adapter, workers = runtime_adapter
    engine, options = await prepared(engine, store, now)
    hass, entry, runtime = wiring(engine, options)
    await adapter.async_configure_online_school(hass, entry)
    await engine.system_update(
        "disable-school", now, lambda ctx: ctx.state["settings"]["modules"].remove("school")
    )
    await reconcile(hass, entry, runtime)
    assert workers[0].stopped and runtime.online_school is None
    await engine.system_update(
        "enable-school", now, lambda ctx: ctx.state["settings"]["modules"].append("school")
    )
    await reconcile(hass, entry, runtime)
    assert len(workers) == 2 and workers[1].started and runtime.online_school is workers[1]
