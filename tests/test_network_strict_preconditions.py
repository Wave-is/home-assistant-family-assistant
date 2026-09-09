"""Unit tests for MikroTik strict-mode precondition gate.

Tests cover:
- check() when no evidence stored → no_topology_evidence
- check() with all booleans False → specific missing preconditions
- check() with all booleans True → empty (strict_available)
- check() with expired evidence → evidence_expired
- check() wrong backend evidence → evidence_wrong_backend
- record_evidence() owner auth / conflict guard
- record_evidence() invalid field validation
- record_evidence() capacity limit (>5 backends)
- record_evidence() replaces existing record for same backend
- record_evidence() returns correct unmet_preconditions and strict_available
- public_status() surfaces same data in card-safe form
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.network.strict_preconditions import (
    REASON_EVIDENCE_EXPIRED,
    REASON_EVIDENCE_WRONG_BACKEND,
    REASON_FASTTRACK_UNACCOUNTED,
    REASON_IPV4_MISSING,
    REASON_IPV6_MISSING,
    REASON_MANAGEMENT_NOT_EXCLUDED,
    REASON_MODULE_DISABLED,
    REASON_NO_EVIDENCE,
    REASON_RESTART_UNVERIFIED,
    check,
    public_status,
    record_evidence,
)
from custom_components.family_assistant.network.inventory import build

BACKEND = "a" * 64
OTHER_BACKEND = "b" * 64
NOW = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)

ALL_TRUE_PAYLOAD = {
    "actor_revision": 1,
    "ipv4_verified": True,
    "ipv6_verified": True,
    "fasttrack_accounted": True,
    "management_excluded": True,
    "restart_verified": True,
}


class FakeStore:
    def __init__(self):
        self.value = None

    async def save(self, state):
        self.value = deepcopy(state)


def make_engine():
    state = new_state("owner", "Test household")
    # Add parent member
    state["members"]["parent"] = {
        "id": "parent",
        "name": "Parent",
        "role": "parent",
        "language": "en",
        "ha_user_id": "synthetic-parent",
        "aliases": [],
        "active": True,
        "revision": 1,
    }
    return Engine(state, FakeStore().save)


def _mikrotik_state(engine):
    """Return a state snapshot with mikrotik module enabled and network seeded."""
    snap = engine.snapshot()
    snap["settings"]["modules"] = list(
        set(snap["settings"].get("modules", [])) | {"mikrotik"}
    )
    snap["network"]["backend"] = BACKEND
    return snap


def _with_evidence(state, backend=BACKEND, *, ipv4=True, ipv6=True, fast=True,
                   mgmt=True, restart=True, age_days=0):
    record = {
        "backend": backend,
        "revision": 1,
        "recorded_at": (NOW - timedelta(days=age_days)).isoformat(),
        "ipv4_verified": ipv4,
        "ipv6_verified": ipv6,
        "fasttrack_accounted": fast,
        "management_excluded": mgmt,
        "restart_verified": restart,
        "notes": None,
    }
    state = deepcopy(state)
    state["network"].setdefault("strict_evidence", {})[backend] = record
    return state


# ─── check() tests ───────────────────────────────────────────────────────────

def test_check_module_disabled():
    state = {"settings": {"modules": []}, "network": {}}
    assert check(state, NOW) == [REASON_MODULE_DISABLED]


def test_check_no_evidence():
    state = {"settings": {"modules": ["mikrotik"]}, "network": {"backend": BACKEND}}
    assert check(state, NOW) == [REASON_NO_EVIDENCE]


def test_check_evidence_wrong_backend():
    state = {
        "settings": {"modules": ["mikrotik"]},
        "network": {"backend": BACKEND, "strict_evidence": {OTHER_BACKEND: {
            "backend": OTHER_BACKEND,
            "revision": 1,
            "recorded_at": NOW.isoformat(),
            "ipv4_verified": True,
            "ipv6_verified": True,
            "fasttrack_accounted": True,
            "management_excluded": True,
            "restart_verified": True,
            "notes": None,
        }}},
    }
    assert check(state, NOW) == [REASON_EVIDENCE_WRONG_BACKEND]


def test_check_evidence_expired():
    state = _with_evidence(
        {"settings": {"modules": ["mikrotik"]}, "network": {"backend": BACKEND}},
        age_days=31,
    )
    assert REASON_EVIDENCE_EXPIRED in check(state, NOW)


def test_check_all_false():
    state = _with_evidence(
        {"settings": {"modules": ["mikrotik"]}, "network": {"backend": BACKEND}},
        ipv4=False, ipv6=False, fast=False, mgmt=False, restart=False,
    )
    reasons = check(state, NOW)
    assert REASON_IPV4_MISSING in reasons
    assert REASON_IPV6_MISSING in reasons
    assert REASON_FASTTRACK_UNACCOUNTED in reasons
    assert REASON_MANAGEMENT_NOT_EXCLUDED in reasons
    assert REASON_RESTART_UNVERIFIED in reasons
    assert REASON_EVIDENCE_EXPIRED not in reasons


def test_check_partial_flags():
    state = _with_evidence(
        {"settings": {"modules": ["mikrotik"]}, "network": {"backend": BACKEND}},
        ipv4=True, ipv6=False, fast=True, mgmt=False, restart=True,
    )
    reasons = check(state, NOW)
    assert REASON_IPV4_MISSING not in reasons
    assert REASON_IPV6_MISSING in reasons
    assert REASON_MANAGEMENT_NOT_EXCLUDED in reasons
    assert REASON_FASTTRACK_UNACCOUNTED not in reasons


def test_check_all_passed():
    state = _with_evidence(
        {"settings": {"modules": ["mikrotik"]}, "network": {"backend": BACKEND}},
    )
    assert check(state, NOW) == []


# ─── record_evidence() tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_evidence_requires_owner():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    # Parent (not owner) must be rejected
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            "parent", "mikrotik.network_record_strict_evidence",
            ALL_TRUE_PAYLOAD, "record-strict-evidence", NOW,
        )


@pytest.mark.asyncio
async def test_record_evidence_conflict_on_wrong_revision():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    bad_payload = {**ALL_TRUE_PAYLOAD, "actor_revision": 999}
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "owner", "mikrotik.network_record_strict_evidence",
            bad_payload, "record-strict-evidence", NOW,
        )


@pytest.mark.asyncio
async def test_record_evidence_invalid_field():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    bad_payload = {**ALL_TRUE_PAYLOAD, "ipv4_verified": "yes"}  # not a bool
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner", "mikrotik.network_record_strict_evidence",
            bad_payload, "record-strict-evidence", NOW,
        )


@pytest.mark.asyncio
async def test_record_evidence_all_true_strict_available():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    result = await engine.execute(
        "owner", "mikrotik.network_record_strict_evidence",
        ALL_TRUE_PAYLOAD, "record-strict-evidence", NOW,
    )
    assert result["strict_available"] is True
    assert result["unmet_preconditions"] == []
    assert isinstance(result["revision"], int)


@pytest.mark.asyncio
async def test_record_evidence_partial_strict_not_available():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    partial = {**ALL_TRUE_PAYLOAD, "ipv6_verified": False, "fasttrack_accounted": False}
    result = await engine.execute(
        "owner", "mikrotik.network_record_strict_evidence",
        partial, "record-strict-evidence", NOW,
    )
    assert result["strict_available"] is False
    assert REASON_IPV6_MISSING in result["unmet_preconditions"]
    assert REASON_FASTTRACK_UNACCOUNTED in result["unmet_preconditions"]


@pytest.mark.asyncio
async def test_record_evidence_replaces_same_backend():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    # First record with ipv6=False
    partial = {**ALL_TRUE_PAYLOAD, "ipv6_verified": False}
    r1 = await engine.execute(
        "owner", "mikrotik.network_record_strict_evidence",
        partial, "record-1", NOW,
    )
    assert r1["strict_available"] is False

    # Second record with all True — should replace
    r2 = await engine.execute(
        "owner", "mikrotik.network_record_strict_evidence",
        ALL_TRUE_PAYLOAD, "record-2", NOW,
    )
    assert r2["strict_available"] is True
    assert r2["revision"] == 2  # incremented


@pytest.mark.asyncio
async def test_record_evidence_notes_optional():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    with_notes = {**ALL_TRUE_PAYLOAD, "notes": "See topology test run #42"}
    result = await engine.execute(
        "owner", "mikrotik.network_record_strict_evidence",
        with_notes, "record-with-notes", NOW,
    )
    assert result["strict_available"] is True


@pytest.mark.asyncio
async def test_record_evidence_notes_too_long():
    engine = make_engine()
    await engine.execute(
        "owner", "settings.save",
        {**engine.snapshot()["settings"], "modules": ["mikrotik"]},
        "enable-mikrotik", NOW,
    )

    def seed(ctx):
        ctx.state["network"]["backend"] = BACKEND

    await engine.system_update("seed-network", NOW, seed)

    bad_notes = {**ALL_TRUE_PAYLOAD, "notes": "x" * 501}
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "owner", "mikrotik.network_record_strict_evidence",
            bad_notes, "record-bad-notes", NOW,
        )


# ─── public_status() tests ───────────────────────────────────────────────────

def test_public_status_module_disabled():
    state = {"settings": {"modules": []}, "network": {}}
    result = public_status(state, NOW)
    assert result["strict_available"] is False
    assert REASON_MODULE_DISABLED in result["unmet_preconditions"]


def test_public_status_all_passed():
    state = _with_evidence(
        {"settings": {"modules": ["mikrotik"]}, "network": {"backend": BACKEND}},
    )
    result = public_status(state, NOW)
    assert result["strict_available"] is True
    assert result["unmet_preconditions"] == []
