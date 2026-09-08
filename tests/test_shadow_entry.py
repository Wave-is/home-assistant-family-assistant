"""Independent persistent entry seal cannot silently become an ordinary family."""

from copy import deepcopy
from types import MappingProxyType

import pytest
from test_shadow_reverify import candidate

from custom_components.family_assistant.domain.engine import new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.migration.shadow_entry import (
    KEY,
    entry_marker,
    validate_entry_state,
)


def sealed():
    original, target = candidate()
    state = original.private_state()
    return state, {
        "owner_user_id": target["members"]["owner"]["ha_user_id"],
        "modules": [],
        KEY: entry_marker(state, original.summary()["fingerprint"]),
    }


def test_exact_shadow_and_frozen_config_entry_data_are_read_only_without_changes():
    state, data = sealed()
    before = deepcopy(state), deepcopy(data)
    assert validate_entry_state(MappingProxyType(data), state)
    assert validate_entry_state(dict(data, migration_shadow=MappingProxyType(data[KEY])), state)
    assert (state, data) == before


@pytest.mark.parametrize("state", [None, new_state("synthetic-owner", "Synthetic family")])
def test_ordinary_entry_creation_and_reload_are_unchanged(state):
    assert validate_entry_state({"owner_user_id": "synthetic-owner"}, state) is False


@pytest.mark.parametrize(
    "fault",
    [
        "missing_store",
        "empty_store",
        "ordinary_store",
        "missing_seal",
        "null_seal",
        "empty_seal",
        "boolean_version",
        "wrong_version",
        "wrong_mode",
        "extra_field",
        "wrong_hash",
        "hash_type",
        "removed_state_marker",
        "removed_archive",
        "schema",
        "changed_task",
        "changed_owner",
        "enabled_modules",
        "owner_binding",
        "modules",
        "raw_string",
        "null_data",
        "archive_only",
    ],
)
def test_missing_or_changed_shadow_cannot_fall_through_to_blank_household(fault):
    state, data = sealed()
    if fault == "missing_store":
        state = None
    elif fault == "empty_store":
        state = {}
    elif fault == "ordinary_store":
        state = new_state("synthetic-owner", "Synthetic family")
    elif fault == "missing_seal":
        data.pop(KEY)
    elif fault == "null_seal":
        data[KEY] = None
    elif fault == "empty_seal":
        data[KEY] = {}
    elif fault == "boolean_version":
        data[KEY]["version"] = True
    elif fault == "wrong_version":
        data[KEY]["version"] = 2
    elif fault == "wrong_mode":
        data[KEY]["mode"] = "active"
    elif fault == "extra_field":
        data[KEY]["extra"] = "private"
    elif fault == "wrong_hash":
        data[KEY]["fingerprint"] = "0" * 64
    elif fault == "hash_type":
        data[KEY]["fingerprint"] = 17
    elif fault == "removed_state_marker":
        state.pop(KEY)
    elif fault == "removed_archive":
        state.pop("migration_archive")
    elif fault == "schema":
        state["schema_version"] = 1
    elif fault == "changed_task":
        state["tasks"]["T000004"]["title"] = "Synthetic changed title"
    elif fault == "changed_owner":
        state["members"]["owner"]["revision"] += 1
    elif fault == "enabled_modules":
        state["settings"]["modules"] = ["alarms"]
    elif fault == "owner_binding":
        data["owner_user_id"] = "another-user"
    elif fault == "modules":
        data["modules"] = ["alarms"]
    elif fault == "raw_string":
        state = "PRIVATE DAMAGED STORE"
    elif fault == "null_data":
        data = None
    elif fault == "archive_only":
        data.pop(KEY)
        state = {"migration_archive": {}}
    with pytest.raises(DomainError, match="^migration_shadow_invalid$"):
        validate_entry_state(data, state)


@pytest.mark.parametrize("value", [None, "", True, 1, "X" * 64, "a" * 63, "a" * 65])
def test_seal_fingerprint_format_is_strict(value):
    state, _ = sealed()
    with pytest.raises(DomainError, match="^migration_shadow_invalid$"):
        entry_marker(state, value)


def test_seal_factory_does_not_leak_nonfinite_or_unencodable_private_data():
    for value in (float("nan"), "\ud800"):
        state, data = sealed()
        state["migration_archive"]["unexpected"] = value
        with pytest.raises(DomainError, match="^migration_shadow_invalid$"):
            entry_marker(state, data[KEY]["fingerprint"])
