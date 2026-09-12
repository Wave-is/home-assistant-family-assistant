"""Two-process actual-HA copy resume acceptance helper.

The orchestrator installs the integration under a writable synthetic HA config
directory, then invokes this file in two separate Python processes::

    python tests/ha_copy_resume_acceptance.py prepare --config ... --contract ... \
        --expected-version ...
    python tests/ha_copy_resume_acceptance.py verify --config ... --contract ... \
        --expected-version ...

Process 1 stages a verified candidate copy through native Options ZIP upload and
intercepts registration to simulate process termination prior to ConfigEntry
creation. Process 2 boots a fresh Home Assistant core, proves no in-memory
candidate survived, verifies the copy is discoverable via native index Options,
validates child denial and false-consent rejection, registers the sealed entry
with true consent, and proves repeated resume produces no duplicate entry.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from ha_copy_wizard_smoke import _open, _package, _review_token, _upload
from ha_options_menu import select_option
from ha_upgrade_acceptance import _runtime_version, _start
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.storage import Store

DOMAIN = "family_assistant"
SCHEMA_VERSION = 1
CONTRACT_SCHEMA = 1

REQUIRED_CONTRACT_KEYS = frozenset(
    {
        "schema",
        "prepare_pid",
        "expected_version",
        "prototype_entry_id",
        "owner_user_id",
        "child_user_id",
        "shadow_entry_id",
        "package_fingerprint",
        "fingerprint",
        "blob_count",
        "original_store_hash",
        "index_store_hash",
        "shadow_store_hash",
        "copy_intent_hash",
        "shadow_intent_hash",
        "media_digest",
    }
)


def _canonical_hash(value: Any) -> str:
    """Compute deterministic canonical sha256 hash of native Store data."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_media_root(hass: HomeAssistant, entry_id: str) -> Path:
    """Resolve entry media storage root via native Home Assistant storage path API."""
    return Path(
        hass.config.path(
            "family_assistant_data",
            hashlib.sha256(entry_id.encode("utf-8")).hexdigest(),
        )
    )


def _media_digest(root: Path) -> dict[str, str]:
    """Collect sha256 digests of all stored blobs by known scoped relative path."""
    if not root.is_dir() or root.is_symlink():
        raise AssertionError("media root directory is invalid")
    result: dict[str, str] = {}
    paths = list(root.iterdir())
    if not 0 < len(paths) <= 512:
        raise AssertionError("synthetic media count is invalid")
    for path in sorted(paths):
        if (
            path.is_symlink()
            or not path.is_file()
            or re.fullmatch(r"[0-9a-f]{64}", path.name) is None
            or not 0 < path.stat().st_size <= 10 * 1024 * 1024
        ):
            raise AssertionError("unexpected synthetic media entry")
        content = path.read_bytes()
        result[path.name] = hashlib.sha256(content).hexdigest()
    return result


async def _open_resume(
    hass: HomeAssistant,
    prototype: ConfigEntry,
    user: Any,
    flows: set[str],
) -> dict:
    """Open the legacy resume options step for a given user."""
    opened = await hass.config_entries.options.async_init(
        prototype.entry_id, context={"user_id": user.id}
    )
    flows.add(opened["flow_id"])
    return await select_option(hass, opened, "legacy_resume")


def _validate_contract(value: object) -> dict:
    """Enforce strict contract schema containing only fingerprints, IDs and hashes."""
    if type(value) is not dict:
        raise AssertionError("copy resume contract is invalid")
    if (
        set(value) != REQUIRED_CONTRACT_KEYS
        or type(value.get("schema")) is not int
        or value["schema"] != CONTRACT_SCHEMA
    ):
        raise AssertionError("copy resume contract schema is invalid")
    if type(value["prepare_pid"]) is not int or value["prepare_pid"] <= 0:
        raise AssertionError("copy resume contract prepare_pid is invalid")
    for key in (
        "expected_version",
        "prototype_entry_id",
        "owner_user_id",
        "child_user_id",
        "shadow_entry_id",
        "package_fingerprint",
        "fingerprint",
        "original_store_hash",
        "index_store_hash",
        "shadow_store_hash",
        "copy_intent_hash",
        "shadow_intent_hash",
    ):
        field_value = value.get(key)
        if type(field_value) is not str or not 0 < len(field_value) <= 128:
            raise AssertionError(f"copy resume contract {key} is invalid")
    for hash_key in (
        "package_fingerprint",
        "fingerprint",
        "original_store_hash",
        "index_store_hash",
        "shadow_store_hash",
        "copy_intent_hash",
        "shadow_intent_hash",
    ):
        if re.fullmatch(r"[0-9a-f]{64}", value[hash_key]) is None:
            raise AssertionError(f"copy resume contract {hash_key} length is invalid")
    if type(value["blob_count"]) is not int or not 0 < value["blob_count"] <= 512:
        raise AssertionError("copy resume contract blob_count is invalid")
    digest = value.get("media_digest")
    if type(digest) is not dict or len(digest) != value["blob_count"]:
        raise AssertionError("copy resume contract media_digest is invalid")
    for path_key, sha_val in digest.items():
        if (
            type(path_key) is not str
            or re.fullmatch(r"[0-9a-f]{64}", path_key) is None
            or type(sha_val) is not str
            or re.fullmatch(r"[0-9a-f]{64}", sha_val) is None
        ):
            raise AssertionError("copy resume contract media_digest entry is invalid")
    return value


async def prepare(config_directory: Path, expected_version: str) -> dict:
    """Stage a candidate copy, intercept registration, and record durable contract."""
    actual_version = _runtime_version(config_directory)
    if actual_version != expected_version:
        raise AssertionError("baseline artifact version mismatch")

    hass = await _start(config_directory)
    try:
        if hass.config_entries.async_entries(DOMAIN):
            raise AssertionError("prepare requires a fresh synthetic HA config")

        owner = await hass.auth.async_create_user(
            "Synthetic copy resume owner", group_ids=[GROUP_ID_ADMIN]
        )
        child = await hass.auth.async_create_user("Synthetic copy resume child")

        prototype = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
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
        await hass.config_entries.async_add(prototype)
        await hass.async_block_till_done()
        if prototype.state != ConfigEntryState.LOADED:
            raise AssertionError("prototype config entry did not load")

        source_state = prototype.runtime_data.engine.snapshot()
        source_store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{prototype.entry_id}")
        original_store_data = await source_store.async_load()
        if original_store_data != source_state:
            raise AssertionError("prototype engine state mismatch with persisted Store")

        flows: set[str] = set()
        bundle = _package(source_state["members"])
        result = await _open(hass, prototype, owner, flows)
        if result.get("type") != "form" or result.get("step_id") != "legacy_copy":
            raise AssertionError("legacy_copy options form did not open")

        upload_id = await _upload(hass, owner, bundle)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "copy_name": "Synthetic resumable staged copy",
                "bundle": upload_id,
                "private_files_reviewed": True,
            },
        )
        while result.get("step_id") == "legacy_copy_matches":
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                {"review_token": _review_token(result), "confirmed": True},
            )
        if result.get("step_id") != "legacy_copy_review":
            raise AssertionError("legacy_copy_review step did not open")

        slot = hass.data[DOMAIN]["migration_copy_review"]
        shadow_entry_id = slot["intent"]["entry_id"]
        fingerprint = slot["candidate"].summary()["fingerprint"]
        package_fingerprint = slot["package_fingerprint"]
        blobs = slot["candidate"].private_blobs()
        candidate_state = slot["candidate"].private_state()

        from custom_components.family_assistant.migration import copy_flow
        from custom_components.family_assistant.migration.shadow_install import async_stage_shadow

        async def interrupt_after_complete_staging(_hass, **kwargs):
            await async_stage_shadow(_hass, **kwargs)
            raise ValueError("synthetic_process_loss_before_registration")

        with patch.object(copy_flow, "async_register_shadow", interrupt_after_complete_staging):
            failed = await hass.config_entries.options.async_configure(
                result["flow_id"], {"review_token": fingerprint, "confirmed": True}
            )
        if failed.get("step_id") != "legacy_copy_review" or not failed.get("errors"):
            raise AssertionError("interrupted registration did not record review failure")

        if hass.config_entries.async_get_entry(shadow_entry_id) is not None:
            raise AssertionError("copy config entry unexpectedly exists before resume")

        shadow_store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{shadow_entry_id}")
        shadow_data = await shadow_store.async_load()
        if shadow_data != candidate_state:
            raise AssertionError("staged shadow state was not durably stored")

        index_store = Store(hass, 1, f"{DOMAIN}.copy_index")
        index_data = await index_store.async_load()
        if not isinstance(index_data, dict) or shadow_entry_id not in index_data.get("records", {}):
            raise AssertionError("staged copy was not recorded in copy index")

        copy_intent_store = Store(hass, 1, f"{DOMAIN}.copy_intent.{shadow_entry_id}")
        copy_intent_data = await copy_intent_store.async_load()
        if copy_intent_data is None:
            raise AssertionError("copy intent was not durably stored")

        shadow_intent_store = Store(hass, 1, f"{DOMAIN}.shadow_intent.{shadow_entry_id}")
        shadow_intent_data = await shadow_intent_store.async_load()
        if shadow_intent_data is None:
            raise AssertionError("shadow intent was not durably stored")

        media_root = _resolve_media_root(hass, shadow_entry_id)
        media_digest = _media_digest(media_root)
        if len(media_digest) != len(blobs):
            raise AssertionError("media digest count mismatch with staged blobs")

        if prototype.runtime_data.engine.snapshot() != source_state:
            raise AssertionError("original business state changed during copy staging")

        contract = {
            "schema": CONTRACT_SCHEMA,
            "prepare_pid": os.getpid(),
            "expected_version": actual_version,
            "prototype_entry_id": prototype.entry_id,
            "owner_user_id": owner.id,
            "child_user_id": child.id,
            "shadow_entry_id": shadow_entry_id,
            "package_fingerprint": package_fingerprint,
            "fingerprint": fingerprint,
            "blob_count": len(blobs),
            "original_store_hash": _canonical_hash(original_store_data),
            "index_store_hash": _canonical_hash(index_data),
            "shadow_store_hash": _canonical_hash(shadow_data),
            "copy_intent_hash": _canonical_hash(copy_intent_data),
            "shadow_intent_hash": _canonical_hash(shadow_intent_data),
            "media_digest": media_digest,
        }

        # Graceful shutdown to flush native auth and config entry writes to disk
        await hass.async_block_till_done()
        await hass.async_stop()
        if hass.state is not CoreState.stopped:
            raise AssertionError("Home Assistant did not stop gracefully")
    finally:
        if hass.is_running:
            await hass.async_stop(force=True)

    return contract


async def verify(config_directory: Path, expected_version: str, contract: dict) -> None:
    """Verify durable continuity, child denial, resume Options, and sealed copy."""
    contract = _validate_contract(contract)

    if os.getpid() == contract["prepare_pid"]:
        raise AssertionError("verify executed in the same process as prepare")

    actual_version = _runtime_version(config_directory)
    if actual_version != expected_version:
        raise AssertionError("installed candidate runtime version mismatch")
    if actual_version != contract["expected_version"]:
        raise AssertionError("runtime version differs from baseline contract version")

    hass = await _start(config_directory)
    try:
        # Verify fresh bootstrap: no in-memory candidate survived process restart
        if hass.data.get(DOMAIN, {}).get("migration_copy_review") is not None:
            raise AssertionError("in-memory candidate unexpectedly retained across restart")

        prototype = hass.config_entries.async_get_entry(contract["prototype_entry_id"])
        if prototype is None or prototype.state != ConfigEntryState.LOADED:
            raise AssertionError("prototype config entry did not load cleanly")
        if prototype.options:
            raise AssertionError("prototype Options unexpectedly modified")

        # Native Store read hashes: no direct .storage reads and no mutations
        original_store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{prototype.entry_id}")
        original_data = await original_store.async_load()
        if _canonical_hash(original_data) != contract["original_store_hash"]:
            raise AssertionError("original Store hash changed across process restart")
        if prototype.runtime_data.engine.snapshot() != original_data:
            raise AssertionError("prototype runtime engine differs from persisted Store")

        index_store = Store(hass, 1, f"{DOMAIN}.copy_index")
        index_data = await index_store.async_load()
        if _canonical_hash(index_data) != contract["index_store_hash"]:
            raise AssertionError("copy index Store hash changed across process restart")

        shadow_store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{contract['shadow_entry_id']}")
        shadow_data = await shadow_store.async_load()
        if _canonical_hash(shadow_data) != contract["shadow_store_hash"]:
            raise AssertionError("shadow Store hash changed across process restart")

        copy_intent_store = Store(hass, 1, f"{DOMAIN}.copy_intent.{contract['shadow_entry_id']}")
        copy_intent_data = await copy_intent_store.async_load()
        if _canonical_hash(copy_intent_data) != contract["copy_intent_hash"]:
            raise AssertionError("copy intent Store hash changed across process restart")

        shadow_intent_store = Store(
            hass, 1, f"{DOMAIN}.shadow_intent.{contract['shadow_entry_id']}"
        )
        shadow_intent_data = await shadow_intent_store.async_load()
        if _canonical_hash(shadow_intent_data) != contract["shadow_intent_hash"]:
            raise AssertionError("shadow intent Store hash changed across process restart")

        # Media blob verification via native runtime storage API
        media_root = _resolve_media_root(hass, contract["shadow_entry_id"])
        actual_blobs = _media_digest(media_root)
        if actual_blobs != contract["media_digest"]:
            raise AssertionError("media blob digest mismatch in fresh process")
        if len(actual_blobs) != contract["blob_count"]:
            raise AssertionError("media blob count mismatch in fresh process")

        owner = await hass.auth.async_get_user(contract["owner_user_id"])
        if owner is None or not owner.is_admin or not owner.is_active:
            raise AssertionError("synthetic owner user missing or not active admin")

        child = await hass.auth.async_get_user(contract["child_user_id"])
        if child is None or not child.is_active or child.is_admin:
            raise AssertionError("synthetic child user missing, inactive or admin")

        if hass.config_entries.async_get_entry(contract["shadow_entry_id"]) is not None:
            raise AssertionError("shadow entry unexpectedly registered before resume")

        flows: set[str] = set()

        # Child denied
        denied = await _open_resume(hass, prototype, child, flows)
        if denied.get("type") != "abort" or denied.get("reason") != "forbidden":
            raise AssertionError("child was not denied access to legacy resume")

        # Owner discovers actual resume Options
        resumed = await _open_resume(hass, prototype, owner, flows)
        if resumed.get("type") != "form" or resumed.get("step_id") != "legacy_resume":
            raise AssertionError("owner could not open legacy resume step")

        resumed = await hass.config_entries.options.async_configure(
            resumed["flow_id"],
            {
                "review_token": _review_token(resumed),
                "attempt": contract["shadow_entry_id"],
            },
        )
        if resumed.get("type") != "form" or resumed.get("step_id") != "legacy_resume_review":
            raise AssertionError("legacy resume review form did not open")

        placeholders = resumed.get("description_placeholders", {})
        if placeholders.get("fingerprint") != contract["fingerprint"]:
            raise AssertionError("fingerprint placeholder mismatch in resume review")
        if placeholders.get("photos") != str(contract["blob_count"]):
            raise AssertionError("photo count placeholder mismatch in resume review")

        # False consent: zero entry created
        declined = await hass.config_entries.options.async_configure(
            resumed["flow_id"],
            {"review_token": contract["fingerprint"], "confirmed": False},
        )
        if declined.get("step_id") != "legacy_resume_review":
            raise AssertionError("declining consent did not return to review step")
        if hass.config_entries.async_get_entry(contract["shadow_entry_id"]) is not None:
            raise AssertionError("shadow entry created without user consent")

        # True consent: same sealed ID, LOADED state, shadow mode, zero providers or scheduler
        completed = await hass.config_entries.options.async_configure(
            resumed["flow_id"],
            {"review_token": contract["fingerprint"], "confirmed": True},
        )
        if completed.get("step_id") != "legacy_copy_complete" or completed.get("errors"):
            raise AssertionError("resume confirmation failed")

        shadow_entry = hass.config_entries.async_get_entry(contract["shadow_entry_id"])
        if shadow_entry is None:
            raise AssertionError("shadow config entry was not created upon consent")
        if shadow_entry.entry_id != contract["shadow_entry_id"]:
            raise AssertionError("shadow entry ID differs from sealed staged ID")
        if shadow_entry.state != ConfigEntryState.LOADED:
            raise AssertionError("shadow config entry did not load cleanly")

        shadow_runtime = shadow_entry.runtime_data
        if shadow_runtime.engine.snapshot() != shadow_data:
            raise AssertionError("loaded shadow differs from the exact staged Store")
        if not getattr(shadow_runtime.engine, "shadow_mode", False):
            raise AssertionError("shadow entry is not in shadow mode")
        if shadow_runtime.scheduler is not None:
            raise AssertionError("shadow entry unexpectedly started a scheduler")
        if shadow_runtime.telegram is not None:
            raise AssertionError("shadow entry unexpectedly started telegram")
        if shadow_runtime.assistant is not None:
            raise AssertionError("shadow entry unexpectedly started assistant")
        if getattr(shadow_runtime, "network", None) is not None:
            raise AssertionError("shadow entry unexpectedly started network provider")
        if getattr(shadow_runtime, "recipes", None) is not None:
            raise AssertionError("shadow entry unexpectedly started recipes provider")

        finished = await hass.config_entries.options.async_configure(completed["flow_id"], {})
        if finished.get("type") != "abort" or finished.get("reason") != "migration_copy_finished":
            raise AssertionError("resume flow did not finish cleanly")

        # Repeat exact resume: no duplicate entry
        repeat = await _open_resume(hass, prototype, owner, flows)
        if repeat.get("type") != "form" or repeat.get("step_id") != "legacy_resume":
            raise AssertionError("second resume attempt could not open legacy resume")

        repeat = await hass.config_entries.options.async_configure(
            repeat["flow_id"],
            {
                "review_token": _review_token(repeat),
                "attempt": contract["shadow_entry_id"],
            },
        )
        if repeat.get("type") != "form" or repeat.get("step_id") != "legacy_resume_review":
            raise AssertionError("second resume review form did not open")

        completed_repeat = await hass.config_entries.options.async_configure(
            repeat["flow_id"],
            {"review_token": contract["fingerprint"], "confirmed": True},
        )
        if completed_repeat.get("step_id") != "legacy_copy_complete" or completed_repeat.get(
            "errors"
        ):
            raise AssertionError("repeated resume confirmation failed")

        finished_repeat = await hass.config_entries.options.async_configure(
            completed_repeat["flow_id"], {}
        )
        if (
            finished_repeat.get("type") != "abort"
            or finished_repeat.get("reason") != "migration_copy_finished"
        ):
            raise AssertionError("second resume flow did not finish cleanly")

        shadow_entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id != prototype.entry_id
        ]
        if len(shadow_entries) != 1:
            raise AssertionError("duplicate shadow entry created by repeated resume")
        if shadow_entries[0].entry_id != contract["shadow_entry_id"]:
            raise AssertionError("shadow entry ID mismatch after repeated resume")

        # Native Store integrity: exact canonical hashes unchanged
        if _canonical_hash(await original_store.async_load()) != contract["original_store_hash"]:
            raise AssertionError("original Store hash mutated after resume")
        if prototype.runtime_data.engine.snapshot() != original_data:
            raise AssertionError("original business state changed during resume")
        if _canonical_hash(await index_store.async_load()) != contract["index_store_hash"]:
            raise AssertionError("copy index Store mutated after resume")
        if _canonical_hash(await shadow_store.async_load()) != contract["shadow_store_hash"]:
            raise AssertionError("shadow Store mutated after resume")
        if _canonical_hash(await copy_intent_store.async_load()) != contract["copy_intent_hash"]:
            raise AssertionError("copy intent Store mutated after resume")
        if (
            _canonical_hash(await shadow_intent_store.async_load())
            != contract["shadow_intent_hash"]
        ):
            raise AssertionError("shadow intent Store mutated after resume")

        # Media root integrity via active runtime storage reference
        active_media_root = shadow_runtime.media.root
        media_after = _media_digest(active_media_root)
        if media_after != contract["media_digest"]:
            raise AssertionError("media blobs mutated during resume")

        # Graceful shutdown
        await hass.async_block_till_done()
        await hass.async_stop()
        if hass.state is not CoreState.stopped:
            raise AssertionError("Home Assistant did not stop gracefully in verify")
    finally:
        if hass.is_running:
            await hass.async_stop(force=True)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    config_directory = arguments.config.resolve(strict=True)
    if arguments.phase == "prepare":
        contract = asyncio.run(prepare(config_directory, arguments.expected_version))
        arguments.contract.parent.mkdir(parents=True, exist_ok=True)
        with arguments.contract.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(contract, target, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            target.write("\n")
        print("PASS: baseline staged copy created durable resume contract")
        return

    try:
        contract = json.loads(arguments.contract.read_bytes())
    except (OSError, TypeError, ValueError) as error:
        raise AssertionError("resume contract could not be read") from error

    asyncio.run(verify(config_directory, arguments.expected_version, contract))
    print(
        "PASS: candidate verified resume Options, identical Store hashes and duplicate prevention"
    )


if __name__ == "__main__":
    main()
