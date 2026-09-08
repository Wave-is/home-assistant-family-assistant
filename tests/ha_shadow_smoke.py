"""Actual isolated HA Store/HTTP/Options/reload acceptance of a whole shadow copy."""

import json
from datetime import UTC, datetime
from types import MappingProxyType

from ha_legacy_archive_smoke import synthetic_source
from ha_presence_smoke import _request


async def verify_shadow(hass, owner_user, *, photos=False):
    from homeassistant.config_entries import ConfigEntry, ConfigEntryState
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.domain.engine import new_state
    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.migration.review import read_store_pair
    from custom_components.family_assistant.migration.shadow import build_shadow_candidate
    from custom_components.family_assistant.migration.shadow_install import (
        ShadowInstallError,
        async_stage_shadow,
    )
    from custom_components.family_assistant.migration.shadow_registration import (
        ShadowRegistrationError,
        async_register_shadow,
    )
    from custom_components.family_assistant.runtime import async_options_updated, safe_diagnostics

    # Prepare the Store before the first setup of this new entry. Reusing a
    # previously active entry would retain its old entity registry records.
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="family_assistant",
        source="user",
        title="Synthetic migration shadow",
        unique_id=None,
        data={"owner_user_id": owner_user.id, "owner_name": "Synthetic owner", "modules": []},
        options={
            key: {"enabled": True} for key in ("telegram", "mikrotik", "conversation", "recipes")
        },
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    try:
        assistant, court, mapping, members = synthetic_source(lifecycle=True)
        if photos:
            data = json.loads(assistant)
            data["data"]["ledger"]["tasks"]["T000004"]["report_type"] = "photo"
            for event in data["data"]["ledger"]["history"]:
                if event["task_id"] == "T000004" and event["type"] == "created":
                    event["details"]["report_type"] = "photo"
            assistant = json.dumps(data).encode()
        child = await hass.auth.async_create_user("Synthetic shadow child")
        target = new_state(owner_user.id, entry.title, modules=[])
        for member in members.values():
            member.update(
                language="en",
                aliases=[],
                ha_user_id=owner_user.id if member["role"] == "owner" else child.id,
            )
        target["members"] = members
        review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
        policy = {
            "schema": 1,
            "revision": 1,
            "source_review_fingerprint": review.summary()["fingerprint"],
            "reviewers": {
                key: [row["reviewer"]]
                for key, row in review.private_data()[0]["ledger"]["tasks"].items()
                if row.get("requires_report") is True
            },
        }
        prepared = datetime(2026, 9, 8, tzinfo=UTC)
        evidence = None
        if photos:
            from ha_media_smoke import _image

            from custom_components.family_assistant.migration.photo_evidence import (
                async_prepare_photo_evidence,
                async_restore_photo_evidence,
                submission_inventory,
            )

            inventory = submission_inventory(review, members=members)
            choices, content = [], {}
            for index, row in enumerate(inventory):
                key = f"selected_{index}"
                choices.append(
                    {key: row[key] for key in ("task_id", "event_sequence", "report_sha256")}
                    | {"attachment_key": key}
                )
                content[key] = _image("PNG")
            evidence = await async_prepare_photo_evidence(
                review,
                members=members,
                source_review_fingerprint=review.summary()["fingerprint"],
                confirmed_by="owner",
                prepared_at=prepared,
                confirmations=choices,
                attachments=content,
            )
            assert len(evidence.private_blobs()) == 3
            restored = await async_restore_photo_evidence(
                review,
                members=members,
                archive=evidence.private_data(),
                blobs=evidence.private_blobs(),
            )
            assert restored.private_data() == evidence.private_data()
        candidate = build_shadow_candidate(
            review, target, reviewer_policy=policy, prepared_at=prepared, photo_evidence=evidence
        )
        expected = candidate.private_state()
        try:
            await async_stage_shadow(
                hass,
                entry_id=entry.entry_id,
                user_id=child.id,
                candidate=candidate,
                target=target,
                expected_fingerprint=candidate.summary()["fingerprint"],
            )
        except ShadowInstallError as error:
            assert str(error) == "shadow_install_forbidden"
        else:
            raise AssertionError("Child unexpectedly staged a migration copy")
        assert await Store(hass, 1, f"family_assistant.{entry.entry_id}").async_load() is None
        if photos:
            from unittest.mock import patch

            from custom_components.family_assistant.domain.shadow import SCHEMA
            from custom_components.family_assistant.migration import shadow_install

            save = shadow_install._settled_save

            async def committed_then_lost(store, value):
                await save(store, value)
                if value.get("schema_version") == SCHEMA:
                    raise OSError("Synthetic lost acknowledgement after native Store commit")

            with patch.object(shadow_install, "_settled_save", committed_then_lost):
                try:
                    await async_stage_shadow(
                        hass,
                        entry_id=entry.entry_id,
                        user_id=owner_user.id,
                        candidate=candidate,
                        target=target,
                        expected_fingerprint=candidate.summary()["fingerprint"],
                    )
                except ShadowInstallError as error:
                    assert str(error) == "shadow_install_retry_required"
                else:
                    raise AssertionError("Synthetic lost acknowledgement was not surfaced")
            assert (
                await Store(hass, 1, f"family_assistant.{entry.entry_id}").async_load() == expected
            )
        receipt = await async_stage_shadow(
            hass,
            entry_id=entry.entry_id,
            user_id=owner_user.id,
            candidate=candidate,
            target=target,
            expected_fingerprint=candidate.summary()["fingerprint"],
        )
        assert receipt["mode"] == "read_only_shadow_staged"
        assert (
            await async_stage_shadow(
                hass,
                entry_id=entry.entry_id,
                user_id=owner_user.id,
                candidate=candidate,
                target=target,
                expected_fingerprint=candidate.summary()["fingerprint"],
            )
            == receipt
        )
        store = Store(hass, 1, f"family_assistant.{entry.entry_id}")
        assert await store.async_load() == expected
        registration_args = {
            "entry_id": entry.entry_id,
            "user_id": owner_user.id,
            "candidate": candidate,
            "target": target,
            "expected_fingerprint": candidate.summary()["fingerprint"],
        }
        if photos:
            manager_type = type(hass.config_entries)
            native_add = manager_type.async_add

            async def added_then_lost(manager, selected_entry):
                await native_add(manager, selected_entry)
                if selected_entry.entry_id == registration_args["entry_id"]:
                    raise OSError("Synthetic lost registration acknowledgement")

            with patch.object(manager_type, "async_add", added_then_lost):
                try:
                    await async_register_shadow(hass, **registration_args)
                except ShadowRegistrationError as error:
                    assert str(error) == "shadow_registration_retry_required"
                else:
                    raise AssertionError("Synthetic lost registration reply was not surfaced")
        registered = await async_register_shadow(hass, **registration_args)
        assert registered["mode"] == "read_only_shadow_registered" and registered["loaded"]
        assert not registered["activation_available"]
        assert await async_register_shadow(hass, **registration_args) == registered
        entry = hass.config_entries.async_get_entry(entry.entry_id)
        assert entry.data["migration_shadow"] == receipt["entry_marker"]
        try:
            await async_register_shadow(hass, **(registration_args | {"user_id": child.id}))
        except ShadowRegistrationError as error:
            assert str(error) == "shadow_registration_forbidden"
        else:
            raise AssertionError("Child repeated a private registration")
        # Even hostile enabled provider options cannot thaw the sealed runtime.
        hass.config_entries.async_update_entry(
            entry,
            options={
                key: {"enabled": True}
                for key in ("telegram", "mikrotik", "conversation", "recipes")
            },
        )
        await hass.async_block_till_done()
        try:
            await async_stage_shadow(
                hass,
                entry_id=entry.entry_id,
                user_id=owner_user.id,
                candidate=candidate,
                target=target,
                expected_fingerprint=candidate.summary()["fingerprint"],
            )
        except ShadowInstallError as error:
            assert str(error) == "shadow_install_busy"
        else:
            raise AssertionError("Registered target unexpectedly accepted staging")
        for turn in range(2):
            if turn:
                assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state == ConfigEntryState.LOADED
            runtime = entry.runtime_data
            assert runtime.engine.shadow_mode
            from homeassistant.helpers import entity_registry

            registry = entity_registry.async_get(hass)
            assert not entity_registry.async_entries_for_config_entry(registry, entry.entry_id)
            assert all(
                getattr(runtime, key) is None
                for key in (
                    "scheduler",
                    "telegram",
                    "network",
                    "assistant",
                    "chat",
                    "articles",
                    "recipes",
                    "media_task",
                    "media_unsub",
                )
            )
            response = await _request(hass, entry, owner_user, 8801)
            assert (
                response["success"]
                and response["result"]["read_only"] == "migration_shadow_read_only"
            )
            assert len(response["result"]["tasks"]) == 3
            if photos:
                from aiohttp import ClientSession
                from ha_media_smoke import _http, _token

                task = next(row for row in response["result"]["tasks"] if row["id"] == "T000004")
                assert len(task["report_attachments"]) == 1
                assert len(task["previous_reports"]) == 2
                assert all(len(row["report_attachments"]) == 1 for row in task["previous_reports"])
                async with (
                    _token(hass, owner_user) as owner_token,
                    _token(hass, child) as child_token,
                    ClientSession() as session,
                ):
                    for image in expected["media"].values():
                        url = f"http://127.0.0.1:8123/api/family_assistant/media/{entry.entry_id}/{image['id']}"
                        status, headers, body = await _http(
                            session, "GET", url, owner_token, image["revision"]
                        )
                        assert (
                            status == 200 and body == candidate.private_blobs()[image["blob_key"]]
                        )
                        assert "no-store" in headers.get("Cache-Control", "")
                        status, _, _ = await _http(
                            session, "GET", url, child_token, image["revision"]
                        )
                        assert status == 403
            denied = await _request(hass, entry, child, 8802)
            assert not denied["success"] and denied["error"]["code"] == "forbidden"
            mutation = await _request(
                hass, entry, owner_user, 8803, "settings.update", {"modules": ["tasks"]}
            )
            assert (
                not mutation["success"]
                and mutation["error"]["code"] == "migration_shadow_read_only"
            )
            options = await hass.config_entries.options.async_init(
                entry.entry_id, context={"user_id": owner_user.id}
            )
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"next_step_id": "telegram"}
            )
            assert options["type"] == "abort" and options["reason"] == "migration_shadow_read_only"
            await async_options_updated(hass, entry)
            assert runtime.telegram is None and runtime.network is None and runtime.recipes is None
            try:
                await runtime.engine.tick(datetime(2027, 1, 1, tzinfo=UTC))
                raise AssertionError("Shadow clock was writable")
            except DomainError as error:
                assert error.code == "migration_shadow_read_only"
            assert "migration_archive" not in safe_diagnostics(runtime)
            assert runtime.engine.snapshot() == expected
            assert await store.async_load() == expected
            assert await hass.config_entries.async_unload(entry.entry_id)
        await verify_shadow_fail_closed(hass, entry, store, expected)
        print(
            "PASS: native shadow installer staged verified blobs then Store, exact retry, "
            "child denial and registered-target refusal"
        )
        print(
            "PASS: native sealed shadow registration/exact retry/child denial; "
            "lost add acknowledgement creates no duplicate entry"
        )
        print(
            "PASS: whole shadow native Store/reload, owner-only authenticated view, "
            "command/Options denial, zero providers/scheduler and unchanged bytes"
        )
        if photos:
            print(
                "PASS: historical photo rounds, actual bounded decoder/archive replay, "
                "native Store/blob reload, owner-only authenticated HTTP bytes and zero workers"
            )
    finally:
        await hass.config_entries.async_remove(entry.entry_id)
    if not photos:
        await verify_shadow(hass, owner_user, photos=True)


async def verify_shadow_fail_closed(hass, entry, store, expected):
    """Exercise missing/changed native Store loads without editing storage files."""
    from copy import deepcopy
    from unittest.mock import patch

    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers.storage import Store

    original_load, original_save = Store.async_load, Store.async_save
    writes = []
    corrupt = deepcopy(expected)
    corrupt["tasks"]["T000004"]["title"] = "Synthetic altered task"
    for selected in (None, {}, corrupt):

        async def selected_load(instance, selected=selected):
            if instance.key == store.key:
                return deepcopy(selected)
            return await original_load(instance)

        async def checked_save(instance, value):
            if instance.key == store.key:
                writes.append(deepcopy(value))
            await original_save(instance, value)

        with (
            patch.object(Store, "async_load", selected_load),
            patch.object(Store, "async_save", checked_save),
        ):
            assert not await hass.config_entries.async_setup(entry.entry_id)
            assert entry.state == ConfigEntryState.SETUP_RETRY
            assert entry.entry_id not in hass.data["family_assistant"]["entries"]
            assert not writes, "Damaged shadow wrote a replacement Store"
        assert await store.async_load() == expected
        # Supported reload cancels a scheduled setup retry before restoring the
        # exact original bytes. No direct .storage writes or file deletion.
        assert await hass.config_entries.async_reload(entry.entry_id)
        assert entry.runtime_data.engine.shadow_mode
        assert await hass.config_entries.async_unload(entry.entry_id)
    print("PASS: native missing/changed shadow Store fails closed; no blank Store or workers")


async def main():
    """Focused offline entry acceptance, without starting an ordinary household."""
    import shutil
    import tempfile
    from pathlib import Path

    from homeassistant import bootstrap, loader
    from homeassistant.auth.const import GROUP_ID_ADMIN
    from homeassistant.core import HomeAssistant
    from homeassistant.setup import async_setup_component

    assert Path("/.dockerenv").is_file()
    assert {path.name for path in Path("/sys/class/net").iterdir() if path.is_dir()} == {"lo"}
    assert "CapEff:\t0000000000000000" in Path("/proc/self/status").read_text()
    with tempfile.TemporaryDirectory(prefix="synthetic-shadow-") as directory:
        shutil.copytree(
            Path(__file__).resolve().parents[1] / "custom_components",
            Path(directory) / "custom_components",
        )
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        try:
            assert await bootstrap.async_from_config_dict(
                {
                    "homeassistant": {
                        "latitude": 0,
                        "longitude": 0,
                        "elevation": 0,
                        "time_zone": "UTC",
                        "unit_system": "metric",
                        "country": "GB",
                    },
                    "http": {"server_host": "127.0.0.1", "server_port": 8123},
                },
                hass,
            )
            await async_setup_component(hass, "websocket_api", {})
            await hass.async_start()
            owner = await hass.auth.async_create_user("Synthetic owner", group_ids=[GROUP_ID_ADMIN])
            await verify_shadow(hass, owner)
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
