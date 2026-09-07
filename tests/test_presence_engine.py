"""Presence consent through the real Engine persistence and replay boundary."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain import presence
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def source_options(engine, *, source_revision=1, member_revision=None, entity=None):
    member = engine.snapshot()["members"]["adult"]
    return {
        "presence_max_age_seconds": 300,
        "presence_sources": {
            "adult": {
                "revision": source_revision,
                "status": "active",
                "member_revision": member_revision or member["revision"],
                "entity_id": entity or "person.synthetic_adult",
            }
        },
    }


async def enabled(engine, store, now):
    state = engine.snapshot()
    if "presence" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("presence")
    result = Engine(state, store.save)
    options = source_options(result)
    await result.system_update(
        "presence_binding_sync", now, lambda ctx: presence.sync_bindings(ctx, options)
    )
    return result, options


def access_payload(engine, *, binding_revision=1, subscription_revision=None, enabled=True):
    return {
        "member": "adult",
        "member_revision": engine.snapshot()["members"]["adult"]["revision"],
        "binding_revision": binding_revision,
        "subscription_revision": subscription_revision,
        "enabled": enabled,
    }


def test_additive_presence_bucket_is_nested_and_preserves_unknown_state(engine, store):
    state = engine.snapshot()
    state.pop("presence", None)
    state["future_extension"] = {"preserved": True}

    loaded = Engine(state, store.save).snapshot()

    assert loaded["presence"] == {"bindings": {}, "subscriptions": {}}
    assert loaded["future_extension"] == {"preserved": True}
    assert all(loaded[key] == value for key, value in state.items())


@pytest.mark.asyncio
async def test_self_consent_is_opaque_persisted_and_absent_from_engine_views(engine, store, now):
    e, options = await enabled(engine, store, now)
    before = e.snapshot()

    receipt = await e.execute(
        "adult",
        "presence.access_set",
        access_payload(e),
        "presence-enable",
        now,
    )

    assert receipt == {"member": "adult", "revision": 1, "status": "enabled"}
    state = e.snapshot()
    assert state["presence"]["subscriptions"]["adult"]["status"] == "enabled"
    assert presence.select_sources(state, state["members"]["adult"], options) == {
        "adult": "person.synthetic_adult"
    }
    assert set(state["processed"]["presence-enable"]["result"]) == {
        "member",
        "revision",
        "status",
    }
    assert state["audit"][-1]["result"] == receipt
    assert state["outbox"] == before["outbox"]
    assert state["tasks"] == before["tasks"]
    assert "person.synthetic_adult" not in repr(state["presence"])
    for actor in ("owner", "parent", "adult", "child", "guest"):
        view = e.view(actor, now=now)
        assert "presence" not in view
        assert "presence" not in plans.projection(view)


@pytest.mark.asyncio
async def test_exact_replay_is_write_free_and_rechecks_module_member_and_ha_link(
    engine, store, now
):
    e, _options = await enabled(engine, store, now)
    payload = access_payload(e)
    receipt = await e.execute("adult", "presence.access_set", payload, "presence-enable", now)
    before, writes = e.snapshot(), store.calls

    assert (
        await e.execute("adult", "presence.access_set", payload, "presence-enable", now) == receipt
    )
    assert e.snapshot() == before and store.calls == writes

    async def save(_state):
        return None

    disabled_state = e.snapshot()
    disabled_state["settings"]["modules"].remove("presence")
    disabled = Engine(disabled_state, save)
    with pytest.raises(DomainError, match="module_disabled"):
        await disabled.execute("adult", "presence.access_set", payload, "presence-enable", now)

    changed_state = e.snapshot()
    changed_state["members"]["adult"]["revision"] += 1
    changed = Engine(changed_state, save)
    with pytest.raises(DomainError, match="conflict"):
        await changed.execute("adult", "presence.access_set", payload, "presence-enable", now)

    unlinked_state = e.snapshot()
    unlinked_state["members"]["adult"]["ha_user_id"] = None
    unlinked = Engine(unlinked_state, save)
    with pytest.raises(DomainError, match="forbidden"):
        await unlinked.execute("adult", "presence.access_set", payload, "presence-enable", now)


@pytest.mark.asyncio
async def test_source_replacement_invalidates_consent_until_exact_reapproval(engine, store, now):
    e, initial = await enabled(engine, store, now)
    await e.execute("adult", "presence.access_set", access_payload(e), "presence-enable", now)
    replacement = source_options(
        e, source_revision=2, entity="device_tracker.synthetic_replacement"
    )
    await e.system_update(
        "presence_binding_replace",
        now,
        lambda ctx: presence.sync_bindings(ctx, replacement),
    )
    state = e.snapshot()
    adult = state["members"]["adult"]
    assert presence.select_sources(state, adult, initial) == {}
    assert presence.select_sources(state, adult, replacement) == {}

    renewed = await e.execute(
        "adult",
        "presence.access_set",
        access_payload(e, binding_revision=2, subscription_revision=1),
        "presence-renew",
        now,
    )
    assert renewed == {"member": "adult", "revision": 2, "status": "enabled"}
    state = e.snapshot()
    assert presence.select_sources(state, state["members"]["adult"], replacement) == {
        "adult": "device_tracker.synthetic_replacement"
    }
    assert "device_tracker.synthetic_replacement" not in repr(state["presence"])


@pytest.mark.asyncio
async def test_store_failure_and_failed_batch_leave_consent_atomic(engine, store, now):
    e, _options = await enabled(engine, store, now)
    before, writes = e.snapshot(), store.calls
    store.fail = True
    with pytest.raises(OSError):
        await e.execute(
            "adult",
            "presence.access_set",
            access_payload(e),
            "presence-failed-store",
            now,
        )
    assert e.snapshot() == before and store.calls == writes + 1
    store.fail = False

    writes = store.calls
    with pytest.raises(DomainError):
        await e.execute(
            "adult",
            "batch",
            {
                "commands": [
                    {"action": "presence.access_set", "payload": access_payload(e)},
                    {"action": "tasks.missing", "payload": {}},
                ]
            },
            "presence-failed-batch",
            now,
        )
    assert e.snapshot() == before and store.calls == writes


@pytest.mark.asyncio
async def test_disable_reenable_lineage_and_cross_actor_denial(engine, store, now):
    e, _options = await enabled(engine, store, now)
    enabled_receipt = await e.execute(
        "adult", "presence.access_set", access_payload(e), "presence-enable", now
    )
    disabled = await e.execute(
        "adult",
        "presence.access_set",
        access_payload(e, subscription_revision=enabled_receipt["revision"], enabled=False),
        "presence-disable",
        now,
    )
    assert disabled == {"member": "adult", "revision": 2, "status": "disabled"}
    with pytest.raises(DomainError, match="forbidden"):
        await e.execute(
            "parent",
            "presence.access_set",
            access_payload(e, subscription_revision=disabled["revision"]),
            "presence-parent-enable",
            now,
        )
    assert e.snapshot()["presence"]["subscriptions"]["adult"]["status"] == "disabled"

    restored = await e.execute(
        "adult",
        "presence.access_set",
        access_payload(e, subscription_revision=disabled["revision"]),
        "presence-reenable",
        now,
    )
    assert restored == {"member": "adult", "revision": 3, "status": "enabled"}
    resumed = Engine(deepcopy(store.value), store.save)
    assert resumed.snapshot()["presence"] == e.snapshot()["presence"]
