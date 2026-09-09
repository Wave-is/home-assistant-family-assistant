"""Actual Engine and notification runner with synthetic new-device observations."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_network_admission import CLIENT, setup

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.admission_inventory import observation_token
from custom_components.family_assistant.network.watch import ACTION, INCIDENT_KEY, KEY, current
from custom_components.family_assistant.notifications import Notifications
from custom_components.family_assistant.telegram.messages import render, targets
from custom_components.family_assistant.telegram.router import route

NEW = "02:11:22:33:44:77"
NEXT = "02:11:22:33:44:88"


async def prepared(engine, now):
    await setup(engine, now)

    def link(ctx):
        ctx.state["members"]["parent"]["telegram_id"] = 850001
        ctx.state["telegram"]["group_id"] = -850099

    await engine.system_update("synthetic-watch-parent", now, link)
    return engine


def payload(e, now, **changes):
    return {
        "actor_revision": 1,
        "watch_revision": None,
        "enabled": True,
        "min_interval_minutes": 30,
        "observation_token": observation_token(e.snapshot()["network"], now),
        **changes,
    }


async def observe(e, now, *macs):
    def change(ctx):
        inventory = ctx.state["network"]["inventory"]
        inventory["observed_at"] = now.isoformat()
        for address in macs:
            if not any(row["mac"] == address for row in inventory["devices"]):
                inventory["devices"].append(
                    {
                        "mac": address,
                        "addresses": ["198.51.100.12"],
                        "suggested_name": "Synthetic discovery",
                        "warnings": [],
                    }
                )

    await e.system_update("synthetic-observation", now, change)


def events(e):
    return [event for event in e.snapshot()["outbox"].values() if event["key"] == KEY]


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["missing", "negative", "bool", "duplicate", "group"])
async def test_private_channel_projection_matches_enable_authorization(engine, now, drift):
    from custom_components.family_assistant.network.watch import public

    e = await prepared(engine, now)

    def change(ctx):
        member = ctx.state["members"]["parent"]
        if drift in {"missing", "negative", "bool"}:
            member["telegram_id"] = {"missing": None, "negative": -850001, "bool": True}[drift]
        elif drift == "duplicate":
            ctx.state["members"]["owner"]["telegram_id"] = member["telegram_id"]
        else:
            ctx.state["telegram"]["group_id"] = member["telegram_id"]

    await e.system_update("synthetic-invalid-channel", now, change)
    assert public(e.snapshot(), "parent")["private_chat_ready"] is False
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "invalid-channel", now)


@pytest.mark.asyncio
async def test_off_default_initial_baseline_one_new_batch_repeated_poll_and_reload(
    engine, store, now
):
    e = await prepared(engine, now)
    await e.tick(now)
    assert not events(e)
    request = payload(e, now)
    result = await e.execute("parent", f"mikrotik.{ACTION}", request, "subscribe", now)
    assert result == {"watch_revision": 1, "enabled": True}
    before = e.snapshot()
    assert await e.execute("parent", f"mikrotik.{ACTION}", request, "subscribe", now) == result
    assert e.snapshot() == before
    await e.tick(now)
    assert not events(e)  # Existing CLIENT is not announced as new.
    later = now + timedelta(seconds=30)
    await observe(e, later, NEW)
    await e.tick(later)
    assert len(events(e)) == 1 and events(e)[0]["data"]["macs"] == [NEW]
    assert CLIENT not in events(e)[0]["data"]["macs"]
    restored = Engine(deepcopy(store.value), store.save)
    await observe(restored, later + timedelta(seconds=30), NEW)
    await restored.tick(later + timedelta(seconds=30))
    assert len(events(restored)) == 1
    assert restored.snapshot()["network"]["tables"] == before["network"]["tables"]
    assert restored.snapshot()["network"]["admission_watches"]["parent"]["seen"] == sorted(
        [*before["network"]["admission_watches"]["parent"]["seen"], NEW]
    )


@pytest.mark.asyncio
async def test_batch_cooldown_accumulates_new_rows_without_repeating_old_batch(engine, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW)
    await e.tick(now)
    await observe(e, now + timedelta(minutes=1), NEXT)
    await e.tick(now + timedelta(minutes=1))
    assert len(events(e)) == 1
    assert e.snapshot()["network"]["admission_watches"]["parent"]["pending"] == [NEXT]
    await observe(e, now + timedelta(minutes=30), NEXT)
    await e.tick(now + timedelta(minutes=30))
    assert len(events(e)) == 2 and events(e)[1]["data"]["macs"] == [NEXT]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    [
        "module",
        "role",
        "epoch",
        "chat",
        "duplicate_chat",
        "backend",
        "disabled",
        "approved",
        "stale",
        "expired",
        "group",
    ],
)
async def test_dispatch_revokes_private_details_on_current_authority_or_source_change(
    engine, now, drift
):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW)
    await e.tick(now)
    event = events(e)[0]
    state = e.snapshot()
    assert current(state, event, now)
    assert targets(event, state) == [
        {"channel": "telegram", "id": 850001, "language": state["members"]["parent"]["language"]}
    ]
    message = render(event, {**targets(event, state)[0], "bot_id": 850002}, state, now=now)
    assert NEW in message["text"] and CLIENT not in message["text"]

    def change(ctx):
        if drift == "module":
            ctx.state["settings"]["modules"].remove("mikrotik")
        if drift == "role":
            ctx.state["members"]["parent"]["role"] = "child"
        if drift == "epoch":
            ctx.state["members"]["parent"]["revision"] += 1
        if drift == "chat":
            ctx.state["members"]["parent"]["telegram_id"] = 850003
        if drift == "duplicate_chat":
            ctx.state["members"]["owner"]["telegram_id"] = 850001
        if drift == "backend":
            ctx.state["network"]["backend"] = "c" * 64
        if drift == "disabled":
            ctx.state["network"]["admission_watches"]["parent"]["enabled"] = False
        if drift == "approved":
            ctx.state["network"]["admission"] = {
                "backend": "a" * 64,
                "revision": 1,
                "updated_at": now.isoformat(),
                "entries": {NEW: {"label": "Reviewed"}},
            }
        if drift == "group":
            ctx.state["telegram"]["group_id"] = 850001

    await e.system_update("synthetic-revoke", now, change)
    check_at = now + timedelta(minutes=4 if drift == "stale" else 61 if drift == "expired" else 0)
    if drift == "expired":
        await observe(e, check_at, NEW)
    assert not current(e.snapshot(), event, check_at)
    sent = []

    async def send(event, target):
        sent.append((event, target))
        return "synthetic-message"

    await Notifications(e, targets, send).run(check_at)
    assert not sent


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["child", "adult", "guest"])
async def test_only_current_parent_may_subscribe_self(engine, now, role):
    e = await prepared(engine, now)
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(role, f"mikrotik.{ACTION}", payload(e, now), f"deny-{role}", now)


@pytest.mark.asyncio
async def test_delivery_survives_newer_fresh_poll_but_never_sends_to_group(engine, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW)
    await e.tick(now)
    later = now + timedelta(minutes=2)
    await observe(e, later, NEW)
    sent = []

    async def send(event, target):
        sent.append(render(event, target, e.snapshot(), now=later))
        return "synthetic-message"

    assert await Notifications(e, targets, send).run(later) == 1
    assert len(sent) == 1 and sent[0]["chat_id"] == 850001 and NEW in sent[0]["text"]
    assert await Notifications(e, targets, send).run(later) == 0


@pytest.mark.asyncio
async def test_failed_store_does_not_consume_discovery_or_duplicate_intent(engine, store, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW)
    before = e.snapshot()
    original = e._persist

    async def fail(_state):
        raise OSError("synthetic Store failure")

    e._persist = fail
    with pytest.raises(OSError):
        await e.tick(now)
    assert e.snapshot() == before and not events(e)
    e._persist = original
    await e.tick(now)
    assert len(events(e)) == 1


@pytest.mark.asyncio
async def test_changed_router_stays_paused_until_new_explicit_baseline(engine, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)

    def replace(ctx):
        ctx.state["network"]["backend"] = "b" * 64

    await e.system_update("synthetic-router-replacement", now, replace)
    await observe(e, now, NEW)
    await e.tick(now)
    assert not events(e)
    view = e.view("parent", now=now)["network"]["admission"]["watch"]
    assert view["enabled"] is True and view["effective"] is False
    await e.execute(
        "parent", f"mikrotik.{ACTION}", payload(e, now, watch_revision=1), "new-baseline", now
    )
    await e.tick(now)
    assert not events(e)  # Device existing when source consent was renewed is baseline.
    await observe(e, now, NEXT)
    await e.tick(now)
    assert events(e)[0]["data"]["macs"] == [NEXT]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "ru", "uk"])
async def test_private_telegram_subscription_replay_off_and_group_no_mutation(
    engine, now, language
):
    from custom_components.family_assistant.telegram.context import PersonalReply
    from custom_components.family_assistant.telegram.watch_messages import COMMAND_COPY

    e = await prepared(engine, now)

    def localize(ctx):
        ctx.state["members"]["parent"]["language"] = language

    await e.system_update("synthetic-language", now, localize)
    before = e.snapshot()
    await route(e, "parent", "/network_alerts on", "group-subscribe", now)
    assert e.snapshot() == before
    first = await route(e, "parent", "/network_alerts on", "private-subscribe", now, private=True)
    assert isinstance(first, PersonalReply) and first == COMMAND_COPY[language]["on"]
    before = e.snapshot()
    assert (
        await route(e, "parent", "/network_alerts on", "private-subscribe", now, private=True)
        == first
    )
    assert e.snapshot() == before
    assert await route(e, "parent", "/network_alerts on", "already-on", now, private=True) == first
    assert e.snapshot() == before
    off = await route(e, "parent", "/network_alerts off", "private-off", now, private=True)
    assert off == COMMAND_COPY[language]["off"]
    assert not e.snapshot()["network"]["admission_watches"]["parent"]["enabled"]


@pytest.mark.asyncio
async def test_quiet_backlog_is_paced_at_actual_dispatch_not_only_event_creation(engine, now):
    e = await prepared(engine, now)
    await e.execute(
        "parent", f"mikrotik.{ACTION}", payload(e, now, min_interval_minutes=5), "subscribe", now
    )
    await observe(e, now, NEW)
    await e.tick(now)
    later = now + timedelta(minutes=5)
    await observe(e, later, NEXT)
    await e.tick(later)
    assert len(events(e)) == 2
    sent = []

    async def send(event, target):
        sent.append(event["id"])
        return "synthetic-message"

    worker = Notifications(e, targets, send)
    assert await worker.run(later) == 1
    assert await worker.run(later + timedelta(seconds=2)) == 0
    await observe(e, later + timedelta(minutes=5))
    assert await worker.run(later + timedelta(minutes=5)) == 1
    assert len(sent) == len(set(sent)) == 2


@pytest.mark.asyncio
async def test_long_quiet_period_keeps_markers_without_expiring_first_discovery(engine, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)

    def quiet(ctx):
        ctx.state["settings"]["notifications"] = {
            "quiet_enabled": True,
            "quiet_start": "08:00",
            "quiet_end": "10:00",
            "timezone": "UTC",
        }

    await e.system_update("synthetic-quiet", now, quiet)
    await observe(e, now, NEW)
    await e.tick(now)
    assert not events(e)
    assert e.snapshot()["network"]["admission_watches"]["parent"]["pending"] == [NEW]
    morning = now + timedelta(hours=2)
    await observe(e, morning)
    await e.tick(morning)
    assert events(e)[0]["data"]["macs"] == [NEW]
    assert current(e.snapshot(), events(e)[0], morning)


@pytest.mark.asyncio
async def test_pretransport_revocation_releases_gate_but_never_sends(engine, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW)
    await e.tick(now)
    sent = []

    async def send(event, target):
        sent.append(event)
        return "synthetic-message"

    worker = Notifications(e, targets, send)
    claimed = await e.system_update("synthetic-claim", now, worker._claim)
    assert e.snapshot()["network"]["admission_watches"]["parent"]["delivery_gate"]

    def approve(ctx):
        ctx.state["network"]["admission"] = {
            "backend": "a" * 64,
            "revision": 1,
            "updated_at": now.isoformat(),
            "entries": {NEW: {"label": "Reviewed"}},
        }

    await e.system_update("synthetic-approval", now, approve)
    assert await worker._authorize_dispatch(claimed[0]["id"], claimed[1]["id"], now) is None
    assert e.snapshot()["network"]["admission_watches"]["parent"]["delivery_gate"] is None
    assert not sent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"actor_revision": True},
        {"watch_revision": True},
        {"enabled": 1},
        {"min_interval_minutes": True},
        {"min_interval_minutes": 4},
        {"min_interval_minutes": 1441},
        {"min_interval_minutes": 5.2},
        {"unexpected": "field"},
    ],
)
async def test_subscription_rejects_malformed_fields_atomically(engine, now, bad):
    e = await prepared(engine, now)
    before = e.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now, **bad), "bad-watch", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_partial_approval_filters_details_and_source_aba_stays_revoked(engine, now):
    from custom_components.family_assistant.network.watch import observe_backend

    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW, NEXT)
    await e.tick(now)
    event = events(e)[0]

    def approve(ctx):
        ctx.state["network"]["admission"] = {
            "backend": "a" * 64,
            "revision": 1,
            "updated_at": now.isoformat(),
            "entries": {NEW: {"label": "Reviewed"}},
        }

    await e.system_update("synthetic-partial-review", now, approve)
    state = e.snapshot()
    assert current(state, event, now)
    message = render(event, targets(event, state)[0], state, now=now)
    assert NEXT in message["text"] and NEW not in message["text"]

    def switch(ctx):
        ctx.state["network"]["backend"] = "b" * 64
        observe_backend(ctx.state, "b" * 64)
        ctx.state["network"]["backend"] = "a" * 64
        observe_backend(ctx.state, "a" * 64)

    await e.system_update("synthetic-source-aba", now, switch)
    assert not current(e.snapshot(), event, now)
    assert not e.view("parent", now=now)["network"]["admission"]["watch"]["effective"]


@pytest.mark.asyncio
async def test_capacity_stop_preserves_markers_and_explicit_reset_makes_new_baseline(engine, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW)
    await e.tick(now)

    def fill(ctx):
        record = ctx.state["network"]["admission_watches"]["parent"]
        record["seen"] += [
            f"02:30:{(i >> 24) & 255:02X}:{(i >> 16) & 255:02X}:{(i >> 8) & 255:02X}:{i & 255:02X}"
            for i in range(10_000 - len(record["seen"]))
        ]

    await e.system_update("synthetic-full-history", now, fill)
    before = e.snapshot()["network"]["admission_watches"]["parent"]["seen"]
    await observe(e, now, NEXT)
    await e.tick(now)
    record = e.snapshot()["network"]["admission_watches"]["parent"]
    assert record["seen"] == before and record["capacity_blocked"] is True
    assert len(events(e)) == 1 and not current(e.snapshot(), events(e)[0], now)
    await e.execute(
        "parent", f"mikrotik.{ACTION}", payload(e, now, watch_revision=1), "review-reset", now
    )
    await e.tick(now)
    assert not e.snapshot()["network"]["admission_watches"]["parent"]["capacity_blocked"]
    assert len(events(e)) == 1  # Reset does not announce existing observations.


@pytest.mark.asyncio
async def test_uncertain_transport_is_not_blindly_retried_or_rediscovered(engine, now):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)
    await observe(e, now, NEW)
    await e.tick(now)
    calls = []

    async def send(event, target):
        calls.append(event["id"])
        raise TimeoutError("synthetic unknown outcome")

    worker = Notifications(e, targets, send)
    assert await worker.run(now) == 1
    assert events(e)[0]["state"] == "uncertain"
    await observe(e, now + timedelta(minutes=2), NEW)
    await e.tick(now + timedelta(minutes=2))
    assert await worker.run(now + timedelta(minutes=2)) == 0
    assert len(calls) == 1 and len(events(e)) == 1


@pytest.mark.asyncio
async def test_old_subscribe_command_does_not_undo_later_withdrawal(engine, now):
    e = await prepared(engine, now)
    await route(e, "parent", "/network_alerts on", "subscribe", now, private=True)
    await route(e, "parent", "/network_alerts off", "withdraw", now, private=True)
    before = e.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await route(e, "parent", "/network_alerts on", "subscribe", now, private=True)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_network_watch_incident_lifecycle_opens_persists_and_closes_with_cleared_notification(
    engine, now
):
    e = await prepared(engine, now)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)

    # 1. New unreviewed device arrives: opens incident and enqueues alert
    await observe(e, now, NEW)
    await e.tick(now)
    snap1 = e.snapshot()
    incident = snap1["incidents"].get("network_watch:parent")
    assert incident is not None
    assert incident["state"] == "open"
    assert incident["macs"] == [NEW]
    assert len(events(e)) == 1

    # 2. Device still unreviewed on next tick: incident stays open, no duplicate alert
    later = now + timedelta(minutes=5)
    await observe(e, later, NEW)
    await e.tick(later)
    snap2 = e.snapshot()
    incident2 = snap2["incidents"].get("network_watch:parent")
    assert incident2["state"] == "open"
    assert incident2["macs"] == [NEW]

    # 3. Device reviewed (approved via admission entries):
    # incident closes and emits cleared notification
    def approve(ctx):
        ctx.state["network"]["admission"] = {
            "backend": ctx.state["network"]["backend"],
            "revision": 1,
            "entries": {NEW: {"label": "Approved Device"}},
            "updated_at": later.isoformat(),
        }

    await e.system_update("approve-new-device", later, approve)
    review_time = later + timedelta(minutes=1)
    await observe(e, review_time, NEW)
    await e.tick(review_time)

    snap3 = e.snapshot()
    incident3 = snap3["incidents"].get("network_watch:parent")
    assert incident3["state"] == "closed"
    assert incident3["macs"] == []

    cleared_events = [ev for ev in snap3["outbox"].values() if ev["key"] == INCIDENT_KEY]
    assert len(cleared_events) == 1
    cleared = cleared_events[0]
    assert cleared["recipient"] == "parent"

    # Verify rendering across locales
    for lang in ("en", "ru", "uk"):
        target = {"channel": "telegram", "id": 850001, "language": lang, "bot_id": 850002}
        msg = render(cleared, target, snap3, now=review_time)
        assert "✅" in msg["text"]

    # 4. Subsequent tick: no duplicate closure notification
    after_time = review_time + timedelta(minutes=5)
    await observe(e, after_time, NEW)
    await e.tick(after_time)
    snap4 = e.snapshot()
    assert len([ev for ev in snap4["outbox"].values() if ev["key"] == INCIDENT_KEY]) == 1


@pytest.mark.asyncio
async def test_network_watch_quiet_hours_unannounced_incident_closes_silently_on_review(
    engine, now
):
    e = await prepared(engine, now)

    # Enable quiet hours covering 08:00
    def set_quiet(ctx):
        ctx.state["settings"]["notifications"] = {
            "quiet_enabled": True,
            "quiet_start": "07:00",
            "quiet_end": "09:00",
            "timezone": "UTC",
        }

    await e.system_update("quiet-policy", now, set_quiet)
    await e.execute("parent", f"mikrotik.{ACTION}", payload(e, now), "subscribe", now)

    # Device arrives during quiet hours: incident is opened, but no alert dispatched
    await observe(e, now, NEW)
    await e.tick(now)
    snap = e.snapshot()
    assert not events(e)  # No alert due to quiet hours
    inc = snap["incidents"].get("network_watch:parent")
    assert inc is not None and inc["state"] == "open"

    # Device is reviewed before quiet hours expire
    def approve(ctx):
        ctx.state["network"]["admission"] = {
            "backend": ctx.state["network"]["backend"],
            "revision": 1,
            "entries": {NEW: {"label": "Approved In Quiet"}},
            "updated_at": now.isoformat(),
        }

    await e.system_update("approve-in-quiet", now, approve)
    later = now + timedelta(minutes=5)
    await observe(e, later, NEW)
    await e.tick(later)

    snap2 = e.snapshot()
    inc2 = snap2["incidents"].get("network_watch:parent")
    assert inc2["state"] == "closed"
    # Never announced -> no cleared notification sent
    assert not [ev for ev in snap2["outbox"].values() if ev["key"] == INCIDENT_KEY]
