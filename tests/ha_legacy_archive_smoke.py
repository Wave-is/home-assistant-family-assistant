"""Actual HA Store roundtrip of a fictional owner-private legacy review archive."""

import json
from copy import deepcopy


def synthetic_source():
    from custom_components.family_assistant.migration.review import ASSISTANT_KEY, COURT_KEY

    stamp = "2026-09-07T08:00:00+00:00"
    ledger = {
        "schema_version": 1,
        "next_task_sequence": 2,
        "next_event_sequence": 2,
        "tasks": {
            "T000001": {
                "task_id": "T000001",
                "kind": "shopping",
                "state": "accepted",
                "title": "Яблоки",
                "creator": "old-parent",
                "assignee": None,
                "created_at": stamp,
                "due_at": stamp,
                "metadata": {
                    "shopping_quantity": 3,
                    "shopping_remaining_quantity": 1.5,
                    "shopping_unit": "kg",
                    "shopping_approval": "approved",
                },
            }
        },
        "history": [{"sequence": 1, "task_id": "T000001", "actor": "old-parent", "at": stamp}],
        "processed_commands": {"old-command": {"private": "synthetic-old-receipt"}},
    }
    assistant = {
        "ledger": ledger,
        "alarms": {
            "schedules": {"old-child": {"weekday": {"time": "07:00", "enabled": True}}},
            "runs": {},
        },
        "memories": {"private": "synthetic-note"},
    }
    for sequence, kind, assignee in [(2, "task", "old-child"), (3, "reminder", "old-parent")]:
        identifier = f"T{sequence:06}"
        ledger["tasks"][identifier] = {
            "task_id": identifier,
            "kind": kind,
            "state": "accepted",
            "title": "Fictional private reminder" if kind == "reminder" else "Fictional chore",
            "creator": "old-parent",
            "assignee": assignee,
            "created_at": stamp,
            "due_at": stamp,
            "requires_report": False,
            "report_type": None,
            "metadata": {},
        }
        ledger["history"].append(
            {"sequence": sequence, "task_id": identifier, "actor": "old-parent", "at": stamp}
        )
    ledger.update(next_task_sequence=4, next_event_sequence=4)
    court = {
        "schema_version": 1,
        "week_id": "source-period",
        "opened_at": stamp,
        "children": {"old-child": {"pluses": 0, "minuses": 1}},
        "history": [
            {
                "event_id": "source-event",
                "child": "old-child",
                "week_id": "source-period",
                "timestamp": stamp,
                "type": "minus",
                "delta": -1,
                "cancelled": False,
                "reason": "Fictional incomplete task",
                "original_text": "synthetic-private-original",
            }
        ],
        "archived_weeks": [],
        "processed_messages": {},
    }

    def wrapped(data, key):
        return (
            json.dumps(
                {"key": key, "version": 1, "data": data}, ensure_ascii=False, indent=2
            ).encode()
            + b"\n"
        )

    members = {
        key: {"id": key, "revision": 1, "active": True, "role": role, "language": "en", "name": key}
        for key, role in [("owner", "owner"), ("child", "child")]
    }
    mapping = {
        "old-parent": {"member_id": "owner", "member_revision": 1},
        "old-child": {"member_id": "child", "member_revision": 1},
    }
    return wrapped(assistant, ASSISTANT_KEY), wrapped(court, COURT_KEY), mapping, members


def proposals(review, members):
    from custom_components.family_assistant.migration.alarm_plan import build_alarm_plan
    from custom_components.family_assistant.migration.court_plan import build_court_plan
    from custom_components.family_assistant.migration.shopping_plan import build_shopping_plan
    from custom_components.family_assistant.migration.task_plan import build_task_plan

    return [
        plan.private_data()
        for plan in (
            build_alarm_plan(review, "UTC", members=members),
            build_shopping_plan(review, members=members),
            build_court_plan(review, members=members),
            build_task_plan(review, members=members),
        )
    ]


async def verify_legacy_archive(hass):
    from homeassistant.helpers.storage import Store

    from custom_components.family_assistant.migration.archive import (
        ArchiveError,
        decode_private_review,
        encode_private_review,
    )
    from custom_components.family_assistant.migration.review import read_store_pair

    assistant, court, mapping, members = synthetic_source()
    review = read_store_pair(assistant, court).review(mapping, members, mapping_revision=1)
    expected = proposals(review, members)
    content = encode_private_review(review, members=members)
    key = "synthetic_family_migration_archive"
    await Store(hass, 1, key).async_save({"private_archive": content.decode()})
    loaded = await Store(hass, 1, key).async_load()
    assert loaded["private_archive"].encode() == content
    restored = decode_private_review(loaded["private_archive"].encode(), members=members)
    assert restored._source._assistant == assistant and restored._source._court == court
    assert restored.summary() == review.summary()
    assert proposals(restored, members) == expected
    assert expected[0]["proposals"][0]["payload"]["enabled"] is False
    assert len(expected[3]["proposals"]) == 1
    assert expected[3]["blocked"] == [
        {"source_task": "T000003", "code": "task_personal_scope_unsupported"}
    ]
    changed = deepcopy(members)
    changed["child"]["telegram_id"] = 778899
    try:
        decode_private_review(content, members=changed)
        raise AssertionError("Changed member binding must invalidate an archived review")
    except ArchiveError as error:
        assert str(error) == "review_changed"
    print(
        "PASS: actual HA Store private review archive, exact source bytes, "
        "proposal replay and changed-binding refusal; no import"
    )
