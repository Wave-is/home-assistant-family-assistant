"""Conservative natural commands. Every proposed action still goes through Engine."""

import re
from dataclasses import dataclass
from datetime import datetime

from ..const import PRIVILEGED
from ..domain.deadlines import extract_due, parse_due
from ..domain.validation import DomainError


@dataclass(frozen=True)
class Intent:
    action: str
    payload: dict


def normalize(value):
    return " ".join(value.casefold().replace("ё", "е").split()).strip(" .?!")


def find_member(state, value):
    lowered = normalize(value)
    matches = [
        m["id"]
        for m in state["members"].values()
        if m["active"]
        and lowered
        in {normalize(m["id"]), normalize(m["name"]), *(normalize(a) for a in m.get("aliases", []))}
    ]
    if len(matches) != 1:
        raise DomainError("unknown_member" if not matches else "ambiguous_member")
    return matches[0]


def task_target(view, explicit, refs):
    available = {task["id"] for task in view["tasks"]}
    candidates = {explicit.upper()} if explicit else {ref for ref in refs if ref.startswith("T")}
    if len(candidates) != 1:
        raise DomainError("context_required")
    target = next(iter(candidates))
    if target not in available:
        raise DomainError("not_found")
    return target


def parse(state, view, content: str, now: datetime, refs=()) -> Intent | None:
    value = content.strip()
    n = normalize(value)
    timezone = state["settings"].get("timezone", "UTC")
    if n in {
        "за что минусы",
        "за что минусы у детей",
        "почему минусы",
        "за що мінуси",
        "за що мінуси у дітей",
        "why the penalties",
        "scores",
        "статистика",
        "статистика детей",
    }:
        return Intent("read.court", {})
    if n in {
        "какие задачи",
        "список задач",
        "мои задачи",
        "мої завдання",
        "список завдань",
        "my tasks",
    }:
        return Intent("read.tasks", {})
    # Assignment grammar takes precedence over verbs within the task title.
    create = re.fullmatch(r"(.{1,80}?)\s+(?:задача|завдання|task)\s*[:.]?\s+(.+)", value, re.I)
    if create:
        member = find_member(state, create[1])
        title, due = extract_due(create[2], now, timezone)
        return Intent("tasks.create", {"assignee": member, "title": title, "due_at": due})
    revise = re.fullmatch(
        r"(?:установи\s+срок|поставь\s+срок|измени\s+срок|встанови\s+термін|зміни\s+термін|set\s+(?:the\s+)?deadline)"
        r"(?:\s+(?:задач[ие]|завдання|for)\s+)?\s*(T\d{6})?\s*[:,-]?\s*(.+)",
        value,
        re.I,
    )
    if revise:
        target = task_target(view, revise[1], refs)
        task = next(t for t in view["tasks"] if t["id"] == target)
        return Intent(
            "tasks.revise",
            {
                "id": target,
                "revision": task["revision"],
                "due_at": parse_due(revise[2], now, timezone),
            },
        )
    complete = re.fullmatch(
        r"(.{1,80}?)\s+(?:выполнил[а]?|викона[вл]а?|completed)\s+(T\d{6})", value, re.I
    )
    if complete:
        member = find_member(state, complete[1])
        target = task_target(view, complete[2], ())
        task = next(t for t in view["tasks"] if t["id"] == target)
        if task["assignee"] != member:
            raise DomainError("ambiguous_command")
        if view["role"] not in PRIVILEGED:
            return Intent("tasks.submit", {"id": target, "report": value})
        return Intent("tasks.complete", {"id": target})
    # Negations, multiple actions and other free text deliberately do not execute.
    return None
