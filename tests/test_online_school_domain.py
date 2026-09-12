"""Synthetic schools only: real Engine transactions, replay and private cache."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import online_school as online
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def school_engine(engine, store):
    state = engine.snapshot()
    state["settings"]["modules"] = sorted(set(state["settings"]["modules"]) | {"school", "tasks"})
    return Engine(state, store.save)


def binding(**changes):
    return {
        "member": "child",
        "member_revision": 1,
        "provider": "respublika",
        "student_id": "student-a",
        "generation": "a" * 32,
        "label": "Example school",
        "timezone": "Europe/Kyiv",
        **changes,
    }


def snapshot(**changes):
    return {
        "student_id": "student-a",
        "student_name": "Example Student",
        "timezone": "Europe/Kyiv",
        "source_url": "https://school-a.example/daybook/student-a",
        "coverage_start": "2026-09-06",
        "coverage_end": "2026-09-26",
        "lessons": [
            {
                "id": "lesson-a",
                "date": "2026-09-07",
                "start": "08:00",
                "end": "08:45",
                "subject": "Science",
                "room": "101",
                "teacher": "Example Teacher",
                "topic": "Water",
                "homework": "Read the water chapter.",
                "estimated_minutes": 20,
                "cancelled": False,
                "replacement": False,
                "links": ["https://resources.example/water"],
                "attachments": [
                    {"id": "file-a", "name": "worksheet.pdf", "ext": "pdf", "size": 50}
                ],
            }
        ],
        "grades": [
            {
                "id": "grade-a",
                "date": "2026-09-06",
                "period": "",
                "subject": "Science",
                "value": "Excellent",
                "comment": "Careful work",
                "kind": "Classwork",
            }
        ],
        "absences": [],
        **changes,
    }


async def save(engine, now, *, actor="owner", operation="source-create", **values):
    return await engine.execute(
        actor, "school.online_source_save", binding(**values), operation, now
    )


async def apply(engine, source, now, value=None, **pins):
    return await engine.system_update(
        "online_school_snapshot",
        now,
        lambda ctx: online.apply_snapshot(
            ctx.state,
            source["id"],
            pins.get("generation", source["generation"]),
            pins.get("member_revision", source["member_revision"]),
            value or snapshot(),
            now,
        ),
    )


def stored(engine, source):
    return engine.snapshot()["school"]["online"]["sources"][source["id"]]


def options(revision=1, **sources):
    return {
        "unrelated": {"preserve": True},
        "online_school": {"revision": revision, "sources": sources},
    }


async def reconcile(engine, now, value):
    return await engine.system_update(
        "online_school_options", now, lambda ctx: online.sync_bindings(ctx, value)
    )


def ack_payload(source, *, ack_revision=None, done=True, value=None):
    lesson = (value or snapshot())["lessons"][0]
    return {
        "id": source["id"],
        "revision": source["revision"],
        "member_revision": source["member_revision"],
        "lesson_id": lesson["id"],
        "homework_hash": online.homework_fingerprint(lesson),
        "ack_revision": ack_revision,
        "done": done,
    }


async def acknowledge(engine, source, now, *, actor="child", operation="ack", **values):
    return await engine.execute(
        actor, "school.online_homework_ack", ack_payload(source, **values), operation, now
    )


async def test_source_uses_real_context_id_and_receipt_has_no_cache(school_engine, now):
    source = await save(school_engine, now)
    assert source["id"] == "OS000001" and source["revision"] == 1
    assert source["rules"] == online.RULE_DEFAULTS
    assert "snapshot" not in source and "status" not in source
    assert stored(school_engine, source)["status"] == "pending"


@pytest.mark.parametrize("actor", ["parent", "child", "sibling", "adult", "guest"])
async def test_only_owner_can_bind_or_disable_sources(school_engine, now, actor):
    source = await save(school_engine, now)
    before = school_engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await save(school_engine, now, actor=actor, operation="forbidden-create")
    with pytest.raises(DomainError, match="forbidden"):
        await school_engine.execute(
            actor,
            "school.online_source_disable",
            {"id": source["id"], "revision": 1},
            "forbidden-disable",
            now,
        )
    assert school_engine.snapshot() == before


@pytest.mark.parametrize(
    "values",
    [
        {"member": "parent"},
        {"member_revision": True},
        {"member_revision": 2},
        {"provider": "invented"},
        {"generation": ""},
        {"timezone": "Mars/Example"},
        {"password": "synthetic-never-persist"},
        {"enabled": 1},
        {"rules": {"automatic_penalty": True}},
        {"rules": {"recipients": ["sibling"]}},
        {"rules": {"recipients": ["adult"]}},
        {"rules": {"enabled": 1}},
        {"rules": {"homework_time": "25:00"}},
        {"id": "OS1"},
        {"revision": 1},
    ],
)
async def test_configuration_is_strict_and_failed_write_is_atomic(school_engine, now, values):
    before = school_engine.snapshot()
    with pytest.raises(DomainError):
        await save(school_engine, now, **values)
    assert school_engine.snapshot() == before


async def test_rules_only_allow_private_bound_child_and_current_parents(school_engine, now):
    source = await save(
        school_engine,
        now,
        rules={"enabled": True, "recipients": ["owner", "child", "parent", " owner "]},
    )
    assert source["rules"]["recipients"] == ["child", "owner", "parent"]
    assert not source["rules"]["notify_changes"]
    assert source["rules"]["homework_time"] == "18:00"
    assert school_engine.snapshot()["outbox"] == {}


async def test_two_school_connections_and_children_have_independent_private_caches(
    school_engine, now
):
    first = await save(school_engine, now)
    second = await save(
        school_engine,
        now,
        operation="other-source",
        member="sibling",
        student_id="student-b",
        generation="b" * 32,
        label="Other example school",
    )
    await apply(school_engine, first, now)
    await apply(
        school_engine,
        second,
        now,
        snapshot(
            student_id="student-b",
            student_name="Other Student",
            source_url="https://school-b.example/daybook/student-b",
        ),
    )
    assert len(online.view(school_engine.snapshot(), "parent", now)["sources"]) == 2
    child = online.view(school_engine.snapshot(), "child", now)["sources"]
    sibling = online.view(school_engine.snapshot(), "sibling", now)["sources"]
    assert [row["id"] for row in child] == [first["id"]]
    assert [row["id"] for row in sibling] == [second["id"]]
    assert "Other Student" not in str(child) and "generation" not in str(child)
    assert "recipients" not in child[0]["rules"]
    for actor in ("adult", "guest", "missing"):
        assert online.view(school_engine.snapshot(), actor, now) == {"sources": []}


async def test_manual_school_tasks_court_and_outbox_remain_untouched(school_engine, now):
    state = school_engine.snapshot()
    state["school"].setdefault("timetables", {})["manual"] = {"synthetic": "manual sentinel"}
    state["school"].setdefault("preparations", {})["manual"] = {"synthetic": "preparation sentinel"}
    before_school = deepcopy(state["school"])
    ctx = Context(state, state["members"]["owner"], now, "synthetic-context")
    source = online.handle(ctx, "source_save", binding())
    online.apply_snapshot(state, source["id"], source["generation"], 1, snapshot(), now)
    assert {
        key: value for key, value in state["school"].items() if key != "online"
    } == before_school
    for bucket in ("tasks", "court", "outbox", "alarm_runs"):
        assert state[bucket] == school_engine.snapshot()[bucket]


async def test_initial_baseline_is_silent_and_reordering_or_replay_cannot_duplicate_changes(
    school_engine, now
):
    source = await save(school_engine, now)
    baseline = await apply(school_engine, source, now)
    assert baseline == {"applied": True, "baseline": True, "changes": []}
    before = school_engine.snapshot()
    assert not (await apply(school_engine, source, now))["applied"]
    assert school_engine.snapshot() == before
    same = await apply(school_engine, source, now + timedelta(minutes=1))
    assert same["changes"] == [] and not same["baseline"]
    assert stored(school_engine, source)["revision"] == 1


async def test_changes_are_factual_hash_identified_and_homework_removal_is_not_missed_submission(
    school_engine, now
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    changed = snapshot()
    changed["lessons"][0].update(homework="Read chapters one and two.", cancelled=True)
    changed["grades"][0].update(value="Revised mark", comment="Correction")
    result = await apply(school_engine, source, now + timedelta(minutes=1), changed)
    assert {item["kind"] for item in result["changes"]} == {"lesson", "homework", "grade"}
    assert all(item["change"] == "changed" and len(item["id"]) == 64 for item in result["changes"])
    assert any(
        item["before"]["value"] == "Excellent" and item["after"]["value"] == "Revised mark"
        for item in result["changes"]
        if item["kind"] == "grade"
    )
    assert not (await apply(school_engine, source, now + timedelta(minutes=2), changed))["changes"]
    assert school_engine.snapshot()["outbox"] == {}


async def test_new_homework_on_existing_lesson_is_new_not_a_fabricated_old_assignment(
    school_engine, now
):
    source = await save(school_engine, now)
    empty = snapshot()
    empty["lessons"][0]["homework"] = ""
    await apply(school_engine, source, now, empty)
    changes = (await apply(school_engine, source, now + timedelta(minutes=1)))["changes"]
    assert len(changes) == 1 and changes[0]["kind"] == "homework" and changes[0]["change"] == "new"


async def test_empty_valid_snapshot_replaces_cache_and_empty_grades_are_not_zero(
    school_engine, now
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    result = await apply(
        school_engine,
        source,
        now + timedelta(minutes=1),
        snapshot(lessons=[], grades=[], absences=[]),
    )
    assert result["applied"] and result["changes"] == []
    assert stored(school_engine, source)["snapshot"]["grades"] == []


async def test_failure_retains_last_good_data_with_explicit_freshness(school_engine, now):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    previous = stored(school_engine, source)
    await school_engine.system_update(
        "online_school_failed",
        now + timedelta(minutes=1),
        lambda ctx: online.record_failure(
            ctx.state,
            source["id"],
            source["generation"],
            1,
            "online_school_auth_failed",
            now + timedelta(minutes=1),
        ),
    )
    current = stored(school_engine, source)
    assert (
        current["snapshot"] == previous["snapshot"]
        and current["last_success"] == previous["last_success"]
    )
    visible = online.view(school_engine.snapshot(), "child", now + timedelta(minutes=1))["sources"][
        0
    ]
    assert visible["stale"] and visible["status"] == "online_school_auth_failed"
    assert visible["snapshot"]["lessons"]
    assert online.view(previous_state := school_engine.snapshot(), "child", None)["sources"][0][
        "stale"
    ]
    assert previous_state == school_engine.snapshot()


async def test_legacy_engine_view_without_now_is_conservatively_stale(school_engine, now):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    assert school_engine.view("owner")["school"]["online"]["sources"][0]["stale"]
    assert not school_engine.view("child", now=now)["school"]["online"]["sources"][0]["stale"]
    assert online.view(
        school_engine.snapshot(), "child", now + online.FRESH_FOR + timedelta(seconds=1)
    )["sources"][0]["stale"]
    assert online.view(school_engine.snapshot(), "child", now - timedelta(seconds=1))["sources"][0][
        "stale"
    ]


async def test_stale_generation_member_epoch_or_out_of_order_completion_is_inert(
    school_engine, now
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now + timedelta(minutes=2))
    before = school_engine.snapshot()
    for pins in ({"generation": "old"}, {"member_revision": 99}, {}):
        assert not (await apply(school_engine, source, now + timedelta(minutes=1), **pins))[
            "applied"
        ]
    assert school_engine.snapshot() == before
    for field, value in (("revision", 2), ("active", False), ("role", "adult")):
        state = school_engine.snapshot()
        state["members"]["child"][field] = value
        unchanged = deepcopy(state)
        assert not online.apply_snapshot(
            state, source["id"], source["generation"], 1, snapshot(), now + timedelta(minutes=3)
        )["applied"]
        assert online.view(state, "owner", now)["sources"] == []
        assert state == unchanged


async def test_module_disable_fences_reads_and_late_success_or_failure(school_engine, now):
    source = await save(school_engine, now)
    state = school_engine.snapshot()
    state["settings"]["modules"].remove("school")
    before = deepcopy(state)
    assert not online.apply_snapshot(state, source["id"], source["generation"], 1, snapshot(), now)[
        "applied"
    ]
    assert not online.record_failure(
        state, source["id"], source["generation"], 1, "online_school_timeout", now
    )["applied"]
    assert online.view(state, "owner", now) == {"sources": []} and state == before


async def test_rebinding_requires_new_generation_and_clears_old_child_cache_history_and_acks(
    school_engine, now
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    await acknowledge(school_engine, source, now)
    with pytest.raises(DomainError, match="conflict"):
        await save(
            school_engine,
            now,
            operation="bad-rebind",
            id=source["id"],
            revision=1,
            member="sibling",
        )
    rebound = await save(
        school_engine,
        now,
        operation="rebind",
        id=source["id"],
        revision=1,
        member="sibling",
        student_id="student-b",
        generation="b" * 32,
    )
    row = stored(school_engine, rebound)
    assert row["snapshot"] is None and row["changes"] == [] and row["acknowledgements"] == {}
    assert online.view(school_engine.snapshot(), "child", now)["sources"] == []
    assert "Read the water" not in str(online.view(school_engine.snapshot(), "sibling", now))
    assert not (await apply(school_engine, source, now + timedelta(minutes=1)))["applied"]


async def test_disable_retains_good_cache_privately_but_blocks_background_and_child_view(
    school_engine, now
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    await school_engine.execute(
        "owner", "school.online_source_disable", {"id": source["id"], "revision": 1}, "disable", now
    )
    assert stored(school_engine, source)["snapshot"] is not None
    assert online.view(school_engine.snapshot(), "child", now)["sources"] == []
    row = online.view(school_engine.snapshot(), "owner", now)["sources"][0]
    assert row["status"] == "disabled" and row["snapshot"] is None
    assert not (await apply(school_engine, source, now + timedelta(minutes=1)))["applied"]


def malformed_cases():
    cases = []
    for key, value in (
        ("password", "synthetic"),
        ("coverage_start", "2026-02-30"),
        ("coverage_end", "2027-09-06"),
        ("timezone", "Not/AZone"),
        ("source_url", "https://user:password@school.example/"),
        ("source_url", "http://school.example/"),
        ("lessons", {}),
        ("grades", None),
    ):
        item = snapshot()
        item[key] = value
        cases.append(item)
    for key, value in (
        ("homework", "<script>bad</script>"),
        ("homework", "x" * 4001),
        ("date", "2026-08-01"),
        ("start", "08:00:01"),
        ("end", "07:00"),
        ("estimated_minutes", True),
        ("estimated_minutes", float("nan")),
        ("cancelled", 1),
        ("links", ["javascript:bad"]),
        ("attachments", [{"id": "F", "name": "x", "ext": "", "size": -1}]),
    ):
        item = snapshot()
        item["lessons"][0][key] = value
        cases.append(item)
    item = snapshot()
    item["lessons"].append(deepcopy(item["lessons"][0]))
    cases.append(item)
    item = snapshot()
    item["grades"][0]["value"] = 0
    cases.append(item)
    item = snapshot()
    item["grades"][0].update(date=None, period="")
    cases.append(item)
    return cases


@pytest.mark.parametrize("invalid", malformed_cases())
async def test_malformed_or_partial_snapshot_never_erases_valid_cache(school_engine, now, invalid):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    before = school_engine.snapshot()
    with pytest.raises(DomainError):
        await apply(school_engine, source, now + timedelta(minutes=1), invalid)
    assert school_engine.snapshot() == before


@pytest.mark.parametrize("field,limit", [("lessons", 300), ("grades", 1000), ("absences", 500)])
def test_record_caps_are_enforced(field, limit):
    value = snapshot(
        absences=[
            {
                "id": "absence",
                "date": "2026-09-06",
                "period": "",
                "subject": "Science",
                "comment": "Reported absent",
            }
        ]
    )
    value[field] = [{**value[field][0], "id": str(index)} for index in range(limit + 1)]
    with pytest.raises(DomainError):
        online.normalize_snapshot(value)


def test_aggregate_snapshot_byte_limit_and_optional_times_or_period_marks():
    value = snapshot()
    value["lessons"][0].update(start="", end="", estimated_minutes=None)
    value["grades"][0].update(date=None, period="First term", value="Pass")
    assert online.normalize_snapshot(value)["grades"][0]["value"] == "Pass"
    value["lessons"] = [
        {**value["lessons"][0], "id": str(index), "homework": "x" * 4000, "topic": "y" * 2000}
        for index in range(300)
    ]
    value["grades"] = [
        {**value["grades"][0], "id": str(index), "comment": "x" * 1000} for index in range(1000)
    ]
    with pytest.raises(DomainError, match="invalid_field"):
        online.normalize_snapshot(value)


def test_real_provider_parser_output_satisfies_canonical_snapshot_contract(now):
    from custom_components.family_assistant.online_school.parsing import snapshot as parse_snapshot

    days = [
        {"date": (now.date() + timedelta(days=index)).strftime("%d.%m.%Y"), "lessons": []}
        for index in range(7)
    ]
    days[0]["lessons"] = [
        {
            "id": 501,
            "subject_name": "Synthetic Science",
            "start_time": "09:00:00",
            "end_time": "09:45:00",
            "homework_html": "<p>Study <b>water</b>.</p>",
            "topic": "Water",
            "work_time": 20,
            "canceled": 0,
            "replacement": 0,
            "homework_files": [
                {"id": 301, "original_name": "worksheet.pdf", "ext": "pdf", "size": 42}
            ],
            "lesson_files": [],
        }
    ]
    student = {"user_id": 101, "user_name": "Synthetic Learner"}
    diary = {"week_days": days, "week": 1, "student": student}
    journal = {
        "student": student,
        "month_num": "1",
        "month_abs_num": "09",
        "dates": ["06"],
        "subjects": {"201": {"id": 201, "name": "Synthetic Science"}},
        "grades": {
            "06": {"201": [{"grade_value": "Pass", "comment": "Synthetic comment", "name": "Quiz"}]}
        },
        "absents": [],
    }
    parsed = parse_snapshot(
        [diary], journal, "101", "Europe/Kyiv", now, "https://school.example.invalid"
    )
    normalized = online.normalize_snapshot(parsed)
    assert normalized == parsed
    assert normalized["lessons"][0]["start"] == "09:00"
    assert normalized["lessons"][0]["homework"] == "Study water."
    assert normalized["grades"][0]["value"] == "Pass"


async def test_pinned_student_and_timezone_mismatch_never_replace_cache(school_engine, now):
    source = await save(school_engine, now)
    before = school_engine.snapshot()
    for value in (snapshot(student_id="student-b"), snapshot(timezone="UTC")):
        with pytest.raises(DomainError):
            await apply(school_engine, source, now, value)
    assert school_engine.snapshot() == before


async def test_local_ack_has_exact_homework_hash_and_separate_revision_and_reopens_on_change(
    school_engine, now
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    result = await acknowledge(school_engine, source, now)
    assert result["done"] and result["revision"] == 1
    assert stored(school_engine, source)["revision"] == 1
    assert stored(school_engine, source)["snapshot"] == online.normalize_snapshot(snapshot())
    before = school_engine.snapshot()
    with pytest.raises(DomainError, match="conflict"):
        await acknowledge(school_engine, source, now, operation="old-ack")
    assert school_engine.snapshot() == before
    changed = snapshot()
    changed["lessons"][0]["homework"] = "Review new instructions."
    await apply(school_engine, source, now + timedelta(minutes=1), changed)
    assert stored(school_engine, source)["acknowledgements"] == {}
    with pytest.raises(DomainError, match="conflict"):
        await acknowledge(school_engine, source, now, operation="ack")


@pytest.mark.parametrize("actor", ["sibling", "adult", "guest"])
async def test_ack_cannot_target_sibling_or_unprivileged_adult(school_engine, now, actor):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    before = school_engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await acknowledge(school_engine, source, now, actor=actor)
    assert school_engine.snapshot() == before


async def test_reload_and_exact_replay_keep_ids_and_do_not_duplicate_local_ack(
    school_engine, now, store
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    ack = await acknowledge(school_engine, source, now, actor="parent")
    reload = Engine(store.value, store.save)
    before = reload.snapshot()
    assert await save(reload, now) == source
    assert await acknowledge(reload, source, now, actor="parent") == ack
    assert reload.snapshot() == before
    assert reload.view("child", now=now)["school"]["online"]["sources"][0]["acknowledgements"][
        "lesson-a"
    ]["done"]


async def test_stale_config_revision_cannot_overwrite_new_rules(school_engine, now):
    source = await save(school_engine, now)
    updated = await save(
        school_engine,
        now,
        operation="rules",
        id=source["id"],
        revision=1,
        rules={"notify_changes": True},
    )
    assert updated["revision"] == 2
    with pytest.raises(DomainError, match="conflict"):
        await save(school_engine, now, operation="stale-rules", id=source["id"], revision=1)


async def test_store_failure_cannot_publish_success_or_replace_good_cache(
    school_engine, now, store
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now)
    before = school_engine.snapshot()
    store.fail = True
    changed = snapshot()
    changed["lessons"][0]["homework"] = "New assignment"
    with pytest.raises(OSError):
        await apply(school_engine, source, now + timedelta(minutes=1), changed)
    assert school_engine.snapshot() == before


async def test_source_count_and_change_history_are_bounded(school_engine, now):
    for index in range(8):
        source = await save(school_engine, now, operation=f"source-{index}")
    with pytest.raises(DomainError, match="capacity_exceeded"):
        await save(school_engine, now, operation="source-9")
    await apply(school_engine, source, now)
    for index in range(105):
        value = snapshot()
        value["grades"][0]["value"] = str(index)
        await apply(school_engine, source, now + timedelta(minutes=index + 1), value)
    rows = stored(school_engine, source)["changes"]
    assert (
        len(rows) == online.MAX_CHANGES and len({row["id"] for row in rows}) == online.MAX_CHANGES
    )


async def test_native_options_bridge_discards_secrets_and_preserves_manual_data(school_engine, now):
    config = options(
        OSsynthetic=binding(
            id="OSsynthetic",
            username="synthetic@example.invalid",
            password="synthetic-private-password",
            base_url="https://school.example",
        )
    )
    result = await reconcile(school_engine, now, config)
    assert result["applied"] and result["sources"][0]["id"] == "OSsynthetic"
    state = school_engine.snapshot()
    source = state["school"]["online"]["sources"]["OSsynthetic"]
    assert source["options_generation"] == "a" * 32
    assert not any(key in source for key in ("username", "password", "base_url"))
    assert "synthetic-private-password" not in str(state)
    assert state["school"]["online"]["options_revision"] == 1


async def test_generated_id_cannot_overwrite_externally_assigned_native_source(school_engine, now):
    await reconcile(school_engine, now, options(OS000001=binding(label="Native source")))
    created = await save(school_engine, now, label="Canonical source")
    assert created["id"] == "OS000002"
    sources = school_engine.snapshot()["school"]["online"]["sources"]
    assert len(sources) == 2 and sources["OS000001"]["label"] == "Native source"


async def test_native_options_revision_and_same_generation_cannot_resurrect_direct_disable(
    school_engine, now
):
    initial = options(OSsynthetic=binding())
    await reconcile(school_engine, now, initial)
    await school_engine.execute(
        "owner",
        "school.online_source_disable",
        {"id": "OSsynthetic", "revision": 1},
        "disable",
        now,
    )
    assert not (await reconcile(school_engine, now, initial))["applied"]
    assert (await reconcile(school_engine, now, options(2, OSsynthetic=binding())))["applied"]
    assert not school_engine.snapshot()["school"]["online"]["sources"]["OSsynthetic"]["enabled"]
    await reconcile(school_engine, now, options(3, OSsynthetic=binding(generation="b" * 32)))
    assert school_engine.snapshot()["school"]["online"]["sources"]["OSsynthetic"]["enabled"]
    before = school_engine.snapshot()
    assert not (await reconcile(school_engine, now, initial))["applied"]
    assert school_engine.snapshot() == before


async def test_native_rebind_is_silent_fresh_baseline_and_removal_disables(school_engine, now):
    await reconcile(school_engine, now, options(OSsynthetic=binding()))
    source = school_engine.snapshot()["school"]["online"]["sources"]["OSsynthetic"]
    await apply(school_engine, source, now)
    await reconcile(
        school_engine,
        now,
        options(
            2, OSsynthetic=binding(member="sibling", student_id="student-b", generation="b" * 32)
        ),
    )
    rebound = stored(school_engine, source)
    assert rebound["snapshot"] is None
    assert online.view(school_engine.snapshot(), "child", now)["sources"] == []
    assert (
        await apply(
            school_engine, rebound, now + timedelta(minutes=1), snapshot(student_id="student-b")
        )
    )["baseline"]
    await reconcile(school_engine, now, options(3))
    assert (
        not stored(school_engine, source)["enabled"]
        and stored(school_engine, source)["snapshot"] is not None
    )


async def test_unrelated_new_options_envelope_does_not_disable_unchanged_source(school_engine, now):
    await reconcile(school_engine, now, options(OSa=binding()))
    await reconcile(
        school_engine,
        now,
        options(
            2,
            OSa=binding(),
            OSb=binding(member="sibling", student_id="student-b", generation="b" * 32),
        ),
    )
    sources = school_engine.snapshot()["school"]["online"]["sources"]
    assert sources["OSa"]["enabled"] and sources["OSa"]["revision"] == 1
    assert sources["OSb"]["enabled"]


async def test_native_options_invalid_source_is_atomic_and_stale_child_does_not_rebind(
    school_engine, now
):
    before = school_engine.snapshot()
    with pytest.raises(DomainError):
        await reconcile(
            school_engine, now, options(OSa=binding(), OSb=binding(timezone="Mars/Test"))
        )
    assert school_engine.snapshot() == before
    await reconcile(school_engine, now, options(OSa=binding()))
    await reconcile(
        school_engine,
        now,
        options(2, OSa=binding(member="sibling", member_revision=99, generation="b" * 32)),
    )
    source = school_engine.snapshot()["school"]["online"]["sources"]["OSa"]
    assert source["member"] == "child" and not source["enabled"]


@pytest.mark.parametrize("generation", [None, [], True, ""])
async def test_malformed_native_generation_is_rejected_even_for_existing_source(
    school_engine, now, generation
):
    await reconcile(school_engine, now, options(OSa=binding()))
    before = school_engine.snapshot()
    with pytest.raises(DomainError):
        await reconcile(school_engine, now, options(2, OSa=binding(generation=generation)))
    assert school_engine.snapshot() == before


async def test_failure_codes_are_allowlisted_and_old_failure_cannot_replace_newer_success(
    school_engine, now
):
    source = await save(school_engine, now)
    await apply(school_engine, source, now + timedelta(minutes=2))
    before = school_engine.snapshot()
    state = deepcopy(before)
    assert not online.record_failure(
        state,
        source["id"],
        source["generation"],
        1,
        "online_school_timeout",
        now + timedelta(minutes=1),
    )["applied"]
    for error in ("raw password from server", {}, None):
        with pytest.raises(DomainError):
            online.record_failure(
                state, source["id"], source["generation"], 1, error, now + timedelta(minutes=3)
            )
    assert state == before
