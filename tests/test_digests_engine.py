"""Digest consent and scheduling through real Engine transactions."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain import digest_settings, digests
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 7, 7, 2, tzinfo=UTC)
CANARY = "DIGEST-PRIVATE-REPORT-CANARY-5d2a"


@pytest.fixture
def digest_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"] = ["tasks", "calendar", "digests"]
    state["settings"].update(
        timezone="UTC",
        digest_policy_revision=1,
        digest_morning_enabled=True,
        digest_morning_time="07:00",
        digest_evening_enabled=False,
        digest_evening_time="19:00",
        digest_weekly_enabled=False,
        digest_weekly_weekday=6,
        digest_weekly_time="18:00",
    )
    state["tasks"] = {
        "T1": {
            "id": "T1",
            "revision": 1,
            "title": "Current child task",
            "assignee": "child",
            "assignee_revision": state["members"]["child"]["revision"],
            "creator": "owner",
            "status": "assigned",
            "due_at": "2026-09-07T12:00:00+00:00",
            "created_at": "2026-09-06T07:00:00+00:00",
            "report_type": "text",
            "report": CANARY,
            "previous_reports": [{"report": CANARY}],
            "checklist": [],
        },
        "T2": {
            "id": "T2",
            "revision": 1,
            "title": "Sibling title",
            "assignee": "sibling",
            "assignee_revision": state["members"]["sibling"]["revision"],
            "creator": "owner",
            "status": "assigned",
            "due_at": "2026-09-07T13:00:00+00:00",
            "created_at": "2026-09-06T07:00:00+00:00",
            "report_type": "none",
            "report": None,
            "checklist": [],
        },
    }
    return Engine(state, store.save)


def consent(engine, actor="child", *, current=None, **changes):
    state = engine.snapshot()
    return {
        "recipient_revision": state["members"][actor]["revision"],
        "subscription_revision": current,
        "morning": True,
        "evening": False,
        "weekly": False,
        **changes,
    }


async def subscribe(engine, operation="digest-consent", actor="child", **changes):
    return await engine.execute(
        actor,
        "digests.access_set",
        consent(engine, actor, **changes),
        operation,
        NOW,
    )


def policy_payload(engine, **changes):
    state = engine.snapshot()
    return {
        "actor_revision": state["members"]["owner"]["revision"],
        "policy_fingerprint": digest_settings.fingerprint(state),
        **digest_settings.values(state),
        **changes,
    }


@pytest.mark.asyncio
async def test_self_consent_projection_is_opaque_and_never_lists_other_subscriptions(
    digest_engine,
):
    child = await subscribe(digest_engine)
    parent = await subscribe(digest_engine, "parent-consent", "parent")
    assert child == parent == {"revision": 1, "status": "enabled"}
    child_view = digest_engine.view("child", now=NOW)["digests"]
    assert child_view["self"] == {
        "recipient_revision": 1,
        "subscription_revision": 1,
        "morning": True,
        "evening": False,
        "weekly": False,
        "can_edit": True,
        "health": "ok",
    }
    assert "parent" not in json.dumps(child_view)
    assert set(digest_engine.snapshot()["digest_subscriptions"]) == {"child", "parent"}
    assert digest_engine.view("guest", now=NOW).get("digests") is None


@pytest.mark.asyncio
async def test_store_failure_and_batch_failure_publish_no_partial_consent(digest_engine, store):
    before = digest_engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await subscribe(digest_engine)
    assert digest_engine.snapshot() == before
    store.fail = False

    command = {"action": "digests.access_set", "payload": consent(digest_engine)}
    with pytest.raises(DomainError, match="conflict"):
        await digest_engine.execute(
            "child",
            "batch",
            {"commands": [command, deepcopy(command)]},
            "digest-batch",
            NOW,
        )
    assert digest_engine.snapshot() == before


@pytest.mark.asyncio
async def test_exact_replay_survives_restart_but_current_authority_is_rechecked(
    digest_engine, store
):
    request = consent(digest_engine)
    receipt = await digest_engine.execute(
        "child", "digests.access_set", request, "digest-replay", NOW
    )
    restarted = Engine(digest_engine.snapshot(), store.save)
    assert (
        await restarted.execute("child", "digests.access_set", request, "digest-replay", NOW)
        == receipt
    )
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await restarted.execute(
            "child",
            "digests.access_set",
            {**request, "weekly": True},
            "digest-replay",
            NOW,
        )
    state = restarted.snapshot()
    state["members"]["child"]["revision"] += 1
    changed = Engine(state, store.save)
    with pytest.raises(DomainError, match="conflict"):
        await changed.execute("child", "digests.access_set", request, "digest-replay", NOW)
    state = restarted.snapshot()
    state["settings"]["modules"].remove("digests")
    disabled = Engine(state, store.save)
    with pytest.raises(DomainError, match="module_disabled"):
        await disabled.execute("child", "digests.access_set", request, "digest-replay", NOW)


@pytest.mark.asyncio
async def test_concurrent_ticks_and_restart_create_one_content_free_intent(digest_engine, store):
    await subscribe(digest_engine)
    await asyncio.gather(digest_engine.tick(NOW), digest_engine.tick(NOW))
    state = digest_engine.snapshot()
    assert len(state["digest_markers"]) == len(state["outbox"]) == 1
    event = next(iter(state["outbox"].values()))
    assert event["key"] == "family_digest" and event["recipient"] == "child"
    assert set(event["data"]) == digests.EVENT_FIELDS
    encoded = json.dumps(
        {"outbox": state["outbox"], "processed": state["processed"], "audit": state["audit"]}
    )
    assert "Current child task" not in encoded
    assert CANARY not in encoded
    restarted = Engine(state, store.save)
    assert await restarted.tick(NOW + timedelta(minutes=1)) is False
    assert len(restarted.snapshot()["outbox"]) == 1


@pytest.mark.asyncio
async def test_tick_store_failure_is_atomic_and_exact_retry_generates_once(digest_engine, store):
    await subscribe(digest_engine)
    before = digest_engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await digest_engine.tick(NOW)
    assert digest_engine.snapshot() == before
    store.fail = False
    assert await digest_engine.tick(NOW) is True
    assert len(digest_engine.snapshot()["outbox"]) == 1


@pytest.mark.asyncio
async def test_prune_and_retirement_floor_are_atomic_and_survive_restart(digest_engine, store):
    await subscribe(digest_engine)
    await digest_engine.tick(NOW)
    state = digest_engine.snapshot()
    event = next(iter(state["outbox"].values()))
    event["state"] = "sent"
    retiring = Engine(state, store.save)
    old_period = event["data"]["window_start"]
    prune_at = NOW + timedelta(days=40)

    before = retiring.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await retiring.system_update("digest-prune", prune_at, digests.prune)
    assert retiring.snapshot() == before
    assert retiring.snapshot()["digest_retired"] == {}

    store.fail = False
    assert await retiring.system_update("digest-prune", prune_at, digests.prune) == 1
    pruned = retiring.snapshot()
    assert pruned["digest_retired"] == {"morning": old_period}
    assert pruned["digest_markers"] == {}
    assert not any(event.get("key") == "family_digest" for event in pruned["outbox"].values())

    restarted = Engine(pruned, store.save)
    rollback_before = restarted.snapshot()
    assert await restarted.system_update("digest-clock-rollback", NOW, digests.tick) is None
    assert restarted.snapshot() == rollback_before


@pytest.mark.asyncio
async def test_malformed_old_timestamp_cannot_poison_future_retirement_floor(digest_engine, store):
    await subscribe(digest_engine)
    await digest_engine.tick(NOW)
    state = digest_engine.snapshot()
    old_marker_key, marker = next(iter(state["digest_markers"].items()))
    event = state["outbox"][marker["event_id"]]
    future_period = "2099-01-01/morning"
    event["data"].update(
        period_key=future_period,
        window_start="2099-01-01",
        window_end="2099-01-02",
        scheduled_at="2000-01-01T07:00:00+00:00",
        expires_at="2000-01-01T13:00:00+00:00",
    )
    event["created_at"] = "2000-01-01T07:00:00+00:00"
    event["state"] = "sent"
    marker_parts = json.loads(old_marker_key)
    marker_parts[2] = future_period
    state["digest_markers"] = {
        json.dumps(marker_parts, ensure_ascii=False, separators=(",", ":")): marker
    }
    poisoned = Engine(state, store.save)
    before = poisoned.snapshot()

    assert (
        await poisoned.system_update(
            "digest-malformed-retention",
            datetime(2100, 1, 1, tzinfo=UTC),
            digests.prune,
        )
        == 0
    )
    assert poisoned.snapshot() == before
    assert poisoned.snapshot()["digest_retired"] == {}


@pytest.mark.asyncio
async def test_policy_aba_never_revives_old_event_or_cached_policy_receipt(digest_engine):
    await subscribe(digest_engine)
    await digest_engine.tick(NOW)
    old_event = next(iter(digest_engine.snapshot()["outbox"].values()))
    first = policy_payload(digest_engine, digest_morning_time="07:01")
    await digest_engine.execute("owner", "settings.digest_policy", first, "policy-b", NOW)
    assert digests.delivery_allowed(digest_engine.snapshot(), old_event, NOW) is False
    second = policy_payload(digest_engine, digest_morning_time="07:00")
    await digest_engine.execute("owner", "settings.digest_policy", second, "policy-a", NOW)
    state = digest_engine.snapshot()
    assert digest_settings.values(state)["digest_morning_time"] == "07:00"
    assert digests.delivery_allowed(state, old_event, NOW) is False
    with pytest.raises(DomainError, match="conflict"):
        await digest_engine.execute("owner", "settings.digest_policy", first, "policy-b", NOW)


@pytest.mark.asyncio
async def test_source_changes_refresh_content_but_empty_or_revoked_scope_supersedes(
    digest_engine,
):
    await subscribe(digest_engine)
    await digest_engine.tick(NOW)
    event = next(iter(digest_engine.snapshot()["outbox"].values()))
    assert digests.delivery_allowed(digest_engine.snapshot(), event, NOW)

    state = digest_engine.snapshot()
    state["tasks"]["T1"]["title"] = "Fresh title"
    changed = Engine(state, lambda _value: asyncio.sleep(0))
    assert digests.delivery_allowed(changed.snapshot(), event, NOW)
    del state["tasks"]["T1"]
    empty = Engine(state, lambda _value: asyncio.sleep(0))
    assert digests.delivery_allowed(empty.snapshot(), event, NOW) is False
    await empty.tick(NOW + timedelta(minutes=1))
    assert next(iter(empty.snapshot()["outbox"].values()))["state"] == "superseded"


@pytest.mark.asyncio
async def test_role_change_revokes_projection_replay_and_pending_delivery(digest_engine, store):
    request = consent(digest_engine)
    await digest_engine.execute("child", "digests.access_set", request, "role-consent", NOW)
    await digest_engine.tick(NOW)
    state = digest_engine.snapshot()
    state["members"]["child"].update(role="guest", revision=2)
    changed = Engine(state, store.save)
    assert changed.view("child", now=NOW).get("digests") is None
    with pytest.raises(DomainError, match="forbidden"):
        await changed.execute("child", "digests.access_set", request, "role-consent", NOW)
    await changed.tick(NOW + timedelta(minutes=1))
    assert next(iter(changed.snapshot()["outbox"].values()))["state"] == "superseded"
