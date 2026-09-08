"""Native index/Options resume of complete staged copies without reupload."""

from unittest.mock import patch


async def verify_copy_resume(hass, owner, child, prototype, source_state, flows, created):
    from ha_copy_wizard_smoke import _open, _package, _review_token, _upload
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.migration import copy_flow
    from custom_components.family_assistant.migration.shadow_install import async_stage_shadow

    result = await _open(hass, prototype, owner, flows)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "copy_name": "Synthetic resumable staged copy",
            "bundle": await _upload(hass, owner, _package(source_state["members"])),
            "private_files_reviewed": True,
        },
    )
    while result.get("step_id") == "legacy_copy_matches":
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"review_token": _review_token(result), "confirmed": True}
        )
    assert result["step_id"] == "legacy_copy_review"
    slot = hass.data["family_assistant"]["migration_copy_review"]
    entry_id = slot["intent"]["entry_id"]
    created.add(entry_id)
    original, blobs = slot["candidate"].private_state(), slot["candidate"].private_blobs()
    fingerprint = slot["candidate"].summary()["fingerprint"]

    async def interrupt_after_complete_staging(_hass, **kwargs):
        await async_stage_shadow(_hass, **kwargs)
        raise ValueError("synthetic_process_loss_before_registration")

    with patch.object(copy_flow, "async_register_shadow", interrupt_after_complete_staging):
        failed = await hass.config_entries.options.async_configure(
            result["flow_id"], {"review_token": fingerprint, "confirmed": True}
        )
    assert failed["step_id"] == "legacy_copy_review" and failed["errors"]
    assert hass.config_entries.async_get_entry(entry_id) is None
    shadow_store = Store(hass, 1, f"family_assistant.{entry_id}")
    index_store = Store(hass, 1, "family_assistant.copy_index")
    assert await shadow_store.async_load() == original
    index_before = await index_store.async_load()
    assert entry_id in index_before["records"]

    # Lose the previous Options/candidate memory and replace its runtime. Native
    # Store instances below are freshly constructed; this is not a mocked index.
    hass.config_entries.options.async_abort(failed["flow_id"])
    hass.data["family_assistant"].pop("migration_copy_review")
    assert await hass.config_entries.async_reload(prototype.entry_id)
    await hass.async_block_till_done()

    async def open_resume(user):
        opened = await hass.config_entries.options.async_init(
            prototype.entry_id, context={"user_id": user.id}
        )
        flows.add(opened["flow_id"])
        return await hass.config_entries.options.async_configure(
            opened["flow_id"], {"next_step_id": "legacy_resume"}
        )

    denied = await open_resume(child)
    assert denied["type"] == "abort" and denied["reason"] == "forbidden"
    for repeat in range(2):
        resumed = await open_resume(owner)
        assert resumed["step_id"] == "legacy_resume", resumed
        resumed = await hass.config_entries.options.async_configure(
            resumed["flow_id"],
            {
                "review_token": _review_token(resumed),
                "attempt": entry_id,
            },
        )
        assert resumed["step_id"] == "legacy_resume_review", resumed
        assert resumed["description_placeholders"]["fingerprint"] == fingerprint
        assert resumed["description_placeholders"]["photos"] == str(len(blobs))
        assert await index_store.async_load() == index_before
        assert await shadow_store.async_load() == original
        if not repeat:
            assert hass.config_entries.async_get_entry(entry_id) is None
        declined = await hass.config_entries.options.async_configure(
            resumed["flow_id"], {"review_token": fingerprint, "confirmed": False}
        )
        assert declined["step_id"] == "legacy_resume_review"
        if not repeat:
            assert hass.config_entries.async_get_entry(entry_id) is None
        completed = await hass.config_entries.options.async_configure(
            resumed["flow_id"], {"review_token": fingerprint, "confirmed": True}
        )
        assert completed["step_id"] == "legacy_copy_complete" and not completed["errors"], completed
        entry = hass.config_entries.async_get_entry(entry_id)
        assert entry.runtime_data.engine.shadow_mode
        assert entry.runtime_data.engine.snapshot() == original
        assert entry.runtime_data.scheduler is None and entry.runtime_data.telegram is None
        assert await index_store.async_load() == index_before
        assert await shadow_store.async_load() == original
        finished = await hass.config_entries.options.async_configure(completed["flow_id"], {})
        assert finished["reason"] == "migration_copy_finished"
    assert prototype.runtime_data.engine.snapshot() == source_state
    print(
        "PASS: native Store index/Options direct resume after lost review and runtime reload, "
        "fresh photo reconversion, child denial, separate confirmation, same sealed ID/replay "
        "and unchanged source/index; no ZIP reupload"
    )
