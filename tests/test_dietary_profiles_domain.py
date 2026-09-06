"""Private dietary profile domain tests with synthetic household data only."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.domain import dietary_profiles
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def enabled_state(engine):
    state = engine.snapshot()
    if "pantry" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("pantry")
    state.setdefault("dietary_profiles", {})
    return state


def context(state, actor_id, now, operation="dietary-test"):
    return Context(state, state["members"][actor_id], now, operation)


def save_payload(member_id="adult", **changes):
    payload = {
        "member_id": member_id,
        "likes": ["Fresh berries"],
        "dislikes": ["Very salty food"],
        "avoid": ["Synthetic canary ingredient"],
        "allergy_note": "MANUAL_ALLERGY_CANARY",
    }
    payload.update(changes)
    return payload


def save(state, actor_id, now, payload=None):
    return dietary_profiles.handle(
        context(state, actor_id, now),
        "dietary_save",
        payload or save_payload(actor_id),
    )


def profile(state, member_id):
    return state["dietary_profiles"][member_id]


def test_adult_profile_is_self_private_until_explicit_current_consent(engine, now):
    state = enabled_state(engine)
    before = deepcopy(state)
    receipt = save(state, "adult", now)
    record = profile(state, "adult")

    assert receipt == {"member_id": "adult", "revision": 1, "status": "active"}
    assert "MANUAL_ALLERGY_CANARY" not in repr(receipt)
    assert record["management"] == "self"
    assert record["share_with_parents"] is False
    assert state["outbox"] == before["outbox"]
    assert (
        dietary_profiles.view(state, state["members"]["adult"])["self"]["allergy_note"]
        == "MANUAL_ALLERGY_CANARY"
    )
    assert dietary_profiles.view(state, state["members"]["parent"])["shared_adults"] == []
    assert "MANUAL_ALLERGY_CANARY" not in repr(
        dietary_profiles.view(state, state["members"]["sibling"])
    )

    granted = dietary_profiles.handle(
        context(state, "adult", now, "grant"),
        "dietary_access_set",
        {
            "member_id": "adult",
            "revision": 1,
            "member_revision": 1,
            "share_with_parents": True,
        },
    )
    assert granted == {"member_id": "adult", "revision": 2, "status": "active"}
    assert profile(state, "adult")["consent_member_revision"] == 1
    [shared] = dietary_profiles.view(state, state["members"]["parent"])["shared_adults"]
    assert shared["allergy_note"] == "MANUAL_ALLERGY_CANARY"
    assert shared["can_edit"] is False and shared["can_share"] is False

    dietary_profiles.handle(
        context(state, "adult", now, "revoke"),
        "dietary_access_set",
        {
            "member_id": "adult",
            "revision": 2,
            "member_revision": 1,
            "share_with_parents": False,
        },
    )
    assert dietary_profiles.view(state, state["members"]["parent"])["shared_adults"] == []
    assert "consent_member_revision" not in profile(state, "adult")


@pytest.mark.parametrize("share", [True, False])
@pytest.mark.parametrize("bad_member_revision", ["missing", None, True, 1.0, "1", 0, 2**53])
def test_grant_and_revoke_require_strict_reviewed_member_revision(
    engine, now, share, bad_member_revision
):
    state = enabled_state(engine)
    save(state, "adult", now)
    record_revision = 1
    if not share:
        dietary_profiles.handle(
            context(state, "adult", now, "initial-grant"),
            "dietary_access_set",
            {
                "member_id": "adult",
                "revision": 1,
                "member_revision": 1,
                "share_with_parents": True,
            },
        )
        record_revision = 2
    payload = {
        "member_id": "adult",
        "revision": record_revision,
        "share_with_parents": share,
    }
    if bad_member_revision != "missing":
        payload["member_revision"] = bad_member_revision
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_field"):
        dietary_profiles.handle(
            context(state, "adult", now, f"invalid-member-revision:{share}"),
            "dietary_access_set",
            payload,
        )
    assert state == before


@pytest.mark.asyncio
async def test_membership_change_before_consent_commit_conflicts_without_store_effect(
    engine, store, now
):
    state = enabled_state(engine)
    runtime = Engine(state, store.save)
    created = await runtime.execute(
        "adult", "pantry.dietary_save", save_payload(), "create-before-race", now
    )
    await runtime.execute(
        "owner",
        "members.save",
        {
            "id": "adult",
            "revision": 1,
            "name": "Changed before consent",
            "role": "adult",
        },
        "change-member-before-consent",
        now,
    )
    before, writes = runtime.snapshot(), store.calls
    with pytest.raises(DomainError, match="conflict"):
        await runtime.execute(
            "adult",
            "pantry.dietary_access_set",
            {
                "member_id": "adult",
                "revision": created["revision"],
                "member_revision": 1,
                "share_with_parents": True,
            },
            "stale-consent-review",
            now,
        )
    assert runtime.snapshot() == before
    assert store.calls == writes
    assert store.value == before


def test_parent_manages_only_parent_child_origin_and_child_sees_own_read_only(engine, now):
    state = enabled_state(engine)
    receipt = save(state, "parent", now, save_payload("child"))
    assert receipt["member_id"] == "child"
    assert profile(state, "child")["management"] == "parent_child"

    child_view = dietary_profiles.view(state, state["members"]["child"])
    assert child_view["self"]["allergy_note"] == "MANUAL_ALLERGY_CANARY"
    assert child_view["self"]["can_edit"] is False
    managed = next(
        row
        for row in dietary_profiles.view(state, state["members"]["owner"])["managed_children"]
        if row["member_id"] == "child"
    )
    assert managed["member_id"] == "child" and managed["can_edit"] is True
    assert dietary_profiles.view(state, state["members"]["adult"])["managed_children"] == []

    for actor in ("child", "sibling", "adult"):
        with pytest.raises(DomainError, match="forbidden"):
            save(
                state,
                actor,
                now,
                save_payload("child", revision=receipt["revision"], likes=[actor]),
            )


def test_parent_view_includes_safe_missing_and_cleared_child_stubs(engine, now):
    state = enabled_state(engine)
    parent_view = dietary_profiles.view(state, state["members"]["parent"])
    assert parent_view["self"] == {
        "member_id": "parent",
        "status": "missing",
        "can_edit": True,
        "can_share": False,
    }
    assert parent_view["managed_children"] == [
        {
            "member_id": "child",
            "status": "missing",
            "can_edit": True,
            "can_share": False,
        },
        {
            "member_id": "sibling",
            "status": "missing",
            "can_edit": True,
            "can_share": False,
        },
    ]
    created = save(state, "parent", now, save_payload("child"))
    dietary_profiles.handle(
        context(state, "parent", now, "clear-child"),
        "dietary_clear",
        {"member_id": "child", "revision": created["revision"]},
    )
    cleared = dietary_profiles.view(state, state["members"]["parent"])["managed_children"][0]
    assert cleared == {
        "member_id": "child",
        "status": "cleared",
        "revision": 2,
        "can_edit": True,
        "can_share": False,
    }


def test_role_changes_do_not_open_private_content_or_resurrect_adult_consent(engine, now):
    state = enabled_state(engine)
    save(state, "adult", now)
    dietary_profiles.handle(
        context(state, "adult", now, "grant"),
        "dietary_access_set",
        {
            "member_id": "adult",
            "revision": 1,
            "member_revision": 1,
            "share_with_parents": True,
        },
    )
    assert len(dietary_profiles.view(state, state["members"]["parent"])["shared_adults"]) == 1

    member = state["members"]["adult"]
    member.update(role="child", revision=2)
    parent_view = dietary_profiles.view(state, state["members"]["parent"])
    assert parent_view["shared_adults"] == []
    assert all(row["member_id"] != "adult" for row in parent_view["managed_children"])

    member.update(role="adult", revision=3)
    assert dietary_profiles.view(state, state["members"]["parent"])["shared_adults"] == []
    own = dietary_profiles.view(state, member)["self"]
    assert own["share_with_parents"] is False

    renewed = dietary_profiles.handle(
        context(state, "adult", now, "renew"),
        "dietary_access_set",
        {
            "member_id": "adult",
            "revision": 2,
            "member_revision": 3,
            "share_with_parents": True,
        },
    )
    assert renewed["revision"] == 3
    assert profile(state, "adult")["consent_member_revision"] == 3
    assert len(dietary_profiles.view(state, state["members"]["parent"])["shared_adults"]) == 1

    member.update(name="Renamed adult", revision=4)
    assert dietary_profiles.view(state, state["members"]["parent"])["shared_adults"] == []
    scrubbed = save(state, "adult", now, save_payload(revision=3))
    assert scrubbed["revision"] == 4
    assert profile(state, "adult")["share_with_parents"] is False
    assert "consent_member_revision" not in profile(state, "adult")


def test_parent_child_role_round_trip_retains_only_original_parent_content(engine, now):
    state = enabled_state(engine)
    save(state, "parent", now, save_payload("child"))
    member = state["members"]["child"]
    member.update(role="adult", revision=2)
    assert dietary_profiles.view(state, state["members"]["parent"])["managed_children"] == [
        {
            "member_id": "sibling",
            "status": "missing",
            "can_edit": True,
            "can_share": False,
        }
    ]
    assert dietary_profiles.view(state, member)["self"]["management"] == "parent_child"

    member.update(role="child", revision=3)
    rows = dietary_profiles.view(state, state["members"]["parent"])["managed_children"]
    child = next(row for row in rows if row["member_id"] == "child")
    assert child["allergy_note"] == "MANUAL_ALLERGY_CANARY"
    assert child["management"] == "parent_child"


def test_promoted_child_claims_profile_and_future_demotion_does_not_expose_it(engine, now):
    state = enabled_state(engine)
    save(state, "parent", now, save_payload("child"))
    state["members"]["child"].update(role="adult", revision=2)

    claimed = dietary_profiles.handle(
        context(state, "child", now, "claim"),
        "dietary_save",
        save_payload("child", revision=1, allergy_note="New private adult note"),
    )
    assert claimed["revision"] == 2
    assert profile(state, "child")["management"] == "self"
    assert profile(state, "child")["share_with_parents"] is False
    assert "New private adult note" not in repr(
        dietary_profiles.view(state, state["members"]["parent"])
    )

    state["members"]["child"].update(role="child", revision=3)
    assert "New private adult note" not in repr(
        dietary_profiles.view(state, state["members"]["parent"])
    )
    with pytest.raises(DomainError, match="forbidden"):
        save(
            state,
            "parent",
            now,
            save_payload("child", revision=2, allergy_note="Parent overwrite"),
        )


@pytest.mark.parametrize("bad_revision", [None, True, 1.0, "1", 0, 2**53, 2])
@pytest.mark.parametrize("action", ["dietary_save", "dietary_access_set", "dietary_clear"])
def test_existing_actions_require_strict_current_revision_without_mutation(
    engine, now, action, bad_revision
):
    state = enabled_state(engine)
    save(state, "adult", now)
    before = deepcopy(state)
    if action == "dietary_save":
        payload = save_payload("adult", revision=bad_revision, likes=["Changed"])
    elif action == "dietary_access_set":
        payload = {
            "member_id": "adult",
            "revision": bad_revision,
            "member_revision": 1,
            "share_with_parents": True,
        }
    else:
        payload = {"member_id": "adult", "revision": bad_revision}
    if bad_revision is None:
        payload.pop("revision")
    with pytest.raises(DomainError) as caught:
        dietary_profiles.handle(context(state, "adult", now), action, payload)
    assert caught.value.code in {"invalid_field", "conflict"}
    assert state == before


def test_creation_forbids_revision_and_validates_every_payload_field_atomically(engine, now):
    state = enabled_state(engine)
    invalid = [
        save_payload(revision=1),
        save_payload(likes="berries"),
        save_payload(likes=["x"] * 31),
        save_payload(likes=["x", "X"]),
        save_payload(likes=["same"], avoid=[" SAME "]),
        save_payload(likes=[""]),
        save_payload(avoid=["x" * 81]),
        save_payload(allergy_note="x" * 1001),
        {**save_payload(), "extra": "no"},
    ]
    for index, payload in enumerate(invalid):
        before = deepcopy(state)
        with pytest.raises(DomainError, match="invalid_field"):
            dietary_profiles.handle(
                context(state, "adult", now, f"invalid:{index}"), "dietary_save", payload
            )
        assert state == before

    with pytest.raises(DomainError, match="invalid_field"):
        dietary_profiles.handle(
            context(state, "adult", now),
            "dietary_access_set",
            {
                "member_id": "adult",
                "revision": 1,
                "member_revision": 1,
                "share_with_parents": 1,
            },
        )
    with pytest.raises(DomainError, match="invalid_field"):
        dietary_profiles.handle(context(state, "adult", now), "dietary_save", None)


def test_labels_are_trimmed_but_not_inferred(engine, now):
    state = enabled_state(engine)
    receipt = save(
        state,
        "adult",
        now,
        save_payload(
            likes=["  Peanut  "],
            dislikes=["Very salty"],
            avoid=["Tree nuts"],
            allergy_note="  manual words only  ",
        ),
    )
    assert receipt == {"member_id": "adult", "revision": 1, "status": "active"}
    assert profile(state, "adult")["likes"] == ["Peanut"]
    assert profile(state, "adult")["dislikes"] == ["Very salty"]
    assert profile(state, "adult")["avoid"] == ["Tree nuts"]
    assert profile(state, "adult")["allergy_note"] == "manual words only"
    assert set(profile(state, "adult")) == {
        "member_id",
        "management",
        "share_with_parents",
        "status",
        "likes",
        "dislikes",
        "avoid",
        "allergy_note",
        "revision",
        "updated_at",
    }


def test_clear_tombstone_scrubs_content_and_prevents_aba(engine, now):
    state = enabled_state(engine)
    save(state, "adult", now)
    dietary_profiles.handle(
        context(state, "adult", now, "grant"),
        "dietary_access_set",
        {
            "member_id": "adult",
            "revision": 1,
            "member_revision": 1,
            "share_with_parents": True,
        },
    )
    cleared = dietary_profiles.handle(
        context(state, "adult", now, "clear"),
        "dietary_clear",
        {"member_id": "adult", "revision": 2},
    )
    assert cleared == {"member_id": "adult", "revision": 3, "status": "cleared"}
    assert profile(state, "adult") == {
        "member_id": "adult",
        "management": "self",
        "status": "cleared",
        "revision": 3,
        "updated_at": now.isoformat(),
    }
    assert "MANUAL_ALLERGY_CANARY" not in repr(state)

    with pytest.raises(DomainError, match="conflict"):
        save(state, "adult", now, save_payload(revision=2))
    with pytest.raises(DomainError, match="invalid_transition"):
        dietary_profiles.handle(
            context(state, "adult", now),
            "dietary_access_set",
            {
                "member_id": "adult",
                "revision": 3,
                "member_revision": 1,
                "share_with_parents": True,
            },
        )
    restored = save(
        state,
        "adult",
        now,
        save_payload(revision=3, allergy_note="replacement"),
    )
    assert restored == {"member_id": "adult", "revision": 4, "status": "active"}
    assert profile(state, "adult")["allergy_note"] == "replacement"


@pytest.mark.parametrize("stored_revision", [True, 1.0, "1", 0, 2**53])
def test_malformed_stored_revision_is_never_accepted_or_mutated(engine, now, stored_revision):
    state = enabled_state(engine)
    save(state, "adult", now)
    profile(state, "adult")["revision"] = stored_revision
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_field"):
        save(state, "adult", now, save_payload(revision=1, likes=["Changed"]))
    assert state == before


@pytest.mark.parametrize("action", ["dietary_save", "dietary_access_set", "dietary_clear"])
def test_maximum_revision_cannot_overflow_json_safe_range(engine, now, action):
    state = enabled_state(engine)
    save(state, "adult", now)
    profile(state, "adult")["revision"] = 2**53 - 1
    if action == "dietary_save":
        payload = save_payload(revision=2**53 - 1, likes=["Changed"])
    elif action == "dietary_access_set":
        payload = {
            "member_id": "adult",
            "revision": 2**53 - 1,
            "member_revision": 1,
            "share_with_parents": True,
        }
    else:
        payload = {"member_id": "adult", "revision": 2**53 - 1}
    before = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_field"):
        dietary_profiles.handle(context(state, "adult", now), action, payload)
    assert state == before


@pytest.mark.parametrize("action", ["dietary_save", "dietary_clear"])
@pytest.mark.parametrize("probe_revision", [None, 1, 2])
def test_unauthorized_parent_cannot_probe_private_profile_revision(
    engine, now, action, probe_revision
):
    state = enabled_state(engine)
    save(state, "adult", now)
    payload = (
        save_payload("adult", likes=["Probe"])
        if action == "dietary_save"
        else {"member_id": "adult"}
    )
    if probe_revision is not None:
        payload["revision"] = probe_revision
    before = deepcopy(state)
    with pytest.raises(DomainError, match="forbidden"):
        dietary_profiles.handle(context(state, "parent", now), action, payload)
    assert state == before


def test_view_is_pure_module_scoped_and_guest_inactive_empty(engine, now):
    state = enabled_state(engine)
    save(state, "adult", now)
    before = deepcopy(state)
    assert dietary_profiles.view(state, state["members"]["adult"])["self"]
    assert state == before

    state["settings"]["modules"].remove("pantry")
    assert dietary_profiles.view(state, state["members"]["adult"]) == {
        "self": None,
        "managed_children": [],
        "shared_adults": [],
    }
    state["settings"]["modules"].append("pantry")
    assert dietary_profiles.view(state, state["members"]["guest"])["self"] is None
    state["members"]["adult"]["active"] = False
    assert dietary_profiles.view(state, state["members"]["adult"])["self"] is None


def test_authorize_replay_rechecks_roles_management_and_consent_version(engine, now):
    state = enabled_state(engine)
    child_payload = save_payload("child")
    save(state, "parent", now, child_payload)
    dietary_profiles.authorize_replay(context(state, "parent", now), "dietary_save", child_payload)
    state["members"]["child"].update(role="adult", revision=2)
    with pytest.raises(DomainError, match="forbidden"):
        dietary_profiles.authorize_replay(
            context(state, "parent", now), "dietary_save", child_payload
        )

    adult_payload = save_payload("adult")
    save(state, "adult", now, adult_payload)
    access_payload = {
        "member_id": "adult",
        "revision": 1,
        "member_revision": 1,
        "share_with_parents": True,
    }
    dietary_profiles.handle(context(state, "adult", now), "dietary_access_set", access_payload)
    dietary_profiles.authorize_replay(
        context(state, "adult", now), "dietary_access_set", access_payload
    )
    state["members"]["adult"].update(name="Changed", revision=2)
    with pytest.raises(DomainError, match="conflict"):
        dietary_profiles.authorize_replay(
            context(state, "adult", now), "dietary_access_set", access_payload
        )


def test_unknown_actions_missing_records_and_noop_updates_fail_without_writes(engine, now):
    state = enabled_state(engine)
    before = deepcopy(state)
    with pytest.raises(DomainError, match="unknown_action"):
        dietary_profiles.handle(context(state, "adult", now), "unknown", {})
    with pytest.raises(DomainError, match="not_found"):
        dietary_profiles.handle(
            context(state, "adult", now),
            "dietary_clear",
            {"member_id": "adult", "revision": 1},
        )
    assert state == before

    save(state, "adult", now)
    current = deepcopy(state)
    with pytest.raises(DomainError, match="invalid_transition"):
        save(state, "adult", now, save_payload(revision=1))
    assert state == current
