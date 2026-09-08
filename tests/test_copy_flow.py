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
