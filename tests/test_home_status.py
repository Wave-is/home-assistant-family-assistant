"""Real Engine projections plus strict pure factual normalization, no devices."""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.home_status import config, facts, observations
from custom_components.family_assistant.home_status.copy import COPY, render
from custom_components.family_assistant.home_status.telegram import parse


def source(entity="sensor.synthetic_power", **changes):
    return {
        "id": "power",
        "label": "Synthetic reading",
        "entity_id": entity,
        "registry_id": "registry-original",
        "section": "energy",
        "group_id": None,
        "metric": "load_power",
        "roles": ["owner", "parent"],
        "active_states": [],
        **changes,
    }


def configured(sources=None, groups=None):
    return {
        "revision": 1,
        "max_age_seconds": 300,
        "groups": groups or [],
        "sources": [source()] if sources is None else sources,
    }


def observed(now, state="2.5", **attributes):
    return SimpleNamespace(
        state=state,
        last_reported=now,
        attributes={
            "unit_of_measurement": "kW",
            "entity_picture": "PRIVATE_URL_CANARY",
            "access_token": "PRIVATE_TOKEN_CANARY",
            **attributes,
        },
    )


def harness(monkeypatch, engine, now, *, settings=None, actor="owner", denied=False):
    state = engine.snapshot()
    state["settings"]["modules"].append(config.MODULE)
    engine = Engine(state, engine._persist)
    runtime = SimpleNamespace(engine=engine)
    entry = SimpleNamespace(
        entry_id="home-status-test",
        options={config.MODULE: settings or configured()},
        runtime_data=runtime,
    )
    calls, values = [], {"sensor.synthetic_power": observed(now)}
    records = {
        item["entity_id"]: SimpleNamespace(entity_id=item["entity_id"], id=item["registry_id"])
        for item in entry.options[config.MODULE]["sources"]
    }

    def read(entity):
        calls.append(("state", entity))
        return values.get(entity)

    def permission(entity, policy):
        calls.append(("permission", entity, policy))
        return not denied

    user = SimpleNamespace(
        id=state["members"][actor]["ha_user_id"],
        is_active=True,
        permissions=SimpleNamespace(check_entity=permission),
    )
    registry = SimpleNamespace(async_get=lambda entity: records.get(entity))
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_entry=lambda _entry: entry),
        states=SimpleNamespace(get=read),
    )
    monkeypatch.setattr(observations, "ha_access", lambda _hass: (registry, "read"))
    return hass, entry, runtime, user, calls, values, records


def test_default_disabled_and_no_retained_ha_data(engine, monkeypatch, now):
    assert config.MODULE not in engine.snapshot()["settings"]["modules"]
    hass, entry, runtime, user, calls, *_ = harness(monkeypatch, engine, now)
    before = runtime.engine.snapshot()
    view = observations.project(hass, entry, runtime, "owner", user, now)
    assert view["energy"][0]["value"] == 2500 and view["energy"][0]["unit"] == "W"
    assert calls == [
        ("permission", "sensor.synthetic_power", "read"),
        ("state", "sensor.synthetic_power"),
    ]
    assert runtime.engine.snapshot() == before
    for canary in (
        "sensor.synthetic_power",
        "registry-original",
        "PRIVATE_URL_CANARY",
        "PRIVATE_TOKEN_CANARY",
    ):
        assert canary not in repr(view)
        assert canary not in repr(runtime.engine.snapshot())
        assert canary not in repr(plans.messages(runtime.engine.view("owner"), "hello", (), now))


def test_family_refresh_metadata_has_no_state_reads_and_revokes_registry_identity(
    engine, monkeypatch, now
):
    hass, entry, runtime, user, calls, _, records = harness(monkeypatch, engine, now)
    first = observations.access_marker(hass, entry, runtime, "owner", user)
    assert isinstance(first, str) and len(first) == 64
    assert calls == [("permission", "sensor.synthetic_power", "read")]
    records["sensor.synthetic_power"].id = "replacement"
    second = observations.access_marker(hass, entry, runtime, "owner", user)
    assert first != second and not any(row[0] == "state" for row in calls)


@pytest.mark.parametrize("actor", ["owner", "parent", "adult", "child", "guest"])
@pytest.mark.parametrize("denied", [False, True])
async def test_current_role_and_acl_precede_every_state_read(
    engine, monkeypatch, now, actor, denied
):
    hass, entry, runtime, user, calls, *_ = harness(
        monkeypatch, engine, now, actor=actor, denied=denied
    )
    if actor == "guest":
        with pytest.raises(DomainError, match="forbidden"):
            observations.project(hass, entry, runtime, actor, user, now)
    else:
        result = observations.project(hass, entry, runtime, actor, user, now)
        assert bool(result["energy"]) == (actor in {"owner", "parent"} and not denied)
    assert any(item[0] == "state" for item in calls) == (
        actor in {"owner", "parent"} and not denied
    )


@pytest.mark.parametrize(
    "change", ["registry", "inactive_user", "entry", "runtime", "unbound", "disabled"]
)
async def test_revoked_or_replaced_source_never_reads(engine, monkeypatch, now, change):
    hass, entry, runtime, user, calls, _, records = harness(monkeypatch, engine, now)
    if change == "registry":
        records["sensor.synthetic_power"].id = "replacement"
    elif change == "inactive_user":
        user.is_active = False
    elif change == "entry":
        hass.config_entries.async_get_entry = lambda _key: None
    elif change == "runtime":
        entry.runtime_data = object()
    else:

        def alter(ctx):
            if change == "unbound":
                ctx.state["members"]["owner"]["ha_user_id"] = "other-user"
            else:
                ctx.state["settings"]["modules"].remove(config.MODULE)

        await runtime.engine.system_update("test-revoke", now, alter)
    try:
        view = observations.project(hass, entry, runtime, "owner", user, now)
        assert change == "registry" and view["energy"] == []
    except DomainError:
        assert change != "registry"
    assert not any(item[0] == "state" for item in calls)


def test_child_grant_and_group_intersection(engine, monkeypatch, now):
    group = {"id": "room", "title": "Synthetic room", "roles": ["owner"]}
    reading = source(section="group", group_id="room", metric=None, roles=["owner", "child"])
    hass, entry, runtime, user, calls, *_ = harness(
        monkeypatch, engine, now, settings=configured([reading], [group]), actor="child"
    )
    assert observations.project(hass, entry, runtime, "child", user, now)["groups"] == []
    assert calls == []
    entry.options[config.MODULE]["groups"][0]["roles"].append("child")
    assert (
        observations.project(hass, entry, runtime, "child", user, now)["groups"][0]["rows"][0][
            "value"
        ]
        == 2.5
    )


@pytest.mark.parametrize(
    ("state", "unit", "metric", "quality", "value"),
    [
        ("0", "%", "battery_soc", "ok", 0),
        ("100", "%", "battery_soc", "ok", 100),
        ("101", "%", "battery_soc", "invalid_value", None),
        ("-1", "%", "battery_soc", "invalid_value", None),
        ("-2.5", "kW", "grid_power", "ok", -2500),
        ("0", "W", "battery_power", "ok", 0),
        ("20", "kWh", "load_power", "invalid_unit", None),
        ("20", "V", "pv_power", "invalid_unit", None),
        ("NaN", "W", "load_power", "invalid_value", None),
        ("Infinity", "W", "load_power", "invalid_value", None),
        ("1e999", "W", "load_power", "invalid_value", None),
        ("bad", "W", "load_power", "invalid_value", None),
        ("21.3", "°C", None, "ok", 21.3),
        ("secret", "unknown-unit", None, "invalid_unit", None),
        ("unknown", "W", "load_power", "unknown", None),
        ("unavailable", "W", "load_power", "unavailable", None),
    ],
)
def test_bounded_units_values_and_signed_power(now, state, unit, metric, quality, value):
    row = facts.normalize(
        source(metric=metric), observed(now, state, unit_of_measurement=unit), now, 300
    )
    assert (row["quality"], row["value"]) == (quality, value)
    assert row["reported_state"] is None and row["active"] is None


@pytest.mark.parametrize(
    ("age", "quality"), [(0, "ok"), (300, "ok"), (301, "stale"), (-1, "future_timestamp")]
)
def test_report_age_does_not_claim_measurement_time(now, age, quality):
    row = facts.normalize(source(), observed(now - timedelta(seconds=age)), now, 300)
    assert row["quality"] == quality
    assert "measured_at" not in row and "observed_at" not in row
    if quality != "ok":
        assert row["value"] is None


@pytest.mark.parametrize("variant", ["restored", "missing", "naive", "future_reported", "legacy"])
def test_timestamp_and_restored_semantics(now, variant):
    state = observed(now)
    if variant == "restored":
        state.attributes["restored"] = True
    elif variant == "missing":
        state.last_reported = None
    elif variant == "naive":
        state.last_reported = now.replace(tzinfo=None)
    elif variant == "future_reported":
        state.last_reported = now + timedelta(seconds=1)
        state.last_updated = now  # Must not silently fall back from a bad current report.
    else:
        del state.last_reported
        state.last_updated = now
    row = facts.normalize(source(), state, now, 300)
    assert (
        row["quality"]
        == {
            "restored": "restored",
            "missing": "missing_timestamp",
            "naive": "missing_timestamp",
            "future_reported": "future_timestamp",
            "legacy": "ok",
        }[variant]
    )
    if variant == "legacy":
        assert row["freshness_basis"] == "last_updated"
    else:
        assert row["value"] is None


@pytest.mark.parametrize(
    ("domain", "state"),
    [("switch", "on"), ("binary_sensor", "on"), ("climate", "heat"), ("media_player", "idle")],
)
def test_activity_is_only_an_explicit_reported_state_match(now, domain, state):
    item = source(f"{domain}.synthetic", section="active", metric=None, active_states=[state])
    configured_value = config.validate(configured([item]))
    row = facts.normalize(item, observed(now, state), now, 300)
    assert row["active"] is True and row["reported_state"] == state and row["value"] is None
    for language in COPY:
        text = render(
            {"generated_at": now.isoformat(), "energy": [], "active": [row], "groups": []}, language
        )
        assert COPY[language]["note"] in text
    configured_value["sources"][0]["active_states"] = []
    with pytest.raises(DomainError):
        config.validate(configured_value)


@pytest.mark.parametrize(
    "change",
    [
        "age_bool",
        "age_big",
        "revision_bool",
        "extra",
        "guest",
        "empty_roles",
        "duplicate_metric",
        "bad_group",
        "camera",
        "sensor_activity",
    ],
)
def test_configuration_rejects_malformed_and_ambiguous_inputs(change):
    value = configured()
    if change == "age_bool":
        value["max_age_seconds"] = True
    elif change == "age_big":
        value["max_age_seconds"] = 86401
    elif change == "revision_bool":
        value["revision"] = True
    elif change == "extra":
        value["service"] = "switch.turn_on"
    elif change == "guest":
        value["sources"][0]["roles"] = ["guest"]
    elif change == "empty_roles":
        value["sources"][0]["roles"] = []
    elif change == "duplicate_metric":
        value["sources"].append(source(id="second"))
    elif change == "bad_group":
        value["sources"][0].update(section="group", metric=None, group_id=[])
    elif change == "camera":
        value["sources"][0]["entity_id"] = "camera.synthetic"
    elif change == "sensor_activity":
        value["sources"][0].update(section="active", metric=None, active_states=["on"])
    with pytest.raises(DomainError):
        config.validate(value)


@pytest.mark.parametrize(
    "content", ["/home extra", "/status", "/status a b", "/energy выключи", "/active sensor.secret"]
)
def test_reserved_commands_reject_whole_invalid_slot(content):
    with pytest.raises(DomainError):
        parse(content)


@pytest.mark.parametrize("content", ["/home", "состояние дома", "стан дому", "home status"])
def test_exact_trilingual_read_query(content):
    assert parse(content) == {"section": "home", "group_id": None}
    assert parse("do not change the home") is None


def test_config_copy_cannot_mutate_source():
    value = configured()
    cloned = config.validate(value)
    cloned["sources"][0]["roles"].append("child")
    assert value == configured()
    assert config.marker(config.validate(value)) == config.marker(deepcopy(value))


@pytest.mark.parametrize("language", ["en", "ru", "uk"])
def test_every_supported_protocol_state_has_localized_factual_delivery(language, now):
    for domain, states in config.STATES.items():
        for state in states:
            selected = source(
                f"{domain}.synthetic", section="active", metric=None, active_states=[state]
            )
            row = facts.normalize(selected, observed(now, state), now, 300)
            text = render(
                {"generated_at": now.isoformat(), "energy": [], "active": [row], "groups": []},
                language,
            )
            assert COPY[language]["state_" + state] in text
            assert COPY[language]["note"] in text
            assert COPY[language]["matched"] in text
