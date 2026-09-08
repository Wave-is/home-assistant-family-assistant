"""Actual isolated HA Store/HTTP/Options/reload acceptance of a whole shadow copy."""

from datetime import UTC, datetime
from types import MappingProxyType

from ha_legacy_archive_smoke import synthetic_source
from ha_presence_smoke import _request


async def verify_shadow(hass, owner_user):
    from homeassistant.config_entries import ConfigEntry, ConfigEntryState
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.domain.engine import new_state
    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.migration.review import read_store_pair
    from custom_components.family_assistant.migration.shadow import build_shadow_candidate
    from custom_components.family_assistant.runtime import async_options_updated, safe_diagnostics

    # Prepare the Store before the first setup of this new entry. Reusing a
    # previously active entry would retain its old entity registry records.
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="family_assistant",
        source="user",
        title="Synthetic migration shadow",
        unique_id=None,
        data={"owner_user_id": owner_user.id, "owner_name": "Synthetic owner", "modules": []},
        options={
            key: {"enabled": True} for key in ("telegram", "mikrotik", "conversation", "recipes")
        },
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    try:
        assistant, court, mapping, members = synthetic_source(lifecycle=True)
        child = await hass.auth.async_create_user("Synthetic shadow child")
        target = new_state(owner_user.id, entry.title, modules=[])
        for member in members.values():
            member.update(
                language="en",
                aliases=[],
                ha_user_id=owner_user.id if member["role"] == "owner" else child.id,
            )
        target["members"] = members
        review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
        policy = {
            "schema": 1,
            "revision": 1,
            "source_review_fingerprint": review.summary()["fingerprint"],
            "reviewers": {
                key: [row["reviewer"]]
                for key, row in review.private_data()[0]["ledger"]["tasks"].items()
                if row.get("requires_report") is True
            },
        }
        candidate = build_shadow_candidate(
            review, target, reviewer_policy=policy, prepared_at=datetime(2026, 9, 8, tzinfo=UTC)
        )
        expected = candidate.private_state()
        store = Store(hass, 1, f"family_assistant.{entry.entry_id}")
        await store.async_save(expected)
        await hass.config_entries.async_add(entry)
        for turn in range(2):
            if turn:
                assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state == ConfigEntryState.LOADED
            runtime = entry.runtime_data
            assert runtime.engine.shadow_mode
            from homeassistant.helpers import entity_registry

            registry = entity_registry.async_get(hass)
            assert not entity_registry.async_entries_for_config_entry(registry, entry.entry_id)
            assert all(
                getattr(runtime, key) is None
                for key in (
                    "scheduler",
                    "telegram",
                    "network",
                    "assistant",
                    "chat",
                    "articles",
                    "recipes",
                    "media_task",
                    "media_unsub",
                )
            )
            response = await _request(hass, entry, owner_user, 8801)
            assert (
                response["success"]
                and response["result"]["read_only"] == "migration_shadow_read_only"
            )
            assert len(response["result"]["tasks"]) == 3
            denied = await _request(hass, entry, child, 8802)
            assert not denied["success"] and denied["error"]["code"] == "forbidden"
            mutation = await _request(
                hass, entry, owner_user, 8803, "settings.update", {"modules": ["tasks"]}
            )
            assert (
                not mutation["success"]
                and mutation["error"]["code"] == "migration_shadow_read_only"
            )
            options = await hass.config_entries.options.async_init(
                entry.entry_id, context={"user_id": owner_user.id}
            )
            options = await hass.config_entries.options.async_configure(
                options["flow_id"], {"next_step_id": "telegram"}
            )
            assert options["type"] == "abort" and options["reason"] == "migration_shadow_read_only"
            await async_options_updated(hass, entry)
            assert runtime.telegram is None and runtime.network is None and runtime.recipes is None
            try:
                await runtime.engine.tick(datetime(2027, 1, 1, tzinfo=UTC))
                raise AssertionError("Shadow clock was writable")
            except DomainError as error:
                assert error.code == "migration_shadow_read_only"
            assert "migration_archive" not in safe_diagnostics(runtime)
            assert runtime.engine.snapshot() == expected
            assert await store.async_load() == expected
            assert await hass.config_entries.async_unload(entry.entry_id)
        print(
            "PASS: whole shadow native Store/reload, owner-only authenticated view, "
            "command/Options denial, zero providers/scheduler and unchanged bytes"
        )
    finally:
        await hass.config_entries.async_remove(entry.entry_id)


async def main():
    """Focused offline entry acceptance, without starting an ordinary household."""
    import shutil
    import tempfile
    from pathlib import Path

    from homeassistant import bootstrap, loader
    from homeassistant.auth.const import GROUP_ID_ADMIN
    from homeassistant.core import HomeAssistant
    from homeassistant.setup import async_setup_component

    assert Path("/.dockerenv").is_file()
    assert {path.name for path in Path("/sys/class/net").iterdir() if path.is_dir()} == {"lo"}
    assert "CapEff:\t0000000000000000" in Path("/proc/self/status").read_text()
    with tempfile.TemporaryDirectory(prefix="synthetic-shadow-") as directory:
        shutil.copytree(
            Path(__file__).resolve().parents[1] / "custom_components",
            Path(directory) / "custom_components",
        )
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        try:
            assert await bootstrap.async_from_config_dict(
                {
                    "homeassistant": {
                        "latitude": 0,
                        "longitude": 0,
                        "elevation": 0,
                        "time_zone": "UTC",
                        "unit_system": "metric",
                        "country": "GB",
                    },
                    "http": {"server_host": "127.0.0.1", "server_port": 8123},
                },
                hass,
            )
            await async_setup_component(hass, "websocket_api", {})
            await hass.async_start()
            owner = await hass.auth.async_create_user("Synthetic owner", group_ids=[GROUP_ID_ADMIN])
            await verify_shadow(hass, owner)
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
