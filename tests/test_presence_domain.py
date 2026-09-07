"""Pure contracts for opt-in, ephemeral household presence evidence."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.presence import (
    authorize_replay,
    handle,
    select_sources,
    sync_bindings,
    validate_options,
    view,
)
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def state():
    members = {
        "owner": {
            "id": "owner",
            "role": "owner",
            "active": True,
            "revision": 1,
            "ha_user_id": "ha_owner",
        },
        "parent": {
            "id": "parent",
            "role": "parent",
            "active": True,
            "revision": 2,
            "ha_user_id": "ha_parent",
        },
        "adult": {
            "id": "adult",
            "role": "adult",
            "active": True,
            "revision": 3,
            "ha_user_id": "ha_adult",
        },
        "child": {
            "id": "child",
            "role": "child",
            "active": True,
            "revision": 4,
            "ha_user_id": "ha_child",
        },
        "guest": {
            "id": "guest",
            "role": "guest",
            "active": True,
            "revision": 5,
            "ha_user_id": "ha_guest",
        },
    }
    return {
        "settings": {"modules": ["presence"]},
        "members": members,
        "presence": {"bindings": {}, "subscriptions": {}},
        "outbox": {},
    }


def context(value, actor="adult", operation="presence-op"):
    return Context(value, value["members"][actor], NOW, operation)


def source_options(**entities):
    result = {}
    value = state()
    for member_id, entity_id in entities.items():
        result[member_id] = {
            "revision": 1,
            "status": "active",
            "member_revision": value["members"][member_id]["revision"],
            "entity_id": entity_id,
        }
    return {"presence_sources": result, "presence_max_age_seconds": 300}


def sync(value, options):
    return sync_bindings(context(value, "owner", "source-sync"), options)


def access_payload(value, member_id, binding_revision=1, subscription_revision=None, enabled=True):
    return {
        "member": member_id,
        "member_revision": value["members"][member_id]["revision"],
        "binding_revision": binding_revision,
        "subscription_revision": subscription_revision,
        "enabled": enabled,
    }


def enable(value, member_id, binding_revision=1):
    return handle(
        context(value, member_id, f"enable-{member_id}"),
        "access_set",
        access_payload(value, member_id, binding_revision),
    )


def assert_error(code, call):
    with pytest.raises(DomainError) as info:
        call()
    assert info.value.code == code


def test_options_are_strict_bounded_and_do_not_retain_unrelated_values():
    options = source_options(
        owner="person.owner",
        adult="device_tracker.adult_phone",
    )
    options["private_provider_token"] = "CANARY"
    assert validate_options(options) == {
        "sources": options["presence_sources"],
        "max_age_seconds": 300,
    }

    invalid = [
        {"presence_sources": [], "presence_max_age_seconds": 300},
        {"presence_sources": {}, "presence_max_age_seconds": True},
        {"presence_sources": {}, "presence_max_age_seconds": 29},
        {"presence_sources": {}, "presence_max_age_seconds": 3601},
    ]
    base = source_options(adult="person.adult")
    for record in (
        {"revision": True, "status": "active", "member_revision": 3, "entity_id": "person.a"},
        {"revision": 1, "status": "active", "member_revision": 3},
        {
            "revision": 1,
            "status": "active",
            "member_revision": 3,
            "entity_id": "sensor.adult",
        },
        {
            "revision": 1,
            "status": "removed",
            "member_revision": 3,
            "entity_id": "person.adult",
        },
        {"revision": 1, "status": "removed", "member_revision": 3, "extra": 1},
    ):
        candidate = deepcopy(base)
        candidate["presence_sources"]["adult"] = record
        invalid.append(candidate)
    duplicate = source_options(adult="person.same", child="person.same")
    invalid.append(duplicate)
    for candidate in invalid:
        assert_error("invalid_field", lambda candidate=candidate: validate_options(candidate))


def test_options_enforce_active_and_total_record_budgets():
    active = {
        f"m{index}": {
            "revision": 1,
            "status": "active",
            "member_revision": 1,
            "entity_id": f"person.m{index}",
        }
        for index in range(21)
    }
    assert_error(
        "invalid_field",
        lambda: validate_options({"presence_sources": active}),
    )
    removed = {
        f"m{index}": {
            "revision": 1,
            "status": "removed",
            "member_revision": 1,
        }
        for index in range(101)
    }
    assert_error(
        "invalid_field",
        lambda: validate_options({"presence_sources": removed}),
    )


def test_binding_sync_persists_no_entity_id_and_requires_monotonic_exact_changes():
    value = state()
    first = source_options(adult="device_tracker.private_canary")
    assert sync(value, first) == {"records": 1, "active": 1}
    binding = value["presence"]["bindings"]["adult"]
    assert binding.keys() == {"member", "revision", "status", "member_revision", "source_hash"}
    assert "private_canary" not in repr(value["presence"])
    before = deepcopy(value)
    assert sync(value, first) == {"records": 1, "active": 1}
    assert value == before

    replaced_without_revision = source_options(adult="person.replacement")
    assert_error("conflict", lambda: sync(value, replaced_without_revision))
    skipped_revision = deepcopy(replaced_without_revision)
    skipped_revision["presence_sources"]["adult"]["revision"] = 3
    assert_error("conflict", lambda: sync(value, skipped_revision))

    removed = {
        "presence_sources": {
            "adult": {
                "revision": 2,
                "status": "removed",
                "member_revision": 3,
            }
        }
    }
    assert sync(value, removed) == {"records": 1, "active": 0}
    assert value["presence"]["bindings"]["adult"] == {
        "member": "adult",
        "revision": 2,
        "status": "removed",
        "member_revision": 3,
    }
    assert_error("conflict", lambda: sync(value, {"presence_sources": {}}))
    readded = source_options(adult="person.replacement")
    readded["presence_sources"]["adult"]["revision"] = 3
    assert sync(value, readded) == {"records": 1, "active": 1}


def test_binding_sync_requires_current_member_epoch_for_active_source():
    value = state()
    options = source_options(adult="person.adult")
    options["presence_sources"]["adult"]["member_revision"] = 2
    before = deepcopy(value)
    assert_error("conflict", lambda: sync(value, options))
    assert value == before


@pytest.mark.parametrize("member_id", ["owner", "parent", "adult", "child"])
def test_every_linked_non_guest_member_can_only_enable_self(member_id):
    value = state()
    options = source_options(**{member_id: f"person.{member_id}"})
    sync(value, options)
    assert enable(value, member_id) == {"member": member_id, "revision": 1, "status": "enabled"}
    record = value["presence"]["subscriptions"][member_id]
    assert record["member_revision"] == value["members"][member_id]["revision"]
    assert record["binding_revision"] == 1
    assert value["outbox"] == {}


def test_parent_owner_guest_inactive_and_unlinked_cannot_consent_for_subject():
    for actor in ("owner", "parent", "guest"):
        value = state()
        sync(value, source_options(adult="person.adult"))
        assert_error(
            "forbidden",
            lambda actor=actor, value=value: handle(
                context(value, actor), "access_set", access_payload(value, "adult")
            ),
        )
    for change in (
        lambda member: member.update(active=False),
        lambda member: member.update(ha_user_id=None),
    ):
        value = state()
        sync(value, source_options(adult="person.adult"))
        change(value["members"]["adult"])
        assert_error(
            "forbidden",
            lambda value=value: handle(
                context(value, "adult"), "access_set", access_payload(value, "adult")
            ),
        )


def test_access_requires_exact_binding_and_subscription_lineage_without_aba():
    value = state()
    options = source_options(adult="person.adult")
    sync(value, options)
    receipt = enable(value, "adult")
    assert_error(
        "invalid_field",
        lambda: handle(
            context(value, "adult"),
            "access_set",
            access_payload(value, "adult", subscription_revision=None, enabled=False),
        ),
    )
    disabled = handle(
        context(value, "adult"),
        "access_set",
        access_payload(
            value,
            "adult",
            subscription_revision=receipt["revision"],
            enabled=False,
        ),
    )
    assert disabled == {"member": "adult", "revision": 2, "status": "disabled"}
    assert set(value["presence"]["subscriptions"]["adult"]) == {
        "member",
        "revision",
        "member_revision",
        "binding_revision",
        "status",
        "created_at",
        "updated_at",
    }
    enabled = handle(
        context(value, "adult"),
        "access_set",
        access_payload(
            value,
            "adult",
            subscription_revision=disabled["revision"],
            enabled=True,
        ),
    )
    assert enabled == {"member": "adult", "revision": 3, "status": "enabled"}

    removed = deepcopy(options)
    removed["presence_sources"]["adult"] = {
        "revision": 2,
        "status": "removed",
        "member_revision": 3,
    }
    sync(value, removed)
    stale = access_payload(
        value,
        "adult",
        binding_revision=1,
        subscription_revision=enabled["revision"],
        enabled=True,
    )
    assert_error("conflict", lambda: handle(context(value, "adult"), "access_set", stale))
    assert_error(
        "invalid_transition",
        lambda: handle(
            context(value, "adult"),
            "access_set",
            access_payload(
                value,
                "adult",
                binding_revision=2,
                subscription_revision=enabled["revision"],
                enabled=True,
            ),
        ),
    )


def test_invalid_payloads_and_revision_overflow_do_not_mutate():
    value = state()
    sync(value, source_options(adult="person.adult"))
    candidates = []
    base = access_payload(value, "adult")
    for field, bad in (
        ("member_revision", True),
        ("binding_revision", 0),
        ("subscription_revision", "1"),
        ("enabled", 1),
    ):
        candidate = {**base, field: bad}
        candidates.append(candidate)
    candidates.append({**base, "extra": "x"})
    for candidate in candidates:
        before = deepcopy(value)
        assert_error(
            "invalid_field",
            lambda candidate=candidate: handle(context(value, "adult"), "access_set", candidate),
        )
        assert value == before
    value["presence"]["subscriptions"]["adult"] = {
        "member": "adult",
        "revision": 2**53 - 1,
        "member_revision": 3,
        "binding_revision": 1,
        "status": "enabled",
    }
    before = deepcopy(value)
    assert_error(
        "invalid_field",
        lambda: handle(
            context(value, "adult"),
            "access_set",
            access_payload(
                value,
                "adult",
                subscription_revision=2**53 - 1,
                enabled=False,
            ),
        ),
    )
    assert value == before


def test_module_and_member_epoch_revoke_selection_and_replay():
    value = state()
    options = source_options(adult="person.adult")
    sync(value, options)
    payload = access_payload(value, "adult")
    receipt = handle(context(value, "adult"), "access_set", payload)
    authorize_replay(context(value, "adult"), "access_set", payload, receipt)
    assert select_sources(value, value["members"]["adult"], options) == {"adult": "person.adult"}

    value["members"]["adult"]["revision"] += 1
    assert select_sources(value, value["members"]["adult"], options) == {}
    assert_error(
        "conflict",
        lambda: authorize_replay(context(value, "adult"), "access_set", payload, receipt),
    )
    value["members"]["adult"]["revision"] -= 1
    value["settings"]["modules"] = []
    assert select_sources(value, value["members"]["adult"], options) == {}
    assert_error(
        "module_disabled",
        lambda: authorize_replay(context(value, "adult"), "access_set", payload, receipt),
    )


def test_binding_change_revokes_old_consent_and_replay_until_fresh_consent():
    value = state()
    original = source_options(adult="person.adult")
    sync(value, original)
    payload = access_payload(value, "adult")
    receipt = handle(context(value, "adult"), "access_set", payload)
    changed = source_options(adult="device_tracker.replacement")
    changed["presence_sources"]["adult"]["revision"] = 2
    sync(value, changed)
    assert select_sources(value, value["members"]["adult"], changed) == {}
    assert_error(
        "conflict",
        lambda: authorize_replay(context(value, "adult"), "access_set", payload, receipt),
    )
    fresh_payload = access_payload(
        value,
        "adult",
        binding_revision=2,
        subscription_revision=receipt["revision"],
    )
    fresh = handle(context(value, "adult"), "access_set", fresh_payload)
    assert fresh == {"member": "adult", "revision": 2, "status": "enabled"}
    assert select_sources(value, value["members"]["adult"], changed) == {
        "adult": "device_tracker.replacement"
    }


@pytest.mark.parametrize(
    ("raw_state", "offset", "expected"),
    [
        ("home", timedelta(seconds=0), ("reported_home", "fresh", True)),
        ("not_home", timedelta(seconds=300), ("reported_away", "fresh", True)),
        ("work", timedelta(seconds=-5), ("reported_away", "fresh", True)),
        ("home", timedelta(seconds=-5, microseconds=-1), ("unknown", "stale", False)),
        ("home", timedelta(seconds=300, microseconds=1), ("unknown", "stale", False)),
        ("unknown", timedelta(0), ("unknown", "unavailable", False)),
        ("unavailable", timedelta(0), ("unknown", "unavailable", False)),
        (" ", timedelta(0), ("unknown", "unavailable", False)),
        (3, timedelta(0), ("unknown", "unavailable", False)),
    ],
)
def test_observation_normalization_and_age_boundaries(raw_state, offset, expected):
    value = state()
    options = source_options(adult="person.adult")
    sync(value, options)
    enable(value, "adult")
    observed = NOW - offset
    projection = view(
        value,
        value["members"]["adult"],
        options,
        {"adult": {"state": raw_state, "observed_at": observed}},
        NOW,
    )["self"]
    actual = (
        projection["status"],
        projection["reason"],
        projection["observed_at"] is not None,
    )
    assert actual == expected


@pytest.mark.parametrize(
    "observation",
    [
        None,
        {},
        {"state": "home"},
        {"state": "home", "observed_at": "bad"},
        {"state": "home", "observed_at": datetime(2026, 9, 7)},
        {"state": "home", "observed_at": NOW, "latitude": 50.0},
    ],
)
def test_malformed_or_attribute_bearing_observation_fails_closed(observation):
    value = state()
    options = source_options(adult="person.adult")
    sync(value, options)
    enable(value, "adult")
    before = deepcopy(value)
    result = view(
        value,
        value["members"]["adult"],
        options,
        {"adult": observation},
        NOW,
    )["self"]
    assert result["status"] == "unknown"
    assert result["observed_at"] is None
    assert value == before


def test_projection_is_self_or_explicitly_shared_parent_only_and_contains_no_source_data():
    value = state()
    options = source_options(
        owner="person.owner",
        adult="device_tracker.private_canary",
        child="person.child",
    )
    sync(value, options)
    for member_id in ("owner", "adult", "child"):
        enable(value, member_id)
    assert select_sources(value, value["members"]["child"], options) == {"child": "person.child"}
    assert set(select_sources(value, value["members"]["parent"], options)) == {
        "owner",
        "adult",
        "child",
    }
    observations = {
        "owner": {"state": "home", "observed_at": NOW},
        "adult": {"state": "Secret Work Zone", "observed_at": NOW},
        "child": {"state": "not_home", "observed_at": NOW},
    }
    before = deepcopy(value)
    adult = view(value, value["members"]["adult"], options, observations, NOW)
    assert adult["self"]["status"] == "reported_away"
    assert adult["shared"] == []
    child = view(value, value["members"]["child"], options, observations, NOW)
    assert child["self"]["member"] == "child" and child["shared"] == []
    parent = view(value, value["members"]["parent"], options, observations, NOW)
    assert parent["self"]["enabled"] is False
    assert {row["member"] for row in parent["shared"]} == {"owner", "adult", "child"}
    guest = view(value, value["members"]["guest"], options, observations, NOW)
    assert guest == {"self": None, "shared": []}
    serialized = repr({"adult": adult, "child": child, "parent": parent, "guest": guest})
    for secret in ("private_canary", "device_tracker", "person.", "Secret Work Zone"):
        assert secret not in serialized
    assert value == before


def test_disabled_or_malformed_options_and_state_never_select_or_leak_last_value():
    value = state()
    options = source_options(adult="person.adult")
    sync(value, options)
    receipt = enable(value, "adult")
    handle(
        context(value, "adult"),
        "access_set",
        access_payload(
            value,
            "adult",
            subscription_revision=receipt["revision"],
            enabled=False,
        ),
    )
    assert select_sources(value, value["members"]["adult"], options) == {}
    own = view(
        value,
        value["members"]["adult"],
        options,
        {"adult": {"state": "home", "observed_at": NOW}},
        NOW,
    )["self"]
    assert own["enabled"] is False and own["reason"] == "not_shared"
    malformed = {"presence_sources": {"adult": {"entity_id": "person.adult"}}}
    assert select_sources(value, value["members"]["adult"], malformed) == {}
    assert (
        view(value, value["members"]["adult"], malformed, {}, NOW)["self"]["reason"]
        == "unconfigured"
    )


def test_empty_additive_bucket_and_removed_source_have_no_enable_control():
    value = state()
    value["presence"] = {}
    options = source_options(adult="person.adult")
    assert select_sources(value, value["members"]["adult"], options) == {}
    own = view(value, value["members"]["adult"], options, {}, NOW)["self"]
    assert own["can_edit"] is False and own["reason"] == "unconfigured"
    with pytest.raises(DomainError, match="conflict"):
        enable(value, "adult")
    sync(value, options)
    enable(value, "adult")
    options["presence_sources"]["adult"] = {
        "revision": 2,
        "member_revision": 3,
        "status": "removed",
    }
    sync(value, options)
    own = view(value, value["members"]["adult"], options, {}, NOW)["self"]
    assert own["can_edit"] is False and own["reason"] == "unconfigured"
    assert own["enabled"] is False
