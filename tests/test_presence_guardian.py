"""Explicit guardian consent through real Engine persistence and authorization."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain import presence
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def setup(engine, store, now, *, child_link=True):
    state = engine.snapshot()
    state["settings"]["modules"].append("presence")
    if not child_link:
        state["members"]["child"]["ha_user_id"] = None
    result = Engine(state, store.save)
    options = {
        "presence_sources": {
            "child": {
                "revision": 1,
                "status": "active",
                "member_revision": 1,
                "entity_id": "person.synthetic_child",
            }
        }
    }
    await result.system_update(
        "guardian-source", now, lambda ctx: presence.sync_bindings(ctx, options)
    )
    return result, options


def payload(**changes):
    return {
        "member": "child",
        "member_revision": 1,
        "binding_revision": 1,
        "subscription_revision": None,
        "enabled": True,
        **changes,
    }


def projection(engine, options, now, actor="parent"):
    state = engine.snapshot()
    return presence.view(
        state,
        state["members"][actor],
        options,
        {"child": {"state": "home", "observed_at": now.isoformat()}},
        now,
    )


def child_row(result):
    return next(row for row in result["managed"] if row["member"] == "child")


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "parent"])
async def test_explicit_guardian_without_child_ha_link_is_opaque_and_durable(
    engine, store, now, actor
):
    e, options = await setup(engine, store, now, child_link=False)
    before = e.snapshot()
    receipt = await e.execute(
        actor, "presence.guardian_access_set", payload(), "guardian-enable", now
    )
    assert receipt == {"member": "child", "revision": 1, "status": "enabled"}
    record = e.snapshot()["presence"]["subscriptions"]["child"]
    assert record["guardian"] == actor and record["guardian_revision"] == 1
    result = projection(e, options, now)
    row = child_row(result)
    assert row["enabled"] and row["consent_kind"] == "guardian" and row["guardian"] == actor
    assert row["status"] == "reported_home"
    assert "person.synthetic_child" not in repr(result)
    assert "source_hash" not in repr(result)
    for key in ("tasks", "outbox", "court", "alarm_runs", "routine_runs"):
        assert e.snapshot()[key] == before[key]
    for viewer in ("owner", "parent", "adult", "child", "guest"):
        ordinary = e.view(viewer, now=now)
        assert "presence" not in ordinary and "presence" not in plans.projection(ordinary)
    assert (
        Engine(deepcopy(store.value), store.save).snapshot()["presence"] == e.snapshot()["presence"]
    )
    state, writes = e.snapshot(), store.calls
    assert (
        await e.execute(actor, "presence.guardian_access_set", payload(), "guardian-enable", now)
        == receipt
    )
    assert e.snapshot() == state and store.calls == writes


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["adult", "child", "sibling", "guest"])
async def test_non_guardian_cannot_manage_child(engine, store, now, actor):
    e, options = await setup(engine, store, now)
    before = e.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(actor, "presence.guardian_access_set", payload(), "denied", now)
    assert e.snapshot() == before
    assert "managed" not in projection(e, options, now, actor)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["adult", "parent", "owner", "guest"])
async def test_guardians_cannot_consent_for_adults_or_guests(engine, store, now, target):
    e, _options = await setup(engine, store, now)
    before = e.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "parent", "presence.guardian_access_set", payload(member=target), "denied", now
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_self_api_is_not_widened_and_child_can_revoke_or_take_over(engine, store, now):
    e, options = await setup(engine, store, now)
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute("parent", "presence.access_set", payload(), "not-self", now)
    await e.execute("parent", "presence.guardian_access_set", payload(), "guardian-enable", now)
    # Same enabled flag still changes the authority, not a no-op.
    await e.execute(
        "child", "presence.access_set", payload(subscription_revision=1), "takeover", now
    )
    record = e.snapshot()["presence"]["subscriptions"]["child"]
    assert "guardian" not in record and "guardian_revision" not in record
    assert child_row(projection(e, options, now))["consent_kind"] == "self"
    await e.execute(
        "child",
        "presence.access_set",
        payload(subscription_revision=2, enabled=False),
        "self-off",
        now,
    )
    assert child_row(projection(e, options, now))["enabled"] is False
    with pytest.raises(DomainError, match="conflict"):
        await e.execute("parent", "presence.guardian_access_set", payload(), "guardian-enable", now)
    # Only a fresh, explicit parent action may enable it again.
    await e.execute(
        "parent",
        "presence.guardian_access_set",
        payload(subscription_revision=3),
        "new-approval",
        now,
    )
    assert child_row(projection(e, options, now))["enabled"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "subject,change",
    [
        ("parent", {"active": False}),
        ("parent", {"role": "adult"}),
        ("parent", {"revision": 2}),
        ("parent", {"ha_user_id": None}),
        ("child", {"active": False}),
        ("child", {"role": "adult"}),
        ("child", {"revision": 2}),
    ],
)
async def test_current_guardian_and_child_epochs_revoke_evidence_and_replay(
    engine, store, now, subject, change
):
    e, options = await setup(engine, store, now)
    await e.execute("parent", "presence.guardian_access_set", payload(), "guardian-enable", now)
    state = e.snapshot()
    state["members"][subject].update(change)
    stale = Engine(state, store.save)
    before, writes = stale.snapshot(), store.calls
    assert presence.select_sources(state, state["members"]["owner"], options) == {}
    assert projection(stale, options, now, "owner")["shared"] == []
    with pytest.raises(DomainError):
        await stale.execute(
            "parent", "presence.guardian_access_set", payload(), "guardian-enable", now
        )
    assert stale.snapshot() == before and store.calls == writes


@pytest.mark.asyncio
async def test_guardian_reapproval_with_same_flag_requires_fresh_current_epoch(engine, store, now):
    e, options = await setup(engine, store, now)
    await e.execute("parent", "presence.guardian_access_set", payload(), "guardian-enable", now)
    state = e.snapshot()
    state["members"]["parent"]["revision"] = 2
    e = Engine(state, store.save)
    assert child_row(projection(e, options, now))["enabled"] is False
    receipt = await e.execute(
        "parent", "presence.guardian_access_set", payload(subscription_revision=1), "renewed", now
    )
    assert receipt["revision"] == 2
    assert e.snapshot()["presence"]["subscriptions"]["child"]["guardian_revision"] == 2
    assert child_row(projection(e, options, now))["enabled"] is True
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute(
            "parent",
            "presence.guardian_access_set",
            payload(subscription_revision=2),
            "unchanged",
            now,
        )


@pytest.mark.asyncio
async def test_guardian_source_replacement_requires_new_review(engine, store, now):
    e, options = await setup(engine, store, now)
    await e.execute("parent", "presence.guardian_access_set", payload(), "guardian-enable", now)
    replacement = deepcopy(options)
    replacement["presence_sources"]["child"].update(
        revision=2, entity_id="device_tracker.synthetic_new_child"
    )
    await e.system_update(
        "replace-source", now, lambda ctx: presence.sync_bindings(ctx, replacement)
    )
    assert child_row(projection(e, replacement, now))["enabled"] is False
    with pytest.raises(DomainError, match="conflict"):
        await e.execute("parent", "presence.guardian_access_set", payload(), "guardian-enable", now)
    await e.execute(
        "parent",
        "presence.guardian_access_set",
        payload(binding_revision=2, subscription_revision=1),
        "new-source-approval",
        now,
    )
    assert child_row(projection(e, replacement, now))["enabled"] is True
    assert projection(e, options, now)["shared"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "replacement",
    [
        {"guardian": "parent"},
        {"guardian_revision": 1},
        {"guardian": None, "guardian_revision": 1},
        {"guardian": "parent", "guardian_revision": None},
        {"guardian": "parent", "guardian_revision": True},
        {"guardian": "child", "guardian_revision": 1},
        {"guardian": "parent", "guardian_revision": 1, "unknown": True},
    ],
)
async def test_partial_or_malformed_guardian_records_fail_closed(engine, store, now, replacement):
    e, options = await setup(engine, store, now)
    await e.execute("child", "presence.access_set", payload(), "self-enable", now)
    state = e.snapshot()
    state["presence"]["subscriptions"]["child"].update(replacement)
    e = Engine(state, store.save)
    assert child_row(projection(e, options, now))["enabled"] is False
    assert projection(e, options, now)["shared"] == []
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "parent",
            "presence.guardian_access_set",
            payload(subscription_revision=1),
            "malformed",
            now,
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_store_failure_and_batch_failure_leave_no_consent_or_effect(engine, store, now):
    e, _options = await setup(engine, store, now)
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute("parent", "presence.guardian_access_set", payload(), "save-failed", now)
    assert e.snapshot() == before
    store.fail = False
    with pytest.raises(DomainError):
        await e.execute(
            "parent",
            "batch",
            {
                "commands": [
                    {"action": "presence.guardian_access_set", "payload": payload()},
                    {"action": "presence.guardian_access_set", "payload": payload(member="adult")},
                ]
            },
            "batch-failed",
            now,
        )
    assert e.snapshot() == before
