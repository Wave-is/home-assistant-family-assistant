"""Actual authenticated equipment PDF upload, purpose segregation and Store reload."""

import json
from copy import deepcopy
from io import BytesIO

from aiohttp import ClientSession
from ha_media_smoke import _assert_forbidden, _command, _http, _token, _view
from pypdf import PdfWriter


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


async def verify_documents(hass, entry, owner, child_id):
    e = entry.runtime_data.engine
    child = await hass.auth.async_get_user(e.snapshot()["members"][child_id]["ha_user_id"])
    owner_revision = e.snapshot()["members"]["owner"]["revision"]
    counter = 950

    async def command(action, payload, operation):
        nonlocal counter
        counter += 1
        return await _command(hass, entry, owner, counter, action, payload, operation)

    asset = await command(
        "maintenance.asset_save",
        {
            "name": "Synthetic document appliance",
            "category": "Synthetic",
            "location": "Lab",
            "responsible_member": "owner",
            "responsible_member_revision": owner_revision,
            "warranty": {"expires_on": None, "vendor": "", "reference": ""},
            "consumables": [],
            "note": "",
        },
        "ha-document-asset",
    )
    protected = {
        key: deepcopy(e.snapshot()[key])
        for key in ("tasks", "task_series", "outbox", "court", "alarm_runs", "routine_runs")
    }
    body = pdf()
    async with (
        _token(hass, owner) as owner_token,
        _token(hass, child) as child_token,
        ClientSession() as session,
    ):
        for index in range(2):
            reserved = await command(
                "media.reserve",
                {
                    "purpose": "equipment_document",
                    "asset_id": asset["id"],
                    "asset_revision": asset["revision"],
                    "uploader_revision": owner_revision,
                },
                f"ha-document-reserve-{index}",
            )
            url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{reserved['id']}"
            status, _, raw = await _http(
                session, "PUT", url, child_token, 1, body=body, content_type="application/pdf"
            )
            _assert_forbidden(status, raw)
            status, _, raw = await _http(
                session,
                "PUT",
                url,
                owner_token,
                1,
                body=b"%PDF-1.7\n%%EOF",
                content_type="application/pdf",
            )
            assert status == 400 and json.loads(raw)["code"] == "media_invalid"
            status, _, raw = await _http(
                session, "PUT", url, owner_token, 1, body=body, content_type="application/pdf"
            )
            assert status == 200, (status, raw)
            available = json.loads(raw)
            status, _, raw = await _http(
                session, "PUT", url, owner_token, 1, body=body, content_type="application/pdf"
            )
            assert status == 200 and json.loads(raw) == available
            payload = {
                "id": asset["id"],
                "revision": asset["revision"],
                "actor_member_revision": owner_revision,
                "media": {"id": reserved["id"], "revision": 2},
                "title": "Synthetic private warranty",
                "kind": "warranty",
                "note": "DOCUMENT-HA-PRIVATE-CANARY",
            }
            result = await command(
                "maintenance.document_attach", payload, f"ha-document-attach-{index}"
            )
            before = e.snapshot()
            assert (
                await command("maintenance.document_attach", payload, f"ha-document-attach-{index}")
                == result
            )
            assert e.snapshot() == before
            row = next(
                row
                for row in (await _view(hass, entry, owner, 990))["maintenance"]["documents"]
                if row["id"] == result["id"]
            )
            attachment = row["attachment"]
            status, headers, raw = await _http(
                session, "GET", url, owner_token, attachment["revision"]
            )
            assert status == 200 and raw == body
            assert headers["Content-Type"].split(";", 1)[0] == "application/pdf"
            assert headers["Content-Disposition"].startswith("attachment;")
            assert headers["X-Content-Type-Options"] == "nosniff"
            status, _, raw = await _http(session, "GET", url, child_token, attachment["revision"])
            _assert_forbidden(status, raw)
            assert "DOCUMENT-HA-PRIVATE-CANARY" not in repr(await _view(hass, entry, child, 991))
            if index == 0:
                purge = {
                    "id": asset["id"],
                    "revision": asset["revision"],
                    "actor_member_revision": owner_revision,
                    "media": {"id": attachment["id"], "revision": attachment["revision"]},
                    "document": {"id": result["id"], "revision": result["revision"]},
                    "reason": "Synthetic reviewed removal",
                }
                removed = await command("maintenance.document_purge", purge, "ha-document-purge")
                status, _, raw = await _http(
                    session, "GET", url, owner_token, attachment["revision"]
                )
                _assert_forbidden(status, raw)
                assert (
                    await command("maintenance.document_purge", purge, "ha-document-purge")
                    == removed
                )
        for key, value in protected.items():
            assert e.snapshot()[key] == value
        assert e.snapshot()["maintenance"]["assets"][asset["id"]]["revision"] == asset["revision"]
        expected = {"asset_id": asset["id"], "document": row, "body": body}
        # Real image-purpose reservation must still reject a structurally valid PDF.
        task = await command(
            "tasks.create",
            {
                "title": "Synthetic image-only document boundary",
                "assignee": child_id,
                "report_type": "photo",
            },
            "ha-document-image-boundary-task",
        )
        reserved = await command(
            "media.reserve",
            {
                "purpose": "task_report",
                "task_id": task["id"],
                "task_revision": task["revision"],
                "uploader_revision": owner_revision,
            },
            "ha-document-image-boundary-reserve",
        )
        url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{reserved['id']}"
        status, _, raw = await _http(
            session, "PUT", url, owner_token, 1, body=body, content_type="application/pdf"
        )
        assert status == 400 and json.loads(raw)["code"] == "media_invalid"
        assert e.snapshot()["media"][reserved["id"]]["status"] == "reserved"
    print(
        "PASS: actual HA private PDF decoder/upload, shared-parent attachment, "
        "image-purpose denial, exact replay and owner purge"
    )
    return expected


async def verify_documents_reload(hass, entry, owner, child_id, expected):
    row = next(
        row
        for row in (await _view(hass, entry, owner, 992))["maintenance"]["documents"]
        if row["id"] == expected["document"]["id"]
    )
    assert row == expected["document"]
    child = await hass.auth.async_get_user(
        entry.runtime_data.engine.snapshot()["members"][child_id]["ha_user_id"]
    )
    attachment = row["attachment"]
    url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{attachment['id']}"
    async with (
        _token(hass, owner) as token,
        _token(hass, child) as denied,
        ClientSession() as session,
    ):
        status, _, content = await _http(session, "GET", url, token, attachment["revision"])
        assert status == 200 and content == expected["body"]
        status, _, content = await _http(session, "GET", url, denied, attachment["revision"])
        _assert_forbidden(status, content)
    print("PASS: actual HA equipment document metadata/private PDF bytes survive Store reload")
