"""Stored results do not preserve a permission that has been revoked."""

import pytest

from custom_components.family_assistant.domain.validation import DomainError


@pytest.mark.asyncio
async def test_replay_after_parent_role_revoked_is_denied(engine, now):
    payload = {"assignee": "sibling", "title": "Private child task"}
    await engine.execute("parent", "tasks.create", payload, "original", now)
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": engine.snapshot()["members"]["parent"]["revision"],
            "name": "Parent",
            "role": "child",
            "language": "en",
            "active": True,
        },
        "revoke-role",
        now,
    )
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("parent", "tasks.create", payload, "original", now)
