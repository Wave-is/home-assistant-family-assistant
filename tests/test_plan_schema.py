"""Actual JSON Schema and strict server validation agree on response envelopes."""

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain.validation import DomainError
from tools.evaluate_model import NOW, fixture

VALID = [
    {"kind": "answer", "text": "Here."},
    {"kind": "clarify", "text": "Which task?"},
    *({"kind": "read", "topic": topic} for topic in plans.READS),
    {"kind": "search", "query": "public astronomical event"},
    {"kind": "commands", "operations": [{"action": "tasks.revise", "payload": {"id": "T000001"}}]},
]
INVALID = [
    {"kind": "read", "topic": "court", "text": "Extra explanation"},
    {"kind": "answer", "text": "Here.", "topic": "tasks"},
    {"kind": "commands", "text": "Marked bought", "topic": "shopping"},
    {"kind": "read", "topic": "unknown"},
    {"kind": "commands", "commands": []},
    {"kind": "commands", "commands": [{"action": "settings.save", "payload": {}}]},
    {
        "kind": "commands",
        "commands": [{"action": "tasks.complete", "payload": {}, "role": "owner"}],
    },
    {"kind": "commands", "commands": [{"action": "tasks.complete", "payload": []}]},
    {"kind": "commands", "commands": [{"action": "tasks.complete", "payload": {}}] * 6},
    {"kind": "answer", "text": "x" * 3001},
    {"kind": "search", "query": "x" * 301},
    {"kind": "answer", "text": ""},
    {"kind": "answer"},
    {"kind": "read"},
    {"kind": "search"},
]


@pytest.mark.parametrize("value", VALID)
def test_valid_response_has_exactly_one_schema_branch_and_validates(value):
    Draft202012Validator.check_schema(plans.SCHEMA)
    assert Draft202012Validator(plans.SCHEMA).is_valid(value)
    assert (
        sum(Draft202012Validator(branch).is_valid(value) for branch in plans.SCHEMA["oneOf"]) == 1
    )
    expected = (
        value
        if "operations" not in value
        else {"kind": "commands", "commands": value["operations"]}
    )
    assert plans.validate(value) == expected


@pytest.mark.parametrize("value", INVALID)
def test_historical_and_cross_kind_responses_fail_both_schema_and_server(value):
    assert not Draft202012Validator(plans.SCHEMA).is_valid(value)
    with pytest.raises(DomainError, match="provider_bad_response"):
        plans.validate(value)


def test_each_kind_rejects_fields_belonging_to_another_kind():
    for value in VALID:
        for key, extra in {
            "text": "Extra",
            "topic": "court",
            "query": "Public",
            "operations": [],
        }.items():
            if key in value:
                continue
            bad = {**deepcopy(value), key: extra}
            assert not Draft202012Validator(plans.SCHEMA).is_valid(bad)
            with pytest.raises(DomainError):
                plans.validate(bad)


def test_shopping_projection_uses_real_partial_purchase_field():
    view = fixture("en").view("owner", now=NOW)
    projected = plans.projection(view)["shopping"][0]
    assert projected["quantity"] == 5 and projected["purchased"] == 2
    assert "purchased_quantity" not in projected
    assert set(projected) == {"id", "name", "quantity", "purchased", "unit", "status"}


def test_dynamic_payload_is_explicit_for_llama_grammar_not_implicit_json_schema_default():
    command = plans.SCHEMA["oneOf"][3]["properties"]["operations"]["items"]
    assert command["additionalProperties"] is False
    assert command["properties"]["payload"]["additionalProperties"] is True


def test_kind_is_first_even_when_provider_serializes_schema_keys_alphabetically():
    for branch in plans.SCHEMA["oneOf"]:
        assert sorted(branch["properties"])[0] == "kind"


def test_wire_operations_normalize_without_changing_saved_canonical_proposal_shape():
    steps = [{"action": "shopping.purchase", "payload": {"id": "S000001"}}]
    canonical = {"kind": "commands", "commands": steps}
    assert plans.validate(canonical) == canonical
    assert plans.validate({"kind": "commands", "operations": steps}) == canonical
    for invalid in (
        {**canonical, "operations": steps},
        {"kind": "read", "operations": steps},
        {"kind": "commands", "operations": steps, "text": "Claimed success"},
    ):
        with pytest.raises(DomainError):
            plans.validate(invalid)


def test_request_schema_requires_alarm_source_spelling_without_mutating_base_schema():
    before = deepcopy(plans.SCHEMA)
    request = "Поставь по будням на 09:30, по выходным на 10:30"
    schema = plans.request_schema(request)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    value = {
        "kind": "commands",
        "operations": [
            {
                "action": "alarms.save",
                "payload": {
                    "member": "child",
                    "time": "09:30",
                    "days_expression": "по будням",
                    "timezone": "UTC",
                },
            }
        ],
    }
    assert validator.is_valid(value)
    value["operations"][0]["payload"]["days_expression"] = "weekdays"
    assert not validator.is_valid(value)
    value["operations"][0]["payload"].pop("days_expression")
    assert not validator.is_valid(value)
    assert validator.is_valid(VALID[-1])
    assert plans.SCHEMA == before
    assert plans.request_schema("Clock only") != schema
