"""Actual HA consent, technical Telegram worker failure, report API and Store reload."""

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime

from ha_options_menu import select_option


async def verify_developer_diagnostics(hass, owner):
    from ha_digests_smoke import _execute, _message, _view
    from ha_telegram_smoke import SyntheticTelegram

    from custom_components.family_assistant.assistant.chat_service import conversation_digest
    from custom_components.family_assistant.assistant.service import Assistant
    from custom_components.family_assistant.domain.developer_diagnostics import configuration
    from custom_components.family_assistant.telegram.manager import TelegramManager

    flow = await hass.config_entries.flow.async_init(
        "family_assistant", context={"source": "user", "user_id": owner.id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            "name": "Synthetic diagnostics household",
            "owner_name": "PRIVATE_OWNER_CANARY",
            "language": "en",
            "timezone": "UTC",
            "template": "manual",
        },
    )
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"conversation": True}
    )
    entry = created["result"]
    await hass.async_block_till_done()
    worker = None
    manager = None
    try:
        runtime = entry.runtime_data
        await runtime.scheduler.stop()
        engine = runtime.engine
        now = datetime.now(UTC)
        assert not configuration(engine.snapshot())["enabled"]
        options = await hass.config_entries.options.async_init(
            entry.entry_id, context={"user_id": owner.id}
        )
        form = await select_option(hass, options, "developer_diagnostics", technical=True)
        assert form["type"] == "form" and form["data_schema"]({}) == {"enabled": False}, form
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], {"enabled": True}
        )
        assert result["type"] == "abort" and result["reason"] == "developer_policy_saved", result
        assert configuration(engine.snapshot())["generation"] == 2

        def bind(ctx):
            ctx.state["members"]["owner"]["telegram_id"] = 770001
            ctx.state["memory"]["PRIVATE_MEMORY_CANARY"] = "PRIVATE_SECRET_CANARY"

        await engine.system_update("synthetic-diagnostic-bind", now, bind)

        class FailedCascade:
            calls = 0

            async def generate(self, *_args, **_kwargs):
                self.calls += 1
                raise TimeoutError("PRIVATE_PROVIDER_CANARY")

        cascade = FailedCascade()
        runtime.assistant = Assistant(engine, cascade)
        runtime.assistant_revision = "b" * 32
        runtime.assistant_config_digest = conversation_digest(
            dict(entry.options).get("conversation")
        )
        manager = TelegramManager(
            hass,
            entry,
            runtime,
            SyntheticTelegram(None, None),
            {"id": 770002, "username": "synthetic_diagnostics_bot"},
        )
        runtime.telegram = manager
        await manager.jobs.enqueue(
            "owner",
            "PRIVATE_MESSAGE_CANARY",
            "synthetic-diagnostic-job",
            now,
            (),
            bot_id=770002,
            chat_id=770001,
            reply_to=770003,
            quoted_text="PRIVATE_QUOTE_CANARY",
        )
        original_persist = engine._persist
        attempts = 0

        async def fail_first_completion(state):
            nonlocal attempts
            if state["assistant_jobs"]["synthetic-diagnostic-job"]["status"] == "complete":
                attempts += 1
                if attempts == 1:
                    raise OSError("PRIVATE_STORAGE_CANARY")
            await original_persist(state)

        engine._persist = fail_first_completion
        worker = asyncio.create_task(manager._conversations())
        async with asyncio.timeout(8):
            while (
                engine.snapshot()["assistant_jobs"]["synthetic-diagnostic-job"]["status"]
                == "pending"
            ):
                await asyncio.sleep(0.02)
        engine._persist = original_persist
        assert attempts == 2 and cascade.calls == 1
        assert (
            len([e for e in engine.snapshot()["outbox"].values() if e["key"] == "telegram_reply"])
            == 1
        )
        manager._stopped = True
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        worker = None
        runtime.telegram = None

        async def report(generation):
            return await _message(
                hass,
                owner,
                {
                    "id": 1,
                    "type": "family_assistant/developer_report",
                    "entry_id": entry.entry_id,
                    "expected_generation": generation,
                },
            )

        observed = await report(2)
        assert observed["success"], observed
        data = observed["result"]
        assert data["cases"] == [
            {
                "stage": "assistant_job",
                "code": "provider_timeout",
                "has_quote": True,
                "has_refs": False,
                "count": 1,
            }
        ]
        assert "PRIVATE_" not in json.dumps(data)
        view = await _view(hass, entry, owner, 2)
        assert view["result"]["developer_diagnostics"]["count"] == 1
        await _execute(
            hass,
            entry,
            owner,
            3,
            "settings.developer_policy",
            {"enabled": False, "expected_generation": 2},
            "synthetic-optout",
        )
        stale = await report(2)
        assert not stale["success"] and stale["error"]["code"] == "conflict", stale
        assert (await report(3))["result"] == data
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await entry.runtime_data.scheduler.stop()
        assert configuration(entry.runtime_data.engine.snapshot())["enabled"] is False
        assert (await report(3))["result"] == data
        print(
            "PASS: actual HA diagnostic consent, Telegram timeout + failed Store retry once, "
            "deidentified authenticated report, epoch fence and reload persistence"
        )
    finally:
        if manager is not None:
            manager._stopped = True
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        if entry.runtime_data is not None:
            entry.runtime_data.telegram = None
        await hass.config_entries.async_remove(entry.entry_id)
