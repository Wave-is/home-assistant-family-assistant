"""Recompute full copies; dataclass fields and caller-owned projections grant nothing."""

import json
from dataclasses import replace

import pytest
from test_legacy_shadow import NOW, inputs

from custom_components.family_assistant.migration.shadow import (
    ShadowCandidate,
    ShadowError,
    async_reverify_shadow,
    build_shadow_candidate,
)


def candidate():
    review, target, policy = inputs()
    return build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW), target


@pytest.mark.asyncio
async def test_full_shadow_reverification_retains_exact_bytes_counts_and_source():
    original, target = candidate()
    rebuilt = await async_reverify_shadow(original, target)
    assert rebuilt == original
    assert rebuilt.private_state() == original.private_state()
    assert rebuilt.private_blobs() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "task",
        "amount",
        "modules",
        "summary",
        "archive",
        "reviewers",
        "target",
        "extra_blob",
        "type",
    ],
)
async def test_changed_candidate_or_target_cannot_be_staged(field):
    original, target = candidate()
    state = original.private_state()
    if field == "task":
        state["tasks"]["T000004"]["title"] = "FORGED PRIVATE TITLE"
    if field == "amount":
        state["shopping"]["S000001"]["quantity"] = 100
    if field == "modules":
        state["settings"]["modules"] = ["alarms"]
    if field == "archive":
        state["migration_archive"]["archive"]["court"] = "NOT SOURCE BYTES"
    if field == "reviewers":
        state["migration_archive"]["reviewer_authority"]["policy"]["reviewers"] = {}
    changed = replace(
        original,
        _state=json.dumps(
            state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode(),
    )
    if field == "summary":
        changed = replace(original, _summary=b"{}")
    if field == "target":
        target["members"]["owner"]["revision"] += 1
    if field == "extra_blob":
        changed = replace(original, _blobs=(("a" * 64, b"PRIVATE EXTRA"),))
    if field == "type":
        changed = state
    with pytest.raises(ShadowError) as caught:
        await async_reverify_shadow(changed, target)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.asyncio
async def test_noncanonical_and_duplicate_json_is_not_an_equal_frozen_candidate():
    original, target = candidate()
    changed = ShadowCandidate(original._state + b" ", original._summary)
    with pytest.raises(ShadowError, match="shadow_candidate_changed"):
        await async_reverify_shadow(changed, target)
    duplicate = ShadowCandidate(
        b'{"schema_version":"wrong",' + original._state[1:], original._summary
    )
    with pytest.raises(ShadowError, match="shadow_candidate_changed"):
        await async_reverify_shadow(duplicate, target)
