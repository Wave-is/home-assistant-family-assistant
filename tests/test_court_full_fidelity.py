"""Court adapter regressions against the actual public Engine and Store contracts."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.court import (
    Assessment,
    FamilyLedger,
    ParsedMessage,
    calculate_court_stats,
    parse_message,
)
from custom_components.family_assistant.court.responses import COPY, weekly_report
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.court_router import route_court
from custom_components.family_assistant.telegram.router import route


@pytest.fixture
def court_engine(engine, store):
    state = engine.snapshot()
    state["members"]["child"].update(name="Ученик", aliases=["Ученику"])
    state["members"]["sibling"].update(name="Подросток", aliases=["Подростку"])
    return Engine(state, store.save)


def parse(engine, content):
    return parse_message(content, members=engine.snapshot()["members"].values())


async def request(engine, actor, content, operation, now, *, parsed=None, language="ru", view=None):
    return await route_court(
        engine,
        actor,
        content,
        operation,
        now,
        parsed or parse(engine, content),
        view or engine.view(actor, now=now),
        language,
    )


async def award(engine, now, member="child", points=1, operation="award", reason="Example reason"):
    return await engine.execute(
        "parent",
        "court.award",
        {"member": member, "points": points, "reason": reason},
        operation,
        now,
    )


def test_parser_uses_only_configured_member_names_and_aliases(court_engine):
    parsed = parse(court_engine, "Ученику плюс за помощь")
    assert parsed.action == "assessments"
    assert parsed.assessments[0].child == "child"
    assert parsed.assessments[0].reason == "помощь"
    assert parse_message("Неизвестному плюс за помощь").action == "missing_child"
    assert parse(court_engine, "Подросток не забыл уроки").action == "ambiguous"
    assert parse(court_engine, "Ученик молодец, а Подросток накосячил").action == "assessments"
    assert parse(court_engine, "Ученик и Подросток сделали уроки").action == "ambiguous"
    assert parse(court_engine, "поставь задачу Ученику сделать уроки").action == "ignore"


@pytest.mark.parametrize(
    "command",
    [
        "/stats",
        "/week",
        "/суд",
        "/баллы",
        "/штрафы",
        "/appeal C000001 | reason",
        "/апелляция C000001 | причина",
        "/award child | 1 | reason",
        "/reverse C000001 | reason",
        "/courtresolve C000001 | reverse | reason",
        "/tasks Подросток не сделал уроки",
    ],
)
def test_canonical_slash_routes_are_not_intercepted(court_engine, command):
    assert parse(court_engine, command).action == "ignore"


def test_duplicate_configured_alias_is_ambiguous(court_engine):
    members = list(court_engine.snapshot()["members"].values())
    for member in members:
        if member["role"] == "child":
            member["aliases"].append("Общий")
    assert parse_message("Общий плюс за помощь", members=members).action == "ambiguous"


async def test_actual_engine_awards_atomically_and_replays_after_restart(court_engine, store, now):
    content = "Ученик плюс за помощь, а Подросток минус за пропуск"
    answer = await request(court_engine, "parent", content, "scores", now)
    assert "Ученик: +1" in answer
    assert "Подросток: −1" in answer
    state = court_engine.snapshot()
    assert len(state["court"]) == 2
    assert state["processed"]["scores"]["result"]["items"][0]["member"] == "child"
    restored = Engine(store.value, store.save)
    await request(restored, "parent", content, "scores", now)
    assert restored.snapshot()["court"] == state["court"]


async def test_invalid_second_score_cannot_commit_first(court_engine, now):
    parsed = ParsedMessage(
        "assessments",
        assessments=(
            Assessment("child", "plus", "Example reason", "", "explicit"),
            Assessment("missing", "minus", "Example reason", "", "explicit"),
        ),
    )
    with pytest.raises(DomainError):
        await request(court_engine, "parent", "synthetic batch", "bad-batch", now, parsed=parsed)
    assert court_engine.snapshot()["court"] == {}


async def test_disk_failure_cannot_commit_score(court_engine, store, now):
    before = court_engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await request(court_engine, "parent", "Ученику плюс за помощь", "disk", now)
    assert court_engine.snapshot() == before


async def test_child_and_adult_views_do_not_reveal_other_scores(court_engine, now):
    await award(court_engine, now, reason="Visible own reason")
    await award(court_engine, now, "sibling", -7, "sibling-award", "Private sibling reason")
    answer = await request(court_engine, "child", "что по баллам", "read", now)
    assert "Visible own reason" in answer
    assert "Private sibling reason" not in answer
    assert "Подросток" not in answer
    answer = await request(court_engine, "adult", "/history", "adult-read", now)
    assert "Visible own reason" not in answer
    assert "Private sibling reason" not in answer


async def test_filtered_history_uses_only_requested_member_and_actual_points(court_engine, now):
    await award(court_engine, now, points=7, reason="Seven point reason")
    await award(court_engine, now, "sibling", -3, "other", "Other child reason")
    answer = await request(court_engine, "parent", "/history Ученик", "history", now)
    assert "+7" in answer and "Seven point reason" in answer
    assert "Other child reason" not in answer
    answer = await request(court_engine, "child", "/дело Подросток", "hidden", now)
    assert answer == COPY["ru"]["denied"]


async def test_fresh_permission_rejects_stale_projection(court_engine, store, now):
    stale = court_engine.view("parent", now=now)
    state = court_engine.snapshot()
    state["members"]["parent"]["active"] = False
    revoked = Engine(state, store.save)
    with pytest.raises(DomainError, match="forbidden"):
        await request(revoked, "parent", "/history", "stale", now, view=stale)


async def test_guest_and_child_cannot_award(court_engine, now):
    for actor in ("guest", "child", "adult"):
        answer = await request(court_engine, actor, "Ученику минус за пропуск", actor, now)
        assert answer == COPY["ru"]["denied"]
    assert court_engine.snapshot()["court"] == {}


async def test_disabled_module_rejected(court_engine, store, now):
    state = court_engine.snapshot()
    state["settings"]["modules"].remove("court")
    disabled = Engine(state, store.save)
    with pytest.raises(DomainError, match="module_disabled"):
        await request(disabled, "parent", "/history", "disabled", now)


async def test_undo_replay_keeps_original_target_after_new_score(court_engine, now):
    first = await award(court_engine, now, operation="first")
    await request(court_engine, "parent", "/undo", "undo", now)
    second = await award(court_engine, now + timedelta(minutes=1), operation="second")
    await request(court_engine, "parent", "/undo", "undo", now + timedelta(minutes=2))
    records = court_engine.snapshot()["court"]
    assert records[first["id"]]["status"] == "reversed"
    assert records[second["id"]]["status"] == "active"


async def test_adapter_period_matches_configured_domain_period(court_engine, now):
    await court_engine.execute(
        "owner",
        "court.configure",
        {"revision": 0, "weekday": 6, "time": "10:00"},
        "configure",
        now,
    )
    await award(court_engine, now - timedelta(days=2), operation="earlier")
    view = court_engine.view("parent", now=now)
    summary = calculate_court_stats(
        view["court"],
        view["settings"]["timezone"],
        now,
        view["members"],
        weekday=6,
        time_str="10:00",
    )
    assert summary.start.isoformat() == view["court_summary"]["start"]
    assert summary.end.isoformat() == view["court_summary"]["end"]
    assert summary.stats["child"]["balance"] == 1
    answer = await request(court_engine, "parent", "что по баллам", "period", now)
    assert view["court_summary"]["start"] in answer


async def test_existing_appeal_is_real_domain_action(court_engine, now):
    record = await award(court_engine, now, points=-1)
    answer = await route(
        court_engine,
        "child",
        f"/appeal {record['id']} | Please review",
        "appeal-command",
        now,
    )
    assert answer
    assert court_engine.snapshot()["court"][record["id"]]["appeal"]["status"] == "pending"


@pytest.mark.parametrize("language", ["en", "ru", "uk"])
async def test_localized_guidance_and_reports_do_not_invent_effects(court_engine, now, language):
    answer = await request(court_engine, "parent", "/rules", language, now, language=language)
    assert answer == COPY[language]["rules"]
    assert "/appeal" in answer
    view = court_engine.view("parent", now=now)
    stats = calculate_court_stats(view["court"], now=now, members=view["members"])
    report = weekly_report(stats.stats, stats.week_id, language=language)
    assert "Ученик" in report
    assert "Babushka" not in report


def test_legacy_compatibility_store_uses_given_members_without_second_runtime_state(now):
    ledger = FamilyLedger(None, now, children=("sample_child",))
    assert set(ledger.state["children"]) == {"sample_child"}
    source = ledger.serializable()
    restored = FamilyLedger(source, now)
    assert restored.serializable() == source
    assessment = Assessment("sample_child", "plus", "Synthetic reason", "", "explicit")
    invalid = Assessment("unknown", "minus", "Synthetic reason", "", "explicit")
    with pytest.raises(ValueError):
        ledger.apply_assessments(
            (assessment, invalid),
            timestamp=now,
            chat_id=1,
            message_id=2,
            original_text="Synthetic",
            parent_user_id=3,
            parent_name="Example parent",
        )
    assert ledger.serializable() == source
    # Existing extensions/rules remain byte-for-byte values in the compatibility shape.
    source["custom_rule"] = {"threshold": 8, "description": "Synthetic privilege rule"}
    copied = FamilyLedger(deepcopy(source), now)
    assert copied.serializable() == source
