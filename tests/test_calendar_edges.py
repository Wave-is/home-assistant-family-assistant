"""Privacy at chat boundaries, strict input and obsolete preparation delivery."""

from datetime import UTC, datetime, timedelta

import pytest
from test_family_calendar import enable_calendar
from test_notifications import Transport

from custom_components.family_assistant.domain.family_calendar import published
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import Notifications
from custom_components.family_assistant.telegram.messages import render
from custom_components.family_assistant.telegram.router import route


async def event(engine, now, **extra):
    return await engine.execute(
        "parent",
        "calendar.save",
        {
            "title": "Synthetic private appointment",
            "start": "2026-09-06T09:00:00Z",
            "end": "2026-09-06T10:00:00Z",
            "participants": ["child"],
            "visibility": "participants",
            "reminder_minutes": [15],
            **extra,
        },
        "appointment",
        now,
    )


@pytest.mark.asyncio
async def test_standard_calendar_uses_ha_zone_for_all_day_overlap(engine, now):
    await enable_calendar(engine, now)
    await event(
        engine, now, all_day=True, start="2026-09-07", end="2026-09-08", visibility="family"
    )
    await engine.execute(
        "owner",
        "calendar.configure",
        {
            "revision": 0,
            "publish_to_ha": True,
            "confirm_public_visibility": True,
        },
        "publish",
        now,
    )
    state = engine.snapshot()
    state["settings"]["timezone"] = "Europe/Kyiv"
    midnight = datetime(2026, 9, 7, tzinfo=UTC)
    assert not published(state, midnight - timedelta(hours=1), midnight, "UTC")
    assert len(published(state, midnight - timedelta(hours=1), midnight, "Europe/Kyiv")) == 1


@pytest.mark.asyncio
async def test_private_calendar_is_not_leaked_by_parent_group_read_cancel_or_replay(engine, now):
    await enable_calendar(engine, now)
    record = await event(engine, now)
    assert "Synthetic private" not in await route(engine, "parent", "/calendar", "list", now)
    assert "Synthetic private" in await route(
        engine, "parent", "/calendar", "pm-list", now, private=True
    )
    assert "Synthetic private" not in await route(
        engine, "sibling", "/calendar", "sibling-list", now, private=True
    )
    command = f"/eventcancel {record['id']} | Synthetic cancellation"
    for _ in range(2):
        response = await route(engine, "parent", command, "cancel", now)
        assert "Synthetic private" not in response and record["id"] in response
    assert engine.snapshot()["calendar"][record["id"]]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_typed_event_child_proposal_approval_and_private_reply(engine, now):
    await enable_calendar(engine, now)
    command = "/event Synthetic trip | 2026-09-06T12:00+03:00 | 2026-09-06T13:00+03:00"
    response = await route(engine, "child", command, "create", now)
    assert "awaiting parent approval" in response
    assert await route(engine, "child", command, "create", now) == response
    record = next(iter(engine.snapshot()["calendar"].values()))
    assert "Synthetic trip" not in await route(engine, "parent", "/calendar", "read", now)
    await route(
        engine, "owner", f"/eventapprove {record['id']} | Synthetic approval", "approve", now
    )
    assert "Synthetic trip" in await route(engine, "parent", "/calendar", "read-again", now)


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "ru", "uk"])
async def test_reminder_render_and_expiry_before_channel_reconnect(engine, now, language):
    await enable_calendar(engine, now)
    await event(
        engine,
        now,
        preparation=["Synthetic notebook"],
        location="Synthetic room",
        timezone="Europe/Kyiv",
    )
    await engine.tick(now + timedelta(minutes=45))
    notice = next(iter(engine.snapshot()["outbox"].values()))
    message = render(notice, {"id": 12345, "language": language}, engine.snapshot())
    assert "12:00" in message["text"] and "Europe/Kyiv" in message["text"]
    assert "☐ Synthetic notebook" in message["text"] and "Synthetic private" in message["text"]
    transport = Transport()
    outbox = Notifications(
        engine, {"telegram": transport}, lambda *_: [{"channel": "telegram", "id": 12345}]
    )
    await outbox.run(now + timedelta(hours=1))
    assert not transport.calls
    assert next(iter(engine.snapshot()["outbox"].values()))["state"] == "superseded"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"participants": []},
        {"participants": ["child", "child"]},
        {"participants": [False]},
        {"escort": "child"},
        {"escort": False},
        {"all_day": 1},
        {"all_day": True},
        {"preparation": [""]},
        {"preparation": "text"},
        {"preparation": ["x"] * 31},
        {"reminder_minutes": [True]},
        {"reminder_minutes": [15.0]},
        {"reminder_minutes": [10081]},
        {"reminder_minutes": list(range(7))},
        {"visibility": "public"},
        {"timezone": "invalid"},
        {"description": None},
        {"status": "confirmed"},
        {"task_ids": [False]},
    ],
)
async def test_strict_calendar_payload_is_atomic(engine, now, extra):
    await enable_calendar(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError):
        await event(engine, now, **extra)
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("until", [False, 0, [], "", "2026-W37-1"])
async def test_invalid_recurrence_end_is_not_silently_treated_as_forever(engine, now, until):
    await enable_calendar(engine, now)
    with pytest.raises(DomainError):
        await event(
            engine,
            now,
            rule={
                "frequency": "daily",
                "start_date": "2026-09-06",
                "time": "09:00",
                "timezone": "UTC",
                "until": until,
            },
        )
