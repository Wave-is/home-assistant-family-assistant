"""Independent notification-purpose HA ACL checks, no coordinate access or storage."""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_presence_delivery import enabled
from test_presence_observations import Permissions, Registry, ReportedState, States

from custom_components.family_assistant import presence_notification_adapter as adapter
from custom_components.family_assistant.domain import presence_delivery
from custom_components.family_assistant.domain.validation import DomainError


async def setup(engine, store, now, monkeypatch, *, guardian=False):
    e, options, _, actor, _ = await enabled(engine, store, now, guardian=guardian)
    calls = []
    source = options["presence_sources"]["child"]["entity_id"]
    runtime = SimpleNamespace(engine=e)
    entry = SimpleNamespace(entry_id="synthetic-entry", options=options, runtime_data=runtime)
    user = SimpleNamespace(
        id=e.snapshot()["members"][actor]["ha_user_id"],
        is_active=True,
        permissions=Permissions({source}, calls),
    )
    users = {user.id: user}

    async def get_user(identifier):
        calls.append(("user", identifier))
        return users.get(identifier)

    hass = SimpleNamespace(
        auth=SimpleNamespace(async_get_user=get_user),
        config_entries=SimpleNamespace(async_get_entry=lambda _id: entry),
        states=States({source: ReportedState("home", now)}, calls),
    )
    registry = Registry({source: source}, calls)
    monkeypatch.setattr(adapter, "_ha_access", lambda _hass: (registry, "read"))
    return e, hass, entry, runtime, user, users, calls, source


@pytest.mark.asyncio
@pytest.mark.parametrize("guardian", [False, True])
async def test_notification_consent_reads_only_its_registered_acl_source(
    engine, store, now, monkeypatch, guardian
):
    e, hass, entry, runtime, _, _, calls, source = await setup(
        engine, store, now, monkeypatch, guardian=guardian
    )
    state = e.snapshot()
    assert state["presence"]["subscriptions"] == {}
    observe = await adapter.prepare(hass, entry, runtime, state, lambda: None)
    assert not any(call[0] == "state" for call in calls)
    policy = presence_delivery.effective_policy(state, "child")
    assert observe(state, state["members"]["child"], policy, now) is True
    assert [call for call in calls if call[0] == "state"] == [("state", source)]
    assert e.snapshot() == state
    assert "PRIVATE_LATITUDE_CANARY" not in repr(state)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    ["acl", "inactive", "missing_user", "entry", "runtime", "options", "member", "policy", "guard"],
)
async def test_revocation_never_reads_entity_state(engine, store, now, monkeypatch, drift):
    e, hass, entry, runtime, user, users, calls, source = await setup(
        engine, store, now, monkeypatch
    )
    state = e.snapshot()
    policy = presence_delivery.effective_policy(state, "child")
    if drift == "missing_user":
        users.clear()
    blocked = {"value": False}

    def guard():
        if blocked["value"]:
            raise DomainError("forbidden")

    observe = await adapter.prepare(hass, entry, runtime, state, guard)
    if drift == "acl":
        user.permissions.allowed.clear()
    if drift == "inactive":
        user.is_active = False
    if drift == "entry":
        hass.config_entries.async_get_entry = lambda _id: None
    if drift == "runtime":
        entry.runtime_data = object()
    if drift == "options":
        entry.options["presence_sources"]["child"]["entity_id"] = "person.unapproved"
    if drift == "member":
        state["members"]["child"]["revision"] += 1
    if drift == "policy":
        state["presence"]["delivery_preferences"]["child"]["revision"] += 1
    if drift == "guard":
        blocked["value"] = True
    assert observe(state, state["members"]["child"], policy, now) is False
    assert not any(call[0] == "state" for call in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,age",
    [
        ("not_home", 0),
        ("PRIVATE_ZONE_NAME", 0),
        ("unavailable", 0),
        ("unknown", 0),
        ("home", -301),
        ("home", 6),
    ],
)
async def test_absent_unknown_stale_and_future_are_not_home(
    engine, store, now, monkeypatch, value, age
):
    e, hass, entry, runtime, _, _, _, source = await setup(engine, store, now, monkeypatch)
    state = e.snapshot()
    before = deepcopy(state)
    hass.states.values[source] = ReportedState(value, now + timedelta(seconds=age))
    observe = await adapter.prepare(hass, entry, runtime, state, lambda: None)
    assert (
        observe(
            state,
            state["members"]["child"],
            presence_delivery.effective_policy(state, "child"),
            now,
        )
        is False
    )
    assert state == before and e.snapshot() == before
