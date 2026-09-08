"""Owner-only native forms prepare a private bundle from explicitly selected files.

Shares the copy wizard's single bounded memory slot, authority pins and final
publication path. Does not export a running source or infer who may review it.
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import ExitStack
from uuid import UUID

import voluptuous as vol
from homeassistant.helpers import selector

from ..domain.validation import DomainError, text
from ..media_storage import _settle
from . import copy_flow as wizard
from .copy_bundle import MAX_PHOTO_BYTES, MAX_PHOTOS_BYTES, parse_copy_bundle
from .copy_inventory import source_inventory
from .copy_package import build_copy_bundle
from .photo_evidence import submission_inventory
from .preflight import MAX_BYTES
from .review import read_store_pair
from .reviewer_policy import build_reviewer_policy_review
from .source_links import inspect_source_links


def _id(value):
    if type(value) is not str or len(value) > 36:
        raise ValueError
    UUID(value)
    return value


def _consume_pair(hass, assistant_id, court_id):
    from homeassistant.components.file_upload import process_uploaded_file

    keys = [_id(assistant_id), _id(court_id)]
    if keys[0] == keys[1]:
        raise ValueError
    with ExitStack() as stack:
        paths = [stack.enter_context(process_uploaded_file(hass, key)) for key in keys]
        values = []
        for path in paths:
            with path.open("rb") as stream:
                values.append(stream.read(MAX_BYTES + 1))
        return read_store_pair(*values)


def _consume_photo(hass, file_id, remaining):
    from homeassistant.components.file_upload import process_uploaded_file

    if remaining <= 0:
        raise ValueError
    with process_uploaded_file(hass, _id(file_id)) as path:
        with path.open("rb") as stream:
            content = stream.read(min(MAX_PHOTO_BYTES, remaining) + 1)
        if not 0 < len(content) <= min(MAX_PHOTO_BYTES, remaining):
            raise ValueError
        return content


async def _executor(hass, function, *args):
    work = asyncio.ensure_future(hass.async_add_executor_job(function, *args))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        try:
            await _settle(work)
        except Exception:  # noqa: BLE001, S110 - never expose private parser errors
            pass
        raise


def _source_form(flow, error=None):
    return flow.async_show_form(
        step_id="legacy_prepare",
        data_schema=vol.Schema(
            {
                vol.Required("copy_name"): str,
                vol.Required("assistant_export"): selector.FileSelector(
                    selector.FileSelectorConfig(accept=".json")
                ),
                vol.Required("court_export"): selector.FileSelector(
                    selector.FileSelectorConfig(accept=".json")
                ),
                vol.Optional("additional_members", default=""): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Required("private_files_reviewed", default=False): bool,
            }
        ),
        errors={"base": error} if error else {},
    )


async def source_step(flow, user_input=None):
    try:
        runtime, state = await wizard._scope(flow)
        if user_input is None:
            return _source_form(flow)
        if user_input.get("private_files_reviewed") is not True:
            return _source_form(flow, "migration_copy_confirmation_required")
        name = text(user_input.get("copy_name"), "copy_name", 80)
        extra = user_input.get("additional_members", "")
        if type(extra) is not str or len(extra) > 65536:
            raise ValueError
        additional = [row.strip() for row in extra.splitlines() if row.strip()]
        slot = wizard._claim_slot(flow, runtime, state, phase="prepare_members")
        try:
            source = await _executor(
                flow.hass,
                _consume_pair,
                flow.hass,
                user_input.get("assistant_export"),
                user_input.get("court_export"),
            )
            await wizard._guard(flow, slot)
            inventory = source_inventory(source, additional_members=additional)
            slot.update(
                prepare={
                    "source": source,
                    "inventory": inventory,
                    "target": wizard._empty_copy(flow, state, name),
                    "mapping": {},
                    "reviewers": {},
                    "photos": [],
                    "attachments": {},
                },
                index=0,
            )
        except BaseException:
            wizard._clear(flow, slot)
            raise
        finally:
            slot["busy"] = False
        return _page_form(flow, slot)
    except DomainError as error:
        return wizard._abort(flow, error.code)
    except (ValueError, TypeError, KeyError, OSError):
        return _source_form(flow, "migration_prepare_source_invalid")


def _rows(slot):
    draft = slot["prepare"]
    return {
        "prepare_members": draft["inventory"]["members"],
        "prepare_reviewers": draft["inventory"]["reviewers"],
        "prepare_photos": draft.get("photo_inventory", []),
    }[slot["phase"]]


def _member_choices(slot):
    draft = slot["prepare"]
    used = {row.get("member_id") for row in draft["mapping"].values()}
    return [
        {"value": key, "label": f"{member['name']} [{key}]"}
        for key, member in sorted(draft["target"]["members"].items())
        if member["active"] and member["role"] != "guest" and key not in used
    ]


def _page_form(flow, slot, error=None):
    draft, phase, index = slot["prepare"], slot["phase"], slot["index"]
    rows = _rows(slot)
    row = rows[index]
    token = hashlib.sha256(wizard._encode([flow.flow_id, phase, index, row])).hexdigest()
    slot["prepare_token"] = token
    schema = {
        vol.Required("review_token", default=token): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[{"value": token, "label": f"{index + 1}/{len(rows)}"}]
            )
        ),
        vol.Required("confirmed", default=False): bool,
        vol.Optional("discard_review", default=False): bool,
    }
    if phase == "prepare_members":
        choices = _member_choices(slot)
        if choices:
            schema[vol.Optional("member")] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=choices)
            )
        if row["archive_allowed"]:
            schema[vol.Optional("archive_only", default=False)] = bool
        association = wizard._markdown(row["source_id"])
    elif phase == "prepare_reviewers":
        options = [
            {"value": key, "label": key}
            for key, binding in sorted(draft["mapping"].items())
            if not binding.get("archive_only")
        ]
        schema[vol.Optional("reviewers")] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=options, multiple=True)
        )
        association = " · ".join(
            wizard._markdown(row[key]) for key in ("task_id", "title", "reviewer")
        )
    else:
        schema[vol.Optional("photo")] = selector.FileSelector(
            selector.FileSelectorConfig(accept="image/jpeg,image/png,image/webp")
        )
        association = " · ".join(
            wizard._markdown(row[key])
            for key in ("task_id", "event_sequence", "submitted_at", "report_reference")
        )
    return flow.async_show_form(
        step_id={
            "prepare_members": "legacy_prepare_member",
            "prepare_reviewers": "legacy_prepare_reviewer",
            "prepare_photos": "legacy_prepare_photo",
        }[phase],
        data_schema=vol.Schema(schema),
        description_placeholders={"association": association},
        errors={"base": error} if error else {},
    )


def _select_member(slot, user_input):
    draft, row = slot["prepare"], _rows(slot)[slot["index"]]
    if user_input.get("archive_only") is True:
        if not row["archive_allowed"] or user_input.get("member"):
            raise ValueError
        binding = {"archive_only": True}
    else:
        key = user_input.get("member")
        if type(key) is not str or key not in {item["value"] for item in _member_choices(slot)}:
            raise ValueError
        binding = {"member_id": key, "member_revision": draft["target"]["members"][key]["revision"]}
    draft["mapping"][row["source_id"]] = binding


def _select_reviewers(slot, user_input):
    draft, row = slot["prepare"], _rows(slot)[slot["index"]]
    chosen = user_input.get("reviewers")
    if (
        type(chosen) is not list
        or not 1 <= len(chosen) <= 512
        or any(type(key) is not str for key in chosen)
    ):
        raise ValueError
    if len(set(chosen)) != len(chosen) or row["reviewer"] not in chosen:
        raise ValueError
    if any(
        key not in draft["mapping"] or draft["mapping"][key].get("archive_only") for key in chosen
    ):
        raise ValueError
    draft["reviewers"][row["task_id"]] = sorted(chosen)


def _pack(draft):
    raw = build_copy_bundle(
        assistant_store=draft["source"]._assistant,
        court_store=draft["source"]._court,
        member_mapping=draft["mapping"],
        reviewer_sets=draft["reviewers"],
        photos=draft["photos"],
        attachments=draft["attachments"],
    )
    return parse_copy_bundle(raw), hashlib.sha256(raw).hexdigest()


async def _advance(flow, slot):
    draft = slot["prepare"]
    slot["index"] += 1
    if slot["index"] < len(_rows(slot)):
        return _page_form(flow, slot)
    if slot["phase"] == "prepare_members":
        draft["review"] = draft["source"].review(
            draft["mapping"], draft["target"]["members"], mapping_revision=1
        )
        if inspect_source_links(draft["review"], members=draft["target"]["members"])["issues"]:
            raise DomainError("migration_copy_source_unsettled")
        slot.update(phase="prepare_reviewers", index=0)
        if _rows(slot):
            return _page_form(flow, slot)
    if slot["phase"] == "prepare_reviewers":
        policy = build_reviewer_policy_review(
            draft["review"],
            {
                "schema": 1,
                "revision": 1,
                "source_review_fingerprint": draft["review"].summary()["fingerprint"],
                "reviewers": draft["reviewers"],
            },
            members=draft["target"]["members"],
        )
        if policy.summary()["changed_tasks_count"]:
            raise DomainError("migration_prepare_policy_changed")
        draft["photo_inventory"] = submission_inventory(
            draft["review"], members=draft["target"]["members"]
        )
        if (
            sum(len(draft["inventory"][key]) for key in ("members", "reviewers"))
            + len(draft["photo_inventory"])
            > 1000
        ):
            raise ValueError
        slot.update(phase="prepare_photos", index=0)
        if _rows(slot):
            return _page_form(flow, slot)
    bundle, digest = await _executor(flow.hass, _pack, draft)
    await wizard._accept_bundle(flow, slot, bundle, digest, draft["target"])
    slot.pop("prepare")
    return wizard._match_form(flow, slot)


async def page_step(flow, phase, user_input=None):
    try:
        slot = wizard._slot(flow)
        async with slot["lock"]:
            await wizard._guard(flow, slot)
            if slot["phase"] != phase:
                raise DomainError("migration_copy_review_changed")
            if user_input is None:
                return _page_form(flow, slot)
            if user_input.get("review_token") != slot.get("prepare_token"):
                return _page_form(flow, slot, "migration_copy_confirmation_required")
            if user_input.get("discard_review") is True:
                return wizard._abort(flow, "migration_copy_cancelled")
            if user_input.get("confirmed") is not True:
                return _page_form(flow, slot, "migration_copy_confirmation_required")
            slot["busy"] = True
            try:
                try:
                    if phase == "prepare_members":
                        _select_member(slot, user_input)
                    elif phase == "prepare_reviewers":
                        _select_reviewers(slot, user_input)
                    else:
                        draft, row = slot["prepare"], _rows(slot)[slot["index"]]
                        content = await _executor(
                            flow.hass,
                            _consume_photo,
                            flow.hass,
                            user_input.get("photo"),
                            MAX_PHOTOS_BYTES - sum(map(len, draft["attachments"].values())),
                        )
                        await wizard._guard(flow, slot)
                        key = f"event_{row['event_sequence']}"
                        draft["attachments"][key] = content
                        draft["photos"].append(
                            {
                                **{
                                    field: row[field]
                                    for field in ("task_id", "event_sequence", "report_sha256")
                                },
                                "attachment_key": key,
                            }
                        )
                except DomainError:
                    raise
                except (ValueError, TypeError, KeyError, OSError):
                    await wizard._guard(flow, slot)
                    return _page_form(flow, slot, "migration_prepare_selection_invalid")
                return await _advance(flow, slot)
            finally:
                slot["busy"] = False
    except DomainError as error:
        return wizard._abort(flow, error.code)
    except (ValueError, TypeError, KeyError, OSError):
        return wizard._abort(flow, "migration_copy_conversion_required")
    except asyncio.CancelledError:
        wizard._abort(flow, "migration_copy_cancelled")
        raise
