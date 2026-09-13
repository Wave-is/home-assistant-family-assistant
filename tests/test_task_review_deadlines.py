"""Reviewer reminders use real Engine transactions and the durable delivery worker."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_task_media import available
from test_task_media import submit as submit_photo

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.task_delivery import current_task_event
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.notifications import DeliveryError, Notifications
from custom_components.family_assistant.telegram.messages import MESSAGES, render, targets

KEY = "task_review_overdue"


def events(engine):
    return [e for e in engine.snapshot()["outbox"].values() if e["key"] == KEY]


async def create(engine, now, **policy):
    return await engine.execute(
        "parent",
        "tasks.create",
        {"title": "Synthetic report", "assignee": "child", **policy},
        "new-task",
        now,
    )


async def action(engine, now, task, name, *, operation=None, **extra):
    current = engine.snapshot()["tasks"][task["id"]]
    return await engine.execute(
        "child" if name == "submit" else "parent",
        f"tasks.{name}",
        {"id": task["id"], "revision": current["revision"], **extra},
        operation or name,
        now,
    )


async def submitted(engine, now, **extra):
    task = await create(engine, now, review_minutes=60, **extra)
    return await action(engine, now, task, "submit", report="Finished")


async def channels(engine, now):
    def change(ctx):
        ctx.state["telegram"]["group_id"] = -10001
        for member, chat in (("owner", 1001), ("parent", 1002), ("child", 1003), ("adult", 1004)):
            ctx.state["members"][member]["telegram_id"] = chat

    await engine.system_update("synthetic-channels", now, change)


def only_review(event, state):
    return targets(event, state) if event["key"] == KEY else []


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", [{}, {"review_minutes": 0}])
async def test_off_default_preserves_old_shape_and_never_schedules(engine, now, policy):
    task = await create(engine, now, **policy)
    assert ("review_minutes" in task) == bool(policy)
    assert task["deadline_policy"] == {"reminder_minutes": 60, "grace_minutes": 30, "penalty": 0}
    await action(engine, now, task, "submit", report="Finished")
    await engine.tick(now + timedelta(days=30))
    assert not events(engine)
    assert "review_deadline" not in engine.snapshot()["tasks"][task["id"]]


@pytest.mark.asyncio
async def test_legacy_submitted_record_is_not_retroactively_scheduled(engine, store, now):
    task = await create(engine, now)
    await action(engine, now, task, "submit", report="Legacy report")
    state = engine.snapshot()
    state["tasks"][task["id"]]["review_minutes"] = 60
    restarted = Engine(state, store.save)
    await restarted.tick(now + timedelta(days=5))
    assert not events(restarted)


@pytest.mark.asyncio
async def test_due_independent_restart_catchup_replay_and_private_delivery_once(engine, store, now):
    await channels(engine, now)
    task = await submitted(engine, now)
    assert task["due_at"] is None
    assert task["review_due_at"] == (now + timedelta(hours=1)).isoformat()
    assert not events(engine)
    await engine.tick(now + timedelta(minutes=59))
    assert not events(engine)
    restarted = Engine(store.value, store.save)
    await restarted.tick(now + timedelta(days=3))
    event = events(restarted)[0]
    assert event["recipient"] == "parents"
    assert current_task_event(restarted.snapshot(), event)
    assert {target["id"] for target in targets(event, restarted.snapshot())} == {1001, 1002}
    calls = []

    async def send(event, target):
        calls.append((event["id"], target["id"]))
        return str(len(calls))

    assert await Notifications(restarted, only_review, send).run(now + timedelta(days=3)) == 2
    restarted = Engine(store.value, store.save)
    await restarted.tick(now + timedelta(days=6))
    assert await Notifications(restarted, only_review, send).run(now + timedelta(days=6)) == 0
    assert len(events(restarted)) == 1
    assert len(calls) == 2
    assert not restarted.snapshot()["court"]


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertain", [False, True])
async def test_outage_retries_same_event_but_uncertain_send_is_never_repeated(
    engine, store, now, uncertain
):
    await channels(engine, now)
    await submitted(engine, now)
    await engine.tick(now + timedelta(hours=1))
    calls = []

    async def send(event, target):
        calls.append((event["id"], target["id"]))
        if len(calls) == 1:
            if uncertain:
                raise TimeoutError()
            raise DeliveryError("connection_failed", retryable=True)
        return "receipt"

    worker = Notifications(engine, lambda event, state: only_review(event, state)[:1], send)
    await worker.run(now + timedelta(hours=1), limit=1)
    restarted = Engine(store.value, store.save)
    await restarted.tick(now + timedelta(days=2))
    worker = Notifications(restarted, lambda event, state: only_review(event, state)[:1], send)
    await worker.run(now + timedelta(days=2))
    assert len(events(restarted)) == 1
    assert len(calls) == (1 if uncertain else 2)
    assert all(call == calls[0] for call in calls)
    assert events(restarted)[0]["state"] == ("uncertain" if uncertain else "sent")


@pytest.mark.asyncio
async def test_submitted_child_never_penalized_even_with_enabled_due_penalty(engine, now):
    settings = engine.snapshot()["settings"]
    await engine.execute(
        "owner",
        "settings.save",
        {
            **{key: settings[key] for key in ("name", "language", "modules")},
            "automatic_penalties": True,
        },
        "enable-penalties",
        now,
    )
    task = await submitted(engine, now, penalty=-1, due_at=(now + timedelta(minutes=5)).isoformat())
    await engine.tick(now + timedelta(days=5))
    assert len(events(engine)) == 1
    assert not engine.snapshot()["court"]
    assert not engine.snapshot()["incidents"]
    assert engine.snapshot()["tasks"][task["id"]]["status"] == "submitted"


@pytest.mark.asyncio
async def test_same_clock_request_changes_and_resubmit_invalidates_old_generation(engine, now):
    task = await submitted(engine, now)
    await engine.tick(now + timedelta(hours=1))
    first = events(engine)[0]
    await action(engine, now, task, "request_changes", note="Add detail")
    assert events(engine)[0]["state"] == "superseded"
    task = await action(engine, now, task, "submit", operation="second-report", report="Updated")
    assert engine.snapshot()["tasks"][task["id"]]["review_generation"] == 2
    assert not current_task_event(engine.snapshot(), first)
    await engine.tick(now + timedelta(hours=1))
    second = events(engine)[1]
    assert second["id"] != first["id"]
    assert second["data"]["review_generation"] == 2
    assert current_task_event(engine.snapshot(), second)
    await engine.tick(now + timedelta(days=2))
    assert len(events(engine)) == 2


@pytest.mark.asyncio
async def test_submit_exact_retry_and_failed_persistence_are_atomic(engine, store, now):
    task = await create(engine, now, review_minutes=30)
    payload = {"id": task["id"], "revision": task["revision"], "report": "Done"}
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.execute("child", "tasks.submit", payload, "report-once", now)
    assert engine.snapshot() == before
    store.fail = False
    result = await engine.execute("child", "tasks.submit", payload, "report-once", now)
    assert await engine.execute("child", "tasks.submit", payload, "report-once", now) == result
    assert engine.snapshot()["tasks"][task["id"]]["review_generation"] == 1
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await engine.tick(now + timedelta(hours=1))
    assert engine.snapshot() == before
    store.fail = False
    await engine.tick(now + timedelta(hours=1))
    assert len(events(engine)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["complete", "cancel", "archive", "request_changes"])
@pytest.mark.parametrize("queued", [False, True])
async def test_terminal_or_return_revokes_scheduled_and_queued_reminders(engine, now, name, queued):
    task = await submitted(engine, now)
    if queued:
        await engine.tick(now + timedelta(hours=1))
    await action(
        engine, now, task, name, **({"note": "Try again"} if name == "request_changes" else {})
    )
    await engine.tick(now + timedelta(days=2))
    assert all(event["state"] == "superseded" for event in events(engine))
    assert engine.snapshot()["tasks"][task["id"]]["review_deadline"]["state"] == "revoked"


@pytest.mark.asyncio
@pytest.mark.parametrize("queued", [False, True])
async def test_module_disable_enable_before_tick_cannot_revive_old_report(engine, now, queued):
    task = await submitted(engine, now)
    if queued:
        await engine.tick(now + timedelta(hours=1))
    for enabled in (False, True):
        await engine.execute(
            "owner",
            "settings.module_toggle",
            {
                "revision": engine.snapshot().get("settings_revision", 1),
                "module": "tasks",
                "enabled": enabled,
            },
            f"tasks-{enabled}",
            now,
        )
    await engine.tick(now + timedelta(days=2))
    assert all(event["state"] == "superseded" for event in events(engine))
    await action(engine, now, task, "request_changes", note="New report")
    await action(engine, now, task, "submit", operation="fresh-after-enable", report="New")
    await engine.tick(now + timedelta(days=2))
    assert events(engine)[-1]["state"] == "pending"
    assert events(engine)[-1]["data"]["review_generation"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "member,change",
    [
        ("child", {"active": False}),
        ("child", {"name": "Changed child"}),
        ("parent", {"role": "adult"}),
        ("parent", {"name": "Changed reviewer"}),
        ("adult", {"role": "parent"}),
    ],
)
async def test_member_changes_revoke_before_transport_without_a_clock_tick(
    engine, now, member, change
):
    await channels(engine, now)
    await submitted(engine, now)
    await engine.tick(now + timedelta(hours=1))
    original = engine.snapshot()["members"][member]
    await engine.execute(
        "owner",
        "members.save",
        {
            **{key: original[key] for key in ("id", "name", "role", "revision")},
            **change,
        },
        "change-member",
        now,
    )
    calls = []

    async def send(event, target):
        calls.append(target)
        return "sent"

    assert targets(events(engine)[0], engine.snapshot()) == []
    await Notifications(engine, only_review, send).run(now + timedelta(hours=1))
    assert not calls
    assert events(engine)[0]["state"] == "superseded"


@pytest.mark.asyncio
async def test_revocation_between_claim_and_send_cancels_delivery(engine, now):
    await channels(engine, now)
    task = await submitted(engine, now)
    await engine.tick(now + timedelta(hours=1))
    calls = []

    async def send(event, target):
        calls.append(target)

    worker = Notifications(engine, only_review, send)
    claimed = await engine.system_update("claim", now, worker._claim)
    assert claimed is not None
    await action(engine, now, task, "complete")
    assert await worker._authorize_dispatch(claimed[0]["id"], claimed[1]["id"], now) is None
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, False, None, "60", 1.5, -1, 10081])
async def test_review_interval_strictly_validates_and_rolls_back(engine, now, value):
    before = engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await create(engine, now, review_minutes=value)
    assert engine.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["child", "adult"])
@pytest.mark.parametrize("value", [0, 60])
async def test_nonparents_cannot_set_review_policy_even_for_own_task(engine, now, actor, value):
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            actor,
            "tasks.create",
            {
                "title": "Own work",
                "assignee": actor,
                "review_minutes": value,
            },
            "denied-create",
            now,
        )
    task = await engine.execute(
        actor,
        "tasks.create",
        {
            "title": "Own work",
            "assignee": actor,
        },
        "own-create",
        now,
    )
    before = engine.snapshot()
    with pytest.raises(DomainError, match="forbidden"):
        await engine.execute(
            actor,
            "tasks.revise",
            {
                "id": task["id"],
                "revision": task["revision"],
                "review_minutes": value,
            },
            "denied-revise",
            now,
        )
    assert engine.snapshot() == before


@pytest.mark.asyncio
async def test_parent_can_enable_edit_disable_but_personal_never_accepts_policy(engine, now):
    task = await create(engine, now)
    task = await action(engine, now, task, "revise", review_minutes=10080)
    assert task["review_minutes"] == 10080
    task = await action(engine, now, task, "revise", operation="disable-review", review_minutes=0)
    task = await action(engine, now, task, "submit", report="Finished")
    assert "review_deadline" not in task
    with pytest.raises(DomainError, match="invalid_field"):
        await engine.execute(
            "parent",
            "tasks.create",
            {
                "title": "Private reminder",
                "assignee": "parent",
                "personal": True,
                "review_minutes": 0,
            },
            "personal-denied",
            now,
        )


@pytest.mark.asyncio
async def test_private_photo_generation_and_exact_source_cannot_be_replaced(engine, now):
    task = await create(engine, now, review_minutes=60, report_type="photo")
    await engine.system_update(
        "synthetic-private-source",
        now,
        lambda ctx: ctx.state["tasks"][task["id"]].update(
            delivery_scope="private",
            source={"kind": "maintenance_fault", "fault_id": "F-SYNTHETIC"},
        ),
    )
    attachment = await available(engine, now, task)
    await submit_photo(engine, now, task, attachment)
    for actor in ("child", "parent"):
        visible = engine.view(actor, now=now)["tasks"][0]
        assert "review_deadline" not in visible
        assert "review_generation" not in visible
        assert visible["review_due_at"] == (now + timedelta(hours=1)).isoformat()
        assert visible["review_status"] == "scheduled"
    assert "source" not in engine.view("child", now=now)["tasks"][0]
    await engine.tick(now + timedelta(hours=1))
    state = engine.snapshot()
    event = events(engine)[0]
    assert current_task_event(state, event)
    assert state["tasks"][task["id"]]["review_deadline"]["report_generation"] == 1
    for changes in (
        {"source": {"kind": "maintenance_fault", "fault_id": "F-OTHER"}},
        {"report_generation": 2},
        {"report_media": []},
        {"delivery_scope": "personal"},
        {"review_minutes": 0},
        {"review_generation": 2},
    ):
        changed = deepcopy(state)
        changed["tasks"][task["id"]].update(changes)
        assert not current_task_event(changed, event)
    for changes in ({"review_generation": 2}, {"submission_id": "other"}, {"review_due_at": "bad"}):
        stale = deepcopy(event)
        stale["data"].update(changes)
        assert not current_task_event(state, stale)


@pytest.mark.asyncio
async def test_all_localized_reminders_render_without_child_blame(engine, now):
    await channels(engine, now)
    await submitted(engine, now)
    await engine.tick(now + timedelta(hours=1))
    event = events(engine)[0]
    for language in ("en", "ru", "uk"):
        assert MESSAGES[language].keys() == MESSAGES["en"].keys()
        message = render(event, {"id": 1001, "language": language}, engine.snapshot())
        assert "Synthetic report" in message["text"]
        assert event["data"]["id"] in message["text"]
