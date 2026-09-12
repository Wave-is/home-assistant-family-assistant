"""Reviewed copies retain optional profiles without granting activation authority."""

import json
from copy import deepcopy

import pytest
from test_legacy_shadow import NOW, inputs

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.migration.shadow import (
    ShadowError,
    async_reverify_shadow,
    build_shadow_candidate,
)
from custom_components.family_assistant.telegram.enrollment import Enrollment


@pytest.mark.parametrize(
    "profile",
    [{"birth_date": "2015-02-03", "avatar": "robot"}, {"birth_date": None, "avatar": None}],
)
@pytest.mark.parametrize("linked", [False, True])
async def test_saved_profiles_survive_full_copy_and_reverification(profile, linked):
    review, target, policy = inputs()

    async def save(_state):
        pass

    engine = Engine(target, save)
    for member_id in ("owner", "child"):
        member = engine.snapshot()["members"][member_id]
        await engine.execute(
            "owner",
            "members.save",
            {
                "id": member_id,
                "revision": member["revision"],
                "name": member["name"],
                "role": member["role"],
                **profile,
            },
            f"profile:{member_id}",
            NOW,
        )
    if linked:
        enrollment = Enrollment(engine)
        invite = await enrollment.issue("owner", "member", NOW, "child")
        assert await enrollment.capture(
            {
                "text": f"/start {invite['code']}",
                "chat": {"id": 990001, "type": "private"},
                "from": {"id": 990001, "first_name": "Synthetic child"},
                "date": int(NOW.timestamp()),
            },
            "synthetic_bot",
            NOW,
        )
        await enrollment.confirm("owner", invite["id"], NOW)
    # The wizard constructs an otherwise fresh target from these current profiles.
    target["members"] = engine.snapshot()["members"]
    mapping = deepcopy(review.private_data()[2])
    for binding in mapping.values():
        if "member_id" in binding:
            binding["member_revision"] = target["members"][binding["member_id"]]["revision"]
    review = review._source.review(mapping, target["members"], mapping_revision=2)
    policy["source_review_fingerprint"] = review.summary()["fingerprint"]
    before = deepcopy(target)

    candidate = build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)
    rebuilt = await async_reverify_shadow(candidate, target)

    assert target == before
    assert rebuilt == candidate
    state = rebuilt.private_state()
    assert state["members"] == target["members"]
    assert state["settings"]["modules"] == []
    assert state["settings"]["automatic_penalties"] is False
    assert all(alarm["enabled"] is False for alarm in state["alarms"].values())
    assert state["migration_shadow"]["mode"] == "read_only"
    assert "2015-02-03" not in json.dumps(rebuilt.summary())
    assert not rebuilt.summary()["activation_available"]
    assert state["telegram"] == {} and state["enrollments"] == {}
    if linked:
        assert state["members"]["child"]["telegram_id"] == 990001

    async def never_save(_state):
        pytest.fail("Read-only copy must not persist Telegram work")

    shadow_engine = Engine(state, never_save)
    assert shadow_engine.shadow_mode
    with pytest.raises(DomainError, match="migration_shadow_read_only"):
        await Enrollment(shadow_engine).issue("owner", "member", NOW, "child")
    assert shadow_engine.snapshot() == state


def test_unknown_profile_fields_still_fail_closed():
    review, target, policy = inputs()
    target["members"]["owner"]["unknown_profile_field"] = "not a supported profile"
    before = deepcopy(target)
    with pytest.raises(ShadowError, match="shadow_target_invalid"):
        build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)
    assert target == before


@pytest.mark.parametrize("value", [None, 990001])
def test_existing_optional_telegram_identity_is_preserved(value):
    review, target, policy = inputs()
    target["members"]["child"]["telegram_id"] = value
    review = review._source.review(review.private_data()[2], target["members"], mapping_revision=2)
    policy["source_review_fingerprint"] = review.summary()["fingerprint"]
    candidate = build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)
    assert candidate.private_state()["members"]["child"]["telegram_id"] == value


@pytest.mark.parametrize("value", [True, "990001", 990001.0, [], {}])
def test_invalid_telegram_identity_fails_closed(value):
    review, target, policy = inputs()
    target["members"]["child"]["telegram_id"] = value
    with pytest.raises(ShadowError, match="shadow_target_invalid"):
        build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)


def test_duplicate_telegram_identity_fails_closed():
    review, target, policy = inputs()
    for member in target["members"].values():
        member["telegram_id"] = 990001
    with pytest.raises(ShadowError, match="shadow_target_invalid"):
        build_shadow_candidate(review, target, reviewer_policy=policy, prepared_at=NOW)
