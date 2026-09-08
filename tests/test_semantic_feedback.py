"""Tests for semantic feedback domain module."""

from __future__ import annotations

import copy
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import new_state
from custom_components.family_assistant.domain.semantic_feedback import (
    MAX_ACTIVE_RECORDS,
    _is_valid_record,
    capture,
    project,
    purge,
)
from custom_components.family_assistant.domain.validation import DomainError


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_state() -> dict:
    state = new_state("synthetic-owner", "Example household")
    for key, role in (
        ("parent", "parent"),
        ("child", "child"),
        ("sibling", "child"),
        ("adult", "adult"),
        ("guest", "guest"),
    ):
        state["members"][key] = {
            "id": key,
            "name": key.title(),
            "role": role,
            "language": "en",
            "ha_user_id": f"synthetic-{key}",
            "aliases": [],
            "active": True,
            "revision": 1,
        }
    return state


def _make_proposal(
    proposal_id: str,
    actor: str = "adult",
    role: str = "adult",
    actor_revision: int = 1,
    source: str = "Please turn off the living room lights",
    status: str = "pending",
    expires_delta: timedelta = timedelta(minutes=5),
    preview: str = "Turn off light.living_room",
    now: datetime | None = None,
) -> dict:
    if now is None:
        now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    return {
        "id": proposal_id,
        "operation_id": f"op-{proposal_id}",
        "actor": actor,
        "role": role,
        "actor_revision": actor_revision,
        "source_hash": _hash(source),
        "status": status,
        "preview": preview,
        "commands": [{"action": "homeassistant.turn_off", "payload": {}}],
        "quote": "turn off living room",
        "config": {"debug": True},
        "created_at": now.isoformat(),
        "expires_at": (now + expires_delta).isoformat(),
        "revision": 1,
    }


def _make_context(
    state: dict,
    actor_id: str = "adult",
    now: datetime | None = None,
    op_id: str = "op-test",
) -> Context:
    if now is None:
        now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    actor = state["members"][actor_id]
    return Context(state, actor, now, op_id)


def test_capture_success_minimal_and_private_record() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P001", "adult", "adult", 1, now=now)

    payload = {
        "category": "wrong_action",
        "expected": "I wanted the air conditioner turned off, not the lights.",
    }

    result = capture(ctx, proposal, payload)
    assert result == {
        "id": "F000001",
        "status": "recorded",
        "actor_revision": 1,
        "role": "adult",
    }

    store = state["memory"]["semantic_feedback"]
    assert "F000001" in store
    rec = store["F000001"]

    assert rec["id"] == "F000001"
    assert rec["actor"] == "adult"
    assert rec["actor_revision"] == 1
    assert rec["role"] == "adult"
    assert rec["proposal_id"] == "P001"
    assert rec["category"] == "wrong_action"
    assert rec["expected"] == "I wanted the air conditioner turned off, not the lights."
    assert rec["source"] == ""
    assert rec["source_available"] is False
    assert rec["preview"] == "Turn off light.living_room"
    assert rec["created_at"] == now.isoformat()

    # Proposal commands/quote/config must not be copied
    assert "commands" not in rec
    assert "quote" not in rec
    assert "config" not in rec


def test_capture_success_with_matching_source() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    orig_source = "turn off living room lights"
    proposal = _make_proposal("P002", "adult", "adult", 1, source=orig_source, now=now)

    payload = {
        "category": "wrong_target",
        "expected": "Turn off bedroom instead",
        "source": orig_source,
    }

    result = capture(ctx, proposal, payload)
    assert result["status"] == "recorded"

    rec = state["memory"]["semantic_feedback"][result["id"]]
    assert rec["source"] == orig_source
    assert rec["source_available"] is True


def test_capture_source_hash_mismatch_raises_invalid_field() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P003", "adult", "adult", 1, source="turn off lights", now=now)

    payload = {
        "category": "wrong_action",
        "expected": "Do nothing",
        "source": "turn off something else",
    }

    with pytest.raises(DomainError) as exc:
        capture(ctx, proposal, payload)
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "source"


def test_capture_payload_source_validation() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P004", "adult", "adult", 1, now=now)

    # Empty string
    with pytest.raises(DomainError) as exc1:
        capture(ctx, proposal, {"category": "wrong_time", "expected": "Soon", "source": ""})
    assert exc1.value.code == "invalid_field"
    assert exc1.value.field == "source"

    # Whitespace only
    with pytest.raises(DomainError) as exc2:
        capture(ctx, proposal, {"category": "wrong_time", "expected": "Soon", "source": "   "})
    assert exc2.value.code == "invalid_field"
    assert exc2.value.field == "source"

    # Non-string
    with pytest.raises(DomainError) as exc3:
        capture(ctx, proposal, {"category": "wrong_time", "expected": "Soon", "source": 12345})
    assert exc3.value.code == "invalid_field"
    assert exc3.value.field == "source"

    # Over 4096 chars
    long_src = "a" * 4097
    long_proposal = _make_proposal("P004b", "adult", "adult", 1, source=long_src, now=now)
    with pytest.raises(DomainError) as exc4:
        capture(
            ctx,
            long_proposal,
            {"category": "wrong_time", "expected": "Soon", "source": long_src},
        )
    assert exc4.value.code == "invalid_field"
    assert exc4.value.field == "source"


def test_capture_payload_expected_validation() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P005", "adult", "adult", 1, now=now)

    # Empty string
    with pytest.raises(DomainError) as exc1:
        capture(ctx, proposal, {"category": "other", "expected": ""})
    assert exc1.value.code == "invalid_field"
    assert exc1.value.field == "expected"

    # Whitespace only
    with pytest.raises(DomainError) as exc2:
        capture(ctx, proposal, {"category": "other", "expected": "   \n  "})
    assert exc2.value.code == "invalid_field"
    assert exc2.value.field == "expected"

    # Non-string
    with pytest.raises(DomainError) as exc3:
        capture(ctx, proposal, {"category": "other", "expected": ["bad"]})
    assert exc3.value.code == "invalid_field"
    assert exc3.value.field == "expected"

    # Over 400 chars
    with pytest.raises(DomainError) as exc4:
        capture(ctx, proposal, {"category": "other", "expected": "x" * 401})
    assert exc4.value.code == "invalid_field"
    assert exc4.value.field == "expected"


def test_capture_payload_category_validation() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)

    for valid_cat in ("wrong_action", "wrong_target", "wrong_time", "other"):
        p = _make_proposal(f"P-cat-{valid_cat}", "adult", "adult", 1, now=now)
        res = capture(ctx, p, {"category": valid_cat, "expected": "Expected result"})
        assert res["status"] == "recorded"

    invalid_p = _make_proposal("P-cat-invalid", "adult", "adult", 1, now=now)
    with pytest.raises(DomainError) as exc:
        capture(ctx, invalid_p, {"category": "unsupported_cat", "expected": "Expected result"})
    assert exc.value.code == "invalid_field"
    assert exc.value.field == "category"


def test_capture_unknown_and_missing_payload_fields() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P006", "adult", "adult", 1, now=now)

    # Missing expected
    with pytest.raises(DomainError) as exc1:
        capture(ctx, proposal, {"category": "wrong_action"})
    assert exc1.value.code == "invalid_field"

    # Missing category
    with pytest.raises(DomainError) as exc2:
        capture(ctx, proposal, {"expected": "Some expectation"})
    assert exc2.value.code == "invalid_field"

    # Unknown field
    with pytest.raises(DomainError) as exc3:
        capture(
            ctx,
            proposal,
            {"category": "wrong_action", "expected": "Action", "unknown_extra": 123},
        )
    assert exc3.value.code == "invalid_field"
    assert exc3.value.field == "unknown_extra"


def test_capture_preview_bounded_to_2200() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    long_preview = "P" * 3000
    proposal = _make_proposal("P007", "adult", "adult", 1, preview=long_preview, now=now)

    result = capture(ctx, proposal, {"category": "other", "expected": "Bounded preview test"})
    rec = state["memory"]["semantic_feedback"][result["id"]]
    assert len(rec["preview"]) == 2200
    assert rec["preview"] == "P" * 2200


def test_capture_proposal_validation() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    payload = {"category": "other", "expected": "Test validation"}

    # Not a dict
    with pytest.raises(DomainError) as exc1:
        capture(ctx, "invalid_proposal", payload)
    assert exc1.value.code == "invalid_field"

    # Missing id
    bad_p1 = _make_proposal("P_bad1", now=now)
    del bad_p1["id"]
    with pytest.raises(DomainError) as exc2:
        capture(ctx, bad_p1, payload)
    assert exc2.value.code == "invalid_field"

    # Invalid source_hash (not 64 hex characters)
    bad_p2 = _make_proposal("P_bad2", now=now)
    bad_p2["source_hash"] = "not-a-valid-sha256"
    with pytest.raises(DomainError) as exc3:
        capture(ctx, bad_p2, payload)
    assert exc3.value.code == "invalid_field"
    assert exc3.value.field == "source_hash"

    # Invalid preview
    bad_p3 = _make_proposal("P_bad3", now=now)
    bad_p3["preview"] = 12345
    with pytest.raises(DomainError) as exc4:
        capture(ctx, bad_p3, payload)
    assert exc4.value.code == "invalid_field"
    assert exc4.value.field == "preview"


def test_capture_proposal_status_and_expiration() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    payload = {"category": "other", "expected": "Test expiry"}

    # Status rejected
    p_rej = _make_proposal("P_rej", "adult", "adult", 1, status="rejected", now=now)
    with pytest.raises(DomainError) as exc1:
        capture(ctx, p_rej, payload)
    assert exc1.value.code == "proposal_expired"

    # Status applied
    p_app = _make_proposal("P_app", "adult", "adult", 1, status="applied", now=now)
    with pytest.raises(DomainError) as exc2:
        capture(ctx, p_app, payload)
    assert exc2.value.code == "proposal_expired"

    # Expired timestamp (now >= expires_at)
    p_exp = _make_proposal(
        "P_exp", "adult", "adult", 1, expires_delta=timedelta(seconds=-1), now=now
    )
    with pytest.raises(DomainError) as exc3:
        capture(ctx, p_exp, payload)
    assert exc3.value.code == "proposal_expired"


def test_capture_roles_and_actor_epochs() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx_adult = _make_context(state, "adult", now)
    payload = {"category": "other", "expected": "Epoch test"}

    # Mismatched actor
    p_other_actor = _make_proposal("P_other_act", actor="parent", role="parent", now=now)
    with pytest.raises(DomainError) as exc1:
        capture(ctx_adult, p_other_actor, payload)
    assert exc1.value.code == "forbidden"

    # Mismatched role
    p_other_role = _make_proposal("P_other_role", actor="adult", role="parent", now=now)
    with pytest.raises(DomainError) as exc2:
        capture(ctx_adult, p_other_role, payload)
    assert exc2.value.code == "forbidden"

    # Mismatched actor revision (old or different epoch)
    p_old_rev = _make_proposal("P_old_rev", actor="adult", role="adult", actor_revision=2, now=now)
    with pytest.raises(DomainError) as exc3:
        capture(ctx_adult, p_old_rev, payload)
    assert exc3.value.code == "conflict"


def test_capture_idempotent_and_conflict_on_same_proposal() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    source = "set alarm 7am"
    proposal = _make_proposal("P_dup", "adult", "adult", 1, source=source, now=now)

    payload = {"category": "wrong_time", "expected": "Set to 8am", "source": source}

    # First capture
    res1 = capture(ctx, proposal, payload)
    assert res1["status"] == "recorded"

    # Exact duplicate capture returns exact old result
    res2 = capture(ctx, proposal, payload)
    assert res2 == res1

    # Exactly 1 record stored
    assert len(state["memory"]["semantic_feedback"]) == 1

    # Conflict on changed category
    with pytest.raises(DomainError) as exc1:
        capture(ctx, proposal, {"category": "other", "expected": "Set to 8am", "source": source})
    assert exc1.value.code == "conflict"

    # Conflict on changed expected
    with pytest.raises(DomainError) as exc2:
        capture(
            ctx, proposal, {"category": "wrong_time", "expected": "Set to 9am", "source": source}
        )
    assert exc2.value.code == "conflict"

    # Conflict on omitted source when original had source
    with pytest.raises(DomainError) as exc3:
        capture(ctx, proposal, {"category": "wrong_time", "expected": "Set to 8am"})
    assert exc3.value.code == "conflict"


def test_capacity_max64_no_eviction() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)

    # Fill 64 records
    for i in range(MAX_ACTIVE_RECORDS):
        p = _make_proposal(f"P_cap_{i}", "adult", "adult", 1, now=now)
        capture(ctx, p, {"category": "other", "expected": f"Expected {i}"})

    assert len(state["memory"]["semantic_feedback"]) == 64
    first_record_id = "F000001"
    assert first_record_id in state["memory"]["semantic_feedback"]

    # 65th capture fails with capacity_reached
    p65 = _make_proposal("P_cap_65", "adult", "adult", 1, now=now)
    with pytest.raises(DomainError) as exc:
        capture(ctx, p65, {"category": "other", "expected": "Expected 65"})
    assert exc.value.code == "capacity_reached"

    # Verify root REJECTS automatic FIFO eviction: exactly 64 records, F000001 intact
    store = state["memory"]["semantic_feedback"]
    assert len(store) == 64
    assert first_record_id in store

    # Idempotent replay of existing record still succeeds at capacity
    p0 = _make_proposal("P_cap_0", "adult", "adult", 1, now=now)
    replay = capture(ctx, p0, {"category": "other", "expected": "Expected 0"})
    assert replay["id"] == first_record_id
    assert replay["status"] == "recorded"


def test_no_false_anonymization() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "child", now)
    proposal = _make_proposal("P_child", "child", "child", 1, now=now)

    result = capture(ctx, proposal, {"category": "wrong_action", "expected": "Not this"})
    rec = state["memory"]["semantic_feedback"][result["id"]]

    # Member name/id is NOT masked as [REDACTED] or synthetic anonymous placeholder
    assert rec["actor"] == "child"
    assert rec["actor_revision"] == 1
    assert rec["role"] == "child"


def test_projection_privacy_epoch_and_copy_isolation() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()

    ctx_child = _make_context(state, "child", now)
    p_child = _make_proposal("P_proj_c", "child", "child", 1, now=now)
    res_child = capture(ctx_child, p_child, {"category": "wrong_action", "expected": "Child note"})

    ctx_adult = _make_context(state, "adult", now)
    p_adult = _make_proposal("P_proj_a", "adult", "adult", 1, now=now)
    res_adult = capture(ctx_adult, p_adult, {"category": "other", "expected": "Adult note"})

    # Child sees only child record
    proj_child = project(state, state["members"]["child"])
    assert proj_child["available"] is True
    assert len(proj_child["records"]) == 1
    assert proj_child["records"][0]["id"] == res_child["id"]

    # Owner / parent never bypasses child privacy
    proj_owner = project(state, state["members"]["parent"])
    assert proj_owner["available"] is True
    assert len(proj_owner["records"]) == 0

    # Adult sees only adult record
    proj_adult = project(state, state["members"]["adult"])
    assert proj_adult["available"] is True
    assert len(proj_adult["records"]) == 1
    assert proj_adult["records"][0]["id"] == res_adult["id"]

    # Member revision increment hides previous epoch records
    state["members"]["adult"]["revision"] = 2
    proj_adult_new_rev = project(state, state["members"]["adult"])
    assert proj_adult_new_rev["available"] is True
    assert len(proj_adult_new_rev["records"]) == 0

    # Copy isolation: modifying projection copy does not mutate storage
    state["members"]["adult"]["revision"] = 1
    proj_adult_again = project(state, state["members"]["adult"])
    proj_adult_again["records"][0]["expected"] = "TAMPERED"
    assert state["memory"]["semantic_feedback"][res_adult["id"]]["expected"] == "Adult note"


def test_purge_success_and_capacity_recovery() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)

    # Add 64 items
    for i in range(MAX_ACTIVE_RECORDS):
        p = _make_proposal(f"P_purge_{i}", "adult", "adult", 1, now=now)
        capture(ctx, p, {"category": "other", "expected": f"Expected {i}"})

    assert len(state["memory"]["semantic_feedback"]) == 64

    # Purge one specific record
    purge_payload = {"id": "F000001", "confirmed": True}
    res = purge(ctx, purge_payload)
    assert res == {
        "id": "F000001",
        "status": "purged",
        "actor_revision": 1,
        "role": "adult",
    }

    assert "F000001" not in state["memory"]["semantic_feedback"]
    assert len(state["memory"]["semantic_feedback"]) == 63
    # Only that record was removed; other records intact
    assert "F000002" in state["memory"]["semantic_feedback"]

    # Now capacity is recovered: can capture a 65th proposal
    p_new = _make_proposal("P_after_purge", "adult", "adult", 1, now=now)
    res_new = capture(ctx, p_new, {"category": "wrong_action", "expected": "New one"})
    assert res_new["status"] == "recorded"
    assert len(state["memory"]["semantic_feedback"]) == 64


def test_purge_validation_and_authorization() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx_adult = _make_context(state, "adult", now)
    p = _make_proposal("P_purge_val", "adult", "adult", 1, now=now)
    cap = capture(ctx_adult, p, {"category": "other", "expected": "Purge test"})
    rec_id = cap["id"]

    # Non-dict payload
    with pytest.raises(DomainError) as exc1:
        purge(ctx_adult, "bad_payload")
    assert exc1.value.code == "invalid_field"

    # Missing confirmed
    with pytest.raises(DomainError) as exc2:
        purge(ctx_adult, {"id": rec_id})
    assert exc2.value.code == "invalid_field"

    # confirmed not strict True
    with pytest.raises(DomainError) as exc3:
        purge(ctx_adult, {"id": rec_id, "confirmed": False})
    assert exc3.value.code == "invalid_field"
    assert exc3.value.field == "confirmed"

    with pytest.raises(DomainError) as exc3b:
        purge(ctx_adult, {"id": rec_id, "confirmed": 1})
    assert exc3b.value.code == "invalid_field"
    assert exc3b.value.field == "confirmed"

    # Unknown payload fields
    with pytest.raises(DomainError) as exc4:
        purge(ctx_adult, {"id": rec_id, "confirmed": True, "extra": "boom"})
    assert exc4.value.code == "invalid_field"

    # Non-existent record id
    with pytest.raises(DomainError) as exc5:
        purge(ctx_adult, {"id": "F999999", "confirmed": True})
    assert exc5.value.code == "not_found"

    # Purging record belonging to another actor is forbidden
    ctx_child = _make_context(state, "child", now)
    with pytest.raises(DomainError) as exc6:
        purge(ctx_child, {"id": rec_id, "confirmed": True})
    assert exc6.value.code == "forbidden"

    # Purging record belonging to an older epoch is conflict
    state["members"]["adult"]["revision"] = 2
    ctx_adult_v2 = _make_context(state, "adult", now)
    with pytest.raises(DomainError) as exc7:
        purge(ctx_adult_v2, {"id": rec_id, "confirmed": True})
    assert exc7.value.code == "conflict"


def test_corrupted_shape_no_overwrites() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

    # 1. semantic_feedback is not a dict
    corrupted_state1 = _make_state()
    corrupted_state1["memory"]["semantic_feedback"] = "MALFORMED_STRING"
    ctx1 = _make_context(corrupted_state1, "adult", now)
    p1 = _make_proposal("P_corr1", "adult", "adult", 1, now=now)
    payload1 = {"category": "other", "expected": "Will fail"}

    with pytest.raises(DomainError) as exc1:
        capture(ctx1, p1, payload1)
    assert exc1.value.code == "invalid_field"
    assert exc1.value.field == "semantic_feedback"
    assert corrupted_state1["memory"]["semantic_feedback"] == "MALFORMED_STRING"

    # Purge on corrupted state
    with pytest.raises(DomainError) as exc1_purge:
        purge(ctx1, {"id": "F000001", "confirmed": True})
    assert exc1_purge.value.code == "invalid_field"
    assert corrupted_state1["memory"]["semantic_feedback"] == "MALFORMED_STRING"

    # Projection safely returns available: False without raising or leaking
    proj1 = project(corrupted_state1, corrupted_state1["members"]["adult"])
    assert proj1 == {"available": False, "records": []}

    # 2. semantic_feedback contains corrupted record
    corrupted_state2 = _make_state()
    corrupted_state2["memory"]["semantic_feedback"] = {"F000001": {"corrupted": True}}
    state_before = copy.deepcopy(corrupted_state2)
    ctx2 = _make_context(corrupted_state2, "adult", now)
    p2 = _make_proposal("P_corr2", "adult", "adult", 1, now=now)

    with pytest.raises(DomainError) as exc2:
        capture(ctx2, p2, payload1)
    assert exc2.value.code == "invalid_field"
    assert exc2.value.field == "semantic_feedback"
    assert corrupted_state2 == state_before

    proj2 = project(corrupted_state2, corrupted_state2["members"]["adult"])
    assert proj2 == {"available": False, "records": []}

    # 3. memory is not a dict
    corrupted_state3 = _make_state()
    corrupted_state3["memory"] = 42
    ctx3 = _make_context(corrupted_state3, "adult", now)
    p3 = _make_proposal("P_corr3", "adult", "adult", 1, now=now)

    with pytest.raises(DomainError) as exc3:
        capture(ctx3, p3, payload1)
    assert exc3.value.code == "invalid_field"
    assert corrupted_state3["memory"] == 42

    proj3 = project(corrupted_state3, corrupted_state3["members"]["adult"])
    assert proj3 == {"available": False, "records": []}


def _make_valid_record(
    rec_id: str = "F000001",
    actor: str = "adult",
    actor_revision: int = 1,
    role: str = "adult",
    proposal_id: str = "P001",
    category: str = "wrong_action",
    expected: str = "Expected result",
    source: str = "",
    source_available: bool = False,
    preview: str = "Preview",
    created_at: str | None = None,
    revision: int | None = 1,
    updated_at: str | None = None,
) -> dict:
    if created_at is None:
        created_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC).isoformat()
    rec = {
        "id": rec_id,
        "actor": actor,
        "actor_revision": actor_revision,
        "role": role,
        "proposal_id": proposal_id,
        "category": category,
        "expected": expected,
        "source": source,
        "source_available": source_available,
        "preview": preview,
        "created_at": created_at,
    }
    if revision is not None:
        rec["revision"] = revision
    if updated_at is not None:
        rec["updated_at"] = updated_at
    return rec


@pytest.mark.parametrize(
    "category",
    [
        ["wrong_action"],
        {"wrong_action": True},
        ("wrong_action",),
        set(["wrong_action"]),
        123,
        None,
        "",
        "   ",
        "invalid_category",
    ],
)
def test_is_valid_record_unhashable_and_invalid_category(category) -> None:
    rec = _make_valid_record()
    rec["category"] = category
    # Must return False without raising TypeError or any unhandled exception
    assert _is_valid_record(rec) is False


@pytest.mark.parametrize(
    "role,expected_valid",
    [
        ("owner", True),
        ("parent", True),
        ("adult", True),
        ("child", True),
        ("guest", False),
        ("admin", False),
        ("", False),
        (None, False),
        (123, False),
        (["adult"], False),
        ({"role": "adult"}, False),
    ],
)
def test_is_valid_record_actor_roles(role, expected_valid) -> None:
    rec = _make_valid_record(role="adult")
    rec["role"] = role
    assert _is_valid_record(rec) is expected_valid


@pytest.mark.parametrize(
    "id_field",
    ["id", "actor", "proposal_id"],
)
@pytest.mark.parametrize(
    "invalid_val",
    [
        "x" * 81,  # exceeds MAX_ID_LENGTH 80
        "",
        "   ",
        " has_leading_space",
        "has_trailing_space ",
        None,
        123,
        [],
        {},
    ],
)
def test_is_valid_record_bounded_ids(id_field, invalid_val) -> None:
    rec = _make_valid_record()
    rec[id_field] = invalid_val
    assert _is_valid_record(rec) is False


@pytest.mark.parametrize(
    "rev_field",
    ["actor_revision", "revision"],
)
@pytest.mark.parametrize(
    "invalid_rev",
    [
        0,
        -1,
        2**53,  # exceeds 2**53 - 1
        2**53 + 1,
        True,  # bool is subclass of int in Python
        False,
        1.5,
        "1",
        None,
        [],
    ],
)
def test_is_valid_record_safe_revisions(rev_field, invalid_rev) -> None:
    rec = _make_valid_record()
    rec[rev_field] = invalid_rev
    assert _is_valid_record(rec) is False


@pytest.mark.parametrize("ts_field", ["created_at", "updated_at"])
def test_is_valid_record_string_timestamps_not_datetime(ts_field) -> None:
    rec = _make_valid_record()
    # Python datetime object must NOT be accepted as stored timestamp
    rec[ts_field] = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    assert _is_valid_record(rec) is False

    # Valid ISO string must be accepted
    rec[ts_field] = "2026-09-08T12:00:00+00:00"
    assert _is_valid_record(rec) is True

    # Non-date string must be rejected
    rec[ts_field] = "not-a-timestamp"
    assert _is_valid_record(rec) is False


def test_semantic_feedback_none_is_malformed_not_overwritten() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    state["memory"]["semantic_feedback"] = None
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P_none", "adult", "adult", 1, now=now)
    payload = {"category": "other", "expected": "Expectation"}

    # capture must raise invalid_field and MUST NOT overwrite None with {}
    with pytest.raises(DomainError) as exc_cap:
        capture(ctx, proposal, payload)
    assert exc_cap.value.code == "invalid_field"
    assert exc_cap.value.field == "semantic_feedback"
    assert state["memory"]["semantic_feedback"] is None

    # purge must raise invalid_field and MUST NOT overwrite None
    with pytest.raises(DomainError) as exc_pur:
        purge(ctx, {"id": "F000001", "confirmed": True})
    assert exc_pur.value.code == "invalid_field"
    assert exc_pur.value.field == "semantic_feedback"
    assert state["memory"]["semantic_feedback"] is None

    # project must fail closed without exception
    proj = project(state, state["members"]["adult"])
    assert proj == {"available": False, "records": []}
    assert state["memory"]["semantic_feedback"] is None


def test_state_memory_none_is_malformed() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    state["memory"] = None
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P_mem_none", "adult", "adult", 1, now=now)
    payload = {"category": "other", "expected": "Expectation"}

    with pytest.raises(DomainError) as exc_cap:
        capture(ctx, proposal, payload)
    assert exc_cap.value.code == "invalid_field"
    assert exc_cap.value.field == "semantic_feedback"

    proj = project(state, state["members"]["adult"])
    assert proj == {"available": False, "records": []}


def test_store_exact_dict_key_equals_record_id() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P_mismatch", "adult", "adult", 1, now=now)

    # Key in dict is "F000001", but record["id"] is "F000002"
    bad_rec = _make_valid_record(rec_id="F000002")
    state["memory"]["semantic_feedback"] = {"F000001": bad_rec}

    with pytest.raises(DomainError) as exc_cap:
        capture(ctx, proposal, {"category": "other", "expected": "Expectation"})
    assert exc_cap.value.code == "invalid_field"
    assert exc_cap.value.field == "semantic_feedback"

    with pytest.raises(DomainError) as exc_pur:
        purge(ctx, {"id": "F000001", "confirmed": True})
    assert exc_pur.value.code == "invalid_field"
    assert exc_pur.value.field == "semantic_feedback"

    proj = project(state, state["members"]["adult"])
    assert proj == {"available": False, "records": []}


def test_store_duplicate_proposal_id_corruption() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P_dup_test", "adult", "adult", 1, now=now)

    # Two records in store sharing the same proposal_id "P_SAME"
    rec1 = _make_valid_record(rec_id="F000001", proposal_id="P_SAME")
    rec2 = _make_valid_record(rec_id="F000002", proposal_id="P_SAME")
    state["memory"]["semantic_feedback"] = {"F000001": rec1, "F000002": rec2}

    with pytest.raises(DomainError) as exc_cap:
        capture(ctx, proposal, {"category": "other", "expected": "Expectation"})
    assert exc_cap.value.code == "invalid_field"
    assert exc_cap.value.field == "semantic_feedback"

    proj = project(state, state["members"]["adult"])
    assert proj == {"available": False, "records": []}


def test_store_exceeds_64_records_is_corrupt() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P_over64", "adult", "adult", 1, now=now)

    # Populate 65 records in store
    store = {}
    for i in range(65):
        store[f"F{i:06}"] = _make_valid_record(rec_id=f"F{i:06}", proposal_id=f"P{i:06}")
    state["memory"]["semantic_feedback"] = store

    with pytest.raises(DomainError) as exc_cap:
        capture(ctx, proposal, {"category": "other", "expected": "Expectation"})
    assert exc_cap.value.code == "invalid_field"
    assert exc_cap.value.field == "semantic_feedback"

    proj = project(state, state["members"]["adult"])
    assert proj == {"available": False, "records": []}


@pytest.mark.parametrize(
    "role",
    ["guest", "stranger", "visitor"],
)
def test_guest_actor_rejected_by_all_operations(role) -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    state["members"]["guest"]["role"] = role
    ctx = _make_context(state, "guest", now)
    proposal = _make_proposal("P_guest", actor="guest", role=role, actor_revision=1, now=now)
    payload = {"category": "other", "expected": "Guest action"}

    # capture rejects
    with pytest.raises(DomainError) as exc_cap:
        capture(ctx, proposal, payload)
    assert exc_cap.value.code == "forbidden"

    # purge rejects
    with pytest.raises(DomainError) as exc_pur:
        purge(ctx, {"id": "F000001", "confirmed": True})
    assert exc_pur.value.code == "forbidden"

    # project fails closed without exception
    proj = project(state, state["members"]["guest"])
    assert proj == {"available": False, "records": []}


def test_inactive_actor_rejected_by_all_operations() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    state["members"]["adult"]["active"] = False
    ctx = _make_context(state, "adult", now)
    proposal = _make_proposal("P_inact", "adult", "adult", 1, now=now)
    payload = {"category": "other", "expected": "Inactive test"}

    # capture rejects
    with pytest.raises(DomainError) as exc_cap:
        capture(ctx, proposal, payload)
    assert exc_cap.value.code == "forbidden"

    # purge rejects
    with pytest.raises(DomainError) as exc_pur:
        purge(ctx, {"id": "F000001", "confirmed": True})
    assert exc_pur.value.code == "forbidden"

    # project fails closed
    proj = project(state, state["members"]["adult"])
    assert proj == {"available": False, "records": []}


def test_sequence_collision_fails_closed_without_overwriting() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)

    # Capture first proposal -> creates F000001
    p1 = _make_proposal("P_first", "adult", "adult", 1, now=now)
    res1 = capture(ctx, p1, {"category": "other", "expected": "First record"})
    assert res1["id"] == "F000001"

    # Corrupt sequences counter back to 0 so next identifier("F") yields "F000001"
    state["sequences"]["F"] = 0

    p2 = _make_proposal("P_second", "adult", "adult", 1, now=now)
    with pytest.raises(DomainError) as exc:
        capture(ctx, p2, {"category": "wrong_action", "expected": "Colliding record"})
    assert exc.value.code == "conflict"

    # Verify F000001 was NOT overwritten or touched
    store = state["memory"]["semantic_feedback"]
    assert len(store) == 1
    assert store["F000001"]["proposal_id"] == "P_first"
    assert store["F000001"]["expected"] == "First record"


def test_duplicate_capture_requires_same_actor_epoch() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)

    p = _make_proposal("P_epoch", "adult", "adult", 1, now=now)
    payload = {"category": "wrong_time", "expected": "Time test"}

    # Initial capture at epoch (adult, revision 1, adult)
    res = capture(ctx, p, payload)
    assert res["status"] == "recorded"

    # Replay with same epoch -> succeeds
    res_replay = capture(ctx, p, payload)
    assert res_replay == res

    # Actor revision advances to 2
    state["members"]["adult"]["revision"] = 2
    ctx_v2 = _make_context(state, "adult", now)

    # Proposal with updated actor revision 2
    p_v2 = _make_proposal("P_epoch", "adult", "adult", 2, now=now)

    # Duplicate capture of same proposal when existing record is epoch 1 must raise conflict
    with pytest.raises(DomainError) as exc:
        capture(ctx_v2, p_v2, payload)
    assert exc.value.code == "conflict"


def test_source_byte_exactness_preserved_with_whitespace_and_unicode() -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    state = _make_state()
    ctx = _make_context(state, "adult", now)

    # Complex source containing unicode, leading/trailing spaces, newlines, tabs
    exact_source = "\r\n\t  Please adjust AC thermostat to 21.5°C — quickly!  \n\t"
    exact_hash = hashlib.sha256(exact_source.encode("utf-8")).hexdigest()

    p = _make_proposal("P_exact_src", "adult", "adult", 1, source="placeholder", now=now)
    p["source_hash"] = exact_hash

    payload = {
        "category": "wrong_action",
        "expected": "Set to 22C instead",
        "source": exact_source,
    }

    res = capture(ctx, p, payload)
    rec = state["memory"]["semantic_feedback"][res["id"]]

    # Exact bytes and string must be preserved; no stripping or naive anonymization
    assert rec["source"] == exact_source
    assert rec["source_available"] is True
    assert hashlib.sha256(rec["source"].encode("utf-8")).hexdigest() == exact_hash


@pytest.mark.parametrize("role", [[], {}, None, True])
def test_unhashable_actor_role_fails_closed(role):
    state = _make_state()
    state["members"]["adult"]["role"] = role
    ctx = _make_context(state)
    assert project(state, ctx.actor) == {"available": False, "records": []}
    with pytest.raises(DomainError, match="forbidden"):
        capture(ctx, _make_proposal("P1"), {"category": "other", "expected": "Expected"})
    with pytest.raises(DomainError, match="forbidden"):
        purge(ctx, {"id": "F1", "confirmed": True})


@pytest.mark.parametrize(
    "sequence", [None, [], {"F": True}, {"F": -1}, {"F": "0"}, {"F": 2**53 - 1}]
)
def test_malformed_sequence_does_not_reset_any_other_domain_counters(sequence):
    state = _make_state()
    state["sequences"] = sequence
    before = copy.deepcopy(sequence)
    with pytest.raises(DomainError, match="invalid_field"):
        capture(
            _make_context(state),
            _make_proposal("P1"),
            {"category": "other", "expected": "Expected"},
        )
    assert state["sequences"] == before
