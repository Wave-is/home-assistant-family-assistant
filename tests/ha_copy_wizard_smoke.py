"""Real FileSelector upload, paged Options review and sealed registration in offline HA."""

import base64
import io
import json
import zipfile
from types import MappingProxyType

from ha_legacy_archive_smoke import synthetic_source
from ha_media_smoke import _image, _token


def _package(members, *, orphan_penalty=False):
    from custom_components.family_assistant.migration.photo_evidence import submission_inventory
    from custom_components.family_assistant.migration.review import read_store_pair

    assistant, court, mapping, _ = synthetic_source(lifecycle=True)
    data = json.loads(assistant)
    data["data"]["ledger"]["tasks"]["T000004"]["report_type"] = "photo"
    for event in data["data"]["ledger"]["history"]:
        if event["task_id"] == "T000004" and event["type"] == "created":
            event["details"]["report_type"] = "photo"
    assistant = json.dumps(data).encode()
    if orphan_penalty:
        court_data = json.loads(court)
        source_key = "task:T000002:missed:2026-09-07"
        court_data["data"]["history"][0].update(
            parent_user_id=0,
            telegram_message_id=f"system:{source_key}",
            original_text=f"automatic task control: {source_key}",
        )
        court = json.dumps(court_data).encode()
    # Enough explicitly archive-only historical identity rows for a second page.
    mapping.update({f"archived-fictional-{n}": {"archive_only": True} for n in range(8)})
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    photos = [
        {key: row[key] for key in ("task_id", "event_sequence", "report_sha256")}
        | {"attachment_key": f"image_{index}"}
        for index, row in enumerate(submission_inventory(review, members=members))
    ]
    manifest = {
        "version": 1,
        "kind": "family_assistant_legacy_shadow",
        "assistant_store": base64.b64encode(assistant).decode(),
        "court_store": base64.b64encode(court).decode(),
        "member_mapping": mapping,
        "reviewer_sets": {
            key: [row["reviewer"]]
            for key, row in data["data"]["ledger"]["tasks"].items()
            if row.get("requires_report") is True
        },
        "photos": photos,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest).encode())
        for row in photos:
            archive.writestr(f"photos/{row['attachment_key']}", _image("PNG"))
    return output.getvalue()


def _review_token(result):
    marker = next(key for key in result["data_schema"].schema if str(key) == "review_token")
    return marker.default()


async def _upload(hass, owner, content):
    from aiohttp import ClientSession, FormData

    async with _token(hass, owner) as token, ClientSession() as session:
        form = FormData()
        form.add_field(
            "file", content, filename="synthetic-review.zip", content_type="application/zip"
        )
        async with session.post(
            "http://127.0.0.1:8123/api/file_upload",
            headers={"Authorization": f"Bearer {token}"},
            data=form,
        ) as response:
            assert response.status == 200, "Synthetic native file upload failed"
            result = await response.json()
            assert isinstance(result["file_id"], str)
            return result["file_id"]


async def _open(hass, prototype, user, flows):
    result = await hass.config_entries.options.async_init(
        prototype.entry_id, context={"user_id": user.id}
    )
    flows.add(result["flow_id"])
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "legacy_copy"}
    )


async def verify_copy_wizard(hass, owner):
    import voluptuous as vol
    from homeassistant.config_entries import ConfigEntry, ConfigEntryState
    from homeassistant.data_entry_flow import UnknownFlow
    from homeassistant.helpers.storage import Store

    child = await hass.auth.async_create_user("Synthetic copy wizard child")
    prototype = ConfigEntry(
        version=1,
        minor_version=1,
        domain="family_assistant",
        source="user",
        title="Synthetic copy prototype",
        unique_id=None,
        data={
            "owner_user_id": owner.id,
            "owner_name": "Synthetic copy owner",
            "modules": [],
            "initial_members": [
                {
                    "id": "child",
                    "name": "Synthetic child",
                    "role": "child",
                    "language": "en",
                    "revision": 1,
                    "active": True,
                    "aliases": [],
                    "ha_user_id": child.id,
                }
            ],
        },
        options={},
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    flows, created = set(), set()
    await hass.config_entries.async_add(prototype)
    try:
        await hass.async_block_till_done()
        assert prototype.state == ConfigEntryState.LOADED
        source_state = prototype.runtime_data.engine.snapshot()
        source_store = Store(hass, 1, f"family_assistant.{prototype.entry_id}")
        assert await source_store.async_load() == source_state
        bundle = _package(source_state["members"])
        denied = await _open(hass, prototype, child, flows)
        assert denied["type"] == "abort" and denied["reason"] == "forbidden"
        inconsistent = await _open(hass, prototype, owner, flows)
        inconsistent = await hass.config_entries.options.async_configure(
            inconsistent["flow_id"],
            {
                "copy_name": "Synthetic inconsistent archive",
                "bundle": await _upload(
                    hass, owner, _package(source_state["members"], orphan_penalty=True)
                ),
                "private_files_reviewed": True,
            },
        )
        refused_id = hass.data["family_assistant"]["migration_copy_review"]["intent"]["entry_id"]
        while inconsistent.get("step_id") == "legacy_copy_matches":
            inconsistent = await hass.config_entries.options.async_configure(
                inconsistent["flow_id"],
                {"review_token": _review_token(inconsistent), "confirmed": True},
            )
        assert (
            inconsistent["type"] == "abort"
            and inconsistent["reason"] == "migration_copy_source_unsettled"
        )
        assert "migration_copy_review" not in hass.data["family_assistant"]
        assert hass.config_entries.async_get_entry(refused_id) is None
        for key in (f"family_assistant.{refused_id}", f"family_assistant.copy_intent.{refused_id}"):
            assert await Store(hass, 1, key).async_load() is None
        cancelled = await _open(hass, prototype, owner, flows)
        cancelled = await hass.config_entries.options.async_configure(
            cancelled["flow_id"],
            {
                "copy_name": "Synthetic reviewed archive",
                "bundle": await _upload(hass, owner, bundle),
                "private_files_reviewed": True,
            },
        )
        abandoned_id = hass.data["family_assistant"]["migration_copy_review"]["intent"]["entry_id"]
        cancelled = await hass.config_entries.options.async_configure(
            cancelled["flow_id"],
            {"review_token": _review_token(cancelled), "confirmed": False, "discard_review": True},
        )
        assert cancelled["type"] == "abort" and cancelled["reason"] == "migration_copy_cancelled"
        assert "migration_copy_review" not in hass.data["family_assistant"]
        assert hass.config_entries.async_get_entry(abandoned_id) is None
        for key in (
            f"family_assistant.{abandoned_id}",
            f"family_assistant.copy_intent.{abandoned_id}",
        ):
            assert await Store(hass, 1, key).async_load() is None
        first = None
        for turn in range(3):
            start = await _open(hass, prototype, owner, flows)
            assert start["step_id"] == "legacy_copy"
            upload_id = await _upload(hass, owner, bundle)
            result = await hass.config_entries.options.async_configure(
                start["flow_id"],
                {
                    "copy_name": "Synthetic reviewed archive",
                    "bundle": upload_id,
                    "private_files_reviewed": True,
                },
            )
            assert result["type"] == "form" and result["step_id"] == "legacy_copy_matches", result
            slot = hass.data["family_assistant"]["migration_copy_review"]
            target_id = slot["intent"]["entry_id"]
            created.add(target_id)
            if not turn:
                assert hass.config_entries.async_get_entry(target_id) is None
                assert await Store(hass, 1, f"family_assistant.{target_id}").async_load() is None
                assert (
                    await Store(hass, 1, f"family_assistant.copy_intent.{target_id}").async_load()
                    is None
                )
            old_token, pages = None, 0
            while result.get("step_id") == "legacy_copy_matches":
                token = _review_token(result)
                if old_token is not None and not turn:
                    try:
                        replay = await hass.config_entries.options.async_configure(
                            result["flow_id"], {"review_token": old_token, "confirmed": True}
                        )
                    except vol.Invalid:
                        pass  # Core rejects a stale SelectSelector value first.
                    else:
                        assert replay["step_id"] == "legacy_copy_matches" and replay["errors"]
                    assert slot["page"] == pages
                old_token = token
                result = await hass.config_entries.options.async_configure(
                    result["flow_id"], {"review_token": token, "confirmed": True}
                )
                pages += 1
            assert pages == 2 and result["step_id"] == "legacy_copy_review", result
            assert result["description_placeholders"]["photos"] == "3"
            if not turn:
                assert hass.config_entries.async_get_entry(target_id) is None
            final_token = _review_token(result)
            if turn == 2:
                cancelled = await hass.config_entries.options.async_configure(
                    result["flow_id"],
                    {"review_token": final_token, "confirmed": False, "discard_review": True},
                )
                assert cancelled["reason"] == "migration_copy_cancelled"
                assert "migration_copy_review" not in hass.data["family_assistant"]
                retained_entry = hass.config_entries.async_get_entry(target_id)
                assert retained_entry.runtime_data.engine.snapshot() == first[2]
                assert (
                    await Store(hass, 1, f"family_assistant.{target_id}").async_load() == first[2]
                )
                assert (
                    await Store(hass, 1, f"family_assistant.copy_intent.{target_id}").async_load()
                    == first[1]
                )
                assert prototype.runtime_data.engine.snapshot() == source_state
                assert await source_store.async_load() == source_state and not prototype.options
                continue
            not_confirmed = await hass.config_entries.options.async_configure(
                result["flow_id"], {"review_token": final_token, "confirmed": False}
            )
            assert not_confirmed["step_id"] == "legacy_copy_review" and not_confirmed["errors"]
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], {"review_token": final_token, "confirmed": True}
            )
            assert result["step_id"] == "legacy_copy_complete" and not result["errors"], result
            entry = hass.config_entries.async_get_entry(target_id)
            assert entry.state == ConfigEntryState.LOADED and entry.runtime_data.engine.shadow_mode
            assert entry.runtime_data.scheduler is None and entry.runtime_data.telegram is None
            exact = (target_id, dict(slot["intent"]), entry.runtime_data.engine.snapshot())
            if first is None:
                first = exact
            else:
                assert exact == first, "Same bundle retry changed ID, preparation time or Store"
            finished = await hass.config_entries.options.async_configure(result["flow_id"], {})
            assert finished["type"] == "abort" and finished["reason"] == "migration_copy_finished"
            assert "migration_copy_review" not in hass.data["family_assistant"]
            assert prototype.runtime_data.engine.snapshot() == source_state
            assert await source_store.async_load() == source_state and not prototype.options
        assert len(created) == 1
        print(
            "PASS: native private ZIP upload/FileSelector, two-page nonce review, "
            "final confirmation, sealed registration, same-bundle reupload replay "
            "and unchanged prototype; discarded reviews preserve existing copies "
            "and retry intents; "
            "one-sided source penalties block registration without Store writes"
        )
    finally:
        slot = hass.data["family_assistant"].get("migration_copy_review")
        if slot and slot["flow_id"] in flows:
            hass.data["family_assistant"].pop("migration_copy_review")
        for flow_id in flows:
            try:
                hass.config_entries.options.async_abort(flow_id)
            except UnknownFlow:
                pass
        for entry_id in created:
            if hass.config_entries.async_get_entry(entry_id):
                await hass.config_entries.async_remove(entry_id)
        await hass.config_entries.async_remove(prototype.entry_id)
