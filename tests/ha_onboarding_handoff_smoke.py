"""Actual Home Assistant post-create onboarding handoff acceptance helper."""

from __future__ import annotations

from copy import deepcopy

from homeassistant import config_entries


async def verify_onboarding_handoff(hass, create_result, owner):
    """Verify Core's next-flow handoff against the exact newly created entry."""
    from custom_components.family_assistant.onboarding_handoff import (
        async_post_create_handoff,
    )

    assert create_result["type"] == "create_entry", create_result
    entry = create_result["result"]
    assert entry.state is config_entries.ConfigEntryState.LOADED, entry.state
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    runtime = entry.runtime_data
    assert hass.data["family_assistant"]["entries"][entry.entry_id] is runtime

    next_flow = create_result.get("next_flow")
    assert isinstance(next_flow, tuple) and len(next_flow) == 2, create_result
    assert next_flow[0] is config_entries.FlowType.OPTIONS_FLOW, next_flow
    flow_id = next_flow[1]
    live = hass.config_entries.options.async_get(flow_id)
    assert live["handler"] == entry.entry_id, live
    assert live["step_id"] == "guided_onboarding", live
    assert live["context"] == {"source": "user", "user_id": owner.id}, live

    before_state = runtime.engine.snapshot()
    before_options = deepcopy(dict(entry.options))
    before_modified = entry.modified_at
    before_runtime = entry.runtime_data

    progress_before = hass.config_entries.options.async_progress_by_handler(
        entry.entry_id, include_uninitialized=True
    )
    repeated_result = dict(create_result)
    repeated_result.pop("next_flow")
    repeated = await async_post_create_handoff(
        hass,
        repeated_result,
        {"source": "user", "user_id": owner.id},
    )
    assert repeated["next_flow"] == next_flow, repeated
    assert (
        hass.config_entries.options.async_progress_by_handler(
            entry.entry_id, include_uninitialized=True
        )
        == progress_before
    )

    guide = await hass.config_entries.options.async_configure(flow_id)
    assert guide["type"] == "menu" and guide["step_id"] == "guided_onboarding", guide
    assert guide["menu_options"][-1] == "guided_finish", guide
    finished = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "guided_finish"}
    )
    assert finished["type"] == "abort" and finished["reason"] == "guided_finished", finished
    await hass.async_block_till_done()

    assert entry.runtime_data is before_runtime
    assert runtime.engine.snapshot() == before_state
    assert dict(entry.options) == before_options
    assert entry.modified_at == before_modified

    manual = await hass.config_entries.options.async_init(
        entry.entry_id,
        context={"source": "user", "user_id": owner.id},
    )
    assert manual["type"] == "menu" and manual["step_id"] == "init", manual
    collision_result = dict(create_result)
    collision_result.pop("next_flow")
    collision = await async_post_create_handoff(
        hass,
        collision_result,
        {"source": "user", "user_id": owner.id},
    )
    assert "next_flow" not in collision, collision
    assert hass.config_entries.options.async_get(manual["flow_id"])["step_id"] == "init"
    hass.config_entries.options.async_abort(manual["flow_id"])

    arbitrary = await hass.config_entries.options.async_init(
        entry.entry_id,
        context={"source": "user", "user_id": owner.id},
        data={"guided_onboarding_handoff": True, "extra": True},
    )
    assert arbitrary["type"] == "menu" and arbitrary["step_id"] == "init", arbitrary
    hass.config_entries.options.async_abort(arbitrary["flow_id"])

    assert entry.runtime_data is before_runtime
    assert runtime.engine.snapshot() == before_state
    assert dict(entry.options) == before_options
    assert entry.modified_at == before_modified
    print(
        "PASS: post-create guide targets the exact loaded entry, deduplicates retries "
        "and performs no Options or Engine write"
    )
