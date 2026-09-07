"""Real HA owner-reviewed photo removal without task or other-blob deletion."""

from __future__ import annotations

import json
from copy import deepcopy

from aiohttp import ClientSession
from ha_media_smoke import _command, _http, _image, _token, _websocket


async def verify_media_retention(hass, entry, owner, child_id):
    runtime = entry.runtime_data
    child_record = runtime.engine.snapshot()["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None
    task = await _command(
        hass,
        entry,
        owner,
        1,
        "tasks.create",
        {
            "title": "Synthetic disposable photo report",
            "assignee": child_id,
            "report_type": "photo",
        },
        "retention-create",
    )
    media = await _command(
        hass,
        entry,
        child,
        2,
        "media.reserve",
        {
            "purpose": "task_report",
            "task_id": task["id"],
            "task_revision": task["revision"],
            "uploader_revision": child_record["revision"],
        },
        "retention-reserve",
    )
    url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{media['id']}"
    async with (
        _token(hass, child) as child_token,
        _token(hass, owner) as owner_token,
        ClientSession() as session,
    ):
        status, _, body = await _http(
            session, "PUT", url, child_token, 1, body=_image("PNG"), content_type="image/png"
        )
        assert status == 200 and json.loads(body)["status"] == "available"
        submitted = await _command(
            hass,
            entry,
            child,
            3,
            "tasks.submit",
            {
                "id": task["id"],
                "revision": task["revision"],
                "media": {"id": media["id"], "revision": 2},
            },
            "retention-submit",
        )
        before = runtime.engine.snapshot()
        protected = {key: deepcopy(before[key]) for key in ("court", "shopping", "outbox")}
        payload = {
            "id": task["id"],
            "revision": submitted["revision"],
            "report_generation": before["tasks"][task["id"]]["report_generation"],
            "media_id": media["id"],
            "media_revision": 3,
            "reason": "Synthetic explicit owner retention review",
            "confirmed": True,
        }
        denied = await _websocket(
            hass,
            entry,
            child,
            {
                "id": 4,
                "type": "family_assistant/execute",
                "entry_id": entry.entry_id,
                "action": "tasks.report_media_purge",
                "payload": payload,
                "operation_id": "retention-child-denied",
            },
        )
        assert not denied["success"] and denied["error"]["code"] == "forbidden"
        purged = await _command(
            hass, entry, owner, 5, "tasks.report_media_purge", payload, "retention-purge"
        )
        assert purged["status"] == submitted["status"] == "submitted"
        # Access stops at Store commit, not only when collector unlinks later.
        status, _, denied_body = await _http(session, "GET", url, owner_token, 3)
        assert status != 200 and _image("PNG") not in denied_body
        after = runtime.engine.snapshot()
        assert {key: after[key] for key in protected} == protected
        assert "report_media_purged_at" in after["tasks"][task["id"]]
        assert "report_media" not in after["tasks"][task["id"]]
        blob = runtime.media.root / before["media"][media["id"]]["blob_key"]
        await runtime.media.collect()
        assert not await hass.async_add_executor_job(blob.exists)
        assert runtime.engine.snapshot()["media"][media["id"]]["status"] == "deleted"
        assert (
            await _command(
                hass, entry, owner, 6, "tasks.report_media_purge", payload, "retention-purge"
            )
            == purged
        )
        # The existing verified reports remain intact and readable on disk.
        for record_id, record in before["media"].items():
            if record_id == media["id"] or record.get("status") != "attached":
                continue
            path = runtime.media.root / record["blob_key"]
            assert await hass.async_add_executor_job(path.is_file)
    print(
        "PASS: actual HA explicit owner photo purge, immediate read revocation, "
        "collector and exact replay"
    )
