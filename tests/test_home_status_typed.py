"""Typed read-only status compatibility; synthetic data and no HA/device I/O."""

from copy import deepcopy
from datetime import UTC, timedelta
from types import SimpleNamespace

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.home_status import config, facts
from custom_components.family_assistant.home_status.copy import COPY, render


def source(domain="sensor"):
    return {
        "id": "reading",
        "label": "Synthetic typed reading",
        "entity_id": f"{domain}.synthetic",
        "registry_id": "synthetic-registry",
        "section": "group",
        "group_id": "group_0",
        "metric": None,
        "roles": ["owner"],
        "active_states": [],
    }


def configuration(count, reading=None):
    return {
        "revision": 1,
        "max_age_seconds": 300,
        "groups": [
            {"id": f"group_{i}", "title": f"Group {i}", "roles": ["owner"]} for i in range(count)
        ],
        "sources": [reading or source()],
    }


def normalize(now, domain, state, **attrs):
    observed = SimpleNamespace(
        state=state,
        last_reported=now,
        attributes={
            "entity_picture": "PRIVATE_IMAGE_CANARY",
            "event_type": "PRIVATE_EVENT_CANARY",
            "access_token": "PRIVATE_TOKEN_CANARY",
            **attrs,
        },
    )
    return facts.normalize(source(domain), observed, now, 300)


@pytest.mark.parametrize("count", [8, 13, 32])
def test_group_capacity_preserves_order_and_scope(count):
    original = configuration(count)
    original["sources"][0]["group_id"] = f"group_{count - 1}"
    assert config.validate(original) == original
    assert config.visible_sources(original, "owner", config.request("group", f"group_{count - 1}"))
    assert config.visible_sources(original, "child", config.request()) == []
    with pytest.raises(DomainError):
        config.validate(configuration(33))


@pytest.mark.parametrize("domain", ["weather", "camera"])
def test_group_enums_are_localized_and_cannot_be_activity_sources(now, domain):
    reading = source(domain)
    assert config.validate(configuration(13, reading))["sources"] == [reading]
    for state in config.GROUP_STATES[domain]:
        row = normalize(now, domain, state)
        assert row["quality"] == "ok" and row["reported_state"] == state
        assert row["active"] is None and "PRIVATE_" not in repr(row)
        for language, labels in COPY.items():
            report = {
                "generated_at": now.isoformat(),
                "energy": [],
                "active": [],
                "groups": [{"title": "Group", "rows": [row]}],
            }
            assert labels["state_" + state] in render(report, language)
        changed = deepcopy(reading)
        changed.update(section="active", group_id=None, active_states=[state])
        with pytest.raises(DomainError):
            config.validate(configuration(13, changed))
    assert normalize(now, domain, "PRIVATE_STATE_CANARY")["reported_state"] is None


@pytest.mark.parametrize("domain", ["event", "sensor"])
def test_typed_timestamp_only_and_no_private_payload(now, domain):
    stamp = (now - timedelta(days=2)).astimezone(UTC)
    row = normalize(now, domain, stamp.isoformat(), device_class="timestamp")
    assert row["reported_timestamp"] == stamp.isoformat()
    assert row["quality"] == "ok" and row["active"] is None
    assert "PRIVATE_" not in repr(row)
    for language in COPY:
        assert stamp.strftime("%Y-%m-%d %H:%M:%S UTC") in render(
            {
                "generated_at": now.isoformat(),
                "energy": [],
                "active": [],
                "groups": [{"title": "Group", "rows": [row]}],
            },
            language,
        )
    future = (now + timedelta(hours=1)).isoformat()
    future_row = normalize(now, domain, future, device_class="timestamp")
    assert future_row["quality"] == ("invalid_state" if domain == "event" else "ok")


@pytest.mark.parametrize(
    "state",
    [
        "PRIVATE_STATE_CANARY",
        "2026-09-13",
        "2026-09-13T12:00:00",
        "2026-02-30T12:00:00Z",
        "2026-09-13 12:00:00Z",
        "2026-09-13T12:00:00+99:00",
        "2026-09-13T12:00:00Z<script>",
        None,
        [],
        {},
        "9999-12-31T23:00:00-23:00",
    ],
)
def test_timestamp_invalid_types_and_offsets_never_leak(now, state):
    row = normalize(now, "event", state)
    assert row["quality"] == "invalid_state" and row["reported_timestamp"] is None
    assert "PRIVATE_" not in repr(row)


@pytest.mark.parametrize(
    "domain,state,attrs",
    [
        ("event", "2026-09-01T12:00:00Z", {}),
        ("weather", "sunny", {}),
        ("camera", "recording", {}),
        ("sensor", "12", {}),
    ],
)
def test_stale_restored_unknown_are_not_released_as_current(now, domain, state, attrs):
    for stale, restored in [(True, False), (False, True)]:
        observed = SimpleNamespace(
            state=state,
            last_reported=now - timedelta(seconds=301 if stale else 0),
            attributes={**attrs, "restored": restored},
        )
        row = facts.normalize(source(domain), observed, now, 300)
        assert row["quality"] == ("stale" if stale else "restored")
        assert row["reported_timestamp"] is None and row["reported_state"] is None
        assert row["value"] is None
    for missing in ["unknown", "unavailable"]:
        assert normalize(now, domain, missing)["quality"] == missing


@pytest.mark.parametrize(
    "state,unit,quality,value",
    [
        ("0", None, "ok", 0),
        ("12", "", "ok", 12),
        ("1.5", None, "ok", 1.5),
        ("PRIVATE_STATE_CANARY", None, "invalid_value", None),
        ("nan", None, "invalid_value", None),
        ("1e999", None, "invalid_value", None),
        ("17", "PRIVATE_UNIT_CANARY", "invalid_unit", None),
    ],
)
def test_unitless_numeric_sources_do_not_admit_arbitrary_text(now, state, unit, quality, value):
    row = normalize(now, "sensor", state, unit_of_measurement=unit)
    assert row["quality"] == quality and row["value"] == value
    assert "PRIVATE_" not in repr(row)
    assert normalize(now, "sensor", "12", device_class="power")["quality"] == "invalid_unit"
