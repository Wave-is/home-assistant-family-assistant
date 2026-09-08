"""Immutable retry coordinates with Store-shaped ports and real canonical checks."""

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_shadow_install import port as stage_port

from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 8, tzinfo=UTC)


@pytest.fixture
def port(monkeypatch, tmp_path):
    p = stage_port.__wrapped__(monkeypatch, tmp_path)
    spec = importlib.util.spec_from_file_location(
        "custom_components.family_assistant.migration._test_copy_intent",
        Path(__file__).parents[1] / "custom_components/family_assistant/migration/copy_intent.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def authorize():
        if not p.user.is_active or not p.user.is_admin:
            raise DomainError("forbidden")

    async def select(**overrides):
        return await module.async_select_copy_intent(
            p.hass,
            **(
                {
                    "package_fingerprint": "a" * 64,
                    "target": p.target,
                    "prepared_at": NOW,
                    "authorize": authorize,
                }
                | overrides
            ),
        )

    async def commit(record, **overrides):
        return await module.async_commit_copy_intent(
            p.hass,
            **(
                {
                    "record": record,
                    "package_fingerprint": "a" * 64,
                    "target": p.target,
                    "authorize": authorize,
                }
                | overrides
            ),
        )

    p.intent, p.select, p.commit = module, select, commit
    return p


@pytest.mark.asyncio
async def test_preview_does_not_write_and_committed_coordinates_survive_later_clock_and_process(
    port,
):
    proposal = await port.select()
    assert not port.values and not port.writes
    await port.commit(proposal)
    before = list(port.writes)
    assert len(before) == 1
    port.hass.data.clear()
    assert await port.select(prepared_at=NOW + timedelta(days=5)) == proposal
    assert await port.commit(proposal) == proposal
    assert port.writes == before


@pytest.mark.asyncio
async def test_lost_commit_acknowledgement_cannot_change_id_or_preparation_time(port):
    proposal = await port.select()

    async def lost(_key):
        raise OSError("PRIVATE SYNTHETIC OUTCOME")

    port.options.after_save = lost
    with pytest.raises(port.intent.CopyIntentError, match="^migration_copy_intent_invalid$"):
        await port.commit(proposal)
    port.options.after_save = None
    assert await port.select(prepared_at=NOW + timedelta(days=1)) == proposal
    assert await port.commit(proposal) == proposal
    assert len(port.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["version", "package", "target", "time", "extra", "identity", "timezone"]
)
async def test_changed_or_malformed_intent_is_never_committed(port, fault):
    proposal = await port.select()
    if fault == "version":
        proposal["version"] = True
    if fault == "package":
        proposal["package_fingerprint"] = "b" * 64
    if fault == "target":
        port.target["settings"]["name"] = "Changed target"
    if fault == "time":
        proposal["prepared_at"] = "PRIVATE NON-DATE"
    if fault == "extra":
        proposal["extra"] = "private"
    if fault == "identity":
        proposal["entry_id"] = "different"
    if fault == "timezone":
        proposal["prepared_at"] = "2026-09-08T12:00:00+03:00"
    with pytest.raises(port.intent.CopyIntentError):
        await port.commit(proposal)
    assert not port.writes


@pytest.mark.asyncio
async def test_two_review_times_for_same_id_cannot_overwrite_first_confirmation(port):
    first = await port.select()
    second = await port.select(prepared_at=NOW + timedelta(seconds=30))
    assert first["entry_id"] == second["entry_id"]
    await port.commit(first)
    with pytest.raises(port.intent.CopyIntentError):
        await port.commit(second)
    assert await port.select() == first and len(port.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["revoked", "backup", "changed_during_read"])
async def test_commit_rechecks_authority_and_target_under_setup_lock(port, fault):
    proposal = await port.select()
    if fault == "revoked":
        port.user.is_active = False
    if fault == "backup":
        port.hass.data["family_assistant"] = {"backup": object()}
    if fault == "changed_during_read":

        async def change(_key):
            port.target["members"]["owner"]["revision"] += 1

        port.options.before_load = change
    with pytest.raises(port.intent.CopyIntentError):
        await port.commit(proposal)
    assert not port.writes


@pytest.mark.asyncio
async def test_cancelled_commit_settles_before_releasing_setup_lock(port):
    proposal = await port.select()
    reached, release = asyncio.Event(), asyncio.Event()

    async def pause(_key):
        reached.set()
        await release.wait()

    port.options.before_save = pause
    task = asyncio.create_task(port.commit(proposal))
    await asyncio.wait_for(reached.wait(), 5)
    task.cancel()
    await asyncio.sleep(0)
    assert port.hass.data["family_assistant"]["setup_lock"].locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    port.options.before_save = None
    assert await port.select() == proposal
    assert await port.commit(proposal) == proposal and len(port.writes) == 1
