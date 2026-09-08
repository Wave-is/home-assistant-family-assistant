"""Owner-initiated discovery and fresh reviewed registration of staged copies."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant.helpers import selector

from ..const import DOMAIN
from ..domain.validation import DomainError
from .copy_flow import (
    _SLOT,
    _abort,
    _claim_slot,
    _guard,
    _markdown,
    _review_form,
    _scope,
    _slot,
    complete_step,
)
from .copy_index import async_list_copies, async_load_copy
from .shadow_registration import async_register_shadow

_ERRORS = {
    "migration_copy_partial_bundle_required",
    "migration_copy_incompatible_bundle_required",
    "migration_copy_index_invalid",
    "migration_copy_index_full",
}
_REVIEW_LABELS = {
    "en": "Current reviewed list",
    "ru": "Текущий проверенный список",
    "uk": "Поточний перевірений список",
}


def _local_time(value, pins):
    local = datetime.fromisoformat(value).astimezone(ZoneInfo(pins["timezone"]))
    pattern = "%Y-%m-%d %H:%M" if pins["language"] == "en" else "%d.%m.%Y %H:%M"
    return f"{local.strftime(pattern)} ({pins['timezone']})"


def _error(error):
    code = str(error)
    return code if code in _ERRORS else "migration_copy_retry_required"


def _inputs(flow, slot):
    return {
        "prototype_entry_id": flow.config_entry.entry_id,
        "user_id": flow.context["user_id"],
        "prototype_pins": slot["pins"],
        "authorize": lambda: _guard(flow, slot),
    }


def _select_form(flow, slot, error=None):
    pins = json.loads(slot["pins"])
    options = [
        {
            "value": row["entry_id"],
            "label": f"{row['copy_name']} · {_local_time(row['prepared_at'], pins)}",
        }
        for row in (attempt.summary() for attempt in slot["attempts"].values())
    ]
    return flow.async_show_form(
        step_id="legacy_resume",
        data_schema=vol.Schema(
            {
                vol.Required(
                    "review_token", default=slot["selection_token"]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": slot["selection_token"],
                                "label": _REVIEW_LABELS[pins["language"]],
                            }
                        ]
                    )
                ),
                vol.Optional("attempt"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                ),
                vol.Optional("discard_review", default=False): bool,
            }
        ),
        errors={"base": error} if error else {},
    )


def _confirm_form(flow, slot, error=None):
    result = _review_form(flow, slot, error)
    result["step_id"] = "legacy_resume_review"
    result["description_placeholders"].update(
        copy_name=_markdown(slot["target"]["settings"]["name"]),
        prepared_at=_local_time(slot["intent"]["prepared_at"], json.loads(slot["pins"])),
    )
    return result


async def select_step(flow, user_input=None):
    try:
        runtime, state = await _scope(flow)
        existing = flow.hass.data[DOMAIN].get(_SLOT)
        if not existing or existing.get("flow_id") != flow.flow_id:
            slot = _claim_slot(flow, runtime, state, phase="resume_select")
            try:
                rows = await async_list_copies(flow.hass, **_inputs(flow, slot))
                await _guard(flow, slot)
                slot["attempts"] = {row.summary()["entry_id"]: row for row in rows}
                slot["selection_token"] = uuid4().hex
            finally:
                slot["busy"] = False
            if not slot["attempts"]:
                return _abort(flow, "migration_copy_no_pending")
        else:
            slot = _slot(flow)
        async with slot["lock"]:
            await _guard(flow, slot)
            if slot["phase"] != "resume_select":
                raise DomainError("migration_copy_review_changed")
            if user_input is None:
                return _select_form(flow, slot)
            if user_input.get("review_token") != slot["selection_token"]:
                return _select_form(flow, slot, "migration_copy_confirmation_required")
            if user_input.get("discard_review") is True:
                return _abort(flow, "migration_copy_cancelled")
            attempt = slot["attempts"].get(user_input.get("attempt"))
            if attempt is None:
                return _select_form(flow, slot, "migration_copy_confirmation_required")
            slot["busy"] = True
            try:
                loaded = await async_load_copy(flow.hass, attempt=attempt, **_inputs(flow, slot))
                await _guard(flow, slot)
                slot.update(loaded, attempt=attempt, phase="resume_review")
            except (ValueError, TypeError, KeyError, OSError) as error:
                await _guard(flow, slot)
                return _select_form(flow, slot, _error(error))
            finally:
                slot["busy"] = False
        return _confirm_form(flow, slot)
    except DomainError as error:
        return _abort(flow, error.code)
    except (ValueError, TypeError, KeyError, OSError) as error:
        return _abort(flow, _error(error))
    except asyncio.CancelledError:
        _abort(flow, "migration_copy_cancelled")
        raise


async def confirm_step(flow, user_input=None):
    try:
        slot = _slot(flow)
        async with slot["lock"]:
            await _guard(flow, slot)
            if slot["phase"] == "complete":
                return await complete_step(flow)
            if slot["phase"] != "resume_review":
                raise DomainError("migration_copy_review_changed")
            if user_input is None:
                return _confirm_form(flow, slot)
            fingerprint = slot["candidate"].summary()["fingerprint"]
            if user_input.get("review_token") != fingerprint:
                return _confirm_form(flow, slot, "migration_copy_confirmation_required")
            if user_input.get("discard_review") is True:
                return _abort(flow, "migration_copy_cancelled")
            if user_input.get("confirmed") is not True:
                return _confirm_form(flow, slot, "migration_copy_confirmation_required")
            slot["busy"] = True
            try:
                loaded = await async_load_copy(
                    flow.hass, attempt=slot["attempt"], **_inputs(flow, slot)
                )
                await _guard(flow, slot)
                if (
                    loaded["candidate"]._state != slot["candidate"]._state
                    or loaded["candidate"]._summary != slot["candidate"]._summary
                    or loaded["intent"] != slot["intent"]
                    or loaded["target"] != slot["target"]
                ):
                    raise DomainError("migration_copy_review_changed")
                slot["result"] = await async_register_shadow(
                    flow.hass,
                    entry_id=loaded["intent"]["entry_id"],
                    user_id=flow.context["user_id"],
                    candidate=loaded["candidate"],
                    target=loaded["target"],
                    expected_fingerprint=fingerprint,
                    authorize=lambda: _guard(flow, slot),
                )
                await _guard(flow, slot)
                slot["phase"] = "complete"
            except (ValueError, TypeError, KeyError, OSError) as error:
                await _guard(flow, slot)
                return _confirm_form(flow, slot, _error(error))
            finally:
                slot["busy"] = False
        return await complete_step(flow)
    except DomainError as error:
        return _abort(flow, error.code)
    except asyncio.CancelledError:
        _abort(flow, "migration_copy_cancelled")
        raise
