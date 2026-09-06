"""Parent bot controls cannot report success before the router worker runs."""

import pytest
from test_kids import prepare_engine

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.network import (
    COPY,
    FIELDS,
    diff_line,
    parsed,
)
from custom_components.family_assistant.telegram.network import (
    status as network_status,
)
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


@pytest.mark.asyncio
async def test_telegram_status_configured_permission_and_privacy(engine, now):
    await prepare_engine(engine, now)
    view = engine.view("parent")
    view["settings"]["timezone"] = "Europe/Kyiv"

    # Profile with known active status
    view["kid_control"]["profiles"][0]["status"] = {
        "mode": "schedule",
        "allows": True,
        "next_change_at": "2026-09-07T20:00:00+00:00",
        "next_allows": False,
        "remaining_minutes": 45,
        "temporary_until": "2026-09-07T21:00:00+00:00",
        "temporary_mode": "grant",
        "valid_until": "2026-09-07T10:00:00+00:00",
        "reason": "fresh",
    }

    text_en = network_status(view, "child", "en")
    assert "Normal schedule" in text_en
    assert "Configured access: Allowed" in text_en
    assert "Remaining: 45 min" in text_en
    assert "Next blocked: 2026-09-07 23:00 (Europe/Kyiv)" in text_en
    assert "Temporary access until: 2026-09-08 00:00 (Europe/Kyiv)" in text_en
    assert "Weekly schedule:" in text_en
    assert "Monday: 08:00-22:00" in text_en
    assert "Devices: Phone" in text_en
    # Privacy check: no MAC address disclosed
    assert "02:11:22:33:44:55" not in text_en
    assert "02:11" not in text_en

    text_ru = network_status(view, "child", "ru")
    assert "Обычное расписание" in text_ru
    assert "По настройкам: доступ разрешён" in text_ru
    assert "Осталось: 45 мин" in text_ru
    assert "Следующая блокировка: 2026-09-07 23:00 (Europe/Kyiv)" in text_ru
    assert "Временный доступ до: 2026-09-08 00:00 (Europe/Kyiv)" in text_ru
    assert "Еженедельное расписание:" in text_ru
    assert "Понедельник: 08:00-22:00" in text_ru
    assert "Устройства: Phone" in text_ru
    assert "02:11" not in text_ru

    text_uk = network_status(view, "child", "uk")
    assert "Звичайний розклад" in text_uk
    assert "За налаштуваннями: доступ дозволено" in text_uk
    assert "Залишилося: 45 хв" in text_uk
    assert "Наступне блокування: 2026-09-07 23:00 (Europe/Kyiv)" in text_uk
    assert "Тимчасовий доступ до: 2026-09-08 00:00 (Europe/Kyiv)" in text_uk
    assert "Щотижневий розклад:" in text_uk
    assert "Понеділок: 08:00-22:00" in text_uk
    assert "Пристрої: Phone" in text_uk
    assert "02:11" not in text_uk

    # Unknown mode / missing status paired with historical disabled=true
    view["kid_control"]["profiles"][0]["observed"]["disabled"] = "true"
    view["kid_control"]["profiles"][0]["status"] = {"mode": "unknown", "allows": None}
    unk_en = network_status(view, "child", "en")
    assert "⚠️ Status unknown: refresh router data" in unk_en
    assert "Configured access: Allowed" not in unk_en
    assert "Configured access: Blocked" not in unk_en
    # Crucial check: NEVER prints restrictions disabled as live status when summary is unknown!
    assert "Restrictions disabled" not in unk_en
    # Historical weekly schedule is still shown
    assert "Weekly schedule:" in unk_en
    assert "Monday: 08:00-22:00" in unk_en

    unk_ru = network_status(view, "child", "ru")
    assert "⚠️ Статус неизвестен: обновите данные роутера" in unk_ru
    assert "Ограничения выключены" not in unk_ru
    assert "Понедельник: 08:00-22:00" in unk_ru

    unk_uk = network_status(view, "child", "uk")
    assert "⚠️ Статус невідомий: оновіть дані роутера" in unk_uk
    assert "Обмеження вимкнено" not in unk_uk
    assert "Понеділок: 08:00-22:00" in unk_uk

    # Invalid mode or non-boolean allows also treated as unknown
    view["kid_control"]["profiles"][0]["status"] = {"mode": "invalid_mode", "allows": True}
    assert "⚠️ Status unknown: refresh router data" in network_status(view, "child", "en")
    view["kid_control"]["profiles"][0]["status"] = {"mode": "schedule", "allows": "yes"}
    assert "⚠️ Status unknown: refresh router data" in network_status(view, "child", "en")

    # Blocked status with timed_pause
    view["kid_control"]["profiles"][0]["status"] = {
        "mode": "paused",
        "allows": False,
        "next_change_at": "2026-09-07T12:00:00+00:00",
        "next_allows": True,
        "remaining_minutes": None,
        "temporary_until": "2026-09-07T12:00:00+00:00",
        "temporary_mode": "timed_pause",
        "valid_until": "2026-09-07T10:00:00+00:00",
        "reason": "fresh",
    }
    paused_en = network_status(view, "child", "en")
    assert "Paused" in paused_en
    assert "Configured access: Blocked" in paused_en
    assert "Next allowed: 2026-09-07 15:00 (Europe/Kyiv)" in paused_en
    assert "Temporary pause until: 2026-09-07 15:00 (Europe/Kyiv)" in paused_en
