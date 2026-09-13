"""Native Options implementation + real Engine contracts; fictional school only."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_online_school_domain import acknowledge, apply, reconcile, snapshot
from test_online_school_options import (
    SOURCE,
    account_values,
    begin,
    student_values,
    visible_form,
)
from test_online_school_options import (
    config_flow as config_flow,
)
from test_online_school_options import (
    harness as harness,
)

from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.online_school import delivery


def source(harness):
    return harness.runtime.engine.snapshot()["school"]["online"]["sources"][SOURCE]


def notices(harness):
    return [
        event
        for event in harness.runtime.engine.snapshot()["outbox"].values()
        if event["key"] == delivery.KEY
    ]


async def prepared(harness, now):
    harness.change_state(
        lambda state: [
            state["members"][member].update(telegram_id=987654001 + index)
            for index, member in enumerate(("owner", "parent", "child"))
        ]
    )
    config = harness.entry.options["online_school"]["sources"][SOURCE]
    config["rules"] = {
        "enabled": True,
        "notify_changes": True,
        "homework_time": "07:30",
        "recipients": ["child", "owner"],
    }
    engine = harness.runtime.engine
    await reconcile(engine, now, harness.entry.options)
    value = snapshot(student_id="101", timezone="UTC")
    await apply(engine, source(harness), now, value)
    await acknowledge(engine, source(harness), now, value=value)
    await engine.system_update(
        "school-edit-notice", now, lambda ctx: delivery.enqueue(ctx, SOURCE, [])
    )
    assert len(notices(harness)) == 2
    assert all(delivery.current(engine.snapshot(), event, now) for event in notices(harness))
    return deepcopy(source(harness))


async def edit(harness, *, account=None, student=None):
    await begin(harness)
    form = await harness.flow.async_step_online_school_account(account_values(**(account or {})))
    assert form["step_id"] == "online_school_student", form
    result = await harness.flow.async_step_online_school_student(form["data_schema"](student or {}))
    assert result["type"] == "create_entry", result
    return result["data"]


async def test_verified_edit_uses_current_defaults_and_noop_needs_no_portal(harness, now, store):
    before = await prepared(harness, now)
    options = deepcopy(harness.entry.options)
    writes = store.calls
    harness.discovery_error = "online_school_timeout"
    account = await begin(harness)
    assert '"refresh_students": {"default": false' in visible_form(account)
    form = await harness.flow.async_step_online_school_account(account_values())
    assert form["data_schema"]({}) == {
        "student_id": "101",
        "notifications": True,
        "notify_changes": True,
        "homework_time": "07:30",
        "recipients": ["child", "owner"],
    }
    result = await harness.flow.async_step_online_school_student(form["data_schema"]({}))
    assert result["data"] == options
    assert source(harness) == before and store.calls == writes
    assert harness.clients == []


@pytest.mark.parametrize(
    ("account", "student"),
    [
        ({"label": "Renamed school"}, {}),
        ({}, {"notifications": False}),
        ({}, {"notify_changes": False}),
        ({}, {"homework_time": "06:00"}),
        ({}, {"recipients": ["owner", "parent"]}),
    ],
)
async def test_policy_edits_keep_facts_acks_and_markers_but_revoke_old_notices(
    harness, now, store, account, student
):
    before = await prepared(harness, now)
    options = await edit(harness, account=account, student=student)
    record = options["online_school"]["sources"][SOURCE]
    assert record["generation"] == before["generation"]
    assert record["policy_update"]["source_revision"] == before["revision"]
    assert harness.clients == []
    harness.entry.options = options
    outcome = await reconcile(harness.runtime.engine, now, options)
    assert len(outcome["sources"]) == 1
    after = source(harness)
    assert after["revision"] == before["revision"] + 1
    for key in (
        "snapshot",
        "snapshot_hash",
        "last_attempt",
        "last_success",
        "acknowledgements",
        "changes",
        "change_sequence",
        "notification_markers",
        "generation",
    ):
        assert after[key] == before[key], key
    assert all(
        not delivery.current(harness.runtime.engine.snapshot(), event, now)
        for event in notices(harness)
    )
    # Rehydrate the actual persisted Store shape, then poll the same preparation day.
    harness.runtime.engine = Engine(deepcopy(store.value), store.save)
    await harness.runtime.engine.system_update(
        "school-edit-after-restart",
        now + timedelta(minutes=1),
        lambda ctx: delivery.enqueue(ctx, SOURCE, []),
    )
    assert len(notices(harness)) == 2
    assert source(harness)["notification_markers"] == before["notification_markers"]
    # An unchanged envelope, and an unrelated later envelope, cannot replay the edit.
    assert not (await reconcile(harness.runtime.engine, now, options))["applied"]
    options["online_school"]["revision"] += 1
    assert (await reconcile(harness.runtime.engine, now, options))["sources"] == []
    assert source(harness) == after


async def test_disabling_bound_account_retains_cache_and_disabled_noop_retains_envelope(
    harness, now
):
    before = await prepared(harness, now)
    harness.discovery_error = "online_school_timeout"
    await begin(harness)
    result = await harness.flow.async_step_online_school_account({"enabled": False})
    options = result["data"]
    assert options["online_school"]["sources"][SOURCE]["generation"] == before["generation"]
    await reconcile(harness.runtime.engine, now, options)
    harness.entry.options = options
    after = source(harness)
    assert not after["enabled"] and after["status"] == "disabled"
    assert after["snapshot"] == before["snapshot"]
    assert after["acknowledgements"] == before["acknowledgements"]
    assert after["notification_markers"] == before["notification_markers"]
    await begin(harness)
    result = await harness.flow.async_step_online_school_account({"enabled": False})
    assert result["data"] == options
    assert harness.clients == []
    # Re-enabling an account is explicit reauthorization and must rediscover.
    await begin(harness)
    result = await harness.flow.async_step_online_school_account(account_values())
    assert result["errors"]["base"] == "online_school_timeout"
    assert len(harness.clients) == 1 and harness.clients[0].closed


@pytest.mark.parametrize(
    "change", ["password", "url", "username", "member", "child_epoch", "timezone", "student"]
)
async def test_identity_changes_require_discovery_and_reset_cache_and_acks(harness, now, change):
    before = await prepared(harness, now)
    account, student = {}, {}
    if change == "password":
        account = {"password": "REPLACEMENT-SYNTHETIC-PASSWORD"}
    elif change in {"url", "username"}:
        account = {
            change: "https://other.respublika.school" if change == "url" else "other-account",
            "password": "REPLACEMENT-SYNTHETIC-PASSWORD",
        }
    elif change == "member":
        account = {"member": "sibling"}
    elif change == "child_epoch":
        harness.change_state(lambda state: state["members"]["child"].update(revision=2))
    elif change == "timezone":
        harness.change_state(lambda state: state["settings"].update(timezone="Europe/Kyiv"))
    else:
        account, student = {"refresh_students": True}, {"student_id": "202"}
        harness.students.append({"id": "202", "name": "Other verified student"})
    options = await edit(harness, account=account, student=student_values(**student))
    record = options["online_school"]["sources"][SOURCE]
    assert record["generation"] != before["generation"]
    assert "policy_update" not in record
    assert len(harness.clients) == 1 and harness.clients[0].closed
    await reconcile(harness.runtime.engine, now, options)
    after = source(harness)
    assert after["snapshot"] is None and after["acknowledgements"] == {}
    assert after["last_success"] is None and after["status"] == "pending"
    assert all(
        not delivery.current(harness.runtime.engine.snapshot(), event, now)
        for event in notices(harness)
    )


async def test_refresh_with_unchanged_student_preserves_facts_and_rejects_undiscovered_id(
    harness, now
):
    before = await prepared(harness, now)
    options = await edit(harness, account={"refresh_students": True})
    assert options == harness.entry.options
    assert len(harness.clients) == 1 and source(harness) == before
    await begin(harness)
    await harness.flow.async_step_online_school_account(account_values(refresh_students=True))
    result = await harness.flow.async_step_online_school_student({"student_id": "999"})
    assert result == {"type": "abort", "reason": "invalid_field"}


@pytest.mark.parametrize("student", ["202", "999", None, 101])
async def test_offline_bypass_accepts_only_exact_saved_student(harness, now, student):
    await prepared(harness, now)
    harness.students.append({"id": "202", "name": "Not rediscovered during this flow"})
    await begin(harness)
    await harness.flow.async_step_online_school_account(account_values())
    result = await harness.flow.async_step_online_school_student({"student_id": student})
    assert result == {"type": "abort", "reason": "invalid_field"}
    assert harness.clients == []


@pytest.mark.parametrize("when", ["account", "student"])
@pytest.mark.parametrize("change", ["owner", "source", "child", "recipient", "chat", "timezone"])
async def test_edit_fences_exact_authority_before_every_step(harness, now, when, change):
    await prepared(harness, now)
    await begin(harness)
    if when == "student":
        await harness.flow.async_step_online_school_account(account_values())

    def mutate(state):
        if change in {"owner", "child"}:
            state["members"][change]["revision"] += 1
        elif change == "recipient":
            state["members"]["parent"]["revision"] += 1
        elif change == "chat":
            state["members"]["parent"]["telegram_id"] += 1
        elif change == "timezone":
            state["settings"]["timezone"] = "Europe/Kyiv"
        else:
            state["school"]["online"]["sources"][SOURCE]["revision"] += 1

    harness.change_state(mutate)
    result = (
        await harness.flow.async_step_online_school_account(account_values())
        if when == "account"
        else await harness.flow.async_step_online_school_student({"student_id": "101"})
    )
    assert result == {"type": "abort", "reason": "conflict"}
    assert harness.clients == []


@pytest.mark.parametrize(
    "change",
    [
        "owner_epoch",
        "owner_role",
        "source",
        "child",
        "recipient_epoch",
        "recipient_role",
        "timezone",
    ],
)
async def test_queued_policy_marker_cannot_apply_after_authority_changes(harness, now, change):
    await prepared(harness, now)
    options = await edit(harness, student={"recipients": ["owner", "parent"]})

    def mutate(state):
        if change == "source":
            state["school"]["online"]["sources"][SOURCE]["revision"] += 1
        elif change == "child":
            state["members"]["child"]["revision"] += 1
        elif change == "timezone":
            state["settings"]["timezone"] = "Europe/Kyiv"
        else:
            member = "parent" if change.startswith("recipient") else "owner"
            if change.endswith("role"):
                state["members"][member]["role"] = "adult"
            else:
                state["members"][member]["revision"] += 1

    harness.change_state(mutate)
    before = source(harness)
    assert (await reconcile(harness.runtime.engine, now, options))["sources"] == []
    assert source(harness) == before
    options["online_school"]["revision"] += 1
    assert (await reconcile(harness.runtime.engine, now, options))["sources"] == []
    assert source(harness) == before


async def test_unrelated_task_and_cache_or_ack_updates_do_not_invalidate_edit(harness, now):
    await prepared(harness, now)
    await begin(harness)
    await harness.flow.async_step_online_school_account(account_values(label="New label"))
    engine = harness.runtime.engine
    await engine.execute(
        "owner",
        "tasks.create",
        {"title": "Unrelated synthetic task", "assignee": "child"},
        "unrelated-school-edit-task",
        now,
    )
    await acknowledge(
        engine,
        source(harness),
        now,
        value=snapshot(student_id="101", timezone="UTC"),
        ack_revision=1,
        done=False,
        operation="school-edit-ack",
    )
    result = await harness.flow.async_step_online_school_student({"student_id": "101"})
    assert result["type"] == "create_entry"
    await reconcile(engine, now, result["data"])
    assert source(harness)["acknowledgements"]["lesson-a"]["done"] is False


async def test_consumed_marker_never_reverts_later_policy_or_canonical_disable(harness, now, store):
    await prepared(harness, now)
    first = await edit(harness, student={"notify_changes": False})
    await reconcile(harness.runtime.engine, now, first)
    harness.entry.options = first
    second = await edit(harness, student={"notify_changes": True})
    await reconcile(harness.runtime.engine, now, second)
    assert source(harness)["rules"]["notify_changes"] is True
    first["online_school"]["revision"] = second["online_school"]["revision"] + 1
    assert (await reconcile(harness.runtime.engine, now, first))["sources"] == []
    assert source(harness)["rules"]["notify_changes"] is True
    await harness.runtime.engine.execute(
        "owner",
        "school.online_source_disable",
        {"id": SOURCE, "revision": source(harness)["revision"]},
        "school-direct-disable",
        now,
    )
    harness.runtime.engine = Engine(deepcopy(store.value), store.save)
    second["online_school"]["revision"] = first["online_school"]["revision"] + 1
    assert (await reconcile(harness.runtime.engine, now, second))["sources"] == []
    assert source(harness)["enabled"] is False


async def test_notifications_off_and_on_do_not_repeat_same_day_preparation(harness, now):
    before = await prepared(harness, now)
    for enabled in (False, True):
        options = await edit(harness, student={"notifications": enabled})
        await reconcile(harness.runtime.engine, now, options)
        harness.entry.options = options
        await harness.runtime.engine.system_update(
            "school-policy-toggle", now, lambda ctx: delivery.enqueue(ctx, SOURCE, [])
        )
    assert source(harness)["rules"]["enabled"] is True
    assert source(harness)["generation"] == before["generation"]
    assert source(harness)["notification_markers"] == before["notification_markers"]
    assert len(notices(harness)) == 2
    assert all(
        not delivery.current(harness.runtime.engine.snapshot(), event, now)
        for event in notices(harness)
    )


@pytest.mark.parametrize(
    "changed", ["student_id", "member", "member_revision", "provider", "generation"]
)
async def test_policy_marker_cannot_authorize_changed_binding(harness, now, changed):
    await prepared(harness, now)
    options = await edit(harness, account={"label": "New label"})
    record = options["online_school"]["sources"][SOURCE]
    if changed == "generation":
        record["policy_update"]["generation"] = "changed-synthetic-value"
    else:
        record[changed] = 2 if changed == "member_revision" else "changed-synthetic-value"
    before = source(harness)
    assert (await reconcile(harness.runtime.engine, now, options))["sources"] == []
    assert source(harness) == before


async def test_malformed_policy_marker_cannot_partially_apply(harness, now):
    await prepared(harness, now)
    options = await edit(harness, account={"label": "New label"})
    del options["online_school"]["sources"][SOURCE]["policy_update"]["owner_revision"]
    before = harness.runtime.engine.snapshot()
    with pytest.raises(DomainError, match="invalid_field"):
        await reconcile(harness.runtime.engine, now, options)
    assert harness.runtime.engine.snapshot() == before
