"""Queued private text never moves to another configured provider implicitly."""

import asyncio
from copy import deepcopy

import pytest

from custom_components.family_assistant.assistant.jobs import Jobs
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


async def prepare(engine, now):
    def setup(ctx):
        ctx.state["settings"]["modules"].append("conversation")
        ctx.state["members"]["parent"]["telegram_id"] = 421

    await engine.system_update("synthetic_job_setup", now, setup)


async def enqueue(jobs, now, operation="synthetic-provider-job"):
    return await jobs.enqueue(
        "parent",
        "Synthetic private question",
        operation,
        now,
        [],
        bot_id=422,
        chat_id=421,
        reply_to=423,
        quoted_text="Synthetic private quote",
    )


@pytest.mark.asyncio
async def test_same_provider_survives_store_reload_without_changing_destination(engine, store, now):
    await prepare(engine, now)
    jobs = Jobs(engine, provider_scope=lambda: "a" * 64)
    await enqueue(jobs, now)
    reloaded = Engine(deepcopy(store.value), store.save)
    resumed = Jobs(reloaded, provider_scope=lambda: "a" * 64)
    job = resumed.next(422)
    assert resumed.authorize(job, now) == "parent"
    assert job["provider_scope"] == "a" * 64
    await resumed.finish(job, "Synthetic response", now)
    assert reloaded.snapshot()["assistant_jobs"][job["id"]]["status"] == "complete"
    assert len(reloaded.snapshot()["outbox"]) == 1


@pytest.mark.asyncio
async def test_changed_provider_rejects_inference_and_cancels_without_private_reply(engine, now):
    await prepare(engine, now)
    marker = ["a" * 64]
    jobs = Jobs(engine, provider_scope=lambda: marker[0])
    await enqueue(jobs, now)
    job = jobs.next(422)
    marker[0] = "b" * 64
    with pytest.raises(DomainError, match="forbidden"):
        jobs.authorize(job, now)
    with pytest.raises(DomainError, match="forbidden"):
        await enqueue(jobs, now)
    await jobs.finish(job, "Must not be sent", now)
    state = engine.snapshot()
    assert state["assistant_jobs"][job["id"]]["status"] == "cancelled"
    assert state["outbox"] == {}


@pytest.mark.asyncio
async def test_legacy_unscoped_job_cannot_use_a_newly_scoped_adapter(engine, now):
    await prepare(engine, now)
    await enqueue(Jobs(engine), now)
    scoped = Jobs(engine, provider_scope=lambda: "a" * 64)
    job = scoped.next(422)
    with pytest.raises(DomainError, match="forbidden"):
        scoped.authorize(job, now)
    await scoped.finish(job, "Must not be sent", now)
    assert engine.snapshot()["outbox"] == {}
    assert engine.snapshot()["assistant_jobs"][job["id"]]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_unscoped_runner_cannot_adopt_a_scoped_job(engine, now):
    await prepare(engine, now)
    scoped = Jobs(engine, provider_scope=lambda: "a" * 64)
    await enqueue(scoped, now)
    unscoped = Jobs(engine)
    job = unscoped.next(422)
    with pytest.raises(DomainError, match="forbidden"):
        unscoped.authorize(job, now)
    with pytest.raises(DomainError, match="forbidden"):
        await enqueue(unscoped, now)
    await unscoped.finish(job, "Must not be sent", now)
    assert engine.snapshot()["outbox"] == {}
    assert engine.snapshot()["assistant_jobs"][job["id"]]["status"] == "cancelled"
    assert unscoped.next(422) is None


@pytest.mark.asyncio
async def test_provider_marker_is_part_of_immutable_selected_job(engine, now):
    await prepare(engine, now)
    jobs = Jobs(engine, provider_scope=lambda: "a" * 64)
    await enqueue(jobs, now)
    altered = jobs.next(422)
    altered["provider_scope"] = "b" * 64
    with pytest.raises(DomainError, match="forbidden"):
        jobs.authorize(altered, now)
    await jobs.finish(altered, "Must not be sent", now)
    assert engine.snapshot()["outbox"] == {}


@pytest.mark.parametrize("marker", [None, True, "", "a" * 63, "A" * 64, "z" * 64])
@pytest.mark.asyncio
async def test_invalid_marker_fails_before_storing_content(engine, now, marker):
    await prepare(engine, now)
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await enqueue(Jobs(engine, provider_scope=lambda: marker), now)
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_runtime_revocation_prevents_completion_delivery(engine, now):
    await prepare(engine, now)
    active = [True]

    def scope():
        if not active[0]:
            raise DomainError("forbidden")
        return "a" * 64

    jobs = Jobs(engine, provider_scope=scope)
    await enqueue(jobs, now)
    job = jobs.next(422)
    active[0] = False
    with pytest.raises(DomainError, match="forbidden"):
        jobs.authorize(job, now)
    await jobs.finish(job, "Must not be sent", now)
    assert engine.snapshot()["outbox"] == {}


@pytest.mark.asyncio
async def test_provider_change_while_waiting_for_engine_lock_prevents_enqueue(engine, now):
    await prepare(engine, now)
    marker = ["a" * 64]
    jobs = Jobs(engine, provider_scope=lambda: marker[0])
    await engine._lock.acquire()
    task = asyncio.create_task(enqueue(jobs, now))
    try:
        await asyncio.sleep(0)
        marker[0] = "b" * 64
    finally:
        engine._lock.release()
    with pytest.raises(DomainError, match="forbidden"):
        await task
    assert engine.snapshot()["assistant_jobs"] == {}
