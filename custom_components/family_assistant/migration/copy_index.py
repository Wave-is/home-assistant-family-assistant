"""Owner-scoped index and reloader for verified candidate copies."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.storage import Store

from ..const import DOMAIN, SCHEMA_VERSION
from ..domain.media import MAX_FILE_BYTES, MAX_VERIFIED_BYTES
from ..domain.validation import DomainError
from ..media_storage import _io, _read
from .copy_intent import CopyIntentError, _check, _identity
from .shadow import ShadowCandidate, ShadowError, _empty_target, async_reverify_shadow
from .shadow_entry import KEY, entry_marker, validate_entry_state
from .shadow_install import _settled_save, _verify_blobs

_MAX_RECORDS = 16
_MAX_ATTACHMENTS = 512
_MAX_RECORD_BYTES = 1024 * 1024
_MAX_INDEX_BYTES = 16 * 1024 * 1024
_MAX_DEPTH = 32
_MAX_ITEMS = 50_000
_MAX_STRING_LEN = 100_000
_SAFE_MIN_INT = -9007199254740991
_SAFE_MAX_INT = 9007199254740991
_BLOB_KEY = re.compile(r"[0-9a-f]{64}")
_ENTRY_ID = re.compile(r"[0-9a-f]{32}")
_DIGEST = re.compile(r"[0-9a-f]{64}")

RECORD_KEYS = frozenset(
    {
        "entry_id",
        "prototype_entry_id",
        "owner_user_id",
        "prototype_pins_hash",
        "package_fingerprint",
        "copy_intent",
        "target",
        "candidate_summary",
        "copy_name",
        "prepared_at",
        "fingerprint",
    }
)


class CopyIndexError(DomainError):
    """Fixed codes only; no private data, paths, or unvetted exceptions."""


def _encode(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _pins(state: dict) -> bytes:
    return _encode(
        {
            "members": state["members"],
            "language": state["settings"]["language"],
            "timezone": state["settings"]["timezone"],
        }
    )


def _pairs_reject_dups(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    res: dict[str, Any] = {}
    for k, v in pairs:
        if type(k) is not str or k in res:
            raise CopyIndexError("migration_copy_index_invalid")
        res[k] = v
    return res


def _assert_bounded_finite_json(root_value: Any) -> None:
    stack = [(root_value, 0)]
    items_count = byte_count = 0
    while stack:
        curr, depth = stack.pop()
        items_count += 1
        if items_count > _MAX_ITEMS or depth > _MAX_DEPTH:
            raise CopyIndexError("migration_copy_index_invalid")

        if curr is None:
            continue
        t = type(curr)
        if t is bool:
            continue
        if t is int:
            if not (_SAFE_MIN_INT <= curr <= _SAFE_MAX_INT):
                raise CopyIndexError("migration_copy_index_invalid")
            continue
        if t is float:
            if not math.isfinite(curr):
                raise CopyIndexError("migration_copy_index_invalid")
            continue
        if t is str:
            if len(curr) > _MAX_STRING_LEN:
                raise CopyIndexError("migration_copy_index_invalid")
            try:
                byte_count += len(curr.encode("utf-8")) * 6 + 2
            except UnicodeError:
                raise CopyIndexError("migration_copy_index_invalid") from None
            if byte_count > _MAX_INDEX_BYTES:
                raise CopyIndexError("migration_copy_index_invalid")
            continue
        if t is list:
            if len(curr) > _MAX_ITEMS - items_count - len(stack):
                raise CopyIndexError("migration_copy_index_invalid")
            for item in curr:
                stack.append((item, depth + 1))
            continue
        if t is dict:
            if len(curr) * 2 > _MAX_ITEMS - items_count - len(stack):
                raise CopyIndexError("migration_copy_index_invalid")
            for k, v in curr.items():
                if type(k) is not str or len(k) > _MAX_STRING_LEN:
                    raise CopyIndexError("migration_copy_index_invalid")
                stack.append((k, depth + 1))
                stack.append((v, depth + 1))
            continue
        raise CopyIndexError("migration_copy_index_invalid")


def _assert_finite_json(value: Any) -> None:
    _assert_bounded_finite_json(value)


def _validate_record(record: Any, expected_entry_id: str | None = None) -> None:
    if type(record) is not dict:
        raise CopyIndexError("migration_copy_index_invalid")
    _assert_bounded_finite_json(record)
    keyset = frozenset(record)
    if keyset != RECORD_KEYS:
        raise CopyIndexError("migration_copy_index_invalid")

    entry_id = record["entry_id"]
    if type(entry_id) is not str or not _ENTRY_ID.fullmatch(entry_id):
        raise CopyIndexError("migration_copy_index_invalid")
    if expected_entry_id is not None and entry_id != expected_entry_id:
        raise CopyIndexError("migration_copy_index_invalid")

    prototype_entry_id = record["prototype_entry_id"]
    if type(prototype_entry_id) is not str or not 0 < len(prototype_entry_id) <= 128:
        raise CopyIndexError("migration_copy_index_invalid")

    owner_user_id = record["owner_user_id"]
    if type(owner_user_id) is not str or not 0 < len(owner_user_id) <= 128:
        raise CopyIndexError("migration_copy_index_invalid")

    pins_hash = record["prototype_pins_hash"]
    if type(pins_hash) is not str or not _DIGEST.fullmatch(pins_hash):
        raise CopyIndexError("migration_copy_index_invalid")

    package_fingerprint = record["package_fingerprint"]
    if type(package_fingerprint) is not str or not _DIGEST.fullmatch(package_fingerprint):
        raise CopyIndexError("migration_copy_index_invalid")

    target = record["target"]
    try:
        _empty_target(target)
    except ShadowError:
        raise CopyIndexError("migration_copy_index_invalid") from None

    target_owner = target.get("members", {}).get("owner", {})
    if type(target_owner) is not dict or target_owner.get("ha_user_id") != owner_user_id:
        raise CopyIndexError("migration_copy_index_invalid")
    try:
        target_pins = _pins(target)
    except Exception:
        raise CopyIndexError("migration_copy_index_invalid") from None
    if hashlib.sha256(target_pins).hexdigest() != pins_hash:
        raise CopyIndexError("migration_copy_index_invalid")

    try:
        identity = _identity(package_fingerprint, target)
        if identity["entry_id"] != entry_id:
            raise CopyIndexError("migration_copy_index_invalid")
        _check(record["copy_intent"], identity)
    except (CopyIntentError, ShadowError, ValueError, KeyError, TypeError):
        raise CopyIndexError("migration_copy_index_invalid") from None

    summary = record["candidate_summary"]
    if type(summary) is not dict:
        raise CopyIndexError("migration_copy_index_invalid")
    summary_keys = set(summary)
    if summary_keys not in (
        {
            "mode",
            "fingerprint",
            "conversion_fingerprint",
            "counts",
            "coherence_verified",
            "activation_available",
        },
        {
            "mode",
            "fingerprint",
            "conversion_fingerprint",
            "counts",
            "coherence_verified",
            "activation_available",
            "photo_evidence",
        },
    ):
        raise CopyIndexError("migration_copy_index_invalid")

    if summary.get("mode") != "read_only_shadow":
        raise CopyIndexError("migration_copy_index_invalid")
    summary_fp = summary.get("fingerprint")
    if type(summary_fp) is not str or not _DIGEST.fullmatch(summary_fp):
        raise CopyIndexError("migration_copy_index_invalid")
    conversion_fp = summary.get("conversion_fingerprint")
    if type(conversion_fp) is not str or not _DIGEST.fullmatch(conversion_fp):
        raise CopyIndexError("migration_copy_index_invalid")
    if summary.get("coherence_verified") is not False:
        raise CopyIndexError("migration_copy_index_invalid")
    if summary.get("activation_available") is not False:
        raise CopyIndexError("migration_copy_index_invalid")

    counts = summary.get("counts")
    if type(counts) is not dict or set(counts) != {
        "members",
        "tasks",
        "shopping",
        "court",
        "alarms",
    }:
        raise CopyIndexError("migration_copy_index_invalid")
    for cnt_val in counts.values():
        if (
            type(cnt_val) is not int
            or isinstance(cnt_val, bool)
            or cnt_val < 0
            or cnt_val > 100_000
        ):
            raise CopyIndexError("migration_copy_index_invalid")

    if "photo_evidence" in summary:
        photo = summary["photo_evidence"]
        if (
            type(photo) is not dict
            or set(photo)
            != {
                "mode",
                "fingerprint",
                "images_count",
                "bytes_count",
                "image_identity_automatically_verified",
                "activation_available",
            }
            or photo["mode"] != "owner_matched_photos"
            or type(photo["fingerprint"]) is not str
            or not _DIGEST.fullmatch(photo["fingerprint"])
            or type(photo["images_count"]) is not int
            or not 0 <= photo["images_count"] <= _MAX_ATTACHMENTS
            or type(photo["bytes_count"]) is not int
            or not 0 <= photo["bytes_count"] <= MAX_VERIFIED_BYTES
            or (photo["images_count"] == 0) != (photo["bytes_count"] == 0)
            or photo["image_identity_automatically_verified"] is not False
            or photo["activation_available"] is not False
        ):
            raise CopyIndexError("migration_copy_index_invalid")

    if "copy_name" in record:
        if record["copy_name"] != target["settings"]["name"]:
            raise CopyIndexError("migration_copy_index_invalid")
    if "prepared_at" in record:
        if record["prepared_at"] != record["copy_intent"]["prepared_at"]:
            raise CopyIndexError("migration_copy_index_invalid")
    if "fingerprint" in record:
        if record["fingerprint"] != summary_fp:
            raise CopyIndexError("migration_copy_index_invalid")


def _validate_index(data: Any) -> dict:
    if data is None:
        return {"version": 1, "records": {}}
    if type(data) is not dict:
        raise CopyIndexError("migration_copy_index_invalid")
    if set(data) != {"version", "records"}:
        raise CopyIndexError("migration_copy_index_invalid")
    if (
        type(data["version"]) is not int
        or isinstance(data["version"], bool)
        or data["version"] != 1
    ):
        raise CopyIndexError("migration_copy_index_invalid")
    if type(data["records"]) is not dict or len(data["records"]) > _MAX_RECORDS:
        raise CopyIndexError("migration_copy_index_invalid")
    _assert_bounded_finite_json(data)
    for entry_id, record in data["records"].items():
        if type(entry_id) is not str or not _ENTRY_ID.fullmatch(entry_id):
            raise CopyIndexError("migration_copy_index_invalid")
        _validate_record(record, expected_entry_id=entry_id)
    return data


@dataclass(frozen=True, repr=False)
class CopyAttempt:
    _record: bytes = field(repr=False)
    _compatible: bool = field(repr=False)

    def __post_init__(self) -> None:
        if type(self._record) is not bytes:
            raise CopyIndexError("migration_copy_index_invalid")
        if type(self._compatible) is not bool:
            raise CopyIndexError("migration_copy_index_invalid")
        if len(self._record) > _MAX_RECORD_BYTES or not self._record:
            raise CopyIndexError("migration_copy_index_invalid")
        try:
            parsed = json.loads(self._record.decode("utf-8"), object_pairs_hook=_pairs_reject_dups)
            _assert_bounded_finite_json(parsed)
            if _encode(parsed) != self._record:
                raise CopyIndexError("migration_copy_index_invalid")
            _validate_record(parsed)
        except Exception:
            raise CopyIndexError("migration_copy_index_invalid") from None

    def __repr__(self) -> str:
        return "CopyAttempt(private=True)"

    def summary(self) -> dict[str, Any]:
        record = json.loads(self._record)
        return {
            "entry_id": record["entry_id"],
            "copy_name": record.get("copy_name", record["target"]["settings"]["name"]),
            "prepared_at": record.get("prepared_at", record["copy_intent"]["prepared_at"]),
            "fingerprint": record.get("fingerprint", record["candidate_summary"]["fingerprint"]),
            "compatible": self._compatible,
        }

    def private_record(self) -> dict[str, Any]:
        return json.loads(self._record)


class _BoundAuthority:
    """Pins prototype ConfigEntry and runtime object identity across awaits."""

    def __init__(
        self,
        hass: Any,
        *,
        prototype_entry_id: str,
        user_id: str,
        prototype_pins: bytes,
        authorize: Callable[[], Awaitable[None]],
        is_load: bool = False,
    ) -> None:
        self._hass = hass
        self._prototype_entry_id = prototype_entry_id
        self._user_id = user_id
        self._prototype_pins = prototype_pins
        self._authorize = authorize
        self._is_load = is_load
        self._pinned_entry: Any = None
        self._pinned_runtime: Any = None

    async def initialize_and_check(self) -> tuple[Any, dict]:
        if type(self._user_id) is not str or not 0 < len(self._user_id) <= 128:
            raise CopyIndexError("forbidden")
        if (
            type(self._prototype_entry_id) is not str
            or not 0 < len(self._prototype_entry_id) <= 128
        ):
            raise CopyIndexError("migration_copy_primary_owner_required")
        if type(self._prototype_pins) is not bytes:
            raise CopyIndexError("migration_copy_index_invalid")
        if not callable(self._authorize):
            raise CopyIndexError("migration_copy_index_invalid")

        entry = self._hass.config_entries.async_get_entry(self._prototype_entry_id)
        domain_entries = self._hass.data.setdefault(DOMAIN, {}).setdefault("entries", {})
        runtime = domain_entries.get(self._prototype_entry_id)
        if (
            entry is None
            or getattr(entry, "domain", None) != DOMAIN
            or runtime is None
            or getattr(entry, "runtime_data", None) is not runtime
        ):
            raise CopyIndexError("migration_copy_primary_owner_required")

        # Reject sealed prototype
        if KEY in getattr(entry, "data", {}) or getattr(runtime.engine, "shadow_mode", False):
            raise CopyIndexError("migration_copy_primary_owner_required")

        self._pinned_entry = entry
        self._pinned_runtime = runtime

        return await self.check()

    async def check(self) -> tuple[Any, dict]:
        if self._pinned_entry is None or self._pinned_runtime is None:
            return await self.initialize_and_check()

        # 1. Call supplied authorize before final checks
        try:
            await self._authorize()
        except DomainError as error:
            code = (
                error.code
                if error.code
                in {
                    "forbidden",
                    "backup_in_progress",
                    "migration_shadow_read_only",
                    "migration_copy_review_changed",
                    "migration_copy_primary_owner_required",
                }
                else "forbidden"
            )
            raise CopyIndexError(code) from None

        # 2. Recheck user authority
        user = await self._hass.auth.async_get_user(self._user_id)
        if (
            not user
            or not getattr(user, "is_active", False)
            or not getattr(user, "is_admin", False)
            or user.id != self._user_id
        ):
            raise CopyIndexError("forbidden")

        # 3. Synchronous checks: NO awaits after this point!
        current_entry = self._hass.config_entries.async_get_entry(self._prototype_entry_id)
        domain_entries = self._hass.data.get(DOMAIN, {}).get("entries", {})
        current_runtime = domain_entries.get(self._prototype_entry_id)
        if (
            current_entry is not self._pinned_entry
            or current_runtime is not self._pinned_runtime
            or getattr(self._pinned_entry, "runtime_data", None) is not self._pinned_runtime
        ):
            raise CopyIndexError("migration_copy_primary_owner_required")

        # Sealed prototype rejection
        if KEY in getattr(self._pinned_entry, "data", {}) or getattr(
            self._pinned_runtime.engine, "shadow_mode", False
        ):
            raise CopyIndexError("migration_copy_primary_owner_required")

        domain = self._hass.data.get(DOMAIN, {})
        if domain.get("backup"):
            raise CopyIndexError("migration_copy_busy")

        state = self._pinned_runtime.engine.snapshot()
        if KEY in state or "migration_archive" in state:
            raise CopyIndexError("migration_copy_primary_owner_required")

        owner = state.get("members", {}).get("owner", {})
        if (
            owner.get("role") != "owner"
            or owner.get("active") is not True
            or owner.get("ha_user_id") != self._user_id
        ):
            raise CopyIndexError("migration_copy_primary_owner_required")

        current_pins = _pins(state)
        if current_pins != self._prototype_pins:
            if self._is_load:
                raise CopyIndexError("migration_copy_incompatible_bundle_required")
            raise CopyIndexError("migration_copy_review_changed")

        return self._pinned_runtime, state


async def _guard(
    hass: Any,
    *,
    prototype_entry_id: str,
    user_id: str,
    prototype_pins: bytes,
    authorize: Callable[[], Awaitable[None]],
    is_load: bool = False,
) -> tuple[Any, dict]:
    authority = _BoundAuthority(
        hass,
        prototype_entry_id=prototype_entry_id,
        user_id=user_id,
        prototype_pins=prototype_pins,
        authorize=authorize,
        is_load=is_load,
    )
    return await authority.initialize_and_check()


def _load_blobs(root: Path, media_records: dict) -> dict[str, bytes]:
    if type(media_records) is not dict:
        raise CopyIndexError("migration_copy_incompatible_bundle_required")
    if len(media_records) > _MAX_ATTACHMENTS:
        raise CopyIndexError("migration_copy_incompatible_bundle_required")

    unique_blobs: dict[str, tuple[int, str]] = {}
    total_bytes = 0
    for record in media_records.values():
        if (
            type(record) is not dict
            or "blob_key" not in record
            or "size_bytes" not in record
            or "sha256" not in record
        ):
            raise CopyIndexError("migration_copy_incompatible_bundle_required")
        key = record["blob_key"]
        size = record["size_bytes"]
        sha = record["sha256"]
        if (
            type(key) is not str
            or not _BLOB_KEY.fullmatch(key)
            or type(size) is not int
            or isinstance(size, bool)
            or not 0 < size <= MAX_FILE_BYTES
            or type(sha) is not str
            or not _DIGEST.fullmatch(sha)
        ):
            raise CopyIndexError("migration_copy_incompatible_bundle_required")

        if key in unique_blobs:
            if unique_blobs[key] != (size, sha):
                raise CopyIndexError("migration_copy_incompatible_bundle_required")
        else:
            unique_blobs[key] = (size, sha)
            total_bytes += size

    if total_bytes > MAX_VERIFIED_BYTES:
        raise CopyIndexError("migration_copy_incompatible_bundle_required")

    if root.is_symlink() or root.resolve() != root.absolute():
        raise CopyIndexError("migration_copy_partial_bundle_required")

    expected_keys = set(unique_blobs)
    if not root.exists():
        if expected_keys:
            raise CopyIndexError("migration_copy_partial_bundle_required")
        return {}

    for path in root.iterdir():
        if path.name not in expected_keys:
            raise CopyIndexError("migration_copy_partial_bundle_required")

    blobs: dict[str, bytes] = {}
    for key, (size, sha) in unique_blobs.items():
        try:
            content = _read(root, key)
        except Exception:
            raise CopyIndexError("migration_copy_partial_bundle_required") from None
        if len(content) != size or hashlib.sha256(content).hexdigest() != sha:
            raise CopyIndexError("migration_copy_partial_bundle_required")
        blobs[key] = content

    try:
        _verify_blobs(root, blobs)
    except Exception:
        raise CopyIndexError("migration_copy_partial_bundle_required") from None

    return blobs


async def async_record_copy(
    hass: Any,
    *,
    prototype_entry_id: str,
    user_id: str,
    prototype_pins: bytes,
    intent: dict,
    package_fingerprint: str,
    target: dict,
    candidate: ShadowCandidate,
    authorize: Callable[[], Awaitable[None]],
) -> CopyAttempt:
    try:
        authority = _BoundAuthority(
            hass,
            prototype_entry_id=prototype_entry_id,
            user_id=user_id,
            prototype_pins=prototype_pins,
            authorize=authorize,
            is_load=False,
        )
        await authority.initialize_and_check()

        try:
            _empty_target(target)
        except ShadowError:
            raise CopyIndexError("migration_copy_index_invalid") from None

        target_owner = target.get("members", {}).get("owner", {})
        if type(target_owner) is not dict or target_owner.get("ha_user_id") != user_id:
            raise CopyIndexError("migration_copy_index_invalid")
        target_pins_hash = hashlib.sha256(_pins(target)).hexdigest()
        if target_pins_hash != hashlib.sha256(prototype_pins).hexdigest():
            raise CopyIndexError("migration_copy_incompatible_bundle_required")

        try:
            identity = _identity(package_fingerprint, target)
            validated_intent = _check(intent, identity)
        except (CopyIntentError, ShadowError, ValueError, KeyError, TypeError):
            raise CopyIndexError("migration_copy_intent_invalid") from None

        entry_id = identity["entry_id"]

        if type(candidate) is not ShadowCandidate:
            raise CopyIndexError("migration_copy_index_invalid")

        try:
            verified = await async_reverify_shadow(candidate, target)
        except ShadowError:
            raise CopyIndexError("migration_copy_incompatible_bundle_required") from None
        except Exception:
            raise CopyIndexError("migration_copy_incompatible_bundle_required") from None

        if verified._state != candidate._state or verified._summary != candidate._summary:
            raise CopyIndexError("migration_copy_incompatible_bundle_required")

        await authority.check()

        copy_intent_store = Store(hass, 1, f"{DOMAIN}.copy_intent.{entry_id}")
        committed = await copy_intent_store.async_load()
        if committed is None:
            raise CopyIndexError("migration_copy_intent_invalid")
        try:
            checked_committed = _check(committed, identity)
        except Exception:
            raise CopyIndexError("migration_copy_intent_invalid") from None
        if _encode(checked_committed) != _encode(validated_intent):
            raise CopyIndexError("migration_copy_intent_invalid")

        selected_target = json.loads(_encode(target))
        candidate_summary = verified.summary()
        record = {
            "entry_id": entry_id,
            "prototype_entry_id": prototype_entry_id,
            "owner_user_id": user_id,
            "prototype_pins_hash": hashlib.sha256(prototype_pins).hexdigest(),
            "package_fingerprint": package_fingerprint,
            "copy_intent": validated_intent,
            "target": selected_target,
            "candidate_summary": candidate_summary,
            "copy_name": selected_target["settings"]["name"],
            "prepared_at": validated_intent["prepared_at"],
            "fingerprint": candidate_summary["fingerprint"],
        }
        _validate_record(record, expected_entry_id=entry_id)

        domain = hass.data.setdefault(DOMAIN, {})
        reg_lock = domain.setdefault("shadow_registration_lock", asyncio.Lock())
        setup_lock = domain.setdefault("setup_lock", asyncio.Lock())

        async with reg_lock:
            async with setup_lock:
                await authority.check()

                committed_lock = await copy_intent_store.async_load()
                if committed_lock is None:
                    raise CopyIndexError("migration_copy_intent_invalid")
                try:
                    checked_lock = _check(committed_lock, identity)
                except Exception:
                    raise CopyIndexError("migration_copy_intent_invalid") from None
                if _encode(checked_lock) != _encode(validated_intent):
                    raise CopyIndexError("migration_copy_intent_invalid")

                index_store = Store(hass, 1, f"{DOMAIN}.copy_index")
                raw_index = await index_store.async_load()
                data = _validate_index(raw_index)
                records = data["records"]

                if entry_id in records:
                    existing_record = records[entry_id]
                    if _encode(existing_record) == _encode(record):
                        await authority.check()
                        return CopyAttempt(_encode(existing_record), _compatible=True)
                    raise CopyIndexError("migration_copy_index_invalid")

                if len(records) >= _MAX_RECORDS:
                    raise CopyIndexError("migration_copy_index_full")

                # Fresh guard immediately before _settled_save:
                # Any revocation during read yields ZERO index writes!
                await authority.check()

                records[entry_id] = record
                await _settled_save(index_store, data)
                readback = await index_store.async_load()
                if _encode(readback) != _encode(data):
                    raise CopyIndexError("migration_copy_index_invalid")

                await authority.check()
                return CopyAttempt(_encode(record), _compatible=True)
    except CopyIndexError:
        raise
    except (TypeError, ValueError, KeyError, OSError, AttributeError, RecursionError):
        raise CopyIndexError("migration_copy_index_invalid") from None


async def async_list_copies(
    hass: Any,
    *,
    prototype_entry_id: str,
    user_id: str,
    prototype_pins: bytes,
    authorize: Callable[[], Awaitable[None]],
) -> list[CopyAttempt]:
    try:
        authority = _BoundAuthority(
            hass,
            prototype_entry_id=prototype_entry_id,
            user_id=user_id,
            prototype_pins=prototype_pins,
            authorize=authorize,
            is_load=False,
        )

        domain = hass.data.setdefault(DOMAIN, {})
        reg_lock = domain.setdefault("shadow_registration_lock", asyncio.Lock())
        setup_lock = domain.setdefault("setup_lock", asyncio.Lock())

        async with reg_lock:
            async with setup_lock:
                await authority.initialize_and_check()

                index_store = Store(hass, 1, f"{DOMAIN}.copy_index")
                raw_index = await index_store.async_load()
                await authority.check()
                data = _validate_index(raw_index)
                current_hash = hashlib.sha256(prototype_pins).hexdigest()
                results: list[CopyAttempt] = []
                for record in data["records"].values():
                    if (
                        record["prototype_entry_id"] == prototype_entry_id
                        and record["owner_user_id"] == user_id
                    ):
                        compatible = record["prototype_pins_hash"] == current_hash
                        results.append(CopyAttempt(_encode(record), _compatible=compatible))
                await authority.check()
                return results
    except CopyIndexError:
        raise
    except (TypeError, ValueError, KeyError, OSError, AttributeError, RecursionError):
        raise CopyIndexError("migration_copy_index_invalid") from None


async def async_load_copy(
    hass: Any,
    *,
    attempt: CopyAttempt,
    prototype_entry_id: str,
    user_id: str,
    prototype_pins: bytes,
    authorize: Callable[[], Awaitable[None]],
) -> dict[str, Any]:
    try:
        if not isinstance(attempt, CopyAttempt):
            raise CopyIndexError("migration_copy_index_invalid")

        attempt_record = attempt.private_record()
        if type(attempt_record) is not dict:
            raise CopyIndexError("migration_copy_index_invalid")
        entry_id = attempt_record.get("entry_id")
        if type(entry_id) is not str or not _ENTRY_ID.fullmatch(entry_id):
            raise CopyIndexError("migration_copy_index_invalid")

        authority = _BoundAuthority(
            hass,
            prototype_entry_id=prototype_entry_id,
            user_id=user_id,
            prototype_pins=prototype_pins,
            authorize=authorize,
            is_load=True,
        )

        domain = hass.data.setdefault(DOMAIN, {})
        reg_lock = domain.setdefault("shadow_registration_lock", asyncio.Lock())
        setup_lock = domain.setdefault("setup_lock", asyncio.Lock())

        async with reg_lock:
            async with setup_lock:
                await authority.initialize_and_check()

                current_pins_hash = hashlib.sha256(prototype_pins).hexdigest()
                if attempt_record.get("prototype_pins_hash") != current_pins_hash:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                index_store = Store(hass, 1, f"{DOMAIN}.copy_index")
                raw_index = await index_store.async_load()
                await authority.check()
                data = _validate_index(raw_index)
                if entry_id not in data["records"]:
                    raise CopyIndexError("migration_copy_index_invalid")
                indexed_record = data["records"][entry_id]
                if _encode(indexed_record) != _encode(attempt_record):
                    raise CopyIndexError("migration_copy_index_invalid")
                if (
                    indexed_record["prototype_entry_id"] != prototype_entry_id
                    or indexed_record["owner_user_id"] != user_id
                ):
                    raise CopyIndexError("migration_copy_index_invalid")

                target_owner = indexed_record["target"].get("members", {}).get("owner", {})
                if type(target_owner) is not dict or target_owner.get("ha_user_id") != user_id:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")
                if hashlib.sha256(_pins(indexed_record["target"])).hexdigest() != current_pins_hash:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                copy_intent_store = Store(hass, 1, f"{DOMAIN}.copy_intent.{entry_id}")
                saved_copy_intent = await copy_intent_store.async_load()
                await authority.check()
                if saved_copy_intent is None:
                    raise CopyIndexError("migration_copy_partial_bundle_required")
                try:
                    identity = _identity(
                        indexed_record["package_fingerprint"], indexed_record["target"]
                    )
                    validated_saved_intent = _check(saved_copy_intent, identity)
                except Exception:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required") from None
                if _encode(validated_saved_intent) != _encode(indexed_record["copy_intent"]):
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                shadow_intent_store = Store(hass, 1, f"{DOMAIN}.shadow_intent.{entry_id}")
                saved_shadow_intent = await shadow_intent_store.async_load()
                await authority.check()
                if saved_shadow_intent is None:
                    raise CopyIndexError("migration_copy_partial_bundle_required")
                expected_shadow_intent = {
                    "version": 1,
                    "mode": "read_only_shadow_staging",
                    "fingerprint": indexed_record["candidate_summary"]["fingerprint"],
                    "target_fingerprint": indexed_record["copy_intent"]["target_fingerprint"],
                }
                if _encode(saved_shadow_intent) != _encode(expected_shadow_intent):
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                candidate_store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry_id}")
                saved_state = await candidate_store.async_load()
                await authority.check()
                if saved_state is None:
                    raise CopyIndexError("migration_copy_partial_bundle_required")

                encoded_saved_state = _encode(saved_state)
                state_fingerprint = hashlib.sha256(encoded_saved_state).hexdigest()
                indexed_fingerprint = indexed_record["candidate_summary"]["fingerprint"]
                if state_fingerprint != indexed_fingerprint:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                existing_entry = hass.config_entries.async_get_entry(entry_id)
                if existing_entry is not None:
                    if (
                        getattr(existing_entry, "domain", None) != DOMAIN
                        or getattr(existing_entry, "source", None) != "user"
                        or getattr(existing_entry, "version", None) != 1
                        or getattr(existing_entry, "minor_version", None) != 1
                        or getattr(existing_entry, "unique_id", None)
                        != f"migration-shadow-{entry_id}"
                        or getattr(existing_entry, "title", None)
                        != indexed_record["target"]["settings"]["name"]
                        or getattr(existing_entry, "options", None)
                    ):
                        raise CopyIndexError("migration_copy_incompatible_bundle_required")
                    try:
                        validate_entry_state(existing_entry.data, saved_state)
                    except DomainError:
                        raise CopyIndexError(
                            "migration_copy_incompatible_bundle_required"
                        ) from None
                    seal = entry_marker(saved_state, indexed_fingerprint)
                    owner = indexed_record["target"]["members"]["owner"]
                    settings = indexed_record["target"]["settings"]
                    expected_entry_data = {
                        "owner_user_id": owner["ha_user_id"],
                        "owner_name": owner["name"],
                        "name": settings["name"],
                        "language": settings["language"],
                        "timezone": settings["timezone"],
                        "modules": [],
                        KEY: seal,
                    }
                    if _encode(dict(existing_entry.data)) != _encode(expected_entry_data):
                        raise CopyIndexError("migration_copy_incompatible_bundle_required")
                    registered_runtime = domain.get("entries", {}).get(entry_id)
                    loaded = (
                        getattr(existing_entry, "state", None) == ConfigEntryState.LOADED
                        and registered_runtime is not None
                    )
                    if loaded and (
                        not getattr(registered_runtime.engine, "shadow_mode", False)
                        or _encode(registered_runtime.engine.snapshot()) != encoded_saved_state
                    ):
                        raise CopyIndexError("migration_copy_incompatible_bundle_required")

                root = Path(
                    hass.config.path(
                        "family_assistant_data",
                        hashlib.sha256(entry_id.encode()).hexdigest(),
                    )
                )
                media_records = saved_state.get("media", {})
                try:
                    blobs = await _io(_load_blobs, root, media_records)
                except CopyIndexError:
                    raise
                except Exception:
                    raise CopyIndexError("migration_copy_partial_bundle_required") from None

                await authority.check()

                candidate = ShadowCandidate(
                    _state=encoded_saved_state,
                    _summary=_encode(indexed_record["candidate_summary"]),
                    _blobs=tuple(blobs.items()),
                )

                try:
                    verified = await async_reverify_shadow(candidate, indexed_record["target"])
                except ShadowError:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required") from None
                except Exception:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required") from None

                archive = verified.private_state().get("migration_archive", {})
                target_fingerprint = hashlib.sha256(_encode(indexed_record["target"])).hexdigest()
                if (
                    archive.get("target_fingerprint") != target_fingerprint
                    or indexed_record["copy_intent"]["target_fingerprint"] != target_fingerprint
                    or indexed_record["copy_intent"]["package_fingerprint"]
                    != indexed_record["package_fingerprint"]
                ):
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                # Recheck candidate store, original index, and both intents after decoder
                current_candidate_state = await candidate_store.async_load()
                if _encode(current_candidate_state) != verified._state:
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                current_index = await index_store.async_load()
                if current_index is None or _encode(
                    current_index.get("records", {}).get(entry_id)
                ) != _encode(indexed_record):
                    raise CopyIndexError("migration_copy_index_invalid")

                current_copy_intent = await copy_intent_store.async_load()
                if _encode(current_copy_intent) != _encode(indexed_record["copy_intent"]):
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                current_shadow_intent = await shadow_intent_store.async_load()
                if _encode(current_shadow_intent) != _encode(expected_shadow_intent):
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                if _encode(indexed_record["target"]) != _encode(attempt_record["target"]):
                    raise CopyIndexError("migration_copy_incompatible_bundle_required")

                # Final authority recheck immediately before return (no awaits after)
                await authority.check()

                return {
                    "candidate": verified,
                    "target": deepcopy(indexed_record["target"]),
                    "intent": deepcopy(indexed_record["copy_intent"]),
                    "package_fingerprint": indexed_record["package_fingerprint"],
                }
    except CopyIndexError:
        raise
    except (TypeError, ValueError, KeyError, OSError, AttributeError, RecursionError):
        raise CopyIndexError("migration_copy_incompatible_bundle_required") from None
