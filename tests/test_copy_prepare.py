"""Private preparation flow guards; real upload/Core acceptance is a separate test."""

import asyncio
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from ha_legacy_archive_smoke import synthetic_source
from test_copy_flow import Flow
from test_copy_flow import module as wizard_module  # noqa: F401 - shared pytest fixture

from custom_components.family_assistant.migration.review import read_store_pair


@pytest.fixture
def module(wizard_module, monkeypatch):  # noqa: F811 - pytest resolves the imported fixture
    helpers = sys.modules["homeassistant.helpers"]
    helpers.selector.TextSelector = lambda _config: str
    helpers.selector.TextSelectorConfig = lambda **kw: kw
    monkeypatch.setitem(
        sys.modules, "custom_components.family_assistant.migration.copy_flow", wizard_module
    )
    import custom_components.family_assistant.migration as parent

    monkeypatch.setattr(parent, "copy_flow", wizard_module, raising=False)
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_copy_prepare",
        Path(__file__).parents[1] / "custom_components/family_assistant/migration/copy_prepare.py",
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def draft(module, *, photos=False):
    flow = Flow(module.wizard, phase="prepare_members")
    if photos:
        assistant, court, mapping, _ = synthetic_source(lifecycle=True)
        data = json.loads(assistant)
        data["data"]["ledger"]["tasks"]["T000004"]["report_type"] = "photo"
        source = read_store_pair(json.dumps(data).encode(), court)
        reviewers, blobs = {"T000004": ["old-parent"]}, {"example": b"private synthetic image"}
    else:
        assistant, court, mapping, _ = synthetic_source()
        source, reviewers, blobs = (
            read_store_pair(assistant, court),
            {"T000004": ["old-parent"]},
            {},
        )
    inventory = module.source_inventory(source, additional_members=[])
    flow.slot.update(
        index=0,
        prepare={
            "source": source,
            "inventory": inventory,
            "target": deepcopy(flow.state),
            "mapping": {},
            "reviewers": {},
            "photos": [],
            "attachments": {},
        },
    )
    flow.slot.pop("candidate")
    flow.slot.pop("intent")

    async def execute(function, *args):
        return await asyncio.to_thread(function, *args)

    flow.hass.async_add_executor_job = execute
    return flow, mapping, reviewers, blobs


def message(module, flow, **values):
    module._page_form(flow, flow.slot)
    return {"review_token": flow.slot["prepare_token"], "confirmed": True, **values}


async def member_pages(module, flow, mapping):
    while flow.slot["phase"] == "prepare_members":
        key = module._rows(flow.slot)[flow.slot["index"]]["source_id"]
        binding = mapping[key]
        values = (
            {"archive_only": True}
            if binding.get("archive_only")
            else {"member": binding["member_id"]}
        )
        result = await module.page_step(flow, "prepare_members", message(module, flow, **values))
        assert result["type"] == "form", result
    return result


async def reviewer_pages(module, flow):
    while flow.slot["phase"] == "prepare_reviewers":
        result = await module.page_step(
            flow, "prepare_reviewers", message(module, flow, reviewers=["old-parent"])
        )
        assert result["type"] == "form", result
    return result


@pytest.mark.asyncio
async def test_text_source_preparation_uses_exact_bounded_zip_without_store_write(
    module, monkeypatch
):
    flow, mapping, _, _ = draft(module)
    captured = []

    async def intent(_hass, **kw):
        await kw["authorize"]()
        captured.append(kw["package_fingerprint"])
        return {"entry_id": "a" * 32, "prepared_at": "2026-09-08T10:00:00+00:00"}

    monkeypatch.setattr(module.wizard, "async_select_copy_intent", intent)
    before = deepcopy(flow.state)
    await member_pages(module, flow, mapping)
    result = await module.page_step(
        flow, "prepare_reviewers", message(module, flow, reviewers=["old-parent"])
    )
    assert result["step_id"] == "legacy_copy_matches"
    assert flow.state == before and "prepare" not in flow.slot
    source, selected, reviewers, photos, blobs = flow.slot["bundle"].private_inputs()
    assert selected == mapping and reviewers == {"T000004": ["old-parent"]}
    assert not photos and not blobs and len(captured) == 1
    assert source._assistant == synthetic_source()[0]


@pytest.mark.asyncio
async def test_stale_page_cannot_choose_next_member_or_discard_review(module):
    flow, mapping, _, _ = draft(module)
    first = message(module, flow, member="child")
    assert module._rows(flow.slot)[0]["source_id"] == "old-child"
    await module.page_step(flow, "prepare_members", first)
    before = deepcopy(flow.slot["prepare"]["mapping"])
    result = await module.page_step(
        flow, "prepare_members", {**first, "member": "owner", "discard_review": True}
    )
    assert result["errors"]["base"] == "migration_copy_confirmation_required"
    assert flow.slot["prepare"]["mapping"] == before and flow.slot["index"] == 1
    assert module.wizard._slot(flow) is flow.slot


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values", [{}, {"member": "unknown"}, {"archive_only": True}, {"member": True}]
)
async def test_invalid_mapping_never_advances(module, values):
    flow, _, _, _ = draft(module)
    result = await module.page_step(flow, "prepare_members", message(module, flow, **values))
    assert result["errors"]["base"] == "migration_prepare_selection_invalid"
    assert flow.slot["index"] == 0 and not flow.slot["prepare"]["mapping"]


@pytest.mark.asyncio
async def test_collapsed_target_member_is_rejected(module):
    flow, _, _, _ = draft(module)
    await module.page_step(flow, "prepare_members", message(module, flow, member="child"))
    result = await module.page_step(flow, "prepare_members", message(module, flow, member="child"))
    assert result["errors"] and flow.slot["index"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["revision", "ha_user", "admin", "expired", "runtime"])
async def test_current_authority_and_pins_are_required_on_every_page(module, fault):
    flow, _, _, _ = draft(module)
    request = message(module, flow, member="child")
    if fault == "revision":
        flow.state["members"]["child"]["revision"] += 1
    elif fault == "ha_user":
        flow.state["members"]["owner"]["ha_user_id"] = "other"
    elif fault == "admin":
        flow.user.is_admin = False
    elif fault == "expired":
        flow.slot["expires"] = 0
    else:
        flow.config_entry.runtime_data = object()
    result = await module.page_step(flow, "prepare_members", request)
    assert result["type"] == "abort" and "description_placeholders" not in result
    assert module.wizard._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
async def test_discard_clears_only_own_memory_without_any_write(module):
    flow, _, _, _ = draft(module)
    result = await module.page_step(
        flow, "prepare_members", message(module, flow, discard_review=True)
    )
    assert result["reason"] == "migration_copy_cancelled"
    assert module.wizard._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chosen", [None, [], ["old-child"], ["old-parent", "old-parent"], ["old-parent", False]]
)
async def test_reviewer_set_is_explicit_strict_and_includes_designated_actor(module, chosen):
    flow, mapping, _, _ = draft(module)
    await member_pages(module, flow, mapping)
    result = await module.page_step(
        flow, "prepare_reviewers", message(module, flow, reviewers=chosen)
    )
    assert result["errors"]["base"] == "migration_prepare_selection_invalid"
    assert not flow.slot["prepare"]["reviewers"]


@pytest.mark.asyncio
async def test_changed_review_rights_abort_before_images_or_package(module):
    flow, mapping, _, _ = draft(module)
    await member_pages(module, flow, mapping)
    result = await module.page_step(
        flow, "prepare_reviewers", message(module, flow, reviewers=["old-parent", "old-child"])
    )
    assert result["reason"] == "migration_prepare_policy_changed"
    assert module.wizard._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_read", [False, True])
async def test_revocation_during_photo_read_never_redisplays_private_form(
    module, monkeypatch, failed_read
):
    flow, mapping, _, blobs = draft(module, photos=True)
    await member_pages(module, flow, mapping)
    await reviewer_pages(module, flow)

    async def executor(_hass, _function, *_args):
        flow.user.is_admin = False
        if failed_read:
            raise ValueError("private-canary")
        return next(iter(blobs.values()))

    monkeypatch.setattr(module, "_executor", executor)
    result = await module.page_step(
        flow, "prepare_photos", message(module, flow, photo="synthetic")
    )
    assert result["reason"] == "forbidden" and "description_placeholders" not in result
    assert module.wizard._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
async def test_cancelled_photo_worker_drains_before_releasing_slot(module, monkeypatch):
    flow, mapping, _, _ = draft(module, photos=True)
    await member_pages(module, flow, mapping)
    await reviewer_pages(module, flow)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def worker(_function, *_args):
        entered.set()
        await finish.wait()
        return b"private image"

    flow.hass.async_add_executor_job = worker
    task = asyncio.create_task(
        module.page_step(flow, "prepare_photos", message(module, flow, photo="synthetic"))
    )
    await asyncio.wait_for(entered.wait(), timeout=3)
    task.cancel()
    await asyncio.sleep(0)
    assert flow.slot["busy"] and module.wizard._slot(flow) is flow.slot
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert module.wizard._SLOT not in flow.hass.data["family_assistant"]
