"""Two-process actual-HA application upgrade acceptance helper.

The orchestrator installs an extracted baseline or candidate integration under
the same writable synthetic HA config directory, then invokes this file in two
separate Python processes::

    python tests/ha_upgrade_acceptance.py prepare --config ... --contract ... \
        --expected-version ...
    python tests/ha_upgrade_acceptance.py verify --config ... --contract ... \
        --expected-version ...

No runtime tree is replaced while Home Assistant or Python is running.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from ha_options_menu import select_option
from homeassistant import bootstrap, config_entries, loader
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.components.siren import DATA_COMPONENT, SirenEntity, SirenEntityFeature
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component

DOMAIN = "family_assistant"
CONTRACT_SCHEMA = 1
HOUSEHOLD_NAME = "Synthetic upgrade household"
OWNER_NAME = "Synthetic upgrade owner"
CHILD_NAME = "Synthetic upgrade child"
OWNER_OPERATION = "upgrade-task-create"
POINT_OPERATION = "upgrade-points-award"
ALARM_OPERATION = "upgrade-alarm-save"
PLACEHOLDER_OPTIONS = {
    "telegram": {
        "enabled": False,
        "token": "synthetic-disabled-placeholder",
        "bot": {"id": 700000001, "username": "upgrade_placeholder_bot"},
    },
    "conversation": {
        "enabled": False,
        "primary": {
            "url": "https://upgrade.invalid/api",
            "model": "synthetic-placeholder",
            "api_key": "synthetic-disabled-placeholder",
            "allow_http": False,
            "timeout": 15,
        },
    },
}


class SyntheticUpgradeSiren(SirenEntity):
    """In-process entity used only to pass the real alarm Options review."""

    _attr_name = "Synthetic upgrade siren"
    _attr_unique_id = "synthetic-upgrade-siren"
    _attr_should_poll = False
    _attr_is_on = False
    _attr_supported_features = SirenEntityFeature.TURN_ON | SirenEntityFeature.TURN_OFF

    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def async_turn_on(self, **_kwargs) -> None:
        self.calls.append(True)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **_kwargs) -> None:
        self.calls.append(False)
        self._attr_is_on = False
        self.async_write_ha_state()


def _core_config() -> dict:
    return {
        "homeassistant": {
            "name": "Synthetic upgrade sandbox",
            "latitude": 0,
            "longitude": 0,
            "elevation": 0,
            "unit_system": "metric",
            "time_zone": "UTC",
            "country": "GB",
        },
        "http": {"server_host": "127.0.0.1", "server_port": 8123},
    }


def _runtime_version(config_directory: Path) -> str:
    manifest_path = config_directory / "custom_components" / DOMAIN / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, TypeError, ValueError) as error:
        raise AssertionError("installed runtime manifest is unavailable") from error
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not version:
        raise AssertionError("installed runtime version is unavailable")
    return version


async def _start(config_directory: Path) -> HomeAssistant:
    hass = HomeAssistant(str(config_directory))
    hass.config.skip_pip = True
    loader.async_setup(hass)
    configured = await bootstrap.async_from_config_dict(_core_config(), hass)
    if configured is None:
        raise AssertionError("Home Assistant bootstrap failed")
    await hass.async_start()
    await hass.async_block_till_done()
    if hass.state is not CoreState.running:
        raise AssertionError("Home Assistant did not reach running state")
    return hass


async def _options_step(hass, entry, user_id: str, step: str):
    result = await hass.config_entries.options.async_init(
        entry.entry_id, context={"source": "user", "user_id": user_id}
    )
    if result.get("type") != "menu":
        raise AssertionError(f"Options did not open at its menu: {result.get('type')}")
    # The same candidate helper prepares both the old baseline and new runtime.
    return await select_option(hass, result, step, allow_flat=True)


async def _create_child(hass, entry, owner_id: str) -> str:
    result = await _options_step(hass, entry, owner_id, "member")
    if result.get("type") != "form" or result.get("step_id") != "member":
        raise AssertionError("member selector did not open")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"member_id": "_new"}
    )
    if result.get("type") != "form" or result.get("step_id") != "edit_member":
        raise AssertionError("member editor did not open")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": CHILD_NAME, "role": "child", "language": "uk", "active": True},
    )
    if result.get("type") != "create_entry":
        raise AssertionError("member Options write failed")
    await hass.async_block_till_done()
    matches = [
        member
        for member in entry.runtime_data.engine.snapshot()["members"].values()
        if member.get("name") == CHILD_NAME
    ]
    if len(matches) != 1:
        raise AssertionError("synthetic child identity is ambiguous")
    return matches[0]["id"]


async def _add_siren(hass) -> SyntheticUpgradeSiren:
    if not await async_setup_component(hass, "siren", {}):
        raise AssertionError("siren component setup failed")
    siren = SyntheticUpgradeSiren()
    await hass.data[DATA_COMPONENT].async_add_entities([siren])
    await hass.async_block_till_done()
    if not isinstance(siren.entity_id, str):
        raise AssertionError("synthetic siren has no entity ID")
    return siren


async def _bind_siren(
    hass, entry, owner_id: str, child_id: str
) -> tuple[str, SyntheticUpgradeSiren]:
    siren = await _add_siren(hass)
    result = await _options_step(hass, entry, owner_id, "alarm_device")
    if result.get("type") != "form" or result.get("step_id") != "alarm_device":
        raise AssertionError("alarm-device Options form did not open")
    fields = {str(key) for key in result["data_schema"].schema}
    payload = {
        "entity_id": siren.entity_id,
        "volume": 0.4,
        "enabled": True,
        "confirmed": True,
    }
    if "entity_id" not in fields:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"member": child_id}
        )
        if result.get("step_id") != "alarm_device_settings":
            raise AssertionError("selected member alarm settings did not open")
    else:
        # The published baseline has the old one-step Options contract.
        payload["member"] = child_id
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        payload,
    )
    if result.get("type") != "create_entry":
        raise AssertionError("alarm-device Options write failed")
    await hass.async_block_till_done()
    if siren.calls:
        raise AssertionError("alarm Options review actuated the synthetic siren")
    return siren.entity_id, siren


def _selected(state: dict, ids: dict[str, str]) -> dict:
    child_id = ids["child_id"]
    return {
        "settings": {
            key: deepcopy(state["settings"][key])
            for key in ("name", "language", "modules", "timezone")
        },
        "member": deepcopy(state["members"][child_id]),
        "task": deepcopy(state["tasks"][ids["task_id"]]),
        "award": deepcopy(state["court"][ids["award_id"]]),
        "alarm": deepcopy(state["alarms"][ids["alarm_id"]]),
        "points": sum(
            item["points"]
            for item in state["court"].values()
            if item.get("member") == child_id and item.get("status") == "active"
        ),
        "processed": {
            operation: deepcopy(state["processed"][operation])
            for operation in (OWNER_OPERATION, POINT_OPERATION, ALARM_OPERATION)
        },
    }


async def prepare(config_directory: Path, expected_version: str) -> dict:
    """Create the baseline through real HA flows and the integration's Store."""
    actual_version = _runtime_version(config_directory)
    if actual_version != expected_version:
        raise AssertionError("baseline artifact version mismatch")
    hass = await _start(config_directory)
    contract = None
    try:
        if hass.config_entries.async_entries(DOMAIN):
            raise AssertionError("prepare requires a fresh synthetic HA config")
        owner = await hass.auth.async_create_user(OWNER_NAME, group_ids=[GROUP_ID_ADMIN])
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user", "user_id": owner.id}
        )
        if result.get("type") != "form" or result.get("step_id") != "user":
            raise AssertionError("integration config flow did not open")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": HOUSEHOLD_NAME,
                "owner_name": OWNER_NAME,
                "language": "en",
                "timezone": "Europe/Berlin",
                "template": "manual",
            },
        )
        if result.get("type") != "form" or result.get("step_id") != "modules":
            raise AssertionError("integration modules step did not open")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"tasks": True, "court": True, "alarms": True}
        )
        if result.get("type") != "create_entry":
            raise AssertionError("integration config entry was not created")
        entry = result["result"]
        await hass.async_block_till_done()
        if entry.state is not config_entries.ConfigEntryState.LOADED:
            raise AssertionError("baseline config entry did not load")
        next_flow = result.get("next_flow")
        if isinstance(next_flow, tuple) and len(next_flow) == 2 and isinstance(next_flow[1], str):
            hass.config_entries.options.async_abort(next_flow[1])

        child_id = await _create_child(hass, entry, owner.id)
        siren_id, siren = await _bind_siren(hass, entry, owner.id, child_id)
        options = {
            **dict(entry.options),
            **deepcopy(PLACEHOLDER_OPTIONS),
        }
        if not hass.config_entries.async_update_entry(entry, options=options):
            raise AssertionError("synthetic provider Options were not written")
        await hass.async_block_till_done()
        if entry.runtime_data.telegram is not None or entry.runtime_data.assistant is not None:
            raise AssertionError("disabled synthetic providers unexpectedly started")

        engine = entry.runtime_data.engine
        now = datetime.now(UTC)
        task_payload = {
            "title": "Synthetic upgrade task",
            "assignee": child_id,
            "due_at": "2099-12-01T09:00:00+00:00",
            "checklist": ["Retain this checklist"],
            "report_type": "text",
            "penalty": 0,
        }
        award_payload = {
            "member": child_id,
            "points": 7,
            "reason": "Synthetic upgrade continuity",
        }
        alarm_payload = {
            "member": child_id,
            "name": "Synthetic disabled school alarm",
            "time": "07:05",
            "days": [0, 2, 4],
            "timezone": "Europe/Berlin",
            "enabled": False,
            "profile": "gentle",
            "penalty": 0,
        }
        task = await engine.execute("owner", "tasks.create", task_payload, OWNER_OPERATION, now)
        award = await engine.execute("owner", "court.award", award_payload, POINT_OPERATION, now)
        alarm = await engine.execute("owner", "alarms.save", alarm_payload, ALARM_OPERATION, now)
        entry.runtime_data.updated()
        await hass.async_block_till_done()
        if siren.calls or engine.snapshot()["alarm_runs"]:
            raise AssertionError("baseline fixture produced an alarm side effect")

        ids = {
            "child_id": child_id,
            "task_id": task["id"],
            "award_id": award["id"],
            "alarm_id": alarm["id"],
        }
        snapshot = engine.snapshot()
        from custom_components.family_assistant.const import SCHEMA_VERSION

        stored = await Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}").async_load()
        if not isinstance(stored, dict) or _selected(stored, ids) != _selected(snapshot, ids):
            raise AssertionError("baseline Engine state was not durably stored")
        contract = {
            "schema": CONTRACT_SCHEMA,
            "baseline_version": actual_version,
            "entry_id": entry.entry_id,
            "owner_user_id": owner.id,
            "entry_data": deepcopy(dict(entry.data)),
            "entry_options": deepcopy(dict(entry.options)),
            "siren_entity_id": siren_id,
            "ids": ids,
            "commands": [
                {
                    "operation_id": OWNER_OPERATION,
                    "action": "tasks.create",
                    "payload": task_payload,
                },
                {
                    "operation_id": POINT_OPERATION,
                    "action": "court.award",
                    "payload": award_payload,
                },
                {
                    "operation_id": ALARM_OPERATION,
                    "action": "alarms.save",
                    "payload": alarm_payload,
                },
            ],
            "selected_state": _selected(snapshot, ids),
        }
    finally:
        await hass.async_stop(force=True)
    if contract is None:
        raise AssertionError("baseline contract was not produced")
    return contract


def _validate_contract(value: object) -> dict:
    required = {
        "schema",
        "baseline_version",
        "entry_id",
        "owner_user_id",
        "entry_data",
        "entry_options",
        "siren_entity_id",
        "ids",
        "commands",
        "selected_state",
    }
    if type(value) is not dict or set(value) != required or value.get("schema") != CONTRACT_SCHEMA:
        raise AssertionError("upgrade contract is invalid")
    if not all(
        isinstance(value.get(key), str) and value[key]
        for key in (
            "baseline_version",
            "entry_id",
            "owner_user_id",
            "siren_entity_id",
        )
    ):
        raise AssertionError("upgrade contract identity is invalid")
    if type(value.get("entry_data")) is not dict or type(value.get("entry_options")) is not dict:
        raise AssertionError("upgrade contract Config Entry data is invalid")
    if type(value.get("ids")) is not dict or set(value["ids"]) != {
        "child_id",
        "task_id",
        "award_id",
        "alarm_id",
    }:
        raise AssertionError("upgrade contract record IDs are invalid")
    if type(value.get("commands")) is not list or len(value["commands"]) != 3:
        raise AssertionError("upgrade contract commands are invalid")
    if type(value.get("selected_state")) is not dict:
        raise AssertionError("upgrade contract state is invalid")
    return value


async def verify(config_directory: Path, expected_version: str, contract: dict) -> None:
    """Load the candidate in a new HA process and verify durable continuity."""
    contract = _validate_contract(contract)
    actual_version = _runtime_version(config_directory)
    if actual_version != expected_version:
        raise AssertionError("candidate artifact version mismatch")
    if actual_version == contract["baseline_version"]:
        raise AssertionError("candidate version must differ from the baseline version")
    hass = await _start(config_directory)
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if len(entries) != 1 or entries[0].entry_id != contract["entry_id"]:
            raise AssertionError("exact config entry ID was not retained")
        entry = hass.config_entries.async_get_entry(contract["entry_id"])
        if entry is None or entry.state is not config_entries.ConfigEntryState.LOADED:
            raise AssertionError("candidate config entry did not load")
        if dict(entry.data) != contract["entry_data"]:
            raise AssertionError("Config Entry data changed during upgrade")
        if dict(entry.options) != contract["entry_options"]:
            raise AssertionError("Config Entry Options changed during upgrade")
        owner = await hass.auth.async_get_user(contract["owner_user_id"])
        if owner is None or owner.is_active is not True or owner.is_admin is not True:
            raise AssertionError("exact synthetic owner identity was not retained")

        runtime = entry.runtime_data
        if runtime.telegram is not None or runtime.assistant is not None:
            raise AssertionError("disabled provider placeholder started a client")
        if runtime.network is not None or runtime.recipes is not None:
            raise AssertionError("an unconfigured optional provider unexpectedly started")
        if dict(entry.options).get("telegram") != PLACEHOLDER_OPTIONS["telegram"]:
            raise AssertionError("disabled bot placeholder was not retained")
        if dict(entry.options).get("conversation") != PLACEHOLDER_OPTIONS["conversation"]:
            raise AssertionError("disabled model placeholder was not retained")

        siren = await _add_siren(hass)
        if siren.entity_id != contract["siren_entity_id"]:
            raise AssertionError("synthetic alarm entity ID was not retained")

        state = runtime.engine.snapshot()
        selected = _selected(state, contract["ids"])
        if selected != contract["selected_state"]:
            raise AssertionError("selected durable integration state changed during upgrade")
        if selected["points"] != 7 or state["alarm_runs"]:
            raise AssertionError("points or disabled-alarm continuity is invalid")

        from custom_components.family_assistant.const import SCHEMA_VERSION

        stored = await Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{contract['entry_id']}").async_load()
        if not isinstance(stored, dict) or _selected(stored, contract["ids"]) != selected:
            raise AssertionError("runtime projection does not match the persisted Store")

        before_replay = runtime.engine.snapshot()
        for command in contract["commands"]:
            operation = command.get("operation_id")
            action = command.get("action")
            payload = command.get("payload")
            if (
                not isinstance(operation, str)
                or not isinstance(action, str)
                or type(payload) is not dict
            ):
                raise AssertionError("upgrade replay command is invalid")
            receipt = await runtime.engine.execute(
                "owner", action, payload, operation, datetime.now(UTC)
            )
            expected = selected["processed"][operation]["result"]
            if receipt != expected:
                raise AssertionError("persisted operation receipt did not replay exactly")
        if runtime.engine.snapshot() != before_replay:
            raise AssertionError("exact replay mutated candidate state")
        if siren.calls:
            raise AssertionError("candidate runtime actuated the disabled synthetic siren")
    finally:
        await hass.async_stop(force=True)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    config_directory = arguments.config.resolve(strict=True)
    if arguments.phase == "prepare":
        contract = asyncio.run(prepare(config_directory, arguments.expected_version))
        with arguments.contract.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(contract, target, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            target.write("\n")
        print("PASS: baseline packaged runtime created durable synthetic upgrade contract")
        return
    try:
        contract = json.loads(arguments.contract.read_bytes())
    except (OSError, TypeError, ValueError) as error:
        raise AssertionError("upgrade contract could not be read") from error
    asyncio.run(verify(config_directory, arguments.expected_version, contract))
    print("PASS: candidate packaged runtime retained Config Entry, Options, Store and replay IDs")


if __name__ == "__main__":
    main()
