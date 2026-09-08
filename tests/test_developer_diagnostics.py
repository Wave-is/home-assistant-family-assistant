"""Unit tests for bounded pure developer diagnostics."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain import developer_diagnostics as diag
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)


def _ctx(state: dict, role: str = "owner", member_id: str = "owner") -> Context:
    return Context(
        state=state,
        actor={"id": member_id, "role": role},
        now=NOW,
        operation_id="op_test_diagnostics",
    )


# =============================================================================
# Defaults, Absent State, and Safe Configuration View
# =============================================================================


def test_absent_state_defaults() -> None:
    """Absent developer_diagnostics yields safe schema1/enabledFalse/generation1 defaults."""
    state: dict = {}
    config = diag.configuration(state)
    assert config == {
        "available": True,
        "enabled": False,
        "generation": 1,
        "count": 0,
        "saturated": False,
    }
    assert diag.capture_generation(state) is None

    # Absent state report uses default empty cases without raising
    report = diag.build_report(state, version="1.0.0")
    assert report == {
        "format": "family_assistant_defect_report",
        "schema": 1,
        "version": "1.0.0",
        "cases": [],
        "overflow_count": 0,
        "saturated": False,
        "limitations": [
            "technical_observations_only",
            "no_message_content",
            "not_a_semantic_reproducer",
        ],
    }

    # Absent state records nothing and mutates nothing
    diag.record_failure(
        state,
        generation=1,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert state == {}


def test_configuration_safe_on_non_dict_or_corrupted_state() -> None:
    """configuration() never raises on non-dict state or non-dict memory."""
    assert diag.configuration(None) == {
        "available": False,
        "enabled": False,
        "generation": 1,
        "count": 0,
        "saturated": False,
    }
    assert diag.configuration("invalid_state")["available"] is False
    assert diag.configuration({"memory": "not_a_dict"})["available"] is False
    assert diag.capture_generation(None) is None
    assert diag.capture_generation({"memory": 123}) is None


# =============================================================================
# Owner-Only Access and Strict Payload Validation
# =============================================================================


@pytest.mark.parametrize("role", ["parent", "adult", "child", "guest", "unknown"])
def test_configure_forbidden_for_non_owners(role: str) -> None:
    """Only owner can configure diagnostics; parents and others are rejected."""
    state: dict = {}
    ctx = _ctx(state, role=role, member_id="user_1")
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": True, "expected_generation": 1})
    assert exc.value.code == "forbidden"
    assert state == {}


def test_configure_strict_payload_keys() -> None:
    """configure() requires exact keys {enabled, expected_generation} with fixed field labels."""
    ctx = _ctx({})

    # Extra key
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": True, "expected_generation": 1, "extra": "forbidden"})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "payload"

    # Missing expected_generation
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": True})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "payload"

    # Missing enabled
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"expected_generation": 1})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "payload"

    # Not a dict
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, "invalid_payload")  # type: ignore[arg-type]
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "payload"

    # Arbitrary keys must never be stringified or leaked in field
    class CanaryKey:
        def __str__(self) -> str:
            raise AssertionError("str() must never be called on arbitrary payload keys")

        def __repr__(self) -> str:
            raise AssertionError("repr() must never be called on arbitrary payload keys")

        def __hash__(self) -> int:
            return 99999

        def __eq__(self, other: object) -> bool:
            return self is other

    with pytest.raises(DomainError) as exc:
        diag.configure(
            ctx,
            {CanaryKey(): "canary_leak", "enabled": True, "expected_generation": 1},  # type: ignore[dict-item]
        )
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "payload"


def test_configure_max_generation_toggle_fails_without_writing_invalid_state() -> None:
    """Generation 2**53-1 cannot advance on toggle and fails without corrupting state."""
    max_gen = 2**53 - 1
    state: dict = {
        "memory": {
            "developer_diagnostics": {
                "schema": 1,
                "enabled": True,
                "generation": max_gen,
                "cases": [],
                "overflow_count": 0,
                "saturated": False,
            }
        }
    }
    ctx = _ctx(state)
    original_state = copy.deepcopy(state)

    # Attempting to toggle enabled from True -> False at max generation must fail
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": False, "expected_generation": max_gen})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "expected_generation"
    # State must remain untouched: not mutated or written with generation 2**53
    assert state == original_state
    assert state["memory"]["developer_diagnostics"]["generation"] == max_gen

    # Re-asserting enabled: True (no toggle) does not advance generation and succeeds
    res = diag.configure(ctx, {"enabled": True, "expected_generation": max_gen})
    assert res["generation"] == max_gen
    assert state["memory"]["developer_diagnostics"]["generation"] == max_gen


@pytest.mark.parametrize("bad_enabled", [1, 0, "true", None, [], {}])
def test_configure_strict_enabled_bool(bad_enabled: object) -> None:
    """enabled must strictly be a bool, not integer or string truthy."""
    ctx = _ctx({})
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": bad_enabled, "expected_generation": 1})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "enabled"


@pytest.mark.parametrize("bad_gen", [0, -1, True, False, "1", 1.5, None])
def test_configure_strict_expected_generation_positive_int(bad_gen: object) -> None:
    """expected_generation must strictly be a positive integer >= 1."""
    ctx = _ctx({})
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": True, "expected_generation": bad_gen})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "expected_generation"


# =============================================================================
# Generation Advancement, Changed Flag Rule, and ABA Protection
# =============================================================================


def test_generation_increments_only_on_changed_flag() -> None:
    """Generation increments only when enabled flag actually toggles."""
    state: dict = {}
    ctx = _ctx(state)

    # 1. Enable from default False -> True: flag changed, generation advances 1 -> 2
    res = diag.configure(ctx, {"enabled": True, "expected_generation": 1})
    assert res == {
        "available": True,
        "enabled": True,
        "generation": 2,
        "count": 0,
        "saturated": False,
    }
    assert state["memory"]["developer_diagnostics"]["generation"] == 2
    assert state["memory"]["developer_diagnostics"]["enabled"] is True

    # 2. Re-assert enable True -> True: flag did NOT change, generation stays 2
    res2 = diag.configure(ctx, {"enabled": True, "expected_generation": 2})
    assert res2["generation"] == 2
    assert state["memory"]["developer_diagnostics"]["generation"] == 2

    # 3. Disable True -> False: flag changed, generation advances 2 -> 3
    res3 = diag.configure(ctx, {"enabled": False, "expected_generation": 2})
    assert res3["generation"] == 3
    assert res3["enabled"] is False
    assert state["memory"]["developer_diagnostics"]["generation"] == 3

    # 4. Re-assert disable False -> False: flag did NOT change, generation stays 3
    res4 = diag.configure(ctx, {"enabled": False, "expected_generation": 3})
    assert res4["generation"] == 3


def test_configure_conflict_on_stale_expected_generation() -> None:
    """Mismatched expected_generation raises DomainError('conflict')."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})  # now gen 2

    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": False, "expected_generation": 1})  # stale gen 1
    assert exc.value.code == "conflict"


def test_generation_aba_isolation_for_in_flight_jobs() -> None:
    """An in-flight job with stale generation cannot mutate state after toggle ABA cycle."""
    state: dict = {}
    ctx = _ctx(state)

    # Enable diagnostics -> generation 2
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})
    job_gen = diag.capture_generation(state)
    assert job_gen == 2

    # Diagnostics toggled off (gen 3) and back on (gen 4)
    diag.configure(ctx, {"enabled": False, "expected_generation": 2})
    assert diag.capture_generation(state) is None
    diag.configure(ctx, {"enabled": True, "expected_generation": 3})
    assert diag.capture_generation(state) == 4

    # Stale job (gen 2) finishes now and tries to record failure:
    diag.record_failure(
        state,
        generation=job_gen,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    # Stale job recording quietly skipped, no mutation
    assert state["memory"]["developer_diagnostics"]["cases"] == []
    assert diag.configuration(state)["count"] == 0

    # Current job (gen 4) records failure:
    diag.record_failure(
        state,
        generation=4,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert diag.configuration(state)["count"] == 1
    assert len(state["memory"]["developer_diagnostics"]["cases"]) == 1


def test_disabled_diagnostics_quietly_skips_recording() -> None:
    """record_failure quietly skips when diagnostics is disabled, even with matching generation."""
    state: dict = {
        "memory": {
            "developer_diagnostics": {
                "schema": 1,
                "enabled": False,
                "generation": 3,
                "cases": [],
                "overflow_count": 0,
                "saturated": False,
            }
        }
    }
    diag.record_failure(
        state,
        generation=3,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert state["memory"]["developer_diagnostics"]["cases"] == []
    assert diag.capture_generation(state) is None


def test_preserves_cases_across_configure_toggles() -> None:
    """Disabling and re-enabling diagnostics preserves previously recorded cases."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})  # gen 2

    diag.record_failure(
        state,
        generation=2,
        code="provider_bad_response",
        has_quote=True,
        has_refs=False,
    )
    assert diag.configuration(state)["count"] == 1

    # Disable diagnostics -> gen 3
    diag.configure(ctx, {"enabled": False, "expected_generation": 2})
    assert diag.configuration(state)["count"] == 1
    assert state["memory"]["developer_diagnostics"]["cases"][0]["code"] == "provider_bad_response"

    # Re-enable diagnostics -> gen 4
    diag.configure(ctx, {"enabled": True, "expected_generation": 3})
    assert diag.configuration(state)["count"] == 1
    assert state["memory"]["developer_diagnostics"]["cases"][0]["code"] == "provider_bad_response"


# =============================================================================
# Code Whitelist, Sanitization, and Context Flags
# =============================================================================


@pytest.mark.parametrize(
    "whitelisted_code",
    [
        "provider_not_configured",
        "provider_timeout",
        "provider_unreachable",
        "provider_authentication",
        "provider_model_missing",
        "provider_bad_response",
        "invalid_model_plan",
        "search_not_configured",
        "other",
    ],
)
def test_whitelisted_codes_recorded_exactly(whitelisted_code: str) -> None:
    """All whitelisted error codes are recorded under their exact code identifier."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})

    diag.record_failure(
        state,
        generation=2,
        code=whitelisted_code,
        has_quote=False,
        has_refs=True,
    )
    cases = state["memory"]["developer_diagnostics"]["cases"]
    assert len(cases) == 1
    assert cases[0] == {
        "stage": "assistant_job",
        "code": whitelisted_code,
        "has_quote": False,
        "has_refs": True,
        "count": 1,
    }


def test_unknown_error_code_and_arbitrary_inputs_sanitized_to_other() -> None:
    """Unknown strings, exceptions, and arbitrary objects map to 'other' without str/repr."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})

    class CanaryLeakException(Exception):
        def __str__(self) -> str:
            raise AssertionError("str() must never be called on arbitrary input")

        def __repr__(self) -> str:
            raise AssertionError("repr() must never be called on arbitrary input")

    # 1. Unknown string code
    diag.record_failure(
        state,
        generation=2,
        code="secret_internal_crash_dump",
        has_quote=False,
        has_refs=False,
    )
    # 2. Arbitrary non-string input (CanaryLeakException will fail if str/repr is invoked)
    diag.record_failure(
        state,
        generation=2,
        code=CanaryLeakException(),
        has_quote=False,
        has_refs=False,
    )

    cases = state["memory"]["developer_diagnostics"]["cases"]
    assert len(cases) == 1
    assert cases[0]["code"] == "other"
    # Both mapped to the same bucket ("other", False, False) -> count is 2
    assert cases[0]["count"] == 2


@pytest.mark.parametrize("bad_flag", [1, 0, "true", "false", None, [], {}])
def test_record_failure_requires_strict_bool_context_flags(bad_flag: object) -> None:
    """Non-bool context flags quietly result in no mutation and no error."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})

    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=bad_flag,
        has_refs=False,
    )
    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=False,
        has_refs=bad_flag,
    )
    assert state["memory"]["developer_diagnostics"]["cases"] == []


# =============================================================================
# Aggregation, Max 64 Bounded Buckets, and Saturation Limits
# =============================================================================


def test_aggregation_of_identical_cases() -> None:
    """Identical failure occurrences aggregate into a single bucket incrementing count."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})

    for _ in range(5):
        diag.record_failure(
            state,
            generation=2,
            code="provider_timeout",
            has_quote=True,
            has_refs=True,
        )

    cases = state["memory"]["developer_diagnostics"]["cases"]
    assert len(cases) == 1
    assert cases[0]["count"] == 5
    assert diag.configuration(state)["count"] == 1
    assert state["memory"]["developer_diagnostics"]["saturated"] is False


def test_buckets_overflow_and_saturation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cases cap at MAX_CASES; excess increments overflow_count and sets saturated=True."""
    monkeypatch.setattr(diag, "MAX_CASES", 3)
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})

    # Record 3 unique valid cases
    diag.record_failure(
        state,
        generation=2,
        code="provider_not_configured",
        has_quote=False,
        has_refs=False,
    )
    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    diag.record_failure(
        state,
        generation=2,
        code="provider_unreachable",
        has_quote=False,
        has_refs=False,
    )
    assert len(state["memory"]["developer_diagnostics"]["cases"]) == 3
    assert state["memory"]["developer_diagnostics"]["overflow_count"] == 0
    assert state["memory"]["developer_diagnostics"]["saturated"] is False

    # Recording a 4th unique case exceeds MAX_CASES=3; overflows instead of appending
    diag.record_failure(
        state,
        generation=2,
        code="provider_authentication",
        has_quote=False,
        has_refs=False,
    )
    assert len(state["memory"]["developer_diagnostics"]["cases"]) == 3
    assert state["memory"]["developer_diagnostics"]["overflow_count"] == 1
    assert state["memory"]["developer_diagnostics"]["saturated"] is True
    assert diag.configuration(state)["count"] == 3
    assert diag.configuration(state)["saturated"] is True

    # Recording an existing matching case increments count without overflowing
    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert len(state["memory"]["developer_diagnostics"]["cases"]) == 3
    assert state["memory"]["developer_diagnostics"]["overflow_count"] == 1
    timeout_case = next(
        c
        for c in state["memory"]["developer_diagnostics"]["cases"]
        if c["code"] == "provider_timeout"
    )
    assert timeout_case["count"] == 2


def test_unique_aggregate_identities_natural_ceiling() -> None:
    """Only 36 unique aggregate identities are possible (9 allowed codes * 2 * 2 booleans)."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})

    unique_count = 0
    for code in sorted(diag.ALLOWED_CODES):
        for has_quote in (False, True):
            for has_refs in (False, True):
                diag.record_failure(
                    state,
                    generation=2,
                    code=code,
                    has_quote=has_quote,
                    has_refs=has_refs,
                )
                unique_count += 1

    assert unique_count == 36
    assert len(state["memory"]["developer_diagnostics"]["cases"]) == 36
    assert state["memory"]["developer_diagnostics"]["overflow_count"] == 0
    assert state["memory"]["developer_diagnostics"]["saturated"] is False


def test_duplicate_aggregate_identities_rejected() -> None:
    """Duplicate aggregate identities in stored state are rejected, not counted twice."""
    duplicate_cases = [
        {
            "stage": "assistant_job",
            "code": "provider_timeout",
            "has_quote": False,
            "has_refs": False,
            "count": 1,
        },
        {
            "stage": "assistant_job",
            "code": "provider_timeout",
            "has_quote": False,
            "has_refs": False,
            "count": 2,
        },
    ]
    diag_data = {
        "schema": 1,
        "enabled": True,
        "generation": 2,
        "cases": duplicate_cases,
        "overflow_count": 0,
        "saturated": False,
    }
    assert diag._is_valid_diagnostics_data(diag_data) is False

    state = {"memory": {"developer_diagnostics": copy.deepcopy(diag_data)}}
    orig = copy.deepcopy(state)

    # configuration safely reports available=False
    cfg = diag.configuration(state)
    assert cfg["available"] is False

    # configure rejects with invalid_field
    ctx = _ctx(state)
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": True, "expected_generation": 2})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "developer_diagnostics"
    assert state == orig

    # build_report rejects with invalid_field
    with pytest.raises(DomainError) as exc_rep:
        diag.build_report(state, version="1.0.0")
    assert exc_rep.value.code == "invalid_field"
    assert exc_rep.value.field == "developer_diagnostics"
    assert state == orig

    # record_failure skips quietly and does not count twice or mutate
    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert state == orig


@pytest.mark.parametrize(
    "unhashable_code",
    [["provider_timeout"], {"code": "bad"}, 123, None, ()],
)
def test_stored_case_code_strict_string_before_whitelist_no_type_error(
    unhashable_code: object,
) -> None:
    """Stored case code that is a list/dict/unhashable must return False without TypeError."""
    bad_diag = {
        "schema": 1,
        "enabled": True,
        "generation": 1,
        "cases": [
            {
                "stage": "assistant_job",
                "code": unhashable_code,
                "has_quote": False,
                "has_refs": False,
                "count": 1,
            }
        ],
        "overflow_count": 0,
        "saturated": False,
    }
    assert diag._is_valid_diagnostics_data(bad_diag) is False

    state = {"memory": {"developer_diagnostics": copy.deepcopy(bad_diag)}}
    assert diag.configuration(state)["available"] is False

    ctx = _ctx(state)
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": True, "expected_generation": 1})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "developer_diagnostics"

    with pytest.raises(DomainError) as exc_rep:
        diag.build_report(state, version="1.0.0")
    assert exc_rep.value.code == "invalid_field"
    assert exc_rep.value.field == "developer_diagnostics"

    # record_failure does not raise TypeError
    diag.record_failure(
        state,
        generation=1,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )


def test_capacity_saturation_at_limit_999999() -> None:
    """Case counts and overflow_count saturate at 999999 and set saturated=True."""
    state: dict = {}
    ctx = _ctx(state)
    diag.configure(ctx, {"enabled": True, "expected_generation": 1})

    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    case = state["memory"]["developer_diagnostics"]["cases"][0]
    case["count"] = 999998
    assert state["memory"]["developer_diagnostics"]["saturated"] is False

    # Increment to 999999 -> saturated becomes True
    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert case["count"] == 999999
    assert state["memory"]["developer_diagnostics"]["saturated"] is True

    # Further attempts do not exceed 999999
    diag.record_failure(
        state,
        generation=2,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert case["count"] == 999999
    assert state["memory"]["developer_diagnostics"]["saturated"] is True


def test_overflow_count_saturates_at_999999() -> None:
    """Overflow count saturates at 999999 and does not exceed it."""
    state: dict = {
        "memory": {
            "developer_diagnostics": {
                "schema": 1,
                "enabled": True,
                "generation": 5,
                "cases": [
                    {
                        "stage": "assistant_job",
                        "code": "other",
                        "has_quote": False,
                        "has_refs": False,
                        "count": 1,
                    }
                ],
                "overflow_count": 999998,
                "saturated": False,
            }
        }
    }
    diag_data = state["memory"]["developer_diagnostics"]
    assert diag._is_valid_diagnostics_data(diag_data) is True

    diag_data["overflow_count"] = 999999
    assert diag._is_valid_diagnostics_data(diag_data) is True
    diag_data["overflow_count"] = 1000000
    assert diag._is_valid_diagnostics_data(diag_data) is False


# =============================================================================
# Malformed State Protection: Never Overwrite, Quietly Skip
# =============================================================================


@pytest.mark.parametrize(
    "corrupted_diag",
    [
        {
            "schema": 2,
            "enabled": True,
            "generation": 1,
            "cases": [],
            "overflow_count": 0,
            "saturated": False,
        },
        {
            "schema": 1,
            "enabled": "not_a_bool",
            "generation": 1,
            "cases": [],
            "overflow_count": 0,
            "saturated": False,
        },
        {
            "schema": 1,
            "enabled": True,
            "generation": 0,
            "cases": [],
            "overflow_count": 0,
            "saturated": False,
        },
        {
            "schema": 1,
            "enabled": True,
            "generation": 1,
            "cases": "not_a_list",
            "overflow_count": 0,
            "saturated": False,
        },
        {
            "schema": 1,
            "enabled": True,
            "generation": 1,
            "cases": [{"bad_key": 1}],
            "overflow_count": 0,
            "saturated": False,
        },
        {
            "schema": 1,
            "enabled": True,
            "generation": 1,
            "cases": [],
            "overflow_count": -1,
            "saturated": False,
        },
        {
            "schema": 1,
            "enabled": True,
            "generation": 1,
            "cases": [],
            "overflow_count": 0,
            "saturated": "not_bool",
        },
        {
            "schema": 1,
            "enabled": True,
            "generation": 1,
            "cases": [],
            "overflow_count": 0,
            "saturated": False,
            "extra_leak": 123,
        },
        "not_a_dict",
        None,
        {},
    ],
)
def test_malformed_state_never_overwritten_and_skips(corrupted_diag: object) -> None:
    """Invalid stored shape throws fixed invalid_field on configure/export; remains unchanged."""
    state = {"memory": {"developer_diagnostics": copy.deepcopy(corrupted_diag)}}
    original_state = copy.deepcopy(state)

    # 1. configuration() safely returns availableFalse without throwing
    cfg = diag.configuration(state)
    assert cfg["available"] is False
    assert cfg["enabled"] is False

    # 2. capture_generation() returns None
    assert diag.capture_generation(state) is None

    # 3. record_failure() quietly skips without raising or mutating
    diag.record_failure(
        state,
        generation=1,
        code="provider_timeout",
        has_quote=False,
        has_refs=False,
    )
    assert state == original_state

    # 4. configure() throws DomainError and DOES NOT overwrite
    ctx = _ctx(state)
    with pytest.raises(DomainError) as exc:
        diag.configure(ctx, {"enabled": True, "expected_generation": 1})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "developer_diagnostics"
    assert state == original_state  # Absolutely no overwrite!

    # 5. build_report() throws DomainError and DOES NOT overwrite
    with pytest.raises(DomainError) as exc_rep:
        diag.build_report(state, version="1.0.0")
    assert exc_rep.value.code == "invalid_field"
    assert exc_rep.value.field == "developer_diagnostics"
    assert state == original_state


# =============================================================================
# Defect Report: SemVer Validation, Determinism, Isolation, and Private Canaries
# =============================================================================


@pytest.mark.parametrize(
    "valid_version",
    [
        "1.0.0",
        "0.1.0",
        "0.1.0-alpha.27",
        "1.2.3-alpha.1",
        "2.0.0-beta.0",
        "2.0.0-rc.5",
        "10.20.30",
    ],
)
def test_build_report_valid_semver(valid_version: str) -> None:
    """build_report accepts valid public numeric SemVer with optional alpha/beta/rc.N."""
    state: dict = {}
    report = diag.build_report(state, version=valid_version)
    assert report["version"] == valid_version
    assert report["format"] == "family_assistant_defect_report"
    assert report["schema"] == 1


@pytest.mark.parametrize(
    "invalid_version",
    [
        "v1.0.0",
        "1.0",
        "1.0.0.0",
        "01.1.0",
        "1.0.0-dev",
        "1.0.0-nightly.1",
        "1.0.0-dirty",
        "beta",
        "",
        None,
        123,
        # Bare alpha/beta/rc without .N are rejected
        "1.2.3-alpha",
        "1.2.3-beta",
        "1.2.3-rc",
        # Trailing/leading newlines are rejected
        "1.0.0\n",
        "1.0.0\r\n",
        "\n1.0.0",
        # Unicode digits are rejected
        "\u0661.0.0",
        "1.\u0660.0",
        "1.0.0-alpha.\u0661",
        # Length bounded <= 64
        "1.0.0." + "0" * 60,
        "1.0.0-alpha.1" + "0" * 60,
    ],
)
def test_build_report_invalid_semver_rejected(invalid_version: object) -> None:
    """Invalid semver strings raise DomainError('invalid_field', 'version')."""
    state: dict = {}
    with pytest.raises(DomainError) as exc:
        diag.build_report(state, version=invalid_version)  # type: ignore[arg-type]
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "version"


def test_build_report_privacy_canaries_and_deterministic_sorting() -> None:
    """Report strictly contains only defined fields; private state and canaries never leak."""
    canary_token = "CANARY_SECRET_TOKEN_XYZ_987"
    canary_name = "Super Secret Person"
    canary_address = "https://private-canary.example.invalid:8123"

    state: dict = {
        "members": {"owner": {"name": canary_name, "token": canary_token}},
        "ha": {"base_url": canary_address},
        "memory": {
            "unrelated_private_data": {"secret_key": canary_token},
            "developer_diagnostics": {
                "schema": 1,
                "enabled": True,
                "generation": 42,
                "cases": [
                    {
                        "stage": "assistant_job",
                        "code": "search_not_configured",
                        "has_quote": True,
                        "has_refs": False,
                        "count": 3,
                    },
                    {
                        "stage": "assistant_job",
                        "code": "invalid_model_plan",
                        "has_quote": False,
                        "has_refs": True,
                        "count": 1,
                    },
                    {
                        "stage": "assistant_job",
                        "code": "invalid_model_plan",
                        "has_quote": False,
                        "has_refs": False,
                        "count": 5,
                    },
                ],
                "overflow_count": 2,
                "saturated": True,
            },
        },
    }

    report = diag.build_report(state, version="0.1.0-alpha.27")

    # Exact expected keys
    assert set(report.keys()) == {
        "format",
        "schema",
        "version",
        "cases",
        "overflow_count",
        "saturated",
        "limitations",
    }
    assert report["format"] == "family_assistant_defect_report"
    assert report["schema"] == 1
    assert report["version"] == "0.1.0-alpha.27"
    assert report["overflow_count"] == 2
    assert report["saturated"] is True
    assert report["limitations"] == [
        "technical_observations_only",
        "no_message_content",
        "not_a_semantic_reproducer",
    ]

    # No generation, no identities, no files/providers/HA in report
    assert "generation" not in report
    assert "members" not in report
    assert "ha" not in report
    assert "actor" not in report

    # Deterministic sorting check
    cases = report["cases"]
    assert len(cases) == 3
    # Sorted by (stage, code, has_quote, has_refs, count)
    # 1. invalid_model_plan, has_quote=False, has_refs=False, count=5
    # 2. invalid_model_plan, has_quote=False, has_refs=True, count=1
    # 3. search_not_configured, has_quote=True, has_refs=False, count=3
    assert cases[0]["code"] == "invalid_model_plan" and cases[0]["has_refs"] is False
    assert cases[1]["code"] == "invalid_model_plan" and cases[1]["has_refs"] is True
    assert cases[2]["code"] == "search_not_configured"

    # Deepcopy isolation check: mutating returned report does not mutate state
    cases[0]["count"] = 9999
    assert state["memory"]["developer_diagnostics"]["cases"][2]["count"] == 5

    # Serialized text inspection for privacy canary guarantees
    serialized = json.dumps(report)
    assert canary_token not in serialized
    assert canary_name not in serialized
    assert canary_address not in serialized
    assert "42" not in serialized  # generation must not leak
