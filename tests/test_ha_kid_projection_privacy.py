"""Regression tests for precise Kid Control privacy assertions in the HA smoke."""

from copy import deepcopy

import pytest
from test_kids import prepare_engine

from tests.ha_telegram_smoke import assert_child_kid_control_private

PRIVATE_IDENTIFIERS = {
    "02:11:22:33:44:55",
    "02:11:22:33:44:77",
    "02:11:22:33:44:88",
    "*3",
    "*4",
}


def child_projection():
    return {
        "can_manage": False,
        "writable": True,
        "observed_at": "2026-09-07T02:11:22+00:00",
        "profiles": [
            {
                "member": "child",
                "name": "Child profile",
                "observed": {"mon": "08:00-22:00", "disabled": "false"},
                "status": {
                    "mode": "schedule",
                    "allows": True,
                    "valid_until": "2026-09-07T02:11:59+00:00",
                },
                "device_names": ["Phone"],
                "devices": [],
            }
        ],
        "candidates": [],
        "delegations": {},
        "plans": [],
    }


def test_privacy_assertion_allows_mac_like_timestamp_prefix():
    projection = child_projection()
    assert "02:11" in str(projection)  # The former prefix assertion rejected this safe timestamp.
    assert_child_kid_control_private(projection, PRIVATE_IDENTIFIERS)


@pytest.mark.asyncio
async def test_actual_child_projection_allows_timestamp_but_omits_router_identifiers(engine, now):
    collision_time = now.replace(hour=2, minute=11, second=22)
    await prepare_engine(engine, collision_time)
    projection = engine.view("child", now=collision_time)["kid_control"]
    assert "02:11" in str(projection)
    assert_child_kid_control_private(
        projection,
        {"02:11:22:33:44:55", "*1", "*2"},
    )


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("profiles", 0, "device_names"), ["Phone", "02:11:22:33:44:55"], "identifiers"),
        (("profiles", 0, "profile_id"), "synthetic-profile", "fields"),
    ],
)
def test_privacy_assertion_detects_full_identifier_and_forbidden_field(path, value, message):
    projection = deepcopy(child_projection())
    target = projection
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(AssertionError, match=message):
        assert_child_kid_control_private(projection, PRIVATE_IDENTIFIERS)
