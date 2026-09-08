"""Internal reviewed shadow registration using Core's native ConfigEntry API.

This is not a ConfigFlow, network endpoint, source capture or activation API.
The future wizard must retain one reviewed target ID across uncertain retries.
Never manufacture a second ID to recover an uncertain registration result.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers.storage import Store

from ..const import DOMAIN, SCHEMA_VERSION
from ..domain.validation import DomainError
from ..media_storage import _io, _settle
from .shadow import ShadowError, _empty_target, async_reverify_shadow
from .shadow_entry import KEY, entry_marker, validate_entry_state
from .shadow_install import ShadowInstallError, _verify_blobs, async_stage_shadow


class ShadowRegistrationError(ValueError):
    """Fixed codes only; no private state, filenames or raw Core exceptions."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


async def async_register_shadow(
    hass, *, entry_id, user_id, candidate, target, expected_fingerprint
):
    """Stage then register exactly one sealed, owner-only read-only entry.

    Caller review is a prerequisite; possessing a dataclass or a fingerprint is
    not user consent. Existing entries are accepted only as exact read-only
    retries. No existing configuration, Store, media or source is overwritten.
    """
    # Reuse the same strict identifier contract as staging even for an existing
    # entry retry. Do not resolve an arbitrary caller-supplied filesystem path.
    import re

    if (
        type(entry_id) is not str
        or not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", entry_id)
        or type(user_id) is not str
        or not 0 < len(user_id) <= 128
    ):
        raise ShadowRegistrationError("shadow_registration_invalid")
    try:
        frozen_target = _encode(target)
        selected = json.loads(frozen_target)
        _empty_target(selected)
    except (ShadowError, DomainError, TypeError, ValueError, RecursionError):
        raise ShadowRegistrationError("shadow_registration_invalid") from None
    owner, settings = selected["members"]["owner"], selected["settings"]
    domain = hass.data.setdefault(DOMAIN, {})
    domain.setdefault("entries", {})

    async def guard():
        user = await hass.auth.async_get_user(user_id)
        try:
            unchanged = _encode(target) == frozen_target
        except (TypeError, ValueError, RecursionError):
            unchanged = False
        if (
            not user
            or not user.is_active
            or not user.is_admin
            or user.id != user_id
            or user.id != owner["ha_user_id"]
            or not unchanged
        ):
            raise ShadowRegistrationError("shadow_registration_forbidden")
        if domain.get("backup"):
            raise ShadowRegistrationError("shadow_registration_busy")

    await guard()
    try:
        verified = await async_reverify_shadow(candidate, selected)
        state = verified.private_state()
        seal = entry_marker(state, expected_fingerprint)
    except (ShadowError, DomainError, TypeError, ValueError, RecursionError):
        raise ShadowRegistrationError("shadow_registration_invalid") from None
    entry_data = {
        "owner_user_id": owner["ha_user_id"],
        "owner_name": owner["name"],
        "name": settings["name"],
        "language": settings["language"],
        "timezone": settings["timezone"],
        "modules": [],
        KEY: seal,
    }

    def same_entry(entry):
        return (
            entry.domain == DOMAIN
            and entry.source == "user"
            and entry.version == 1
            and entry.minor_version == 1
            and entry.unique_id == f"migration-shadow-{entry_id}"
            and entry.title == settings["name"]
            and _encode(dict(entry.data)) == _encode(entry_data)
            and not entry.options
        )

    await guard()
    # Separate from setup_lock: Core's async_add immediately registers the
    # entry and then calls our normal setup, which itself takes setup_lock.
    async with domain.setdefault("shadow_registration_lock", asyncio.Lock()):
        try:
            await guard()
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                await async_stage_shadow(
                    hass,
                    entry_id=entry_id,
                    user_id=user_id,
                    candidate=verified,
                    target=selected,
                    expected_fingerprint=expected_fingerprint,
                )
                await guard()
                if hass.config_entries.async_get_entry(entry_id) is not None:
                    raise ShadowRegistrationError("shadow_registration_conflict")
                entry = ConfigEntry(
                    entry_id=entry_id,
                    version=1,
                    minor_version=1,
                    domain=DOMAIN,
                    source="user",
                    title=settings["name"],
                    unique_id=f"migration-shadow-{entry_id}",
                    data=entry_data,
                    options={},
                    discovery_keys=MappingProxyType({}),
                    subentries_data=None,
                )
                # The owned task repeats its guard immediately before Core's
                # synchronous insertion. Setup is sealed even if the reply is lost.
                await _settled_add(hass.config_entries, entry, guard)
            elif not same_entry(entry):
                raise ShadowRegistrationError("shadow_registration_conflict")
            await guard()
            if hass.config_entries.async_get_entry(entry_id) is not entry or not same_entry(entry):
                raise ShadowRegistrationError("shadow_registration_conflict")
            store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry_id}")
            current = await store.async_load()
            if _encode(current) != verified._state:
                raise ShadowRegistrationError("shadow_registration_conflict")
            validate_entry_state(entry.data, current)
            root = Path(
                hass.config.path(
                    "family_assistant_data", hashlib.sha256(entry_id.encode()).hexdigest()
                )
            )
            await _io(_verify_blobs, root, verified.private_blobs())
            await guard()
            if hass.config_entries.async_get_entry(entry_id) is not entry or not same_entry(entry):
                raise ShadowRegistrationError("shadow_registration_conflict")
            # Do not force reload/retry an entry that Core is setting up. An
            # unloaded/disabled/retrying entry remains registered and sealed;
            # the receipt distinguishes this from an actually loaded viewer.
            runtime = domain["entries"].get(entry_id)
            loaded = entry.state == ConfigEntryState.LOADED and runtime is not None
            if loaded and (
                not runtime.engine.shadow_mode
                or _encode(runtime.engine.snapshot()) != verified._state
            ):
                raise ShadowRegistrationError("shadow_registration_conflict")
            return {
                "mode": "read_only_shadow_registered",
                "entry_id": entry_id,
                "fingerprint": expected_fingerprint,
                "loaded": loaded,
                "activation_available": False,
            }
        except ShadowRegistrationError:
            raise
        except ShadowInstallError:
            raise ShadowRegistrationError("shadow_registration_retry_required") from None
        except Exception:  # noqa: BLE001 - Core/provider text may contain private data
            # The entry may already be registered. Never remove it or invent a
            # new one; the same ID and exact candidate are the only safe retry.
            raise ShadowRegistrationError("shadow_registration_retry_required") from None


async def _settled_add(manager, entry, guard):
    """Drain an owned Core insertion before releasing the registration lock."""

    async def guarded_add():
        await guard()
        if manager.async_get_entry(entry.entry_id) is not None:
            raise ShadowRegistrationError("shadow_registration_conflict")
        await manager.async_add(entry)

    task = asyncio.create_task(guarded_add())
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await _settle(task)
        except Exception:  # noqa: BLE001, S110 - preserve cancellation, never print Core text
            pass
        raise
