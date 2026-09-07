"""Explicit school backpack preparation tests using synthetic state only."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain import routines, school, school_preparation
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

BAD_REVISIONS = (None, True, 1.0, "1", 0, 2**53)


def enabled_state(engine):
    state = engine.snapshot()
    state["settings"]["modules"] += ["school", "routines"]
    return state


def context(state, actor_id, now, operation="school-preparation-test"):
    return Context(state, state["members"][actor_id], now, operation)


def create_template(state, now, **changes):
    return routines.handle(
        context(state, "parent", now, "routine-template"),
        "save",
        {
            "title": "Pack school backpack",
            "description": "Reviewed school preparation",
            "assignees": ["child"],
            "steps": [
                {"title": "Pack books", "confirmation": "manual"},
                {
                    "title": "Parent check",
                    "confirmation": "manual",
                    "assignee": "parent",
                },
            ],
            **changes,
        },
    )


def create_timetable(state, now, template, **changes):
    return school.handle(
        context(state, "parent", now, "timetable"),
        "timetable_save",
        {
            "member": "child",
            "member_revision": 1,
            "title": "School week",
            "valid_from": "2026-09-01",
            "valid_until": "2026-12-31",
            "lessons": [
                {
                    "weekday": 0,
                    "start": "08:30",
                    "end": "09:15",
                    "subject": "Mathematics",
                    "room": "12",
                    "materials": ["Workbook", "Pencil"],
                }
            ],
            "backpack_routine": {
                "id": template["id"],
                "revision": template["revision"],
            },
            "exceptions": [],
            **changes,
        },
    )


def start_payload(timetable, template, **changes):
    return {
        "timetable_id": timetable["id"],
        "timetable_revision": timetable["revision"],
        "member": "child",
        "member_revision": 1,
        "date": "2026-09-07",
        "routine_id": template["id"],
        "routine_revision": template["revision"],
        **changes,
    }


def setup(state, now, **timetable_changes):
    template = create_template(state, now)
    timetable = create_timetable(state, now, template, **timetable_changes)
    return template, timetable


def rejected_without_mutation(state, call, code="invalid_field", field=None):
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code
    if field is not None:
        assert caught.value.field == field
    assert state == before


def test_child_explicit_start_is_atomic_minimal_and_never_returns_nonce(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    assert "preparations" not in state["school"]
    unchanged = {
        key: deepcopy(state[key]) for key in ("tasks", "alarms", "alarm_runs", "alarm_outputs")
    }

    receipt = school_preparation.handle(
        context(state, "child", now, "start-backpack"),
        "backpack_start",
        start_payload(timetable, template),
    )

    assert receipt == {
        "id": "SP000001",
        "revision": 1,
        "status": "started",
        "run_id": "J000001",
    }
    assert "nonce" not in repr(receipt)
    marker = state["school"]["preparations"][receipt["id"]]
    assert marker == {
        "id": "SP000001",
        "revision": 1,
        "status": "started",
        "timetable_id": timetable["id"],
        "timetable_revision": timetable["revision"],
        "member": "child",
        "member_revision": 1,
        "date": "2026-09-07",
        "routine_id": template["id"],
        "routine_revision": template["revision"],
        "run_id": "J000001",
        "created_by": "child",
        "created_at": now.isoformat(),
    }
    run = state["routine_runs"][receipt["run_id"]]
    assert run["template_id"] == template["id"] and run["member"] == "child"
    assert run["steps"][0]["nonce"]
    assert all(key not in repr(marker) for key in ("Mathematics", "Workbook", "nonce"))
    for key, value in unchanged.items():
        assert state[key] == value


def test_current_parent_can_start_for_child_but_adult_guest_and_sibling_cannot(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    payload = start_payload(timetable, template)
    for actor in ("adult", "guest", "sibling"):
        rejected_without_mutation(
            state,
            lambda actor=actor: school_preparation.handle(
                context(state, actor, now), "backpack_start", payload
            ),
            "forbidden",
        )

    receipt = school_preparation.handle(context(state, "owner", now), "backpack_start", payload)
    assert receipt["status"] == "started"
    assert state["school"]["preparations"][receipt["id"]]["created_by"] == "owner"


@pytest.mark.parametrize(
    "field",
    ("timetable_revision", "member_revision", "routine_revision"),
)
@pytest.mark.parametrize("bad", BAD_REVISIONS)
def test_every_reviewed_revision_is_strict(engine, now, field, bad):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(
            context(state, "child", now),
            "backpack_start",
            start_payload(timetable, template, **{field: bad}),
        ),
        field=field,
    )


def test_stale_timetable_member_and_routine_epochs_conflict_without_run(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    base = start_payload(timetable, template)
    for mutate, changes in (
        (
            lambda: state["school"]["timetables"][timetable["id"]].update(revision=2),
            {},
        ),
        (lambda: state["members"]["child"].update(revision=2), {}),
        (lambda: state["routines"][template["id"]].update(revision=2), {}),
    ):
        copy = deepcopy(state)
        mutate()
        before = deepcopy(state)
        with pytest.raises(DomainError, match="conflict"):
            school_preparation.handle(
                context(state, "child", now),
                "backpack_start",
                {**base, **changes},
            )
        assert state == before
        state.clear()
        state.update(copy)


@pytest.mark.parametrize("module", ("school", "routines"))
def test_both_modules_are_required_without_lazy_marker(engine, now, module):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    state["settings"]["modules"].remove(module)
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(
            context(state, "child", now),
            "backpack_start",
            start_payload(timetable, template),
        ),
        "module_disabled",
    )
    assert "preparations" not in state["school"]


@pytest.mark.parametrize(
    ("date", "exceptions", "code"),
    [
        ("2026-09-06", [], "invalid_transition"),  # Today has no Sunday lesson.
        ("2026-09-07", ["2026-09-07"], "invalid_transition"),
        ("2026-09-08", [], "invalid_field"),  # Beyond tomorrow.
        ("2026-09-07T00:00:00", [], "invalid_field"),
    ],
)
def test_date_must_be_today_or_tomorrow_with_actual_nonexception_lesson(
    engine, now, date, exceptions, code
):
    state = enabled_state(engine)
    template, timetable = setup(state, now, exceptions=exceptions)
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(
            context(state, "child", now),
            "backpack_start",
            start_payload(timetable, template, date=date),
        ),
        code,
    )


def test_household_local_day_controls_today_and_tomorrow(engine):
    state = enabled_state(engine)
    state["settings"]["timezone"] = "Europe/Kyiv"
    now = datetime(2026, 9, 6, 21, 30, tzinfo=UTC)  # Monday locally.
    template, timetable = setup(state, now)
    receipt = school_preparation.handle(
        context(state, "child", now),
        "backpack_start",
        start_payload(timetable, template),
    )
    assert receipt["status"] == "started"


def test_duplicate_date_and_unrelated_active_routine_are_not_adopted(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    payload = start_payload(timetable, template)
    school_preparation.handle(context(state, "child", now, "first"), "backpack_start", payload)
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(
            context(state, "child", now, "duplicate"), "backpack_start", payload
        ),
        "invalid_transition",
    )

    other_state = enabled_state(engine)
    other_template, other_timetable = setup(other_state, now)
    routines.handle(
        context(other_state, "child", now, "manual-start"),
        "start",
        {
            "id": other_template["id"],
            "revision": other_template["revision"],
            "member": "child",
        },
    )
    rejected_without_mutation(
        other_state,
        lambda: school_preparation.handle(
            context(other_state, "parent", now),
            "backpack_start",
            start_payload(other_timetable, other_template),
        ),
        "invalid_transition",
    )
    assert "preparations" not in other_state["school"]


@pytest.mark.parametrize("change", ("disabled", "creator", "step_assignee"))
def test_unusable_pinned_routine_fails_before_mutation(engine, now, change):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    if change == "disabled":
        state["routines"][template["id"]]["enabled"] = False
    elif change == "creator":
        state["members"]["parent"]["role"] = "adult"
    else:
        state["members"]["parent"]["role"] = "guest"
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(
            context(state, "child", now),
            "backpack_start",
            start_payload(timetable, template),
        ),
        "invalid_transition",
    )


def test_malformed_preparation_bucket_blocks_start_before_routine_effects(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    state["school"]["preparations"] = []
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(
            context(state, "child", now),
            "backpack_start",
            start_payload(timetable, template),
        ),
    )
    assert state["routine_runs"] == {}


def test_view_is_pure_minimal_parent_and_current_child_only(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    receipt = school_preparation.handle(
        context(state, "child", now),
        "backpack_start",
        start_payload(timetable, template),
    )
    before = deepcopy(state)
    child_view = school_preparation.view(state, state["members"]["child"])
    assert child_view == {
        "preparations": [
            {
                "id": receipt["id"],
                "revision": 1,
                "status": "started",
                "timetable_id": timetable["id"],
                "member": "child",
                "date": "2026-09-07",
                "run_id": receipt["run_id"],
                "run_status": "active",
            }
        ]
    }
    assert school_preparation.view(state, state["members"]["sibling"])["preparations"] == []
    assert school_preparation.view(state, state["members"]["adult"])["preparations"] == []
    assert school_preparation.view(state, state["members"]["guest"])["preparations"] == []
    assert school_preparation.view(state, state["members"]["parent"]) == child_view
    assert state == before

    state["members"]["child"]["revision"] = 2
    assert school_preparation.view(state, state["members"]["child"])["preparations"] == []
    assert len(school_preparation.view(state, state["members"]["parent"])["preparations"]) == 1


def test_view_history_remains_when_routines_module_is_disabled(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    school_preparation.handle(
        context(state, "child", now),
        "backpack_start",
        start_payload(timetable, template),
    )
    state["settings"]["modules"].remove("routines")
    assert len(school_preparation.view(state, state["members"]["child"])["preparations"]) == 1


def test_replay_is_date_stable_but_rechecks_modules_epochs_sources_and_result(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    payload = start_payload(timetable, template)
    receipt = school_preparation.handle(context(state, "child", now), "backpack_start", payload)
    future = datetime(2026, 9, 20, 8, tzinfo=UTC)
    before = deepcopy(state)
    school_preparation.authorize_replay(
        context(state, "child", future), "backpack_start", payload, receipt
    )
    assert state == before

    cases = (
        lambda value: value["settings"]["modules"].remove("routines"),
        lambda value: value["members"]["child"].update(revision=2),
        lambda value: value["school"]["timetables"][timetable["id"]].update(revision=2),
        lambda value: value["routines"][template["id"]].update(revision=2),
        lambda value: value["routine_runs"][receipt["run_id"]].update(
            cancellation_cause="authorization_removed"
        ),
    )
    for mutate in cases:
        changed = deepcopy(state)
        mutate(changed)
        with pytest.raises(DomainError):
            school_preparation.authorize_replay(
                context(changed, "child", future),
                "backpack_start",
                payload,
                receipt,
            )

    changed_result = {**receipt, "run_id": "J999999"}
    with pytest.raises(DomainError, match="forbidden"):
        school_preparation.authorize_replay(
            context(state, "child", future),
            "backpack_start",
            payload,
            changed_result,
        )

    # Current authority is checked before a malformed historical payload can
    # reveal field validation details to a downgraded actor.
    downgraded = deepcopy(state)
    downgraded["members"]["child"]["role"] = "adult"
    with pytest.raises(DomainError, match="forbidden"):
        school_preparation.authorize_replay(
            context(downgraded, "child", future),
            "backpack_start",
            {},
            receipt,
        )


def test_unknown_fields_actions_and_marker_limit_are_atomic(engine, now):
    state = enabled_state(engine)
    template, timetable = setup(state, now)
    payload = start_payload(timetable, template)
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(
            context(state, "child", now),
            "backpack_start",
            {**payload, "observations": {}},
        ),
    )
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(context(state, "child", now), "tick", {}),
        "unknown_action",
    )
    state["school"]["preparations"] = {
        f"SP{index:06}": {"id": f"SP{index:06}"}
        for index in range(school_preparation.MAX_PREPARATIONS)
    }
    rejected_without_mutation(
        state,
        lambda: school_preparation.handle(context(state, "child", now), "backpack_start", payload),
        "invalid_transition",
    )
