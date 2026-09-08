"""Actual authenticated native source-file, identity, reviewer and photo forms."""

from ha_copy_wizard_smoke import _package, _review_token, _upload
from ha_media_smoke import _image


async def verify_copy_preparation(hass, owner, child, prototype, source_state, flows, created):
    import voluptuous as vol
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.migration.copy_bundle import parse_copy_bundle

    async def open_form(user):
        result = await hass.config_entries.options.async_init(
            prototype.entry_id, context={"user_id": user.id}
        )
        flows.add(result["flow_id"])
        return await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "legacy_prepare"}
        )

    async def source_files(result):
        source, _, _, _, _ = parse_copy_bundle(_package(source_state["members"])).private_inputs()
        return await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "copy_name": "Synthetic prepared archive",
                "assistant_export": await _upload(
                    hass,
                    owner,
                    source._assistant,
                    filename="assistant.json",
                    content_type="application/json",
                ),
                "court_export": await _upload(
                    hass,
                    owner,
                    source._court,
                    filename="court.json",
                    content_type="application/json",
                ),
                "private_files_reviewed": True,
            },
        )

    denied = await open_form(child)
    assert denied["reason"] == "forbidden"
    entries_before = len(hass.config_entries.async_entries("family_assistant"))
    original = None
    for attempt in range(2):
        result = await source_files(await open_form(owner))
        assert result["step_id"] == "legacy_prepare_member", result
        slot = hass.data["family_assistant"]["migration_copy_review"]
        previous_token = None
        count = 0
        while result.get("step_id") == "legacy_prepare_member":
            current = _review_token(result)
            if previous_token and not attempt:
                try:
                    stale = await hass.config_entries.options.async_configure(
                        result["flow_id"],
                        {
                            "review_token": previous_token,
                            "confirmed": True,
                            "member": "owner",
                        },
                    )
                except vol.Invalid:
                    pass
                else:
                    assert stale["errors"] and stale["step_id"] == "legacy_prepare_member"
                assert slot["index"] == count
            source_id = slot["prepare"]["inventory"]["members"][slot["index"]]["source_id"]
            selected = {"old-child": "child", "old-parent": "owner"}[source_id]
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {
                    "review_token": current,
                    "confirmed": True,
                    "member": selected,
                },
            )
            previous_token = current
            count += 1
        assert count == 2 and result["step_id"] == "legacy_prepare_reviewer", result
        count = 0
        while result.get("step_id") == "legacy_prepare_reviewer":
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {
                    "review_token": _review_token(result),
                    "confirmed": True,
                    "reviewers": ["old-parent"],
                },
            )
            count += 1
        assert count == 2 and result["step_id"] == "legacy_prepare_photo", result
        count = 0
        while result.get("step_id") == "legacy_prepare_photo":
            image_id = await _upload(
                hass, owner, _image("PNG"), filename="report.png", content_type="image/png"
            )
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {
                    "review_token": _review_token(result),
                    "confirmed": True,
                    "photo": image_id,
                },
            )
            count += 1
        assert count == 3 and result["step_id"] == "legacy_copy_matches", result
        target_id = slot["intent"]["entry_id"]
        created.add(target_id)
        if not attempt:
            assert len(hass.config_entries.async_entries("family_assistant")) == entries_before
            for key in (
                f"family_assistant.{target_id}",
                f"family_assistant.copy_intent.{target_id}",
            ):
                assert await Store(hass, 1, key).async_load() is None
        while result.get("step_id") == "legacy_copy_matches":
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {
                    "review_token": _review_token(result),
                    "confirmed": True,
                },
            )
        assert result["step_id"] == "legacy_copy_review", result
        assert result["description_placeholders"]["photos"] == "3"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "review_token": _review_token(result),
                "confirmed": True,
            },
        )
        assert result["step_id"] == "legacy_copy_complete", result
        entry = hass.config_entries.async_get_entry(target_id)
        assert entry.state == ConfigEntryState.LOADED and entry.runtime_data.engine.shadow_mode
        assert entry.runtime_data.scheduler is None and entry.runtime_data.telegram is None
        exact = (
            target_id,
            dict(slot["intent"]),
            entry.runtime_data.engine.snapshot(),
            slot["package_fingerprint"],
        )
        if original is None:
            original = exact
        else:
            assert exact == original, (
                "Identical manual selections changed retry identity or sealed copy"
            )
        assert (await hass.config_entries.options.async_configure(result["flow_id"], {}))[
            "reason"
        ] == "migration_copy_finished"

    result = await source_files(await open_form(owner))
    cancelled = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "review_token": _review_token(result),
            "confirmed": False,
            "discard_review": True,
        },
    )
    assert cancelled["reason"] == "migration_copy_cancelled"
    assert "migration_copy_review" not in hass.data["family_assistant"]
    assert await Store(hass, 1, f"family_assistant.{original[0]}").async_load() == original[2]
    assert (
        await Store(hass, 1, f"family_assistant.copy_intent.{original[0]}").async_load()
        == original[1]
    )
    assert prototype.runtime_data.engine.snapshot() == source_state and not prototype.options
    assert (
        await Store(hass, 1, f"family_assistant.{prototype.entry_id}").async_load() == source_state
    )
    print(
        "PASS: native source-pair upload, two explicit member and two reviewer selections, "
        "three historical images, sealed copy, deterministic repeat and preparation "
        "discard without deleting the copy"
    )
