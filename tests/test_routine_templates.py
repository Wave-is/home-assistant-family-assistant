"""Tests for domain routine templates starter catalog."""

import pytest

from custom_components.family_assistant.domain.routine_templates import (
    SUPPORTED_LANGUAGES,
    templates,
)
from custom_components.family_assistant.domain.validation import DomainError


def test_supported_languages_parity_and_ids():
    expected_ids = ["morning", "evening", "school_bag"]
    assert SUPPORTED_LANGUAGES == {"en", "ru", "uk"}

    for lang in ("en", "ru", "uk"):
        catalog = templates(lang)
        assert len(catalog) == 3
        ids = [item["id"] for item in catalog]
        assert ids == expected_ids


def test_invalid_language_raises_domain_error():
    for invalid_lang in ("de", "fr", "es", "", "unknown", None, 123, [], {}):
        with pytest.raises(DomainError) as exc_info:
            templates(invalid_lang)
        assert exc_info.value.code == "invalid_field"
        assert exc_info.value.field == "language"


def test_template_and_step_shapes():
    for lang in ("en", "ru", "uk"):
        catalog = templates(lang)
        for tpl in catalog:
            assert set(tpl.keys()) == {"id", "title", "description", "steps", "skip_when"}
            assert isinstance(tpl["id"], str) and tpl["id"]
            assert isinstance(tpl["title"], str) and tpl["title"].strip()
            assert isinstance(tpl["description"], str) and tpl["description"].strip()
            assert isinstance(tpl["steps"], list)
            assert 1 <= len(tpl["steps"]) <= 5

            if tpl["id"] in ("morning", "school_bag"):
                assert tpl["skip_when"] == {
                    "kind": "any",
                    "conditions": [
                        {"kind": "mode", "mode": "holidays"},
                        {"kind": "mode", "mode": "vacation"},
                    ],
                }
            elif tpl["id"] == "evening":
                assert tpl["skip_when"] is None

            for step in tpl["steps"]:
                assert set(step.keys()) == {
                    "title",
                    "offset_minutes",
                    "confirmation",
                    "completion_condition",
                    "skip_when",
                    "escalate_minutes",
                }
                assert isinstance(step["title"], str) and step["title"].strip()
                assert step["offset_minutes"] == 0
                assert step["confirmation"] == "manual"
                assert step["completion_condition"] is None
                assert step["skip_when"] is None
                assert step["escalate_minutes"] == 15


def test_no_entities_assignees_credentials_or_ids_baked():
    disallowed_substrings = [
        "entity_id",
        "device_id",
        "chat_id",
        "person.",
        "user_",
        "token",
        "password",
        "router",
    ]

    for lang in ("en", "ru", "uk"):
        catalog = templates(lang)
        for tpl in catalog:
            serialized = str(tpl).lower()
            for forbidden in disallowed_substrings:
                assert forbidden not in serialized


def test_deep_immutability():
    # Calling templates multiple times must yield independent deep copies
    first_call = templates("en")
    second_call = templates("en")

    assert first_call == second_call
    assert first_call is not second_call

    # Mutate top-level list
    first_call.pop()
    assert len(templates("en")) == 3

    # Mutate template dictionary and nested structures
    fresh = templates("en")
    fresh[0]["title"] = "MUTATED"
    fresh[0]["steps"][0]["title"] = "MUTATED_STEP"
    fresh[0]["skip_when"]["conditions"].append({"kind": "mode", "mode": "mutated"})

    clean = templates("en")
    assert clean[0]["title"] != "MUTATED"
    assert clean[0]["steps"][0]["title"] != "MUTATED_STEP"
    assert len(clean[0]["skip_when"]["conditions"]) == 2
