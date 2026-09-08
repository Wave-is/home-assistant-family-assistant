"""Persistent migration isolation must reject every public write lane."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain.engine import Engine, new_state
from custom_components.family_assistant.domain.shadow import SCHEMA
from custom_components.family_assistant.domain.validation import DomainError

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def isolated_state():
    state = new_state("synthetic-owner", "Synthetic review", modules=[])
    state["schema_version"] = SCHEMA
    state["migration_shadow"] = {
        "version": 1,
        "mode": "read_only",
        "source_fingerprint": "a" * 64,
        "conversion_fingerprint": "b" * 64,
    }
    return state


async def never_save(_state):
    pytest.fail("Shadow wrote state")


@pytest.mark.asyncio
async def test_every_write_lane_denied_before_callback_and_after_reload():
    state = isolated_state()
    for engine in (Engine(state, never_save), Engine(deepcopy(state), never_save)):
        assert engine.shadow_mode

        def never_change(_ctx):
            pytest.fail("Shadow invoked mutation callback")

        for method in (
            lambda selected=engine: selected.execute(
                "owner", "settings.update", {"name": "changed"}, "one", NOW
            ),
            lambda selected=engine: selected.tick(NOW),
            lambda selected=engine: selected.system_update("synthetic", NOW, never_change),
            lambda selected=engine: selected.background_update("synthetic", NOW, never_change),
        ):
            with pytest.raises(DomainError, match="migration_shadow_read_only"):
                await method()
        assert engine.snapshot() == state
        token = await engine.async_begin_backup()
        await engine.async_end_backup(token)
        with pytest.raises(DomainError, match="migration_shadow_read_only"):
            await engine.tick(NOW)
        await engine.async_close()


def test_projection_owner_only_and_no_private_archive_or_fingerprint():
    state = isolated_state()
    state["members"]["parent"] = {
        **state["members"]["owner"],
        "id": "parent",
        "role": "parent",
        "ha_user_id": "synthetic-parent",
    }
    state["migration_archive"] = {"private": "never a family-view field"}
    engine = Engine(state, never_save)
    view = engine.view("owner", now=NOW)
    assert view["read_only"] == "migration_shadow_read_only"
    assert "migration_archive" not in view and "migration_shadow" not in view
    with pytest.raises(DomainError, match="forbidden"):
        engine.view("parent", now=NOW)
    with pytest.raises(DomainError, match="forbidden"):
        engine.actor_for_ha("synthetic-parent")


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "version",
        "sha",
        "newline",
        "extra",
        "modules",
        "penalties",
        "outbox",
        "network",
        "alarm_runs",
        "alarm",
    ],
)
def test_unsafe_or_malformed_shadow_cannot_load(mutation):
    state = isolated_state()
    marker = state["migration_shadow"]
    if mutation == "none":
        state["migration_shadow"] = None
    elif mutation == "version":
        marker["version"] = True
    elif mutation in {"sha", "newline"}:
        marker["source_fingerprint"] = "wrong" if mutation == "sha" else "a" * 64 + "\n"
    elif mutation == "extra":
        marker["activation"] = True
    elif mutation == "modules":
        state["settings"]["modules"] = ["tasks"]
    elif mutation == "penalties":
        state["settings"]["automatic_penalties"] = True
    elif mutation == "alarm":
        state["alarms"]["A000001"] = {"enabled": True}
    else:
        state[mutation]["unsafe"] = True
    with pytest.raises(DomainError, match="migration_shadow_invalid"):
        Engine(state, never_save)


@pytest.mark.asyncio
async def test_normal_engine_still_writable():
    writes = []

    async def save(state):
        writes.append(state)

    engine = Engine(new_state("synthetic-owner", "Synthetic normal"), save)
    assert not engine.shadow_mode
    await engine.system_update(
        "synthetic", NOW, lambda ctx: ctx.state["settings"].update(name="Updated")
    )
    assert len(writes) == 1 and engine.snapshot()["settings"]["name"] == "Updated"


@pytest.mark.parametrize(
    "mutation", ["ordinary_schema", "missing_marker", "alarm_none", "outbox_list", "settings_list"]
)
def test_shadow_schema_and_structural_contract_cannot_be_partially_removed(mutation):
    state = isolated_state()
    if mutation == "ordinary_schema":
        state["schema_version"] = 1
    elif mutation == "missing_marker":
        state.pop("migration_shadow")
    elif mutation == "alarm_none":
        state["alarms"] = None
    elif mutation == "outbox_list":
        state["outbox"] = []
    else:
        state["settings"] = []
    with pytest.raises(DomainError, match="migration_shadow_invalid"):
        Engine(state, never_save)
