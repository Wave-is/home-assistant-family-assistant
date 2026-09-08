"""Real Home Assistant HTTP checks for private maintenance fault photos."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from aiohttp import ClientSession
from ha_media_smoke import (
    _assert_forbidden,
    _command,
    _http,
    _image,
    _token,
    _view,
    _websocket,
)
from homeassistant.auth.const import GROUP_ID_ADMIN


def _settings_payload(settings: dict, modules: list[str]) -> dict:
    optional = {
        "automatic_penalties",
        "daily_penalty_cap",
        "timezone",
        "pantry_expiry_reminders",
        "pantry_expiry_days",
        "school_preparation_reminders",
        "school_preparation_days_before",
        "school_preparation_time",
        "digest_morning_enabled",
        "digest_morning_time",
        "digest_evening_enabled",
        "digest_evening_time",
        "digest_weekly_enabled",
        "digest_weekly_weekday",
        "digest_weekly_time",
    }
    return {
        "name": settings["name"],
        "language": settings["language"],
        "modules": list(modules),
        **{key: settings[key] for key in optional if key in settings},
    }


async def verify_fault_photos(hass, entry, owner, child_id):
    """Exercise real HTTP upload, fault photo attachment, access gates and purge."""
    runtime = entry.runtime_data
    engine = runtime.engine
    initial_snapshot = engine.snapshot()
    initial_settings = initial_snapshot["settings"]

    # 1. Enable maintenance/tasks preserving settings
    current_modules = list(initial_settings["modules"])
    needed_modules = list(dict.fromkeys([*current_modules, "maintenance", "tasks"]))
    sequence = 700
    if set(current_modules) != set(needed_modules):
        sequence += 1
        await _command(
            hass,
            entry,
            owner,
            sequence,
            "settings.save",
            _settings_payload(initial_settings, needed_modules),
            "ha-fault-photos-enable-modules",
        )
    assert {"maintenance", "tasks"} <= set(engine.snapshot()["settings"]["modules"])

    child_record = engine.snapshot()["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None

    admin = await hass.auth.async_create_user(
        "Synthetic unlinked fault photo observer", group_ids=[GROUP_ID_ADMIN]
    )

    try:
        # 2. Create reportable asset
        owner_record = engine.snapshot()["members"]["owner"]
        sequence += 1
        asset_payload = {
            "name": "Synthetic ventilation unit",
            "category": "Ventilation",
            "location": "Utility room",
            "responsible_member": "owner",
            "responsible_member_revision": owner_record["revision"],
            "warranty": {
                "expires_on": "2027-09-07",
                "vendor": "Synthetic vendor",
                "reference": "SYNTHETIC_FAULT_PHOTO_WARRANTY",
            },
            "consumables": [],
            "note": "Synthetic asset private maintenance note",
            "reportable": True,
        }
        asset = await _command(
            hass,
            entry,
            owner,
            sequence,
            "maintenance.asset_save",
            asset_payload,
            "ha-fault-photo-asset-create",
        )
        assert set(asset) == {"id", "revision", "status"}
        assert asset["status"] == "active"
        asset_id = asset["id"]

        # 3. Create child-reported fault
        child_record = engine.snapshot()["members"][child_id]
        sequence += 1
        fault_payload = {
            "asset_id": asset_id,
            "asset_revision": asset["revision"],
            "reporter_member_revision": child_record["revision"],
            "summary": "Synthetic noisy motor observation",
            "details": "Synthetic observation only; no diagnosis",
            "attachment_ids": [],
        }
        fault = await _command(
            hass,
            entry,
            child,
            sequence,
            "maintenance.fault_report",
            fault_payload,
            "ha-fault-photo-report",
        )
        assert set(fault) == {"id", "revision", "status", "task_id"}
        assert fault["status"] == "reported"
        fault_task_id = fault["task_id"]
        fault_task = engine.snapshot()["tasks"][fault_task_id]
        assert fault_task["status"] == "assigned"
        protected = {
            key: deepcopy(engine.snapshot()[key])
            for key in ("tasks", "outbox", "court", "alarm_runs", "routine_runs")
        }

        # 4. Reserve actual PNG media
        child_record = engine.snapshot()["members"][child_id]
        sequence += 1
        reserve_payload = {
            "purpose": "maintenance_fault",
            "fault_id": fault["id"],
            "fault_revision": fault["revision"],
            "uploader_revision": child_record["revision"],
        }
        reserved = await _command(
            hass,
            entry,
            child,
            sequence,
            "media.reserve",
            reserve_payload,
            "ha-fault-photo-reserve",
        )
        assert reserved == {
            "id": reserved["id"],
            "revision": 1,
            "status": "reserved",
        }
        url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{reserved['id']}"
        body = _image("PNG")

        async with (
            _token(hass, owner) as owner_token,
            _token(hass, child) as child_token,
            _token(hass, admin) as admin_token,
            ClientSession() as session,
        ):
            # Unrelated HA administrator cannot upload
            status, _, denied_upload = await _http(
                session,
                "PUT",
                url,
                admin_token,
                1,
                body=body,
                content_type="image/png",
            )
            _assert_forbidden(status, denied_upload)
            assert body not in denied_upload

            # 5. Upload actual PNG via HTTP (revision 1 -> 2)
            status, _, raw = await _http(
                session,
                "PUT",
                url,
                child_token,
                1,
                body=body,
                content_type="image/png",
            )
            assert status == 200, (status, raw)
            available = json.loads(raw)
            assert available == {
                "id": reserved["id"],
                "revision": 2,
                "status": "available",
            }
            stored = engine.snapshot()["media"][reserved["id"]]
            assert stored["mime_type"] == "image/png"
            assert stored["size_bytes"] == len(body)
            assert stored["sha256"] == hashlib.sha256(body).hexdigest()
            assert stored["status"] == "available"

            # 6. Available uploader only: pending bytes remain uploader-private
            status, _, denied_owner = await _http(session, "GET", url, owner_token, 2)
            _assert_forbidden(status, denied_owner)
            assert body not in denied_owner

            status, _, denied_admin = await _http(session, "GET", url, admin_token, 2)
            _assert_forbidden(status, denied_admin)
            assert body not in denied_admin

            status, headers, downloaded = await _http(session, "GET", url, child_token, 2)
            assert status == 200 and downloaded == body
            assert headers["Content-Type"].split(";", 1)[0] == "image/png"

            # 7. Attach via execute
            child_record = engine.snapshot()["members"][child_id]
            sequence += 1
            attach_payload = {
                "id": fault["id"],
                "revision": fault["revision"],
                "actor_member_revision": child_record["revision"],
                "media": {"id": reserved["id"], "revision": 2},
            }
            attached = await _command(
                hass,
                entry,
                child,
                sequence,
                "maintenance.fault_photo_attach",
                attach_payload,
                "ha-fault-photo-attach",
            )
            assert attached == {
                "id": fault["id"],
                "revision": 2,
                "status": "reported",
            }
            # Verify idempotent replay
            assert (
                await _command(
                    hass,
                    entry,
                    child,
                    sequence,
                    "maintenance.fault_photo_attach",
                    attach_payload,
                    "ha-fault-photo-attach",
                )
                == attached
            )

            # 8. Authorized parent/child GET, unrelated HA user denied
            # Owner GET
            status, headers, downloaded = await _http(session, "GET", url, owner_token, 3)
            assert status == 200 and downloaded == body
            assert headers["Content-Type"].split(";", 1)[0] == "image/png"
            assert {part.strip() for part in headers["Cache-Control"].split(",")} >= {
                "private",
                "no-store",
            }
            assert headers["Pragma"] == "no-cache"
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
            assert headers["Content-Disposition"].startswith("attachment;")
            assert reserved["id"] not in headers["Content-Disposition"]
            assert headers["Content-Length"] == str(len(body))
            assert "Content-Range" not in headers and "Accept-Ranges" not in headers

            # Child GET
            status, headers, downloaded = await _http(session, "GET", url, child_token, 3)
            assert status == 200 and downloaded == body
            assert headers["Content-Type"].split(";", 1)[0] == "image/png"

            # Unrelated HA user denied
            status, _, denied_admin = await _http(session, "GET", url, admin_token, 3)
            _assert_forbidden(status, denied_admin)
            assert body not in denied_admin

            # 9. Fault photo not task completion
            # Fault task status remains open and uncompleted
            task_snapshot = engine.snapshot()["tasks"][fault_task_id]
            assert task_snapshot["status"] == "assigned"
            assert task_snapshot["status"] != "completed"
            assert task_snapshot.get("report_media") in (None, [])
            for key, expected in protected.items():
                assert engine.snapshot()[key] == expected

            # Attempting to submit the fault photo as a task completion report fails
            sequence += 1
            photo_task = await _command(
                hass,
                entry,
                owner,
                sequence,
                "tasks.create",
                {
                    "title": "Synthetic photo completion check",
                    "assignee": child_id,
                    "report_type": "photo",
                },
                "ha-fault-photo-task-check",
            )
            sequence += 1
            denied_task_submit = await _websocket(
                hass,
                entry,
                child,
                {
                    "id": sequence,
                    "type": "family_assistant/execute",
                    "entry_id": entry.entry_id,
                    "action": "tasks.submit",
                    "payload": {
                        "id": photo_task["id"],
                        "revision": photo_task["revision"],
                        "media": {"id": reserved["id"], "revision": 3},
                    },
                    "operation_id": "ha-fault-photo-wrong-purpose",
                },
            )
            assert not denied_task_submit["success"]
            assert denied_task_submit["error"]["code"] == "invalid_field", denied_task_submit
            assert engine.snapshot()["tasks"][fault_task_id]["status"] == "assigned"

            # Projections verify attached metadata without leaking private hashes or keys
            sequence += 1
            owner_view = await _view(hass, entry, owner, sequence)
            sequence += 1
            child_view = await _view(hass, entry, child, sequence)
            for view in (owner_view, child_view):
                fault_row = next(f for f in view["maintenance"]["faults"] if f["id"] == fault["id"])
                assert fault_row["photo_attachment"] == {
                    "id": reserved["id"],
                    "revision": 3,
                    "purpose": "maintenance_fault",
                    "mime_type": "image/png",
                    "size_bytes": len(body),
                    "status": "attached",
                }
                assert "blob_key" not in repr(fault_row) and "sha256" not in repr(fault_row)
            child_fault_row = next(
                f for f in child_view["maintenance"]["faults"] if f["id"] == fault["id"]
            )
            assert "photo_history" not in child_fault_row

            # Non-owners cannot purge
            sequence += 1
            denied_purge = await _websocket(
                hass,
                entry,
                child,
                {
                    "id": sequence,
                    "type": "family_assistant/execute",
                    "entry_id": entry.entry_id,
                    "action": "maintenance.fault_photo_purge",
                    "payload": {
                        "id": fault["id"],
                        "revision": 2,
                        "actor_member_revision": child_record["revision"],
                        "media": {"id": reserved["id"], "revision": 3},
                        "reason": "Child cannot purge",
                    },
                    "operation_id": "ha-fault-photo-purge-denied",
                },
            )
            assert not denied_purge["success"] and denied_purge["error"]["code"] == "forbidden"

            # 10. Owner purge revokes GET immediately
            sequence += 1
            owner_record = engine.snapshot()["members"]["owner"]
            purge_reason = "Synthetic explicit owner photo purge"
            purge_payload = {
                "id": fault["id"],
                "revision": 2,
                "actor_member_revision": owner_record["revision"],
                "media": {"id": reserved["id"], "revision": 3},
                "reason": purge_reason,
            }
            purged = await _command(
                hass,
                entry,
                owner,
                sequence,
                "maintenance.fault_photo_purge",
                purge_payload,
                "ha-fault-photo-purge",
            )
            assert purged == {
                "id": fault["id"],
                "revision": 3,
                "status": "reported",
            }

            # Immediate read revocation at commit for all actors
            status, _, denied_owner = await _http(session, "GET", url, owner_token, 3)
            assert status != 200 and body not in denied_owner

            status, _, denied_child = await _http(session, "GET", url, child_token, 3)
            assert status != 200 and body not in denied_child

            # 11. Persisted data remains consistent
            snapshot_after_purge = engine.snapshot()
            purged_fault = snapshot_after_purge["maintenance"]["faults"][fault["id"]]
            assert purged_fault["attachment_ids"] == []
            assert len(purged_fault["photo_history"]) == 2
            assert purged_fault["photo_history"][-1]["action"] == "fault_photo_purge"
            assert purged_fault["photo_history"][-1]["reason"] == purge_reason
            assert purged_fault["photo_history"][-1]["actor"] == "owner"
            assert purged_fault["photo_purge"] == {
                "media_id": reserved["id"],
                "reason": purge_reason,
                "actor": "owner",
                "actor_member_revision": owner_record["revision"],
                "at": purged_fault["photo_purge"]["at"],
            }
            # Task remains open and untouched
            assert snapshot_after_purge["tasks"][fault_task_id]["status"] == "assigned"
            assert snapshot_after_purge["tasks"][fault_task_id]["source"]["fault_id"] == fault["id"]

            # Media status is deleting
            media_record = snapshot_after_purge["media"][reserved["id"]]
            assert media_record["status"] == "deleting"
            assert media_record["revision"] == 4

            # Blob is still on disk until collector unlinks it
            blob = runtime.media.root / media_record["blob_key"]
            assert await hass.async_add_executor_job(blob.is_file)

            # Collector cleans up blob and marks media as deleted
            await runtime.media.collect()
            assert not await hass.async_add_executor_job(blob.exists)
            assert engine.snapshot()["media"][reserved["id"]]["status"] == "deleted"

            # Replay of owner purge succeeds idempotently
            sequence += 1
            assert (
                await _command(
                    hass,
                    entry,
                    owner,
                    sequence,
                    "maintenance.fault_photo_purge",
                    purge_payload,
                    "ha-fault-photo-purge",
                )
                == purged
            )

            # Views after purge do not contain attachment and child view omits history/reason
            sequence += 1
            owner_view_after = await _view(hass, entry, owner, sequence)
            sequence += 1
            child_view_after = await _view(hass, entry, child, sequence)
            owner_fault_row = next(
                f for f in owner_view_after["maintenance"]["faults"] if f["id"] == fault["id"]
            )
            child_fault_row = next(
                f for f in child_view_after["maintenance"]["faults"] if f["id"] == fault["id"]
            )
            assert owner_fault_row.get("photo_attachment") is None
            assert child_fault_row.get("photo_attachment") is None
            assert "photo_history" not in child_fault_row
            assert purge_reason not in json.dumps(child_view_after)

            # Keep a second real image attached for the enclosing Store/reload gate.
            reserved_again = await _command(
                hass,
                entry,
                child,
                900,
                "media.reserve",
                {**reserve_payload, "fault_revision": 3},
                "ha-fault-photo-reserve-again",
            )
            second_url = (
                "http://127.0.0.1:8123/api/family_assistant/media/"
                f"{entry.entry_id}/{reserved_again['id']}"
            )
            status, _, _ = await _http(
                session, "PUT", second_url, child_token, 1, body=body, content_type="image/png"
            )
            assert status == 200
            await _command(
                hass,
                entry,
                child,
                901,
                "maintenance.fault_photo_attach",
                {
                    **attach_payload,
                    "revision": 3,
                    "media": {"id": reserved_again["id"], "revision": 2},
                },
                "ha-fault-photo-attach-again",
            )
    finally:
        await hass.auth.async_remove_user(admin)

    print(
        "PASS: actual HA maintenance fault photo upload, uploader privacy, "
        "attachment, authorized GET, task completion separation, owner purge revocation"
    )
    return {
        "asset_id": asset_id,
        "fault_id": fault["id"],
        "media_id": reserved_again["id"],
        "task_id": fault_task_id,
        "fault": deepcopy(engine.snapshot()["maintenance"]["faults"][fault["id"]]),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


async def verify_fault_photos_reload(hass, entry, owner, child_id, expected):
    """Read the exact attached fault image through fresh HTTP authority after Store reload."""
    state = entry.runtime_data.engine.snapshot()
    assert state["maintenance"]["faults"][expected["fault_id"]] == expected["fault"]
    assert len(expected["fault"]["photo_history"]) == 3
    assert state["tasks"][expected["task_id"]]["status"] == "assigned"
    child = await hass.auth.async_get_user(state["members"][child_id]["ha_user_id"])
    url = (
        f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{expected['media_id']}"
    )
    for user in (owner, child):
        async with _token(hass, user) as token, ClientSession() as session:
            status, _, body = await _http(session, "GET", url, token, 3)
            assert status == 200 and hashlib.sha256(body).hexdigest() == expected["sha256"]
    print("PASS: fault photo metadata, history and private authenticated bytes after Store reload")
