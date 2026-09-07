"""Permission-checked, ephemeral Home Assistant presence projections."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.family_assistant import presence_observations
from custom_components.family_assistant.domain import presence
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine


class Permissions:
    def __init__(self, allowed, calls):
        self.allowed = set(allowed)
        self.calls = calls

    def check_entity(self, entity_id, policy):
        self.calls.append(("permission", entity_id, policy))
        return entity_id in self.allowed


class Registry:
    def __init__(self, entities, calls):
        self.entities = dict(entities)
        self.calls = calls

    def async_get(self, entity_id):
        self.calls.append(("registry", entity_id))
        value = self.entities.get(entity_id)
        return SimpleNamespace(entity_id=value) if value is not None else None


class States:
    def __init__(self, values, calls):
        self.values = dict(values)
        self.calls = calls

    def get(self, entity_id):
        self.calls.append(("state", entity_id))
        return self.values.get(entity_id)


class ReportedState:
    def __init__(self, state, reported, *, updated=None):
        self.state = state
        self.last_reported = reported
        self.last_updated = updated
        self.attributes = {
            "latitude": "PRIVATE_LATITUDE_CANARY",
            "longitude": "PRIVATE_LONGITUDE_CANARY",
            "friendly_name": "PRIVATE_TRACKER_NAME_CANARY",
        }


class LegacyState:
    def __init__(self, state, updated):
        self.state = state
        self.last_updated = updated
        self.attributes = {"zone": "PRIVATE_LEGACY_ZONE_CANARY"}


def configured(engine, now, members=("parent", "child", "sibling")):
    state = engine.snapshot()
    state["settings"]["modules"].append("presence")
    options = {
        "presence_max_age_seconds": 300,
        "presence_sources": {
            member: {
                "revision": 1,
                "status": "active",
                "member_revision": state["members"][member]["revision"],
                "entity_id": (
                    f"person.{member}" if member == "parent" else f"device_tracker.{member}"
                ),
            }
            for member in members
        },
    }
    presence.sync_bindings(Context(state, state["members"]["parent"], now, "sync"), options)
    for member in members:
        actor = state["members"][member]
        presence.handle(
            Context(state, actor, now, f"enable-{member}"),
            "access_set",
            {
                "member": member,
                "member_revision": actor["revision"],
                "binding_revision": 1,
                "subscription_revision": None,
                "enabled": True,
            },
        )

    async def save(_state):
        return None

    return Engine(state, save), options


def harness(monkeypatch, engine, options, values, allowed, *, registry_entities=None):
    calls = []
    runtime = SimpleNamespace(engine=engine)
    entry = SimpleNamespace(entry_id="synthetic-entry", options=options, runtime_data=runtime)
    if registry_entities is None:
        registry_entities = {
            source["entity_id"]: source["entity_id"]
            for source in options["presence_sources"].values()
            if source["status"] == "active"
        }
    registry = Registry(registry_entities, calls)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda entry_id: entry),
        states=States(values, calls),
    )
    user = SimpleNamespace(id="synthetic-parent", permissions=Permissions(allowed, calls))
    monkeypatch.setattr(presence_observations, "_ha_access", lambda _hass: (registry, "read"))
    return hass, entry, runtime, user, calls


def test_parent_reads_only_registered_permitted_sources_and_never_attributes(
    engine, now, monkeypatch
):
    configured_engine, options = configured(engine, now)
    values = {
        "person.parent": ReportedState("home", now, updated=now - timedelta(days=1)),
        "device_tracker.child": ReportedState("PRIVATE_ZONE_CANARY", now),
        "device_tracker.sibling": ReportedState("home", now),
    }
    hass, entry, runtime, user, calls = harness(
        monkeypatch,
        configured_engine,
        options,
        values,
        {"person.parent", "device_tracker.child"},
    )
    before = configured_engine.snapshot()

    result = presence_observations.project(hass, entry, runtime, "parent", user, now)

    assert result["self"] == {
        "member": "parent",
        "member_revision": 1,
        "binding_revision": 1,
        "subscription_revision": 1,
        "enabled": True,
        "can_edit": True,
        "status": "reported_home",
        "reason": "fresh",
        "observed_at": now.isoformat(),
    }
    assert result["shared"] == [
        {
            "member": "child",
            "member_revision": 1,
            "status": "reported_away",
            "reason": "fresh",
            "observed_at": now.isoformat(),
        },
        {
            "member": "sibling",
            "member_revision": 1,
            "status": "unknown",
            "reason": "unavailable",
            "observed_at": None,
        },
    ]
    assert [item[1] for item in calls if item[0] == "state"] == [
        "person.parent",
        "device_tracker.child",
    ]
    assert calls.index(("permission", "person.parent", "read")) < calls.index(
        ("state", "person.parent")
    )
    assert calls.index(("permission", "device_tracker.child", "read")) < calls.index(
        ("state", "device_tracker.child")
    )
    encoded = repr(result)
    for canary in (
        "PRIVATE_ZONE_CANARY",
        "PRIVATE_LATITUDE_CANARY",
        "PRIVATE_LONGITUDE_CANARY",
        "PRIVATE_TRACKER_NAME_CANARY",
        "person.parent",
        "device_tracker.child",
    ):
        assert canary not in encoded
    assert configured_engine.snapshot() == before


def test_nonparent_reads_only_self_even_with_permission_for_every_source(engine, now, monkeypatch):
    configured_engine, options = configured(engine, now)
    values = {
        source["entity_id"]: ReportedState("home", now)
        for source in options["presence_sources"].values()
    }
    hass, entry, runtime, _parent, calls = harness(
        monkeypatch, configured_engine, options, values, set(values)
    )
    child = SimpleNamespace(id="synthetic-child", permissions=Permissions(set(values), calls))

    result = presence_observations.project(hass, entry, runtime, "child", child, now)

    assert result["self"]["status"] == "reported_home"
    assert result["shared"] == []
    assert [item[1] for item in calls if item[0] == "state"] == ["device_tracker.child"]


@pytest.mark.parametrize("revocation", ("module", "subscription", "binding", "member"))
def test_disabled_or_revoked_actor_source_performs_zero_state_reads(
    engine, now, monkeypatch, revocation
):
    configured_engine, options = configured(engine, now, ("parent",))
    state = configured_engine.snapshot()
    if revocation == "module":
        state["settings"]["modules"].remove("presence")
    elif revocation == "subscription":
        state["presence"]["subscriptions"]["parent"]["status"] = "disabled"
    elif revocation == "binding":
        state["presence"]["bindings"]["parent"]["source_hash"] = "0" * 64
    else:
        state["members"]["parent"]["revision"] += 1

    async def save(_state):
        return None

    revoked = Engine(state, save)
    hass, entry, runtime, user, calls = harness(
        monkeypatch,
        revoked,
        options,
        {"person.parent": ReportedState("home", now)},
        {"person.parent"},
    )

    result = presence_observations.project(hass, entry, runtime, "parent", user, now)

    assert not any(item[0] == "state" for item in calls)
    if revocation == "module":
        assert result == {"self": None, "shared": []}
    else:
        assert result["self"]["status"] == "unknown"


def test_wrong_ha_user_or_entry_generation_performs_no_registry_or_state_read(
    engine, now, monkeypatch
):
    configured_engine, options = configured(engine, now, ("parent",))
    hass, entry, runtime, user, calls = harness(
        monkeypatch,
        configured_engine,
        options,
        {"person.parent": ReportedState("home", now)},
        {"person.parent"},
    )
    wrong_user = SimpleNamespace(id="synthetic-child", permissions=user.permissions)
    assert presence_observations.project(hass, entry, runtime, "parent", wrong_user, now) == {
        "self": None,
        "shared": [],
    }
    assert calls == []

    entry.runtime_data = SimpleNamespace(engine=configured_engine)
    assert presence_observations.project(hass, entry, runtime, "parent", user, now) == {
        "self": None,
        "shared": [],
    }
    assert calls == []


def test_unregistered_or_denied_source_projects_unknown_without_state_read(
    engine, now, monkeypatch
):
    configured_engine, options = configured(engine, now, ("parent",))
    for registry_entities, allowed in (
        ({}, {"person.parent"}),
        ({"person.parent": "person.parent"}, set()),
    ):
        hass, entry, runtime, user, calls = harness(
            monkeypatch,
            configured_engine,
            options,
            {"person.parent": ReportedState("home", now)},
            allowed,
            registry_entities=registry_entities,
        )
        result = presence_observations.project(hass, entry, runtime, "parent", user, now)
        assert result["self"]["status"] == "unknown"
        assert result["self"]["reason"] == "unavailable"
        assert not any(item[0] == "state" for item in calls)


@pytest.mark.parametrize(
    ("observed", "status", "reason", "observed_at"),
    (
        (None, "unknown", "unavailable", None),
        (ReportedState("unknown", None), "unknown", "unavailable", None),
        (ReportedState(7, None), "unknown", "unavailable", None),
        (ReportedState("home", None, updated=None), "unknown", "unavailable", None),
        (ReportedState("home", "malformed"), "unknown", "unavailable", None),
        ("stale", "unknown", "stale", None),
        ("future", "unknown", "stale", None),
        ("legacy", "reported_away", "fresh", "NOW"),
    ),
)
def test_missing_stale_malformed_and_legacy_state_normalize_safely(
    engine, now, monkeypatch, observed, status, reason, observed_at
):
    configured_engine, options = configured(engine, now, ("parent",))
    if observed == "stale":
        observed = ReportedState("home", now - timedelta(seconds=301))
    elif observed == "future":
        observed = ReportedState("home", now + timedelta(seconds=6))
    elif observed == "legacy":
        observed = LegacyState("PRIVATE_NAMED_ZONE_CANARY", now)
    values = {} if observed is None else {"person.parent": observed}
    hass, entry, runtime, user, _calls = harness(
        monkeypatch, configured_engine, options, values, {"person.parent"}
    )

    row = presence_observations.project(hass, entry, runtime, "parent", user, now)["self"]

    assert (row["status"], row["reason"]) == (status, reason)
    assert row["observed_at"] == (now.isoformat() if observed_at == "NOW" else observed_at)
    assert "PRIVATE_NAMED_ZONE_CANARY" not in repr(row)
