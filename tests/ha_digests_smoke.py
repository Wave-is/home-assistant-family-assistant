"""Actual Home Assistant acceptance for private, opt-in family digests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from aiohttp import ClientSession
from ha_options_menu import select_option


@asynccontextmanager
async def _socket(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/digests-smoke"
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


async def _message(hass, user, message):
    async with _socket(hass, user) as ws:
        await ws.send_json(message)
        return await ws.receive_json()


async def _execute(hass, entry, user, identifier, action, payload, operation):
    return await _message(
        hass,
        user,
        {
            "id": identifier,
            "type": "family_assistant/execute",
            "entry_id": entry.entry_id,
            "action": action,
            "payload": payload,
            "operation_id": operation,
        },
    )


async def _view(hass, entry, user, identifier):
    return await _message(
        hass,
        user,
        {
            "id": identifier,
            "type": "family_assistant/view",
            "entry_id": entry.entry_id,
        },
    )


async def _preview(hass, entry, user, identifier, kind="morning"):
    return await _message(
        hass,
        user,
        {
            "id": identifier,
            "type": "family_assistant/digest_preview",
            "entry_id": entry.entry_id,
            "kind": kind,
        },
    )


async def _policy(hass, entry, user, **changes):
    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    assert flow["type"] == "menu", flow
    form = await select_option(hass, flow, "digests")
    if form["type"] == "abort":
        return form
    assert form["type"] == "form" and form["step_id"] == "digests", form
    values = {**dict(form["data_schema"]({})), **changes}
    review = await hass.config_entries.options.async_configure(form["flow_id"], values)
    assert review["type"] == "form" and review["step_id"] == "digest_policy_review", review
    result = await hass.config_entries.options.async_configure(
        review["flow_id"], {"confirmed": True}
    )
    await hass.async_block_till_done()
    return result


async def _module(hass, entry, user, enabled):
    from custom_components.family_assistant.config_flow import CONFIGURABLE_MODULES

    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    form = await select_option(hass, flow, "general")
    assert form["type"] == "form" and form["step_id"] == "general", form
    state = entry.runtime_data.engine.snapshot()
    values = {
        "name": state["settings"]["name"],
        "language": state["settings"]["language"],
        "timezone": state["settings"]["timezone"],
        "automatic_penalties": state["settings"].get("automatic_penalties", False),
        "daily_penalty_cap": state["settings"].get("daily_penalty_cap", 1),
        "pantry_expiry_reminders": state["settings"].get("pantry_expiry_reminders", False),
        "pantry_expiry_days": state["settings"].get("pantry_expiry_days", 3),
        "school_preparation_reminders": state["settings"].get(
            "school_preparation_reminders", False
        ),
        "school_preparation_days_before": state["settings"].get(
            "school_preparation_days_before", 1
        ),
        "school_preparation_time": state["settings"].get("school_preparation_time", "20:00"),
        **{module: module in state["settings"]["modules"] for module in CONFIGURABLE_MODULES},
    }
    values["digests"] = enabled
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    await hass.async_block_till_done()
    return result


def _section(snapshot, key):
    return next(item for item in snapshot["sections"] if item["key"] == key)


async def verify_digests(hass, entry, owner_user, child_id):
    """Verify real Options, WebSocket, Store, notification and renderer boundaries."""
    from custom_components.family_assistant.assistant import plans
    from custom_components.family_assistant.domain import digests
    from custom_components.family_assistant.notifications import Notifications
    from custom_components.family_assistant.telegram import messages

    main_child = entry.runtime_data.engine.snapshot()["members"][child_id]
    child_user = await hass.auth.async_get_user(main_child["ha_user_id"])
    assert child_user is not None
    created = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner_user.id}
    )
    created = await hass.config_entries.flow.async_configure(
        created["flow_id"],
        {
            "name": "Synthetic digest household",
            "owner_name": "Digest owner",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(
        created["flow_id"], {"tasks": True, "calendar": True, "digests": True}
    )
    isolated = created["result"]
    await hass.async_block_till_done()
    try:
        await isolated.runtime_data.scheduler.stop()
        engine = isolated.runtime_data.engine
        base = datetime.now(UTC).replace(hour=10, minute=2, second=0, microsecond=0)
        day = base.date().isoformat()
        tomorrow = (base.date() + timedelta(days=1)).isoformat()

        child_created = await _execute(
            hass,
            isolated,
            owner_user,
            1,
            "members.save",
            {
                "name": "Digest child",
                "role": "child",
                "language": "uk",
                "ha_user_id": child_user.id,
            },
            "digest-ha-child",
        )
        assert child_created["success"], child_created
        digest_child = child_created["result"]["id"]
        sibling_created = await _execute(
            hass,
            isolated,
            owner_user,
            2,
            "members.save",
            {"name": "Digest sibling", "role": "child", "language": "ru"},
            "digest-ha-sibling",
        )
        assert sibling_created["success"], sibling_created
        sibling = sibling_created["result"]["id"]

        denied_policy = await _policy(
            hass,
            isolated,
            child_user,
            digest_morning_enabled=True,
            digest_morning_time="10:00",
        )
        assert denied_policy["type"] == "abort", denied_policy
        assert denied_policy["reason"] == "forbidden", denied_policy
        enabled = await _policy(
            hass,
            isolated,
            owner_user,
            digest_morning_enabled=True,
            digest_morning_time="10:00",
        )
        assert enabled["type"] == "create_entry", enabled

        child_revision = engine.snapshot()["members"][digest_child]["revision"]
        subscribe_payload = {
            "recipient_revision": child_revision,
            "subscription_revision": None,
            "morning": True,
            "evening": False,
            "weekly": False,
        }
        subscribed = await _execute(
            hass,
            isolated,
            child_user,
            3,
            "digests.access_set",
            subscribe_payload,
            "digest-ha-subscribe",
        )
        assert subscribed["success"] and subscribed["result"] == {
            "revision": 1,
            "status": "enabled",
        }
        replay = await _execute(
            hass,
            isolated,
            child_user,
            4,
            "digests.access_set",
            subscribe_payload,
            "digest-ha-subscribe",
        )
        assert replay["success"] and replay["result"] == subscribed["result"]

        task = await _execute(
            hass,
            isolated,
            owner_user,
            5,
            "tasks.create",
            {
                "title": "Pack the blue notebook",
                "assignee": digest_child,
                "due_at": f"{day}T14:00:00+00:00",
                "report_type": "text",
            },
            "digest-ha-task",
        )
        sibling_task = await _execute(
            hass,
            isolated,
            owner_user,
            6,
            "tasks.create",
            {
                "title": "SIBLING-TITLE-CANARY-407a",
                "assignee": sibling,
                "due_at": f"{day}T15:00:00+00:00",
            },
            "digest-ha-sibling-task",
        )
        assert task["success"] and sibling_task["success"]
        event = await _execute(
            hass,
            isolated,
            owner_user,
            7,
            "calendar.save",
            {
                "title": "Music practice",
                "start": f"{day}T12:00:00+00:00",
                "end": f"{day}T12:30:00+00:00",
                "participants": [digest_child],
                "visibility": "participants",
                "description": "CALENDAR-DESCRIPTION-CANARY-81d4",
                "location": "CALENDAR-LOCATION-CANARY-99b1",
            },
            "digest-ha-calendar",
        )
        assert event["success"], event

        def prepare(ctx):
            ctx.state["members"][digest_child]["telegram_id"] = 820001
            ctx.state["telegram"]["group_id"] = -820099
            ctx.state["tasks"][task["result"]["id"]]["report"] = "TASK-REPORT-CANARY-c6e0"
            ctx.state["tasks"][task["result"]["id"]]["previous_reports"] = [
                {"report": "OLD-REPORT-CANARY-e48b"}
            ]
            ctx.state["outbox"] = {}

        await engine.system_update("digest-ha-fixture", base, prepare)

        child_view = await _view(hass, isolated, child_user, 8)
        owner_view = await _view(hass, isolated, owner_user, 9)
        assert child_view["success"] and owner_view["success"]
        assert "digest_subscriptions" not in json_text(child_view["result"])
        assert child_view["result"]["digests"]["self"]["morning"] is True
        assert owner_view["result"]["digests"]["self"]["subscription_revision"] is None

        child_preview = await _preview(hass, isolated, child_user, 10)
        owner_preview = await _preview(hass, isolated, owner_user, 11)
        assert child_preview["success"] and owner_preview["success"]
        child_snapshot = child_preview["result"]
        assert _section(child_snapshot, "tasks")["rows"][0]["title"] == ("Pack the blue notebook")
        assert _section(child_snapshot, "calendar")["rows"][0]["title"] == "Music practice"
        preview_text = json_text(child_snapshot)
        for canary in (
            "SIBLING-TITLE-CANARY-407a",
            "CALENDAR-DESCRIPTION-CANARY-81d4",
            "CALENDAR-LOCATION-CANARY-99b1",
            "TASK-REPORT-CANARY-c6e0",
            "OLD-REPORT-CANARY-e48b",
        ):
            assert canary not in preview_text
        owner_tasks = _section(owner_preview["result"], "tasks")
        assert owner_tasks["count"] == 2 and owner_tasks["rows"] == []
        assert "digests" not in json_text(plans.projection(child_view["result"]))
        assert "TASK-REPORT-CANARY-c6e0" not in json_text(plans.projection(child_view["result"]))

        sources_before = {key: deepcopy(engine.snapshot()[key]) for key in ("tasks", "calendar")}
        assert await engine.tick(base)
        current = engine.snapshot()
        assert current["tasks"] == sources_before["tasks"]
        assert current["calendar"] == sources_before["calendar"]
        digest_event = next(
            value for value in current["outbox"].values() if value["key"] == "family_digest"
        )
        assert set(digest_event["data"]) == digests.EVENT_FIELDS
        assert messages.targets(digest_event, current) == [
            {"channel": "telegram", "id": 820001, "language": "uk"}
        ]
        assert messages.targets(digest_event, current)[0]["id"] != current["telegram"]["group_id"]

        def quiet(ctx):
            ctx.state["settings"]["notifications"] = {
                "quiet_enabled": True,
                "quiet_start": "09:00",
                "quiet_end": "11:00",
                "timezone": "UTC",
            }

        await engine.system_update("digest-ha-quiet", base, quiet)
        sent = []

        async def send(current_event, target):
            envelope = messages.render(current_event, target, engine.snapshot(), now=base)
            sent.append(envelope)
            return "synthetic-digest-receipt"

        worker = Notifications(engine, messages.targets, send, clock=lambda: base)
        assert await worker.run(base) == 0 and sent == []

        revised = await _execute(
            hass,
            isolated,
            owner_user,
            12,
            "tasks.revise",
            {
                "id": task["result"]["id"],
                "revision": engine.snapshot()["tasks"][task["result"]["id"]]["revision"],
                "title": "Pack the revised notebook",
            },
            "digest-ha-task-revise",
        )
        assert revised["success"], revised

        def unquiet(ctx):
            ctx.state["settings"]["notifications"]["quiet_enabled"] = False

        await engine.system_update("digest-ha-unquiet", base, unquiet)
        assert await worker.run(base) == 1 and len(sent) == 1
        assert sent[0]["chat_id"] == 820001
        assert sent[0]["link_preview_options"] == {"is_disabled": True}
        assert "Pack the revised notebook" in sent[0]["text"]
        assert len(sent[0]["text"].encode("utf-16-le")) // 2 <= 3800
        assert "SIBLING-TITLE-CANARY-407a" not in sent[0]["text"]
        unchanged_calendar = engine.snapshot()["calendar"]
        assert unchanged_calendar == sources_before["calendar"]

        old_event = deepcopy(digest_event)
        changed = await _policy(hass, isolated, owner_user, digest_morning_time="10:01")
        assert changed["type"] == "create_entry", changed
        restored = await _policy(hass, isolated, owner_user, digest_morning_time="10:00")
        assert restored["type"] == "create_entry", restored
        assert not digests.delivery_allowed(engine.snapshot(), old_event, base)

        next_task = engine.snapshot()["tasks"][task["result"]["id"]]
        moved = await _execute(
            hass,
            isolated,
            owner_user,
            13,
            "tasks.revise",
            {
                "id": next_task["id"],
                "revision": next_task["revision"],
                "due_at": f"{tomorrow}T14:00:00+00:00",
            },
            "digest-ha-task-next",
        )
        assert moved["success"], moved
        sibling_cancelled = await _execute(
            hass,
            isolated,
            owner_user,
            17,
            "tasks.cancel",
            {
                "id": sibling_task["result"]["id"],
                "revision": engine.snapshot()["tasks"][sibling_task["result"]["id"]]["revision"],
            },
            "digest-ha-sibling-cancel",
        )
        assert sibling_cancelled["success"], sibling_cancelled
        assert await engine.tick(base + timedelta(days=1))
        second_event = next(
            value
            for value in engine.snapshot()["outbox"].values()
            if value["key"] == "family_digest" and value["id"] != digest_event["id"]
        )
        disabled = await _execute(
            hass,
            isolated,
            child_user,
            14,
            "digests.access_set",
            {**subscribe_payload, "subscription_revision": 1, "morning": False},
            "digest-ha-disable",
        )
        assert disabled["success"] and disabled["result"]["status"] == "disabled"
        worker = Notifications(
            engine,
            messages.targets,
            send,
            clock=lambda: base + timedelta(days=1),
        )
        assert await worker.run(base + timedelta(days=1)) == 0
        assert engine.snapshot()["outbox"][second_event["id"]]["state"] == "superseded"

        module_off = await _module(hass, isolated, owner_user, False)
        assert module_off["type"] == "create_entry", module_off
        denied_preview = await _preview(hass, isolated, child_user, 15)
        assert not denied_preview["success"]
        assert denied_preview["error"]["code"] == "module_disabled"
        denied_replay = await _execute(
            hass,
            isolated,
            child_user,
            16,
            "digests.access_set",
            subscribe_payload,
            "digest-ha-subscribe",
        )
        assert not denied_replay["success"]
        assert denied_replay["error"]["code"] == "module_disabled"

        # Pruning advances a persisted, content-free floor before a clock or
        # policy rollback could regenerate an already retired local period.
        assert (
            await engine.system_update("digest-ha-retire", base + timedelta(days=40), digests.prune)
            == 2
        )
        retired = deepcopy(engine.snapshot()["digest_retired"])
        assert retired == {"morning": tomorrow}
        assert not any(
            value.get("key") == "family_digest" for value in engine.snapshot()["outbox"].values()
        )
        retired_view = await _view(hass, isolated, owner_user, 18)
        assert retired_view["success"]
        assert "digest_retired" not in json_text(retired_view["result"])
        from custom_components.family_assistant.runtime import safe_diagnostics

        diagnostics = safe_diagnostics(isolated.runtime_data)
        assert "digest_retired" not in diagnostics
        assert set(diagnostics["digest_capacity"]) == {
            "markers",
            "retained",
            "unresolved",
            "capacity",
        }

        from homeassistant.helpers import issue_registry as ir

        from custom_components.family_assistant import digest_health

        class SnapshotEngine:
            def __init__(self, value):
                self.value = value

            def snapshot(self):
                return deepcopy(self.value)

        health_runtime = SimpleNamespace(
            engine=SnapshotEngine({"digest_markers": {"one": {}}, "outbox": {}}),
            health={},
        )
        issue_id = f"{isolated.entry_id}_digest_retention"
        with patch.object(digests, "MAX_RECORDS", 1):
            stats = digest_health.synchronize(hass, isolated, health_runtime)
        assert stats == {"markers": 1, "retained": 0, "unresolved": 0, "capacity": True}
        assert health_runtime.health == {"digests": "digest_retention_attention"}
        assert ir.async_get(hass).async_get_issue("family_assistant", issue_id) is not None

        health_runtime.engine.value = {"digest_markers": {}, "outbox": {}}
        stats = digest_health.synchronize(hass, isolated, health_runtime)
        assert stats == {"markers": 0, "retained": 0, "unresolved": 0, "capacity": False}
        assert health_runtime.health == {}
        assert ir.async_get(hass).async_get_issue("family_assistant", issue_id) is None

        expected = {
            "subscriptions": deepcopy(engine.snapshot()["digest_subscriptions"]),
            "markers": deepcopy(engine.snapshot()["digest_markers"]),
            "retired": retired,
            "events": {
                key: deepcopy(value)
                for key, value in engine.snapshot()["outbox"].items()
                if value.get("key") == "family_digest"
            },
        }
        assert await hass.config_entries.async_reload(isolated.entry_id)
        await hass.async_block_till_done()
        reloaded = isolated.runtime_data.engine.snapshot()
        assert reloaded["digest_subscriptions"] == expected["subscriptions"]
        assert reloaded["digest_markers"] == expected["markers"]
        assert reloaded["digest_retired"] == expected["retired"]
        assert {
            key: value
            for key, value in reloaded["outbox"].items()
            if value.get("key") == "family_digest"
        } == expected["events"]
        print(
            "PASS: actual HA digest Options, private previews, quiet delivery, "
            "revocation, policy ABA and Store reload"
        )
    finally:
        await hass.config_entries.async_unload(isolated.entry_id)
        await hass.async_block_till_done()


def json_text(value):
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
