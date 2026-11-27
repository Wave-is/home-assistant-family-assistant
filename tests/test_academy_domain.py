"""Synthetic Academy tests: scope, deterministic answers and review."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.family_assistant.domain import academy, academy_curriculum
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fixture():
    parent = {"id": "owner", "role": "owner", "active": True, "revision": 1}
    child = {"id": "child", "role": "child", "active": True, "revision": 1}
    sibling = {"id": "sibling", "role": "child", "active": True, "revision": 1}
    state = {"members": {x["id"]: x for x in (parent, child, sibling)},
             "settings": {"modules": ["academy"]}, "sequences": {}}
    result = academy.handle(Context(state, parent, NOW, "a"), "assign",
                            {"member": "child", "member_revision": 1, "grade": 6,
                             "language": "uk", "topics": ["fractions"]})
    return state, parent, child, sibling, result["id"]


def test_private_mastery_and_review():
    state, parent, child, sibling, key = fixture()
    assert not academy.project(state, sibling, NOW)["assignments"]
    assert academy.project(state, parent, NOW)["assignments"][0]["question"] is None
    for i in range(3):
        row = academy.project(state, child, NOW)["assignments"][0]
        assert "answer" not in row["question"]
        _, answer = academy_curriculum.question("fractions", key, i, "uk")
        academy.handle(Context(state, child, NOW, str(i)), "answer",
                       {"id": key, "revision": row["revision"], "topic": "fractions",
                        "answer": str(answer)})
    row = academy.project(state, child, NOW)["assignments"][0]
    assert row["mastered"] == 1 and row["question"] is None
    assert academy.project(state, child, NOW + timedelta(days=1))["assignments"][0]["question"]
    child["revision"] = 2
    assert not academy.project(state, child, NOW)["assignments"]


def test_forbidden_and_stale():
    state, parent, child, sibling, key = fixture()
    payload = {"id": key, "revision": 1, "topic": "fractions", "answer": "1"}
    with pytest.raises(DomainError, match="forbidden"):
        academy.handle(Context(state, sibling, NOW, "s"), "answer", payload)
    with pytest.raises(DomainError, match="forbidden"):
        academy.handle(Context(state, parent, NOW, "p"), "answer", payload)
    academy.handle(Context(state, child, NOW, "c"), "answer", payload)
    with pytest.raises(DomainError, match="conflict"):
        academy.handle(Context(state, child, NOW, "stale"), "answer", payload)
    state["settings"]["modules"] = []
    with pytest.raises(DomainError, match="module_disabled"):
        academy.project(state, child, NOW)
