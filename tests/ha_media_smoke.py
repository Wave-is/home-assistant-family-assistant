"""Actual Home Assistant HTTP checks for private task-report media."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from hashlib import sha256
from io import BytesIO

from aiohttp import ClientSession
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.util import dt as dt_util


@asynccontextmanager
async def _token(hass, user):
    refresh = await hass.auth.async_create_refresh_token(
        user, client_id="https://example.invalid/media-smoke"
    )
    try:
        yield hass.auth.async_create_access_token(refresh)
    finally:
        hass.auth.async_remove_refresh_token(refresh)


async def _websocket(hass, entry, user, message):
    async with _token(hass, user) as token, ClientSession() as session:
        ws = await session.ws_connect("http://127.0.0.1:8123/api/websocket")
        try:
            assert (await ws.receive_json())["type"] == "auth_required"
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"
            await ws.send_json(message)
            return await ws.receive_json()
        finally:
            await ws.close()


async def _command(hass, entry, user, identifier, action, payload, operation):
    response = await _websocket(
        hass,
        entry,
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
    assert response["success"], response
    return response["result"]


async def _view(hass, entry, user, identifier):
    response = await _websocket(
        hass,
        entry,
        user,
        {
            "id": identifier,
            "type": "family_assistant/view",
            "entry_id": entry.entry_id,
        },
    )
    assert response["success"], response
    return response["result"]


def _image(format_name):
    from PIL import Image

    output = BytesIO()
    image = Image.new("RGB", (7, 5), (37, 83, 149))
    image.putpixel((3, 2), (211, 19, 71))
    image.save(output, format=format_name)
    return output.getvalue()


def _settings_payload(settings, modules):
    optional = {
        "automatic_penalties",
        "daily_penalty_cap",
        "timezone",
        "pantry_expiry_reminders",
        "pantry_expiry_days",
        "school_preparation_reminders",
        "school_preparation_days_before",
        "school_preparation_time",
    }
    return {
        "name": settings["name"],
        "language": settings["language"],
        "modules": list(modules),
        **{key: settings[key] for key in optional if key in settings},
    }


async def _http(session, method, url, token, revision, *, body=None, content_type=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Family-Media-Revision": str(revision),
    }
    if content_type is not None:
        headers["Content-Type"] = content_type
    async with session.request(method, url, headers=headers, data=body) as response:
        content = await response.read()
        return response.status, dict(response.headers), content


def _assert_forbidden(status, content):
    assert status == 403
    assert json.loads(content) == {"code": "forbidden"}


async def verify_media(hass, entry, owner, child_id):
    """Exercise real decoding, private HTTP authorization and Store persistence."""
    from custom_components.family_assistant.assistant.plans import projection
    from custom_components.family_assistant.runtime import safe_diagnostics

    runtime = entry.runtime_data
    engine = runtime.engine
    initial = engine.snapshot()
    child_record = initial["members"][child_id]
    child = await hass.auth.async_get_user(child_record["ha_user_id"])
    assert child is not None
    admin = await hass.auth.async_create_user(
        "Synthetic unlinked media administrator", group_ids=[GROUP_ID_ADMIN]
    )
    created = []
    sequence = 900
    try:
        async with (
            _token(hass, owner) as owner_token,
            _token(hass, child) as child_token,
            _token(hass, admin) as admin_token,
            ClientSession() as session,
        ):
            for format_name, mime_type in (
                ("PNG", "image/png"),
                ("JPEG", "image/jpeg"),
                ("WEBP", "image/webp"),
            ):
                sequence += 1
                task = await _command(
                    hass,
                    entry,
                    owner,
                    sequence,
                    "tasks.create",
                    {
                        "title": f"Synthetic private {format_name} report",
                        "assignee": child_id,
                        "report_type": "photo",
                    },
                    f"ha-media-task-{format_name.lower()}",
                )
                child_record = engine.snapshot()["members"][child_id]
                sequence += 1
                reserved = await _command(
                    hass,
                    entry,
                    child,
                    sequence,
                    "media.reserve",
                    {
                        "purpose": "task_report",
                        "task_id": task["id"],
                        "task_revision": task["revision"],
                        "uploader_revision": child_record["revision"],
                    },
                    f"ha-media-reserve-{format_name.lower()}",
                )
                assert reserved == {
                    "id": reserved["id"],
                    "revision": 1,
                    "status": "reserved",
                }
                url = (
                    "http://127.0.0.1:8123/api/family_assistant/media/"
                    f"{entry.entry_id}/{reserved['id']}"
                )
                body = _image(format_name)

                # A linked HA administrator is not implied by HA's admin bit.
                status, _, denied = await _http(
                    session,
                    "PUT",
                    url,
                    admin_token,
                    1,
                    body=body,
                    content_type=mime_type,
                )
                _assert_forbidden(status, denied)
                assert body not in denied

                status, _, raw = await _http(
                    session,
                    "PUT",
                    url,
                    child_token,
                    1,
                    body=body,
                    content_type=mime_type,
                )
                assert status == 200, (status, raw)
                available = json.loads(raw)
                assert available == {
                    "id": reserved["id"],
                    "revision": 2,
                    "status": "available",
                }
                stored = engine.snapshot()["media"][reserved["id"]]
                assert stored["mime_type"] == mime_type
                assert stored["size_bytes"] == len(body)
                assert stored["sha256"] == sha256(body).hexdigest()
                assert stored["status"] == "available"
                if format_name == "PNG":
                    # Content-Type is an allowlisted hint, never trusted as the
                    # decoded format. An exact retry remains the same PNG record.
                    status, _, spoofed = await _http(
                        session,
                        "PUT",
                        url,
                        child_token,
                        1,
                        body=body,
                        content_type="image/jpeg",
                    )
                    assert status == 200 and json.loads(spoofed) == available
                    assert engine.snapshot()["media"][reserved["id"]]["mime_type"] == "image/png"

                # Pending bytes remain uploader-private, including from parents.
                status, _, denied = await _http(session, "GET", url, owner_token, 2)
                _assert_forbidden(status, denied)
                assert body not in denied
                status, headers, downloaded = await _http(session, "GET", url, child_token, 2)
                assert status == 200 and downloaded == body
                assert headers["Content-Type"].split(";", 1)[0] == mime_type

                sequence += 1
                submitted = await _command(
                    hass,
                    entry,
                    child,
                    sequence,
                    "tasks.submit",
                    {
                        "id": task["id"],
                        "revision": task["revision"],
                        "media": {"id": reserved["id"], "revision": 2},
                    },
                    f"ha-media-submit-{format_name.lower()}",
                )
                assert submitted["status"] == "submitted"
                status, headers, downloaded = await _http(session, "GET", url, owner_token, 3)
                assert status == 200 and downloaded == body
                assert headers["Content-Type"].split(";", 1)[0] == mime_type
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
                status, _, denied = await _http(session, "GET", url, admin_token, 3)
                _assert_forbidden(status, denied)
                assert body not in denied
                created.append(
                    {
                        "task_id": task["id"],
                        "media_id": reserved["id"],
                        "mime_type": mime_type,
                        "sha256": stored["sha256"],
                        "body": body,
                    }
                )

            parent_view = await _view(hass, entry, owner, sequence + 1)
            child_view = await _view(hass, entry, child, sequence + 2)
            for item in created:
                for view in (parent_view, child_view):
                    task = next(row for row in view["tasks"] if row["id"] == item["task_id"])
                    assert task["report_attachments"] == [
                        {
                            "id": item["media_id"],
                            "revision": 3,
                            "purpose": "task_report",
                            "mime_type": item["mime_type"],
                            "size_bytes": len(item["body"]),
                            "status": "attached",
                        }
                    ]

            snapshot = engine.snapshot()
            serialized_outbox = repr(snapshot["outbox"])
            serialized_diagnostics = repr(safe_diagnostics(runtime))
            for item in created:
                assert item["media_id"] not in serialized_outbox
                assert item["sha256"] not in serialized_outbox
                assert item["media_id"] not in serialized_diagnostics
                assert item["sha256"] not in serialized_diagnostics
                for view in (parent_view, child_view):
                    assert item["media_id"] not in repr(projection(view))
                    assert item["sha256"] not in repr(projection(view))

            # The task module is a live download authorization gate. Restoring it
            # does not rewrite the attached task or its immutable blob.
            settings = engine.snapshot()["settings"]
            original_modules = list(settings["modules"])
            await engine.execute(
                "owner",
                "settings.save",
                _settings_payload(settings, [m for m in original_modules if m != "tasks"]),
                "ha-media-disable-tasks",
                dt_util.utcnow(),
            )
            first = created[0]
            url = (
                "http://127.0.0.1:8123/api/family_assistant/media/"
                f"{entry.entry_id}/{first['media_id']}"
            )
            status, _, denied = await _http(session, "GET", url, owner_token, 3)
            _assert_forbidden(status, denied)
            assert first["body"] not in denied
            current = engine.snapshot()["settings"]
            await engine.execute(
                "owner",
                "settings.save",
                _settings_payload(current, original_modules),
                "ha-media-restore-tasks",
                dt_util.utcnow(),
            )
            status, _, downloaded = await _http(session, "GET", url, owner_token, 3)
            assert status == 200 and downloaded == first["body"]
    finally:
        await hass.auth.async_remove_user(admin)

    final = engine.snapshot()
    assert final["settings"]["modules"] == initial["settings"]["modules"]
    print(
        "PASS: actual HA authenticated private PNG/JPEG/WebP upload, attachment, "
        "download authorization and decoder subprocess"
    )
    return {
        "records": [
            {
                "task_id": item["task_id"],
                "media_id": item["media_id"],
                "mime_type": item["mime_type"],
                "size_bytes": len(item["body"]),
                "sha256": item["sha256"],
            }
            for item in created
        ]
    }


async def verify_media_reload(entry, expected):
    """Confirm Store metadata and immutable private blobs after entry reload."""
    runtime = entry.runtime_data
    state = runtime.engine.snapshot()
    assert isinstance(expected, dict) and set(expected) == {"records"}
    for item in expected["records"]:
        record = state["media"][item["media_id"]]
        assert record["status"] == "attached" and record["revision"] == 3
        assert record["mime_type"] == item["mime_type"]
        assert record["size_bytes"] == item["size_bytes"]
        assert record["sha256"] == item["sha256"]
        assert state["tasks"][item["task_id"]]["report_media"] == [item["media_id"]]
        path = runtime.media.root / record["blob_key"]
        assert path.is_file() and not path.is_symlink()
        content = path.read_bytes()
        assert len(content) == item["size_bytes"]
        assert sha256(content).hexdigest() == item["sha256"]
