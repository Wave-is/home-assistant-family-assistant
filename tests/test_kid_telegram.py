"""Parent bot controls cannot report success before the router worker runs."""

import pytest
from test_kids import prepare_engine

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.network import COPY, FIELDS, diff_line, parsed
from custom_components.family_assistant.telegram.router import route


@pytest.mark.asyncio
async def test_parent_natural_grant_confirmation_replay_and_child_status(engine, now):
    await prepare_engine(engine, now)
    response = await route(engine, "parent", "give Child internet for 30 minutes", "tg-plan", now)
    assert "Review only" in response and "/netconfirm K000001" in response
    assert engine.snapshot()["network"]["kid_plans"]["K000001"]["status"] == "preview"
    queued = await route(engine, "parent", "/netconfirm K000001", "tg-apply", now)
    assert "Queued" in queued and "Configuration applied" not in queued
    assert await route(engine, "parent", "/netconfirm K000001", "tg-apply", now) == queued
    own = await route(engine, "child", "/internet Child", "read-own", now)
    assert "08:00-22:00" in own and "02:11" not in own
    with pytest.raises(DomainError):
        await route(engine, "sibling", "/internet Child", "read-other", now)
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/netconfirm K000001", "child-apply", now)


@pytest.mark.asyncio
async def test_all_languages_schedule_and_no_guessing_compound_negation(engine, now):
    await prepare_engine(engine, now)
    for command, mode in [
        ("выключи интернет Child", "pause"),
        ("увімкни Child інтернет", "resume"),
        ("дай Child интернет на 30 минут", "grant"),
        ("/netschedule Child | weekdays | 08:00-22:00", "schedule"),
        ("/netlimit Child | 5M", "rate"),
    ]:
        action, payload = parsed(engine.snapshot(), command, now)
        assert action == "mikrotik.kid_plan" and payload["mode"] == mode
    assert parsed(engine.snapshot(), "не выключи интернет Child", now) is None
    with pytest.raises(DomainError, match="unknown_member"):
        parsed(engine.snapshot(), "выключи интернет Child и Sibling", now)
    assert all(set(locale) == set(COPY["en"]) for locale in COPY.values())
    assert all(set(locale) == set(FIELDS["en"]) for locale in FIELDS.values())
    assert diff_line("disabled", {"before": "false", "after": "true"}, "ru") == (
        "Ограничения: Включены → Выключены"
    )
