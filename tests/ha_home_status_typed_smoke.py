"""Actual Options/registry/Store paths for typed status sources, no device I/O."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta


async def verify_typed_home_status(hass, entry, owner, child_user):
    from ha_home_status_smoke import _group, _read, _settings, _source
    from homeassistant.helpers import entity_registry
    from homeassistant.helpers.storage import Store

    for index in range(1, 13):
        await _group(hass, entry, owner, key=f"synthetic_group_{index}")
    assert len(entry.options["home_status"]["groups"]) == 13
    registry = entity_registry.async_get(hass)
    now = datetime.now(UTC)
    event_stamp = (now - timedelta(days=1)).isoformat()
    planned_stamp = (now + timedelta(hours=2)).isoformat()
    expected = [
        ("weather", "sunny", {}, "reported_state", "sunny"),
        ("camera", "recording", {}, "reported_state", "recording"),
        ("event", event_stamp, {}, "reported_timestamp", event_stamp),
        (
            "sensor",
            planned_stamp,
            {"device_class": "timestamp"},
            "reported_timestamp",
            planned_stamp,
        ),
        ("sensor", "12", {}, "value", 12),
    ]
    for index, (domain, state, attrs, _, _) in enumerate(expected):
        row = registry.async_get_or_create(
            domain,
            "family_assistant",
            f"synthetic-typed-status-{index}",
            suggested_object_id=f"synthetic_typed_status_{index}",
        )
        hass.states.async_set(
            row.entity_id,
            state,
            {
                **attrs,
                "entity_picture": "PRIVATE_TYPED_IMAGE_CANARY",
                "event_type": "PRIVATE_TYPED_EVENT_CANARY",
                "access_token": "PRIVATE_TYPED_TOKEN_CANARY",
            },
        )
        await _source(
            hass, entry, owner, row.entity_id, "group:synthetic_group_12", f"Typed {index}"
        )
    exact = deepcopy(dict(entry.options))
    await _settings(hass, entry, owner)
    assert dict(entry.options) == exact
    result = await _read(hass, entry, owner, 500, section="group", group_id="synthetic_group_12")
    assert result["success"], result
    rows = result["result"]["groups"][0]["rows"]
    assert len(rows) == 5, result
    for row, (_, _, _, field, value) in zip(rows, expected, strict=True):
        assert row["quality"] == "ok" and row[field] == value, row
        assert row["active"] is None
    assert "PRIVATE_TYPED_" not in repr(result)
    child = await _read(
        hass, entry, child_user, 501, section="group", group_id="synthetic_group_12"
    )
    assert child["success"] and child["result"]["groups"] == [], child
    assert "Typed 0" not in repr(child) and "PRIVATE_TYPED_" not in repr(child)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await entry.runtime_data.scheduler.stop()
    assert dict(entry.options) == exact
    after = await _read(hass, entry, owner, 502, section="group", group_id="synthetic_group_12")
    assert after["success"], after
    assert len(after["result"]["groups"][0]["rows"]) == len(rows)
    for actual, previous in zip(after["result"]["groups"][0]["rows"], rows, strict=True):
        assert {key: value for key, value in actual.items() if key != "report_age_seconds"} == {
            key: value for key, value in previous.items() if key != "report_age_seconds"
        }
    stored = await Store(hass, 1, f"family_assistant.{entry.entry_id}").async_load()
    assert "PRIVATE_TYPED_" not in repr(stored) and event_stamp not in repr(stored)
    print(
        "PASS: native typed home status: 13 groups, weather/camera enums, event/planned timestamp, "
        "unitless count, no-op Options, current child ACL and reload; no media or device services"
    )
