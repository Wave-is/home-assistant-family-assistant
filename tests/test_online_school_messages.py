"""Actual router/privacy boundaries with synthetic school facts, never network I/O."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.assistant.plans import projection
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.online_school import apply_snapshot
from custom_components.family_assistant.online_school.messages import SchoolReply, reply_current
from custom_components.family_assistant.telegram.router import route


@pytest.fixture
async def connected_school(engine, store, now):
    state = engine.snapshot()
    state["settings"]["modules"].append("school")
    selected = Engine(state, store.save)
    for member, student in (("child", "101"), ("sibling", "202")):
        source = await selected.execute(
            "owner",
            "school.online_source_save",
            {
                "member": member,
                "member_revision": 1,
                "provider": "respublika",
                "student_id": student,
                "generation": member,
                "label": member + " school",
                "timezone": "UTC",
            },
            "school-" + member,
            now,
        )
        snapshot = {
            "student_id": student,
            "student_name": "Private " + member,
            "timezone": "UTC",
            "source_url": "https://school.example/daybook/" + student,
            "coverage_start": "2026-09-06",
            "coverage_end": "2026-09-12",
            "lessons": [
                {
                    "id": member + "-lesson",
                    "date": "2026-09-07",
                    "start": "08:00",
                    "end": "08:45",
                    "subject": "Science",
                    "room": "A",
                    "teacher": "Teacher",
                    "topic": "Water",
                    "homework": member + " private assignment",
                    "estimated_minutes": 20,
                    "cancelled": False,
                    "replacement": False,
                    "links": ["https://resources.example/worksheet"],
                    "attachments": [],
                }
            ],
            "grades": [
                {
                    "id": member + "-mark",
                    "date": None,
                    "period": "Term",
                    "subject": "Science",
                    "value": "Excellent",
                    "comment": member + " private mark",
                    "kind": "Report",
                }
            ],
            "absences": [],
        }
        await selected.system_update(
            "school-snapshot",
            now,
            lambda ctx, source=source, snapshot=snapshot: apply_snapshot(
                ctx.state,
                source["id"],
                source["generation"],
                1,
                snapshot,
                now,
            ),
        )
    return selected


async def test_child_gets_exact_homework_without_model(connected_school, now):
    async def forbidden_model(*args, **kwargs):
        pytest.fail("School content must not invoke a model")

    result = await route(
        connected_school, "child", "/homework", "query", now, private=True, fallback=forbidden_model
    )
    assert isinstance(result, SchoolReply)
    assert "child private assignment" in result
    assert "20 min" in result and "2026-09-07" in result
    assert "sibling private" not in result
    assert reply_current(
        connected_school.snapshot(), {"actor": "child", "school_context": result.school_scope}
    )


async def test_private_reply_survives_real_outbox_deepcopy(connected_school, now):
    result = await route(connected_school, "child", "/homework", "read", now, private=True)
    copied = deepcopy(result)
    assert copied.school_scope == result.school_scope and str(copied) == str(result)
    await connected_school.system_update(
        "reply",
        now,
        lambda ctx: ctx.notify(
            "child",
            "telegram_reply",
            {
                "text": result,
                "actor": "child",
                "private_context": True,
                "school_context": result.school_scope,
            },
        ),
    )
    saved = next(iter(connected_school.snapshot()["outbox"].values()))
    assert saved["data"]["text"] == result


async def test_parent_must_choose_when_two_children(connected_school, now):
    result = await route(connected_school, "owner", "/homework", "query", now, private=True)
    assert "Choose a child" in result and "private assignment" not in result


async def test_explicit_student_is_selected(connected_school, now):
    result = await route(
        connected_school, "owner", "/homework Sibling tomorrow", "query", now, private=True
    )
    assert "sibling private assignment" in result and "child private assignment" not in result


async def test_child_cannot_query_sibling(connected_school, now):
    result = await route(connected_school, "child", "/grades Sibling", "query", now, private=True)
    assert "private mark" not in result and "Excellent" not in result


@pytest.mark.parametrize(
    "command", ["/school Child", "/homework Child", "/grades Sibling", "что по дз у Child?"]
)
async def test_group_query_never_discloses_school_facts(connected_school, now, command):
    result = await route(connected_school, "owner", command, "query", now, private=False)
    assert (
        "private chat" in result
        and "school.example" not in result
        and "private assignment" not in result
    )
    assert not isinstance(result, SchoolReply)


@pytest.mark.parametrize(
    "content",
    ["/tasks school", "/shopping school", "добавь задачу пойти в школу", "buy homework notebook"],
)
def test_school_words_do_not_hijack_other_commands(connected_school, now, content):
    from custom_components.family_assistant.online_school.messages import query

    assert query(connected_school, "owner", content, now, private=True, language="en") is None


@pytest.mark.parametrize(
    "mutation", ["disabled", "child_epoch", "generation", "snapshot", "role", "module"]
)
async def test_queued_school_reply_is_revoked_with_source(connected_school, now, mutation):
    result = await route(connected_school, "child", "/homework", "query", now, private=True)
    state = connected_school.snapshot()
    source = state["school"]["online"]["sources"][result.school_scope[0]["id"]]
    if mutation == "disabled":
        source["enabled"] = False
    elif mutation == "child_epoch":
        state["members"]["child"]["revision"] += 1
    elif mutation == "generation":
        source["generation"] = "new-generation"
    elif mutation == "snapshot":
        source["snapshot_hash"] = "changed"
    elif mutation == "role":
        state["members"]["child"]["role"] = "guest"
    else:
        state["settings"]["modules"].remove("school")
    assert not reply_current(state, {"actor": "child", "school_context": result.school_scope})


async def test_marks_are_literal_not_converted_to_zero(connected_school, now):
    result = await route(connected_school, "child", "/grades", "query", now, private=True)
    assert "Excellent" in result and "child private mark" in result


@pytest.mark.parametrize(
    "content", ["покажи оценки Child", "show grades Child", "покажи оцінки Child"]
)
async def test_natural_marks_are_deterministic(connected_school, now, content):
    result = await route(connected_school, "owner", content, "marks", now, private=True)
    assert isinstance(result, SchoolReply) and "child private mark" in result


def test_llm_projection_never_contains_imported_school(connected_school, now):
    import json

    value = json.dumps(projection(connected_school.view("owner", now=now)))
    assert "private assignment" not in value and "private mark" not in value
    assert "school.example" not in value and "online" not in value


async def test_stale_data_is_labelled_without_erasing_it(connected_school, store, now):
    state = deepcopy(connected_school.snapshot())
    for source in state["school"]["online"]["sources"].values():
        source["status"] = "online_school_auth_failed"
    selected = Engine(state, store.save)
    result = await route(selected, "child", "/homework", "query", now, private=True)
    assert "Saved data" in result and "child private assignment" in result
