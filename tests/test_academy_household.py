"""Synthetic tests for Academy's canonical household transaction boundary."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.academy.household import AcademyError, mutate, project

NOW = datetime(2026, 1, 1, 22, 30, tzinfo=UTC)
HOUSE = "synthetic-house"


@pytest.fixture
def state():
    return {"settings": {"modules": ["academy"], "timezone": "Europe/Kyiv"}, "members": {
        name: {"id": name, "name": name, "role": role, "active": True, "revision": 1}
        for name, role in [("owner", "owner"), ("parent", "parent"), ("child", "child"),
                           ("sibling", "child"), ("guest", "guest"), ("adult", "adult")]
    }}


def view(state, actor="child", member=None, now=NOW):
    return project(state, HOUSE, actor, now, member)


def enroll(state, member="child", epoch=0, enabled=True, revision=1, actor="parent"):
    return mutate(state, HOUSE, actor, NOW, "enroll", {"member_id": member,
                  "member_revision": revision, "epoch": epoch, "enabled": enabled})


def action(state, command, operation, *, epoch=1, now=NOW, **kw):
    return mutate(state, HOUSE, "child", now, command, {"epoch": epoch,
                  "operation_id": operation, **kw})


def task_fields(state):
    current = view(state)["current"]
    return {"session_id": current["session_id"], "task_id": current["task"]["id"]}


def test_explicit_enrollment_and_role_projection(state):
    assert not view(state)["student"]["enrolled"]
    assert "academy" not in state
    assert len(view(state, "owner")["students"]) == 2
    enroll(state)
    assert view(state)["student"]["enrolled"]
    assert not view(state, "sibling")["student"]["enrolled"]
    assert "current" not in view(state, "parent", "child")
    assert "journal" not in json.dumps(view(state))


@pytest.mark.parametrize("actor", ["child", "sibling", "adult", "guest"])
def test_only_parents_enroll(state, actor):
    with pytest.raises(AcademyError, match="forbidden"):
        enroll(state, actor=actor)
    assert "academy" not in state


@pytest.mark.parametrize("actor", ["adult", "guest", "missing"])
def test_unprivileged_views(state, actor):
    with pytest.raises(AcademyError, match="forbidden"):
        view(state, actor)


def test_sibling_and_parent_cannot_impersonate_learner(state):
    enroll(state)
    with pytest.raises(AcademyError, match="forbidden"):
        view(state, "sibling", "child")
    with pytest.raises(AcademyError, match="forbidden"):
        mutate(state, HOUSE, "parent", NOW, "start", {"epoch": 1, "operation_id": "x"})
    with pytest.raises(AcademyError, match="invalid_field"):
        action(state, "start", "x", member_id="sibling")


def test_disable_module_preserves_private_state(state):
    enroll(state)
    action(state, "start", "s")
    old = deepcopy(state["academy"])
    state["settings"]["modules"] = []
    with pytest.raises(AcademyError, match="module_disabled"):
        view(state)
    with pytest.raises(AcademyError, match="module_disabled"):
        action(state, "start", "s")
    assert state["academy"] == old


def test_enrollment_epoch_and_identity_revision(state):
    enroll(state)
    action(state, "start", "s")
    enroll(state, epoch=1, enabled=False)
    with pytest.raises(AcademyError, match="conflict"):
        action(state, "start", "s")
    enroll(state, epoch=2)
    assert view(state)["current"]["session_id"] == "1:s"
    state["members"]["child"]["revision"] = 2
    assert view(state)["student"]["rebind_required"]
    with pytest.raises(AcademyError, match="conflict"):
        enroll(state, epoch=3, revision=1)
    enroll(state, epoch=3, revision=2)
    assert view(state)["current"] is None
    assert "1" in state["academy"]["child"]["journals"]
    with pytest.raises(AcademyError, match="conflict"):
        action(state, "start", "s", epoch=3)


def test_session_roundtrip_and_hidden_evidence(state):
    enroll(state)
    first = action(state, "start", "s")
    assert first["position"] == 0
    assert "knowledge" not in view(state)
    assert "knowledge" in view(state, "parent", "child")
    action(state, "hint", "h", **task_fields(state))
    action(state, "pause", "p", session_id=first["session_id"])
    reloaded = json.loads(json.dumps(state))
    current = view(reloaded)["current"]
    assert current["status"] == "paused" and current["hints_used"] == 1
    action(reloaded, "resume", "r", session_id=first["session_id"])
    for i in range(3):
        result = action(reloaded, "answer", f"a{i}", answer="-99", **task_fields(reloaded))
        if i < 2:
            assert "knowledge" not in view(reloaded)
    assert result["status"] == "completed"
    assert view(reloaded)["last_report"] == result["report"]
    assert result["report"]["independent_total"] == 2


def test_idempotent_replay_across_midnight(state):
    enroll(state)
    first = action(state, "start", "s")
    old = deepcopy(state)
    assert action(state, "start", "s", now=NOW + timedelta(days=1)) == first
    assert state == old
    journal = json.loads(state["academy"]["child"]["journals"]["1"])
    assert journal["events"][0]["day"] == "2026-01-02"


def test_invalid_input_no_write_and_stale_task(state):
    enroll(state)
    action(state, "start", "s")
    old = deepcopy(state)
    fields = task_fields(state)
    assert action(state, "answer", "a", answer="1/0", **fields)["status"] == "invalid"
    assert state == old
    action(state, "answer", "a", answer="-99", **fields)
    with pytest.raises(AcademyError, match="conflict"):
        action(state, "answer", "b", answer="1", **fields)
    with pytest.raises(AcademyError, match="conflict"):
        action(state, "answer", "a", answer="1", **fields)


@pytest.mark.parametrize("epoch", [True, -1, 1.0, "1"])
def test_epoch_validation(state, epoch):
    with pytest.raises(AcademyError, match="invalid_field"):
        enroll(state, epoch=epoch)
