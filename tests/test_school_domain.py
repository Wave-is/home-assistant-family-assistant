"""School timetable domain tests using only synthetic household state."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain import school
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

BAD_REVISIONS = (None, True, 1.0, "1", 0, 2**53)


def enabled_state(engine):
    state = engine.snapshot()
    state["settings"]["modules"].append("school")
    return state


def context(state, actor_id, now, operation="school-test"):
    return Context(state, state["members"][actor_id], now, operation)


def lesson(
    weekday=0,
    start="08:30",
    end="09:15",
    subject="Mathematics",
    room="12",
    materials=None,
):
    return {
        "weekday": weekday,
        "start": start,
        "end": end,
        "subject": subject,
        "room": room,
        "materials": ["Workbook", "Pencil"] if materials is None else materials,
    }


def payload(**changes):
    return {
        "member": "child",
        "member_revision": 1,
        "title": "Autumn timetable",
        "valid_from": "2026-09-07",
        "valid_until": "2026-12-18",
        "lessons": [lesson()],
        "backpack_routine": None,
        "exceptions": ["2026-10-12"],
        **changes,
    }


def save(state, now, *, actor="parent", operation="save", **changes):
    return school.handle(
        context(state, actor, now, operation), "timetable_save", payload(**changes)
    )


def assert_rejected_without_mutation(state, call, code="invalid_field", field=None):
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code
    if field is not None:
        assert caught.value.field == field
    assert state == before


def add_routine(state, **changes):
    if "routines" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("routines")
    state["routines"]["U000001"] = {
        "id": "U000001",
        "revision": 1,
        "title": "Pack backpack",
        "creator": "parent",
        "enabled": True,
        "assignees": ["child"],
        "steps": [{"title": "Books"}, {"title": "Lunch", "assignee": "parent"}],
        **changes,
    }
    return {"id": "U000001", "revision": 1}


def test_create_is_lazy_parent_only_opaque_and_has_no_effects(engine, now):
    state = enabled_state(engine)
    assert state["school"] == {}
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(context(state, "child", now), "timetable_save", payload()),
        "forbidden",
    )
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_save",
            {**payload(), "revision": 1},
        ),
    )

    outbox = deepcopy(state["outbox"])
    runs = deepcopy(state["routine_runs"])
    receipt = save(state, now)
    assert receipt == {"id": "ST000001", "revision": 1, "status": "active"}
    record = state["school"]["timetables"][receipt["id"]]
    assert record["member_revision"] == 1
    assert record["created_by"] == "parent"
    assert record["history"] == [{"actor": "parent", "at": now.isoformat(), "action": "created"}]
    assert not ({"title", "lessons", "materials", "room"} & receipt.keys())
    assert state["outbox"] == outbox and state["routine_runs"] == runs


def test_save_requires_current_child_membership_epoch_and_immutable_member(engine, now):
    state = enabled_state(engine)
    for bad in BAD_REVISIONS:
        assert_rejected_without_mutation(
            state,
            lambda bad=bad: save(state, now, member_revision=bad),
            field="member_revision",
        )
    state["members"]["child"]["revision"] = 2
    assert_rejected_without_mutation(state, lambda: save(state, now), "conflict")
    receipt = save(state, now, member_revision=2)
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_save",
            {
                **payload(
                    member="sibling",
                    member_revision=state["members"]["sibling"]["revision"],
                    title="Moved",
                ),
                "id": receipt["id"],
                "revision": receipt["revision"],
            },
        ),
        field="member",
    )
    state["members"]["child"]["role"] = "adult"
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_save",
            {
                **payload(member_revision=2, title="No longer child"),
                "id": receipt["id"],
                "revision": receipt["revision"],
            },
        ),
        "unknown_member",
    )


def test_edit_is_full_replacement_and_omitted_exceptions_clear(engine, now):
    state = enabled_state(engine)
    created = save(state, now)
    replacement = payload(
        title="Winter timetable",
        valid_until=None,
        lessons=[lesson(2, "10:00", "10:45", "History", "")],
    )
    replacement.pop("exceptions")
    edited = school.handle(
        context(state, "owner", now, "replace"),
        "timetable_save",
        {**replacement, "id": created["id"], "revision": created["revision"]},
    )
    assert edited == {"id": created["id"], "revision": 2, "status": "active"}
    record = state["school"]["timetables"][created["id"]]
    assert record["title"] == "Winter timetable"
    assert record["valid_until"] is None and record["exceptions"] == []
    assert record["lessons"] == [replacement["lessons"][0]]
    assert [event["action"] for event in record["history"]] == ["created", "updated"]

    partial = {"id": created["id"], "revision": edited["revision"], "title": "Partial"}
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(context(state, "parent", now), "timetable_save", partial),
    )


@pytest.mark.parametrize("bad", BAD_REVISIONS)
def test_existing_record_revision_is_strict_for_save_and_archive(engine, now, bad):
    state = enabled_state(engine)
    created = save(state, now)
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_save",
            {**payload(title="Edited"), "id": created["id"], "revision": bad},
        ),
    )
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_archive",
            {"id": created["id"], "revision": bad, "reason": "Superseded"},
        ),
    )


def test_stale_revision_conflicts_and_failed_history_validation_is_atomic(engine, now):
    state = enabled_state(engine)
    created = save(state, now)
    edited = school.handle(
        context(state, "parent", now),
        "timetable_save",
        {**payload(title="Current"), "id": created["id"], "revision": created["revision"]},
    )
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_archive",
            {"id": created["id"], "revision": created["revision"], "reason": "Stale"},
        ),
        "conflict",
    )
    state["school"]["timetables"][created["id"]]["history"] = "malformed"
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_save",
            {**payload(title="No mutation"), "id": created["id"], "revision": edited["revision"]},
        ),
    )


def test_lesson_shape_order_overlap_and_material_budgets(engine, now):
    state = enabled_state(engine)
    invalid = (
        [],
        [lesson()] * 71,
        [lesson(weekday=True)],
        [lesson(start="8:30")],
        [lesson(start="09:00", end="09:00")],
        [lesson(subject="")],
        [lesson(room="x" * 81)],
        [lesson(materials=[str(index) for index in range(13)])],
        [lesson(materials=["Book", " book "])],
        [lesson(), lesson(start="09:00", end="09:30", subject="Overlap")],
        [{**lesson(), "unexpected": True}],
    )
    for index, lessons in enumerate(invalid):
        assert_rejected_without_mutation(
            state,
            lambda lessons=lessons, index=index: save(
                state, now, operation=f"bad-lessons:{index}", lessons=lessons
            ),
        )

    too_many_materials = [
        lesson(
            weekday=index // 10,
            start=f"{index % 10:02}:00",
            end=f"{index % 10:02}:30",
            subject=str(index),
            materials=[f"M{index}-{item}" for item in range(12)],
        )
        for index in range(17)
    ]
    assert_rejected_without_mutation(
        state, lambda: save(state, now, lessons=too_many_materials), field="materials"
    )
    accepted = save(
        state,
        now,
        lessons=[
            lesson(start="09:15", end="10:00", subject="Second"),
            lesson(start="08:30", end="09:15", subject="First"),
        ],
    )
    stored = state["school"]["timetables"][accepted["id"]]
    assert [item["subject"] for item in stored["lessons"]] == ["First", "Second"]


def test_dates_and_exception_replacement_are_strict(engine, now):
    state = enabled_state(engine)
    invalid = (
        {"valid_from": "2026-9-7"},
        {"valid_from": "2026-09-07T00:00:00"},
        {"valid_until": "2026-09-06"},
        {"exceptions": ["2026-09-06"]},
        {"exceptions": ["2026-12-19"]},
        {"exceptions": ["2026-10-12", "2026-10-12"]},
        {"exceptions": ["2026-10-12"] * 367},
    )
    for index, changes in enumerate(invalid):
        assert_rejected_without_mutation(
            state,
            lambda changes=changes, index=index: save(
                state, now, operation=f"bad-date:{index}", **changes
            ),
        )


def test_one_active_per_child_archive_is_explicit_and_historical_parent_allowed(engine, now):
    state = enabled_state(engine)
    first = save(state, now)
    assert_rejected_without_mutation(state, lambda: save(state, now), "conflict", "member")
    state["members"]["child"].update(active=False, role="adult", revision=2)
    archived = school.handle(
        context(state, "owner", now),
        "timetable_archive",
        {"id": first["id"], "revision": first["revision"], "reason": "School changed"},
    )
    assert archived == {"id": first["id"], "revision": 2, "status": "archived"}
    record = state["school"]["timetables"][first["id"]]
    assert record["history"][-1]["reason"] == "School changed"
    for action, value in (
        (
            "timetable_save",
            {**payload(), "id": first["id"], "revision": archived["revision"]},
        ),
        (
            "timetable_archive",
            {"id": first["id"], "revision": archived["revision"], "reason": "Again"},
        ),
    ):
        assert_rejected_without_mutation(
            state,
            lambda action=action, value=value: school.handle(
                context(state, "owner", now), action, value
            ),
            "invalid_transition",
        )


def test_current_actor_role_and_module_are_rechecked(engine, now):
    state = enabled_state(engine)
    state["members"]["parent"]["active"] = False
    forged = Context(state, {"id": "parent", "role": "owner"}, now, "forged")
    assert_rejected_without_mutation(
        state, lambda: school.handle(forged, "timetable_save", payload()), "forbidden"
    )
    state["members"]["parent"]["active"] = True
    state["settings"]["modules"].remove("school")
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(context(state, "parent", now), "timetable_save", payload()),
        "module_disabled",
    )
    assert school.view(state, state["members"]["parent"], now) == {
        "timetables": [],
        "upcoming": [],
    }


def test_backpack_link_is_pinned_current_and_never_starts_routine(engine, now):
    state = enabled_state(engine)
    link = add_routine(state)
    runs = deepcopy(state["routine_runs"])
    created = save(state, now, backpack_routine=link)
    assert state["routine_runs"] == runs
    parent_view = school.view(state, state["members"]["parent"], now)
    assert parent_view["timetables"][0]["backpack_routine"] == link
    current = {**link, "title": "Pack backpack"}
    assert parent_view["timetables"][0]["backpack_routine_current"] == current
    child_view = school.view(state, state["members"]["child"], now)
    assert child_view["timetables"][0]["backpack_routine"] == current
    assert state["routine_runs"] == runs

    state["routines"][link["id"]]["revision"] = 2
    parent_view = school.view(state, state["members"]["parent"], now)
    assert parent_view["timetables"][0]["backpack_routine"] == link
    assert parent_view["timetables"][0]["backpack_routine_current"] is None
    assert (
        school.view(state, state["members"]["child"], now)["timetables"][0]["backpack_routine"]
        is None
    )
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_save",
            {
                **payload(backpack_routine=link, title="Stale link"),
                "id": created["id"],
                "revision": created["revision"],
            },
        ),
        "conflict",
    )


def test_backpack_link_requires_enabled_routines_module_and_malformed_assignee_fails_closed(
    engine, now
):
    state = enabled_state(engine)
    link = add_routine(state)
    created = save(state, now, backpack_routine=link)
    state["settings"]["modules"].remove("routines")
    parent = school.view(state, state["members"]["parent"], now)
    assert parent["timetables"][0]["backpack_routine_current"] is None
    assert (
        school.view(state, state["members"]["child"], now)["timetables"][0]["backpack_routine"]
        is None
    )
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(
            context(state, "parent", now),
            "timetable_save",
            {
                **payload(backpack_routine=link, title="No disabled routine"),
                "id": created["id"],
                "revision": created["revision"],
            },
        ),
        field="backpack_routine",
    )

    state["settings"]["modules"].append("routines")
    state["routines"][link["id"]]["steps"][0]["assignee"] = []
    parent = school.view(state, state["members"]["parent"], now)
    assert parent["timetables"][0]["backpack_routine_current"] is None


@pytest.mark.parametrize(
    "change",
    (
        {"enabled": False},
        {"creator": "adult"},
        {"assignees": ["sibling"]},
        {"steps": [{"title": "Guest step", "assignee": "guest"}]},
    ),
)
def test_backpack_link_requires_current_start_authority(engine, now, change):
    state = enabled_state(engine)
    link = add_routine(state, **change)
    assert_rejected_without_mutation(
        state, lambda: save(state, now, backpack_routine=link), field="backpack_routine"
    )


def test_view_is_pure_private_and_membership_epoch_bound(engine, now):
    state = enabled_state(engine)
    own = save(state, now)
    sibling = save(
        state,
        now,
        operation="sibling",
        member="sibling",
        title="Sibling private timetable",
    )
    school.handle(
        context(state, "parent", now),
        "timetable_archive",
        {"id": sibling["id"], "revision": sibling["revision"], "reason": "Historic"},
    )
    before = deepcopy(state)
    parent = school.view(state, state["members"]["parent"], now)
    assert {item["id"] for item in parent["timetables"]} == {own["id"], sibling["id"]}
    child = school.view(state, state["members"]["child"], now)
    assert [item["id"] for item in child["timetables"]] == [own["id"]]
    assert "history" not in child["timetables"][0]
    assert "created_by" not in child["timetables"][0]
    assert school.view(state, state["members"]["sibling"], now)["timetables"] == []
    assert school.view(state, state["members"]["adult"], now) == {
        "timetables": [],
        "upcoming": [],
    }
    assert school.view(state, state["members"]["guest"], now) == {
        "timetables": [],
        "upcoming": [],
    }
    child["timetables"][0]["lessons"][0]["subject"] = "Local edit"
    assert state == before

    state["members"]["child"]["revision"] = 2
    assert school.view(state, state["members"]["child"], now) == {
        "timetables": [],
        "upcoming": [],
    }


def test_upcoming_uses_household_local_date_exceptions_and_fourteen_days(engine, now):
    state = enabled_state(engine)
    state["settings"]["timezone"] = "Pacific/Kiritimati"
    save(
        state,
        now,
        valid_from="2026-09-07",
        valid_until="2026-09-21",
        exceptions=["2026-09-14"],
        lessons=[lesson(0), lesson(6, "11:00", "11:30", "Music", "Hall", [])],
    )
    # Sunday UTC is already Monday in UTC+14, so the local horizon starts 2026-09-07.
    moment = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    child = school.view(state, state["members"]["child"], moment)
    assert child["upcoming"] == [
        {
            "id": "ST000001:2026-09-07:0",
            "timetable_id": "ST000001",
            "member": "child",
            "date": "2026-09-07",
            "subject": "Mathematics",
            "start": "08:30",
            "end": "09:15",
            "room": "12",
            "materials": ["Workbook", "Pencil"],
            "backpack_routine": None,
        },
        {
            "id": "ST000001:2026-09-13:1",
            "timetable_id": "ST000001",
            "member": "child",
            "date": "2026-09-13",
            "subject": "Music",
            "start": "11:00",
            "end": "11:30",
            "room": "Hall",
            "materials": [],
            "backpack_routine": None,
        },
        # 2026-09-14 is excluded; the horizon ends at 2026-09-20 inclusive.
        {
            "id": "ST000001:2026-09-20:1",
            "timetable_id": "ST000001",
            "member": "child",
            "date": "2026-09-20",
            "subject": "Music",
            "start": "11:00",
            "end": "11:30",
            "room": "Hall",
            "materials": [],
            "backpack_routine": None,
        },
    ]


def test_parent_upcoming_is_globally_sorted_across_children(engine, now):
    state = enabled_state(engine)
    save(state, now, lessons=[lesson(start="10:00", end="10:30", subject="Later")])
    save(
        state,
        now,
        operation="sibling",
        member="sibling",
        title="Sibling",
        lessons=[lesson(start="08:00", end="08:30", subject="Earlier")],
    )
    rows = school.view(state, state["members"]["parent"], datetime(2026, 9, 7, 6, tzinfo=UTC))[
        "upcoming"
    ]
    assert [(row["date"], row["start"], row["member"]) for row in rows[:2]] == [
        ("2026-09-07", "08:00", "sibling"),
        ("2026-09-07", "10:00", "child"),
    ]


def test_upcoming_date_max_is_bounded_and_view_without_now_is_pure(engine, now):
    state = enabled_state(engine)
    state["settings"]["timezone"] = "UTC"
    save(
        state,
        now,
        valid_from="9999-12-31",
        valid_until=None,
        exceptions=[],
        lessons=[lesson(4)],
    )
    before = deepcopy(state)
    assert school.view(state, state["members"]["child"])["upcoming"] == []
    near_end = datetime(9999, 12, 31, 12, tzinfo=UTC)
    rows = school.view(state, state["members"]["child"], near_end)["upcoming"]
    assert [row["date"] for row in rows] == ["9999-12-31"]
    assert state == before


def test_local_date_conversion_overflow_is_a_stable_domain_error(engine, now):
    state = enabled_state(engine)
    state["settings"]["timezone"] = "Pacific/Kiritimati"
    save(
        state,
        now,
        valid_from="9999-12-31",
        valid_until=None,
        exceptions=[],
        lessons=[lesson(4)],
    )
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        school.view(
            state,
            state["members"]["child"],
            datetime(9999, 12, 31, 23, 59, tzinfo=UTC),
        )
    assert (caught.value.code, caught.value.field) == ("invalid_field", "now")
    assert state == before


def test_invalid_bucket_and_unknown_action_are_rejected_without_repair(engine, now):
    state = enabled_state(engine)
    state["school"]["timetables"] = []
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(context(state, "parent", now), "timetable_save", payload()),
    )
    with pytest.raises(DomainError) as caught:
        school.view(state, state["members"]["parent"], now)
    assert caught.value.code == "invalid_field"

    state = enabled_state(engine)
    assert_rejected_without_mutation(
        state,
        lambda: school.handle(context(state, "parent", now), "timetable_delete", {}),
        "unknown_action",
    )
