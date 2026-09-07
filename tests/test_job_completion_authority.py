"""Slow assistant jobs recheck identity and time at durable completion."""

import asyncio
from datetime import timedelta

import pytest

from custom_components.family_assistant.assistant.jobs import Jobs
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


async def _enable_and_bind(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {**settings, "modules": [*settings["modules"], "conversation"]},
        "enable-job-completion-tests",
        now,
    )

    def bind(ctx):
        ctx.state["members"]["parent"]["telegram_id"] = 1001
        ctx.state["telegram"]["group_id"] = -10001

    await engine.system_update("bind-job-completion-parent", now, bind)


async def _configured(engine, now, clock):
    await _enable_and_bind(engine, now)
    jobs = Jobs(engine, clock=clock)
    await jobs.enqueue(
        "parent",
        "Explain the schedule",
        "job-completion-authority",
        now,
        (),
        bot_id=1000,
        chat_id=-10001,
        reply_to=7,
    )
    job = jobs.next(1000)
    assert job["member_revision"] == engine.snapshot()["members"]["parent"]["revision"]
    return jobs, job


def _model_results(state):
    return [event for event in state["outbox"].values() if event["key"] == "telegram_reply"]


@pytest.mark.asyncio
async def test_current_job_completes_once_with_delivery_authority(engine, now):
    clock = Clock(now)
    jobs, job = await _configured(engine, now, clock)
    assert jobs.authorize(job, now) == "parent"

    clock.now = now + timedelta(seconds=10)
    await jobs.finish(job, "Current answer", now)
    await jobs.finish(job, "Duplicate answer", now)

    state = engine.snapshot()
    stored = state["assistant_jobs"][job["id"]]
    assert stored["status"] == "complete"
    assert stored["finished_at"] == clock.now.isoformat()
    events = _model_results(state)
    assert len(events) == 1
    assert events[0]["data"] == {
        "text": "Current answer",
        "actor": "parent",
        "actor_revision": job["member_revision"],
        "bot_id": 1000,
        "chat_id": -10001,
        "reply_to": 7,
        "expires_at": job["expires_at"],
        "proposal_id": None,
        "refs": [],
    }


@pytest.mark.asyncio
async def test_expiry_during_backup_cancels_completion_without_reply(engine, now):
    clock = Clock(now)
    jobs, job = await _configured(engine, now, clock)
    token = await engine.async_begin_backup()
    finishing = asyncio.create_task(jobs.finish(job, "Expired answer", now))
    await asyncio.sleep(0)
    assert not finishing.done()
    assert engine.snapshot()["assistant_jobs"][job["id"]]["status"] == "pending"

    clock.now = now + timedelta(minutes=5)
    await engine.async_end_backup(token)
    await asyncio.wait_for(finishing, timeout=2)

    state = engine.snapshot()
    assert state["assistant_jobs"][job["id"]]["status"] == "cancelled"
    assert state["assistant_jobs"][job["id"]]["finished_at"] == clock.now.isoformat()
    assert _model_results(state) == []


class FinishGateEngine(Engine):
    """Pause a returned model response before its fresh completion transaction."""

    def __init__(self, state, persist):
        super().__init__(state, persist)
        self.finish_entered = asyncio.Event()
        self.release_finish = asyncio.Event()

    async def background_update(self, kind, now, change):
        if kind == "assistant_finished":
            self.finish_entered.set()
            await self.release_finish.wait()
        return await super().background_update(kind, now, change)


class EnqueueGateEngine(Engine):
    """Pause after enqueue captures its authority and before the save callback."""

    def __init__(self, state, persist):
        super().__init__(state, persist)
        self.enqueue_entered = asyncio.Event()
        self.release_enqueue = asyncio.Event()

    async def system_update(self, kind, now, change):
        if kind == "assistant_queued":
            self.enqueue_entered.set()
            await self.release_enqueue.wait()
        return await super().system_update(kind, now, change)


@pytest.mark.asyncio
async def test_enqueue_rejects_identity_rebound_before_serialized_save(engine, store, now):
    await _enable_and_bind(engine, now)
    current = EnqueueGateEngine(engine.snapshot(), store.save)
    jobs = Jobs(current)
    enqueue = asyncio.create_task(
        jobs.enqueue(
            "parent",
            "Original identity request",
            "rebound-enqueue",
            now,
            (),
            bot_id=1000,
            chat_id=-10001,
            reply_to=8,
        )
    )
    await asyncio.wait_for(current.enqueue_entered.wait(), timeout=2)

    def rebind(ctx):
        member = ctx.state["members"]["parent"]
        member.update(telegram_id=1002, revision=member["revision"] + 1)

    await Engine.system_update(current, "rebind-before-enqueue", now, rebind)
    current.release_enqueue.set()
    with pytest.raises(DomainError, match="forbidden"):
        await asyncio.wait_for(enqueue, timeout=2)
    assert "rebound-enqueue" not in current.snapshot()["assistant_jobs"]


@pytest.mark.asyncio
async def test_member_revocation_before_post_backup_commit_cancels_reply(engine, store, now):
    clock = Clock(now)
    _seeded_jobs, job = await _configured(engine, now, clock)
    current = FinishGateEngine(engine.snapshot(), store.save)
    jobs = Jobs(current, clock=clock)
    token = await current.async_begin_backup()
    finishing = asyncio.create_task(jobs.finish(job, "Stale answer", now))
    await asyncio.wait_for(current.finish_entered.wait(), timeout=2)
    assert jobs.authorize(job, now) == "parent"

    await current.async_end_backup(token)

    def revoke(ctx):
        member = ctx.state["members"]["parent"]
        member.update(active=False, revision=member["revision"] + 1)

    await current.system_update("revoke-job-member", now, revoke)
    current.release_finish.set()
    await asyncio.wait_for(finishing, timeout=2)

    state = current.snapshot()
    assert state["assistant_jobs"][job["id"]]["status"] == "cancelled"
    assert _model_results(state) == []


@pytest.mark.asyncio
async def test_failed_completion_save_retries_exactly_once(engine, store, now):
    clock = Clock(now)
    jobs, job = await _configured(engine, now, clock)
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError, match="synthetic disk error"):
        await jobs.finish(job, "Persist exactly once", now)
    assert engine.snapshot() == before

    store.fail = False
    await jobs.finish(job, "Persist exactly once", now)
    await jobs.finish(job, "Do not replace", now)
    state = engine.snapshot()
    assert state["assistant_jobs"][job["id"]]["status"] == "complete"
    events = _model_results(state)
    assert len(events) == 1
    assert events[0]["data"]["text"] == "Persist exactly once"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["epoch", "role", "binding", "module", "expiry"])
async def test_authorize_rechecks_current_job_authority(engine, now, change):
    clock = Clock(now)
    jobs, job = await _configured(engine, now, clock)
    if change == "expiry":
        clock.now = now + timedelta(minutes=5)
    else:

        def mutate(ctx):
            member = ctx.state["members"]["parent"]
            if change == "epoch":
                member["revision"] += 1
            elif change == "role":
                member.update(role="child", revision=member["revision"] + 1)
            elif change == "binding":
                member.update(telegram_id=1002, revision=member["revision"] + 1)
            else:
                ctx.state["settings"]["modules"].remove("conversation")

        await engine.system_update("change-job-authority", now, mutate)

    code = (
        "assistant_job_expired"
        if change == "expiry"
        else ("module_disabled" if change == "module" else "forbidden")
    )
    with pytest.raises(DomainError, match=code):
        jobs.authorize(job, now)


@pytest.mark.asyncio
async def test_legacy_pending_job_without_member_epoch_fails_closed(engine, store, now):
    clock = Clock(now)
    _jobs, job = await _configured(engine, now, clock)
    state = engine.snapshot()
    del state["assistant_jobs"][job["id"]]["member_revision"]
    legacy = Engine(state, store.save)
    selected = legacy.snapshot()["assistant_jobs"][job["id"]]
    jobs = Jobs(legacy, clock=clock)

    with pytest.raises(DomainError, match="forbidden"):
        jobs.authorize(selected, now)
    await jobs.finish(selected, "Must not be sent", now)
    state = legacy.snapshot()
    assert state["assistant_jobs"][job["id"]]["status"] == "cancelled"
    assert _model_results(state) == []
