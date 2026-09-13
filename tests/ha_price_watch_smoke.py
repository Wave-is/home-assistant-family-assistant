"""Real HA timer/Options/WS/Store price watching; synthetic transport, no merchant I/O."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from inspect import iscoroutinefunction
from threading import get_ident
from unittest.mock import patch


async def verify_price_watch(hass, owner):
    from ha_digests_smoke import _execute
    from ha_options_menu import select_option
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.core import HassJob
    from homeassistant.helpers import event as ha_event
    from homeassistant.helpers.storage import Store
    from homeassistant.util import dt as dt_util

    from custom_components.family_assistant import price_watch_fetcher as fetcher
    from custom_components.family_assistant.const import DOMAIN, SCHEMA_VERSION
    from custom_components.family_assistant.domain import price_watch as domain

    loop, thread = asyncio.get_running_loop(), get_ident()
    calls, registrations, timer_firings = [], [], []
    repeated = asyncio.Event()
    real_timer = ha_event.async_track_time_interval
    entry = None
    counter = 0
    pause_timer = False

    def short_timer(selected_hass, callback, interval):
        if not isinstance(getattr(callback, "__self__", None), fetcher.PriceWatchScheduler):
            return real_timer(selected_hass, callback, interval)
        assert selected_hass is hass and interval == timedelta(minutes=30)
        assert iscoroutinefunction(callback)
        assert HassJob(callback).job_type.name == "Coroutinefunction"
        registrations.append(callback)

        async def fired(now):
            if pause_timer:
                return
            timer_firings.append(now)
            await callback(now)

        # Keep HA's actual registration, timer and HassJob classification. Only
        # shorten time; a manually invoked startup poll cannot satisfy this test.
        return real_timer(hass, fired, timedelta(milliseconds=25))

    async def synthetic_fetch(url, *, scope_check):
        nonlocal pause_timer
        assert asyncio.get_running_loop() is loop and get_ident() == thread
        assert url == "https://merchant.example/synthetic-product"
        scope_check()
        calls.append(url)
        if len(calls) >= 2:
            pause_timer = True
            repeated.set()
        return fetcher.PriceFetchResult(
            price_text="100" if len(calls) == 1 else "90",
            currency="USD",
            availability="in_stock",
        )

    async def request(action, payload, *, user=owner, success=True):
        nonlocal counter
        counter += 1
        result = await _execute(
            hass, entry, user, counter, action, payload, f"price-native-{counter}"
        )
        assert result["success"] is success, result
        await hass.async_block_till_done()
        return result.get("result")

    async def options(enabled):
        form = await hass.config_entries.options.async_init(
            entry.entry_id, context={"user_id": owner.id}
        )
        form = await select_option(hass, form, "general")
        assert form["type"] == "form" and form["step_id"] == "general"
        values = {key.schema: key.default() for key in form["data_schema"].schema}
        values["price_watch"] = enabled
        result = await hass.config_entries.options.async_configure(form["flow_id"], values)
        assert result["type"] == "create_entry", result
        await hass.async_block_till_done()

    with (
        patch.object(ha_event, "async_track_time_interval", short_timer),
        patch.object(fetcher, "fetch_price", synthetic_fetch),
    ):
        try:
            flow = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "user", "user_id": owner.id}
            )
            flow = await hass.config_entries.flow.async_configure(
                flow["flow_id"],
                {
                    "name": "Synthetic price family",
                    "owner_name": "Synthetic parent",
                    "language": "en",
                    "timezone": "UTC",
                    "template": "manual",
                },
            )
            created = await hass.config_entries.flow.async_configure(
                flow["flow_id"], {"price_watch": True}
            )
            assert created["type"] == "create_entry", created
            entry = created["result"]
            await hass.async_block_till_done()
            assert entry.state is ConfigEntryState.LOADED
            await entry.runtime_data.scheduler.stop()
            watcher = await request(
                "price_watch.add",
                {
                    "url": "https://merchant.example/synthetic-product",
                    "name": "Synthetic product",
                },
            )
            await asyncio.wait_for(repeated.wait(), timeout=5)
            worker = entry.runtime_data.price_watcher
            if worker._task is not None:
                await worker._task
            assert len(timer_firings) >= 2 and len(registrations) == 1
            snapshot = entry.runtime_data.engine.snapshot()
            record = snapshot["price_watches"][watcher["id"]]
            assert record["price_text"] == "90" and len(record["history"]) >= 2
            notices = [
                event for event in snapshot["outbox"].values() if event["key"] == "price_watch_drop"
            ]
            assert len(notices) == 1 and domain.current_event(
                snapshot, notices[0], dt_util.utcnow()
            )
            # Pause only timer dispatch while checking a no-op Options callback.
            # A recreated worker's immediate startup request would still be seen.
            pause_timer = True
            if worker._task is not None:
                await worker._task
            before_calls = len(calls)
            await options(True)
            assert entry.runtime_data.price_watcher is worker
            assert len(registrations) == 1 and len(calls) == before_calls
            from custom_components.family_assistant.runtime import async_options_updated

            await async_options_updated(hass, entry)
            assert entry.runtime_data.price_watcher is worker and len(calls) == before_calls
            pause_timer = False
            child_user = await hass.auth.async_create_user("Synthetic price child")
            await request(
                "members.save",
                {
                    "name": "Synthetic child",
                    "role": "child",
                    "ha_user_id": child_user.id,
                },
            )
            await request(
                "price_watch.edit",
                {
                    "id": watcher["id"],
                    "revision": record["revision"],
                },
                user=child_user,
                success=False,
            )
            await options(False)
            assert entry.runtime_data.price_watcher is None
            stopped_calls = len(calls)
            assert worker._task is None and worker._unsub is None
            hass.async_run_hass_job(HassJob(registrations[0]), dt_util.utcnow())
            await hass.async_block_till_done()
            await asyncio.sleep(0.06)
            assert len(calls) == stopped_calls
            snapshot = entry.runtime_data.engine.snapshot()
            assert not domain.current_event(snapshot, notices[0], dt_util.utcnow())
            # Change the approving owner's epoch while off. Re-enabling cannot
            # silently reauthorize retained watches or historical notices.
            member = snapshot["members"]["owner"]
            await request(
                "members.save",
                {
                    "id": "owner",
                    "revision": member["revision"],
                    "role": "owner",
                    "name": "Reviewed synthetic parent",
                },
            )
            await options(True)
            await asyncio.sleep(0.06)
            assert len(calls) == stopped_calls
            engine = entry.runtime_data.engine
            assert engine.view("owner")["price_watches"][0]["policy_status"] == "review_required"
            current = engine.snapshot()["price_watches"][watcher["id"]]
            await request(
                "price_watch.edit", {"id": watcher["id"], "revision": current["revision"]}
            )
            await options(False)
            snapshot = deepcopy(entry.runtime_data.engine.snapshot())
            store = Store(hass, SCHEMA_VERSION, f"{DOMAIN}.{entry.entry_id}")
            assert (await store.async_load())["price_watches"] == snapshot["price_watches"]
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            await entry.runtime_data.scheduler.stop()
            assert entry.runtime_data.price_watcher is None
            assert (
                entry.runtime_data.engine.snapshot()["price_watches"] == snapshot["price_watches"]
            )
            assert (await store.async_load())["price_watch_epoch"] == snapshot["price_watch_epoch"]
        finally:
            if entry is not None and entry.state is ConfigEntryState.LOADED:
                assert await hass.config_entries.async_unload(entry.entry_id)
    print(
        "PASS: actual HA price timer/HassJob, Options disable/re-enable, exact consent, "
        "Store/reload and stop"
    )
