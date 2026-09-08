"""Wizard authority/page/cancellation guards; Core transport has a separate native test."""

import asyncio
import importlib.util
import sys
import time
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_shadow_reverify import candidate

from custom_components.family_assistant.domain.validation import DomainError


@pytest.fixture
def module(monkeypatch):
    helpers = ModuleType("homeassistant.helpers")
    helpers.selector = SimpleNamespace(
        FileSelector=lambda _config: str,
        SelectSelector=lambda _config: str,
        FileSelectorConfig=lambda **kw: kw,
        SelectSelectorConfig=lambda **kw: kw,
    )
    util = ModuleType("homeassistant.util")
    util.dt = SimpleNamespace(utcnow=lambda: None)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.util", util)
    recovery = ModuleType("custom_components.family_assistant.migration.residue_recovery")

    async def no_residue(*_args, **_kwargs):
        return None

    async def no_automatic_preservation(*_args, **_kwargs):
        raise AssertionError("Preservation requires separate explicit confirmation")

    recovery.async_review_residue = no_residue
    recovery.async_preserve_residue = no_automatic_preservation
    monkeypatch.setitem(sys.modules, recovery.__name__, recovery)
    index = ModuleType("custom_components.family_assistant.migration.copy_index")

    async def record_index(_hass, **kwargs):
        await kwargs["authorize"]()

    index.async_record_copy = record_index
    monkeypatch.setitem(sys.modules, index.__name__, index)
    for name, methods in {
        "copy_intent": ["async_commit_copy_intent", "async_select_copy_intent"],
        "shadow_registration": ["async_register_shadow"],
    }.items():
        port = ModuleType(f"custom_components.family_assistant.migration.{name}")

        async def unexpected(*_args, **_kwargs):
            raise AssertionError("Unexpected persistence boundary before final confirmation")

        for method in methods:
            setattr(port, method, unexpected)
        monkeypatch.setitem(sys.modules, port.__name__, port)
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_copy_flow",
        Path(__file__).parents[1] / "custom_components/family_assistant/migration/copy_flow.py",
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Flow:
    def __init__(self, module, phase="matches"):
        self.candidate, self.state = candidate()
        self.user = SimpleNamespace(
            id=self.state["members"]["owner"]["ha_user_id"], is_admin=True, is_active=True
        )
        self.context, self.flow_id = {"user_id": self.user.id}, "synthetic-review-flow"
        self.runtime = SimpleNamespace(
            engine=SimpleNamespace(snapshot=lambda: deepcopy(self.state))
        )
        self.config_entry = SimpleNamespace(entry_id="prototype", runtime_data=self.runtime)

        async def get_user(_user_id):
            await asyncio.sleep(0)
            return self.user

        self.hass = SimpleNamespace(
            data={"family_assistant": {}},
            auth=SimpleNamespace(async_get_user=get_user),
            config_entries=SimpleNamespace(async_get_entry=lambda _id: self.config_entry),
        )
        self.slot = {
            "flow_id": self.flow_id,
            "user_id": self.user.id,
            "runtime": self.runtime,
            "pins": module._pins(self.state),
            "expires": time.monotonic() + 900,
            "lock": asyncio.Lock(),
            "busy": False,
            "phase": phase,
            "page": 0,
            "rows": [f"Synthetic association {n}" for n in range(25)],
            "target": deepcopy(self.state),
            "candidate": self.candidate,
            "intent": {"entry_id": "a" * 32},
            "package_fingerprint": "b" * 64,
        }
        self.hass.data["family_assistant"][module._SLOT] = self.slot

    def _authorized_runtime(self):
        if self.state["members"]["owner"]["role"] != "owner":
            raise DomainError("forbidden")
        return self.runtime, "owner"

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}


@pytest.mark.asyncio
async def test_paged_review_rejects_replayed_old_confirmation_without_advancing(module):
    flow = Flow(module)
    first = await module.matches_step(flow)
    assert first["step_id"] == "legacy_copy_matches"
    old = flow.slot["page_token"]
    no = await module.matches_step(flow, {"review_token": old, "confirmed": False})
    assert no["errors"] and flow.slot["page"] == 0
    second = await module.matches_step(flow, {"review_token": old, "confirmed": True})
    assert second["step_id"] == "legacy_copy_matches" and flow.slot["page"] == 1
    current = flow.slot["page_token"]
    replay = await module.matches_step(flow, {"review_token": old, "confirmed": True})
    assert replay["errors"] and flow.slot["page"] == 1 and flow.slot["page_token"] == current


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    ["inactive", "admin", "owner", "member", "language", "runtime", "entry", "expiry", "flow"],
)
async def test_changed_authority_or_members_refuse_review_and_release_only_own_idle_slot(
    module, fault
):
    flow = Flow(module, phase="review")
    if fault == "inactive":
        flow.user.is_active = False
    if fault == "admin":
        flow.user.is_admin = False
    if fault == "owner":
        flow.state["members"]["owner"]["role"] = "child"
    if fault == "member":
        flow.state["members"]["owner"]["revision"] += 1
    if fault == "language":
        flow.state["settings"]["language"] = "uk"
    if fault == "runtime":
        flow.config_entry.runtime_data = object()
    if fault == "entry":
        flow.hass.config_entries.async_get_entry = lambda _id: None
    if fault == "expiry":
        flow.slot["expires"] = 0
    if fault == "flow":
        flow.slot["flow_id"] = "someone-else"
    result = await module.review_step(
        flow, {"review_token": flow.candidate.summary()["fingerprint"], "confirmed": True}
    )
    assert result["type"] == "abort"
    assert (module._SLOT in flow.hass.data["family_assistant"]) is (fault == "flow")


@pytest.mark.asyncio
async def test_preview_and_false_or_wrong_fingerprint_never_cross_persistence_boundary(module):
    flow = Flow(module, phase="review")
    assert (await module.review_step(flow))["step_id"] == "legacy_copy_review"
    for token, value in [("wrong", True), (flow.candidate.summary()["fingerprint"], False)]:
        result = await module.review_step(flow, {"review_token": token, "confirmed": value})
        assert result["errors"] and flow.slot["phase"] == "review"


@pytest.mark.asyncio
async def test_confirmed_review_passes_fresh_guards_and_exact_same_id_to_registration(
    module, monkeypatch
):
    flow = Flow(module, phase="review")
    effects = []

    async def intent(_hass, **kwargs):
        await kwargs["authorize"]()
        effects.append(("intent", kwargs["record"]["entry_id"]))

    async def register(_hass, **kwargs):
        await kwargs["authorize"]()
        assert kwargs["expected_fingerprint"] == flow.candidate.summary()["fingerprint"]
        effects.append(("register", kwargs["entry_id"]))
        return {"entry_id": kwargs["entry_id"], "loaded": True}

    monkeypatch.setattr(module, "async_commit_copy_intent", intent)
    monkeypatch.setattr(module, "async_register_shadow", register)
    message = {"review_token": flow.candidate.summary()["fingerprint"], "confirmed": True}
    assert (await module.review_step(flow, message))["step_id"] == "legacy_copy_complete"
    assert (await module.review_step(flow, message))["step_id"] == "legacy_copy_complete"
    assert effects == [("intent", "a" * 32), ("register", "a" * 32)]
    assert (await module.complete_step(flow, {}))["reason"] == "migration_copy_finished"
    assert module._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
async def test_revocation_after_intent_prevents_register_effect(module, monkeypatch):
    flow = Flow(module, phase="review")

    async def intent(_hass, **kwargs):
        await kwargs["authorize"]()
        flow.user.is_active = False

    async def register(_hass, **kwargs):
        await kwargs["authorize"]()
        raise AssertionError("Revocation should have blocked registration")

    monkeypatch.setattr(module, "async_commit_copy_intent", intent)
    monkeypatch.setattr(module, "async_register_shadow", register)
    result = await module.review_step(
        flow, {"review_token": flow.candidate.summary()["fingerprint"], "confirmed": True}
    )
    assert result["type"] == "abort" and result["reason"] == "forbidden"


@pytest.mark.asyncio
async def test_upload_cancellation_drains_owned_future_before_returning(module):
    reached, release = asyncio.Event(), asyncio.Event()

    async def work():
        reached.set()
        await release.wait()
        return "private result"

    hass = SimpleNamespace(async_add_executor_job=lambda *_args: asyncio.create_task(work()))
    task = asyncio.create_task(module._uploaded_bundle(hass, "a" * 32))
    await asyncio.wait_for(reached.wait(), 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_private_markdown_associations_cannot_introduce_links_or_html(module):
    displayed = module._markdown("[open](javascript:evil)\n<img src=x> | **secret**")
    assert "<img" not in displayed and "[open]" not in displayed and "**secret**" not in displayed
    assert "\n" not in displayed


@pytest.mark.asyncio
async def test_cancelled_final_writer_settles_then_releases_memory_but_keeps_receipt(
    module, monkeypatch
):
    flow = Flow(module, phase="review")
    entered, release = asyncio.Event(), asyncio.Event()
    saved = []

    async def writer(_hass, **kwargs):
        async def commit():
            entered.set()
            await release.wait()
            saved.append(kwargs["record"]["entry_id"])

        work = asyncio.create_task(commit())
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            await work
            raise

    monkeypatch.setattr(module, "async_commit_copy_intent", writer)
    request = {"review_token": flow.candidate.summary()["fingerprint"], "confirmed": True}
    task = asyncio.create_task(module.review_step(flow, request))
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    await asyncio.sleep(0)
    assert flow.slot["busy"] and module._slot(flow) is flow.slot
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert saved == ["a" * 32]
    assert module._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
async def test_cancelled_match_authorization_releases_only_own_idle_slot(module, monkeypatch):
    flow = Flow(module)
    entered = asyncio.Event()

    async def cancelled_guard(*_args):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(module, "_guard", cancelled_guard)
    task = asyncio.create_task(module.matches_step(flow))
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert module._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["matches", "review"])
async def test_owner_can_discard_own_review_without_any_store_or_entry_action(module, phase):
    flow = Flow(module, phase=phase)
    if phase == "matches":
        await module.matches_step(flow)
        method, token = module.matches_step, flow.slot["page_token"]
    else:
        method, token = module.review_step, flow.candidate.summary()["fingerprint"]
    result = await method(flow, {"review_token": token, "discard_review": True, "confirmed": False})
    assert result["reason"] == "migration_copy_cancelled"
    assert module._SLOT not in flow.hass.data["family_assistant"]


def _residue_flow(module):
    flow = Flow(module, phase="residue")
    flow.slot["recovery"] = SimpleNamespace(
        summary=lambda: {"fingerprint": "c" * 64, "temp_count": 2, "temp_bytes": 37}
    )
    return flow


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmation", [False, 1, "true", None])
async def test_residue_requires_separate_exact_confirmation(module, confirmation):
    flow = _residue_flow(module)
    shown = await module.residue_step(flow)
    assert shown["description_placeholders"]["temp_count"] == "2"
    refused = await module.residue_step(flow, {"review_token": "c" * 64, "confirmed": confirmation})
    assert refused["errors"] and flow.slot["phase"] == "residue"


@pytest.mark.asyncio
async def test_residue_wrong_token_and_discard_have_no_filesystem_effects(module):
    flow = _residue_flow(module)
    refused = await module.residue_step(flow, {"review_token": "d" * 64, "confirmed": True})
    assert refused["errors"]
    cancelled = await module.residue_step(flow, {"review_token": "c" * 64, "discard_review": True})
    assert cancelled["reason"] == "migration_copy_cancelled"
    assert module._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["preserve", "register", "revoked", "none"])
async def test_residue_retry_pins_candidate_and_preserves_before_registration(
    module, monkeypatch, failure
):
    flow = _residue_flow(module)
    port = sys.modules["custom_components.family_assistant.migration.residue_recovery"]
    effects = []
    pending_failure = failure

    async def preserve(_hass, **kwargs):
        nonlocal pending_failure
        await kwargs["authorize"]()
        assert kwargs["review"] is flow.slot["recovery"] and kwargs["confirmed"] is True
        effects.append(("preserve", kwargs["entry_id"], kwargs["expected_fingerprint"]))
        if pending_failure == "preserve":
            pending_failure = "none"
            raise ValueError("synthetic_retry")
        if pending_failure == "revoked":
            flow.user.is_active = False

    async def register(_hass, **kwargs):
        nonlocal pending_failure
        await kwargs["authorize"]()
        effects.append(("register", kwargs["entry_id"], kwargs["expected_fingerprint"]))
        if pending_failure == "register":
            pending_failure = "none"
            raise ValueError("synthetic_retry")
        return {"entry_id": kwargs["entry_id"], "loaded": True}

    monkeypatch.setattr(port, "async_preserve_residue", preserve)
    monkeypatch.setattr(module, "async_register_shadow", register)
    request = {"review_token": "c" * 64, "confirmed": True}
    result = await module.residue_step(flow, request)
    if failure == "revoked":
        assert result["type"] == "abort" and [row[0] for row in effects] == ["preserve"]
        return
    if failure != "none":
        assert result["step_id"] == "legacy_copy_residue" and result["errors"]
        assert not flow.slot["busy"]
        result = await module.residue_step(flow, request)
    assert result["step_id"] == "legacy_copy_complete"
    assert effects[-2][0] == "preserve" and effects[-1][0] == "register"
    assert all(row[1:] == ("a" * 32, flow.candidate.summary()["fingerprint"]) for row in effects)
    before = len(effects)
    assert (await module.residue_step(flow, request))["step_id"] == "legacy_copy_complete"
    assert len(effects) == before


@pytest.mark.asyncio
async def test_failed_registration_offers_read_only_residue_review_not_preservation(
    module, monkeypatch
):
    flow = _residue_flow(module)
    recovery = flow.slot.pop("recovery")
    flow.slot["phase"] = "review"
    calls = []

    async def intent(*_args, **kwargs):
        await kwargs["authorize"]()

    async def register(*_args, **_kwargs):
        raise ValueError("synthetic_interrupted")

    async def inspect(_hass, **kwargs):
        await kwargs["authorize"]()
        calls.append(kwargs["entry_id"])
        return recovery

    monkeypatch.setattr(module, "async_commit_copy_intent", intent)
    monkeypatch.setattr(module, "async_register_shadow", register)
    monkeypatch.setattr(
        sys.modules["custom_components.family_assistant.migration.residue_recovery"],
        "async_review_residue",
        inspect,
    )
    result = await module.review_step(
        flow, {"review_token": flow.candidate.summary()["fingerprint"], "confirmed": True}
    )
    assert result["step_id"] == "legacy_copy_residue" and calls == ["a" * 32]
    assert flow.slot["recovery"] is recovery and not flow.slot["busy"]


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_during_review", [False, True])
async def test_residue_inspection_revocation_never_returns_previous_private_review(
    module, monkeypatch, raise_during_review
):
    flow = Flow(module, phase="review")

    async def intent(*_args, **_kwargs):
        return None

    async def register(*_args, **_kwargs):
        raise ValueError("synthetic_interrupted")

    async def inspect(*_args, **_kwargs):
        flow.user.is_active = False
        if raise_during_review:
            raise ValueError("synthetic_inspection_failure")
        return None

    monkeypatch.setattr(module, "async_commit_copy_intent", intent)
    monkeypatch.setattr(module, "async_register_shadow", register)
    monkeypatch.setattr(
        sys.modules["custom_components.family_assistant.migration.residue_recovery"],
        "async_review_residue",
        inspect,
    )
    result = await module.review_step(
        flow, {"review_token": flow.candidate.summary()["fingerprint"], "confirmed": True}
    )
    assert result["type"] == "abort"
    assert module._SLOT not in flow.hass.data["family_assistant"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_code", [None, "migration_copy_index_full", "migration_copy_index_invalid"]
)
async def test_confirmed_copy_index_is_committed_after_intent_before_any_staging(
    module, monkeypatch, error_code
):
    flow = Flow(module, phase="review")
    effects = []

    async def intent(*_args, **kwargs):
        await kwargs["authorize"]()
        effects.append("intent")

    async def record(*_args, **kwargs):
        await kwargs["authorize"]()
        assert kwargs["prototype_pins"] == flow.slot["pins"]
        assert kwargs["intent"] == flow.slot["intent"]
        assert kwargs["candidate"] is flow.candidate
        effects.append("index")
        if error_code:
            raise DomainError(error_code)

    async def register(*_args, **_kwargs):
        effects.append("register")
        return {"entry_id": "a" * 32, "loaded": True}

    monkeypatch.setattr(module, "async_commit_copy_intent", intent)
    monkeypatch.setattr(module, "async_register_shadow", register)
    monkeypatch.setattr(
        sys.modules["custom_components.family_assistant.migration.copy_index"],
        "async_record_copy",
        record,
    )
    result = await module.review_step(
        flow, {"review_token": flow.candidate.summary()["fingerprint"], "confirmed": True}
    )
    if error_code:
        assert result["errors"]["base"] == error_code and effects == ["intent", "index"]
    else:
        assert result["step_id"] == "legacy_copy_complete" and effects == [
            "intent",
            "index",
            "register",
        ]
