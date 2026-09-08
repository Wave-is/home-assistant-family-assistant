"""Recovery wrapper authority/journal guards against real shadow candidates."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from test_shadow_install import ENTRY, JOURNAL, STORE
from test_shadow_install import port as install_port


@pytest.fixture
def port(monkeypatch, tmp_path):
    result = install_port.__wrapped__(monkeypatch, tmp_path)
    monkeypatch.setitem(
        sys.modules, "custom_components.family_assistant.migration.shadow_install", result.module
    )
    name = "custom_components.family_assistant.migration._test_residue"
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).parents[1]
        / "custom_components/family_assistant/migration/residue_recovery.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    result.recovery = module
    result.inputs = {
        "entry_id": ENTRY,
        "user_id": result.user.id,
        "candidate": result.candidate,
        "target": result.target,
        "expected_fingerprint": result.candidate.summary()["fingerprint"],
        "authorize": None,
    }
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "inactive",
        "not_admin",
        "wrong_user",
        "owner",
        "entry",
        "runtime",
        "backup",
        "fingerprint",
        "store",
        "intent",
        "bool_intent",
        "journal",
        "missing_intent",
    ],
)
async def test_refuses_unsafe_recovery_without_writes(port, fault):
    await port.stage()
    if fault == "inactive":
        port.user.is_active = False
    elif fault == "not_admin":
        port.user.is_admin = False
    elif fault == "wrong_user":
        port.inputs["user_id"] = "other-user"
    elif fault == "owner":
        port.target["members"]["owner"]["ha_user_id"] = "other-user"
    elif fault == "entry":
        port.entries[ENTRY] = object()
    elif fault == "runtime":
        port.hass.data["family_assistant"]["entries"][ENTRY] = object()
    elif fault == "backup":
        port.hass.data["family_assistant"]["backup"] = object()
    elif fault == "fingerprint":
        port.inputs["expected_fingerprint"] = "f" * 64
    elif fault == "store":
        port.values[STORE]["settings"]["language"] = "uk"
    elif fault == "intent":
        port.values[JOURNAL]["fingerprint"] = "f" * 64
    elif fault == "bool_intent":
        port.values[JOURNAL]["version"] = True
    elif fault == "missing_intent":
        port.values.pop(JOURNAL)
    elif fault == "journal":
        port.values[f"family_assistant.shadow_recovery.{ENTRY}"] = {"version": True}
    before, writes = deepcopy(port.values), list(port.writes)
    with pytest.raises(port.recovery.ResidueRecoveryError):
        await port.recovery.async_review_residue(port.hass, **port.inputs)
    assert port.values == before and port.writes == writes
    assert not (port.root / "family_assistant_recovery").exists()


@pytest.mark.asyncio
async def test_caller_guard_rechecked_after_store_load(port):
    await port.stage()
    calls = 0

    async def authorize():
        nonlocal calls
        calls += 1
        if calls >= 4:
            port.user.is_active = False
            raise ValueError("synthetic_expired_review")

    before = deepcopy(port.values)
    with pytest.raises(port.recovery.ResidueRecoveryError):
        await port.recovery.async_review_residue(
            port.hass, **(port.inputs | {"authorize": authorize})
        )
    assert calls >= 4 and port.values == before


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [False, 1, "true", None])
async def test_preservation_refuses_nonexplicit_consent_before_any_io(port, confirmed):
    review = port.recovery.ResidueReview(b"{}", b"{}", b"{}")
    with pytest.raises(port.recovery.ResidueRecoveryError, match="confirmation_required"):
        await port.recovery.async_preserve_residue(
            port.hass, review=review, confirmed=confirmed, **port.inputs
        )
    assert not port.writes and not port.values


def test_review_summary_is_copied_and_representation_contains_no_private_values(port):
    review = port.recovery.ResidueReview(b'"PRIVATE_OWNER"', b'"PRIVATE_PATH"', b'{"temp_count":2}')
    mutated = review.summary()
    mutated["temp_count"] = 100
    assert review.summary() == {"temp_count": 2}
    assert "PRIVATE" not in repr(review)
