"""Immutable same-package retry coordinates; no source data or active effects."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import timedelta

from homeassistant.helpers.storage import Store

from ..const import DOMAIN
from ..domain.validation import timestamp
from .shadow import _empty_target
from .shadow_install import _settled_save


class CopyIntentError(ValueError):
    """Fixed code only; an unknown outcome never resets the preparation time."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _identity(package_fingerprint, target):
    _empty_target(target)
    if type(package_fingerprint) is not str or not re.fullmatch(
        r"[0-9a-f]{64}", package_fingerprint
    ):
        raise CopyIntentError("migration_copy_intent_invalid")
    target_fingerprint = hashlib.sha256(_encode(target)).hexdigest()
    entry_id = hashlib.sha256(
        b"family_assistant_legacy_copy/v1\0"
        + package_fingerprint.encode()
        + target_fingerprint.encode()
    ).hexdigest()[:32]
    return {
        "version": 1,
        "entry_id": entry_id,
        "package_fingerprint": package_fingerprint,
        "target_fingerprint": target_fingerprint,
    }


def _check(record, identity):
    if (
        type(record) is not dict
        or set(record) != {*identity, "prepared_at"}
        or type(record.get("version")) is not int
        or any(record[key] != value for key, value in identity.items())
    ):
        raise CopyIntentError("migration_copy_intent_invalid")
    prepared = timestamp(record["prepared_at"], "prepared_at")
    if prepared.utcoffset() != timedelta(0) or prepared.isoformat() != record["prepared_at"]:
        raise CopyIntentError("migration_copy_intent_invalid")
    return json.loads(_encode(record))


async def async_select_copy_intent(hass, *, package_fingerprint, target, prepared_at, authorize):
    """Read prior coordinates, or propose new ones without any Store write."""
    try:
        await authorize()
        identity = _identity(package_fingerprint, target)
        store = Store(hass, 1, f"{DOMAIN}.copy_intent.{identity['entry_id']}")
        previous = await store.async_load()
        await authorize()
        if _identity(package_fingerprint, target) != identity:
            raise CopyIntentError("migration_copy_intent_invalid")
        record = (
            previous
            if previous is not None
            else identity | {"prepared_at": prepared_at.isoformat()}
        )
        return _check(record, identity)
    except CopyIntentError:
        raise
    except (TypeError, ValueError, KeyError, OSError, AttributeError, RecursionError):
        raise CopyIntentError("migration_copy_intent_invalid") from None


async def async_commit_copy_intent(hass, *, record, package_fingerprint, target, authorize):
    """Only after final owner confirmation: preserve exact same-ID/time retries."""
    try:
        await authorize()
        identity = _identity(package_fingerprint, target)
        selected = _check(record, identity)
        domain = hass.data.setdefault(DOMAIN, {})
        async with domain.setdefault("setup_lock", asyncio.Lock()):
            await authorize()
            if domain.get("backup") or _identity(package_fingerprint, target) != identity:
                raise CopyIntentError("migration_copy_intent_invalid")
            store = Store(hass, 1, f"{DOMAIN}.copy_intent.{identity['entry_id']}")
            previous = await store.async_load()
            await authorize()
            if _identity(package_fingerprint, target) != identity or _encode(record) != _encode(
                selected
            ):
                raise CopyIntentError("migration_copy_intent_invalid")
            if previous is not None and _encode(_check(previous, identity)) != _encode(selected):
                raise CopyIntentError("migration_copy_intent_invalid")
            if previous is None:
                await _settled_save(store, selected)
            current = await store.async_load()
            await authorize()
            if _identity(package_fingerprint, target) != identity or _encode(record) != _encode(
                selected
            ):
                raise CopyIntentError("migration_copy_intent_invalid")
            if _encode(_check(current, identity)) != _encode(selected):
                raise CopyIntentError("migration_copy_intent_invalid")
            return selected
    except CopyIntentError:
        raise
    except (TypeError, ValueError, KeyError, OSError, AttributeError, RecursionError):
        raise CopyIntentError("migration_copy_intent_invalid") from None
