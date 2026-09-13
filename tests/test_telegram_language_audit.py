"""Synthetic migration compatibility regressions against the canonical Engine."""

from datetime import timedelta

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.commands import signature
from custom_components.family_assistant.telegram.intents import find_member
from custom_components.family_assistant.telegram.router import COPY, canonical_command, route


async def enable_conversation(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "enable",
        now,
    )


@pytest.mark.parametrize("command", ["/forget", "/забыть", "/forget L000001", "/забыть L000001"])
async def test_legacy_forget_never_deletes_a_learned_phrase(engine, now, command):
    await enable_conversation(engine, now)
    result = await engine.execute(
        "parent",
        "conversation.learn",
        {"source": "pantry roll", "canonical": "/shopping"},
        "learn",
        now,
    )
    reply = await route(engine, "parent", command, "legacy-forget", now, private=True)
    assert "/forgetphrase" in reply
    assert engine.snapshot()["memory"]["phrases"][result["id"]]["active"] is True


async def test_explicit_forgetphrase_checks_actor_and_replays(engine, now):
    await enable_conversation(engine, now)
    result = await engine.execute(
        "parent",
        "conversation.learn",
        {"source": "pantry roll", "canonical": "/shopping"},
        "learn",
        now,
    )
    command = "/forgetphrase " + result["id"]
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", command, "child-forget", now, private=True)
    assert engine.snapshot()["memory"]["phrases"][result["id"]]["active"] is True
    reply = await route(engine, "parent", command, "forget-phrase", now, private=True)
    assert engine.snapshot()["memory"]["phrases"][result["id"]]["active"] is False
    assert (
        await route(
            engine, "parent", command, "forget-phrase", now + timedelta(days=1), private=True
        )
        == reply
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "create task Child One read chapter",
        "создай задачу Child One прочитать главу",
        "створи завдання Child One прочитати розділ",
    ],
)
async def test_multiword_task_recipient_does_not_silently_use_first_name(engine, now, phrase):
    await engine.system_update(
        "name", now, lambda ctx: ctx.state["members"]["sibling"].update(name="Child One")
    )
    await route(engine, "parent", phrase, "create", now)
    task = next(iter(engine.snapshot()["tasks"].values()))
    assert task["assignee"] == "sibling"
    assert not task["title"].startswith("One ")


@pytest.mark.parametrize(
    "phrase",
    [
        "assign Child One task read chapter",
        "назначь Child One задачу прочитать главу",
        "признач Child One завдання прочитати розділ",
    ],
)
async def test_multiword_task_recipient_before_task_marker(engine, now, phrase):
    await engine.system_update(
        "name", now, lambda ctx: ctx.state["members"]["sibling"].update(name="Child One")
    )
    await route(engine, "parent", phrase, "create", now)
    assert next(iter(engine.snapshot()["tasks"].values()))["assignee"] == "sibling"


@pytest.mark.parametrize("word", ["сыну", "жене", "доньці", "дружині", "wife", "son"])
def test_kinship_requires_explicit_configuration(engine, word):
    with pytest.raises(DomainError, match="unknown_member"):
        find_member(engine.snapshot(), word)


def test_explicit_kinship_alias_cannot_resolve_two_people(engine):
    state = engine.snapshot()
    state["members"]["child"]["aliases"] = ["сыну"]
    assert find_member(state, "сыну") == "child"
    state["members"]["sibling"]["aliases"] = ["сыну"]
    with pytest.raises(DomainError, match="ambiguous_member"):
        find_member(state, "сыну")


@pytest.mark.parametrize("separator", ["\t", "\n", "\r\n"])
async def test_slash_arguments_accept_telegram_whitespace_without_model(engine, now, separator):
    async def forbidden_fallback(*_):
        pytest.fail("Explicit slash command must not be delegated to a model")

    await route(
        engine,
        "parent",
        "/task" + separator + "Child | Read chapter",
        "create",
        now,
        fallback=forbidden_fallback,
    )
    assert engine.snapshot()["tasks"]["T000001"]["title"] == "Read chapter"
    await route(
        engine,
        "parent",
        "/alarm" + separator + "Child | weekdays | 07:15",
        "alarm",
        now,
        fallback=forbidden_fallback,
    )
    assert engine.snapshot()["alarms"]["A000001"]["time"] == "07:15"


async def test_old_pending_forget_plan_cannot_disable_a_phrase_after_upgrade(engine, now):
    await enable_conversation(engine, now)
    phrase = await engine.execute(
        "parent",
        "conversation.learn",
        {"source": "pantry roll", "canonical": "/shopping"},
        "learn",
        now,
    )
    content = "/forget " + phrase["id"]
    await engine.system_update(
        "old-plan",
        now,
        lambda ctx: (
            ctx.state["telegram"]
            .setdefault("plans", {})
            .update(
                {
                    "old-forget": {
                        "signature": signature("parent", content, ()),
                        "actor": "parent",
                        "action": "conversation.forget",
                        "payload": {"id": phrase["id"]},
                        "created_at": now.isoformat(),
                    }
                }
            )
        ),
    )
    assert "/forgetphrase" in await route(engine, "parent", content, "old-forget", now)
    assert engine.snapshot()["memory"]["phrases"][phrase["id"]]["active"] is True
    assert "old-forget" not in engine.snapshot()["processed"]


async def test_ambiguous_full_name_never_falls_back_to_unique_short_id(engine, now):
    def configure(ctx):
        ctx.state["members"]["sibling"]["name"] = "Child One"
        ctx.state["members"]["child"]["aliases"] = ["Child One"]

    await engine.system_update("aliases", now, configure)
    with pytest.raises(DomainError, match="ambiguous_member"):
        await route(engine, "parent", "create task Child One read chapter", "ambiguous", now)
    assert not engine.snapshot()["tasks"]


async def test_multiline_command_receipt_keeps_exact_original_request(engine, now):
    content = "/task\nChild | Read chapter"
    response = await route(engine, "parent", content, "create", now)
    assert await route(engine, "parent", content, "create", now) == response
    with pytest.raises(DomainError, match="idempotency_conflict"):
        await route(engine, "parent", "/task Child | Read chapter", "create", now)
    assert len(engine.snapshot()["tasks"]) == 1


@pytest.mark.parametrize("language", ["en", "ru", "uk"])
async def test_migration_forget_help_is_localized_and_command_help_remains_bounded(
    engine, now, language
):
    await engine.system_update(
        "language", now, lambda ctx: ctx.state["members"]["parent"].update(language=language)
    )
    assert await route(engine, "parent", "/forget", "forget", now) == COPY[language]["forget_scope"]
    reply = await route(engine, "parent", "/commands", "commands", now)
    assert "/forgetphrase" in reply and len(reply) <= 4000
    for command in (
        "/polls",
        "/feedback",
        "/confirm",
        "/cancel",
        "/netblock",
        "/netuntil",
        "/netlimit",
        "/netcancel",
    ):
        assert command in reply


def test_russian_yo_in_read_aliases_is_normalized():
    assert canonical_command("/подъём") == "/alarms"
    assert canonical_command("/КОШЕЛЁК") == "/wallet"


@pytest.mark.parametrize(
    "command",
    [
        "/память",
        "/запомни Fictional fact",
        "/забудьпамять M000001",
        "/забыть_память M000001",
        "/forgetmemory M000001",
        "/продлить T000001 на неделю",
    ],
)
async def test_unimplemented_legacy_slash_is_not_delegated_or_reported_as_saved(
    engine, now, command
):
    async def forbidden_fallback(*_):
        pytest.fail("Unsupported explicit commands must not become model actions")

    before = engine.snapshot()
    assert (
        await route(engine, "parent", command, "unsupported", now, fallback=forbidden_fallback)
        == COPY["en"]["unknown"]
    )
    assert engine.snapshot() == before


@pytest.mark.parametrize("language", ["en", "ru", "uk"])
async def test_voice_command_is_an_explicit_localized_no_model_response(engine, now, language):
    async def forbidden_fallback(*_):
        pytest.fail("Voice is unsupported, not a model input")

    await engine.system_update(
        "language", now, lambda ctx: ctx.state["members"]["parent"].update(language=language)
    )
    assert (
        await route(engine, "parent", "/voice", "voice", now, fallback=forbidden_fallback)
        == COPY[language]["voice_unsupported"]
    )


@pytest.mark.parametrize(
    "command,mode",
    [
        ("/netpause Child", "pause"),
        ("/netresume Child", "resume"),
        ("/netgrant Child | 30", "grant"),
        ("/netblock Child | 30", "timed_pause"),
        ("/netuntil Child | 08:30", "grant"),
        ("/netschedule Child | weekdays | 08:00-22:00", "schedule"),
        ("/netlimit Child | 2M/5M", "rate"),
    ],
)
async def test_advertised_network_commands_make_reviewed_plans_only(engine, now, command, mode):
    from test_kids import prepare_engine

    await prepare_engine(engine, now)
    reply = await route(engine, "parent", command, "plan", now)
    plan = engine.snapshot()["network"]["kid_plans"]["K000001"]
    assert plan["mode"] == mode and plan["status"] == "preview"
    assert "Review only" in reply and "Configuration applied" not in reply
    assert await route(engine, "parent", command, "plan", now) == reply
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", command, "child-plan", now)
    cancelled = await route(engine, "parent", "/netcancel K000001", "cancel-plan", now)
    assert "cancelled" in cancelled.lower()
    assert engine.snapshot()["network"]["kid_plans"]["K000001"]["status"] == "cancelled"


async def test_routine_mode_cancel_and_task_title_use_existing_guarded_contracts(
    engine, store, now
):
    from test_routine_edges import enabled, setup_run

    engine = enabled(engine, store)
    run = await setup_run(engine, now)
    await route(engine, "parent", "/routinemode holidays", "mode", now, private=True)
    assert engine.snapshot()["settings"]["routines"]["modes"] == ["holidays"]
    await route(
        engine,
        "parent",
        "/routinecancel " + run["id"] + " | Changed plans",
        "cancel",
        now,
        private=True,
    )
    assert engine.snapshot()["routine_runs"][run["id"]]["status"] == "cancelled"
    await route(engine, "parent", "/task Child | Original", "task", now)
    await route(engine, "parent", "/edit T000001 title Reviewed title", "edit", now)
    assert engine.snapshot()["tasks"]["T000001"]["title"] == "Reviewed title"
