"""Maintenance through actual HA options, WebSockets, scheduler and projections."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from aiohttp import ClientSession


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/maintenance-smoke"
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
                "operation_id": operation or f"maintenance-ha-{identifier}",
            }
        await ws.send_json(message)
        return await ws.receive_json()


async def _general(hass, entry, user, *, maintenance, tasks):
    from custom_components.family_assistant.config_flow import CONFIGURABLE_MODULES

    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    assert flow["type"] == "menu", flow
    form = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": "general"}
    )
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
        "maintenance": maintenance,
        "tasks": tasks,
    }
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    await hass.async_block_till_done()
    return result


def _member_payload(member, *, role=None):
    return {
        "id": member["id"],
        "revision": member["revision"],
        "name": member["name"],
        "role": role or member["role"],
    }


async def verify_maintenance(hass, entry, owner, child_id):
    """Verify maintenance authority, task reuse, privacy and persistence."""
    from homeassistant.core import Context
    from homeassistant.helpers import llm

    from custom_components.family_assistant.domain.task_delivery import current_task_event
    from custom_components.family_assistant.llm_api import FamilyAPI
    from custom_components.family_assistant.notifications import Notifications
    from custom_components.family_assistant.runtime import safe_diagnostics
    from custom_components.family_assistant.telegram.messages import targets

    engine = entry.runtime_data.engine
    snapshot = engine.snapshot()
    member_ids = set(snapshot["members"])
    child_record = snapshot["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None
    parent_record = next(
        member
        for member in snapshot["members"].values()
        if member["role"] == "parent" and member.get("ha_user_id")
    )
    parent = await hass.auth.async_get_user(parent_record["ha_user_id"])
    assert parent is not None
    unrelated_record = next(
        member
        for member in snapshot["members"].values()
        if member["role"] == "adult" and member.get("ha_user_id")
    )
    unrelated = await hass.auth.async_get_user(unrelated_record["ha_user_id"])
    assert unrelated is not None

    denied_options = await _general(hass, entry, child, maintenance=True, tasks=True)
    assert denied_options["type"] == "abort" and denied_options["reason"] == "forbidden"
    enabled = await _general(hass, entry, owner, maintenance=True, tasks=True)
    assert enabled["type"] == "create_entry", enabled
    assert {"tasks", "maintenance"} <= set(engine.snapshot()["settings"]["modules"])

    private_note = "SYNTHETIC_MAINTENANCE_PARENT_PRIVATE_NOTE"
    warranty_reference = "SYNTHETIC_MAINTENANCE_PRIVATE_WARRANTY"
    log_summary = "Synthetic maintenance service recorded"
    asset_payload = {
        "name": "Synthetic ventilation unit",
        "category": "Ventilation",
        "location": "Utility room",
        "responsible_member": "owner",
        "responsible_member_revision": engine.snapshot()["members"]["owner"]["revision"],
        "warranty": {
            "expires_on": "2027-09-07",
            "vendor": "Synthetic vendor",
            "reference": warranty_reference,
        },
        "consumables": [],
        "note": private_note,
    }
    sequence = 300

    async def command(user, action, payload, *, operation=None, error=None):
        nonlocal sequence
        sequence += 1
        response = await _request(
            hass,
            entry,
            user,
            sequence,
            action,
            payload,
            operation,
        )
        if error is not None:
            assert not response["success"] and response["error"]["code"] == error, response
            return None
        assert response["success"], response
        return response["result"]

    outbox_before_asset = deepcopy(engine.snapshot()["outbox"])
    created = await command(
        parent,
        "maintenance.asset_save",
        asset_payload,
        operation="maintenance-ha-asset-create",
    )
    assert set(created) == {"id", "revision", "status"}
    assert created["status"] == "active"
    asset_id = created["id"]
    stored_asset = engine.snapshot()["maintenance"]["assets"][asset_id]
    assert stored_asset["reportable"] is False
    assert stored_asset["approved_by"] == parent_record["id"]

    await command(child, "maintenance.asset_save", asset_payload, error="forbidden")
    child_view = await _request(hass, entry, child, sequence + 1, "view")
    assert child_view["success"]
    assert child_view["result"]["maintenance"]["assets"] == []
    fault_payload = {
        "asset_id": asset_id,
        "asset_revision": created["revision"],
        "reporter_member_revision": child_record["revision"],
        "summary": "Synthetic fan noise",
        "details": "Synthetic observation only; no diagnosis",
        "attachment_ids": [],
    }
    await command(child, "maintenance.fault_report", fault_payload, error="forbidden")

    editable = {
        **asset_payload,
        "id": asset_id,
        "revision": created["revision"],
        "reportable": True,
    }
    reportable = await command(parent, "maintenance.asset_save", editable)
    assert reportable["revision"] > created["revision"]
    assert engine.snapshot()["outbox"] == outbox_before_asset
    fault_payload["asset_revision"] = reportable["revision"]
    fault_payload["reporter_member_revision"] = child_record["revision"] + 1
    await command(child, "maintenance.fault_report", fault_payload, error="conflict")
    fault_payload["reporter_member_revision"] = child_record["revision"]

    tasks_before_fault = set(engine.snapshot()["tasks"])
    fault = await command(
        child,
        "maintenance.fault_report",
        fault_payload,
        operation="maintenance-ha-fault",
    )
    assert set(fault) == {"id", "revision", "status", "task_id"}
    assert fault["status"] == "reported"
    assert (
        await command(
            child,
            "maintenance.fault_report",
            fault_payload,
            operation="maintenance-ha-fault",
        )
        == fault
    )
    tasks_after_fault = engine.snapshot()["tasks"]
    assert set(tasks_after_fault) - tasks_before_fault == {fault["task_id"]}
    fault_task = tasks_after_fault[fault["task_id"]]
    assert fault_task["assignee"] == "owner"
    assert fault_task["creator"] == parent_record["id"]
    assert fault_task["delivery_scope"] == "private"
    assert fault_task["source"] == {
        "kind": "maintenance_fault",
        "asset_id": asset_id,
        "asset_revision": reportable["revision"],
        "fault_id": fault["id"],
    }

    # A persisted receipt does not resurrect a reporter identity epoch that the
    # current projection no longer recognizes, even when the role is unchanged.
    current_child = engine.snapshot()["members"][child_id]
    child_record = await command(owner, "members.save", _member_payload(current_child))
    await command(
        child,
        "maintenance.fault_report",
        fault_payload,
        operation="maintenance-ha-fault",
        error="conflict",
    )
    child_after_epoch = await _request(hass, entry, child, sequence + 1, "view")
    assert child_after_epoch["success"]
    assert child_after_epoch["result"]["maintenance"]["faults"] == []

    now = datetime.now(UTC)
    release = (now + timedelta(minutes=5)).replace(second=0, microsecond=0)
    due = release + timedelta(hours=1)
    child_revision = child_record["revision"]
    service_payload = {
        "asset_id": asset_id,
        "asset_revision": reportable["revision"],
        "title": "Synthetic filter inspection",
        "assignees": [{"id": child_id, "revision": child_revision}],
        "rotation": False,
        "rule": {
            "frequency": "daily",
            "start_date": release.date().isoformat(),
            "time": release.strftime("%H:%M"),
            "timezone": "UTC",
        },
        "due_time": due.strftime("%H:%M"),
        "checklist": ["Record synthetic inspection"],
        "enabled": True,
        "reminder_minutes": 15,
        "grace_minutes": 30,
    }
    service = await command(
        parent,
        "maintenance.service_save",
        service_payload,
        operation="maintenance-ha-service",
    )
    assert set(service) == {"id", "revision", "enabled"}
    assert service["enabled"] is True
    assert (
        await command(
            parent,
            "maintenance.service_save",
            service_payload,
            operation="maintenance-ha-service",
        )
        == service
    )
    managed = engine.snapshot()["task_series"][service["id"]]
    assert managed["source"]["kind"] == "maintenance"
    assert managed["source"]["asset_id"] == asset_id
    assert managed["source"]["member_revisions"] == {child_id: child_revision}
    await command(
        parent,
        "tasks.series_enable",
        {"id": service["id"], "revision": service["revision"], "enabled": False},
        error="forbidden",
    )

    service_tasks_before = {
        task["id"]
        for task in engine.snapshot()["tasks"].values()
        if task.get("series_id") == service["id"]
    }
    assert not service_tasks_before
    assert await engine.tick(release + timedelta(seconds=5))
    generated = [
        task
        for task in engine.snapshot()["tasks"].values()
        if task.get("series_id") == service["id"]
    ]
    assert len(generated) == 1
    service_task = generated[0]
    assert service_task["assignee"] == child_id
    assert service_task["delivery_scope"] == "private"
    assert service_task["deadline_policy"]["penalty"] == 0
    assert service_task["source"]["kind"] == "maintenance_service"
    assert service_task["source"]["asset_id"] == asset_id
    assert service_task["source"]["series_id"] == service["id"]
    assert service_task["source"]["series_revision"] == service["revision"]
    await engine.tick(release + timedelta(seconds=10))
    assert (
        len(
            [
                task
                for task in engine.snapshot()["tasks"].values()
                if task.get("series_id") == service["id"]
            ]
        )
        == 1
    )

    # Assignment events contain identifiers only and resolve to private member
    # targets, never the configured family group.
    snapshot = engine.snapshot()
    group = snapshot["telegram"].get("group_id")
    for task_id in (fault["task_id"], service_task["id"]):
        notice = next(
            item
            for item in snapshot["outbox"].values()
            if item["key"] == "task_assigned" and item["data"].get("id") == task_id
        )
        assert private_note not in str(notice) and warranty_reference not in str(notice)
        task = snapshot["tasks"][task_id]
        assert notice["recipient"] == task["assignee"]
        assert notice["data"] == {
            "id": task_id,
            "member": task["assignee"],
            "member_revision": task["assignee_revision"],
        }
        resolved = targets(notice, snapshot)
        assert resolved
        assert all(target["id"] != group for target in resolved)

    # Parent-only fields are absent from all unprivileged projections. Exercise
    # a second current child without adding a fixture user, then restore its role.
    parent_view = await _request(hass, entry, parent, sequence + 2, "view")
    assert parent_view["success"]
    assert private_note in str(parent_view["result"]["maintenance"])
    assert warranty_reference in str(parent_view["result"]["maintenance"])
    second_child = await command(
        owner,
        "members.save",
        _member_payload(unrelated_record, role="child"),
    )
    unrelated_view = await _request(hass, entry, unrelated, sequence + 3, "view")
    assert unrelated_view["success"]
    limited = unrelated_view["result"]["maintenance"]
    assert limited["faults"] == [] and limited["services"] == []
    assert limited["service_logs"] == []
    assert private_note not in str(limited) and warranty_reference not in str(limited)
    restored_adult = await command(
        owner,
        "members.save",
        _member_payload(second_child, role="adult"),
    )
    assert restored_adult["role"] == "adult" and restored_adult["ha_user_id"] == unrelated.id

    context = llm.LLMContext(
        platform="conversation",
        context=Context(user_id=owner.id),
        language="en",
        assistant="conversation",
        device_id=None,
    )
    api = await FamilyAPI(hass, entry).async_get_api_instance(context)
    family = await api.async_call_tool(llm.ToolInput(tool_name="ReadFamily", tool_args={}))
    for canary in (
        private_note,
        warranty_reference,
        fault_task["title"],
        service_task["title"],
    ):
        assert canary not in str(family)
    for canary in (private_note, warranty_reference):
        assert canary not in str(safe_diagnostics(entry.runtime_data))
        assert canary not in str([state.as_dict() for state in hass.states.async_all()])
        assert canary not in str(engine.snapshot()["audit"])
        assert canary not in str(engine.snapshot()["processed"])

    retired = await command(
        parent,
        "maintenance.asset_retire",
        {
            "id": asset_id,
            "revision": reportable["revision"],
            "reason": "Synthetic replacement",
        },
    )
    assert retired["status"] == "retired"
    disabled = await _general(hass, entry, owner, maintenance=False, tasks=True)
    assert disabled["type"] == "create_entry", disabled
    for user in (owner, child):
        hidden = await _request(hass, entry, user, sequence + 4, "view")
        assert hidden["success"] and "maintenance" not in hidden["result"]
    await command(
        parent,
        "maintenance.asset_save",
        asset_payload,
        operation="maintenance-ha-asset-create",
        error="module_disabled",
    )
    await command(
        child,
        "maintenance.fault_report",
        fault_payload,
        operation="maintenance-ha-fault",
        error="module_disabled",
    )
    await command(
        parent,
        "maintenance.service_save",
        service_payload,
        operation="maintenance-ha-service",
        error="module_disabled",
    )

    # The generated ordinary task remains usable after its source asset retires
    # and while Maintenance is disabled, provided Tasks itself remains enabled.
    started = await command(
        child,
        "tasks.start",
        {"id": service_task["id"], "revision": service_task["revision"]},
        operation="maintenance-ha-private-task-start",
    )
    assert started["delivery_scope"] == "private" and "source" not in started
    assert (
        await command(
            child,
            "tasks.start",
            {"id": service_task["id"], "revision": service_task["revision"]},
            operation="maintenance-ha-private-task-start",
        )
        == started
    )
    submitted = await command(
        child,
        "tasks.submit",
        {
            "id": started["id"],
            "revision": started["revision"],
            "report": "Synthetic service report",
        },
    )
    completed = await command(
        parent,
        "tasks.complete",
        {"id": submitted["id"], "revision": submitted["revision"]},
    )
    assert completed["status"] == "completed"
    assert "source" not in submitted and completed["source"]["kind"] == "maintenance_service"

    reenabled = await _general(hass, entry, owner, maintenance=True, tasks=True)
    assert reenabled["type"] == "create_entry", reenabled
    no_order_before = {
        "shopping": deepcopy(engine.snapshot()["shopping"]),
        "pantry": deepcopy(engine.snapshot()["pantry"]),
        "outbox": deepcopy(engine.snapshot()["outbox"]),
    }
    service_log = await command(
        parent,
        "maintenance.service_log",
        {
            "asset_id": asset_id,
            "asset_revision": retired["revision"],
            "performed_on": datetime.now(UTC).date().isoformat(),
            "summary": log_summary,
            "task": {"id": completed["id"], "revision": completed["revision"]},
            "consumables_used": [],
            "attachment_ids": [],
        },
    )
    assert set(service_log) == {"id", "revision", "status"}
    assert service_log["status"] == "recorded"
    assert engine.snapshot()["shopping"] == no_order_before["shopping"]
    assert engine.snapshot()["pantry"] == no_order_before["pantry"]
    assert engine.snapshot()["outbox"] == no_order_before["outbox"]

    # A retired source suppresses the next recurrence, while the first task and
    # its immutable manual service log remain present.
    await engine.tick(release + timedelta(days=1, seconds=5))
    assert (
        len(
            [
                task
                for task in engine.snapshot()["tasks"].values()
                if task.get("series_id") == service["id"]
            ]
        )
        == 1
    )
    assert engine.snapshot()["tasks"][completed["id"]]["status"] == "completed"
    assert (
        engine.snapshot()["maintenance"]["service_logs"][service_log["id"]]["task_id"]
        == (completed["id"])
    )

    # Stage a real persisted delivery claim, then revoke Tasks before the final
    # adapter authorization. No transport callback is reached.
    fault_notice = next(
        item
        for item in engine.snapshot()["outbox"].values()
        if item["key"] == "task_assigned" and item["data"].get("id") == fault["task_id"]
    )
    assert current_task_event(engine.snapshot(), fault_notice)
    delivery_id = "maintenance-smoke-delivery"
    staged_target = {"channel": "synthetic", "id": "private-owner"}

    def stage_delivery(ctx):
        notice = ctx.state["outbox"][fault_notice["id"]]
        notice["state"] = "sending"
        notice["deliveries"] = {
            delivery_id: {
                "id": delivery_id,
                "target": staged_target,
                "state": "sending",
                "attempts": 1,
            }
        }

    await engine.system_update("maintenance-stage-delivery", datetime.now(UTC), stage_delivery)
    tasks_disabled = await _general(hass, entry, owner, maintenance=True, tasks=False)
    assert tasks_disabled["type"] == "create_entry", tasks_disabled

    async def no_send(_event, _target):
        raise AssertionError("revoked task event reached transport")

    notifications = Notifications(engine, lambda _event, _state: [staged_target], no_send)
    assert (
        await notifications._authorize_dispatch(fault_notice["id"], delivery_id, datetime.now(UTC))
        is None
    )
    staged = engine.snapshot()["outbox"][fault_notice["id"]]
    assert staged["deliveries"][delivery_id]["state"] == "superseded"
    await command(
        child,
        "maintenance.fault_report",
        fault_payload,
        operation="maintenance-ha-fault",
        error="module_disabled",
    )
    await command(
        parent,
        "maintenance.service_save",
        service_payload,
        operation="maintenance-ha-service",
        error="module_disabled",
    )
    restored_modules = await _general(hass, entry, owner, maintenance=True, tasks=True)
    assert restored_modules["type"] == "create_entry", restored_modules

    final = (await _request(hass, entry, parent, sequence + 5, "view"))["result"]["maintenance"]
    final_asset = next(item for item in final["assets"] if item["id"] == asset_id)
    final_log = next(item for item in final["service_logs"] if item["id"] == service_log["id"])
    assert final_asset["status"] == "retired"
    assert final_log["task_id"] == completed["id"]
    assert set(engine.snapshot()["members"]) == member_ids
    assert engine.snapshot()["members"][child_id]["role"] == "child"
    print(
        "PASS: actual HA maintenance versions, privacy, task reuse, recurrence, "
        "replay and pre-transport revocation"
    )
    return {
        "asset_id": asset_id,
        "fault_id": fault["id"],
        "fault_task_id": fault["task_id"],
        "service_id": service["id"],
        "service_task_id": completed["id"],
        "service_log_id": service_log["id"],
    }
