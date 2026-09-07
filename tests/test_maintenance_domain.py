"""Maintenance domain tests with synthetic household state only."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from custom_components.family_assistant.domain import maintenance, media, task_series, tasks
from custom_components.family_assistant.domain.context import Context
from custom_components.family_assistant.domain.validation import DomainError

BAD_REVISIONS = (None, True, 1.0, "1", 0, 2**53)


def enabled_state(engine):
    state = engine.snapshot()
    state["settings"]["modules"].append("maintenance")
    return state


def context(state, actor_id, now, operation="maintenance-test"):
    return Context(state, state["members"][actor_id], now, operation)


def asset_payload(**changes):
    return {
        "name": "Heating boiler",
        "category": "Heating",
        "location": "Utility room",
        "responsible_member": "adult",
        "responsible_member_revision": 1,
        "warranty": {
            "expires_on": "2027-09-01",
            "vendor": "Example vendor",
            "reference": "Public synthetic reference",
        },
        "consumables": [],
        "note": "Parent-only serial and maintenance note",
        **changes,
    }


def save_asset(state, now, *, actor="parent", operation="asset-save", **changes):
    return maintenance.handle(
        context(state, actor, now, operation),
        "asset_save",
        asset_payload(**changes),
    )


def fault_payload(asset, reporter="child", **changes):
    return {
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "reporter_member_revision": 1,
        "summary": "Water pressure warning",
        "details": "The display showed a warning after breakfast.",
        "attachment_ids": [],
        **changes,
    }


def service_payload(asset, **changes):
    return {
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "title": "Check boiler pressure",
        "assignees": [{"id": "adult", "revision": 1}],
        "rotation": False,
        "rule": {
            "frequency": "monthly",
            "start_date": "2026-09-01",
            "time": "09:00",
            "timezone": "Europe/Kyiv",
            "month_day": 1,
            "catchup_hours": 24,
        },
        "due_time": "18:00",
        "checklist": ["Read the pressure gauge"],
        "enabled": True,
        "reminder_minutes": 60,
        "grace_minutes": 30,
        **changes,
    }


def rejected_without_mutation(state, call, code="invalid_field", field=None):
    before = deepcopy(state)
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code
    if field is not None:
        assert caught.value.field == field
    assert state == before


def test_asset_create_is_lazy_parent_only_opaque_and_has_no_effects(engine, now):
    state = enabled_state(engine)
    assert state["maintenance"] == {}
    rejected_without_mutation(
        state,
        lambda: save_asset(state, now, actor="adult"),
        "forbidden",
    )
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "parent", now),
            "asset_save",
            {**asset_payload(), "revision": 1},
        ),
    )

    effects = {
        "tasks": deepcopy(state["tasks"]),
        "task_series": deepcopy(state["task_series"]),
        "outbox": deepcopy(state["outbox"]),
        "pantry": deepcopy(state["pantry"]),
    }
    receipt = save_asset(state, now)
    assert receipt == {"id": "MX000001", "revision": 1, "status": "active"}
    assert set(receipt) == {"id", "revision", "status"}
    record = state["maintenance"]["assets"][receipt["id"]]
    assert record["reportable"] is False
    assert record["approved_by"] == "parent"
    assert record["approved_by_revision"] == 1
    assert record["history"] == [{"actor": "parent", "at": now.isoformat(), "action": "created"}]
    for bucket, value in effects.items():
        assert state[bucket] == value


@pytest.mark.parametrize("bad", BAD_REVISIONS)
def test_asset_edit_revision_is_strict_and_atomic(engine, now, bad):
    state = enabled_state(engine)
    created = save_asset(state, now)
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "parent", now),
            "asset_save",
            {
                **asset_payload(name="Changed"),
                "id": created["id"],
                "revision": bad,
            },
        ),
    )


def test_asset_full_edit_reapproves_epochs_and_preserves_omitted_reportable(engine, now):
    state = enabled_state(engine)
    created = save_asset(state, now, reportable=True)
    state["members"]["adult"]["revision"] = 2
    state["members"]["parent"]["revision"] = 2

    edited = maintenance.handle(
        context(state, "parent", now, "asset-edit"),
        "asset_save",
        {
            **asset_payload(
                name="Heating boiler v2",
                responsible_member_revision=2,
            ),
            "id": created["id"],
            "revision": created["revision"],
        },
    )
    record = state["maintenance"]["assets"][created["id"]]
    assert edited == {"id": created["id"], "revision": 2, "status": "active"}
    assert record["reportable"] is True
    assert record["approved_by_revision"] == 2
    assert record["responsible_member_revision"] == 2
    assert [event["action"] for event in record["history"]] == ["created", "updated"]

    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "parent", now),
            "asset_save",
            {"id": created["id"], "revision": edited["revision"], "name": "Partial"},
        ),
    )


def test_asset_retire_preserves_materialized_tasks_and_disables_series_guard(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    service = maintenance.handle(
        context(state, "parent", now, "service-create"),
        "service_save",
        service_payload(asset),
    )
    state["tasks"]["T999999"] = {
        "id": "T999999",
        "revision": 1,
        "status": "assigned",
        "assignee": "adult",
        "assignee_revision": 1,
        "source": {
            "kind": "maintenance_service",
            "asset_id": asset["id"],
            "asset_revision": asset["revision"],
            "series_id": service["id"],
            "series_revision": service["revision"],
        },
    }
    tasks_before = deepcopy(state["tasks"])

    retired = maintenance.handle(
        context(state, "owner", now, "retire"),
        "asset_retire",
        {"id": asset["id"], "revision": asset["revision"], "reason": "Replaced"},
    )
    assert retired == {"id": asset["id"], "revision": 2, "status": "retired"}
    assert state["tasks"] == tasks_before
    assert maintenance.series_current(state, state["task_series"][service["id"]]) is False


def test_asset_consumables_links_are_exact_informational_and_bounded(engine, now):
    state = enabled_state(engine)
    state["settings"]["modules"].append("pantry")
    state["pantry"] = {
        "items": {
            "I000001": {
                "id": "I000001",
                "revision": 2**53 - 1,
                "status": "active",
                "unit": "l",
                "quantity": 2,
            }
        }
    }
    pantry_before = deepcopy(state["pantry"])
    created = save_asset(
        state,
        now,
        consumables=[
            {
                "label": "Inhibitor",
                "unit": "l",
                "quantity": 0.125,
                "pantry": {"id": "I000001", "revision": 2**53 - 1},
            }
        ],
    )
    assert state["maintenance"]["assets"][created["id"]]["consumables"][0]["pantry"] == {
        "id": "I000001",
        "revision": 2**53 - 1,
    }
    assert state["pantry"] == pantry_before

    for quantity in (True, 0, 0.0001, 1.0001, float("inf")):
        rejected_without_mutation(
            state,
            lambda quantity=quantity: save_asset(
                state,
                now,
                operation=f"bad-quantity:{quantity}",
                name=f"Asset {quantity}",
                consumables=[
                    {
                        "label": "Filter",
                        "unit": "piece",
                        "quantity": quantity,
                        "pantry": None,
                    }
                ],
            ),
        )


def test_child_fault_requires_explicit_scope_current_epochs_and_empty_attachments(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "child", now),
            "fault_report",
            fault_payload(asset),
        ),
        "forbidden",
    )
    state["maintenance"]["assets"][asset["id"]]["reportable"] = True
    state["members"]["child"]["revision"] = 2
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "child", now),
            "fault_report",
            fault_payload(asset),
        ),
        "conflict",
    )
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "child", now),
            "fault_report",
            fault_payload(asset, reporter_member_revision=2, attachment_ids=["media-1"]),
        ),
    )
    state["members"]["adult"]["revision"] = 2
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "child", now),
            "fault_report",
            fault_payload(asset, reporter_member_revision=2),
        ),
        "conflict",
    )


def test_fault_creates_private_ordinary_task_without_copying_private_asset_data(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now, reportable=True)
    receipt = maintenance.handle(
        context(state, "child", now, "fault-create"),
        "fault_report",
        fault_payload(asset),
    )
    assert receipt == {
        "id": "MF000001",
        "revision": 1,
        "status": "reported",
        "task_id": "T000001",
    }
    fault = state["maintenance"]["faults"][receipt["id"]]
    task = state["tasks"][receipt["task_id"]]
    assert fault["reporter"] == "child" and fault["reporter_member_revision"] == 1
    assert task["creator"] == "parent"
    assert task["assignee"] == "adult" and task["assignee_revision"] == 1
    assert task["title"] == "Water pressure warning"
    assert task["report_type"] == "text"
    assert task["deadline_policy"]["penalty"] == 0
    assert task["delivery_scope"] == "private"
    assert task["source"] == {
        "kind": "maintenance_fault",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "fault_id": receipt["id"],
    }
    serialized_task = repr(task)
    assert "Parent-only serial" not in serialized_task
    assert "Utility room" not in serialized_task
    assert "display showed" not in serialized_task
    assigned = next(iter(state["outbox"].values()))
    assert assigned["recipient"] == "adult"
    assert assigned["data"] == {
        "id": task["id"],
        "member": "adult",
        "member_revision": 1,
    }

    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "child", now, "fault-duplicate"),
            "fault_report",
            fault_payload(asset, summary="  WATER   pressure WARNING "),
        ),
        "invalid_transition",
    )


def test_fault_active_limit_is_bounded_without_creating_task(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now, reportable=True)
    faults = state["maintenance"].setdefault("faults", {})
    for index in range(maintenance.MAX_ACTIVE_FAULTS_PER_REPORTER):
        task_id = f"T{index + 100:06}"
        state["tasks"][task_id] = {"id": task_id, "status": "assigned"}
        faults[f"MF{index + 100:06}"] = {
            "id": f"MF{index + 100:06}",
            "reporter": "child",
            "asset_id": asset["id"],
            "normalized_summary": f"fault {index}",
            "task_id": task_id,
        }
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "child", now), "fault_report", fault_payload(asset)
        ),
        "invalid_transition",
    )


def test_service_save_pins_reviewed_source_and_generic_series_route_is_closed(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    tasks_before = deepcopy(state["tasks"])
    outbox_before = deepcopy(state["outbox"])
    receipt = maintenance.handle(
        context(state, "parent", now, "service-create"),
        "service_save",
        service_payload(asset),
    )
    assert receipt == {"id": "D000001", "revision": 1, "enabled": True}
    series = state["task_series"][receipt["id"]]
    assert series["source"] == {
        "kind": "maintenance",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "approved_by": "parent",
        "approved_by_revision": 1,
        "member_revisions": {"adult": 1},
    }
    assert series["creator"] == "parent"
    assert series["report_type"] == "text"
    assert series["deadline_policy"]["penalty"] == 0
    assert maintenance.series_current(state, series) is True
    assert state["tasks"] == tasks_before and state["outbox"] == outbox_before

    rejected_without_mutation(
        state,
        lambda: task_series.handle(
            context(state, "parent", now),
            "series_enable",
            {"id": series["id"], "revision": series["revision"], "enabled": False},
        ),
        "forbidden",
    )


def test_service_report_type_defaults_to_text_and_omitted_edit_preserves_photo(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    text_service = maintenance.handle(
        context(state, "parent", now, "service-text"),
        "service_save",
        service_payload(asset),
    )
    assert state["task_series"][text_service["id"]]["report_type"] == "text"

    photo_service = maintenance.handle(
        context(state, "parent", now, "service-photo"),
        "service_save",
        service_payload(asset, title="Photograph pressure gauge", report_type="photo"),
    )
    photo_series = state["task_series"][photo_service["id"]]
    assert photo_series["report_type"] == "photo"
    assert maintenance.series_current(state, photo_series) is True
    projected = {
        item["id"]: item for item in maintenance.view(state, state["members"]["parent"])["services"]
    }
    assert projected[photo_service["id"]]["report_type"] == "photo"

    edited = maintenance.handle(
        context(state, "parent", now, "service-photo-edit"),
        "service_save",
        {
            **service_payload(asset, title="Photograph boiler and gauge"),
            "id": photo_service["id"],
            "revision": photo_service["revision"],
        },
    )
    assert edited["revision"] == photo_service["revision"] + 1
    assert state["task_series"][photo_service["id"]]["report_type"] == "photo"

    for value in (None, "none", "video", True, 1, [], {}):
        rejected_without_mutation(
            state,
            lambda value=value: maintenance.handle(
                context(state, "parent", now, f"bad-report-{value}"),
                "service_save",
                service_payload(asset, title=f"Bad report {value}", report_type=value),
            ),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state, asset, series: state["settings"]["modules"].remove("maintenance"),
        lambda state, asset, series: state["settings"]["modules"].remove("tasks"),
        lambda state, asset, series: state["members"]["parent"].update(revision=2),
        lambda state, asset, series: state["members"]["adult"].update(revision=2),
        lambda state, asset, series: asset.update(revision=2),
        lambda state, asset, series: asset.update(status="retired"),
        lambda state, asset, series: series.update(report_type="video"),
        lambda state, asset, series: series["deadline_policy"].update(penalty=-1),
        lambda state, asset, series: series["source"].update(extra="untrusted"),
    ],
)
def test_series_current_fails_closed_for_every_authority_epoch(engine, now, mutate):
    state = enabled_state(engine)
    asset_receipt = save_asset(state, now)
    service = maintenance.handle(
        context(state, "parent", now), "service_save", service_payload(asset_receipt)
    )
    asset = state["maintenance"]["assets"][asset_receipt["id"]]
    series = state["task_series"][service["id"]]
    mutate(state, asset, series)
    assert maintenance.series_current(state, series) is False


def test_service_edit_reapproves_current_asset_and_member_epochs(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    created = maintenance.handle(
        context(state, "parent", now), "service_save", service_payload(asset)
    )
    state["members"]["adult"]["revision"] = 2
    state["members"]["parent"]["revision"] = 2
    current_asset = maintenance.handle(
        context(state, "parent", now, "asset-reapprove"),
        "asset_save",
        {
            **asset_payload(responsible_member_revision=2),
            "id": asset["id"],
            "revision": asset["revision"],
        },
    )
    edited = maintenance.handle(
        context(state, "parent", now, "service-edit"),
        "service_save",
        {
            **service_payload(
                current_asset,
                title="Check boiler and expansion vessel",
                assignees=[{"id": "adult", "revision": 2}],
            ),
            "id": created["id"],
            "revision": created["revision"],
        },
    )
    series = state["task_series"][created["id"]]
    assert edited == {"id": created["id"], "revision": 2, "enabled": True}
    assert series["source"]["asset_revision"] == 2
    assert series["source"]["approved_by_revision"] == 2
    assert series["source"]["member_revisions"] == {"adult": 2}
    assert maintenance.series_current(state, series) is True


def test_service_enable_requires_current_guard_but_orphan_disable_remains_possible(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    service = maintenance.handle(
        context(state, "parent", now), "service_save", service_payload(asset, enabled=False)
    )
    enabled = maintenance.handle(
        context(state, "parent", now, "enable"),
        "service_enable",
        {
            "id": service["id"],
            "revision": service["revision"],
            "enabled": True,
            "asset_revision": asset["revision"],
        },
    )
    assert enabled == {"id": service["id"], "revision": 2, "enabled": True}
    state["maintenance"]["assets"][asset["id"]]["status"] = "retired"
    disabled = maintenance.handle(
        context(state, "owner", now, "disable-orphan"),
        "service_enable",
        {
            "id": service["id"],
            "revision": enabled["revision"],
            "enabled": False,
            "asset_revision": asset["revision"],
        },
    )
    assert disabled == {"id": service["id"], "revision": 3, "enabled": False}
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "parent", now),
            "service_enable",
            {
                "id": service["id"],
                "revision": disabled["revision"],
                "enabled": True,
                "asset_revision": asset["revision"],
            },
        ),
        "conflict",
    )


def test_service_log_accepts_only_completed_immutable_maintenance_task_once(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now, reportable=True)
    fault = maintenance.handle(context(state, "child", now), "fault_report", fault_payload(asset))
    task = state["tasks"][fault["task_id"]]
    task["status"] = "completed"
    task["revision"] = 2
    tasks_before = deepcopy(state["tasks"])
    receipt = maintenance.handle(
        context(state, "parent", now, "log"),
        "service_log",
        {
            "asset_id": asset["id"],
            "asset_revision": asset["revision"],
            "performed_on": "2026-09-06",
            "summary": "Pressure restored after inspection.",
            "task": {"id": task["id"], "revision": task["revision"]},
            "consumables_used": [],
            "attachment_ids": [],
        },
    )
    assert receipt == {"id": "MH000001", "revision": 1, "status": "recorded"}
    assert state["tasks"] == tasks_before
    log = state["maintenance"]["service_logs"][receipt["id"]]
    assert log["task_id"] == task["id"] and log["task_revision"] == 2

    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "parent", now, "duplicate-log"),
            "service_log",
            {
                "asset_id": asset["id"],
                "asset_revision": asset["revision"],
                "performed_on": "2026-09-06",
                "summary": "Duplicate",
                "task": {"id": task["id"], "revision": task["revision"]},
                "consumables_used": [],
                "attachment_ids": [],
            },
        ),
        "invalid_transition",
    )


def test_service_log_rejects_future_unrelated_and_nonempty_attachment(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    state["tasks"]["T999999"] = {
        "id": "T999999",
        "revision": 1,
        "status": "completed",
        "source": {"kind": "ordinary", "asset_id": asset["id"]},
    }
    base = {
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "performed_on": "2026-09-06",
        "summary": "Manual inspection",
        "task": None,
        "consumables_used": [],
        "attachment_ids": [],
    }
    for changes, code in (
        ({"performed_on": "2026-09-07"}, "invalid_field"),
        ({"attachment_ids": ["pending-media"]}, "invalid_field"),
        ({"task": {"id": "T999999", "revision": 1}}, "invalid_field"),
    ):
        rejected_without_mutation(
            state,
            lambda changes=changes: maintenance.handle(
                context(state, "parent", now), "service_log", {**base, **changes}
            ),
            code,
        )


def test_view_is_pure_and_relationships_require_current_identity_epochs(engine, now):
    state = enabled_state(engine)
    private_asset = save_asset(state, now)
    public_asset = save_asset(
        state,
        now,
        operation="public-asset",
        name="Shared sink",
        responsible_member="sibling",
        reportable=True,
    )
    fault = maintenance.handle(
        context(state, "child", now), "fault_report", fault_payload(public_asset)
    )
    task = state["tasks"][fault["task_id"]]
    before = deepcopy(state)

    child_view = maintenance.view(state, state["members"]["child"])
    assert {item["id"] for item in child_view["assets"]} == {public_asset["id"]}
    assert child_view["faults"][0]["id"] == fault["id"]
    assert not ({"note", "warranty", "consumables", "history"} & child_view["assets"][0].keys())
    assert child_view["services"] == [] and child_view["service_logs"] == []
    assert maintenance.view(state, state["members"]["guest"]) == {
        "assets": [],
        "faults": [],
        "service_logs": [],
        "services": [],
    }
    parent_view = maintenance.view(state, state["members"]["parent"])
    parent_assets = {item["id"]: item for item in parent_view["assets"]}
    assert parent_assets[private_asset["id"]]["current"] is True
    assert parent_assets[private_asset["id"]]["can_report"] is True
    assert parent_assets[private_asset["id"]]["note"].startswith("Parent-only")
    assert state == before

    state["members"]["child"]["revision"] = 2
    current_child = maintenance.view(state, state["members"]["child"])
    assert current_child["faults"] == []
    assert {item["id"] for item in current_child["assets"]} == {public_asset["id"]}
    state["members"]["sibling"]["revision"] = 2
    sibling_view = maintenance.view(state, state["members"]["sibling"])
    assert sibling_view["assets"][0]["can_report"] is False

    task["assignee"] = "adult"
    task["assignee_revision"] = 0
    adult_view = maintenance.view(state, state["members"]["adult"])
    assert adult_view["faults"] == []
    adult_assets = {item["id"]: item for item in adult_view["assets"]}
    assert set(adult_assets) == {private_asset["id"], public_asset["id"]}
    assert adult_assets[public_asset["id"]]["can_report"] is False


def test_view_hides_private_nonreportable_assets_after_responsible_aba(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now)
    assert [
        item["id"] for item in maintenance.view(state, state["members"]["adult"])["assets"]
    ] == [asset["id"]]
    state["members"]["adult"]["revision"] = 2
    assert maintenance.view(state, state["members"]["adult"])["assets"] == []


def test_module_roles_and_replay_scope_are_rechecked_without_writes(engine, now):
    state = enabled_state(engine)
    before = deepcopy(state)
    maintenance.authorize_replay(
        context(state, "child", now),
        "fault_report",
        {"reporter_member_revision": 1},
    )
    assert state == before
    with pytest.raises(DomainError, match="forbidden"):
        maintenance.authorize_replay(context(state, "adult", now), "asset_save", {})
    state["members"]["child"]["revision"] = 2
    with pytest.raises(DomainError, match="conflict"):
        maintenance.authorize_replay(
            context(state, "child", now),
            "fault_report",
            {"reporter_member_revision": 1},
        )
    with pytest.raises(DomainError) as malformed:
        maintenance.authorize_replay(
            context(state, "child", now),
            "fault_report",
            {"reporter_member_revision": True},
        )
    assert malformed.value.code == "invalid_field"
    assert malformed.value.field == "reporter_member_revision"
    state["settings"]["modules"].remove("tasks")
    with pytest.raises(DomainError, match="module_disabled"):
        maintenance.authorize_replay(
            context(state, "child", now),
            "fault_report",
            {"reporter_member_revision": 2},
        )
    with pytest.raises(DomainError, match="module_disabled"):
        maintenance.authorize_replay(context(state, "parent", now), "service_save", {})


def test_unknown_action_and_disabled_module_never_initialize_state(engine, now):
    state = engine.snapshot()
    before = deepcopy(state)
    with pytest.raises(DomainError, match="module_disabled"):
        maintenance.handle(context(state, "parent", now), "asset_save", asset_payload())
    assert state == before
    state["settings"]["modules"].append("maintenance")
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(context(state, "parent", now), "unknown", {}),
        "unknown_action",
    )


def test_max_revision_sources_are_readable_but_mutations_cannot_overflow(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now, reportable=True)
    record = state["maintenance"]["assets"][asset["id"]]
    record["revision"] = 2**53 - 1
    asset_at_max = {"id": asset["id"], "revision": 2**53 - 1}
    reported = maintenance.handle(
        context(state, "child", now), "fault_report", fault_payload(asset_at_max)
    )
    assert state["tasks"][reported["task_id"]]["source"]["asset_revision"] == 2**53 - 1
    rejected_without_mutation(
        state,
        lambda: maintenance.handle(
            context(state, "parent", now),
            "asset_retire",
            {"id": asset["id"], "revision": 2**53 - 1, "reason": "No overflow"},
        ),
    )


def test_manual_service_log_uses_household_local_date(engine):
    state = enabled_state(engine)
    state["settings"]["timezone"] = "Europe/Kyiv"
    now = datetime(2026, 9, 6, 21, 30, tzinfo=UTC)  # 2026-09-07 locally.
    asset = save_asset(state, now)
    receipt = maintenance.handle(
        context(state, "parent", now),
        "service_log",
        {
            "asset_id": asset["id"],
            "asset_revision": asset["revision"],
            "performed_on": "2026-09-07",
            "summary": "Late-evening local maintenance",
            "task": None,
            "consumables_used": [],
            "attachment_ids": [],
        },
    )
    assert receipt["status"] == "recorded"


def test_service_materialization_is_private_and_preserves_frozen_source(engine):
    state = enabled_state(engine)
    asset = save_asset(state, now=datetime(2026, 9, 6, 8, 0, tzinfo=UTC))
    created_at = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    service = maintenance.handle(
        context(state, "parent", created_at),
        "service_save",
        service_payload(
            asset,
            rule={
                "frequency": "daily",
                "start_date": "2026-09-06",
                "time": "09:00",
                "timezone": "UTC",
                "catchup_hours": 24,
            },
            due_time="18:00",
        ),
    )
    tick_at = datetime(2026, 9, 6, 9, 1, tzinfo=UTC)
    task_series.tick(context(state, "owner", tick_at, "tick"))
    generated = next(iter(state["tasks"].values()))
    assert generated["delivery_scope"] == "private"
    assert generated["assignee_revision"] == 1
    assert generated["source"] == {
        "kind": "maintenance_service",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "series_id": service["id"],
        "series_revision": service["revision"],
    }
    assert generated["deadline_policy"]["penalty"] == 0
    assert generated["title"] == "Check boiler pressure"
    assert "Parent-only" not in repr(generated)

    state["maintenance"]["assets"][asset["id"]]["revision"] = 2
    generated_before = deepcopy(state["tasks"])
    next_day = datetime(2026, 9, 7, 9, 1, tzinfo=UTC)
    task_series.tick(context(state, "owner", next_day, "tick-next"))
    assert state["tasks"] == generated_before


def test_photo_service_materializes_private_task_and_uses_real_media_submission(engine):
    state = enabled_state(engine)
    created_at = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    asset = save_asset(state, now=created_at)
    service = maintenance.handle(
        context(state, "parent", created_at, "photo-service"),
        "service_save",
        service_payload(
            asset,
            title="Photograph boiler gauge",
            report_type="photo",
            rule={
                "frequency": "daily",
                "start_date": "2026-09-06",
                "time": "09:00",
                "timezone": "UTC",
                "catchup_hours": 24,
            },
            due_time="18:00",
        ),
    )
    tick_at = datetime(2026, 9, 6, 9, 1, tzinfo=UTC)
    task_series.tick(context(state, "owner", tick_at, "photo-tick"))
    generated = next(iter(state["tasks"].values()))
    assert generated["report_type"] == "photo"
    assert generated["delivery_scope"] == "private"
    assert generated["source"] == {
        "kind": "maintenance_service",
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "series_id": service["id"],
        "series_revision": service["revision"],
    }

    reserved = media.handle(
        context(state, "adult", tick_at, "photo-reserve"),
        "reserve",
        {
            "purpose": "task_report",
            "task_id": generated["id"],
            "task_revision": generated["revision"],
            "uploader_revision": state["members"]["adult"]["revision"],
        },
    )
    available = media.finalize(
        Context(state, {"id": "system", "role": "system"}, tick_at, "photo-finalize"),
        "adult",
        reserved["id"],
        reserved["revision"],
        "image/png",
        128,
        "a" * 64,
    )
    submitted = tasks.handle(
        context(state, "adult", tick_at, "photo-submit"),
        "submit",
        {
            "id": generated["id"],
            "revision": generated["revision"],
            "media": {"id": available["id"], "revision": available["revision"]},
        },
    )
    assert submitted == {"id": generated["id"], "revision": 2, "status": "submitted"}
    assert state["tasks"][generated["id"]]["report_media"] == [available["id"]]
    assert state["media"][available["id"]]["status"] == "attached"


def test_ordinary_task_lifecycle_remains_independent_after_asset_retirement(engine, now):
    state = enabled_state(engine)
    asset = save_asset(state, now, reportable=True)
    fault = maintenance.handle(context(state, "child", now), "fault_report", fault_payload(asset))
    task = state["tasks"][fault["task_id"]]
    maintenance.handle(
        context(state, "parent", now),
        "asset_retire",
        {"id": asset["id"], "revision": asset["revision"], "reason": "Replaced"},
    )
    result = tasks.handle(
        context(state, "adult", now, "task-start"),
        "start",
        {"id": task["id"], "revision": task["revision"]},
    )
    assert result["status"] == "in_progress"
