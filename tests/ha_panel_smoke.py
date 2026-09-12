"""Real HA REST/WS control-center acceptance with synthetic identities only."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from aiohttp import ClientSession
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util


async def verify_panel(hass, user):
    await async_setup_component(hass, "websocket_api", {})
    await async_setup_component(hass, "config", {})
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.org/panel"
    )
    token = hass.auth.async_create_access_token(refresh)
    headers = {"Authorization": f"Bearer {token}"}
    base = "http://127.0.0.1:8123"
    outsider = await hass.auth.async_create_user("Other administrator", group_ids=[GROUP_ID_ADMIN])
    other_refresh = await hass.auth.async_create_refresh_token(
        outsider, client_id="https://example.org/panel-outsider"
    )
    other_token = hass.auth.async_create_access_token(other_refresh)

    async with ClientSession() as session:

        async def post(path, data, *, selected_headers=headers):
            async with session.post(base + path, headers=selected_headers, json=data) as response:
                value = await response.json()
                assert response.status == 200, (response.status, value)
                return value

        # These are the actual frontend HTTP routes: Core passes no user_id in context.
        flow = await post("/api/config/config_entries/flow", {"handler": "family_assistant"})
        path = "/api/config/config_entries/flow/" + flow["flow_id"]
        flow = await post(
            path,
            {
                "name": "Panel test family",
                "owner_name": "Guardian",
                "language": "en",
                "timezone": "UTC",
                "template": "manual",
            },
        )
        assert flow["step_id"] == "modules", flow
        result = await post(path, {"shopping": True, "tasks": True, "court": True})
        assert result["type"] == "create_entry", result
        entry_id = result["result"]["entry_id"]
        entry = hass.config_entries.async_get_entry(entry_id)
        await hass.async_block_till_done()
        runtime = entry.runtime_data
        assert runtime.engine.snapshot()["members"]["owner"]["ha_user_id"] == user.id
        await runtime.scheduler.stop()
        assert "family" in hass.data[DATA_PANELS]
        url = hass.data[DATA_PANELS]["family"].config["_panel_custom"]["module_url"]
        async with session.get(base + url) as response:
            assert response.status == 200
            assert "family-panel.js" in await response.text()

        async def ws_call(endpoint, *, selected_token=token, **values):
            async with session.ws_connect(base + "/api/websocket") as socket:
                assert (await socket.receive_json())["type"] == "auth_required"
                await socket.send_json({"type": "auth", "access_token": selected_token})
                assert (await socket.receive_json())["type"] == "auth_ok"
                await socket.send_json(
                    {
                        "id": 1,
                        "type": f"family_assistant/{endpoint}",
                        "entry_id": entry_id,
                        **values,
                    }
                )
                while True:
                    answer = await socket.receive_json()
                    if answer.get("id") == 1:
                        return answer

        async def execute(action, payload, *, operation_id=None):
            answer = await ws_call(
                "execute", action=action, payload=payload, operation_id=operation_id or str(uuid4())
            )
            assert answer["success"], answer
            return answer["result"]

        original = (await ws_call("panel"))["result"]
        assert original["settings_revision"] == 1
        assert original["connections"]["telegram"]["text_ok"] is None
        before = runtime.engine.snapshot()
        preview = await ws_call("ai_sandbox_test", text="buy apples")
        assert preview["success"] and preview["result"]["simulated"]
        assert runtime.engine.snapshot() == before
        for kind in ("panel", "telegram_verify", "ai_sandbox_test"):
            denied = await ws_call(
                kind,
                selected_token=other_token,
                **({"text": "buy apples"} if kind == "ai_sandbox_test" else {}),
            )
            assert not denied["success"] and denied["error"]["code"] == "forbidden", denied

        child = await execute(
            "members.save",
            {"name": "Junior", "role": "child", "birth_date": "2015-02-03", "avatar": "robot"},
        )
        assert child["ha_user_id"] is None

        # Exercise the actual panel enrollment transport with a synthetic Telegram
        # adapter; no real token, network request or household message is involved.
        from custom_components.family_assistant.telegram.enrollment import Enrollment

        runtime.telegram = SimpleNamespace(bot={"id": 900001, "username": "synthetic_family_bot"})
        try:
            for kind, member, candidate in (
                ("member", "owner", {"chat_id": 900002, "user_id": 900002}),
                ("member", child["id"], {"chat_id": 900003, "user_id": 900003}),
                ("group", None, {"chat_id": -900004, "user_id": 900002}),
            ):
                issued = await ws_call(
                    "telegram_invite", kind=kind, **({"member_id": member} if member else {})
                )
                assert issued["success"], issued
                invitation = issued["result"]
                panel_data = (await ws_call("panel"))["result"]
                assert any(item["id"] == invitation["id"] for item in panel_data["enrollments"])
                assert invitation["code"] not in str(panel_data), (
                    "Invite secret leaked in projection"
                )
                now = dt_util.utcnow()
                assert await Enrollment(runtime.engine).capture(
                    {
                        "text": (
                            "/start " + invitation["code"] if member else invitation["instruction"]
                        ),
                        "date": int(now.timestamp()),
                        "from": {"id": candidate["user_id"], "first_name": "Synthetic person"},
                        "chat": {
                            "id": candidate["chat_id"],
                            "type": "private" if member else "supergroup",
                            "title": "Synthetic group",
                        },
                    },
                    "synthetic_family_bot",
                    now,
                )
                status = await ws_call("telegram_enrollment", enrollment_id=invitation["id"])
                assert status["success"] and status["result"]["state"] == "captured", status
                snapshot = runtime.engine.snapshot()
                for selected_token, displayed, error in (
                    (other_token, candidate, "forbidden"),
                    (token, {**candidate, "user_id": 900099}, "conflict"),
                ):
                    denied = await ws_call(
                        "telegram_enrollment_confirm",
                        selected_token=selected_token,
                        enrollment_id=invitation["id"],
                        candidate=displayed,
                    )
                    assert not denied["success"] and denied["error"]["code"] == error, denied
                    assert runtime.engine.snapshot() == snapshot
                for _attempt in range(2):
                    confirmed = await ws_call(
                        "telegram_enrollment_confirm",
                        enrollment_id=invitation["id"],
                        candidate=candidate,
                    )
                    assert confirmed["success"] and confirmed["result"]["linked"], confirmed
                status = await ws_call("telegram_enrollment", enrollment_id=invitation["id"])
                assert status["result"]["state"] == "confirmed"
                assert not (await ws_call("panel"))["result"]["enrollments"]
        finally:
            runtime.telegram = None
        await execute(
            "settings.patch",
            {"revision": 1, "changes": {"school_preparation_time": "19:30"}},
            operation_id="school-settings",
        )
        stale = await ws_call(
            "execute",
            action="settings.patch",
            payload={"revision": 1, "changes": {"name": "Stale family"}},
            operation_id="stale-window",
        )
        assert not stale["success"] and stale["error"]["code"] == "conflict", stale
        await execute("settings.onboarding", {"revision": 1, "step": 3, "skipped": ["telegram"]})

        # Canonical module switches reconcile services without reloading HA or
        # restarting Telegram. Model-less deterministic chat is a real service.
        for enabled in (True, False, True, False):
            current = (await ws_call("panel"))["result"]
            modules = set(current["view"]["settings"]["modules"])
            modules.add("conversation") if enabled else modules.discard("conversation")
            previous_telegram = runtime.telegram
            await execute(
                "settings.patch",
                {
                    "revision": current["settings_revision"],
                    "changes": {"modules": sorted(modules)},
                },
            )
            await hass.async_block_till_done()
            assert (runtime.chat is not None) == enabled
            assert runtime.assistant is None
            assert runtime.telegram is previous_telegram
            assert entry.runtime_data is runtime

        # Read the native options through HTTP and keep the actual caller identity.
        options = await post("/api/config/config_entries/options/flow", {"handler": entry_id})
        options_path = "/api/config/config_entries/options/flow/" + options["flow_id"]
        options = await post(options_path, {"next_step_id": "menu_family"})
        options = await post(options_path, {"next_step_id": "general"})
        assert options["step_id"] == "general" and options["type"] == "form", options
        denied = await post(
            options_path,
            {"name": "Hijacked", "language": "en"},
            selected_headers={"Authorization": f"Bearer {other_token}"},
        )
        assert denied["type"] == "abort" and denied["reason"] == "forbidden", denied

        expected = deepcopy(runtime.engine.snapshot())
        assert await hass.config_entries.async_reload(entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
        restored = (await ws_call("panel"))["result"]
        assert restored["onboarding"] == {
            "revision": 2,
            "step": 3,
            "completed": False,
            "skipped": ["telegram"],
        }
        assert restored["view"]["settings"]["school_preparation_time"] == "19:30"
        assert entry.runtime_data.engine.snapshot()["members"] == expected["members"]
        assert entry.runtime_data.engine.snapshot()["outbox"] == expected["outbox"]
        assert "family" in hass.data[DATA_PANELS]
        assert await hass.config_entries.async_unload(entry_id)
        assert "family" not in hass.data[DATA_PANELS]
    hass.auth.async_remove_refresh_token(refresh)
    hass.auth.async_remove_refresh_token(other_refresh)
    print(
        "PASS: actual HA panel REST identity, authorized WS, canonical saves, stale edits, "
        "private previews, guide reload and panel lifecycle"
    )
