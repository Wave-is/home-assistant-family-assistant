"""Native Options/Store crash recovery using only a synthetic copied archive."""

import hashlib
import os
from pathlib import Path
from unittest.mock import patch


async def verify_residue_wizard(hass, owner, child, result, slot):
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.migration import copy_flow, residue_recovery
    from custom_components.family_assistant.migration.shadow_install import async_stage_shadow

    entry_id = slot["intent"]["entry_id"]
    fingerprint = slot["candidate"].summary()["fingerprint"]
    inputs = {
        "entry_id": entry_id,
        "user_id": owner.id,
        "candidate": slot["candidate"],
        "target": slot["target"],
        "expected_fingerprint": fingerprint,
        "authorize": None,
    }
    root = Path(
        hass.config.path("family_assistant_data", hashlib.sha256(entry_id.encode()).hexdigest())
    )
    saved_store = Store(hass, 1, f"family_assistant.{entry_id}")
    journal_store = Store(hass, 1, f"family_assistant.shadow_recovery.{entry_id}")
    blob_key, blob = next(iter(slot["candidate"].private_blobs().items()))
    names = (".upload-fake0001", ".upload-fake0002")

    def inject():
        (root / names[0]).write_bytes(blob[:17])
        os.link(root / blob_key, root / names[1])

    async def interrupted_registration(_hass, **kwargs):
        await async_stage_shadow(_hass, **kwargs)
        await hass.async_add_executor_job(inject)
        raise ValueError("synthetic_interrupted_before_registration")

    flow_id = result["flow_id"]
    with patch.object(copy_flow, "async_register_shadow", interrupted_registration):
        offered = await hass.config_entries.options.async_configure(
            flow_id, {"review_token": fingerprint, "confirmed": True}
        )
    assert offered["step_id"] == "legacy_copy_residue", offered
    assert offered["description_placeholders"]["temp_count"] == "2"
    assert await journal_store.async_load() is None
    exact = await saved_store.async_load()
    assert exact == slot["candidate"].private_state()
    assert hass.config_entries.async_get_entry(entry_id) is None
    review = slot["recovery"]
    token = review.summary()["fingerprint"]

    for changed in ({"user_id": child.id}, {"expected_fingerprint": "f" * 64}):
        try:
            await residue_recovery.async_review_residue(hass, **(inputs | changed))
        except residue_recovery.ResidueRecoveryError:
            pass
        else:
            raise AssertionError("Changed identity/candidate unexpectedly permitted recovery")
    for confirmed in (False, 1, "true"):
        try:
            await residue_recovery.async_preserve_residue(
                hass, review=review, confirmed=confirmed, **inputs
            )
        except residue_recovery.ResidueRecoveryError:
            pass
        else:
            raise AssertionError("Recovery requires exact separate confirmation")
    assert await journal_store.async_load() is None
    not_confirmed = await hass.config_entries.options.async_configure(
        flow_id, {"review_token": token, "confirmed": False}
    )
    assert not_confirmed["step_id"] == "legacy_copy_residue" and not_confirmed["errors"]
    assert await journal_store.async_load() is None

    original_save = residue_recovery._settled_save

    async def fail_completed_journal(store, value):
        if any(row["phase"] == "preserved" for row in value["records"].values()):
            raise OSError("synthetic_response_loss_after_preservation")
        await original_save(store, value)

    with patch.object(residue_recovery, "_settled_save", fail_completed_journal):
        retry = await hass.config_entries.options.async_configure(
            flow_id, {"review_token": token, "confirmed": True}
        )
    assert retry["step_id"] == "legacy_copy_residue" and retry["errors"]
    durable = await journal_store.async_load()
    assert durable["records"][token]["phase"] == "prepared"
    assert hass.config_entries.async_get_entry(entry_id) is None
    assert await saved_store.async_load() == exact
    # Rebuild from the durable journal, not an in-memory plan; this is the
    # same boundary a reuploaded candidate reaches after a Core restart.
    restored = await residue_recovery.async_review_residue(hass, **inputs)
    assert restored.summary() == review.summary()
    slot["recovery"] = restored
    archive = Path(
        hass.config.path(
            "family_assistant_recovery", hashlib.sha256(entry_id.encode()).hexdigest(), token
        )
    )

    def verify_preserved():
        assert (archive / names[0]).read_bytes() == blob[:17]
        assert (archive / names[1]).read_bytes() == blob
        assert not any((root / name).exists() for name in names)
        assert (root / blob_key).read_bytes() == blob
        assert (root / blob_key).stat().st_nlink == 1

    await hass.async_add_executor_job(verify_preserved)
    completed = await hass.config_entries.options.async_configure(
        flow_id, {"review_token": token, "confirmed": True}
    )
    assert completed["step_id"] == "legacy_copy_complete" and not completed["errors"], completed
    assert (await journal_store.async_load())["records"][token]["phase"] == "preserved"
    assert await saved_store.async_load() == exact
    assert hass.config_entries.async_get_entry(entry_id).runtime_data.engine.shadow_mode
    try:
        await residue_recovery.async_preserve_residue(
            hass, review=restored, confirmed=True, **inputs
        )
    except residue_recovery.ResidueRecoveryError:
        pass
    else:
        raise AssertionError("Recovery must never operate on a registered copy")
    await hass.async_add_executor_job(verify_preserved)
    print(
        "PASS: native Options separate residue consent, durable retry after interrupted journal, "
        "preserved partial upload/hardlink, unchanged Store and sealed registration"
    )
    return completed
