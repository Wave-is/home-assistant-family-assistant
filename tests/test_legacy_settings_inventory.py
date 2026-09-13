"""Coverage drift is distinct from runtime parity; fixtures contain no defaults."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.check_legacy_settings_inventory import declared_keys, validate

INVENTORY = json.loads(
    (Path(__file__).parents[1] / "docs/legacy-settings-inventory.json").read_text()
)


def synthetic_sources():
    return {
        name: "\n".join(f'CONF_{key.upper()} = "{key}"' for keys in groups.values() for key in keys)
        for name, groups in INVENTORY["sources"].items()
    }


def test_inventory_has_explicit_unfinished_settings_not_a_blanket_pass():
    result = validate(INVENTORY)
    assert result == {
        "status": "declarations_accounted_for",
        "source_verified": False,
        "missing": 16,
        "replaced": 10,
        "review_required": 3,
    }


def test_source_coverage_checks_every_legacy_declared_setting():
    assert validate(INVENTORY, synthetic_sources())["source_verified"]


@pytest.mark.parametrize("mutation", ["added", "removed", "renamed"])
def test_new_or_changed_legacy_settings_need_audit_not_silent_omission(mutation):
    sources = synthetic_sources()
    if mutation == "added":
        sources["family_assistant"] += '\nCONF_NEW_BEHAVIOR = "new_behavior"'
    elif mutation == "removed":
        sources["family_assistant"] = sources["family_assistant"].replace(
            'CONF_GATE_ENTITY = "gate_entity"', ""
        )
    else:
        sources["family_assistant"] = sources["family_assistant"].replace(
            '"gate_entity"', '"new_gate_entity"'
        )
    with pytest.raises(ValueError, match="legacy_configuration_coverage_changed"):
        validate(INVENTORY, sources)


def test_coverage_does_not_execute_source_or_inspect_arbitrary_defaults():
    assert declared_keys(
        'raise RuntimeError("not executed")\nCONF_X = "example"\n'
        'OTHER = "private value"\nDEFAULT = dangerous()'
    ) == {"example"}


def test_same_key_cannot_be_both_complete_and_missing():
    broken = deepcopy(INVENTORY)
    broken["sources"]["family_assistant"]["replaced"].append("gate_entity")
    with pytest.raises(ValueError, match="duplicate_inventory_key"):
        validate(broken)
