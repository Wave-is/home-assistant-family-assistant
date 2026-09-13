"""Explicit numbered task creation; one fully validated, identity-bound batch."""

import re

from ..const import PRIVILEGED
from ..domain.validation import DomainError, text
from .creation import task_details
from .intents import TASK_CREATE_PATTERNS, find_member, parse

VERBS = (
    r"создай(?:те)?|добавь(?:те)?|поставь(?:те)?|назначь(?:те)?|дай(?:те)?|"
    r"створи|створіть|додай(?:те)?|признач(?:те)?|create|add|assign|give"
)
TASKS = r"задачи|задач|завдання|завдань|tasks"
TASK_WORD = r"задач(?:а|и|у|е)?|завдання|завдань|tasks?"
NEGATION = r"не|ні|not|never|don't|do\s+not"
COUNT_LIKE = (
    r"[+\-\d.,/]+|zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"ноль|нуль|одну|одна|две|два|дві|три|четыре|чотири|пять|п'ять|п’ять|шість|шесть"
)
HEADER = re.compile(rf"^(?:(?:{VERBS})\s+)?([2-5])\s+(?:{TASKS})(?:\s+(.+))?$", re.I)
DECLARATION = re.compile(
    rf"^(?:(?:{NEGATION})\s+)?(?:(?:{VERBS})\s+)?(?:{COUNT_LIKE})\s+(?:{TASK_WORD})\b", re.I
)
NUMBERED = re.compile(r"^([1-5])([.)])\s+(.+)$")
EXPLICIT_MEMBER = re.compile(r"^(?:для|for)\s+(.{1,80}?)\s*:\s*(.+)$", re.I)


def candidate(content):
    """Claim explicit declarations, including malformed ones, before other routes."""
    if content.lstrip().startswith("/"):
        return False  # Explicit slash commands retain their literal argument grammar.
    lines = content.strip().splitlines()
    if not lines:
        return False
    first = lines[0].strip()
    return bool(
        DECLARATION.match(first)
        or (
            re.search(rf"\b(?:{TASK_WORD})\b", first, re.I)
            and any(re.match(r"\s*\d+[.)]", line) for line in lines[1:])
        )
    )


def _explicit(state, view, content, now):
    """Only a complete single assignment or a delimited 'for MEMBER: TITLE'."""
    if content.startswith("/") or candidate(content):
        raise DomainError("invalid_field", "commands")
    if match := EXPLICIT_MEMBER.fullmatch(content):
        return {
            "assignee": find_member(state, match[1]),
            **task_details(content=match[2], now=now, timezone=state["settings"]["timezone"]),
        }
    unnegated = re.sub(rf"^(?:{NEGATION})\s+", "", content, flags=re.I)
    if unnegated != content and (
        EXPLICIT_MEMBER.fullmatch(unnegated)
        or any(pattern.fullmatch(unnegated) for pattern in TASK_CREATE_PATTERNS)
    ):
        raise DomainError("invalid_field", "commands")
    if any(pattern.fullmatch(content) for pattern in TASK_CREATE_PATTERNS):
        intent = parse(state, view, content, now)
        if intent is None or intent.action != "tasks.create":
            raise DomainError("invalid_field", "commands")
        return intent.payload
    return None


def parsed(state, view, content, now):
    """Return a batch payload, or None for ordinary non-batch messages.

    Once claimed, errors must bypass generic model/name repair. No calls here
    write a plan, allocate task IDs, or mutate the Engine.
    """
    if not candidate(content):
        return None
    if len(content) > 4096:
        raise DomainError("command_too_large")
    lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
    if not lines[0].endswith(":"):
        raise DomainError("invalid_field", "commands")
    header = HEADER.fullmatch(lines[0][:-1].rstrip())
    if header is None or len(lines) - 1 != int(header[1]):
        raise DomainError("invalid_field", "commands")
    timezone = state["settings"]["timezone"]
    defaults = task_details(header[2] or "", now, timezone, allow_empty_title=True)
    shared_member = find_member(state, defaults["title"]) if defaults["title"] else None
    commands = []
    delimiter = None
    for index, line in enumerate(lines[1:], 1):
        match = NUMBERED.fullmatch(line)
        if match is None or int(match[1]) != index:
            raise DomainError("invalid_field", "commands")
        if delimiter is not None and match[2] != delimiter:
            raise DomainError("invalid_field", "commands")
        delimiter = match[2]
        payload = _explicit(state, view, match[3], now)
        if payload is None:
            if shared_member is None:
                raise DomainError("context_required")
            payload = {"assignee": shared_member, **task_details(match[3], now, timezone)}
        member = state["members"][payload["assignee"]]
        if view["role"] == "guest" or (
            view["role"] not in PRIVILEGED and member["id"] != view["actor"]
        ):
            raise DomainError("forbidden")
        if not member["active"] or member["role"] == "guest":
            raise DomainError("invalid_field", "assignee")
        payload["title"] = text(payload["title"], "title")
        payload["assignee_revision"] = member["revision"]
        if payload["due_at"] is None:
            payload["due_at"] = defaults["due_at"]
        payload.setdefault("report_type", defaults.get("report_type", "text"))
        commands.append({"action": "tasks.create", "payload": payload})
    return {"commands": commands}
