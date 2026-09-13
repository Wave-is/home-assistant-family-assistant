"""Native HA timer/HassJob dispatch; synthetic poll transport only, no portal I/O."""

import asyncio
from datetime import timedelta
from inspect import iscoroutinefunction
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import patch


async def verify_online_school_interval(hass):
    from homeassistant.core import HassJob
    from homeassistant.helpers import event as ha_event
    from homeassistant.util import dt as dt_util

    from custom_components.family_assistant.online_school import manager

    loop = asyncio.get_running_loop()
    thread = get_ident()
    calls = []
    repeated = asyncio.Event()
    registered = []
    runtime = SimpleNamespace(engine=object(), health={}, updated=lambda: None)
    entry = SimpleNamespace(options={"online_school": {"sources": {}}})
    worker = manager.SchoolManager(hass, entry, runtime)
    real_timer = ha_event.async_track_time_interval

    async def synthetic_poll(engine, options, now, **kwargs):
        assert asyncio.get_running_loop() is loop and get_ident() == thread
        assert engine is runtime.engine and options == worker.options
        calls.append(now)
        if len(calls) >= 2:
            repeated.set()

    def short_real_timer(selected_hass, callback, interval):
        assert selected_hass is hass and interval == timedelta(minutes=1)
        assert callback == worker._interval and iscoroutinefunction(callback)
        job = HassJob(callback)
        assert job.job_type.name == "Coroutinefunction", job.job_type
        registered.append(callback)
        # Only shorten the delay. Use HA's real timer registration and HassJob
        # dispatch; a direct request() or fake timer cannot satisfy this test.
        return real_timer(hass, callback, timedelta(milliseconds=20))

    with patch.object(manager, "poll", synthetic_poll):
        try:
            with patch.object(ha_event, "async_track_time_interval", short_real_timer):
                worker.start()
                worker.start()  # Starting twice must not leak a second interval.
            await asyncio.wait_for(repeated.wait(), timeout=5)
            assert len(registered) == 1 and len(calls) >= 2
            await worker.stop()
            stopped_calls = len(calls)
            assert worker.task is None and worker.unsubscribe is None
            # A previously queued HA job cannot revive the stopped manager.
            hass.async_run_hass_job(HassJob(registered[0]), dt_util.utcnow())
            await hass.async_block_till_done()
            await asyncio.sleep(0.05)
            assert len(calls) == stopped_calls and worker.task is None
            assert runtime.health == {}
        finally:
            await worker.stop()
    print("PASS: actual HA online-school interval/HassJob loop dispatch and stopped callback fence")
