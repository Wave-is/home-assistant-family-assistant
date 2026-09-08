"""Separate notification-purpose consent through real Engine transactions."""

from copy import deepcopy

import pytest
from test_presence_guardian import setup

from custom_components.family_assistant.domain import presence, presence_delivery
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def payload(**changes):
    return {
        "member": "child",
        "member_revision": 1,
        "binding_revision": 1,
        "preference_revision": None,
        "enabled": True,
        "max_wait_minutes": 720,
        "actor_member_revision": 1,
        **changes,
    }


async def enabled(engine, store, now, *, guardian=False):
    e, options = await setup(engine, store, now, child_link=not guardian)
    action = (
        "presence.guardian_notification_access_set"
        if guardian
        else "presence.notification_access_set"
    )
    actor = "parent" if guardian else "child"
    result = await e.execute(actor, action, payload(), "delivery-consent", now)
    return e, options, action, actor, result


@pytest.mark.asyncio
@pytest.mark.parametrize("guardian", [True, False])
async def test_separate_consent_is_atomic_opaque_and_does_not_grant_dashboard_access(
    engine, store, now, guardian
):
    e, options, action, actor, result = await enabled(engine, store, now, guardian=guardian)
    assert result == {"member": "child", "revision": 1, "status": "enabled"}
    state = e.snapshot()
    record = presence_delivery.effective_policy(state, "child")
    assert record["approved_by"] == actor and record["max_wait_minutes"] == 720
    assert state["presence"]["subscriptions"] == {}
    assert presence.select_sources(state, state["members"][actor], options) == {}
    assert "person." not in repr(state["presence"]["delivery_preferences"])
    assert "observed_at" not in repr(record)
    for bucket in ("tasks", "outbox", "court", "alarm_runs", "routine_runs"):
        assert state[bucket] == engine.snapshot()[bucket]
    before, writes = e.snapshot(), store.calls
    assert await e.execute(actor, action, payload(), "delivery-consent", now) == result
    assert e.snapshot() == before and store.calls == writes
    restored = Engine(deepcopy(store.value), store.save)
    assert presence_delivery.effective_policy(restored.snapshot(), "child") == record
    assert "presence" not in restored.view(actor, now=now)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "parent", "adult", "sibling", "guest"])
async def test_self_action_cannot_change_someone_else(engine, store, now, actor):
    e, _ = await setup(engine, store, now)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(actor, "presence.notification_access_set", payload(), "denied", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor,target",
    [
        ("child", "child"),
        ("adult", "child"),
        ("parent", "adult"),
        ("owner", "parent"),
        ("guest", "child"),
    ],
)
async def test_guardian_action_is_not_parent_control_of_adult_notifications(
    engine, store, now, actor, target
):
    e, _ = await setup(engine, store, now)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            actor,
            "presence.guardian_notification_access_set",
            payload(member=target),
            "denied",
            now,
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key,value",
    [
        ("member_revision", True),
        ("binding_revision", True),
        ("actor_member_revision", True),
        ("preference_revision", True),
        ("member_revision", 0),
        ("binding_revision", 1.0),
        ("enabled", 1),
        ("enabled", "true"),
        ("max_wait_minutes", True),
        ("max_wait_minutes", 14),
        ("max_wait_minutes", 1441),
        ("max_wait_minutes", "720"),
        ("unexpected", 1),
    ],
)
async def test_strict_payloads_never_silently_coerce_or_rebase(engine, store, now, key, value):
    e, _ = await setup(engine, store, now)
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(
            "child", "presence.notification_access_set", payload(**{key: value}), "invalid", now
        )
    assert e.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift", ["subject", "approver", "role", "link", "binding", "removed", "module"]
)
async def test_each_identity_source_or_module_revocation_stops_background_permission(
    engine, store, now, drift
):
    e, _, action, actor, _ = await enabled(engine, store, now, guardian=True)
    state = e.snapshot()
    if drift == "subject":
        state["members"]["child"]["revision"] += 1
    if drift == "approver":
        state["members"]["parent"]["revision"] += 1
    if drift == "role":
        state["members"]["parent"]["role"] = "adult"
    if drift == "link":
        state["members"]["parent"]["ha_user_id"] = None
    if drift == "binding":
        state["presence"]["bindings"]["child"]["revision"] += 1
    if drift == "removed":
        state["presence"]["bindings"]["child"]["status"] = "removed"
    if drift == "module":
        state["settings"]["modules"].remove("presence")
    e = Engine(state, store.save)
    assert presence_delivery.effective_policy(e.snapshot(), "child") is None
    before = e.snapshot()
    with pytest.raises(DomainError):
        await e.execute(actor, action, payload(), "delivery-consent", now)
    assert e.snapshot() == before


@pytest.mark.asyncio
async def test_dashboard_consent_is_not_notification_consent(engine, store, now):
    e, options = await setup(engine, store, now)
    await e.execute(
        "child",
        "presence.access_set",
        {
            "member": "child",
            "member_revision": 1,
            "binding_revision": 1,
            "subscription_revision": None,
            "enabled": True,
        },
        "dashboard",
        now,
    )
    assert presence.select_sources(e.snapshot(), e.snapshot()["members"]["child"], options)
    assert presence_delivery.effective_policy(e.snapshot(), "child") is None


@pytest.mark.asyncio
async def test_store_failure_noop_reapproval_child_takeover_and_removed_source_disable(
    engine, store, now
):
    e, options = await setup(engine, store, now)
    before = e.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await e.execute(
            "parent", "presence.guardian_notification_access_set", payload(), "initial", now
        )
    assert e.snapshot() == before
    store.fail = False
    await e.execute(
        "parent", "presence.guardian_notification_access_set", payload(), "initial", now
    )
    with pytest.raises(DomainError, match="invalid_transition"):
        await e.execute(
            "parent",
            "presence.guardian_notification_access_set",
            payload(preference_revision=1),
            "noop",
            now,
        )
    # Child explicitly takes over the guardian policy; unchanged duration is not a no-op.
    await e.execute(
        "child", "presence.notification_access_set", payload(preference_revision=1), "takeover", now
    )
    assert presence_delivery.effective_policy(e.snapshot(), "child")["approved_by"] == "child"
    options["presence_sources"]["child"] = {
        "revision": 2,
        "status": "removed",
        "member_revision": 1,
    }
    await e.system_update("remove-source", now, lambda ctx: presence.sync_bindings(ctx, options))
    assert presence_delivery.effective_policy(e.snapshot(), "child") is None
    result = await e.execute(
        "child",
        "presence.notification_access_set",
        payload(binding_revision=2, preference_revision=2, enabled=False),
        "disable",
        now,
    )
    assert result["status"] == "disabled" and result["revision"] == 3


@pytest.mark.asyncio
async def test_views_are_metadata_only_self_or_parent_children(engine, store, now):
    e, _, _, _, _ = await enabled(engine, store, now, guardian=True)
    state = e.snapshot()
    parent = presence_delivery.view(state, state["members"]["parent"])
    child = presence_delivery.view(state, state["members"]["child"])
    assert child["self"]["effective"] is True and "managed" not in child
    assert any(
        row["member"] == "child" and row["approved_by"] == "parent" for row in parent["managed"]
    )
    for forbidden in (
        "entity_id",
        "source_hash",
        "observed_at",
        "created_at",
        "updated_at",
        "telegram_id",
        "ha_user_id",
    ):
        assert forbidden not in repr(parent)
    assert presence_delivery.view(state, state["members"]["guest"]) == {"self": None}
