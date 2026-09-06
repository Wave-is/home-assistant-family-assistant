"""Pantry expiry reminder tests using synthetic household state only."""

from copy import deepcopy
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from custom_components.family_assistant.domain import pantry, pantry_expiry
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


def context(state, actor_id, now, operation="expiry-test"):
    return Context(state, state["members"][actor_id], now, operation)


def enabled_state(engine, *, timezone="Europe/Kyiv", days=3):
    state = engine.snapshot()
    state["settings"].update(
        timezone=timezone,
        pantry_expiry_reminders=True,
        pantry_expiry_days=days,
    )
    if "pantry" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("pantry")
    return state


def add_item(state, now, *, name="Milk", quantity=1, expires_on="2026-09-07"):
    return pantry.handle(
        context(state, "parent", now, f"add:{name}"),
        "item_save",
        {
            "name": name,
            "unit": "l",
            "quantity": quantity,
            "minimum_quantity": 0,
            "category": "Food",
            "location": "Fridge",
            "note": "Private parent note",
            "expires_on": expires_on,
        },
    )


def expiry_events(state):
    return [event for event in state["outbox"].values() if event["key"] == "pantry_expiry"]


def local_utc(day, clock, zone="Europe/Kyiv"):
    return datetime.combine(day, clock, tzinfo=ZoneInfo(zone)).astimezone(UTC)


def test_defaults_are_opted_out_and_disabled_tick_is_lazy(engine, now):
    state = engine.snapshot()
    assert state["settings"]["pantry_expiry_reminders"] is False
    assert state["settings"]["pantry_expiry_days"] == 3
    if "pantry" not in state["settings"]["modules"]:
        state["settings"]["modules"].append("pantry")
    add_item(state, now)
    pantry.tick(context(state, "owner", now))
    assert expiry_events(state) == []
    assert "expiry_reminders" not in state["pantry"]


def test_local_date_lead_window_and_nine_oclock_boundary_are_dst_safe(engine, now):
    state = enabled_state(engine, days=0)
    state["settings"]["timezone"] = "Europe/Kyiv"
    item = add_item(state, now, expires_on="2026-10-25")
    before = local_utc(item_date := datetime(2026, 10, 25).date(), time(8, 59))
    at_nine = local_utc(item_date, time(9, 0))
    assert before.astimezone(ZoneInfo("Europe/Kyiv")).strftime("%H:%M") == "08:59"
    assert at_nine.astimezone(ZoneInfo("Europe/Kyiv")).strftime("%H:%M") == "09:00"
    assert (at_nine - before).total_seconds() == 60

    pantry.tick(context(state, "owner", before, "before-nine"))
    assert expiry_events(state) == []
    pantry.tick(context(state, "owner", at_nine, "at-nine"))
    assert len(expiry_events(state)) == 1
    assert expiry_events(state)[0]["data"]["id"] == item["id"]

    state = enabled_state(engine, days=2)
    add_item(state, now, expires_on="2026-09-10")
    pantry.tick(
        context(
            state,
            "owner",
            local_utc(datetime(2026, 9, 7).date(), time(12)),
            "outside-lead",
        )
    )
    assert expiry_events(state) == []
    pantry.tick(
        context(
            state,
            "owner",
            local_utc(datetime(2026, 9, 8).date(), time(9)),
            "inside-lead",
        )
    )
    assert len(expiry_events(state)) == 1


def test_past_dates_are_not_backfilled_after_downtime(engine, now):
    state = enabled_state(engine, days=30)
    add_item(state, now, expires_on="2026-09-06")
    pantry.tick(
        context(
            state,
            "owner",
            local_utc(datetime(2026, 9, 7).date(), time(12)),
            "restart-after-expiry",
        )
    )
    assert expiry_events(state) == []
    assert "expiry_reminders" not in state["pantry"]


def test_notification_is_minimal_deduplicated_and_has_no_other_effects(engine, now):
    state = enabled_state(engine)
    item = add_item(state, now)
    items_before = deepcopy(state["pantry"]["items"])
    shopping_before = deepcopy(state["shopping"])
    first_now = local_utc(datetime(2026, 9, 7).date(), time(9))
    pantry.tick(context(state, "owner", first_now, "first"))
    event = expiry_events(state)[0]
    assert event["recipient"] == "parents"
    assert event["key"] == "pantry_expiry"
    assert event["data"] == {
        "id": item["id"],
        "source_revision": item["revision"],
        "name": "Milk",
        "expires_on": "2026-09-07",
    }
    assert "Private parent note" not in repr(event)
    assert "Fridge" not in repr(event)
    assert state["pantry"]["items"] == items_before
    assert state["shopping"] == shopping_before
    assert state["pantry"]["expiry_reminders"] == {
        item["id"]: {"source_revision": item["revision"], "event_id": event["id"]}
    }

    after_first = deepcopy(state)
    pantry.tick(context(state, "owner", first_now, "second"))
    assert state == after_first


def test_new_item_revision_supersedes_old_intent_and_replaces_bounded_marker(engine, now):
    state = enabled_state(engine)
    item = add_item(state, now)
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "first"))
    old_event = expiry_events(state)[0]
    updated = pantry.handle(
        context(state, "parent", tick_now, "metadata-edit"),
        "item_save",
        {"id": item["id"], "revision": item["revision"], "category": "Dairy"},
    )
    pantry.tick(context(state, "owner", tick_now, "new-revision"))
    events = expiry_events(state)
    assert len(events) == 2
    assert old_event["state"] == "superseded"
    assert events[-1]["data"]["source_revision"] == updated["revision"]
    assert state["pantry"]["expiry_reminders"] == {
        item["id"]: {
            "source_revision": updated["revision"],
            "event_id": events[-1]["id"],
        }
    }


@pytest.mark.parametrize("change", ["disable", "zero", "archive", "remove_expiry"])
def test_revocation_supersedes_unsent_intent_without_creating_replacement(engine, now, change):
    state = enabled_state(engine)
    item = add_item(state, now)
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "first"))
    event = expiry_events(state)[0]

    if change == "disable":
        state["settings"]["pantry_expiry_reminders"] = False
    elif change == "zero":
        pantry.handle(
            context(state, "parent", tick_now, "zero"),
            "stock_set",
            {"id": item["id"], "revision": item["revision"], "quantity": 0, "reason": "Used"},
        )
    elif change == "archive":
        pantry.handle(
            context(state, "parent", tick_now, "archive"),
            "item_archive",
            {"id": item["id"], "revision": item["revision"], "reason": "Removed"},
        )
    else:
        pantry.handle(
            context(state, "parent", tick_now, "remove-expiry"),
            "item_save",
            {"id": item["id"], "revision": item["revision"], "expires_on": None},
        )
    pantry.tick(context(state, "owner", tick_now, f"sweep:{change}"))
    assert event["state"] == "superseded"
    assert len(expiry_events(state)) == 1

    if change == "disable":
        state["settings"]["pantry_expiry_reminders"] = True
        pantry.tick(context(state, "owner", tick_now, "reenable-same-revision"))
        assert len(expiry_events(state)) == 1


def test_pantry_module_disable_and_local_day_cutoff_invalidate_current_event(engine, now):
    state = enabled_state(engine)
    add_item(state, now)
    expiry_day = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", expiry_day, "create"))
    event = expiry_events(state)[0]
    assert pantry_expiry.current_event(state, event)
    assert pantry_expiry.current_event(state, event, expiry_day)
    after = local_utc(datetime(2026, 9, 8).date(), time(0))
    assert not pantry_expiry.current_event(state, event, after)
    pantry.tick(context(state, "owner", after, "expiry-cutoff"))
    assert event["state"] == "superseded"

    state = enabled_state(engine)
    add_item(state, now)
    pantry.tick(context(state, "owner", expiry_day, "create-two"))
    event = expiry_events(state)[0]
    state["settings"]["modules"].remove("pantry")
    pantry.tick(context(state, "owner", expiry_day, "module-off"))
    assert event["state"] == "superseded"
    assert not pantry_expiry.current_event(state, event)


def test_narrowed_lead_window_supersedes_unsent_event_without_repeating_revision(engine, now):
    state = enabled_state(engine, days=3)
    add_item(state, now, expires_on="2026-09-08")
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "create"))
    event = expiry_events(state)[0]
    state["settings"]["pantry_expiry_days"] = 0
    assert pantry_expiry.current_event(state, event)
    assert not pantry_expiry.current_event(state, event, tick_now)
    pantry.tick(context(state, "owner", tick_now, "narrow-window"))
    assert event["state"] == "superseded"

    next_day = local_utc(datetime(2026, 9, 8).date(), time(10))
    pantry.tick(context(state, "owner", next_day, "same-revision"))
    assert len(expiry_events(state)) == 1


@pytest.mark.parametrize("value", [None, True, 1.0, "3", -1, 31])
def test_current_event_rejects_malformed_lead_setting_without_now(engine, now, value):
    state = enabled_state(engine)
    add_item(state, now)
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "create"))
    event = expiry_events(state)[0]
    state["settings"]["pantry_expiry_days"] = value
    assert not pantry_expiry.current_event(state, event)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state, item: state["settings"].update(pantry_expiry_reminders=False),
        lambda state, item: state["settings"]["modules"].remove("pantry"),
        lambda state, item: item.update(status="archived"),
        lambda state, item: item.update(revision=item["revision"] + 1),
        lambda state, item: item.update(expires_on=None),
        lambda state, item: item.update(quantity=0),
        lambda state, item: item.update(name="Changed"),
    ],
)
def test_current_event_rechecks_every_adapter_boundary(engine, now, mutate):
    state = enabled_state(engine)
    item = add_item(state, now)
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "create"))
    event = expiry_events(state)[0]
    mutate(state, item)
    assert not pantry_expiry.current_event(state, event, tick_now)


@pytest.mark.parametrize(
    "mutate_event",
    [
        lambda event: event.update(recipient="child"),
        lambda event: event["data"].update(note="must not be delivered"),
        lambda event: event["data"].update(source_revision=1.0),
    ],
)
def test_current_event_rejects_non_parent_or_nonminimal_intents(engine, now, mutate_event):
    state = enabled_state(engine)
    add_item(state, now)
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "create"))
    event = expiry_events(state)[0]
    mutate_event(event)
    assert not pantry_expiry.current_event(state, event, tick_now)


def test_sweep_never_claims_recall_of_sending_sent_or_uncertain(engine, now):
    state = enabled_state(engine)
    add_item(state, now)
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "create"))
    original = expiry_events(state)[0]
    for status in ("sending", "sent", "uncertain"):
        event = deepcopy(original)
        event["id"] = f"{original['id']}:{status}"
        event["state"] = status
        event["deliveries"] = {
            "delivery": {"id": "delivery", "state": status, "target": {"id": "synthetic"}}
        }
        state["outbox"][event["id"]] = event
    state["settings"]["pantry_expiry_reminders"] = False
    pantry.tick(context(state, "owner", tick_now, "disabled-sweep"))
    by_id = state["outbox"]
    assert by_id[f"{original['id']}:sending"]["state"] == "sending"
    assert by_id[f"{original['id']}:sent"]["state"] == "sent"
    assert by_id[f"{original['id']}:uncertain"]["state"] == "uncertain"


def test_sweep_supersedes_only_pending_deliveries_and_preserves_sent_receipts(engine, now):
    state = enabled_state(engine)
    add_item(state, now)
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(10))
    pantry.tick(context(state, "owner", tick_now, "create"))
    event = expiry_events(state)[0]
    event["deliveries"] = {
        "pending": {"id": "pending", "state": "pending"},
        "sent": {"id": "sent", "state": "sent", "receipt": "synthetic"},
    }
    state["settings"]["pantry_expiry_reminders"] = False
    pantry.tick(context(state, "owner", tick_now, "sweep"))
    assert event["deliveries"]["pending"]["state"] == "superseded"
    assert event["deliveries"]["sent"]["state"] == "sent"
    assert event["deliveries"]["sent"]["receipt"] == "synthetic"
    assert event["state"] == "sent"


@pytest.mark.asyncio
async def test_owner_settings_preserve_optional_values_and_invalid_inputs_are_atomic(
    engine, store, now
):
    base = engine.snapshot()["settings"]
    payload = {
        "name": base["name"],
        "language": base["language"],
        "modules": [*base["modules"], "pantry"],
        "pantry_expiry_reminders": True,
        "pantry_expiry_days": 7,
    }
    result = await engine.execute("owner", "settings.save", payload, "enable-expiry", now)
    assert result["pantry_expiry_reminders"] is True
    assert result["pantry_expiry_days"] == 7

    current = engine.snapshot()["settings"]
    unrelated = {
        "name": "Renamed household",
        "language": current["language"],
        "modules": current["modules"],
    }
    result = await engine.execute("owner", "settings.save", unrelated, "rename", now)
    assert result["pantry_expiry_reminders"] is True
    assert result["pantry_expiry_days"] == 7

    for field, value in (
        ("pantry_expiry_reminders", 1),
        ("pantry_expiry_days", True),
        ("pantry_expiry_days", -1),
        ("pantry_expiry_days", 31),
    ):
        before = engine.snapshot()
        invalid = {**unrelated, field: value}
        with pytest.raises(DomainError, match="invalid_field"):
            await engine.execute("owner", "settings.save", invalid, f"invalid:{field}:{value}", now)
        assert engine.snapshot() == before
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute("parent", "settings.save", unrelated, "parent-settings", now)
    assert store.value == engine.snapshot()


@pytest.mark.asyncio
async def test_tick_store_failure_restart_and_dedup_are_atomic(engine, store, now):
    state = enabled_state(engine, days=0)
    state["settings"]["modules"] = ["pantry"]
    tick_now = local_utc(datetime(2026, 9, 7).date(), time(9))
    add_item(state, tick_now)
    runtime = Engine(state, store.save)
    before = runtime.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await runtime.tick(tick_now)
    assert runtime.snapshot() == before

    store.fail = False
    assert await runtime.tick(tick_now)
    committed = runtime.snapshot()
    assert len(expiry_events(committed)) == 1
    assert len(committed["pantry"]["expiry_reminders"]) == 1

    restarted = Engine(store.value, store.save)
    calls = store.calls
    assert not await restarted.tick(tick_now)
    assert store.calls == calls
    assert restarted.snapshot() == committed
