"""Synthetic typed name repair through real HA entry storage, reload and routing."""

from copy import deepcopy
from datetime import UTC, datetime


async def verify_name_learning(hass, owner):
    from ha_digests_smoke import _execute, _view
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.assistant import plans
    from custom_components.family_assistant.assistant.provider import Cascade
    from custom_components.family_assistant.assistant.service import Assistant
    from custom_components.family_assistant.domain.validation import DomainError
    from custom_components.family_assistant.telegram.router import route

    flow = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner.id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Synthetic learned recipient",
            "owner_name": "Owner",
            "language": "ru",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"conversation": True, "tasks": True}
    )
    assert created["type"] == "create_entry", created
    entry = created["result"]
    await hass.async_block_till_done()
    child_user = await hass.auth.async_create_user("Synthetic learned recipient child")
    try:
        assert entry.state == ConfigEntryState.LOADED, entry.state
        await entry.runtime_data.scheduler.stop()
        added = await _execute(
            hass,
            entry,
            owner,
            1,
            "members.save",
            {
                "name": "Роман",
                "role": "child",
                "language": "ru",
                "ha_user_id": child_user.id,
            },
            "native-name-member",
        )
        assert added["success"], added
        child = added["result"]["id"]
        engine = entry.runtime_data.engine
        members_before = engine.snapshot()["members"]
        first = "поставь задачу Ропану - Купить хлеб"
        second = "поставь задачу Ропану - Помыть посуду"

        class Provider:
            calls = 0

            async def generate(self, messages, schema):
                self.calls += 1
                assert schema == plans.request_schema(first)
                assert first in messages[-1]["content"]
                return {
                    "kind": "commands",
                    "operations": [
                        {
                            "action": "tasks.create",
                            "payload": {"assignee": child, "title": "Купить хлеб"},
                        }
                    ],
                }

        provider = Provider()
        assistant = Assistant(engine, Cascade([provider], {}))
        now = datetime.now(UTC)
        reply = await route(
            engine, "owner", first, "native-name-first", now, fallback=assistant.respond
        )
        assert provider.calls == 1
        assert "Роман" in reply and "Купить хлеб" in reply
        snapshot = engine.snapshot()
        assert snapshot["members"] == members_before
        assert not snapshot["proposals"]
        assert len(snapshot["tasks"]) == 1
        task = next(iter(snapshot["tasks"].values()))
        assert task["assignee"] == child and task["title"] == "Купить хлеб"
        assert task["due_at"] is None and task["report_type"] == "text"
        rules = (await _view(hass, entry, owner, 2))["result"]["learned_phrases"]
        assert len(rules) == 1 and rules[0]["kind"] == "member_alias"
        assert rules[0]["effective"] and rules[0]["id"] in reply
        assert not (await _view(hass, entry, child_user, 3))["result"]["learned_phrases"]

        # Read the actual HA Store, not a copy passed into a fake Engine.
        stored = await Store(hass, 1, f"family_assistant.{entry.entry_id}").async_load()
        assert stored["tasks"] == snapshot["tasks"]
        assert stored["memory"]["phrases"] == snapshot["memory"]["phrases"]
        before_tasks = deepcopy(stored["tasks"])
        before_rules = deepcopy(stored["memory"]["phrases"])
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED, entry.state
        await entry.runtime_data.scheduler.stop()
        reloaded = entry.runtime_data.engine
        assert reloaded is not engine
        assert reloaded.snapshot()["tasks"] == before_tasks
        assert reloaded.snapshot()["memory"]["phrases"] == before_rules

        class OfflineProvider:
            calls = 0

            async def generate(self, *_args):
                self.calls += 1
                raise AssertionError("A durable learned recipient must not call a model")

        offline = OfflineProvider()
        offline_assistant = Assistant(reloaded, Cascade([offline], {}))
        second_reply = await route(
            reloaded,
            "owner",
            second,
            "native-name-second",
            datetime.now(UTC),
            fallback=offline_assistant.respond,
        )
        assert "Помыть посуду" in second_reply and offline.calls == 0
        after = reloaded.snapshot()
        assert len(after["tasks"]) == 2 and after["members"] == members_before
        assert after["memory"]["phrases"] == before_rules
        assert not after["proposals"]
        assert {record["assignee"] for record in after["tasks"].values()} == {child}
        for source, operation in [(first, "native-name-first"), (second, "native-name-second")]:
            await route(
                reloaded,
                "owner",
                source,
                operation,
                datetime.now(UTC),
                fallback=offline_assistant.respond,
            )
        assert len(reloaded.snapshot()["tasks"]) == 2 and offline.calls == 0

        # Another actor cannot borrow or remove this private correction.
        try:
            await route(reloaded, child, second, "native-name-child", datetime.now(UTC))
        except DomainError as err:
            assert err.code == "unknown_member", err.code
        else:
            raise AssertionError("Actor-private alias was used by another member")
        denied = await _execute(
            hass,
            entry,
            child_user,
            4,
            "conversation.forget",
            {"id": rules[0]["id"]},
            "native-name-child-forget",
        )
        assert not denied["success"] and denied["error"]["code"] == "forbidden", denied
        assert len(reloaded.snapshot()["tasks"]) == 2
        final_stored = await Store(hass, 1, f"family_assistant.{entry.entry_id}").async_load()
        assert final_stored["tasks"] == reloaded.snapshot()["tasks"]
        assert final_stored["memory"]["phrases"] == before_rules
        print(
            "PASS: actual HA typed task name repair, atomic task/alias Store persistence, "
            "entry reload, offline distinct task, exact replay and actor-private learning"
        )
    finally:
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.auth.async_remove_user(child_user)
