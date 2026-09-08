"""Owner-reviewed preservation of interrupted, unregistered shadow upload files.

No activation, source capture, directory discovery, or automatic cleanup. The
caller supplies the same reviewed candidate/target and holds its wizard scope.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from homeassistant.helpers.storage import Store

from ..const import DOMAIN, SCHEMA_VERSION
from ..domain.validation import DomainError
from ..media_storage import _io
from .shadow import _empty_target, async_reverify_shadow
from .shadow_install import _settled_save


class ResidueRecoveryError(ValueError):
    """Fixed codes; never include names, paths, private manifests or Core errors."""


def _encode(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


@dataclass(frozen=True, repr=False)
class ResidueReview:
    _identity: bytes = field(repr=False)
    _manifest: bytes = field(repr=False)
    _summary: bytes = field(repr=False)

    def __repr__(self):
        return "ResidueReview(private=True, activation_available=False)"

    def summary(self):
        return json.loads(self._summary)


def _journal(value, identity):
    if value is None:
        return {"version": 1, "identity": identity, "records": {}}
    if (
        type(value) is not dict
        or set(value) != {"version", "identity", "records"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["identity"] != identity
        or type(value["records"]) is not dict
        or len(value["records"]) > 16
    ):
        raise ResidueRecoveryError("migration_residue_conflict")
    pending = 0
    from .temporary_recovery import restore_plan

    for fingerprint, row in value["records"].items():
        if (
            type(row) is not dict
            or set(row) != {"phase", "manifest"}
            or row["phase"] not in ("prepared", "preserved")
            or type(fingerprint) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", fingerprint)
            or restore_plan(row["manifest"]).summary()["fingerprint"] != fingerprint
        ):
            raise ResidueRecoveryError("migration_residue_conflict")
        pending += row["phase"] == "prepared"
    if pending > 1:
        raise ResidueRecoveryError("migration_residue_conflict")
    return json.loads(_encode(value))


async def _inputs(hass, *, entry_id, user_id, candidate, target, expected_fingerprint, authorize):
    if (
        type(entry_id) is not str
        or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", entry_id)
        or type(user_id) is not str
        or not 0 < len(user_id) <= 128
        or type(expected_fingerprint) is not str
        or not re.fullmatch(r"[a-f0-9]{64}", expected_fingerprint)
    ):
        raise ResidueRecoveryError("migration_residue_conflict")
    _empty_target(target)
    frozen = _encode(target)
    domain = hass.data.setdefault(DOMAIN, {})
    identity = {
        "entry_id": entry_id,
        "owner_user_id": user_id,
        "target_fingerprint": hashlib.sha256(frozen).hexdigest(),
        "fingerprint": expected_fingerprint,
    }

    async def guard():
        user = await hass.auth.async_get_user(user_id)
        if (
            not user
            or not user.is_active
            or not user.is_admin
            or user.id != user_id
            or target["members"]["owner"].get("ha_user_id") != user_id
            or _encode(target) != frozen
        ):
            raise ResidueRecoveryError("migration_residue_forbidden")
        if (
            domain.get("backup")
            or hass.config_entries.async_get_entry(entry_id) is not None
            or entry_id in domain.get("entries", {})
        ):
            raise ResidueRecoveryError("migration_residue_busy")
        if authorize is not None:
            await authorize()

    await guard()
    verified = await async_reverify_shadow(candidate, target)
    await guard()
    if verified.summary()["fingerprint"] != expected_fingerprint:
        raise ResidueRecoveryError("migration_residue_conflict")
    root = Path(
        hass.config.path("family_assistant_data", hashlib.sha256(entry_id.encode()).hexdigest())
    )
    journal = Store(hass, 1, f"{DOMAIN}.shadow_recovery.{entry_id}")

    async def stored():
        await guard()
        intent = await Store(hass, 1, f"{DOMAIN}.shadow_intent.{entry_id}").async_load()
        await guard()
        if _encode(intent) != _encode(
            {
                "version": 1,
                "mode": "read_only_shadow_staging",
                "fingerprint": expected_fingerprint,
                "target_fingerprint": identity["target_fingerprint"],
            }
        ):
            raise ResidueRecoveryError("migration_residue_conflict")
        saved = await Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry_id}").async_load()
        await guard()
        if saved is not None and _encode(saved) != verified._state:
            raise ResidueRecoveryError("migration_residue_conflict")
        return _journal(await journal.async_load(), identity)

    return domain, identity, verified, root, journal, guard, stored


async def async_review_residue(hass, **kwargs):
    """Read only: current residue or a durable unfinished preservation attempt."""
    from .temporary_recovery import inspect_residue, restore_plan

    try:
        domain, identity, candidate, root, _store, guard, stored = await _inputs(hass, **kwargs)
        # Match registration -> setup lock order, preventing Core insertion while
        # a recovery inspects/preserves an as-yet-unregistered directory.
        async with domain.setdefault("shadow_registration_lock", asyncio.Lock()):
            async with domain.setdefault("setup_lock", asyncio.Lock()):
                journal = await stored()
                pending = [r for r in journal["records"].values() if r["phase"] == "prepared"]
                plan = (
                    restore_plan(pending[0]["manifest"])
                    if pending
                    else await _io(inspect_residue, root, candidate.private_blobs())
                )
                await guard()
                if plan is None:
                    return None
                return ResidueReview(
                    _encode(identity), _encode(plan.private_manifest()), _encode(plan.summary())
                )
    except ResidueRecoveryError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError):
        raise ResidueRecoveryError("migration_residue_conflict") from None


async def async_preserve_residue(hass, *, review, confirmed, **kwargs):
    """Preserve reviewed temps before removing their active names; never a blank reset."""
    from .temporary_recovery import apply_residue, restore_plan

    if type(review) is not ResidueReview or confirmed is not True:
        raise ResidueRecoveryError("migration_residue_confirmation_required")
    try:
        domain, identity, candidate, root, store, guard, stored = await _inputs(hass, **kwargs)
        if _encode(identity) != review._identity:
            raise ResidueRecoveryError("migration_residue_conflict")
        plan = restore_plan(json.loads(review._manifest))
        if _encode(plan.summary()) != review._summary:
            raise ResidueRecoveryError("migration_residue_conflict")
        fingerprint = plan.summary()["fingerprint"]
        archive = Path(
            hass.config.path(
                "family_assistant_recovery",
                hashlib.sha256(identity["entry_id"].encode()).hexdigest(),
                fingerprint,
            )
        )
        async with domain.setdefault("shadow_registration_lock", asyncio.Lock()):
            async with domain.setdefault("setup_lock", asyncio.Lock()):
                journal = await stored()
                record = {"phase": "prepared", "manifest": plan.private_manifest()}
                previous = journal["records"].get(fingerprint)
                if previous is None:
                    if len(journal["records"]) >= 16 or any(
                        r["phase"] == "prepared" for r in journal["records"].values()
                    ):
                        raise ResidueRecoveryError("migration_residue_conflict")
                    # An archive directory with no matching journal is foreign.
                    if await _io(archive.exists):
                        raise ResidueRecoveryError("migration_residue_conflict")
                    journal["records"][fingerprint] = record
                    await guard()
                    await _settled_save(store, journal)
                elif previous["manifest"] != record["manifest"]:
                    raise ResidueRecoveryError("migration_residue_conflict")
                await guard()
                if _journal(await store.async_load(), identity) != journal:
                    raise ResidueRecoveryError("migration_residue_conflict")
                await guard()
                # _io drains the bounded owned filesystem operation under cancellation.
                result = await _io(apply_residue, root, archive, plan, candidate.private_blobs())
                await guard()
                journal["records"][fingerprint]["phase"] = "preserved"
                await _settled_save(store, journal)
                await guard()
                if _journal(await store.async_load(), identity) != journal:
                    raise ResidueRecoveryError("migration_residue_conflict")
                await guard()
                return result
    except ResidueRecoveryError:
        raise
    except DomainError:
        raise ResidueRecoveryError("migration_residue_forbidden") from None
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError):
        raise ResidueRecoveryError("migration_residue_retry_required") from None
