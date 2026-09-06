"""Tests for pure routine validation."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.routine_validation import (
    condition,
    configuration,
    entities,
    normalize_template,
    validate_allowlist,
    validate_modes,
)
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def routine_ctx():
    now = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    state = {
        "settings": {
            "routines": {
                "modes": ["normal"],
                "entity_allowlist": ["binary_sensor.front_door", "sensor.kitchen_temp"],
                "revision": 3,
            }
        },
        "members": {
            "parent": {"id": "parent", "name": "Parent", "role": "parent", "active": True},
            "child": {"id": "child", "name": "Child", "role": "child", "active": True},
            "sibling": {"id": "sibling", "name": "Sibling", "role": "child", "active": True},
            "guest": {"id": "guest", "name": "Guest", "role": "guest", "active": True},
            "inactive_member": {
                "id": "inactive_member",
                "name": "Inactive",
                "role": "child",
                "active": False,
            },
        },
        "sequences": {},
        "outbox": {},
    }
    return Context(state, {"id": "parent", "role": "parent"}, now, "op_test")


def test_configuration_defaults_and_deepcopy():
    state_empty = {"settings": {}}
    cfg = configuration(state_empty)
    assert cfg == {"modes": ["normal"], "entity_allowlist": [], "revision": 0}

    # Verify mutating result does not affect subsequent calls or state
    cfg["modes"].append("holidays")
    cfg["entity_allowlist"].append("switch.test")
    cfg2 = configuration(state_empty)
    assert cfg2 == {"modes": ["normal"], "entity_allowlist": [], "revision": 0}

    # Verify with populated state and deepcopy isolation
    state_custom = {
        "settings": {
            "routines": {
                "modes": ["vacation"],
                "entity_allowlist": ["light.living_room"],
                "revision": 5,
            }
        }
    }
    cfg3 = configuration(state_custom)
    assert cfg3 == {
        "modes": ["vacation"],
        "entity_allowlist": ["light.living_room"],
        "revision": 5,
    }
    cfg3["modes"].append("ill")
    assert state_custom["settings"]["routines"]["modes"] == ["vacation"]


def test_entities_recursive():
    cond = {
        "kind": "all",
        "conditions": [
            {"kind": "mode", "mode": "normal"},
            {"kind": "entity_state", "entity_id": "binary_sensor.door", "state": "on"},
            {
                "kind": "any",
                "conditions": [
                    {"kind": "entity_state", "entity_id": "switch.heater", "state": "off"},
                    {"kind": "entity_state", "entity_id": "binary_sensor.door", "state": "off"},
                ],
            },
        ],
    }
    found = entities(cond)
    assert found == {"binary_sensor.door", "switch.heater"}
    assert entities(None) == set()
    assert entities({"kind": "mode", "mode": "normal"}) == set()


def test_condition_validation_and_allowlist():
    assert condition(None, ["binary_sensor.door"]) is None

    valid_cond = {
        "kind": "entity_state",
        "entity_id": "binary_sensor.front_door",
        "state": "on",
    }
    norm = condition(valid_cond, ["binary_sensor.front_door", "sensor.kitchen_temp"])
    assert norm["entity_id"] == "binary_sensor.front_door"

    # Forbidden entity
    with pytest.raises(DomainError) as exc_info:
        condition(valid_cond, ["sensor.kitchen_temp"])
    assert exc_info.value.code == "forbidden"

    # Nested forbidden entity
    nested_cond = {
        "kind": "all",
        "conditions": [
            {"kind": "mode", "mode": "normal"},
            {"kind": "entity_state", "entity_id": "switch.forbidden", "state": "on"},
        ],
    }
    with pytest.raises(DomainError) as exc_info:
        condition(nested_cond, ["binary_sensor.front_door"])
    assert exc_info.value.code == "forbidden"

    # Malformed condition structure
    with pytest.raises(DomainError) as exc_info:
        condition({"kind": "unknown_kind"}, ["binary_sensor.front_door"])
    assert exc_info.value.code == "invalid_field"


def test_validate_modes():
    # Valid modes
    assert validate_modes(["normal"]) == ["normal"]
    assert validate_modes(["holidays", "vacation"]) == ["holidays", "vacation"]
    assert validate_modes(["vacation", "holidays"]) == ["holidays", "vacation"]
    assert validate_modes(["ill", "guests", "holidays", "vacation"]) == [
        "guests",
        "holidays",
        "ill",
        "vacation",
    ]

    # Normal exclusive
    with pytest.raises(DomainError) as exc_info:
        validate_modes(["normal", "holidays"])
    assert exc_info.value.code == "invalid_field"
    assert exc_info.value.field == "modes"

    # Duplicates rejected
    with pytest.raises(DomainError) as exc_info:
        validate_modes(["holidays", "holidays"])
    assert exc_info.value.code == "invalid_field"

    # Empty list or too large
    with pytest.raises(DomainError) as exc_info:
        validate_modes([])
    assert exc_info.value.code == "invalid_field"

    with pytest.raises(DomainError) as exc_info:
        validate_modes(["normal", "holidays", "guests", "ill", "vacation", "extra"])
    assert exc_info.value.code == "invalid_field"

    # Invalid mode string or type
    for bad in ["other", 123, True, None, "NORMAL"]:
        with pytest.raises(DomainError) as exc_info:
            validate_modes([bad])
        assert exc_info.value.code == "invalid_field"

    with pytest.raises(DomainError) as exc_info:
        validate_modes("normal")
    assert exc_info.value.code == "invalid_field"


def test_validate_allowlist():
    # Valid
    assert validate_allowlist([]) == []
    assert validate_allowlist(["binary_sensor.door", "switch.light_1"]) == [
        "binary_sensor.door",
        "switch.light_1",
    ]

    # Distinct / duplicates reject
    with pytest.raises(DomainError) as exc_info:
        validate_allowlist(["binary_sensor.door", "binary_sensor.door"])
    assert exc_info.value.code == "invalid_field"
    assert exc_info.value.field == "entity_allowlist"

    # Lowercase regex IDs <= 255
    with pytest.raises(DomainError):
        validate_allowlist(["Binary_Sensor.door"])
    with pytest.raises(DomainError):
        validate_allowlist(["invalid_id_without_domain"])
    with pytest.raises(DomainError):
        validate_allowlist(["domain.entity.extra"])
    with pytest.raises(DomainError):
        validate_allowlist(["domain." + "a" * 255])

    # Reject non-list types: dict, bool, string, etc.
    for bad in [{}, True, False, "binary_sensor.door", 123, None]:
        with pytest.raises(DomainError) as exc_info:
            validate_allowlist(bad)
        assert exc_info.value.code == "invalid_field"

    # Bounded 0..50
    too_many = [f"sensor.item_{i}" for i in range(51)]
    with pytest.raises(DomainError) as exc_info:
        validate_allowlist(too_many)
    assert exc_info.value.code == "invalid_field"


def test_normalize_template_happy_path_and_immutability(routine_ctx):
    raw = {
        "title": "Morning Routine",
        "description": "Routine description",
        "assignees": ["child", "sibling"],
        "enabled": True,
        "rule": {
            "frequency": "daily",
            "start_date": "2026-09-01",
            "time": "07:00",
            "timezone": "UTC",
        },
        "skip_when": {"kind": "mode", "mode": "vacation"},
        "steps": [
            {
                "title": "Brush teeth",
                "offset_minutes": 0,
                "confirmation": "manual",
            },
            {
                "title": "Check kitchen sensor",
                "offset_minutes": 10,
                "confirmation": "entity_state",
                "completion_condition": {
                    "kind": "entity_state",
                    "entity_id": "sensor.kitchen_temp",
                    "state": "normal",
                },
                "escalate_minutes": 30,
            },
            {
                "title": "Leave for school",
                "offset_minutes": 20,
                "confirmation": "none",
            },
        ],
        "extra_custom_key": "custom_value",
    }
    raw_clone = deepcopy(raw)

    result = normalize_template(routine_ctx, raw)

    # Input immutability check
    assert raw == raw_clone
    assert result is not raw

    # Defaults applied for step 1
    assert result["steps"][0]["confirmation"] == "manual"
    assert result["steps"][0]["completion_condition"] is None
    assert result["steps"][0]["skip_when"] is None
    assert result["steps"][0]["escalate_minutes"] == 15

    # Step 2
    assert result["steps"][1]["confirmation"] == "entity_state"
    assert result["steps"][1]["completion_condition"]["entity_id"] == "sensor.kitchen_temp"
    assert result["steps"][1]["escalate_minutes"] == 30

    # Step 3
    assert result["steps"][2]["confirmation"] == "none"
    assert result["steps"][2]["completion_condition"] is None

    # Extra top level keys preserved
    assert result["extra_custom_key"] == "custom_value"


def test_normalize_template_assignees_validation(routine_ctx):
    base = {
        "title": "Routine",
        "enabled": True,
        "assignees": ["child"],
        "steps": [{"title": "Step 1"}],
    }

    # Empty assignees
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "assignees": []})
    assert exc_info.value.field == "assignees"

    # Duplicate assignees
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "assignees": ["child", "child"]})
    assert exc_info.value.field == "assignees"

    # Guest assignee
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "assignees": ["guest"]})
    assert exc_info.value.field == "assignees"

    # Inactive member
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "assignees": ["inactive_member"]})
    assert exc_info.value.code in {"unknown_member", "invalid_field"}

    # Unknown member
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "assignees": ["unknown_id"]})
    assert exc_info.value.code in {"unknown_member", "invalid_field"}

    # More than 20 assignees
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "assignees": [f"user_{i}" for i in range(21)]})
    assert exc_info.value.field == "assignees"


def test_normalize_template_strict_booleans_and_integers(routine_ctx):
    base = {
        "title": "Routine",
        "enabled": True,
        "assignees": ["child"],
        "steps": [{"title": "Step 1"}],
    }

    # Enabled strict boolean (reject 1, 0, "true", None)
    for bad_bool in [1, 0, "true", None, 1.0]:
        with pytest.raises(DomainError) as exc_info:
            normalize_template(routine_ctx, {**base, "enabled": bad_bool})
        assert exc_info.value.field == "enabled"

    # Step offset_minutes strict integer (reject bool, float, negative, > 10080)
    for bad_offset in [True, False, 1.5, -1, 10081, "10"]:
        with pytest.raises(DomainError) as exc_info:
            normalize_template(
                routine_ctx,
                {**base, "steps": [{"title": "Step 1", "offset_minutes": bad_offset}]},
            )
        assert exc_info.value.field == "offset_minutes"

    # Step escalate_minutes strict integer (reject bool, float, 0, > 1440)
    for bad_esc in [True, False, 0, 1.5, 1441, "15"]:
        with pytest.raises(DomainError) as exc_info:
            normalize_template(
                routine_ctx,
                {**base, "steps": [{"title": "Step 1", "escalate_minutes": bad_esc}]},
            )
        assert exc_info.value.field == "escalate_minutes"


def test_normalize_template_step_confirmation_and_completion_rules(routine_ctx):
    base = {
        "title": "Routine",
        "enabled": True,
        "assignees": ["child"],
    }

    # entity_state confirmation requires completion_condition with entity_state node
    with pytest.raises(DomainError) as exc_info:
        normalize_template(
            routine_ctx,
            {**base, "steps": [{"title": "Step 1", "confirmation": "entity_state"}]},
        )
    assert exc_info.value.field == "completion_condition"

    with pytest.raises(DomainError) as exc_info:
        normalize_template(
            routine_ctx,
            {
                **base,
                "steps": [
                    {
                        "title": "Step 1",
                        "confirmation": "entity_state",
                        "completion_condition": {"kind": "mode", "mode": "normal"},
                    }
                ],
            },
        )
    assert exc_info.value.field == "completion_condition"

    # manual confirmation cannot have completion_condition
    with pytest.raises(DomainError) as exc_info:
        normalize_template(
            routine_ctx,
            {
                **base,
                "steps": [
                    {
                        "title": "Step 1",
                        "confirmation": "manual",
                        "completion_condition": {
                            "kind": "entity_state",
                            "entity_id": "sensor.kitchen_temp",
                            "state": "normal",
                        },
                    }
                ],
            },
        )
    assert exc_info.value.field == "completion_condition"

    # none confirmation cannot have completion_condition
    with pytest.raises(DomainError) as exc_info:
        normalize_template(
            routine_ctx,
            {
                **base,
                "steps": [
                    {
                        "title": "Step 1",
                        "confirmation": "none",
                        "completion_condition": {
                            "kind": "entity_state",
                            "entity_id": "sensor.kitchen_temp",
                            "state": "normal",
                        },
                    }
                ],
            },
        )
    assert exc_info.value.field == "completion_condition"


def test_normalize_template_extra_step_fields_rejected(routine_ctx):
    base = {
        "title": "Routine",
        "enabled": True,
        "assignees": ["child"],
        "steps": [{"title": "Step 1", "extra_field": "disallowed"}],
    }
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, base)
    assert exc_info.value.code == "invalid_field"
    assert exc_info.value.field == "extra_field"


def test_normalize_template_steps_ordering(routine_ctx):
    # offset_minutes must be non-descending
    valid_steps = [
        {"title": "Step 1", "offset_minutes": 0},
        {"title": "Step 2", "offset_minutes": 5},
        {"title": "Step 3", "offset_minutes": 5},
        {"title": "Step 4", "offset_minutes": 10},
    ]
    res = normalize_template(
        routine_ctx,
        {"title": "Routine", "enabled": True, "assignees": ["child"], "steps": valid_steps},
    )
    assert len(res["steps"]) == 4

    descending_steps = [
        {"title": "Step 1", "offset_minutes": 10},
        {"title": "Step 2", "offset_minutes": 5},
    ]
    with pytest.raises(DomainError) as exc_info:
        normalize_template(
            routine_ctx,
            {
                "title": "Routine",
                "enabled": True,
                "assignees": ["child"],
                "steps": descending_steps,
            },
        )
    assert exc_info.value.field == "offset_minutes"


def test_normalize_template_steps_bounded_list(routine_ctx):
    base = {"title": "Routine", "enabled": True, "assignees": ["child"]}

    # 0 steps
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "steps": []})
    assert exc_info.value.field == "steps"

    # 31 steps
    too_many = [{"title": f"Step {i}", "offset_minutes": i} for i in range(31)]
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "steps": too_many})
    assert exc_info.value.field == "steps"


def test_normalize_template_title_and_description(routine_ctx):
    base = {"enabled": True, "assignees": ["child"], "steps": [{"title": "Step 1"}]}

    # Empty or missing title
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "title": ""})
    assert exc_info.value.field == "title"

    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "title": "   "})
    assert exc_info.value.field == "title"

    # Title > 255
    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "title": "a" * 256})
    assert exc_info.value.field == "title"

    # Optional description empty or <= 2000
    res_empty_desc = normalize_template(routine_ctx, {**base, "title": "T", "description": ""})
    assert res_empty_desc["description"] == ""

    res_none_desc = normalize_template(routine_ctx, {**base, "title": "T", "description": None})
    assert res_none_desc["description"] == ""

    with pytest.raises(DomainError) as exc_info:
        normalize_template(routine_ctx, {**base, "title": "T", "description": "a" * 2001})
    assert exc_info.value.field == "description"


def test_step_title_only_required_field(routine_ctx):
    raw = {
        "title": "Routine",
        "enabled": False,
        "assignees": ["child"],
        "steps": [{"title": "Step Only Title"}],
    }
    normalized = normalize_template(routine_ctx, raw)
    step = normalized["steps"][0]
    assert step["title"] == "Step Only Title"
    assert step["offset_minutes"] == 0
    assert step["confirmation"] == "manual"
    assert step["completion_condition"] is None
    assert step["skip_when"] is None
    assert step["escalate_minutes"] == 15
