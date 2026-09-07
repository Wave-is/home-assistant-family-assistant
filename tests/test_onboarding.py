"""Pure guided-onboarding readiness contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from string import Formatter

import pytest

from custom_components.family_assistant.domain.engine import new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.onboarding import item, readiness


def state():
    return new_state(
        "ha-owner",
        "Synthetic household",
        "en",
        ["shopping", "tasks", "alarms", "court"],
        timezone="Europe/Kyiv",
    )


def test_minimal_household_is_ready_without_optional_services():
    report = readiness(state(), {}, "owner")

    assert report["schema"] == 1
    assert [row["key"] for row in report["items"]] == [
        "household",
        "members",
        "modules",
        "telegram",
        "models",
        "siren",
    ]
    assert item(report, "household")["status"] == "ready"
    assert item(report, "members") == {
        "key": "members",
        "status": "ready",
        "action": "member",
        "counts": {"active": 1, "ha_linked": 1, "telegram_linked": 0},
    }
    assert item(report, "modules")["counts"] == {"enabled": 4}
    assert item(report, "telegram")["status"] == "off"
    assert item(report, "models")["status"] == "off"
    assert item(report, "siren")["status"] == "optional"


def test_unlinked_template_member_is_attention_not_a_required_second_person():
    current = state()
    current["members"]["child"] = {
        "id": "child",
        "name": "Child",
        "role": "child",
        "language": "en",
        "active": True,
        "revision": 1,
        "ha_user_id": None,
        "aliases": [],
    }

    report = readiness(current, {}, "owner")

    assert item(report, "members")["status"] == "attention"
    assert item(report, "members")["counts"]["active"] == 2
    assert item(report, "members")["counts"]["ha_linked"] == 1


def test_external_statuses_are_structural_and_output_contains_no_values():
    current = state()
    current["settings"]["modules"].append("conversation")
    current["members"]["owner"]["telegram_id"] = 77112233
    current["telegram"] = {"group_id": -99887766, "group_name": "PRIVATE-GROUP-CANARY"}
    options = {
        "telegram": {
            "enabled": True,
            "token": "SECRET-TOKEN-CANARY",
            "bot": {"id": 123456, "username": "PRIVATE-BOT-CANARY"},
        },
        "conversation": {
            "enabled": True,
            "primary": {
                "url": "https://PRIVATE-PROVIDER-CANARY.invalid",
                "model": "PRIVATE-MODEL-CANARY",
                "api_key": "SECRET-MODEL-KEY-CANARY",
            },
            "search": {"url": "https://PRIVATE-SEARCH-CANARY.invalid"},
        },
        "alarm_devices": {
            "owner": {
                "entity_id": "siren.private_entity_canary",
                "confirmed": True,
                "volume": 0.5,
            }
        },
    }

    report = readiness(
        current,
        options,
        "owner",
        {"telegram_ready": True, "assistant_ready": True},
    )

    assert item(report, "telegram")["status"] == "ready"
    assert item(report, "telegram")["counts"] == {"private_links": 1, "group_linked": 1}
    assert item(report, "models")["status"] == "ready"
    assert item(report, "models")["counts"] == {"search_enabled": 1}
    assert item(report, "siren")["status"] == "ready"
    encoded = json.dumps(report, sort_keys=True)
    for canary in (
        "SECRET",
        "PRIVATE",
        "77112233",
        "99887766",
        "123456",
        "siren.private_entity_canary",
    ):
        assert canary not in encoded


def test_enabled_external_services_need_saved_shape_and_current_runtime():
    current = state()
    current["settings"]["modules"].append("conversation")
    options = {
        "telegram": {"enabled": True, "token": "token", "bot": {"id": 1, "username": "b"}},
        "conversation": {
            "enabled": True,
            "primary": {"url": "https://model.invalid", "model": "m"},
        },
    }

    report = readiness(current, options, "owner")
    assert item(report, "telegram")["status"] == "attention"
    assert item(report, "models")["status"] == "attention"

    malformed = deepcopy(options)
    malformed["telegram"]["enabled"] = "yes"
    malformed["conversation"]["primary"] = {"url": "", "model": "m"}
    report = readiness(
        current,
        malformed,
        "owner",
        {"telegram_ready": True, "assistant_ready": True},
    )
    assert item(report, "telegram")["status"] == "attention"
    assert item(report, "models")["status"] == "attention"


def test_siren_is_local_metadata_only_and_flags_stale_member_binding():
    current = state()
    report = readiness(
        current,
        {
            "alarm_devices": {
                "removed-member": {
                    "entity_id": "siren.exists_but_must_not_be_read",
                    "confirmed": True,
                }
            }
        },
        "owner",
    )
    assert item(report, "siren")["status"] == "attention"
    assert item(report, "siren")["counts"] == {"bindings": 0}

    current["settings"]["modules"].remove("alarms")
    report = readiness(current, {"alarm_devices": object()}, "owner")
    assert item(report, "siren")["status"] == "off"


@pytest.mark.parametrize("change", ["role", "active", "missing"])
def test_current_owner_authority_is_required(change):
    current = state()
    if change == "role":
        current["members"]["owner"]["role"] = "parent"
    elif change == "active":
        current["members"]["owner"]["active"] = False
    else:
        current["members"].pop("owner")

    with pytest.raises(DomainError) as error:
        readiness(current, {}, "owner")
    assert error.value.code == "forbidden"


def test_malformed_current_state_fails_closed_without_returning_raw_values():
    current = state()
    current["settings"]["timezone"] = "PRIVATE-ZONE-CANARY"
    current["settings"]["modules"] = ["alarms", "unknown-secret-module"]
    current["members"]["broken"] = {"PRIVATE-MEMBER-CANARY": "value", "active": True}

    report = readiness(current, {"alarm_devices": []}, "owner", {"unexpected": True})

    assert item(report, "household")["status"] == "attention"
    assert item(report, "members")["status"] == "attention"
    assert item(report, "modules")["status"] == "attention"
    assert "PRIVATE" not in json.dumps(report)

    report = readiness(state(), [], "owner")
    assert all(row["status"] == "attention" for row in report["items"][3:])


def test_item_rejects_malformed_or_ambiguous_reports():
    with pytest.raises(DomainError):
        item({}, "members")
    with pytest.raises(DomainError):
        item({"schema": 1, "items": [{"key": "members", "status": "ready"}] * 2}, "members")


def test_guided_translation_keys_and_placeholders_match_in_all_languages():
    package = Path(__file__).resolve().parents[1] / "custom_components" / "family_assistant"
    paths = [package / "strings.json"] + [
        package / "translations" / f"{language}.json" for language in ("en", "ru", "uk")
    ]
    expected_placeholders = {
        "household_status",
        "members_status",
        "modules_status",
        "telegram_status",
        "models_status",
        "siren_status",
        "active_members",
        "ha_linked_members",
        "telegram_linked_members",
        "enabled_modules",
        "private_chats",
        "group_links",
        "search_enabled",
        "siren_bindings",
    }
    expected_menu = {
        "general",
        "member",
        "telegram",
        "telegram_member",
        "telegram_group",
        "conversation",
        "search",
        "alarm_device",
        "guided_finish",
    }
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        guided = document["options"]["step"]["guided_onboarding"]
        placeholders = {
            field_name
            for _literal, field_name, _format_spec, _conversion in Formatter().parse(
                guided["description"]
            )
            if field_name
        }
        assert placeholders == expected_placeholders
        assert set(guided["menu_options"]) == expected_menu
        assert set(document["selector"]["onboarding_status"]["options"]) == {
            "ready",
            "attention",
            "optional",
            "off",
        }
        assert "guided_finished" in document["options"]["abort"]
