"""Options discovery/resume scope; actual Store/decoder contracts tested separately."""

import asyncio
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_copy_flow import Flow
from test_copy_flow import module as copy_module


@pytest.fixture
def port(monkeypatch):
    copy = copy_module.__wrapped__(monkeypatch)
    monkeypatch.setitem(sys.modules, "custom_components.family_assistant.migration.copy_flow", copy)
    flow = Flow(copy, phase="resume_select")
    flow.slot["intent"]["prepared_at"] = "2026-09-08T00:00:00+00:00"
    original = {
        "candidate": flow.candidate,
        "target": deepcopy(flow.state),
        "intent": deepcopy(flow.slot["intent"]),
        "package_fingerprint": "b" * 64,
    }
    summary = {
        "entry_id": "a" * 32,
        "copy_name": "Synthetic saved copy",
        "prepared_at": original["intent"]["prepared_at"],
        "fingerprint": flow.candidate.summary()["fingerprint"],
        "compatible": True,
    }
    attempt = SimpleNamespace(summary=lambda: dict(summary))
    effects = []
    options = SimpleNamespace(empty=False, load_error=None, revoke=False)

    async def list_copies(_hass, **kwargs):
        await kwargs["authorize"]()
        effects.append("list")
        return [] if options.empty else [attempt]

    async def load_copy(_hass, **kwargs):
        await kwargs["authorize"]()
        assert kwargs["attempt"] is attempt
        assert kwargs["prototype_entry_id"] == flow.config_entry.entry_id
        assert kwargs["prototype_pins"] == copy._pins(flow.state)
        effects.append("load")
        if options.revoke:
            flow.user.is_active = False
        if options.load_error:
            raise ValueError(options.load_error)
        return {key: deepcopy(value) for key, value in original.items()}

    async def register(_hass, **kwargs):
        await kwargs["authorize"]()
        assert kwargs["entry_id"] == "a" * 32
        assert kwargs["expected_fingerprint"] == summary["fingerprint"]
        effects.append("register")
        return {"entry_id": "a" * 32, "loaded": True}

    index = sys.modules["custom_components.family_assistant.migration.copy_index"]
    index.async_list_copies, index.async_load_copy = list_copies, load_copy
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_copy_resume",
        Path(__file__).parents[1] / "custom_components/family_assistant/migration/copy_resume.py",
    )
    resume = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resume)
    monkeypatch.setattr(resume, "async_register_shadow", register)
    flow.hass.data["family_assistant"].pop(copy._SLOT)
    return SimpleNamespace(flow=flow, copy=copy, resume=resume, options=options, effects=effects)


async def choose(port):
    result = await port.resume.select_step(port.flow)
    assert result["step_id"] == "legacy_resume"
    slot = port.flow.hass.data["family_assistant"][port.copy._SLOT]
    result = await port.resume.select_step(
        port.flow, {"review_token": slot["selection_token"], "attempt": "a" * 32}
    )
    return result, slot


@pytest.mark.asyncio
async def test_discovery_and_selection_never_register_before_fresh_final_confirmation(port):
    result, slot = await choose(port)
    assert result["step_id"] == "legacy_resume_review" and port.effects == ["list", "load"]
    token = slot["candidate"].summary()["fingerprint"]
    for confirm in (False, None, 1, "true"):
        denied = await port.resume.confirm_step(
            port.flow, {"review_token": token, "confirmed": confirm}
        )
        assert denied["errors"] and port.effects == ["list", "load"]
    request = {"review_token": token, "confirmed": True}
    done = await port.resume.confirm_step(port.flow, request)
    assert done["step_id"] == "legacy_copy_complete"
    assert port.effects == ["list", "load", "load", "register"]
    assert (await port.resume.confirm_step(port.flow, request))["step_id"] == "legacy_copy_complete"
    assert port.effects.count("register") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["selection", "review"])
async def test_cancel_releases_only_memory_not_index_or_copy(port, phase):
    if phase == "review":
        _, slot = await choose(port)
        method, token = port.resume.confirm_step, slot["candidate"].summary()["fingerprint"]
    else:
        await port.resume.select_step(port.flow)
        slot = port.flow.hass.data["family_assistant"][port.copy._SLOT]
        method, token = port.resume.select_step, slot["selection_token"]
    before = list(port.effects)
    result = await method(port.flow, {"review_token": token, "discard_review": True})
    assert result["reason"] == "migration_copy_cancelled"
    assert port.copy._SLOT not in port.flow.hass.data["family_assistant"] and port.effects == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        "migration_copy_partial_bundle_required",
        "migration_copy_incompatible_bundle_required",
        "PRIVATE_ERROR",
    ],
)
async def test_partial_or_changed_copy_does_not_register_or_leak_raw_error(port, error):
    port.options.load_error = error
    result, slot = await choose(port)
    assert result["step_id"] == "legacy_resume" and result["errors"]
    assert "PRIVATE" not in str(result) and "register" not in port.effects
    assert slot["phase"] == "resume_select" and not slot["busy"]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["selection", "review"])
async def test_revoked_identity_after_async_verification_aborts_without_old_preview(port, phase):
    if phase == "review":
        _, slot = await choose(port)
        port.options.revoke = True
        result = await port.resume.confirm_step(
            port.flow,
            {
                "review_token": slot["candidate"].summary()["fingerprint"],
                "confirmed": True,
            },
        )
    else:
        port.options.revoke = True
        result, _ = await choose(port)
    assert result["type"] == "abort" and "register" not in port.effects
    assert port.copy._SLOT not in port.flow.hass.data["family_assistant"]


@pytest.mark.asyncio
async def test_no_indexed_attempts_closes_only_review_slot(port):
    port.options.empty = True
    result = await port.resume.select_step(port.flow)
    assert result["reason"] == "migration_copy_no_pending" and port.effects == ["list"]
    assert port.copy._SLOT not in port.flow.hass.data["family_assistant"]


@pytest.mark.asyncio
async def test_stale_selection_token_cannot_choose_copy(port):
    await port.resume.select_step(port.flow)
    result = await port.resume.select_step(port.flow, {"review_token": "old", "attempt": "a" * 32})
    assert result["errors"] and port.effects == ["list"]


@pytest.mark.parametrize(
    "language, expected",
    [
        ("en", "2026-09-08 03:00"),
        ("ru", "08.09.2026 03:00"),
        ("uk", "08.09.2026 03:00"),
    ],
)
def test_preparation_time_shown_in_household_zone_with_explicit_zone(port, language, expected):
    assert (
        port.resume._local_time(
            "2026-09-08T00:00:00+00:00",
            {
                "language": language,
                "timezone": "Europe/Kyiv",
            },
        )
        == expected + " (Europe/Kyiv)"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["selection", "review"])
async def test_cancelled_verification_releases_own_review_without_registration(
    port, monkeypatch, phase
):
    if phase == "review":
        _, slot = await choose(port)
        method = port.resume.confirm_step
        request = {"review_token": slot["candidate"].summary()["fingerprint"], "confirmed": True}
    else:
        await port.resume.select_step(port.flow)
        slot = port.flow.hass.data["family_assistant"][port.copy._SLOT]
        method = port.resume.select_step
        request = {"review_token": slot["selection_token"], "attempt": "a" * 32}
    entered = asyncio.Event()

    async def pending(*_args, **_kwargs):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(port.resume, "async_load_copy", pending)
    task = asyncio.create_task(method(port.flow, request))
    await asyncio.wait_for(entered.wait(), 3)
    assert slot["busy"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert port.copy._SLOT not in port.flow.hass.data["family_assistant"]
    assert "register" not in port.effects
