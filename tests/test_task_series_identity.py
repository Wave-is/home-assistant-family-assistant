"""Identity-epoch safety for generic recurring task definitions."""

from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.family_assistant.domain import maintenance, task_series
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.engine import Engine
from custom_components.family_assistant.domain.members import handle as member_command
from custom_components.family_assistant.domain.validation import DomainError


def _ctx(state, actor, now, operation="identity-test"):
    return Context(state, state["members"][actor], now, operation)


def _payload(state, *, actor="parent", assignees=("child",), existing=None, **changes):
    creator = existing.get("creator") if existing else actor
    return {
        **({"id": existing["id"], "revision": existing["revision"]} if existing else {}),
        "actor_revision": state["members"][actor]["revision"],
        "creator_revision": state["members"][creator]["revision"],
        "title": "Clean kitchen",
        "assignees": list(assignees),
        "assignee_revisions": {
            member: state["members"][member]["revision"] for member in assignees
        },
        "rotation": len(assignees) > 1,
        "rule": {
            "frequency": "daily",
            "start_date": "2026-09-01",
            "time": "07:00",
            "timezone": "UTC",
        },
        "due_time": "20:00",
        **changes,
    }


async def _create(engine, now, *, assignees=("child",), operation="create"):
    state = engine.snapshot()
    return await engine.execute(
        "parent",
        "tasks.series_save",
        _payload(state, assignees=assignees),
        operation,
        now - timedelta(hours=2),
    )


@pytest.mark.asyncio
async def test_same_role_assignee_rebind_stops_whole_rotation_until_exact_review(engine, now):
    created = await _create(engine, now, assignees=("child", "sibling"))
    before = engine.snapshot()
    assert task_series.generic_series_current(before, before["task_series"][created["id"]])

    child = before["members"]["child"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": child["revision"],
            "name": "Renamed child",
            "role": "child",
        },
        "same-role-child-rebind",
        now,
    )
    assert not await engine.tick(now)
    stale = engine.snapshot()["task_series"][created["id"]]
    assert stale["occurrences"] == {}

    disabled = await engine.execute(
        "parent",
        "tasks.series_enable",
        {
            "id": stale["id"],
            "revision": stale["revision"],
            "enabled": False,
            "actor_revision": 1,
        },
        "disable-stale",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "parent",
            "tasks.series_enable",
            {
                "id": disabled["id"],
                "revision": disabled["revision"],
                "enabled": True,
                "actor_revision": 1,
            },
            "enable-stale",
            now,
        )

    state = engine.snapshot()
    reviewed = await engine.execute(
        "parent",
        "tasks.series_save",
        _payload(
            state,
            assignees=("child", "sibling"),
            existing=state["task_series"][created["id"]],
            enabled=False,
        ),
        "review-new-child-epoch",
        now,
    )
    assert reviewed["assignee_revisions"]["child"] == 2
    enabled = await engine.execute(
        "parent",
        "tasks.series_enable",
        {
            "id": reviewed["id"],
            "revision": reviewed["revision"],
            "enabled": True,
            "actor_revision": 1,
        },
        "enable-reviewed",
        now,
    )
    assert enabled["enabled"] is True
    assert await engine.tick(now + timedelta(days=1))
    assert len(engine.snapshot()["tasks"]) == 1


@pytest.mark.asyncio
async def test_same_role_creator_rebind_needs_current_original_creator_review(engine, now):
    created = await _create(engine, now)
    parent = engine.snapshot()["members"]["parent"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": parent["revision"],
            "name": "Renamed parent",
            "role": "parent",
        },
        "same-role-parent-rebind",
        now,
    )
    assert not await engine.tick(now)
    state = engine.snapshot()
    stale_payload = _payload(
        state,
        actor="owner",
        existing=state["task_series"][created["id"]],
    )
    stale_payload["creator_revision"] = 1
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute(
            "owner", "tasks.series_save", stale_payload, "stale-creator-review", now
        )

    reviewed = await engine.execute(
        "owner",
        "tasks.series_save",
        _payload(
            state,
            actor="owner",
            existing=state["task_series"][created["id"]],
        ),
        "current-creator-review",
        now,
    )
    assert reviewed["creator"] == "parent"
    assert reviewed["creator_revision"] == 2
    assert await engine.tick(now + timedelta(days=1))


@pytest.mark.asyncio
async def test_legacy_lineage_survives_reload_but_is_inert_until_review(engine, store, now):
    created = await _create(engine, now)
    legacy = engine.snapshot()
    legacy_row = legacy["task_series"][created["id"]]
    legacy_row.pop("creator_revision")
    legacy_row.pop("assignee_revisions")
    restarted = Engine(legacy, store.save)

    assert not await restarted.tick(now)
    row = restarted.snapshot()["task_series"][created["id"]]
    disabled = await restarted.execute(
        "parent",
        "tasks.series_enable",
        {
            "id": row["id"],
            "revision": row["revision"],
            "enabled": False,
            "actor_revision": 1,
        },
        "legacy-disable",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await restarted.execute(
            "parent",
            "tasks.series_enable",
            {
                "id": disabled["id"],
                "revision": disabled["revision"],
                "enabled": True,
                "actor_revision": 1,
            },
            "legacy-enable",
            now,
        )

    state = restarted.snapshot()
    reviewed = await restarted.execute(
        "parent",
        "tasks.series_save",
        _payload(
            state,
            existing=state["task_series"][created["id"]],
            enabled=False,
        ),
        "legacy-review",
        now,
    )
    assert store.value["task_series"][created["id"]]["creator_revision"] == 1
    reloaded = Engine(deepcopy(store.value), store.save)
    assert task_series.generic_series_current(
        reloaded.snapshot(), reloaded.snapshot()["task_series"][reviewed["id"]]
    )


def _asset_payload():
    return {
        "name": "Heating boiler",
        "category": "Heating",
        "location": "Utility room",
        "responsible_member": "adult",
        "responsible_member_revision": 1,
        "warranty": {"expires_on": None, "vendor": "", "reference": ""},
        "consumables": [],
        "note": "Synthetic note",
    }


def _service_payload(asset, *, record_id=None, revision=None, assignee_revision=1):
    return {
        **({"id": record_id, "revision": revision} if revision is not None else {}),
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "title": "Check boiler",
        "assignees": [{"id": "adult", "revision": assignee_revision}],
        "rotation": False,
        "rule": {
            "frequency": "monthly",
            "start_date": "2026-09-01",
            "time": "09:00",
            "timezone": "UTC",
            "month_day": 1,
        },
        "due_time": "18:00",
        "checklist": [],
        "enabled": True,
        "reminder_minutes": 60,
        "grace_minutes": 30,
    }


def test_maintenance_series_keeps_its_existing_source_lineage_contract(engine, now):
    state = engine.snapshot()
    state["settings"]["modules"].append("maintenance")
    asset = maintenance.handle(_ctx(state, "parent", now), "asset_save", _asset_payload())
    service = maintenance.handle(
        _ctx(state, "parent", now, "service-create"),
        "service_save",
        _service_payload(asset),
    )
    row = state["task_series"][service["id"]]
    assert "creator_revision" not in row
    assert "assignee_revisions" not in row
    assert task_series.series_current(state, row)

    member_command(
        _ctx(state, "owner", now, "adult-rebind"),
        "save",
        {
            "id": "adult",
            "revision": 1,
            "name": "Renamed adult",
            "role": "adult",
        },
    )
    assert not task_series.series_current(state, row)
    asset = maintenance.handle(
        _ctx(state, "parent", now, "asset-review"),
        "asset_save",
        {
            **_asset_payload(),
            "id": asset["id"],
            "revision": asset["revision"],
            "responsible_member_revision": 2,
        },
    )
    updated = maintenance.handle(
        _ctx(state, "parent", now, "service-review"),
        "service_save",
        _service_payload(
            asset,
            record_id=service["id"],
            revision=service["revision"],
            assignee_revision=2,
        ),
    )
    assert task_series.series_current(state, state["task_series"][updated["id"]])


def test_replay_and_projection_do_not_cross_actor_epoch_or_expose_lineage(engine, now):
    state = engine.snapshot()
    payload = _payload(state)
    result = task_series.handle(_ctx(state, "parent", now), "series_save", payload)
    task_series.authorize_replay(
        _ctx(state, "parent", now, "replay"), "series_save", payload, result
    )
    child_row = task_series.public_record(state, result, parent=False)
    assert child_row["current"] is True
    assert (
        not {
            "creator",
            "creator_revision",
            "assignee_revisions",
            "cursor",
            "occurrences",
        }
        & child_row.keys()
    )

    state["members"]["parent"]["revision"] += 1
    with pytest.raises(DomainError, match="conflict"):
        task_series.authorize_replay(
            _ctx(state, "parent", now, "rebound-replay"),
            "series_save",
            payload,
            result,
        )


@pytest.mark.asyncio
async def test_engine_replay_denies_same_role_actor_rebind(engine, now):
    state = engine.snapshot()
    payload = _payload(state)
    receipt = await engine.execute(
        "parent", "tasks.series_save", payload, "frozen-series-operation", now
    )
    assert receipt["creator_revision"] == 1
    parent = engine.snapshot()["members"]["parent"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "parent",
            "revision": parent["revision"],
            "name": "Same-role replacement",
            "role": "parent",
        },
        "rebind-series-actor",
        now,
    )
    with pytest.raises(DomainError, match="conflict"):
        await engine.execute("parent", "tasks.series_save", payload, "frozen-series-operation", now)


@pytest.mark.asyncio
async def test_child_projection_hides_rebound_and_legacy_series_titles(engine, store, now):
    created = await _create(engine, now)
    assert [row["title"] for row in engine.view("child")["task_series"]] == ["Clean kitchen"]
    child = engine.snapshot()["members"]["child"]
    await engine.execute(
        "owner",
        "members.save",
        {
            "id": "child",
            "revision": child["revision"],
            "name": "Rebound child",
            "role": "child",
        },
        "rebind-series-child",
        now,
    )
    assert engine.view("child")["task_series"] == []
    assert engine.view("parent")["task_series"][0]["current"] is False

    legacy = engine.snapshot()
    legacy_row = legacy["task_series"][created["id"]]
    legacy_row.pop("creator_revision")
    legacy_row.pop("assignee_revisions")
    restarted = Engine(legacy, store.save)
    assert restarted.view("child")["task_series"] == []
    parent_rows = restarted.view("parent")["task_series"]
    assert parent_rows[0]["title"] == "Clean kitchen"
    assert parent_rows[0]["current"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"actor_revision": True},
        {"creator_revision": 0},
        {"assignee_revisions": {}},
        {"assignee_revisions": {"child": "1"}},
        {"assignee_revisions": {"child": 1, "sibling": 1}},
    ],
)
def test_lineage_payload_is_strict_and_atomic(engine, now, change):
    state = engine.snapshot()
    before = deepcopy(state)
    with pytest.raises(DomainError):
        task_series.handle(_ctx(state, "parent", now), "series_save", _payload(state, **change))
    assert state == before
