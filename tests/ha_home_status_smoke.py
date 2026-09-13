"""Actual isolated HA Options, registry/ACL, WebSocket, Store and late Telegram reads."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch


async def _open(hass, entry, user, step):
    from ha_options_menu import select_option

    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": user.id}
    )
    menu = await select_option(hass, flow, "home_status")
    assert menu["type"] == "menu" and step in menu["menu_options"], menu
    return await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": step}
    )


async def _save(hass, form, values, *, confirmed=True):
    reviewed = await hass.config_entries.options.async_configure(form["flow_id"], values)
    assert reviewed["type"] == "form" and reviewed["step_id"] == "home_status_review", reviewed
    result = await hass.config_entries.options.async_configure(
        reviewed["flow_id"], {"confirmed": confirmed}
    )
    await hass.async_block_till_done()
    assert result["type"] == ("create_entry" if confirmed else "menu"), result
    return result


async def _settings(hass, entry, user, age=None, *, confirmed=True):
    form = await _open(hass, entry, user, "home_status_settings")
    if age is None:
        age = form["data_schema"]({})["max_age_seconds"]
    return await _save(hass, form, {"max_age_seconds": age}, confirmed=confirmed)


async def _group(hass, entry, user, *, existing=False, confirmed=True, key="synthetic_room"):
    form = await _open(hass, entry, user, "home_status_group")
    form = await hass.config_entries.options.async_configure(
        form["flow_id"], {"record": key if existing else "new"}
    )
    values = {
        "key": key,
        "title": "Synthetic status group",
        "roles": ["owner", "parent"],
        "remove": False,
    }
    return await _save(hass, form, values, confirmed=confirmed)


async def _source(hass, entry, user, entity_id, mode, label, *, key="new", active_states=None):
    form = await _open(hass, entry, user, "home_status_source")
    form = await hass.config_entries.options.async_configure(form["flow_id"], {"record": key})
    assert form["step_id"] == "home_status_source_edit", form
    values = {
        "label": label,
        "entity_id": entity_id,
        "mode": mode,
        "roles": ["owner", "parent"],
        "active_states": active_states or [],
        "remove": False,
    }
    return await _save(hass, form, values)


async def _module(hass, entry, owner, enabled):
    from ha_options_menu import select_option

    flow = await hass.config_entries.options.async_init(
        entry.entry_id, context={"user_id": owner.id}
    )
    form = await select_option(hass, flow, "general")
    values = dict(form["data_schema"]({}))
    values["home_status"] = enabled
    result = await hass.config_entries.options.async_configure(form["flow_id"], values)
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()


async def _read(hass, entry, user, identifier, *, general=False, **query):
    from ha_digests_smoke import _message

    return await _message(
        hass,
        user,
        {
            "id": identifier,
            "type": "family_assistant/view" if general else "family_assistant/home_status",
            "entry_id": entry.entry_id,
            **query,
        },
    )


@contextmanager
def _reads(hass, module):
    """Instrument only a real synchronous projection, not unrelated HA tasks."""
    calls = []
    original_project = module.project
    original_get = type(hass.states).get

    def get(machine, entity_id):
        if machine is hass.states:
            calls.append(entity_id)
        return original_get(machine, entity_id)

    def project(*args, **kwargs):
        with patch.object(type(hass.states), "get", new=get):
            return original_project(*args, **kwargs)

    with patch.object(module, "project", new=project):
        yield calls


def _update(identifier, telegram_id, text):
    return {
        "update_id": identifier,
        "message": {
            "message_id": identifier,
            "from": {"id": telegram_id, "is_bot": False},
            "chat": {"id": telegram_id, "type": "private"},
            "text": text,
            "date": int(datetime.now(UTC).timestamp()),
        },
    }


async def verify_home_status(hass, owner):
    from ha_digests_smoke import _execute
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.assistant import plans
    from custom_components.family_assistant.home_status import api, observations
    from custom_components.family_assistant.telegram.context import reply_quote
    from custom_components.family_assistant.telegram.enrollment import Enrollment
    from custom_components.family_assistant.telegram.manager import TelegramManager

    initial = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner.id}
    )
    form = await hass.config_entries.flow.async_configure(
        initial["flow_id"],
        {
            "name": "Synthetic household status",
            "owner_name": "Owner",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"shopping": True, "tasks": True}
    )
    assert created["type"] == "create_entry", created
    entry = created["result"]
    await hass.async_block_till_done()
    child_user = await hass.auth.async_create_user("Synthetic status child")
    try:
        assert entry.state is ConfigEntryState.LOADED
        await entry.runtime_data.scheduler.stop()
        assert "home_status" not in entry.runtime_data.engine.snapshot()["settings"]["modules"]
        disabled = await _read(hass, entry, owner, 1)
        assert not disabled["success"] and disabled["error"]["code"] == "module_disabled", disabled
        empty_options = deepcopy(dict(entry.options))
        await _settings(hass, entry, owner)  # Default no-op does not introduce options.
        assert dict(entry.options) == empty_options
        await _settings(hass, entry, owner, 600, confirmed=False)
        assert dict(entry.options) == empty_options
        await _group(hass, entry, owner)
        exact = deepcopy(dict(entry.options))
        await _group(hass, entry, owner, existing=True)
        assert dict(entry.options) == exact
        registry = entity_registry.async_get(hass)
        entities = {}
        for metric, state, unit in (
            ("battery_soc", "80", "%"),
            ("battery_power", "-250", "W"),
            ("load_power", "100", "W"),
            ("pv_power", "950", "W"),
            ("grid_power", "1234.5", "W"),
        ):
            row = registry.async_get_or_create(
                "sensor",
                "family_assistant",
                "status-smoke-" + metric,
                suggested_object_id="synthetic_status_" + metric,
            )
            entities[metric] = row.entity_id
            hass.states.async_set(
                row.entity_id,
                state,
                {
                    "unit_of_measurement": unit,
                    "entity_picture": "PRIVATE_STATUS_URL_CANARY",
                    "access_token": "PRIVATE_STATUS_TOKEN_CANARY",
                },
            )
            await _source(
                hass, entry, owner, row.entity_id, "energy:" + metric, "Synthetic " + metric
            )
        active = registry.async_get_or_create(
            "input_boolean",
            "family_assistant",
            "status-smoke-active",
            suggested_object_id="synthetic_status_active",
        )
        hass.states.async_set(active.entity_id, "on")
        await _source(
            hass,
            entry,
            owner,
            active.entity_id,
            "active",
            "Synthetic reported activity",
            active_states=["on"],
        )
        await _source(
            hass,
            entry,
            owner,
            entities["load_power"],
            "group:synthetic_room",
            "Synthetic group reading",
        )
        exact = deepcopy(dict(entry.options))
        grid = next(
            row for row in entry.options["home_status"]["sources"] if row["metric"] == "grid_power"
        )
        await _source(
            hass,
            entry,
            owner,
            entities["grid_power"],
            "energy:grid_power",
            grid["label"],
            key=grid["id"],
        )
        await _settings(hass, entry, owner)
        assert dict(entry.options) == exact  # No reorder, epoch bump or descriptor cancellation.
        await _settings(hass, entry, owner, 600)
        assert entry.options["home_status"]["max_age_seconds"] == 600
        await _module(hass, entry, owner, True)
        runtime = entry.runtime_data
        await runtime.scheduler.stop()
        engine = runtime.engine
        before = engine.snapshot()
        with _reads(hass, api) as reads:
            current = await _read(hass, entry, owner, 2)
        assert current["success"] and len(current["result"]["energy"]) == 5, current
        assert set(reads) == {*entities.values(), active.entity_id}
        assert current["result"]["active"][0]["active"] is True
        assert current["result"]["groups"][0]["id"] == "synthetic_room"
        assert engine.snapshot() == before
        # The ordinary family view only publishes opaque revocation metadata.
        original_get = type(hass.states).get
        general_reads = []

        def get(machine, entity_id):
            if machine is hass.states and entity_id in {*entities.values(), active.entity_id}:
                general_reads.append(entity_id)
            return original_get(machine, entity_id)

        with patch.object(type(hass.states), "get", new=get):
            general = await _read(hass, entry, owner, 3, general=True)
        assert general["success"] and general_reads == [], general
        assert general["result"]["home_status_access"] == current["result"]["access_marker"]
        for canary in (
            *entities.values(),
            "PRIVATE_STATUS_URL_CANARY",
            "PRIVATE_STATUS_TOKEN_CANARY",
        ):
            assert canary not in repr(current) and canary not in repr(general)
            assert canary not in repr(engine.snapshot())
            assert canary not in repr(
                plans.messages(engine.view("owner"), "hello", (), datetime.now(UTC))
            )
        child = await _execute(
            hass,
            entry,
            owner,
            4,
            "members.save",
            {"name": "Synthetic child", "role": "child", "ha_user_id": child_user.id},
            "home-status-child",
        )
        assert child["success"], child
        with _reads(hass, api) as reads:
            child_view = await _read(hass, entry, child_user, 5)
        assert child_view["success"] and child_view["result"]["energy"] == [] and reads == [], (
            child_view
        )
        denied_user = SimpleNamespace(
            id=owner.id,
            is_active=True,
            permissions=SimpleNamespace(check_entity=lambda entity, policy: False),
        )
        with _reads(hass, observations) as reads:
            denied = observations.project(
                hass, entry, runtime, "owner", denied_user, datetime.now(UTC)
            )
        assert denied["energy"] == [] and reads == []
        report_time = hass.states.get(entities["grid_power"]).last_reported
        with patch.object(api.dt_util, "utcnow", return_value=report_time + timedelta(seconds=601)):
            stale = await _read(hass, entry, owner, 6, section="energy")
        assert all(
            row["value"] is None and row["quality"] == "stale" for row in stale["result"]["energy"]
        )
        hass.states.async_set(entities["load_power"], "4", {"unit_of_measurement": "kWh"})
        bad = await _read(hass, entry, owner, 7, section="energy")
        assert (
            next(row for row in bad["result"]["energy"] if row["metric"] == "load_power")["quality"]
            == "invalid_unit"
        )
        # Same entity_id, a different registry identity: no silent source replacement.
        old_id = entities["load_power"]
        registry.async_remove(old_id)
        hass.states.async_remove(old_id)
        replacement = registry.async_get_or_create(
            "sensor",
            "family_assistant",
            "status-smoke-replacement",
            suggested_object_id=old_id.split(".", 1)[1],
        )
        assert replacement.entity_id == old_id
        hass.states.async_set(old_id, "99999", {"unit_of_measurement": "W"})
        with _reads(hass, api) as reads:
            replaced = await _read(hass, entry, owner, 8)
        assert old_id not in reads and len(replaced["result"]["energy"]) == 4
        changed_access = await _read(hass, entry, owner, 9, general=True)
        assert (
            changed_access["result"]["home_status_access"]
            != general["result"]["home_status_access"]
        )
        enrollment = Enrollment(engine)
        now = datetime.now(UTC)
        issued = await enrollment.issue("owner", "member", now, "owner")
        assert await enrollment.capture(
            _update(1, 901001, "/start " + issued["code"])["message"], "synthetic_status_bot", now
        )
        assert (await enrollment.confirm("owner", issued["id"], now))["linked"]

        class Client:
            def __init__(self):
                self.calls = []

            async def call(self, method, payload):
                assert method == "sendMessage"
                self.calls.append(deepcopy(payload))
                return {"message_id": len(self.calls)}

        bot = {"id": 909001, "username": "synthetic_status_bot"}
        client = Client()
        manager = TelegramManager(hass, entry, runtime, client, bot)
        runtime.telegram = manager  # Real manager, no polling/background task is started.
        await manager.process(_update(101, 901001, "/energy"))
        pending = deepcopy(engine.snapshot()["outbox"])
        assert len(pending) == 1 and not client.calls
        assert "1234.5" not in repr(pending) and "Synthetic grid_power" not in repr(pending)
        exact_options = deepcopy(dict(entry.options))
        await _settings(hass, entry, owner)  # No-op must leave pending descriptor valid.
        assert dict(entry.options) == exact_options
        # Options lifecycle may rebuild adapters; persist/reload is intentionally tested.
        assert await hass.config_entries.async_reload(entry.entry_id)
        runtime = entry.runtime_data
        await runtime.scheduler.stop()
        engine = runtime.engine
        assert engine.snapshot()["outbox"] == pending
        client = Client()
        manager = TelegramManager(hass, entry, runtime, client, bot)
        runtime.telegram = manager
        hass.states.async_set(entities["grid_power"], "3456.75", {"unit_of_measurement": "W"})
        await manager.notifications.run(datetime.now(UTC))
        assert len(client.calls) == 1 and "3456.75 W" in client.calls[0]["text"]
        assert "1234.5" not in client.calls[0]["text"]
        stored = await Store(hass, 1, f"family_assistant.{entry.entry_id}").async_load()
        assert "3456.75" not in repr(stored) and "PRIVATE_STATUS" not in repr(stored)
        quoted = {
            "chat": {"id": 901001},
            "reply_to_message": {
                "message_id": 1,
                "from": {"id": bot["id"]},
                "text": client.calls[0]["text"],
            },
        }
        assert reply_quote(engine.snapshot(), quoted, bot) == ""
        await manager.process(_update(101, 901001, "/energy"))
        await manager.notifications.run(datetime.now(UTC))
        assert len(client.calls) == 1
        await manager.process(_update(102, 901001, "/home"))
        owner_member = engine.snapshot()["members"]["owner"]
        revoked = await _execute(
            hass,
            entry,
            owner,
            10,
            "members.save",
            {
                "id": "owner",
                "revision": owner_member["revision"],
                "name": "Owner revised",
                "role": "owner",
            },
            "home-status-epoch",
        )
        assert revoked["success"], revoked
        await manager.notifications.run(datetime.now(UTC))
        assert len(client.calls) == 1
        from ha_home_status_typed_smoke import verify_typed_home_status

        await verify_typed_home_status(hass, entry, owner, child_user)
        print(
            "PASS: actual HA home-status native Options/no-op/cancel, explicit registry/role/ACL "
            "reads, metadata-only family refresh, units/stale/replacement, private late Telegram "
            "descriptor/replay/revocation and Store reload"
        )
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


__all__ = ["verify_home_status"]
