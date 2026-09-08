"""Run with the real HA image; no production config, network or credentials.

docker run --rm --network none -v "$PWD:/work:ro" --entrypoint python \
  ghcr.io/home-assistant/home-assistant:2026.8.2 /work/tests/ha_smoke.py
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiohttp import ClientSession
from homeassistant import bootstrap, config_entries, loader
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.components.siren import DATA_COMPONENT, SirenEntity, SirenEntityFeature
from homeassistant.core import Context, CoreState, HomeAssistant
from homeassistant.setup import async_setup_component


class SyntheticSiren(SirenEntity):
    _attr_name = "Synthetic wake-up siren"
    _attr_unique_id = "synthetic-wakeup-test"
    _attr_should_poll = False
    _attr_is_on = False
    _attr_available_tones = {1: "Chime", 2: "Melody"}
    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.DURATION
        | SirenEntityFeature.VOLUME_SET
        | SirenEntityFeature.TONES
    )

    def __init__(self):
        self.calls = []

    async def async_turn_on(self, **kwargs):
        self.calls.append((True, kwargs))
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self.calls.append((False, kwargs))
        self._attr_is_on = False
        self.async_write_ha_state()


async def main():
    source = Path(__file__).resolve().parents[1] / "custom_components" / "family_assistant"
    with tempfile.TemporaryDirectory(prefix="family-ha-smoke-") as directory:
        shutil.copytree(source, Path(directory) / "custom_components" / "family_assistant")
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        assert await bootstrap.async_from_config_dict(
            {
                "homeassistant": {
                    "name": "Sandbox",
                    "latitude": 0,
                    "longitude": 0,
                    "elevation": 0,
                    "unit_system": "metric",
                    "time_zone": "UTC",
                    "country": "GB",
                },
                "http": {"server_host": "127.0.0.1", "server_port": 8123},
            },
            hass,
        )
        user = await hass.auth.async_create_user("Synthetic owner", group_ids=[GROUP_ID_ADMIN])
        try:
            # Bootstrap loads integrations; the real lifecycle transition is
            # separate. BackupManager correctly remains blocked until started.
            await hass.async_start()
            await hass.async_block_till_done()
            assert hass.state is CoreState.running
            await async_setup_component(hass, "websocket_api", {})
            result = await hass.config_entries.flow.async_init(
                "family_assistant", context={"source": "user", "user_id": user.id}
            )
            assert result["type"] == "form", result
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "name": "Synthetic family",
                    "owner_name": "Parent",
                    "language": "en",
                    "timezone": "Europe/Berlin",
                    "template": "pair",
                },
            )
            assert result["step_id"] == "modules", result
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    "shopping": True,
                    "tasks": True,
                    "court": True,
                    "alarms": True,
                },
            )
            assert result["type"] == "create_entry", result
            entry = result["result"]
            await hass.async_block_till_done()
            assert entry.state == config_entries.ConfigEntryState.LOADED, entry.state
            from ha_onboarding_handoff_smoke import verify_onboarding_handoff

            await verify_onboarding_handoff(hass, result, user)
            from ha_onboarding_smoke import verify_onboarding

            await verify_onboarding(hass, entry, user)
            from ha_frontend_resources_smoke import verify_frontend_resources

            await verify_frontend_resources(hass, entry)
            engine = entry.runtime_data.engine
            record = await engine.execute(
                "owner", "shopping.add", {"name": "Milk"}, "smoke-add", datetime.now(UTC)
            )
            assert record["id"] == "S000001"
            entry.runtime_data.updated()
            await hass.async_block_till_done()
            assert any(state.domain == "sensor" for state in hass.states.async_all())
            options = await hass.config_entries.options.async_init(
                entry.entry_id, context={"user_id": user.id}
            )
            assert options["type"] == "menu", options
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"next_step_id": "member"}
            )
            assert options["type"] == "form", options
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"member_id": "_new"}
            )
            assert options["step_id"] == "edit_member", options
            options = await hass.config_entries.options.async_configure(
                options["flow_id"],
                {
                    "name": "Child",
                    "role": "child",
                    "language": "uk",
                    "active": True,
                },
            )
            assert options["type"] == "create_entry", options
            assert len(engine.view("owner")["members"]) == 3
            assert engine.snapshot()["settings"]["timezone"] == "Europe/Berlin"
            assert engine.snapshot()["members"]["M000001"]["ha_user_id"] is None
            # Exercise the real core service registry with authenticated context.
            response = await hass.services.async_call(
                "family_assistant",
                "execute",
                {
                    "entry_id": entry.entry_id,
                    "action": "shopping.add",
                    "payload": {"name": "Bread"},
                    "operation_id": "smoke-service",
                },
                blocking=True,
                return_response=True,
                context=Context(user_id=user.id),
            )
            assert response["result"]["name"] == "Bread"
            # No physical device: this virtual entity uses HA's real siren platform,
            # including feature checks, tone mapping and service parameter validation.
            assert await async_setup_component(hass, "siren", {})
            siren = SyntheticSiren()
            await hass.data[DATA_COMPONENT].async_add_entities([siren])
            child_id = next(
                m["id"] for m in engine.view("owner")["members"] if m["role"] == "child"
            )
            options = await hass.config_entries.options.async_init(
                entry.entry_id, context={"user_id": user.id}
            )
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"next_step_id": "alarm_device"}
            )
            options = await hass.config_entries.options.async_configure(
                options["flow_id"],
                {
                    "member": child_id,
                    "entity_id": siren.entity_id,
                    "volume": 0.5,
                    "enabled": True,
                    "confirmed": False,
                },
            )
            assert options["errors"]["base"] == "device_confirmation_required"
            options = await hass.config_entries.options.async_configure(
                options["flow_id"],
                {
                    "member": child_id,
                    "entity_id": siren.entity_id,
                    "volume": 0.5,
                    "enabled": True,
                    "confirmed": True,
                },
            )
            assert options["type"] == "create_entry"
            clock = datetime.now(UTC)
            alarm = await engine.execute(
                "owner",
                "alarms.save",
                {
                    "member": child_id,
                    "time": "00:00",
                    "days": [0],
                    "timezone": "UTC",
                    "profile": "strict",
                },
                "smoke-alarm",
                clock,
            )
            run = await engine.execute(
                "owner", "alarms.test", {"id": alarm["id"]}, "smoke-ring", clock
            )
            await entry.runtime_data.scheduler.run(clock)
            assert siren.calls[-1] == (True, {"duration": 35, "volume_level": 0.5, "tone": 1}), (
                siren.calls
            )
            await entry.runtime_data.scheduler.run(clock + timedelta(seconds=20))
            assert siren.calls[-1][1]["tone"] == 2
            correct = sum(int(n) for n in run["challenge"]["question"].split(" + "))
            await engine.execute(
                child_id,
                "alarms.answer",
                {"id": run["id"], "nonce": run["challenge"]["nonce"], "answer": correct},
                "smoke-woke",
                clock + timedelta(seconds=21),
            )
            await entry.runtime_data.scheduler.run(clock + timedelta(seconds=21))
            assert siren.calls[-1][0] is False
            from ha_telegram_smoke import run as telegram_smoke

            await telegram_smoke(hass, entry, user, child_id)
            from ha_background_backup_smoke import verify_background_backup_loops

            await verify_background_backup_loops(hass, entry, user)
            await run_websocket(hass, entry, user, child_id)
            from ha_article_smoke import verify_articles

            await verify_articles(hass, entry, user, child_id)
            from ha_chat_scope_smoke import verify_chat_scope

            await verify_chat_scope(hass, entry, user, child_id)
            from ha_assistant_scope_smoke import verify_ha_assistant_scope

            await verify_ha_assistant_scope(hass, entry, user, child_id)
            from ha_command_scope_smoke import verify_command_scope

            await verify_command_scope(hass, entry, user)
            engine = entry.runtime_data.engine
            from ha_member_revision_smoke import verify_member_revision_options

            await verify_member_revision_options(hass, entry, user, child_id)
            from ha_telegram_smoke import run_network

            await run_network(hass, entry, user, child_id)
            from ha_recipes_smoke import verify_recipes

            await verify_recipes(hass, entry, user, child_id)
            from ha_pantry_expiry_smoke import verify_pantry_expiry

            await verify_pantry_expiry(hass, user)
            from ha_school_reminders_smoke import verify_school_reminders

            await verify_school_reminders(hass, user)
            from ha_school_smoke import verify_school

            school_id = await verify_school(hass, entry, user, child_id)
            from ha_school_import_smoke import verify_school_import

            school_import_child_id = await verify_school_import(hass, entry, user, child_id)
            from ha_maintenance_smoke import verify_maintenance

            maintenance_ids = await verify_maintenance(hass, entry, user, child_id)
            from ha_fault_photo_smoke import verify_fault_photos, verify_fault_photos_reload

            fault_photo_expected = await verify_fault_photos(hass, entry, user, child_id)
            from ha_document_smoke import verify_documents, verify_documents_reload

            document_expected = await verify_documents(hass, entry, user, child_id)
            maintenance_expected = entry.runtime_data.engine.snapshot()["maintenance"]
            maintenance_task_series = entry.runtime_data.engine.snapshot()["task_series"]
            maintenance_tasks = {
                task_id: entry.runtime_data.engine.snapshot()["tasks"][task_id]
                for task_id in (
                    maintenance_ids["fault_task_id"],
                    maintenance_ids["service_task_id"],
                )
            }
            from ha_school_work_smoke import verify_school_work

            school_work_ids = await verify_school_work(hass, entry, user, child_id)
            from ha_media_smoke import verify_media, verify_media_reload

            media_expected = await verify_media(hass, entry, user, child_id)
            from ha_media_retention_smoke import verify_media_retention

            await verify_media_retention(hass, entry, user, child_id)
            from ha_polls_smoke import verify_polls

            await verify_polls(hass, entry, user, child_id)
            from ha_presence_smoke import verify_presence

            await verify_presence(hass, entry, user)
            from ha_presence_notifications_smoke import verify_presence_notifications

            await verify_presence_notifications(hass, user)
            from ha_network_admission_smoke import verify_network_admission

            await verify_network_admission(hass, user)
            from ha_digests_smoke import verify_digests

            await verify_digests(hass, entry, user, child_id)
            from ha_developer_smoke import verify_developer_diagnostics

            await verify_developer_diagnostics(hass, user)
            from ha_semantic_feedback_smoke import verify_semantic_feedback

            await verify_semantic_feedback(hass, user)
            from ha_school_retention_smoke import verify_school_retention

            await verify_school_retention(hass, entry)
            from ha_backup_smoke import verify_backup

            await verify_backup(hass, entry, user, media_expected)
            from ha_backup_recovery_smoke import verify_backup_recovery

            await verify_backup_recovery(hass, user)
            from ha_encrypted_archive_smoke import verify_encrypted_archive

            await verify_encrypted_archive(hass, entry, user, media_expected)
            school_expected = entry.runtime_data.engine.snapshot()["school"]
            school_tasks_expected = {
                task_id: entry.runtime_data.engine.snapshot()["tasks"][task_id]
                for task_id in (
                    school_work_ids["child_homework_id"],
                    school_work_ids["parent_homework_id"],
                )
            }
            dietary_expected = entry.runtime_data.engine.snapshot()["dietary_profiles"]
            shopping_expected = entry.runtime_data.engine.snapshot()["shopping"]
            from ha_model_plan_smoke import verify_model_plan_reload, verify_model_plans

            model_plan_expected = await verify_model_plans(hass, entry, user, child_id)
            from ha_legacy_archive_smoke import verify_legacy_archive

            await verify_legacy_archive(hass)
            from ha_shadow_smoke import verify_shadow

            await verify_shadow(hass, user)
            from ha_copy_wizard_smoke import verify_copy_wizard

            await verify_copy_wizard(hass, user)
            from ha_personal_task_smoke import verify_personal_tasks

            personal_id = await verify_personal_tasks(hass, entry, user, child_id)
            personal_before_reload = entry.runtime_data.engine.snapshot()["tasks"][personal_id]
            text_history_before_reload = {
                key: task
                for key, task in entry.runtime_data.engine.snapshot()["tasks"].items()
                if task.get("report_type") == "text" and task.get("previous_reports")
            }
            assert text_history_before_reload
            # Reload reads the same Store; HACS code updates do not replace it.
            members_before_reload = entry.runtime_data.engine.snapshot()["members"]
            routines_before_reload = entry.runtime_data.engine.snapshot()["routine_runs"]
            active_routine = next(
                r for r in routines_before_reload.values() if r["status"] == "active"
            )
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state == config_entries.ConfigEntryState.LOADED
            for key, task in text_history_before_reload.items():
                assert entry.runtime_data.engine.snapshot()["tasks"][key] == task
            assert (
                entry.runtime_data.engine.snapshot()["tasks"][personal_id] == personal_before_reload
            )
            assert not any(
                task["id"] == personal_id
                for task in entry.runtime_data.engine.view("owner")["tasks"]
            )
            await verify_model_plan_reload(hass, entry, user, model_plan_expected)
            assert entry.runtime_data.engine.snapshot()["school"] == school_expected
            assert school_expected["timetables"][school_id]["status"] == "active"
            for task_id, task in school_tasks_expected.items():
                assert entry.runtime_data.engine.snapshot()["tasks"][task_id] == task
                assert task["source"]["kind"] == "school_homework"
            assert (
                school_expected["preparations"][school_work_ids["preparation_id"]]["run_id"]
                == school_work_ids["run_id"]
            )
            assert entry.runtime_data.engine.snapshot()["maintenance"] == maintenance_expected
            assert entry.runtime_data.engine.snapshot()["task_series"] == maintenance_task_series
            for task_id, task in maintenance_tasks.items():
                assert entry.runtime_data.engine.snapshot()["tasks"][task_id] == task
                assert (
                    task["delivery_scope"] == "private"
                    and task["source"]["asset_id"] == maintenance_ids["asset_id"]
                )
            assert entry.runtime_data.engine.snapshot()["dietary_profiles"] == dietary_expected
            from ha_dietary_smoke import verify_dietary_reload

            verify_dietary_reload(entry, dietary_expected)
            await verify_media_reload(entry, media_expected)
            await verify_fault_photos_reload(hass, entry, user, child_id, fault_photo_expected)
            await verify_documents_reload(hass, entry, user, child_id, document_expected)
            shopping_after_reload = entry.runtime_data.engine.view("owner")["shopping"]
            assert entry.runtime_data.engine.snapshot()["shopping"] == shopping_expected
            assert any(
                event.get("detail", {}).get("price") == {"total": "1.234", "currency": "EUR"}
                for item in shopping_expected.values()
                for event in item.get("history", [])
            ), "Actual priced history must survive the Store reload comparison"
            assert len(shopping_after_reload) == len(shopping_expected)
            pantry_after_reload = entry.runtime_data.engine.snapshot()["pantry"]
            assert len(pantry_after_reload["items"]) == 1
            assert next(iter(pantry_after_reload["items"].values()))["quantity"] == 0.5
            assert next(iter(pantry_after_reload["suggestions"].values()))["status"] == "accepted"
            meal_after_reload = next(iter(pantry_after_reload["meal_plans"].values()))
            assert meal_after_reload["status"] == "published"
            assert meal_after_reload["title"] == "Revised menu"
            assert meal_after_reload["entries"][0]["ingredients"][0]["quantity"] == 0.5
            meal_transfers = pantry_after_reload["meal_shopping"].values()
            accepted_meal = next(item for item in meal_transfers if item["status"] == "accepted")
            assert accepted_meal["transfer_count"] == 1
            assert accepted_meal["lines"][0]["quantity"] == 0.4
            merged_source = next(p for p in shopping_after_reload if p["status"] == "merged")
            assert merged_source["history"][-1]["action"] == "merge"
            merge_target = next(
                p for p in shopping_after_reload if p["id"] == merged_source["merged_into"]
            )
            assert merge_target["quantity"] == 3 and merge_target["purchased"] == 0.5
            assert len(entry.runtime_data.engine.view("owner")["shopping_series"]) == 1
            edited_task = next(
                task
                for task in entry.runtime_data.engine.view("owner")["tasks"]
                if task["title"] == "Synthetic reviewed task"
            )
            assert edited_task["status"] == "completed" and edited_task["due_at"] is None
            assert edited_task["checklist"] == [{"text": "Synthetic step", "done": True}]
            assert edited_task["report"] == "Synthetic corrected report"
            court_after_reload = entry.runtime_data.engine.snapshot()
            appealed = next(
                c
                for c in court_after_reload["court"].values()
                if c.get("reason") == "Synthetic disputed score"
            )
            assert appealed["status"] == "reversed"
            assert appealed["appeal"]["resolution"]["reason"] == "Synthetic independent review"
            assert len(court_after_reload["court_reports"]) == 1
            assert court_after_reload["settings"]["court"]["second_adult_review"] is True
            reward = next(iter(court_after_reload["reward_requests"].values()))
            assert reward["status"] == "fulfilled" and reward["cost"] == 6
            assert [h["status"] for h in reward["history"]] == [
                "requested",
                "approved",
                "fulfilled",
            ]
            calendar_after_reload = entry.runtime_data.engine.snapshot()["calendar"]
            assert len(calendar_after_reload) == 3
            assert not entry.runtime_data.engine.snapshot()["settings"]["calendar"]["publish_to_ha"]
            routines_after_reload = entry.runtime_data.engine.snapshot()["routine_runs"]
            assert routines_after_reload == routines_before_reload
            assert (
                routines_after_reload[active_routine["id"]]["steps"][0]["nonce"]
                == active_routine["steps"][0]["nonce"]
            )
            assert any(r["status"] == "completed" for r in routines_after_reload.values())
            # Every synthetic cohort, including guardian-presence identities, survives.
            assert {
                member["id"] for member in entry.runtime_data.engine.view("owner")["members"]
            } == set(members_before_reload)
            assert entry.runtime_data.engine.snapshot()["members"] == members_before_reload
            assert members_before_reload[school_import_child_id]["role"] == "child"
            assert members_before_reload["synthetic-presence-managed-child"]["ha_user_id"] is None
            assert members_before_reload["synthetic-presence-adult"]["role"] == "adult"
            assert await hass.config_entries.async_unload(entry.entry_id)
            assert not hass.data["family_assistant"]["entries"]
            from homeassistant.helpers import llm

            assert not any(
                api.id.startswith("family_assistant_") for api in llm.async_get_apis(hass)
            )
            print(
                "PASS: real HA config/options/service, siren renewal/tones/answer, "
                "Store/reload/unload"
            )
        finally:
            await hass.async_stop(force=True)


async def run_websocket(hass, entry, owner, child_id):
    """Real HTTP/WebSocket protocol on container loopback, not handler mocks."""
    await hass.http.start()
    child = await hass.auth.async_create_user("Synthetic child HA user")
    stranger = await hass.auth.async_create_user("Synthetic unlinked HA user")
    engine = entry.runtime_data.engine
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": child_id,
            "revision": engine.snapshot()["members"][child_id]["revision"],
            "name": "Child",
            "role": "child",
            "ha_user_id": child.id,
        },
        "ws-bind-child",
        datetime.now(UTC),
    )
    async with ClientSession() as client:
        for user, allowed in ((owner, True), (child, True), (stranger, False)):
            refresh = await hass.auth.async_create_refresh_token(
                user, client_id="https://example.invalid/synthetic-client"
            )
            token = hass.auth.async_create_access_token(refresh)
            async with client.ws_connect("http://127.0.0.1:8123/api/websocket") as ws:
                assert (await ws.receive_json())["type"] == "auth_required"
                await ws.send_json({"type": "auth", "access_token": token})
                assert (await ws.receive_json())["type"] == "auth_ok"
                await ws.send_json({"id": 1, "type": "family_assistant/households"})
                result = await ws.receive_json()
                assert result["success"]
                assert result["result"] == (
                    [{"entry_id": entry.entry_id, "title": entry.title}] if allowed else []
                )
                await ws.send_json(
                    {"id": 2, "type": "family_assistant/view", "entry_id": entry.entry_id}
                )
                result = await ws.receive_json()
                assert result["success"] == allowed
                if allowed:
                    assert result["result"]["role"] == ("owner" if user is owner else "child")
                    assert "telegram_id" not in str(result["result"])
                    assert ("network" in result["result"]) == (user is owner)
                if user is child:
                    await ws.send_json(
                        {
                            "id": 3,
                            "type": "family_assistant/execute",
                            "entry_id": entry.entry_id,
                            "action": "court.award",
                            "payload": {"member": child_id, "points": 1, "reason": "Self-award"},
                            "operation_id": "ws-forbidden",
                        }
                    )
                    result = await ws.receive_json()
                    assert not result["success"] and result["error"]["code"] == "forbidden"
                    assert not engine.snapshot()["court"]
                await ws.send_json(
                    {
                        "id": 4,
                        "type": "family_assistant/chat",
                        "entry_id": entry.entry_id,
                        "text": "/ping",
                        "operation_id": "ws-chat-" + user.id,
                        "session_id": "synthetic-session",
                        "actor_revision": engine.snapshot()["members"][
                            "owner" if user is owner else child_id
                        ]["revision"],
                        "source_revision": entry.runtime_data.assistant_revision,
                    }
                )
                result = await ws.receive_json()
                assert result["success"] == allowed
                if allowed:
                    assert ("I'm here" if user is owner else "Я тут") in result["result"][
                        "reply"
                    ], result
                await ws.send_json(
                    {
                        "id": 5,
                        "type": "family_assistant/network_refresh",
                        "entry_id": entry.entry_id,
                    }
                )
                result = await ws.receive_json()
                assert not result["success"] and result["error"]["code"] == (
                    "network_not_configured" if user is owner else "forbidden"
                )
            hass.auth.async_remove_refresh_token(refresh)
    print("PASS: actual HA WebSocket auth, household names, projections and command denial")
    # Rule times have minute precision. Keeping wall-clock seconds here could
    # put the +5-second check outside the one-minute no-catchup window.
    release = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(minutes=2)
    duty = await engine.execute(
        "owner",
        "tasks.series_save",
        {
            "title": "Synthetic rotating duty",
            "assignees": [child_id],
            "actor_revision": engine.snapshot()["members"]["owner"]["revision"],
            "creator_revision": engine.snapshot()["members"]["owner"]["revision"],
            "assignee_revisions": {child_id: engine.snapshot()["members"][child_id]["revision"]},
            "rotation": True,
            "rule": {
                "frequency": "daily",
                "start_date": release.date().isoformat(),
                "time": release.strftime("%H:%M"),
                "timezone": "UTC",
            },
            "due_time": (release + timedelta(hours=1)).strftime("%H:%M"),
        },
        "smoke-series",
        datetime.now(UTC),
    )
    shopping_series = await engine.execute(
        "owner",
        "shopping.series_save",
        {
            "name": "Synthetic recurring milk",
            "quantity": 2,
            "unit": "l",
            "rule": {
                "frequency": "daily",
                "start_date": release.date().isoformat(),
                "time": release.strftime("%H:%M"),
                "timezone": "UTC",
            },
        },
        "smoke-shopping-series",
        datetime.now(UTC),
    )
    # A manual future tick must not be dropped by a concurrent normal HA tick.
    async with asyncio.timeout(15):
        while entry.runtime_data.scheduler._busy:
            await asyncio.sleep(0.01)
        await entry.runtime_data.scheduler.run(release + timedelta(seconds=5))
    assert (
        len([t for t in engine.snapshot()["tasks"].values() if t.get("series_id") == duty["id"]])
        == 1
    )
    print("PASS: HA scheduler generated one recurring task instance")
    purchases = [
        p
        for p in engine.snapshot()["shopping"].values()
        if p.get("series_id") == shopping_series["id"]
    ]
    assert len(purchases) == 1 and purchases[0]["status"] == "approved"
    await entry.runtime_data.scheduler.run(release + timedelta(seconds=10))
    assert len(engine.view("owner")["shopping_series"]) == 1
    assert (
        len(
            [
                p
                for p in engine.snapshot()["shopping"].values()
                if p.get("series_id") == shopping_series["id"]
            ]
        )
        == 1
    )
    print("PASS: HA scheduler generated one separate recurring purchase without duplicate replay")
    manual = await engine.execute(
        "owner",
        "shopping.add",
        {"name": "Synthetic recurring milk", "unit": "l"},
        "smoke-shopping-manual",
        datetime.now(UTC),
    )
    original = purchases[0]
    partial = await engine.execute(
        "owner",
        "shopping.purchase",
        {"id": original["id"], "revision": original["revision"], "quantity": 0.5},
        "smoke-shopping-partial",
        datetime.now(UTC),
    )
    merge_payload = {
        "id": manual["id"],
        "revision": manual["revision"],
        "sources": [{"id": original["id"], "revision": partial["revision"]}],
    }
    merged = await engine.execute(
        "owner",
        "shopping.merge",
        merge_payload,
        "smoke-shopping-merge",
        datetime.now(UTC),
    )
    assert merged["quantity"] == 3 and merged["purchased"] == 0.5
    assert (
        await engine.execute(
            "owner",
            "shopping.merge",
            merge_payload,
            "smoke-shopping-merge",
            datetime.now(UTC),
        )
        == merged
    )
    assert engine.snapshot()["shopping"][original["id"]]["status"] == "merged"
    print("PASS: HA atomic shopping merge preserved partial quantities, history and replay")
    await verify_task_controls(hass, entry, owner, child_id)
    from ha_task_batch_smoke import verify_task_batch

    await verify_task_batch(hass, owner)
    await verify_court_controls(hass, entry, owner, child, child_id)


async def verify_task_controls(hass, entry, owner, child_id):
    """Dashboard-shaped task mutations through actual authenticated HA WebSocket."""
    refresh = await hass.auth.async_create_refresh_token(
        owner, client_id="https://example.invalid/task-smoke"
    )
    try:
        async with ClientSession() as client:
            async with client.ws_connect("http://127.0.0.1:8123/api/websocket") as ws:
                assert (await ws.receive_json())["type"] == "auth_required"
                await ws.send_json(
                    {"type": "auth", "access_token": hass.auth.async_create_access_token(refresh)}
                )
                assert (await ws.receive_json())["type"] == "auth_ok"
                sequence = 0

                async def command(action, payload, operation=None):
                    nonlocal sequence
                    sequence += 1
                    await ws.send_json(
                        {
                            "id": sequence,
                            "type": "family_assistant/execute",
                            "entry_id": entry.entry_id,
                            "action": "tasks." + action,
                            "payload": payload,
                            "operation_id": operation or f"task-smoke-{sequence}",
                        }
                    )
                    response = await ws.receive_json()
                    assert response["success"], response
                    return response["result"]

                item = await command(
                    "create",
                    {
                        "title": "Synthetic reviewed task",
                        "assignee": child_id,
                        "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                        "checklist": ["Synthetic step"],
                        "report_type": "text",
                    },
                )
                item = await command(
                    "check",
                    {
                        "id": item["id"],
                        "revision": item["revision"],
                        "checklist_index": 0,
                        "done": True,
                    },
                )
                item = await command("start", {"id": item["id"], "revision": item["revision"]})
                payload = {
                    "id": item["id"],
                    "revision": item["revision"],
                    "due_at": None,
                    "assignee": child_id,
                }
                item = await command("revise", payload, "task-smoke-revise")
                assert item["status"] == "in_progress" and item["due_at"] is None
                assert await command("revise", payload, "task-smoke-revise") == item
                item = await command(
                    "submit",
                    {
                        "id": item["id"],
                        "revision": item["revision"],
                        "report": "Synthetic first report",
                    },
                )
                assert item["status"] == "submitted"
                item = await command(
                    "request_changes",
                    {
                        "id": item["id"],
                        "revision": item["revision"],
                        "note": "Synthetic review note",
                    },
                )
                assert item["status"] == "needs_changes"
                item = await command(
                    "submit",
                    {
                        "id": item["id"],
                        "revision": item["revision"],
                        "report": "Synthetic corrected report",
                    },
                )
                assert item["report"] == "Synthetic corrected report"
                assert "review_note" not in item
                assert item["previous_reports"][0]["report"] == "Synthetic first report"
                assert item["previous_reports"][0]["review_note"] == "Synthetic review note"
                assert item["previous_reports"][0]["submitted_at"] <= item["submitted_at"]
                item = await command("complete", {"id": item["id"], "revision": item["revision"]})
                assert item["status"] == "completed" and item["checklist"][0]["done"]
    finally:
        hass.auth.async_remove_refresh_token(refresh)
    print("PASS: actual HA WebSocket task checklist/edit/clear/replay/report/review/completion")


async def verify_court_controls(hass, entry, owner, child, child_id):
    """Three actual authenticated HA users, independent appeal review and scheduler."""
    engine = entry.runtime_data.engine
    reviewer = await hass.auth.async_create_user("Synthetic second parent")
    reviewer_id = next(m["id"] for m in engine.view("owner")["members"] if m["role"] == "adult")
    sequence = 0

    async def request(user, action, payload, operation=None, error=None):
        nonlocal sequence
        sequence += 1
        refresh = await hass.auth.async_create_refresh_token(
            user, client_id="https://example.invalid/court-smoke"
        )
        try:
            async with (
                ClientSession() as client,
                client.ws_connect("http://127.0.0.1:8123/api/websocket") as ws,
            ):
                assert (await ws.receive_json())["type"] == "auth_required"
                await ws.send_json(
                    {"type": "auth", "access_token": hass.auth.async_create_access_token(refresh)}
                )
                assert (await ws.receive_json())["type"] == "auth_ok"
                message = {
                    "id": 1,
                    "type": "family_assistant/execute",
                    "entry_id": entry.entry_id,
                    "action": action,
                    "payload": payload,
                    "operation_id": operation or f"court-smoke-{sequence}",
                }
                if action == "view":
                    message = {"id": 1, "type": "family_assistant/view", "entry_id": entry.entry_id}
                await ws.send_json(message)
                response = await ws.receive_json()
                if error:
                    assert not response["success"] and response["error"]["code"] == error, response
                    return None
                assert response["success"], response
                return response["result"]
        finally:
            hass.auth.async_remove_refresh_token(refresh)

    await request(
        owner,
        "members.save",
        {
            "id": reviewer_id,
            "revision": engine.snapshot()["members"][reviewer_id]["revision"],
            "name": "Synthetic reviewer",
            "role": "parent",
            "ha_user_id": reviewer.id,
        },
    )
    boundary = (datetime.now(UTC) + timedelta(minutes=2)).replace(second=0, microsecond=0)
    local_boundary = boundary.astimezone(ZoneInfo(engine.snapshot()["settings"]["timezone"]))
    config = {
        "revision": 0,
        "weekly_enabled": True,
        "weekday": local_boundary.weekday(),
        "time": local_boundary.strftime("%H:%M"),
        "second_adult_review": True,
    }
    await request(child, "court.configure", config, error="forbidden")
    await request(owner, "court.configure", config)
    await request(owner, "court.configure", config, error="conflict")
    item = await request(
        owner,
        "court.award",
        {"member": child_id, "points": -2, "reason": "Synthetic disputed score"},
    )
    appeal = {"id": item["id"], "revision": item["revision"], "reason": "Synthetic appeal"}
    item = await request(child, "court.appeal", appeal)
    child_view = await request(child, "view", {})
    assert [c["id"] for c in child_view["court"]] == [item["id"]]
    assert "court_reports" not in child_view and "court_config" not in child_view
    await entry.runtime_data.scheduler.run(boundary)
    reports = engine.snapshot()["court_reports"]
    assert len(reports) == 1
    report = next(iter(reports.values()))
    assert report["events"] == [item["id"]] and report["rows"][0]["total"] == -2
    decision = {
        "id": item["id"],
        "revision": item["revision"],
        "decision": "reverse",
        "reason": "Synthetic independent review",
    }
    await request(child, "court.resolve_appeal", decision, error="forbidden")
    await request(owner, "court.resolve_appeal", decision, error="forbidden")
    await request(
        owner,
        "court.reverse",
        {k: v for k, v in decision.items() if k != "decision"},
        error="forbidden",
    )
    result = await request(reviewer, "court.resolve_appeal", decision, "court-smoke-resolve")
    assert result["status"] == "reversed" and result["reason"] == "Synthetic disputed score"
    assert (
        await request(reviewer, "court.resolve_appeal", decision, "court-smoke-resolve") == result
    )
    await entry.runtime_data.scheduler.run(boundary + timedelta(seconds=30))
    assert engine.snapshot()["court_reports"] == reports
    assert (await request(child, "view", {}))["court_summary"]["rows"][0]["total"] == 0
    print(
        "PASS: actual HA WebSocket court configuration, child appeal, "
        "independent review, replay and weekly snapshot"
    )

    await request(
        owner,
        "court.award",
        {"member": child_id, "points": 10, "reason": "Synthetic earned privilege"},
    )
    reward = await request(
        owner, "court.reward_save", {"name": "Synthetic family privilege", "cost": 6}
    )
    reservation = {"id": reward["id"], "revision": reward["revision"]}
    item = await request(child, "court.reward_request", reservation, "reward-smoke-reserve")
    assert await request(child, "court.reward_request", reservation, "reward-smoke-reserve") == item
    await request(child, "court.reward_request", reservation, error="insufficient_points")
    projected = (await request(child, "view", {}))["rewards"]
    assert projected["balances"][0]["available"] == 4 and projected["balances"][0]["reserved"] == 6
    decision = {
        "id": item["id"],
        "revision": item["revision"],
        "decision": "approve",
        "reason": "Synthetic approval",
    }
    await request(child, "court.reward_transition", decision, error="forbidden")
    item = await request(owner, "court.reward_transition", decision)
    decision.update(revision=item["revision"], decision="fulfill", reason="Synthetic provided")
    item = await request(owner, "court.reward_transition", decision, "reward-smoke-fulfill")
    assert await request(owner, "court.reward_transition", decision, "reward-smoke-fulfill") == item
    projected = (await request(child, "view", {}))["rewards"]
    assert projected["balances"][0]["spent"] == 6 and projected["balances"][0]["reserved"] == 0
    assert item["name"] == "Synthetic family privilege" and item["status"] == "fulfilled"
    print(
        "PASS: actual HA WebSocket privilege reservation, parent approval, fulfillment and replay"
    )
    await verify_calendar_controls(hass, entry, owner, child, child_id, request)
    await verify_routine_controls(hass, entry, owner, child, child_id, request)
    await verify_pantry_controls(hass, entry, owner, child, request)
    from ha_meals_smoke import verify_meals_controls

    await verify_meals_controls(hass, entry, owner, child, request)
    from ha_meal_shopping_smoke import verify_meal_shopping

    await verify_meal_shopping(hass, entry, owner, child, request)
    from ha_dietary_smoke import verify_dietary_controls

    await verify_dietary_controls(hass, entry, owner, child, child_id, request)
    from ha_shopping_edit_smoke import verify_shopping_edit

    await verify_shopping_edit(hass, entry, owner, child, child_id, request)
    from ha_shopping_price_smoke import verify_shopping_price

    await verify_shopping_price(entry, owner, child, request)


async def verify_pantry_controls(hass, entry, owner, child, request):
    """Stock remains manual and parent notes stay private through actual HA transport."""
    settings = entry.runtime_data.engine.snapshot()["settings"]
    await request(
        owner,
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": [*settings["modules"], "pantry", "school", "maintenance", "polls"],
        },
    )
    options = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": owner.id}
    )
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {"next_step_id": "general"}
    )
    schema_fields = {key.schema for key in options["data_schema"].schema}
    assert {"routines", "pantry", "school", "maintenance"} <= schema_fields
    assert "polls" in schema_fields
    options = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {
            "name": settings["name"],
            "language": settings["language"],
        },
    )
    assert options["type"] == "create_entry", options
    await hass.async_block_till_done()
    assert {"routines", "pantry", "school", "maintenance", "polls"} <= set(
        entry.runtime_data.engine.snapshot()["settings"]["modules"]
    )
    payload = {
        "name": "Synthetic pantry milk",
        "unit": "l",
        "quantity": 0.5,
        "minimum_quantity": 2,
        "note": "Synthetic parent-private pantry note",
        "expires_on": (datetime.now(UTC) + timedelta(days=3)).date().isoformat(),
    }
    await request(child, "pantry.item_save", payload, error="forbidden")
    item = await request(owner, "pantry.item_save", payload)
    # A WebSocket write schedules background reconciliation. Scheduler.run is
    # deliberately single-flight and can return while that earlier tick still
    # owns the lock; first drain it before forcing the assertion's clock pass.
    await hass.async_block_till_done()
    await entry.runtime_data.scheduler.run(datetime.now(UTC))
    assert "scheduler" not in entry.runtime_data.health
    parent_view = (await request(owner, "view", {}))["pantry"]
    child_view = (await request(child, "view", {}))["pantry"]
    assert child_view["items"][0]["expiry_status"] == "expiring"
    assert "note" not in child_view["items"][0] and child_view["suggestions"] == []
    proposal = next(p for p in parent_view["suggestions"] if p["status"] == "open")
    accept = {"id": proposal["id"], "revision": proposal["revision"]}
    await request(child, "pantry.suggestion_accept", accept, error="forbidden")
    result = await request(owner, "pantry.suggestion_accept", accept, "pantry-ha-accept")
    assert result["status"] == "accepted"
    assert await request(owner, "pantry.suggestion_accept", accept, "pantry-ha-accept") == result
    child_data = await request(child, "view", {})
    assert "Synthetic parent-private pantry note" not in str(child_data)
    purchase = next(s for s in child_data["shopping"] if s["id"] == result["shopping_id"])
    assert purchase["quantity"] == 1.5 and purchase["purchased"] == 0 and purchase["note"] == ""
    assert entry.runtime_data.engine.snapshot()["pantry"]["items"][item["id"]]["quantity"] == 0.5
    print(
        "PASS: actual HA pantry privacy, stock proposals, shopping-only acceptance "
        "and options preservation"
    )


async def verify_calendar_controls(hass, entry, owner, child, child_id, request):
    """Opt-in HA projection has no private events and cannot bypass family authorization."""
    from homeassistant.components.calendar.const import DATA_COMPONENT as CALENDAR_COMPONENT
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import entity_registry as er

    settings = entry.runtime_data.engine.snapshot()["settings"]
    await request(
        owner,
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": [*settings["modules"], "calendar"],
        },
    )
    unique_id = f"{entry.entry_id}_family_calendar"
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("calendar", "family_assistant", unique_id) is None
    start = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    payload = {
        "title": "Synthetic private appointment",
        "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(),
        "visibility": "participants",
    }
    private = await request(child, "calendar.save", payload, "calendar-private-create")
    assert private["status"] == "tentative"
    assert await request(child, "calendar.save", payload, "calendar-private-create") == private
    private = await request(
        owner,
        "calendar.approve",
        {
            "id": private["id"],
            "revision": private["revision"],
            "reason": "Synthetic approval",
        },
    )
    assert private["participants"] == [child_id] and private["status"] == "confirmed"
    shared_payload = {**payload, "title": "Synthetic shared visit", "visibility": "family"}
    shared = await request(owner, "calendar.save", shared_payload)
    all_day_start = (start + timedelta(days=1)).date()
    await request(
        owner,
        "calendar.save",
        {
            "title": "Synthetic all-day trip",
            "all_day": True,
            "start": all_day_start.isoformat(),
            "end": (all_day_start + timedelta(days=1)).isoformat(),
        },
    )
    config = {"revision": 0, "publish_to_ha": True}
    await request(child, "calendar.configure", config, error="forbidden")
    await request(owner, "calendar.configure", config, error="confirmation_required")
    await request(owner, "calendar.configure", {**config, "confirm_public_visibility": True})
    await hass.async_block_till_done()
    entity_id = registry.async_get_entity_id("calendar", "family_assistant", unique_id)
    assert entity_id and hass.states.get(entity_id).state == "off"
    entity = hass.data[CALENDAR_COMPONENT].get_entity(entity_id)
    assert entity.supported_features == 0
    events = await entity.async_get_events(
        hass, start - timedelta(hours=1), start + timedelta(days=3)
    )
    assert [e.summary for e in events] == ["Synthetic shared visit", "Synthetic all-day trip"]
    assert type(events[1].start).__name__ == "date" and type(events[0].start) is datetime
    assert entity.event.uid == shared["id"]
    # All-day queries use HA's timezone, even if household/event timezone differs.
    midnight = datetime.combine(all_day_start, datetime.min.time(), UTC)
    assert await entity.async_get_events(hass, midnight - timedelta(hours=1), midnight) == []
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": entity_id,
            "start_date_time": start.isoformat(),
            "end_date_time": (start + timedelta(days=3)).isoformat(),
        },
        blocking=True,
        return_response=True,
        context=Context(user_id=owner.id),
    )
    assert len(response[entity_id]["events"]) == 2
    try:
        await hass.services.async_call(
            "calendar",
            "create_event",
            {
                "entity_id": entity_id,
                "summary": "Must not bypass family permissions",
                "start_date_time": start.isoformat(),
                "end_date_time": (start + timedelta(hours=1)).isoformat(),
            },
            blocking=True,
            context=Context(user_id=owner.id),
        )
    except HomeAssistantError:
        pass
    else:
        raise AssertionError("The read-only calendar accepted a mutation")
    await request(owner, "calendar.configure", {"revision": 1, "publish_to_ha": False})
    await hass.async_block_till_done()
    assert entity.event is None and not entity.available
    assert "message" not in hass.states.get(entity_id).attributes
    assert await entity.async_get_events(hass, start, start + timedelta(days=3)) == []
    linked_task = next(
        task
        for task in entry.runtime_data.engine.snapshot()["tasks"].values()
        if task["assignee"] == child_id
    )
    rule = {
        "frequency": "weekly",
        "interval": 2,
        "start_date": start.date().isoformat(),
        "time": "09:00",
        "timezone": "UTC",
        "weekdays": [start.weekday()],
        "month_day": 31,
        "until": (start + timedelta(days=90)).date().isoformat(),
        "exceptions": [(start + timedelta(days=14)).date().isoformat()],
        "catchup_hours": 0,
    }
    edited = await request(
        child,
        "calendar.save",
        {
            **payload,
            "id": private["id"],
            "revision": private["revision"],
            "timezone": "UTC",
            "rule": rule,
            "task_ids": [linked_task["id"]],
        },
        "calendar-recurring-edit",
    )
    assert edited["rule"] == rule and edited["task_ids"] == [linked_task["id"]]
    assert edited["status"] == "tentative"
    renamed = await request(
        child,
        "calendar.save",
        {
            "id": edited["id"],
            "revision": edited["revision"],
            "title": "Synthetic renamed series",
            "start": edited["start"],
            "end": edited["end"],
        },
    )
    assert renamed["rule"] == rule and renamed["task_ids"] == [linked_task["id"]]
    assert await entity.async_get_events(hass, start, start + timedelta(days=3)) == []
    print("PASS: actual HA recurring calendar edit preserves rules, links and private approval")
    print("PASS: actual HA calendar opt-in, approval, privacy, date types, read-only and revoke")


async def verify_routine_controls(hass, entry, owner, child, child_id, request):
    """Actual HA state reports, authenticated ordered steps, private callbacks and reload data."""
    from ha_telegram_smoke import SyntheticTelegram, process_current

    from custom_components.family_assistant.telegram.manager import TelegramManager
    from custom_components.family_assistant.telegram.messages import render
    from custom_components.family_assistant.telegram.routines import callback

    settings = entry.runtime_data.engine.snapshot()["settings"]
    await request(
        owner,
        "settings.save",
        {
            "name": settings["name"],
            "language": settings["language"],
            "modules": [*settings["modules"], "routines"],
        },
    )
    config = {"revision": 0, "entity_allowlist": ["binary_sensor.synthetic_routine"]}
    await request(child, "routines.configure", config, error="forbidden")
    await request(owner, "routines.configure", config)
    condition = {
        "kind": "entity_state",
        "entity_id": "binary_sensor.synthetic_routine",
        "state": "on",
    }
    owner_member = entry.runtime_data.engine.actor_for_ha(owner.id)
    payload = {
        "title": "Synthetic ordered morning",
        "assignees": [child_id],
        "skip_when": {
            "kind": "all",
            "conditions": [
                {"kind": "mode", "mode": "holidays"},
                {
                    "kind": "any",
                    "conditions": [
                        {
                            "kind": "time_window",
                            "start": "22:00",
                            "end": "08:00",
                            "timezone": "UTC",
                        },
                        {**condition, "negate": True},
                    ],
                },
            ],
        },
        "steps": [
            {"title": "Synthetic preparation"},
            {
                "title": "Synthetic readiness observation",
                "confirmation": "entity_state",
                "completion_condition": condition,
            },
            {"title": "Synthetic parent handoff", "assignee": owner_member},
        ],
    }
    await request(child, "routines.save", payload, error="forbidden")
    template = await request(owner, "routines.save", payload, "routine-ha-save")
    retained_condition = template["skip_when"]
    assert retained_condition["conditions"][1]["conditions"][1]["negate"] is True
    renamed = {k: v for k, v in payload.items() if k != "skip_when"}
    renamed.update(
        id=template["id"], revision=template["revision"], title="Synthetic renamed routine"
    )
    template = await request(owner, "routines.save", renamed, "routine-ha-rename")
    assert template["skip_when"] == retained_condition
    run = await request(
        child,
        "routines.start",
        {"id": template["id"], "revision": template["revision"], "member": child_id},
    )
    assert run["steps"][0]["status"] == "active" and run["steps"][1]["status"] == "pending"
    snapshot = entry.runtime_data.engine.snapshot()
    event = next(e for e in snapshot["outbox"].values() if e["key"] == "routine_step")
    message = render(event, {"id": 12345, "language": "uk"}, snapshot)
    encoded = message["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    confirmation = callback(encoded)
    await request(owner, "routines.confirm", confirmation, error="forbidden")
    receiver = TelegramManager(
        hass,
        entry,
        entry.runtime_data,
        SyntheticTelegram(None, None),
        {"id": 1000, "username": "synthetic_family_bot"},
    )
    tg_user = snapshot["members"][child_id]["telegram_id"]
    update = {
        "update_id": 4900,
        "callback_query": {
            "id": "synthetic-routine-confirm",
            "from": {"id": tg_user, "is_bot": False},
            "data": encoded,
            "message": {
                "message_id": 6010,
                "chat": {"id": tg_user, "type": "private"},
                "from": {"id": 1000},
            },
        },
    }
    await process_current(entry.runtime_data, receiver, update)
    run = entry.runtime_data.engine.snapshot()["routine_runs"][run["id"]]
    assert run["steps"][0]["status"] == "completed"
    await process_current(entry.runtime_data, receiver, update)
    assert entry.runtime_data.engine.snapshot()["routine_runs"][run["id"]] == run
    assert run["steps"][1]["status"] == "active"
    hass.states.async_set("binary_sensor.synthetic_routine", "unavailable")
    await entry.runtime_data.scheduler.run(datetime.now(UTC))
    assert entry.runtime_data.engine.snapshot()["routine_runs"][run["id"]]["status"] == "active"
    hass.states.async_set("binary_sensor.synthetic_routine", "on")
    await entry.runtime_data.scheduler.run(datetime.now(UTC))
    current = entry.runtime_data.engine.snapshot()["routine_runs"][run["id"]]
    assert current["status"] == "active" and current["steps"][2]["member"] == owner_member
    projected = (await request(child, "view", {}))["routines"]
    assert "entity_allowlist" not in projected["config"]
    assert "completion_condition" not in projected["runs"][0]["steps"][1]
    assert "nonce" not in projected["runs"][0]["steps"][2]
    handoff = {
        "id": current["id"],
        "revision": current["revision"],
        "step": 2,
        "nonce": current["steps"][2]["nonce"],
    }
    await request(child, "routines.confirm", handoff, error="forbidden")
    completed = await request(owner, "routines.confirm", handoff, "routine-parent-handoff")
    assert completed["status"] == "completed"
    assert await request(owner, "routines.confirm", handoff, "routine-parent-handoff") == completed
    assert any(
        e["recipient"] == owner_member and e["key"] == "routine_step" and e["data"]["step"] == 2
        for e in entry.runtime_data.engine.snapshot()["outbox"].values()
    )
    # Leave one current manual nonce in Store and verify it survives a real entry reload.
    active = await request(
        child,
        "routines.start",
        {"id": template["id"], "revision": template["revision"], "member": child_id},
    )
    assert active["status"] == "active" and active["steps"][0]["nonce"]
    print(
        "PASS: actual HA ordered routines, parent handoff, approved observations, "
        "nonce replay and privacy"
    )


if __name__ == "__main__":
    asyncio.run(main())
