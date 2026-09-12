"""Legacy user workflows restored through canonical public-domain APIs."""

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.context import PersonalReply
from custom_components.family_assistant.telegram.router import route


async def test_task_lifecycle_legacy_commands_keep_current_roles(engine, now):
    await route(engine, "parent", "/task Child | Clean desk", "create", now)
    await route(engine, "child", "/принять T000001", "accept", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "accepted"
    await route(engine, "child", "/begin T000001", "begin", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "in_progress"
    await route(engine, "child", "/готово T000001 Wiped desk", "submit", now)
    assert engine.snapshot()["tasks"]["T000001"]["report"] == "Wiped desk"
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/подтвердить T000001", "child-approve", now)
    await route(engine, "parent", "/переделать T000001 | Clean underneath", "changes", now)
    await route(engine, "child", "/done T000001 | Finished underneath", "resubmit", now)
    await route(engine, "parent", "/подтвердить T000001", "approve", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "completed"
    await route(engine, "parent", "/archive T000001", "archive", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "archived"
    assert engine.snapshot()["tasks"]["T000001"]["report"] == "Finished underneath"


async def test_edit_and_archive_use_current_revision_without_aliasing_people(engine, now):
    await route(engine, "parent", "/завдання Child | Water plants", "create", now)
    await route(engine, "parent", "/edit T000001 срок завтра", "deadline", now)
    assert engine.snapshot()["tasks"]["T000001"]["due_at"].startswith("2026-09-07")
    await route(engine, "parent", "/edit T000001 исполнитель Sibling", "assign", now)
    assert engine.snapshot()["tasks"]["T000001"]["assignee"] == "sibling"
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "sibling", "/archive T000001", "child-archive", now)
    await route(engine, "parent", "/отменитьзадачу T000001", "cancel", now)
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "cancelled"


async def test_purchase_approval_name_resolution_and_legacy_partial_quantity(engine, now):
    await route(engine, "child", "добавь молоко в покупки", "suggest", now)
    assert engine.snapshot()["shopping"]["S000001"]["status"] == "pending"
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/approvebuy S000001", "child-approve", now)
    await route(engine, "parent", "/approvebuy S000001", "approve", now)
    await route(engine, "parent", "купил молоко", "bought", now)
    assert engine.snapshot()["shopping"]["S000001"]["status"] == "purchased"
    await route(engine, "parent", "/buy Tea | 5 | bags", "tea", now)
    await route(engine, "parent", "/bought S000002 2", "partial", now)
    assert engine.snapshot()["shopping"]["S000002"]["purchased"] == 2
    await route(engine, "child", "/buy sweets", "sweets", now)
    await route(engine, "parent", "/rejectbuy S000003", "reject", now)
    assert engine.snapshot()["shopping"]["S000003"]["status"] == "rejected"


async def test_duplicate_name_cannot_close_arbitrary_purchase(engine, now):
    for number in range(2):
        await route(engine, "parent", "/buy Tea", f"tea-{number}", now)
    with pytest.raises(DomainError, match="ambiguous_command"):
        await route(engine, "parent", "bought Tea", "ambiguous", now)
    assert all(row["purchased"] == 0 for row in engine.snapshot()["shopping"].values())


async def test_personal_reminder_and_mine_do_not_expose_other_members(engine, now):
    await route(engine, "parent", "/task Child | Child task", "child-task", now)
    response = await route(
        engine, "parent", "напомни мне позвонить завтра в 18:00", "remind", now, private=True
    )
    assert isinstance(response, PersonalReply)
    reminder = engine.snapshot()["tasks"]["T000002"]
    assert reminder["delivery_scope"] == "personal" and reminder["assignee"] == "parent"
    assert reminder["deadline_policy"]["penalty"] == 0
    assert "позвонить" in await route(engine, "parent", "/mine", "mine", now, private=True)
    assert "Child task" not in await route(engine, "parent", "мои задачи", "my-tasks", now)
    assert "позвонить" not in await route(
        engine, "parent", "/mine", "group-mine", now, private=False
    )
    assert "позвонить" not in await route(engine, "adult", "/tasks", "adult-tasks", now)


async def test_ask_routes_only_explicit_payload_and_help_never_needs_model(engine, now):
    calls = []

    async def fallback(actor, content, operation_id, at, refs):
        calls.append((actor, content, operation_id, at, refs))
        return "Synthetic answer"

    assert (
        await route(engine, "parent", "/ask Explain rain", "ask", now, fallback=fallback)
        == "Synthetic answer"
    )
    assert calls[0][1] == "Explain rain"
    for command in ("/commands", "/команды", "/помощник"):
        assert "/accept" in await route(engine, "parent", command, command, now, fallback=fallback)
    assert len(calls) == 1


async def test_reply_done_uses_one_receipt_target(engine, now):
    await route(engine, "parent", "/task Child | Read chapter", "create", now)
    await route(engine, "child", "готово", "submit", now, refs=["T000001"])
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "submitted"
    await route(engine, "parent", "готово", "approve", now, refs=["T000001"])
    assert engine.snapshot()["tasks"]["T000001"]["status"] == "completed"


async def test_alarm_two_groups_create_update_toggle_and_replay_without_model(engine, now):
    command = "поставь Child будильник на будни на 07:00 и на выходные на 09:30"
    reply = await route(engine, "parent", command, "alarms", now)
    rows = list(engine.snapshot()["alarms"].values())
    assert [(row["days"], row["time"]) for row in rows] == [
        (list(range(5)), "07:00"),
        ([5, 6], "09:30"),
    ]
    assert all(row["penalty"] == 0 for row in rows)
    assert await route(engine, "parent", command, "alarms", now) == reply
    assert len(engine.snapshot()["alarms"]) == 2
    await route(engine, "parent", "выключи будильник Child на выходные", "off", now)
    assert engine.snapshot()["alarms"]["A000002"]["enabled"] is False
    await route(engine, "parent", "/alarm Child | weekends | on", "on", now)
    await route(engine, "parent", "/alarm Child | weekdays | 08:15", "update-time", now)
    assert engine.snapshot()["alarms"]["A000001"]["time"] == "08:15"
    assert len(engine.snapshot()["alarms"]) == 2


@pytest.mark.parametrize(
    "phrase",
    [
        "встанови Child будильник у будні о 07:15",
        "set alarm Child on weekdays at 07:15",
        "set Child alarm on weekdays at 07:15",
    ],
)
async def test_alarm_supported_languages(phrase, engine, now):
    await route(engine, "parent", phrase, "set", now)
    row = next(iter(engine.snapshot()["alarms"].values()))
    assert row["member"] == "child" and row["days"] == list(range(5)) and row["time"] == "07:15"


@pytest.mark.parametrize(
    "phrase",
    [
        "поставь Child будильник на будни на 24:30",
        "поставь Child будильник на будни на 07:00 и на будни на 08:00",
        "поставь Child будильник на будни на 07:00 и выходные когда удобно",
        "поставь Unknown будильник на будни на 07:00",
        "поставь Child будильник на 07:00",
    ],
)
async def test_bad_alarm_never_creates_partial_schedule(phrase, engine, now):
    with pytest.raises(DomainError):
        await route(engine, "parent", phrase, "bad", now)
    assert not engine.snapshot()["alarms"]


async def test_children_cannot_change_alarm_schedule(engine, now):
    with pytest.raises(DomainError, match="forbidden"):
        await route(engine, "child", "/alarm Child | weekdays | 07:00", "child-alarm", now)
    assert not engine.snapshot()["alarms"]


@pytest.mark.parametrize("language", ["en", "ru", "uk"])
async def test_help_catalog_fits_one_telegram_message(engine, now, language):
    await engine.system_update(
        "language", now, lambda ctx: ctx.state["members"]["parent"].update(language=language)
    )
    reply = await route(engine, "parent", "/commands", "help", now)
    assert len(reply) <= 4000
    assert "/alarm" in reply and "/ask" in reply


def test_court_thresholds_report_only_configured_names_and_labels():
    from custom_components.family_assistant.telegram.presentation import threshold_lines

    report = {
        "thresholds": [
            {"member": "child", "label": "Optional family rule", "reached": False, "remaining": 2}
        ]
    }
    assert threshold_lines(report, [{"id": "child", "name": "Child"}], "en") == [
        "Current period thresholds",
        "Child · Optional family rule: remaining: 2",
    ]
    assert not threshold_lines(report, [{"id": "sibling", "name": "Sibling"}], "en")
