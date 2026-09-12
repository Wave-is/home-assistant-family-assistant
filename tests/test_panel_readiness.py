"""Configuration facts never substitute for external-service observations."""

from copy import deepcopy

from custom_components.family_assistant.panel_readiness import capabilities, member_readiness


def test_disabled_imported_alarm_is_visible_without_any_activation(engine):
    state = engine.snapshot()
    state["settings"]["modules"] = ["alarms"]
    state["alarms"] = {
        "legacy": {
            "member": "child",
            "enabled": False,
            "profile": "gentle",
            "penalty": 0,
        }
    }
    before = deepcopy(state)
    checks = member_readiness(state, {}, list(state["members"].values()))
    child = next(row for row in checks if row["id"] == "child")
    assert child["alarms"]["issues"] == ["alarm_schedules_disabled"]
    assert child["alarms"]["total"] == 1 and child["alarms"]["enabled"] == 0
    rows = capabilities(state, {}, {}, checks)
    assert next(row for row in rows if row["id"] == "alarms")["ready"] is False
    assert state == before


def test_strict_siren_configuration_is_not_a_physical_sound_test(engine):
    state = engine.snapshot()
    state["settings"]["modules"] = ["alarms"]
    state["alarms"] = {"alarm": {"member": "child", "enabled": True, "profile": "strict"}}
    members = [state["members"]["child"]]
    missing = member_readiness(state, {}, members)[0]
    assert missing["alarms"]["issues"] == ["alarm_output_missing"]
    options = {"alarm_devices": {"child": {"entity_id": "siren.synthetic", "confirmed": True}}}
    configured = member_readiness(state, options, members)[0]
    assert configured["alarms"]["output_configured"] is True
    assert "tested" not in str(configured)


def test_school_only_counts_current_active_timetables(engine):
    state = engine.snapshot()
    state["settings"]["modules"] = ["school"]
    member = state["members"]["child"]
    state["school"] = {
        "timetables": {
            "week": {
                "member": "child",
                "member_revision": member["revision"],
                "status": "active",
            }
        }
    }
    assert member_readiness(state, {}, [member])[0]["school"]["timetables"] == 1
    state["school"]["timetables"]["week"]["status"] = "archived"
    assert member_readiness(state, {}, [member])[0]["school"]["timetables"] == 0
    state["school"]["timetables"]["week"]["status"] = "active"
    member["revision"] += 1
    assert member_readiness(state, {}, [member])[0]["school"]["issues"] == ["school_no_timetable"]


def test_service_constructed_does_not_claim_verified_provider_health(engine):
    state = engine.snapshot()
    state["settings"]["modules"] = ["conversation", "mikrotik"]
    services = {"conversation": True, "mikrotik": True}
    rows = capabilities(state, services, {}, [])
    assert all(row["ready"] is None for row in rows if row["enabled"])
    rows = capabilities(
        state, services, {"conversation": "connected", "mikrotik": "network_connected"}, []
    )
    assert all(row["ready"] is True for row in rows if row["enabled"])
    rows = capabilities(
        state,
        services,
        {"conversation": "provider_quota_exceeded", "mikrotik": "network_unavailable"},
        [],
    )
    assert all(row["ready"] is False for row in rows if row["enabled"])


def test_member_projection_does_not_inspect_an_unauthorized_sibling(engine):
    state = engine.snapshot()
    state["members"]["sibling"] = {**state["members"]["child"], "id": "sibling"}
    visible = [state["members"]["child"]]
    assert [row["id"] for row in member_readiness(state, {}, visible)] == ["child"]
