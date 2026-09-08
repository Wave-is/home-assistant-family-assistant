"""Bounded developer diagnostics collection and defect report generation."""

from __future__ import annotations

import copy
import re
from typing import Any

from .context import Context
from .validation import DomainError

STAGE_ASSISTANT_JOB = "assistant_job"
REPORT_FORMAT = "family_assistant_defect_report"
REPORT_SCHEMA = 1
STORAGE_SCHEMA = 1
MAX_CASES = 64
MAX_COUNT = 999999
MAX_GENERATION = 2**53 - 1
MAX_VERSION_LENGTH = 64

ALLOWED_CODES = frozenset(
    {
        "provider_not_configured",
        "provider_timeout",
        "provider_unreachable",
        "provider_authentication",
        "provider_model_missing",
        "provider_bad_response",
        "invalid_model_plan",
        "search_not_configured",
        "other",
    }
)

FIXED_LIMITATIONS = [
    "technical_observations_only",
    "no_message_content",
    "not_a_semantic_reproducer",
]

# Validated public numeric SemVer with optional prerelease exactly alpha.N/beta.N/rc.N
_SEMVER_REGEX = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(alpha|beta|rc)\.(0|[1-9][0-9]*))?\Z",
    re.ASCII,
)


def _is_valid_diagnostics_data(data: Any) -> bool:
    """Validate strict exact shape and bounds of stored developer diagnostics."""
    if not isinstance(data, dict):
        return False
    if set(data.keys()) != {
        "schema",
        "enabled",
        "generation",
        "cases",
        "overflow_count",
        "saturated",
    }:
        return False
    if type(data["schema"]) is not int or data["schema"] != STORAGE_SCHEMA:
        return False
    if type(data["enabled"]) is not bool:
        return False
    if (
        type(data["generation"]) is not int
        or data["generation"] < 1
        or data["generation"] > MAX_GENERATION
    ):
        return False
    if type(data["overflow_count"]) is not int or not (0 <= data["overflow_count"] <= MAX_COUNT):
        return False
    if type(data["saturated"]) is not bool:
        return False
    if not isinstance(data["cases"], list) or len(data["cases"]) > MAX_CASES:
        return False

    seen_identities: set[tuple[str, str, bool, bool]] = set()
    for case in data["cases"]:
        if not isinstance(case, dict):
            return False
        if set(case.keys()) != {"stage", "code", "has_quote", "has_refs", "count"}:
            return False
        if type(case["stage"]) is not str or case["stage"] != STAGE_ASSISTANT_JOB:
            return False
        if type(case["code"]) is not str or case["code"] not in ALLOWED_CODES:
            return False
        if type(case["has_quote"]) is not bool:
            return False
        if type(case["has_refs"]) is not bool:
            return False
        if type(case["count"]) is not int or not (1 <= case["count"] <= MAX_COUNT):
            return False
        identity = (case["stage"], case["code"], case["has_quote"], case["has_refs"])
        if identity in seen_identities:
            return False
        seen_identities.add(identity)

    return True


def _inspect_diagnostics(state: Any) -> tuple[str, dict[str, Any] | None]:
    """Inspect state for developer_diagnostics, returning 'absent', 'valid', or 'invalid'."""
    if not isinstance(state, dict):
        return "invalid", None
    if "memory" not in state:
        return "absent", None
    memory = state["memory"]
    if not isinstance(memory, dict):
        return "invalid", None
    if "developer_diagnostics" not in memory:
        return "absent", None
    diag = memory["developer_diagnostics"]
    if not _is_valid_diagnostics_data(diag):
        return "invalid", None
    return "valid", diag


def configuration(state: Any) -> dict[str, Any]:
    """Return safe configuration view without throwing or exposing private state."""
    status, diag = _inspect_diagnostics(state)
    if status == "invalid":
        return {
            "available": False,
            "enabled": False,
            "generation": 1,
            "count": 0,
            "saturated": False,
        }
    if status == "absent":
        return {
            "available": True,
            "enabled": False,
            "generation": 1,
            "count": 0,
            "saturated": False,
        }
    assert diag is not None
    return {
        "available": True,
        "enabled": diag["enabled"],
        "generation": diag["generation"],
        "count": len(diag["cases"]),
        "saturated": diag["saturated"],
    }


def capture_generation(state: Any) -> int | None:
    """Return active valid generation positive integer if enabled, else None."""
    status, diag = _inspect_diagnostics(state)
    if status != "valid":
        return None
    assert diag is not None
    if not diag["enabled"]:
        return None
    return diag["generation"]


def configure(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    """Owner-only configuration with strict generation concurrency check."""
    if not isinstance(ctx.actor, dict) or ctx.actor.get("role") != "owner":
        raise DomainError("forbidden")

    if not isinstance(payload, dict):
        raise DomainError("invalid_field", "payload")

    allowed_keys = {"enabled", "expected_generation"}
    if set(payload.keys()) != allowed_keys:
        raise DomainError("invalid_field", "payload")

    if type(payload["enabled"]) is not bool:
        raise DomainError("invalid_field", "enabled")

    expected_gen = payload["expected_generation"]
    if type(expected_gen) is not int or expected_gen < 1 or expected_gen > MAX_GENERATION:
        raise DomainError("invalid_field", "expected_generation")

    status, diag = _inspect_diagnostics(ctx.state)
    if status == "invalid":
        raise DomainError("invalid_field", "developer_diagnostics")

    if status == "absent":
        current_enabled = False
        current_generation = 1
        cases: list[dict[str, Any]] = []
        overflow_count = 0
        saturated = False
    else:
        assert diag is not None
        current_enabled = diag["enabled"]
        current_generation = diag["generation"]
        cases = diag["cases"]
        overflow_count = diag["overflow_count"]
        saturated = diag["saturated"]

    if expected_gen != current_generation:
        raise DomainError("conflict")

    target_enabled = payload["enabled"]
    if target_enabled != current_enabled:
        if current_generation >= MAX_GENERATION:
            raise DomainError("invalid_field", "expected_generation")
        next_generation = current_generation + 1
    else:
        next_generation = current_generation

    if not isinstance(ctx.state, dict):
        raise DomainError("invalid_field", "state")

    memory = ctx.state.setdefault("memory", {})
    if not isinstance(memory, dict):
        raise DomainError("invalid_field", "memory")

    memory["developer_diagnostics"] = {
        "schema": STORAGE_SCHEMA,
        "enabled": target_enabled,
        "generation": next_generation,
        "cases": cases,
        "overflow_count": overflow_count,
        "saturated": saturated,
    }
    return configuration(ctx.state)


def record_failure(
    state: Any,
    *,
    generation: Any,
    code: Any,
    has_quote: Any,
    has_refs: Any,
) -> None:
    """Mutate existing enabled valid generation-matched developer diagnostics only."""
    if type(has_quote) is not bool or type(has_refs) is not bool:
        return
    if type(generation) is not int:
        return

    status, diag = _inspect_diagnostics(state)
    if status != "valid":
        return
    assert diag is not None
    if not diag["enabled"]:
        return
    if diag["generation"] != generation:
        return

    sanitized_code = code if isinstance(code, str) and code in ALLOWED_CODES else "other"
    cases = diag["cases"]

    for case in cases:
        if (
            case["stage"] == STAGE_ASSISTANT_JOB
            and case["code"] == sanitized_code
            and case["has_quote"] == has_quote
            and case["has_refs"] == has_refs
        ):
            if case["count"] < MAX_COUNT:
                case["count"] += 1
                if case["count"] == MAX_COUNT:
                    diag["saturated"] = True
            else:
                diag["saturated"] = True
            return

    if len(cases) < MAX_CASES:
        cases.append(
            {
                "stage": STAGE_ASSISTANT_JOB,
                "code": sanitized_code,
                "has_quote": has_quote,
                "has_refs": has_refs,
                "count": 1,
            }
        )
    else:
        diag["saturated"] = True
        if diag["overflow_count"] < MAX_COUNT:
            diag["overflow_count"] += 1


def build_report(state: Any, *, version: Any) -> dict[str, Any]:
    """Generate fixed format sanitized defect report with validated SemVer."""
    if (
        not isinstance(version, str)
        or len(version) > MAX_VERSION_LENGTH
        or not _SEMVER_REGEX.fullmatch(version)
    ):
        raise DomainError("invalid_field", "version")

    status, diag = _inspect_diagnostics(state)
    if status == "invalid":
        raise DomainError("invalid_field", "developer_diagnostics")

    if status == "absent":
        cases: list[dict[str, Any]] = []
        overflow_count = 0
        saturated = False
    else:
        assert diag is not None
        cases = copy.deepcopy(diag["cases"])
        overflow_count = diag["overflow_count"]
        saturated = diag["saturated"]

    sorted_cases = sorted(
        cases,
        key=lambda c: (c["stage"], c["code"], c["has_quote"], c["has_refs"], c["count"]),
    )

    return {
        "format": REPORT_FORMAT,
        "schema": REPORT_SCHEMA,
        "version": version,
        "cases": sorted_cases,
        "overflow_count": overflow_count,
        "saturated": saturated,
        "limitations": list(FIXED_LIMITATIONS),
    }
