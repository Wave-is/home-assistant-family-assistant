"""Acceptance navigation uses shown menus on baseline and candidate releases."""

from types import SimpleNamespace

import pytest
from ha_options_menu import GROUPS, select_option


def menu(step, options):
    return {"type": "menu", "step_id": step, "flow_id": "synthetic", "menu_options": options}


def harness(*responses):
    remaining = iter(responses)
    calls = []

    async def configure(flow_id, payload):
        calls.append((flow_id, payload))
        return next(remaining)

    return SimpleNamespace(
        config_entries=SimpleNamespace(options=SimpleNamespace(async_configure=configure))
    ), calls


@pytest.mark.parametrize("allow_flat", [False, True])
@pytest.mark.parametrize(
    ("group", "step"), [(group, step) for group, steps in GROUPS.items() for step in sorted(steps)]
)
async def test_candidate_uses_actual_category_before_leaf(group, step, allow_flat):
    leaf = {"type": "form", "step_id": step}
    hass, calls = harness(menu(group, sorted(GROUPS[group] | {"init"})), leaf)
    result = await select_option(
        hass, menu("init", [*GROUPS, "all_options"]), step, allow_flat=allow_flat
    )
    assert result is leaf
    assert calls == [
        ("synthetic", {"next_step_id": group}),
        ("synthetic", {"next_step_id": step}),
    ]


@pytest.mark.parametrize("step", ["member", "alarm_device"])
async def test_baseline_upgrade_uses_leaf_only_when_already_visible(step):
    leaf = {"type": "form", "step_id": step}
    hass, calls = harness(leaf)
    result = await select_option(
        hass, menu("init", ["general", "member", "alarm_device"]), step, allow_flat=True
    )
    assert result is leaf
    assert calls == [("synthetic", {"next_step_id": step})]


async def test_candidate_only_checks_do_not_accept_flat_menu():
    hass, calls = harness()
    with pytest.raises(AssertionError):
        await select_option(hass, menu("init", ["legacy_resume"]), "legacy_resume")
    assert calls == []


async def test_missing_category_is_not_bypassed_in_baseline_compatibility():
    hass, calls = harness()
    with pytest.raises(AssertionError):
        await select_option(hass, menu("init", ["general"]), "member", allow_flat=True)
    assert calls == []


async def test_missing_category_leaf_does_not_send_invisible_step():
    hass, calls = harness(menu("menu_family", ["general", "init"]))
    with pytest.raises(AssertionError):
        await select_option(hass, menu("init", [*GROUPS, "all_options"]), "member")
    assert calls == [("synthetic", {"next_step_id": "menu_family"})]


async def test_technical_route_also_checks_visible_leaf():
    hass, calls = harness(menu("all_options", ["general", "init"]))
    with pytest.raises(AssertionError):
        await select_option(hass, menu("init", [*GROUPS, "all_options"]), "member", technical=True)
    assert calls == [("synthetic", {"next_step_id": "all_options"})]
