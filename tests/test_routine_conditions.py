"""Tests for routine conditions validation and tri-state evaluation."""

import copy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.family_assistant.domain.routine_conditions import evaluate, validate
from custom_components.family_assistant.domain.validation import DomainError


def test_validate_normalized_defaults_and_strict_types():
    raw = {"kind": "entity_state", "entity_id": "binary_sensor.motion", "state": "on"}
    assert validate(raw) == {
        "kind": "entity_state",
        "entity_id": "binary_sensor.motion",
        "state": "on",
        "max_age_seconds": 120,
        "negate": False,
    }
    for bad in [
        {"kind": "mode", "mode": "normal", "negate": 1},
        {"kind": "mode", "mode": "party"},
        {"kind": "entity_state", "entity_id": "Motion", "state": "on"},
    ]:
        with pytest.raises(DomainError):
            validate(bad)


def test_validate_depth_limit_and_total_node_cap():
    valid_d3 = {
        "kind": "all",
        "conditions": [{"kind": "any", "conditions": [{"kind": "mode", "mode": "normal"}]}],
    }
    assert validate(valid_d3)["kind"] == "all"
    d4 = {
        "kind": "all",
        "conditions": [
            {
                "kind": "all",
                "conditions": [{"kind": "all", "conditions": [{"kind": "mode", "mode": "normal"}]}],
            }
        ],
    }
    with pytest.raises(DomainError):
        validate(d4)
    many = {"kind": "all", "conditions": [{"kind": "mode", "mode": "normal"} for _ in range(21)]}
    with pytest.raises(DomainError):
        validate(many)


def test_validate_time_window_equal_bounds_and_unknown_fields():
    with pytest.raises(DomainError):
        validate({"kind": "time_window", "start": "10:00", "end": "10:00", "timezone": "UTC"})
    with pytest.raises(DomainError):
        validate({"kind": "mode", "mode": "normal", "extra": 123})


def test_evaluate_rejects_naive_now_and_invalid_inputs():
    cond = {"kind": "mode", "mode": "normal"}
    with pytest.raises(DomainError):
        evaluate(cond, datetime(2026, 1, 1, 12, 0), ["normal"], {})
    with pytest.raises(DomainError):
        evaluate(cond, datetime.now(UTC), ["unknown_mode"], {})
    with pytest.raises(DomainError):
        evaluate(cond, datetime.now(UTC), ["normal"], "not-a-dict")


def test_evaluate_mode_and_negate_preserves_unknown():
    now = datetime.now(UTC)
    c_mode = {"kind": "mode", "mode": "vacation"}
    assert evaluate(c_mode, now, ["vacation"], {}) is True
    assert evaluate({**c_mode, "negate": True}, now, ["vacation"], {}) is False
    c_stale = {"kind": "entity_state", "entity_id": "sensor.temp", "state": "20", "negate": True}
    assert evaluate(c_stale, now, [], {}) is None  # Unknown negated remains None


def test_evaluate_observations_missing_stale_future_and_bad_record():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    c = {
        "kind": "entity_state",
        "entity_id": "binary_sensor.door",
        "state": "open",
        "max_age_seconds": 60,
    }
    # Missing, bad state, malformed time
    assert evaluate(c, now, [], {}) is None
    assert (
        evaluate(
            c, now, [], {"binary_sensor.door": {"state": "unknown", "observed_at": now.isoformat()}}
        )
        is None
    )
    assert (
        evaluate(c, now, [], {"binary_sensor.door": {"state": "open", "observed_at": "bad-date"}})
        is None
    )
    # Stale (>60s) and future (>5s)
    stale_iso = (now - timedelta(seconds=65)).isoformat()
    assert (
        evaluate(c, now, [], {"binary_sensor.door": {"state": "open", "observed_at": stale_iso}})
        is None
    )
    future_iso = (now + timedelta(seconds=6)).isoformat()
    assert (
        evaluate(c, now, [], {"binary_sensor.door": {"state": "open", "observed_at": future_iso}})
        is None
    )
    # Valid live state: exact match vs mismatch
    fresh_iso = (now - timedelta(seconds=10)).isoformat()
    assert (
        evaluate(c, now, [], {"binary_sensor.door": {"state": "open", "observed_at": fresh_iso}})
        is True
    )
    assert (
        evaluate(c, now, [], {"binary_sensor.door": {"state": "closed", "observed_at": fresh_iso}})
        is False
    )


def test_evaluate_time_window_daytime_and_overnight():
    tz = "America/New_York"
    day_cond = {"kind": "time_window", "start": "09:00", "end": "17:00", "timezone": tz}
    in_day = datetime(2026, 1, 1, 10, 30, tzinfo=ZoneInfo(tz))
    out_day = datetime(2026, 1, 1, 17, 0, tzinfo=ZoneInfo(tz))  # end exclusive
    assert evaluate(day_cond, in_day, [], {}) is True
    assert evaluate(day_cond, out_day, [], {}) is False

    night_cond = {"kind": "time_window", "start": "22:00", "end": "06:00", "timezone": tz}
    at_night1 = datetime(2026, 1, 1, 23, 0, tzinfo=ZoneInfo(tz))
    at_night2 = datetime(2026, 1, 2, 4, 30, tzinfo=ZoneInfo(tz))
    out_night = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo(tz))
    assert evaluate(night_cond, at_night1, [], {}) is True
    assert evaluate(night_cond, at_night2, [], {}) is True
    assert evaluate(night_cond, out_night, [], {}) is False


def test_evaluate_time_window_dst_stability():
    # US Eastern DST transition: March 8 2026 02:00 -> 03:00
    tz = "America/New_York"
    cond = {"kind": "time_window", "start": "01:30", "end": "03:30", "timezone": tz}
    t1 = datetime(2026, 3, 8, 1, 45, tzinfo=ZoneInfo(tz))
    assert evaluate(cond, t1, [], {}) is True
    t2 = datetime(2026, 3, 8, 3, 15, tzinfo=ZoneInfo(tz))
    assert evaluate(cond, t2, [], {}) is True


def test_evaluate_tri_state_all_logic():
    now = datetime.now(UTC)
    c_true = {"kind": "mode", "mode": "normal"}
    c_false = {"kind": "mode", "mode": "vacation"}
    c_unk = {"kind": "entity_state", "entity_id": "sensor.temp", "state": "20"}
    # all: False if any False; else None if any Unknown; else True
    assert (
        evaluate({"kind": "all", "conditions": [c_true, c_false, c_unk]}, now, ["normal"], {})
        is False
    )
    assert evaluate({"kind": "all", "conditions": [c_true, c_unk]}, now, ["normal"], {}) is None
    assert evaluate({"kind": "all", "conditions": [c_true, c_true]}, now, ["normal"], {}) is True


def test_evaluate_tri_state_any_logic():
    now = datetime.now(UTC)
    c_true = {"kind": "mode", "mode": "normal"}
    c_false = {"kind": "mode", "mode": "vacation"}
    c_unk = {"kind": "entity_state", "entity_id": "sensor.temp", "state": "20"}
    # any: True if any True; else None if any Unknown; else False
    assert (
        evaluate({"kind": "any", "conditions": [c_false, c_true, c_unk]}, now, ["normal"], {})
        is True
    )
    assert evaluate({"kind": "any", "conditions": [c_false, c_unk]}, now, ["normal"], {}) is None
    assert evaluate({"kind": "any", "conditions": [c_false, c_false]}, now, ["normal"], {}) is False


def test_no_arbitrary_code_execution_or_eval():
    injection = {"kind": "__import__('os').system('echo pwned')", "mode": "normal"}
    with pytest.raises(DomainError):
        validate(injection)


def test_source_immutability():
    raw_cond = {"kind": "all", "conditions": [{"kind": "mode", "mode": "normal"}]}
    raw_copy = copy.deepcopy(raw_cond)
    obs = {"sensor.temp": {"state": "21", "observed_at": datetime.now(UTC).isoformat()}}
    obs_copy = copy.deepcopy(obs)
    modes = ["normal"]
    modes_copy = copy.deepcopy(modes)
    evaluate(raw_cond, datetime.now(UTC), modes, obs)
    assert raw_cond == raw_copy
    assert obs == obs_copy
    assert modes == modes_copy


def test_fold_age_uses_elapsed_time_not_identical_wall_clock():
    zone = ZoneInfo("Europe/Kyiv")
    earlier = datetime(2026, 10, 25, 3, 30, tzinfo=zone, fold=0)
    now = datetime(2026, 10, 25, 3, 30, tzinfo=zone, fold=1)
    condition = {"kind": "entity_state", "entity_id": "sensor.synthetic", "state": "on"}
    observation = {"sensor.synthetic": {"state": "on", "observed_at": earlier}}
    assert evaluate(condition, now, [], observation) is None
    assert evaluate({**condition, "negate": True}, now, [], observation) is None


@pytest.mark.parametrize("kind", [[], {}, False, None])
def test_malformed_kind_is_domain_error(kind):
    with pytest.raises(DomainError):
        validate({"kind": kind})


def test_node_limit_is_shared_across_branches():
    child = {"kind": "mode", "mode": "normal"}
    group = {"kind": "any", "conditions": [child] * 10}
    with pytest.raises(DomainError):
        validate({"kind": "all", "conditions": [group, group]})
