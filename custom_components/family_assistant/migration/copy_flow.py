"""Owner-private Options wizard: review a bundle and create a separate sealed copy."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import re
import time
from copy import deepcopy
from uuid import UUID

import voluptuous as vol
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from ..domain.engine import new_state
from ..domain.validation import DomainError, text, timestamp
from ..media_storage import _settle
from .copy_bundle import MAX_BUNDLE_BYTES, parse_copy_bundle
from .copy_intent import async_commit_copy_intent, async_select_copy_intent
from .photo_evidence import async_prepare_photo_evidence
from .shadow import ShadowError, build_shadow_candidate
from .shadow_registration import async_register_shadow

_SLOT = "migration_copy_review"
_TTL = 15 * 60
_PAGE = 10
_LABELS = {
    "en": ("Member", "Reviewers", "Photo", "Archive only"),
    "ru": ("Участник", "Проверяющие", "Фото", "Только архив"),
    "uk": ("Учасник", "Перевіряльники", "Фото", "Лише архів"),
}
_ROLES = {
    "en": {
        "owner": "owner",
        "parent": "parent",
        "adult": "adult",
        "child": "child",
        "guest": "guest",
    },
    "ru": {
        "owner": "владелец",
        "parent": "родитель",
        "adult": "взрослый",
        "child": "ребёнок",
        "guest": "гость",
    },
    "uk": {
        "owner": "власник",
        "parent": "один із батьків",
        "adult": "дорослий",
        "child": "дитина",
        "guest": "гість",
    },
}


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _markdown(value):
    escaped = html.escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", escaped)


async def _scope(flow):
    user_id = flow.context.get("user_id")
    user = await flow.hass.auth.async_get_user(user_id)
    if not user or not user.is_active or not user.is_admin or user.id != user_id:
        raise DomainError("forbidden")
    runtime, actor = flow._authorized_runtime()
    if (
        flow.hass.config_entries.async_get_entry(flow.config_entry.entry_id)
        is not flow.config_entry
        or flow.config_entry.runtime_data is not runtime
        or actor != "owner"
    ):
        raise DomainError("migration_copy_primary_owner_required")
    state = runtime.engine.snapshot()
    if state["members"]["owner"].get("ha_user_id") != user_id:
        raise DomainError("forbidden")
    return runtime, state


def _pins(state):
    return _encode(
        {
            "members": state["members"],
            "language": state["settings"]["language"],
            "timezone": state["settings"]["timezone"],
        }
    )


async def _guard(flow, slot):
    runtime, state = await _scope(flow)
    if (
        flow.hass.data[DOMAIN].get(_SLOT) is not slot
        or slot["flow_id"] != flow.flow_id
        or slot["user_id"] != flow.context.get("user_id")
        or slot["runtime"] is not runtime
        or slot["pins"] != _pins(state)
        or time.monotonic() > slot["expires"]
    ):
        raise DomainError("migration_copy_review_changed")


def _slot(flow):
    slot = flow.hass.data.get(DOMAIN, {}).get(_SLOT)
    if not isinstance(slot, dict) or slot.get("flow_id") != flow.flow_id:
        raise DomainError("migration_copy_review_changed")
    return slot


def _clear(flow, slot):
    if flow.hass.data.get(DOMAIN, {}).get(_SLOT) is slot:
        flow.hass.data[DOMAIN].pop(_SLOT)


def _abort(flow, reason):
    slot = flow.hass.data.get(DOMAIN, {}).get(_SLOT)
    if slot and slot.get("flow_id") == flow.flow_id and not slot.get("busy"):
        _clear(flow, slot)
    return flow.async_abort(reason=reason)


def _consume_upload(hass, file_id):
    """Core owns the temporary upload path and cleanup; never accept a path/URL."""
    from homeassistant.components.file_upload import process_uploaded_file

    if type(file_id) is not str or len(file_id) > 36:
        raise ValueError("migration_copy_bundle_invalid")
    UUID(file_id)
    with process_uploaded_file(hass, file_id) as path:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BUNDLE_BYTES + 1)
        bundle = parse_copy_bundle(raw)
        return bundle, hashlib.sha256(raw).hexdigest()


async def _uploaded_bundle(hass, file_id):
    # Cancelling an executor Future does not stop its parser thread. Keep the
    # single private-memory slot occupied until our owned thread has settled.
    work = asyncio.ensure_future(hass.async_add_executor_job(_consume_upload, hass, file_id))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        try:
            await _settle(work)
        except Exception:  # noqa: BLE001, S110 - preserve cancellation, never print private data
            pass
        raise


def _claim_slot(flow, runtime, state, *, phase):
    existing = flow.hass.data[DOMAIN].get(_SLOT)
    if existing and (existing["busy"] or existing["expires"] >= time.monotonic()):
        raise DomainError("migration_copy_busy")
    slot = {
        "flow_id": flow.flow_id,
        "user_id": flow.context["user_id"],
        "runtime": runtime,
        "pins": _pins(state),
        "expires": time.monotonic() + _TTL,
        "busy": True,
        "lock": asyncio.Lock(),
        "phase": phase,
    }
    flow.hass.data[DOMAIN][_SLOT] = slot
    return slot


def _empty_copy(flow, state, name):
    target = new_state(
        flow.context["user_id"],
        name,
        state["settings"]["language"],
        [],
        timezone=state["settings"]["timezone"],
    )
    target["members"] = deepcopy(state["members"])
    return target


async def _accept_bundle(flow, slot, bundle, digest, target):
    """Common prepared/ZIP entry point; no persistent write before final review."""
    await _guard(flow, slot)
    source, mapping, reviewers, _, _ = bundle.private_inputs()
    review = source.review(mapping, target["members"], mapping_revision=1)
    slot.update(
        bundle=bundle,
        package_fingerprint=digest,
        target=target,
        source_review=review,
        rows=_match_rows(bundle, target["members"], target["settings"]["language"]),
        page=0,
        phase="matches",
        reviewer_policy={
            "schema": 1,
            "revision": 1,
            "source_review_fingerprint": review.summary()["fingerprint"],
            "reviewers": reviewers,
        },
    )
    slot["intent"] = await async_select_copy_intent(
        flow.hass,
        package_fingerprint=digest,
        target=target,
        prepared_at=dt_util.utcnow(),
        authorize=lambda: _guard(flow, slot),
    )


def _upload_form(flow, error=None):
    return flow.async_show_form(
        step_id="legacy_copy",
        data_schema=vol.Schema(
            {
                vol.Required("copy_name"): str,
                vol.Required("bundle"): selector.FileSelector(
                    selector.FileSelectorConfig(accept=".zip")
                ),
                vol.Required("private_files_reviewed", default=False): bool,
            }
        ),
        errors={"base": error} if error else {},
    )


def _match_rows(bundle, members, language):
    _, mapping, reviewers, photos, _ = bundle.private_inputs()
    member_label, reviewer_label, photo_label, archive_label = _LABELS.get(language, _LABELS["en"])
    rows = []
    for old_id, binding in sorted(mapping.items()):
        target = archive_label
        if not binding.get("archive_only"):
            member = members[binding["member_id"]]
            role = _ROLES.get(language, _ROLES["en"])[member["role"]]
            target = f"{member['name']} [{member['id']} · {role} · #{member['revision']}]"
        rows.append(f"{member_label}: {_markdown(old_id)} → {_markdown(target)}")
    for task, actors in sorted(reviewers.items()):
        rows.append(f"{reviewer_label}: {_markdown(task)} → {_markdown(', '.join(actors))}")
    for row in photos:
        rows.append(
            f"{photo_label}: {_markdown(row['task_id'])} · {row['event_sequence']} · "
            f"{row['report_sha256']} → {_markdown(row['attachment_key'])}"
        )
    if not rows or len(rows) > 1000:
        raise ValueError("migration_copy_bundle_invalid")
    return rows


async def upload_step(flow, user_input=None):
    try:
        runtime, state = await _scope(flow)
        if user_input is None:
            return _upload_form(flow)
        if user_input.get("private_files_reviewed") is not True:
            return _upload_form(flow, "migration_copy_confirmation_required")
        name = text(user_input.get("copy_name"), "copy_name", 80)
        # Exactly one process-local slot bounds private bundle memory. Expired
        # idle slots are replaced; their persistent retry intent is not removed.
        slot = _claim_slot(flow, runtime, state, phase="upload")
        try:
            bundle, digest = await _uploaded_bundle(flow.hass, user_input.get("bundle"))
            await _accept_bundle(flow, slot, bundle, digest, _empty_copy(flow, state, name))
        except BaseException:
            _clear(flow, slot)
            raise
        finally:
            slot["busy"] = False
        return await matches_step(flow)
    except DomainError as error:
        return _abort(flow, error.code)
    except (ValueError, TypeError, KeyError, OSError):
        return _upload_form(flow, "migration_copy_bundle_invalid")


def _match_form(flow, slot, error=None):
    page, rows = slot["page"], slot["rows"]
    text_rows = "\n\n".join(rows[page * _PAGE : (page + 1) * _PAGE])
    token = hashlib.sha256(_encode([flow.flow_id, page, text_rows])).hexdigest()
    slot["page_token"] = token
    return flow.async_show_form(
        step_id="legacy_copy_matches",
        data_schema=vol.Schema(
            {
                vol.Required("review_token", default=token): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": token, "label": f"{page + 1}/{math.ceil(len(rows) / _PAGE)}"}
                        ]
                    )
                ),
                vol.Required("confirmed", default=False): bool,
                vol.Optional("discard_review", default=False): bool,
            }
        ),
        description_placeholders={"associations": text_rows},
        errors={"base": error} if error else {},
    )


async def matches_step(flow, user_input=None):
    try:
        slot = _slot(flow)
        async with slot["lock"]:
            await _guard(flow, slot)
            if slot["phase"] != "matches":
                raise DomainError("migration_copy_review_changed")
            if user_input is None:
                return _match_form(flow, slot)
            if user_input.get("discard_review") is True and user_input.get(
                "review_token"
            ) == slot.get("page_token"):
                return _abort(flow, "migration_copy_cancelled")
            if user_input.get("confirmed") is not True or user_input.get(
                "review_token"
            ) != slot.get("page_token"):
                return _match_form(flow, slot, "migration_copy_confirmation_required")
            if (slot["page"] + 1) * _PAGE < len(slot["rows"]):
                slot["page"] += 1
                return _match_form(flow, slot)
            slot["busy"] = True
            try:
                _, _, _, photos, blobs = slot["bundle"].private_inputs()
                prepared = timestamp(slot["intent"]["prepared_at"], "prepared_at")
                evidence = None
                if photos:
                    evidence = await async_prepare_photo_evidence(
                        slot["source_review"],
                        members=slot["target"]["members"],
                        source_review_fingerprint=slot["source_review"].summary()["fingerprint"],
                        confirmed_by="owner",
                        prepared_at=prepared,
                        confirmations=photos,
                        attachments=blobs,
                    )
                await _guard(flow, slot)
                slot["candidate"] = build_shadow_candidate(
                    slot["source_review"],
                    slot["target"],
                    reviewer_policy=slot["reviewer_policy"],
                    prepared_at=prepared,
                    photo_evidence=evidence,
                )
                slot["phase"] = "review"
                # The candidate now owns original source plus verified canonical
                # images. Release the original ZIP image payloads from this slot.
                slot.pop("bundle")
                slot.pop("source_review")
            finally:
                slot["busy"] = False
        return await review_step(flow)
    except DomainError as error:
        return _abort(flow, error.code)
    except ShadowError as error:
        if str(error) == "shadow_source_effects_unsettled":
            return _abort(flow, "migration_copy_source_unsettled")
        return _abort(flow, "migration_copy_conversion_required")
    except (ValueError, TypeError, KeyError, OSError):
        return _abort(flow, "migration_copy_conversion_required")
    except asyncio.CancelledError:
        _abort(flow, "migration_copy_cancelled")
        raise


def _review_form(flow, slot, error=None):
    summary = slot["candidate"].summary()
    fingerprint = summary["fingerprint"]
    return flow.async_show_form(
        step_id="legacy_copy_review",
        data_schema=vol.Schema(
            {
                vol.Required("review_token", default=fingerprint): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[{"value": fingerprint, "label": fingerprint}]
                    )
                ),
                vol.Required("confirmed", default=False): bool,
                vol.Optional("discard_review", default=False): bool,
            }
        ),
        description_placeholders={
            **{key: str(value) for key, value in summary["counts"].items()},
            "photos": str(len(slot["candidate"].private_blobs())),
            "fingerprint": fingerprint,
        },
        errors={"base": error} if error else {},
    )


async def review_step(flow, user_input=None):
    try:
        slot = _slot(flow)
        async with slot["lock"]:
            await _guard(flow, slot)
            if slot["phase"] == "complete":
                return await complete_step(flow)
            if slot["phase"] != "review":
                raise DomainError("migration_copy_review_changed")
            if user_input is None:
                return _review_form(flow, slot)
            fingerprint = slot["candidate"].summary()["fingerprint"]
            if (
                user_input.get("discard_review") is True
                and user_input.get("review_token") == fingerprint
            ):
                return _abort(flow, "migration_copy_cancelled")
            if (
                user_input.get("confirmed") is not True
                or user_input.get("review_token") != fingerprint
            ):
                return _review_form(flow, slot, "migration_copy_confirmation_required")
            slot["busy"] = True
            try:
                await async_commit_copy_intent(
                    flow.hass,
                    record=slot["intent"],
                    package_fingerprint=slot["package_fingerprint"],
                    target=slot["target"],
                    authorize=lambda: _guard(flow, slot),
                )
                slot["result"] = await async_register_shadow(
                    flow.hass,
                    entry_id=slot["intent"]["entry_id"],
                    user_id=flow.context["user_id"],
                    candidate=slot["candidate"],
                    target=slot["target"],
                    expected_fingerprint=fingerprint,
                    authorize=lambda: _guard(flow, slot),
                )
                slot["phase"] = "complete"
            except (ValueError, OSError, TypeError, KeyError):
                await _guard(flow, slot)
                return _review_form(flow, slot, "migration_copy_retry_required")
            finally:
                slot["busy"] = False
        return await complete_step(flow)
    except DomainError as error:
        return _abort(flow, error.code)
    except asyncio.CancelledError:
        _abort(flow, "migration_copy_cancelled")
        raise


async def complete_step(flow, user_input=None):
    try:
        slot = _slot(flow)
        await _guard(flow, slot)
        if slot["phase"] != "complete":
            raise DomainError("migration_copy_review_changed")
        if user_input is not None:
            _clear(flow, slot)
            return flow.async_abort(reason="migration_copy_finished")
        return flow.async_show_form(
            step_id="legacy_copy_complete",
            data_schema=vol.Schema({}),
            description_placeholders={"entry_id": slot["result"]["entry_id"]},
            errors={} if slot["result"]["loaded"] else {"base": "migration_copy_not_loaded"},
        )
    except DomainError as error:
        return _abort(flow, error.code)
