"""Focused contracts for local private-ballot family polls."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import polls
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError


def context(state, actor_id, now, operation="poll-test"):
    return Context(state, state["members"][actor_id], now, operation)


def enabled_state(engine):
    state = engine.snapshot()
    if "polls" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("polls")
    return state


def create_poll(state, now, *, actor="parent", eligible=None, **changes):
    eligible = ["child", "sibling"] if eligible is None else eligible
    eligible_payload = (
        [
            {"member": member_id, "revision": state["members"][member_id]["revision"]}
            for member_id in eligible
        ]
        if all(isinstance(member_id, str) for member_id in eligible)
        else eligible
    )
    payload = {
        "actor_revision": state["members"][actor]["revision"],
        "question": "Which park should we visit?",
        "options": ["Riverside", "Hilltop"],
        "eligible": eligible_payload,
        "closes_at": (now + timedelta(days=1)).isoformat(),
        "confirm_private_ballot_limits": True,
        **changes,
    }
    return polls.handle(context(state, actor, now), "create", payload)


def vote(state, now, poll_id, actor, option_id, ballot_revision=None, **changes):
    record = state["polls"][poll_id]
    payload = {
        "id": poll_id,
        "definition_revision": record["definition_revision"],
        "voter_revision": state["members"][actor]["revision"],
        "option_id": option_id,
        "ballot_revision": ballot_revision,
        **changes,
    }
    return polls.handle(context(state, actor, now), "vote", payload)


def parent_command(state, now, action, poll_id, *, actor="parent", **changes):
    payload = {
        "id": poll_id,
        "revision": state["polls"][poll_id]["revision"],
        "actor_revision": state["members"][actor]["revision"],
        **changes,
    }
    return polls.handle(context(state, actor, now), action, payload)


def assert_error(code, callback, field=None):
    with pytest.raises(DomainError) as caught:
        callback()
    assert caught.value.code == code
    if field is not None:
        assert caught.value.field == field


def test_create_accepts_one_voter_and_stores_only_bounded_definition(engine, now):
    state = enabled_state(engine)
    receipt = create_poll(state, now, eligible=["child"])

    assert receipt == {"id": "PL000001", "revision": 1, "status": "open"}
    record = state["polls"][receipt["id"]]
    assert record["options"] == [
        {"id": "O1", "label": "Riverside"},
        {"id": "O2", "label": "Hilltop"},
    ]
    assert record["eligible"] == [{"member": "child", "member_revision": 1}]
    assert record["ballot_mode"] == "private_mapping"
    assert receipt["id"] not in state.get("poll_ballots", {})
    assert "history" not in record


@pytest.mark.parametrize(
    ("changes", "code", "field"),
    [
        ({"confirm_private_ballot_limits": False}, "confirmation_required", None),
        ({"options": ["Same", " same "]}, "invalid_field", "options"),
        ({"options": ["Only one"]}, "invalid_field", "options"),
        ({"eligible": []}, "invalid_field", "eligible"),
        (
            {"eligible": [{"member": "guest", "revision": 1}]},
            "unknown_member",
            None,
        ),
        (
            {"eligible": [{"member": "child", "revision": 2}]},
            "conflict",
            "eligible[0].revision",
        ),
        ({"closes_at": "2026-09-06T08:04:59+00:00"}, "invalid_field", "closes_at"),
        ({"closes_at": "2026-10-07T08:00:01+00:00"}, "invalid_field", "closes_at"),
        ({"question": "x" * 241}, "invalid_field", "question"),
    ],
)
def test_create_validation_is_strict_and_does_not_allocate_id(engine, now, changes, code, field):
    state = enabled_state(engine)
    before = deepcopy(state)
    assert_error(code, lambda: create_poll(state, now, **changes), field)
    assert state == before


def test_create_requires_current_parent_epoch_and_exact_payload(engine, now):
    state = enabled_state(engine)
    assert_error("forbidden", lambda: create_poll(state, now, actor="adult", eligible=["child"]))
    state["members"]["parent"]["revision"] = 2
    assert_error(
        "conflict",
        lambda: create_poll(state, now, actor_revision=1),
        "actor_revision",
    )
    state["members"]["parent"]["active"] = False
    assert_error("forbidden", lambda: create_poll(state, now))


def test_vote_changes_use_independent_ballot_revision_not_poll_revision(engine, now):
    state = enabled_state(engine)
    poll_id = create_poll(state, now)["id"]

    first = vote(state, now, poll_id, "child", "O1")
    sibling = vote(state, now, poll_id, "sibling", "O2")
    changed = vote(state, now, poll_id, "child", "O2", first["ballot_revision"])

    assert first == {"id": poll_id, "ballot_revision": 1}
    assert sibling == {"id": poll_id, "ballot_revision": 1}
    assert changed == {"id": poll_id, "ballot_revision": 2}
    assert state["polls"][poll_id]["revision"] == 1
    assert state["poll_ballots"][poll_id]["child"]["option_id"] == "O2"
    assert_error("invalid_transition", lambda: vote(state, now, poll_id, "child", "O2", 2))
    assert_error("forbidden", lambda: vote(state, now, poll_id, "adult", "O1"))
    assert_error("invalid_field", lambda: vote(state, now, poll_id, "child", "O99", 2))


def test_nonvoter_gets_uniform_forbidden_for_guessed_poll_ids_and_states(engine, now):
    state = enabled_state(engine)
    poll_id = create_poll(state, now, eligible=["child"])["id"]

    def attempt(target):
        return polls.handle(
            context(state, "sibling", now),
            "vote",
            {
                "id": target,
                "definition_revision": 1,
                "voter_revision": 1,
                "option_id": "O1",
                "ballot_revision": None,
            },
        )

    before = deepcopy(state)
    assert_error("forbidden", lambda: attempt(poll_id))
    assert_error("forbidden", lambda: attempt("PL999999"))
    parent_command(state, now, "close", poll_id)
    assert_error("forbidden", lambda: attempt(poll_id))
    assert state.get("poll_ballots", {}) == before.get("poll_ballots", {})


@pytest.mark.parametrize("bad", [None, True, 1.0, "1", 0, -1, 2**53])
def test_existing_ballot_revision_is_strict(engine, now, bad):
    state = enabled_state(engine)
    poll_id = create_poll(state, now, eligible=["child"])["id"]
    vote(state, now, poll_id, "child", "O1")
    before = deepcopy(state)
    assert_error("invalid_field", lambda: vote(state, now, poll_id, "child", "O2", bad))
    assert state == before


def test_open_projection_is_private_and_relationship_scoped(engine, now):
    state = enabled_state(engine)
    poll_id = create_poll(state, now, eligible=["child", "parent"])["id"]
    vote(state, now, poll_id, "child", "O1")
    vote(state, now, poll_id, "parent", "O2")
    before = deepcopy(state)

    child = polls.view(state, state["members"]["child"], now)["open"][0]
    assert child["own_ballot"] == {"option_id": "O1", "revision": 1}
    assert child["can_vote"] is True
    assert not ({"eligible", "created_by", "created_at", "results", "cast_count"} & child.keys())
    assert "parent" not in repr(child)

    parent = polls.view(state, state["members"]["parent"], now)["open"][0]
    assert parent["own_ballot"] == {"option_id": "O2", "revision": 1}
    assert parent["eligible_count"] == 2 and parent["can_close"] is True
    assert all(
        set(entry) == {"member", "member_revision", "current"} for entry in parent["eligible"]
    )
    assert "child" not in repr(parent["own_ballot"])

    assert polls.view(state, state["members"]["sibling"], now) == {
        "open": [],
        "closed": [],
        "archived": [],
    }
    assert polls.view(state, state["members"]["adult"], now) == {
        "open": [],
        "closed": [],
        "archived": [],
    }
    assert polls.view(state, state["members"]["guest"], now) == {
        "open": [],
        "closed": [],
        "archived": [],
    }
    assert state == before


def test_explicit_view_clock_and_tick_close_deterministically(engine, now):
    state = enabled_state(engine)
    poll_id = create_poll(state, now, eligible=["child"])["id"]
    vote(state, now, poll_id, "child", "O1")
    deadline = now + timedelta(days=1)

    assert polls.view(state, state["members"]["child"])["open"]
    derived = polls.view(state, state["members"]["child"], deadline)
    assert not derived["open"]
    assert derived["closed"][0]["closed_at"] == deadline.isoformat()
    assert derived["closed"][0]["results"] == [
        {"option_id": "O1", "count": 1},
        {"option_id": "O2", "count": 0},
    ]
    parent_derived = polls.view(state, state["members"]["parent"], deadline)["closed"][0]
    assert parent_derived["can_close"] is False
    assert parent_derived["can_archive"] is False
    assert state["polls"][poll_id]["status"] == "open"

    polls.tick(context(state, "owner", deadline, "poll-clock"))
    assert state["polls"][poll_id]["status"] == "closed"
    assert state["polls"][poll_id]["closed_at"] == deadline.isoformat()
    revision = state["polls"][poll_id]["revision"]
    polls.tick(context(state, "owner", deadline + timedelta(hours=1), "poll-clock-2"))
    assert state["polls"][poll_id]["revision"] == revision


def test_member_epoch_revocation_hides_live_poll_but_preserves_final_count(engine, now):
    state = enabled_state(engine)
    poll_id = create_poll(state, now, eligible=["child"])["id"]
    vote(state, now, poll_id, "child", "O1")
    state["members"]["child"]["revision"] = 2

    assert polls.view(state, state["members"]["child"], now)["open"] == []
    parent_row = polls.view(state, state["members"]["parent"], now)["open"][0]
    assert parent_row["eligible"] == [{"member": "child", "member_revision": 1, "current": False}]
    assert_error(
        "forbidden",
        lambda: vote(
            state,
            now,
            poll_id,
            "child",
            "O2",
            1,
            voter_revision=2,
        ),
    )
    parent_command(state, now, "close", poll_id)
    final = polls.view(state, state["members"]["parent"], now)["closed"][0]
    assert final["results"] == [{"option_id": "O1", "count": 1}, {"option_id": "O2", "count": 0}]


def test_close_archive_compacts_private_mapping_and_owner_purge_is_explicit(engine, now):
    state = enabled_state(engine)
    poll_id = create_poll(state, now)["id"]
    vote(state, now, poll_id, "child", "O1")
    vote(state, now, poll_id, "sibling", "O2")

    closed = parent_command(state, now, "close", poll_id)
    assert closed == {"id": poll_id, "revision": 2, "status": "closed"}
    archived = parent_command(state, now, "archive", poll_id)
    assert archived == {"id": poll_id, "revision": 3, "status": "archived"}
    record = state["polls"][poll_id]
    assert not (
        {"eligible", "definition_revision", "created_by", "creator_revision"} & record.keys()
    )
    assert record["cast_count"] == 2 and record["eligible_count"] == 2
    assert poll_id not in state["poll_ballots"]
    assert polls.view(state, state["members"]["child"], now)["archived"] == []
    assert polls.view(state, state["members"]["parent"], now)["archived"][0]["can_purge"] is False
    assert polls.view(state, state["members"]["owner"], now)["archived"][0]["can_purge"] is True

    assert_error(
        "forbidden",
        lambda: parent_command(state, now, "purge", poll_id, actor="parent", confirm_delete=True),
    )
    assert_error(
        "confirmation_required",
        lambda: parent_command(state, now, "purge", poll_id, actor="owner", confirm_delete=False),
    )
    stale = deepcopy(state)
    assert_error(
        "conflict",
        lambda: polls.handle(
            context(stale, "owner", now),
            "purge",
            {
                "id": poll_id,
                "revision": 2,
                "actor_revision": 1,
                "confirm_delete": True,
            },
        ),
    )
    deleted = parent_command(state, now, "purge", poll_id, actor="owner", confirm_delete=True)
    assert deleted == {"id": poll_id, "status": "deleted"}
    assert poll_id not in state["polls"]


@pytest.mark.parametrize("bad", [None, True, 1.0, "1", 0, -1, 2**53])
def test_poll_lifecycle_revision_has_no_null_or_type_bypass(engine, now, bad):
    state = enabled_state(engine)
    poll_id = create_poll(state, now)["id"]
    before = deepcopy(state)
    assert_error(
        "invalid_field",
        lambda: polls.handle(
            context(state, "parent", now),
            "close",
            {"id": poll_id, "revision": bad, "actor_revision": 1},
        ),
        "revision",
    )
    assert state == before


def test_replay_rechecks_identity_definition_and_compaction_boundaries(engine, now):
    state = enabled_state(engine)
    poll_id = create_poll(state, now, eligible=["child"])["id"]
    create_payload = {
        "actor_revision": 1,
        "question": "Which park should we visit?",
        "options": ["Riverside", "Hilltop"],
        "eligible": [{"member": "child", "revision": 1}],
        "closes_at": (now + timedelta(days=1)).isoformat(),
        "confirm_private_ballot_limits": True,
    }
    polls.authorize_replay(
        context(state, "parent", now),
        "create",
        create_payload,
        {"id": poll_id, "revision": 1, "status": "open"},
    )
    vote_payload = {
        "id": poll_id,
        "definition_revision": 1,
        "voter_revision": 1,
        "option_id": "O1",
        "ballot_revision": None,
    }
    vote_result = vote(state, now, poll_id, "child", "O1")
    polls.authorize_replay(context(state, "child", now), "vote", vote_payload, vote_result)
    assert_error(
        "conflict",
        lambda: polls.authorize_replay(
            context(state, "child", now),
            "vote",
            vote_payload,
            {**vote_result, "id": "PL999999"},
        ),
    )

    parent_command(state, now, "close", poll_id)
    polls.authorize_replay(context(state, "child", now), "vote", vote_payload, vote_result)
    parent_command(state, now, "archive", poll_id)
    assert_error(
        "forbidden",
        lambda: polls.authorize_replay(
            context(state, "child", now), "vote", vote_payload, vote_result
        ),
    )
    state["members"]["parent"]["revision"] = 2
    assert_error(
        "conflict",
        lambda: polls.authorize_replay(
            context(state, "parent", now),
            "create",
            create_payload,
            {"id": poll_id, "revision": 1, "status": "open"},
        ),
    )


def test_actions_have_no_task_points_device_or_notification_effects(engine, now):
    state = enabled_state(engine)
    protected = {
        key: deepcopy(state[key])
        for key in ("tasks", "rewards", "outbox", "alarms", "alarm_outputs", "routines")
    }
    poll_id = create_poll(state, now, eligible=["child"])["id"]
    vote(state, now, poll_id, "child", "O1")
    parent_command(state, now, "close", poll_id)
    parent_command(state, now, "archive", poll_id)
    assert {key: state[key] for key in protected} == protected


def test_module_disable_and_malformed_state_fail_closed_without_writes(engine, now):
    state = engine.snapshot()
    before = deepcopy(state)
    assert_error("module_disabled", lambda: create_poll(state, now))
    assert state == before

    state = enabled_state(engine)
    state["polls"] = []
    before = deepcopy(state)
    assert_error("invalid_field", lambda: create_poll(state, now), "polls")
    assert state == before

    state = enabled_state(engine)
    state["members"]["child"]["revision"] = True
    before = deepcopy(state)
    assert_error("invalid_field", lambda: create_poll(state, now), "eligible[0].revision")
    assert polls.view(state, state["members"]["child"], now) == {
        "open": [],
        "closed": [],
        "archived": [],
    }
    assert state == before


def test_archived_projection_is_bounded_to_newest_one_hundred(engine, now):
    state = enabled_state(engine)
    for index in range(101):
        poll_id = create_poll(
            state,
            now + timedelta(seconds=index),
            eligible=["child"],
            closes_at=(now + timedelta(days=1, seconds=index)).isoformat(),
        )["id"]
        parent_command(state, now + timedelta(seconds=index), "close", poll_id)
        parent_command(state, now + timedelta(seconds=index), "archive", poll_id)

    rows = polls.view(state, state["members"]["owner"], now)["archived"]
    assert len(rows) == 100
    assert rows[0]["id"] == "PL000101"
    assert rows[-1]["id"] == "PL000002"
