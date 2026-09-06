"""Synthetic domain fixtures. No running HA, Telegram or router is contacted."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state


@pytest.fixture
def now():
    return datetime(2026, 9, 6, 8, 0, tzinfo=UTC)


class MemoryStore:
    def __init__(self):
        self.value = None
        self.fail = False
        self.calls = 0

    async def save(self, state):
        self.calls += 1
        if self.fail:
            raise OSError("synthetic disk error")
        self.value = deepcopy(state)


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def engine(store):
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
    return Engine(state, store.save)
