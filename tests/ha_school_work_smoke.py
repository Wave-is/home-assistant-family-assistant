"""School homework and backpack flows through actual Home Assistant WebSockets."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiohttp import ClientSession
from ha_options_menu import select_option


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/school-work-smoke"
    )
    token = hass.auth.async_create_access_token(refresh)
    session = ClientSession()
    try:
        ws = await session.ws_connect("http://127.0.0.1:8123/api/websocket")
        assert (await ws.receive_json())["type"] == "auth_required"
        await ws.send_json({"type": "auth", "access_token": token})
        assert (await ws.receive_json())["type"] == "auth_ok"
        yield ws
        await ws.close()
    finally:
        await session.close()
        hass.auth.async_remove_refresh_token(refresh)


async def _request(hass, entry, user, identifier, action, payload=None, operation=None):
    async with _socket(hass, user) as ws:
        if action == "view":
            message = {
                "id": identifier,
                "type": "family_assistant/view",
                "entry_id": entry.entry_id,
            }
        else:
            message = {
                "id": identifier,
                "type": "family_assistant/execute",
                "entry_id": entry.entry_id,
                "action": action,
                "payload": payload,
                "operation_id": operation or f"school-work-ha-{identifier}",
            }
        await ws.send_json(message)
        return await ws.receive_json()


async def _general(hass, entry, user, *, school, tasks, routines):
    from custom_components.family_assistant.config_flow import CONFIGURABLE_MODULES

    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    assert flow["type"] == "menu", flow
    form = await select_option(hass, flow, "general")
    if form["type"] == "abort":
        return form
    assert form["type"] == "form" and form["step_id"] == "general", form
    settings = entry.runtime_data.engine.snapshot()["settings"]
    values = {
        "name": settings["name"],
        "language": settings["language"],
        "timezone": settings["timezone"],
        "automatic_penalties": settings.get("automatic_penalties", False),
        "daily_penalty_cap": settings.get("daily_penalty_cap", 1),
        "pantry_expiry_reminders": settings.get("pantry_expiry_reminders", False),
        "pantry_expiry_days": settings.get("pantry_expiry_days", 3),
        **{module: module in settings["modules"] for module in CONFIGURABLE_MODULES},
        "school": school,
        "tasks": tasks,
        "routines": routines,
    }
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    await hass.async_block_till_done()
    return result


def _timetable_payload(record, child_revision, routine):
    return {
        "id": record["id"],
        "revision": record["revision"],
        "member": record["member"],
        "member_revision": child_revision,
        "title": record["title"],
        "valid_from": record["valid_from"],
        "valid_until": record["valid_until"],
        "lessons": deepcopy(record["lessons"]),
        "exceptions": deepcopy(record.get("exceptions", [])),
        "backpack_routine": {"id": routine["id"], "revision": routine["revision"]},
    }


def _routine_payload(child_id):
    return {
        "title": "Synthetic private backpack routine",
        "assignees": [child_id],
        "enabled": True,
        "rule": None,
        "skip_when": None,
        "description": "Synthetic school preparation only",
        "steps": [
            {
                "title": "Pack the synthetic school notebook",
                "confirmation": "manual",
                "offset_minutes": 0,
                "escalate_minutes": None,
                "completion_condition": None,
                "skip_when": None,
            }
        ],
    }


def _occurrence(table, today):
    exceptions = set(table.get("exceptions", []))
    valid_from = datetime.fromisoformat(table["valid_from"]).date()
    valid_until = (
        None
        if table.get("valid_until") is None
        else datetime.fromisoformat(table["valid_until"]).date()
    )
    for offset in range(2):
        day = today + timedelta(days=offset)
        if day < valid_from or valid_until is not None and day > valid_until:
            continue
        if day.isoformat() in exceptions:
            continue
        for index, lesson in enumerate(table["lessons"]):
            if lesson["weekday"] == day.weekday():
                return day, index
    raise AssertionError("active timetable has no today/tomorrow occurrence")


async def verify_school_work(hass, entry, owner, child_id):
    """Verify private homework reuse and explicitly reviewed backpack starts."""
    from homeassistant.core import Context
    from homeassistant.helpers import llm

    from custom_components.family_assistant.llm_api import FamilyAPI
    from custom_components.family_assistant.runtime import safe_diagnostics

    engine = entry.runtime_data.engine
    initial = engine.snapshot()
    member_ids = set(initial["members"])
    child_record = initial["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None
    parent_record = next(
        member
        for member in initial["members"].values()
        if member["role"] == "parent" and member.get("ha_user_id")
    )
    parent = await hass.auth.async_get_user(parent_record["ha_user_id"])
    assert parent is not None
    adult_record = next(
        (
            member
            for member in initial["members"].values()
            if member["role"] == "adult" and member.get("ha_user_id")
        ),
        None,
    )
    adult = (
        None if adult_record is None else await hass.auth.async_get_user(adult_record["ha_user_id"])
    )

    denied = await _general(hass, entry, child, school=True, tasks=True, routines=True)
    assert denied["type"] == "abort" and denied["reason"] == "forbidden"
    enabled = await _general(hass, entry, owner, school=True, tasks=True, routines=True)
    assert enabled["type"] == "create_entry", enabled

    sequence = 500

    async def command(user, action, payload, *, operation=None, error=None):
        nonlocal sequence
        sequence += 1
        response = await _request(hass, entry, user, sequence, action, payload, operation)
        if error is not None:
            assert not response["success"] and response["error"]["code"] == error, response
            return None
        assert response["success"], response
        return response["result"]

    snapshot = engine.snapshot()
    child_record = snapshot["members"][child_id]
    table = next(
        record
        for record in snapshot["school"]["timetables"].values()
        if record["status"] == "active" and record["member"] == child_id
    )
    # Create a known-current private fixture instead of relying on a routine left
    # by an earlier smoke helper whose creator or assignee epoch may have changed.
    routine = await command(parent, "routines.save", _routine_payload(child_id))

    linked = await command(
        parent,
        "school.timetable_save",
        _timetable_payload(table, child_record["revision"], routine),
        operation="school-work-link-routine",
    )
    assert linked["id"] == table["id"] and linked["revision"] > table["revision"]
    table = engine.snapshot()["school"]["timetables"][linked["id"]]
    zone = ZoneInfo(engine.snapshot()["settings"]["timezone"])
    today = datetime.now(UTC).astimezone(zone).date()
    lesson_day, lesson_index = _occurrence(table, today)
    lesson = {
        "timetable_id": table["id"],
        "timetable_revision": table["revision"],
        "date": lesson_day.isoformat(),
        "lesson_index": lesson_index,
    }

    child_title = "SYNTHETIC_PRIVATE_CHILD_HOMEWORK"
    parent_title = "SYNTHETIC_PRIVATE_PARENT_HOMEWORK"
    revised_title = "SYNTHETIC_PRIVATE_REVISED_HOMEWORK"
    checklist_canary = "SYNTHETIC_PRIVATE_HOMEWORK_CHECKLIST"
    child_payload = {
        "member": child_id,
        "member_revision": child_record["revision"],
        "title": child_title,
        "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "checklist": [checklist_canary],
        "reminder_minutes": 45,
        "grace_minutes": 20,
        "lesson": lesson,
    }
    before_stale = engine.snapshot()
    await command(
        child,
        "school.homework_create",
        {**child_payload, "member_revision": child_record["revision"] - 1},
        error="conflict",
    )
    await command(
        child,
        "school.homework_create",
        {
            **child_payload,
            "lesson": {**lesson, "timetable_revision": table["revision"] - 1},
        },
        error="conflict",
    )
    assert engine.snapshot() == before_stale
    child_homework = await command(
        child,
        "school.homework_create",
        child_payload,
        operation="school-work-child-homework",
    )
    assert set(child_homework) == {"id", "revision", "status"}
    assert (
        await command(
            child,
            "school.homework_create",
            child_payload,
            operation="school-work-child-homework",
        )
        == child_homework
    )

    parent_payload = {
        **child_payload,
        "title": parent_title,
        "lesson": None,
    }
    parent_homework = await command(
        parent,
        "school.homework_create",
        parent_payload,
        operation="school-work-parent-homework",
    )
    if adult is not None:
        before = engine.snapshot()
        await command(
            adult,
            "school.homework_create",
            {**parent_payload, "title": "Forbidden adult homework"},
            error="forbidden",
        )
        assert engine.snapshot() == before
        adult_view = await _request(hass, entry, adult, 699, "view")
        assert adult_view["success"] and "school" not in adult_view["result"]
        assert not any(
            title in str(adult_view) for title in (child_title, parent_title, checklist_canary)
        )

    stored = engine.snapshot()["tasks"][child_homework["id"]]
    assert stored["delivery_scope"] == "private"
    assert stored["source"] == {
        "kind": "school_homework",
        "member": child_id,
        "member_revision": child_record["revision"],
        "lesson": lesson,
    }
    assert stored["deadline_policy"]["penalty"] == 0
    revise_payload = {
        "id": stored["id"],
        "revision": stored["revision"],
        "member_revision": child_record["revision"],
        "title": revised_title,
        "due_at": stored["due_at"],
        "reminder_minutes": 15,
        "grace_minutes": 5,
    }
    await command(
        child,
        "school.homework_revise",
        revise_payload,
        error="forbidden",
    )
    await command(
        child,
        "tasks.revise",
        {
            "id": stored["id"],
            "revision": stored["revision"],
            "title": "Bypass",
            "due_at": stored["due_at"],
            "assignee": child_id,
            "penalty": 0,
            "reminder_minutes": 15,
            "grace_minutes": 5,
        },
        error="forbidden",
    )
    revised = await command(
        parent,
        "school.homework_revise",
        revise_payload,
        operation="school-work-parent-revise",
    )
    assert set(revised) == {"id", "revision", "status"}
    assert revised["revision"] > stored["revision"]
    assert engine.snapshot()["tasks"][revised["id"]]["checklist"] == [
        {"text": checklist_canary, "done": False}
    ]

    # One failing command rolls back the earlier valid command in a real batch.
    before_batch = engine.snapshot()
    batch = {
        "commands": [
            {
                "action": "school.homework_create",
                "payload": {**parent_payload, "title": "Rolled back homework"},
            },
            {
                "action": "school.homework_create",
                "payload": {**parent_payload, "member_revision": 0},
            },
        ]
    }
    await command(parent, "batch", batch, error="invalid_field")
    assert engine.snapshot() == before_batch

    parent_view = await _request(hass, entry, parent, 700, "view")
    child_view = await _request(hass, entry, child, 701, "view")
    assert parent_view["success"] and child_view["success"]
    parent_rows = parent_view["result"]["school"]["homework"]
    child_rows = child_view["result"]["school"]["homework"]
    parent_row = next(row for row in parent_rows if row["id"] == revised["id"])
    child_row = next(row for row in child_rows if row["id"] == revised["id"])
    assert parent_row["managed_by"] == "school"
    assert parent_row["source"]["kind"] == "school_homework"
    assert child_row["managed_by"] == "school"
    assert "source" not in child_row and "previous_reports" not in child_row
    assert all(row["assignee"] == child_id for row in child_rows)

    context = llm.LLMContext(
        platform="conversation",
        context=Context(user_id=owner.id),
        language="en",
        assistant="conversation",
        device_id=None,
    )
    api = await FamilyAPI(hass, entry).async_get_api_instance(context)
    family = await api.async_call_tool(llm.ToolInput(tool_name="ReadFamily", tool_args={}))
    canaries = (child_title, parent_title, revised_title, checklist_canary)
    for canary in canaries:
        assert canary not in str(family)
        assert canary not in str(safe_diagnostics(entry.runtime_data))
        assert canary not in str([state.as_dict() for state in hass.states.async_all()])
        assert canary not in str(engine.snapshot()["audit"])
        assert canary not in str(engine.snapshot()["processed"])

    # Task notifications carry only private member stamps, never homework text.
    homework_ids = {child_homework["id"], parent_homework["id"]}
    notices = [
        event
        for event in engine.snapshot()["outbox"].values()
        if event.get("data", {}).get("id") in homework_ids
    ]
    assert notices
    assert all(event["recipient"] in {child_id, "parents"} for event in notices)
    assert all(not any(canary in str(event) for canary in canaries) for event in notices)

    run_ids = set(engine.snapshot()["routine_runs"])
    preparation_payload = {
        "timetable_id": table["id"],
        "timetable_revision": table["revision"],
        "member": child_id,
        "member_revision": child_record["revision"],
        "date": lesson_day.isoformat(),
        "routine_id": routine["id"],
        "routine_revision": routine["revision"],
    }
    before_bad_pin = engine.snapshot()
    await command(
        child,
        "school.backpack_start",
        {**preparation_payload, "routine_revision": routine["revision"] - 1},
        error="invalid_field",
    )
    assert engine.snapshot() == before_bad_pin
    preparation = await command(
        child,
        "school.backpack_start",
        preparation_payload,
        operation="school-work-backpack-start",
    )
    assert set(preparation) == {"id", "revision", "status", "run_id"}
    assert preparation["status"] == "started"
    assert set(engine.snapshot()["routine_runs"]) == {*run_ids, preparation["run_id"]}
    assert (
        await command(
            child,
            "school.backpack_start",
            preparation_payload,
            operation="school-work-backpack-start",
        )
        == preparation
    )
    before_duplicate = engine.snapshot()
    await command(
        parent,
        "school.backpack_start",
        preparation_payload,
        error="invalid_transition",
    )
    assert engine.snapshot() == before_duplicate

    tasks_disabled = await _general(hass, entry, owner, school=True, tasks=False, routines=True)
    assert tasks_disabled["type"] == "create_entry", tasks_disabled
    tasks_hidden = await _request(hass, entry, child, 702, "view")
    assert tasks_hidden["success"]
    assert tasks_hidden["result"]["school"]["homework"] == []
    assert tasks_hidden["result"]["school"]["preparations"]
    await command(
        child,
        "school.homework_create",
        child_payload,
        operation="school-work-child-homework",
        error="module_disabled",
    )
    assert (
        await command(
            child,
            "school.backpack_start",
            preparation_payload,
            operation="school-work-backpack-start",
        )
        == preparation
    )
    tasks_restored = await _general(hass, entry, owner, school=True, tasks=True, routines=True)
    assert tasks_restored["type"] == "create_entry", tasks_restored

    routines_disabled = await _general(hass, entry, owner, school=True, tasks=True, routines=False)
    assert routines_disabled["type"] == "create_entry", routines_disabled
    await command(
        child,
        "school.backpack_start",
        preparation_payload,
        operation="school-work-backpack-start",
        error="module_disabled",
    )
    assert (
        await command(
            child,
            "school.homework_create",
            child_payload,
            operation="school-work-child-homework",
        )
        == child_homework
    )
    routines_restored = await _general(hass, entry, owner, school=True, tasks=True, routines=True)
    assert routines_restored["type"] == "create_entry", routines_restored

    disabled = await _general(hass, entry, owner, school=False, tasks=True, routines=True)
    assert disabled["type"] == "create_entry", disabled
    hidden = await _request(hass, entry, child, 703, "view")
    assert hidden["success"] and "school" not in hidden["result"]
    await command(
        child,
        "school.homework_create",
        child_payload,
        operation="school-work-child-homework",
        error="module_disabled",
    )
    await command(
        child,
        "school.backpack_start",
        preparation_payload,
        operation="school-work-backpack-start",
        error="module_disabled",
    )
    restored = await _general(hass, entry, owner, school=True, tasks=True, routines=True)
    assert restored["type"] == "create_entry", restored

    # Disabling Routines deliberately cancels active runs. Establish a fresh,
    # explicitly requested ordinary run to exercise nonce persistence on reload;
    # the original school-date preparation marker must still prevent a duplicate.
    reload_run = await command(
        child,
        "routines.start",
        {"id": routine["id"], "revision": routine["revision"], "member": child_id},
        operation="school-work-reload-routine",
    )
    assert reload_run["status"] == "active"
    await command(parent, "school.backpack_start", preparation_payload, error="invalid_transition")
    final = engine.snapshot()
    assert set(final["members"]) == member_ids
    assert final["members"][child_id]["role"] == "child"
    assert final["tasks"][revised["id"]]["title"] == revised_title
    assert final["school"]["preparations"][preparation["id"]]["run_id"] == preparation["run_id"]
    print(
        "PASS: actual HA private school homework, guarded task reuse, backpack "
        "review, replay and module revocation"
    )
    return {
        "timetable_id": table["id"],
        "child_homework_id": revised["id"],
        "parent_homework_id": parent_homework["id"],
        "preparation_id": preparation["id"],
        "run_id": preparation["run_id"],
    }
