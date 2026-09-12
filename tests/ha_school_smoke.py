"""School timetables through actual Home Assistant options and WebSockets."""

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
        user, client_id="https://example.invalid/school-smoke"
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
                "operation_id": operation or f"school-ha-{identifier}",
            }
        await ws.send_json(message)
        return await ws.receive_json()


async def _general(hass, entry, user, *, school):
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
    }
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    await hass.async_block_till_done()
    return result


def _side_effects(engine):
    snapshot = engine.snapshot()
    return {
        key: deepcopy(snapshot[key])
        for key in (
            "tasks",
            "task_series",
            "outbox",
            "court",
            "rewards",
            "routine_runs",
            "alarm_outputs",
        )
    }


async def verify_school(hass, entry, owner, child_id):
    """Verify current-child timetable authority, privacy, replay and persistence."""
    from homeassistant.core import Context
    from homeassistant.helpers import llm

    from custom_components.family_assistant.llm_api import FamilyAPI
    from custom_components.family_assistant.runtime import safe_diagnostics

    engine = entry.runtime_data.engine
    child_record = engine.snapshot()["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None
    parent_record = next(
        member
        for member in engine.snapshot()["members"].values()
        if member["role"] == "parent" and member.get("ha_user_id")
    )
    parent = await hass.auth.async_get_user(parent_record["ha_user_id"])
    assert parent is not None
    original_modules = list(engine.snapshot()["settings"]["modules"])

    denied_options = await _general(hass, entry, child, school=True)
    assert denied_options["type"] == "abort" and denied_options["reason"] == "forbidden"
    enabled = await _general(hass, entry, owner, school=True)
    assert enabled["type"] == "create_entry", enabled
    enabled_modules = engine.snapshot()["settings"]["modules"]
    assert "school" in enabled_modules
    assert set(enabled_modules) == {*original_modules, "school"}

    zone = ZoneInfo(engine.snapshot()["settings"]["timezone"])
    today = datetime.now(UTC).astimezone(zone).date()
    tomorrow = today + timedelta(days=1)
    private_title = "SYNTHETIC_PRIVATE_SCHOOL_TIMETABLE"
    private_subject = "SYNTHETIC_PRIVATE_SCHOOL_SUBJECT"
    private_material = "SYNTHETIC_PRIVATE_SCHOOL_MATERIAL"
    canaries = (private_title, private_subject, private_material)
    lessons = [
        {
            "weekday": today.weekday(),
            "start": "08:30",
            "end": "09:15",
            "subject": private_subject,
            "room": "Synthetic room",
            "materials": [private_material, "Notebook"],
        },
        {
            "weekday": tomorrow.weekday(),
            "start": "10:00",
            "end": "10:45",
            "subject": "Synthetic excluded lesson",
            "room": "",
            "materials": [],
        },
    ]
    payload = {
        "member": child_id,
        "member_revision": child_record["revision"],
        "title": private_title,
        "valid_from": today.isoformat(),
        "valid_until": (today + timedelta(days=28)).isoformat(),
        "lessons": lessons,
        "backpack_routine": None,
        "exceptions": [tomorrow.isoformat()],
    }

    sequence = 100

    async def school(action, command, *, operation=None, error=None):
        nonlocal sequence
        sequence += 1
        before = _side_effects(engine)
        response = await _request(
            hass,
            entry,
            parent,
            sequence,
            action,
            command,
            operation,
        )
        assert _side_effects(engine) == before
        if error is not None:
            assert not response["success"] and response["error"]["code"] == error, response
            return None
        assert response["success"], response
        return response["result"]

    created = await school("school.timetable_save", payload, operation="school-ha-create")
    assert set(created) == {"id", "revision", "status"}
    assert created["status"] == "active"
    assert await school("school.timetable_save", payload, operation="school-ha-create") == created
    before_child_denials = engine.snapshot()
    child_save = await _request(
        hass,
        entry,
        child,
        201,
        "school.timetable_save",
        payload,
        "school-child-forbidden",
    )
    assert not child_save["success"] and child_save["error"]["code"] == "forbidden"
    child_denial = await _request(
        hass,
        entry,
        child,
        202,
        "school.timetable_archive",
        {"id": created["id"], "revision": created["revision"], "reason": "No"},
        "school-child-archive-forbidden",
    )
    assert not child_denial["success"] and child_denial["error"]["code"] == "forbidden"
    assert engine.snapshot() == before_child_denials

    owner_view = await _request(hass, entry, owner, 203, "view")
    assert owner_view["success"]
    projected = owner_view["result"]["school"]
    assert projected["timetables"][0]["history"][0]["action"] == "created"
    assert private_subject in str(projected)
    assert tomorrow.isoformat() not in {row["date"] for row in projected["upcoming"]}
    assert any(row["subject"] == private_subject for row in projected["upcoming"])
    child_view = await _request(hass, entry, child, 204, "view")
    own = child_view["result"]["school"]["timetables"]
    assert len(own) == 1 and own[0]["id"] == created["id"]
    assert not {"history", "created_by"} & own[0].keys()

    # The real assistant projection, diagnostics and HA entities do not inherit
    # subjects, materials or other student-private timetable text.
    context = llm.LLMContext(
        platform="conversation",
        context=Context(user_id=owner.id),
        language="en",
        assistant="conversation",
        device_id=None,
    )
    api = await FamilyAPI(hass, entry).async_get_api_instance(context)
    family = await api.async_call_tool(llm.ToolInput(tool_name="ReadFamily", tool_args={}))
    for canary in canaries:
        assert canary not in str(family)
        assert canary not in str(safe_diagnostics(entry.runtime_data))
        assert canary not in str([state.as_dict() for state in hass.states.async_all()])
        assert canary not in str(engine.snapshot()["audit"])
        assert canary not in str(engine.snapshot()["processed"])

    # Existing non-child household members and an unlinked HA identity receive no data.
    adult_member = next(
        (
            member
            for member in engine.snapshot()["members"].values()
            if member["role"] == "adult" and member.get("ha_user_id")
        ),
        None,
    )
    if adult_member is not None:
        adult = await hass.auth.async_get_user(adult_member["ha_user_id"])
        adult_view = await _request(hass, entry, adult, 205, "view")
        assert adult_view["success"]
        assert not any(canary in str(adult_view) for canary in canaries)
        assert adult_view["result"].get("school", {"timetables": []})["timetables"] == []
    users = await hass.auth.async_get_users()
    stranger = next((user for user in users if user.name == "Synthetic unlinked HA user"), None)
    if stranger is not None:
        stranger_view = await _request(hass, entry, stranger, 206, "view")
        assert not stranger_view["success"]
        assert not any(canary in str(stranger_view) for canary in canaries)

    # A current member epoch is mandatory. Re-save with the new epoch and a pinned
    # existing routine link; School must not start or alter that routine.
    current_child = engine.snapshot()["members"][child_id]
    revised_child = await engine.execute(
        "owner",
        "members.save",
        {
            "id": child_id,
            "revision": current_child["revision"],
            "name": current_child["name"],
            "role": "child",
        },
        "school-member-epoch",
        datetime.now(UTC),
    )
    stale_edit = {
        **payload,
        "id": created["id"],
        "revision": created["revision"],
        "title": "Stale school edit",
    }
    await school("school.timetable_save", stale_edit, error="conflict")
    routine = next(
        (
            record
            for record in engine.snapshot()["routines"].values()
            if record.get("enabled") and child_id in record.get("assignees", [])
        ),
        None,
    )
    link = {"id": routine["id"], "revision": routine["revision"]} if routine else None
    replacement = {
        **stale_edit,
        "member_revision": revised_child["revision"],
        "title": private_title + " REVISED",
        "backpack_routine": link,
    }
    replacement.pop("exceptions")
    revised = await school("school.timetable_save", replacement)
    assert revised["revision"] > created["revision"]
    revised_view = (await _request(hass, entry, child, 207, "view"))["result"]["school"]
    assert revised_view["timetables"][0]["exceptions"] == []
    if routine is not None:
        assert revised_view["timetables"][0]["backpack_routine"] == {
            "id": routine["id"],
            "revision": routine["revision"],
            "title": routine["title"],
        }

    # A former child's record can be archived but cannot be edited as a timetable.
    current_child = engine.snapshot()["members"][child_id]
    former = await engine.execute(
        "owner",
        "members.save",
        {
            "id": child_id,
            "revision": current_child["revision"],
            "name": current_child["name"],
            "role": "adult",
        },
        "school-child-role-revoke",
        datetime.now(UTC),
    )
    invalid_former = {
        **replacement,
        "revision": revised["revision"],
        "member_revision": former["revision"],
    }
    await school("school.timetable_save", invalid_former, error="unknown_member")
    former_view = await _request(hass, entry, child, 208, "view")
    assert former_view["success"]
    assert former_view["result"].get("school", {"timetables": []})["timetables"] == []
    archive_payload = {
        "id": created["id"],
        "revision": revised["revision"],
        "reason": "Synthetic term completed",
    }
    archived = await school(
        "school.timetable_archive", archive_payload, operation="school-ha-archive"
    )
    assert archived["status"] == "archived"
    assert (
        await school("school.timetable_archive", archive_payload, operation="school-ha-archive")
        == archived
    )
    archived_view = (await _request(hass, entry, owner, 209, "view"))["result"]["school"]
    archived_row = next(row for row in archived_view["timetables"] if row["id"] == created["id"])
    assert archived_row["history"][-1] == {
        "actor": parent_record["id"],
        "at": archived_row["archived_at"],
        "action": "archived",
        "reason": "Synthetic term completed",
    }

    restored = await engine.execute(
        "owner",
        "members.save",
        {
            "id": child_id,
            "revision": former["revision"],
            "name": child_record["name"],
            "role": "child",
        },
        "school-child-role-restore",
        datetime.now(UTC),
    )
    active_payload = {
        **payload,
        "member_revision": restored["revision"],
        "title": private_title + " ACTIVE",
    }
    active = await school(
        "school.timetable_save", active_payload, operation="school-ha-active-create"
    )
    assert active["id"] != archived["id"] and active["status"] == "active"

    disabled = await _general(hass, entry, owner, school=False)
    assert disabled["type"] == "create_entry", disabled
    assert "school" not in engine.snapshot()["settings"]["modules"]
    for user in (owner, child):
        hidden = await _request(hass, entry, user, 210, "view")
        assert hidden["success"] and "school" not in hidden["result"]
    replay_disabled = await _request(
        hass,
        entry,
        parent,
        211,
        "school.timetable_save",
        active_payload,
        "school-ha-active-create",
    )
    assert not replay_disabled["success"]
    assert replay_disabled["error"]["code"] == "module_disabled", replay_disabled
    reenabled = await _general(hass, entry, owner, school=True)
    assert reenabled["type"] == "create_entry", reenabled
    assert "school" in engine.snapshot()["settings"]["modules"]
    final = (await _request(hass, entry, owner, 212, "view"))["result"]["school"]
    current = next(row for row in final["timetables"] if row["id"] == active["id"])
    assert current["status"] == "active" and current["member"] == child_id
    print("PASS: actual HA school timetable versions, privacy, replay and module revocation")
    return active["id"]
