"""Internal new-entry staging: private blobs first, one atomic HA Store last.

No ConfigEntry creation, source mutation, registration or activation endpoint.
An immutable native-Store intent permits exact retries after interrupted staging.
Existing data is never overwritten or deleted. Only a fully verified read-only
Store becomes visible to a future, separately authorized entry-creation step.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from homeassistant.helpers.storage import Store

from ..const import DOMAIN, SCHEMA_VERSION
from ..media_storage import (
    _cleanup,
    _directory,
    _io,
    _publish,
    _read,
    _settle,
    _sync_close,
    _temporary,
)
from .shadow import ShadowError, _empty_target, async_reverify_shadow
from .shadow_entry import entry_marker


class ShadowInstallError(ValueError):
    """Only fixed codes, never storage paths, identities or source data."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _root_check(root, has_intent):
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ShadowInstallError("shadow_install_conflict")
    if root.exists() and not has_intent:
        # Even an empty pre-existing directory belongs to someone else.
        raise ShadowInstallError("shadow_install_conflict")


def _put_blob(root, key, content, metadata):
    stream, path = _temporary(root)
    try:
        stream.write(content)
        _sync_close(stream)
        _publish(root, path, key, metadata)
    finally:
        _cleanup(stream, path)


def _verify_blobs(root, blobs):
    _root_check(root, True)
    if root.exists():
        # Refuse unknown residues rather than deleting another actor's files.
        # Abrupt-process temporary files need separate reviewed recovery.
        for path in root.iterdir():
            if path.name not in blobs:
                raise ShadowInstallError("shadow_install_conflict")
    for key, expected in blobs.items():
        if _read(root, key) != expected:
            raise ShadowInstallError("shadow_install_conflict")


async def async_stage_shadow(hass, *, entry_id, user_id, candidate, target, expected_fingerprint):
    """Stage only a fresh unregistered entry, or resume its exact private intent.

    The caller must obtain a separate explicit owner review before calling this
    internal API. The fingerprint pins that exact displayed whole candidate;
    no arbitrary projection or partial set can be committed. A returned receipt
    is not permission to register the entry or enable providers.
    """
    if (
        type(entry_id) is not str
        or not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", entry_id)
        or type(user_id) is not str
        or not 0 < len(user_id) <= 128
        or type(expected_fingerprint) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint)
    ):
        raise ShadowInstallError("shadow_install_invalid")
    try:
        _empty_target(target)
    except ShadowError:
        raise ShadowInstallError("shadow_install_invalid") from None
    frozen_target = _encode(target)
    selected_target = json.loads(frozen_target)
    owner = selected_target.get("members", {}).get("owner", {})
    domain = hass.data.setdefault(DOMAIN, {})
    domain.setdefault("entries", {})

    async def guard():
        user = await hass.auth.async_get_user(user_id)
        if (
            not user
            or not user.is_active
            or not user.is_admin
            or owner.get("ha_user_id") != user.id
            or owner.get("role") != "owner"
            or owner.get("active") is not True
            or _encode(target) != frozen_target
        ):
            raise ShadowInstallError("shadow_install_forbidden")
        if (
            hass.config_entries.async_get_entry(entry_id) is not None
            or entry_id in domain["entries"]
            or domain.get("backup")
        ):
            raise ShadowInstallError("shadow_install_busy")

    await guard()
    try:
        verified = await async_reverify_shadow(candidate, selected_target)
    except ShadowError:
        raise ShadowInstallError("shadow_install_invalid") from None
    state, blobs = verified.private_state(), verified.private_blobs()
    if verified.summary()["fingerprint"] != expected_fingerprint:
        raise ShadowInstallError("shadow_install_changed")
    receipt = {
        "mode": "read_only_shadow_staged",
        "fingerprint": expected_fingerprint,
        "entry_marker": entry_marker(state, expected_fingerprint),
    }
    intent = {
        "version": 1,
        "mode": "read_only_shadow_staging",
        "fingerprint": expected_fingerprint,
        "target_fingerprint": hashlib.sha256(frozen_target).hexdigest(),
    }
    root = Path(
        hass.config.path("family_assistant_data", hashlib.sha256(entry_id.encode()).hexdigest())
    )
    store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry_id}")
    journal = Store(hass, 1, f"{DOMAIN}.shadow_intent.{entry_id}")
    lock = domain.setdefault("setup_lock", asyncio.Lock())
    try:
        async with lock:
            await guard()
            saved = await store.async_load()
            if saved is not None:
                if _encode(saved) != verified._state:
                    raise ShadowInstallError("shadow_install_conflict")
                await _io(_verify_blobs, root, blobs)
                await guard()
                return receipt
            previous_intent = await journal.async_load()
            if previous_intent is not None and _encode(previous_intent) != _encode(intent):
                raise ShadowInstallError("shadow_install_conflict")
            await _io(_root_check, root, previous_intent is not None)
            await guard()
            if previous_intent is None:
                await _settled_save(journal, intent)
            if blobs:
                await _io(_directory, root)
            for record in state.get("media", {}).values():
                await guard()
                key = record["blob_key"]
                await _io(_put_blob, root, key, blobs[key], record)
            await _io(_verify_blobs, root, blobs)
            await guard()
            # Last await before publication rechecks that no Store appeared while
            # preparing the blobs. There are no worker/entity/ConfigEntry effects.
            if await store.async_load() is not None:
                raise ShadowInstallError("shadow_install_conflict")
            await guard()
            await _settled_save(store, state)
            if _encode(await store.async_load()) != verified._state:
                raise ShadowInstallError("shadow_install_uncertain")
            await guard()
            return receipt
    except ShadowInstallError:
        raise
    except (OSError, ValueError, KeyError):
        # Leave the immutable intent/blobs for exact retry, never delete or roll
        # back a Store whose write outcome may be uncertain.
        raise ShadowInstallError("shadow_install_retry_required") from None


async def _settled_save(store, value):
    task = asyncio.create_task(store.async_save(value))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await _settle(task)
        except Exception:  # noqa: BLE001, S110 - retain cancellation; never log private Store data
            pass
        raise
