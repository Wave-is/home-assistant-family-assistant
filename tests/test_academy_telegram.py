"""Synthetic scheduler, private command and delivery tests."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.family_assistant.academy.household import mutate, project
from custom_components.family_assistant.academy.telegram import (
    KEY, current, disable, handle, recognizes, render, target, tick,
)

HOUSE = "synthetic-house"
NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)  # Monday, 12:00 in Kyiv


@pytest.fixture
def state():
    result = {"settings": {"modules": ["academy"], "timezone": "Europe/Kyiv"},
              "telegram": {"group_id": -100}, "outbox": {}, "members": {}}
    for i, (name, role) in enumerate([("owner", "owner"), ("parent", "parent"),
                                     ("child", "child"), ("sibling", "child"),
                                     ("guest", "guest"), ("adult", "adult")], 1):
        result["members"][name] = {"id": name, "name": name, "active": True, "role": role,
                                   "revision": 1, "telegram_id": i, "language": "en"}
    mutate(result, HOUSE, "parent", NOW, "enroll", {"member_id": "child", "member_revision": 1,
                                                   "epoch": 0, "enabled": True})
    return result


def command(state, update, content, *, actor="child", private=True, now=NOW, quoted=None):
    assert handle(state, HOUSE, actor, now, 99, update, content, private=private, quoted=quoted)
    return state["outbox"].get(f"academy:tg:99:{update}")


def message(state, event, now=NOW):
    selected = target(state, event, now)
    assert selected is not None
    return render(state, event, {**selected, "bot_id": 99}, now)


def learner(state, now=NOW):
    return project(state, HOUSE, "child", now)


def scheduled(state, kind):
    return [e for e in state["outbox"].values() if e["key"] == KEY and e["data"]["kind"] == kind]


@pytest.mark.parametrize("content", ["/academy", "/academy_start", "/academy_answer a 1/2", "ac:hint:token"])
def test_group_commands_never_write(state, content):
    before = deepcopy(state)
    assert recognizes(content)
    assert command(state, 1, content, private=False) is None
    assert state == before


@pytest.mark.parametrize("actor", ["guest", "adult"])
def test_unprivileged_actor_never_queues(state, actor):
    before = deepcopy(state)
    assert command(state, 1, "/academy", actor=actor) is None
    assert state == before


def test_private_start_hint_answer_restart_and_replay(state):
    first = command(state, 1, "/academy_start")
    prompt = message(state, first)
    assert "🟩" in prompt["text"] and prompt["chat_id"] == 3
    token = first["data"]["question_token"]
    assert len(token) == 24
    assert all(len(b["callback_data"].encode()) <= 64 for row in prompt["reply_markup"]["inline_keyboard"] for b in row)
    hint = command(state, 2, f"ac:hint:{token}")
    assert "Count" in message(state, hint)["text"]
    before = deepcopy(state)
    assert command(state, 2, f"ac:hint:{token}") == hint
    assert state == before
    paused = command(state, 3, f"ac:pause:{token}")
    assert not current(state, first, NOW)
    state = json.loads(json.dumps(state))
    token = paused["data"]["question_token"]
    resumed = command(state, 4, f"ac:resume:{token}")
    assert learner(state)["current"]["hints_used"] == 1
    invalid = command(state, 5, "1/0", quoted=resumed["data"])
    assert "valid number" in message(state, invalid)["text"]
    answered = command(state, 6, "-99", quoted=resumed["data"])
    assert "Review:" in message(state, answered)["text"]
    assert learner(state)["current"]["position"] == 1
    before = deepcopy(state["academy"])
    command(state, 7, "-99", quoted=resumed["data"])
    assert state["academy"] == before
    command(state, 8, f"/academy_answer {answered['data']['question_token']} -99")
    exit_event = state["outbox"]["academy:tg:99:8"]
    exit_msg = message(state, exit_event)
    assert "Hint" not in str(exit_msg.get("reply_markup"))
    assert "Show solution" not in str(exit_msg.get("reply_markup"))
    assert "knowledge" not in learner(state)
    done = command(state, 9, "-99", quoted=exit_event["data"])
    assert "Last mission" in message(state, done)["text"]
    assert learner(state)["current"] is None
    assert learner(state)["last_report"]["independent_total"] == 2


def test_parent_cannot_answer_as_child_and_child_cannot_configure(state):
    first = command(state, 1, "/academy_start")
    before = deepcopy(state["academy"])
    command(state, 2, f"/academy_answer {first['data']['question_token']} 1/2", actor="parent")
    command(state, 3, "/academy_schedule sibling mon 13:00")
    assert state["academy"] == before
    assert "academy_policies" not in state


def test_delivery_fenced_by_enrollment_bot_and_member(state):
    event = command(state, 1, "/academy_start")
    selected = target(state, event, NOW)
    assert render(state, event, {**selected, "bot_id": 100}, NOW) is None
    assert render(state, event, {**selected, "id": -100, "bot_id": 99}, NOW) is None
    assert not current(state, event, NOW + timedelta(minutes=5))
    mutate(state, HOUSE, "parent", NOW, "enroll", {"member_id": "child", "member_revision": 1,
                                                   "epoch": 1, "enabled": False})
    assert not current(state, event, NOW)
    mutate(state, HOUSE, "parent", NOW, "enroll", {"member_id": "child", "member_revision": 1,
                                                   "epoch": 2, "enabled": True})
    assert not current(state, event, NOW)
    state["members"]["child"]["revision"] = 2
    assert not current(state, event, NOW)


def test_schedule_no_backlog_duplicate_or_group_target(state):
    command(state, 1, "/academy_schedule child mon,tue 13:00", actor="parent")
    due = NOW + timedelta(hours=1)
    tick(state, due - timedelta(seconds=1))
    assert not scheduled(state, "reminder")
    tick(state, due)
    events = scheduled(state, "reminder")
    assert len(events) == 1
    assert message(state, events[0], due)["chat_id"] == 3
    reloaded = json.loads(json.dumps(state))
    tick(reloaded, due + timedelta(minutes=5))
    assert len(scheduled(reloaded, "reminder")) == 1
    tick(reloaded, due + timedelta(days=1, hours=2))
    assert len(scheduled(reloaded, "reminder")) == 1
    assert not current(reloaded, events[0], due + timedelta(minutes=30))
    command(reloaded, 2, "/academy_schedule child mon 14:00", actor="parent", now=due + timedelta(minutes=5))
    tick(reloaded, due + timedelta(hours=1))
    assert len(scheduled(reloaded, "reminder")) == 1
    assert not current(reloaded, events[0], due + timedelta(minutes=5))


def test_skip_and_disable_revoke_pending(state):
    command(state, 1, "/academy_schedule child mon,tue 13:00", actor="parent")
    command(state, 2, "/academy_skip child 2026-01-05", actor="owner")
    tick(state, NOW + timedelta(hours=1))
    assert not scheduled(state, "reminder")
    due = NOW + timedelta(days=1, hours=1)
    tick(state, due)
    event, = scheduled(state, "reminder")
    assert current(state, event, due)
    disable(state)
    state["settings"]["modules"] = []
    assert not current(state, event, due)
    state["settings"]["modules"] = ["academy"]
    assert not current(state, event, due)
    tick(state, due + timedelta(days=6))
    assert len(scheduled(state, "reminder")) == 1


def test_report_opt_in_weekly_private_counts(state):
    first = command(state, 1, "/academy_start")
    for i in range(2, 5):
        first = command(state, i, "-99", quoted=first["data"])
    command(state, 5, "/academy_reports child fri 19:00", actor="parent")
    friday = datetime(2026, 1, 9, 17, tzinfo=UTC)
    tick(state, friday)
    report, = scheduled(state, "report")
    body = message(state, report, friday)
    assert body["chat_id"] == 2
    assert "Completed missions: 1" in body["text"]
    assert "Independent answers: 0/3" in body["text"]
    assert "-99" not in body["text"]
    tick(state, friday + timedelta(minutes=2))
    assert len(scheduled(state, "report")) == 1
    state["members"]["parent"]["role"] = "adult"
    assert not current(state, report, friday)


def test_ambiguous_telegram_binding_fails_closed(state):
    state["members"]["sibling"]["telegram_id"] = 3
    assert command(state, 1, "/academy_start") is None


def test_dst_gap_skipped_fold_once(state):
    state["settings"]["timezone"] = "Europe/Berlin"
    command(state, 1, "/academy_schedule child sun 02:30", actor="parent")
    tick(state, datetime(2026, 3, 29, 1, 30, tzinfo=UTC))
    assert not scheduled(state, "reminder")
    first = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    tick(state, first)
    tick(state, first + timedelta(hours=1))
    assert len(scheduled(state, "reminder")) == 1


def test_disabled_module_and_unrelated_messages(state):
    assert not handle(state, HOUSE, "child", NOW, 99, 1, "/ping", private=True)
    state["settings"]["modules"] = []
    before = deepcopy(state)
    assert command(state, 2, "/academy_start") is None
    tick(state, NOW)
    assert state == before
