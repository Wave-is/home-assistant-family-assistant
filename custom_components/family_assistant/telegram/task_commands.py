"""Explicit compatibility commands translated to the canonical domain contracts."""

import re

from ..domain.deadlines import parse_due
from ..domain.shopping import normalized_name
from ..domain.validation import DomainError
from .intents import find_member, task_target


def shopping_target(view, value):
    if re.fullmatch(r"S\d{6,}", value, re.I):
        target = value.upper()
        if not any(row["id"] == target for row in view["shopping"]):
            raise DomainError("not_found")
        return target
    candidates = [
        row["id"]
        for row in view["shopping"]
        if row.get("status") in {"pending", "approved"}
        and normalized_name(row["name"]) == normalized_name(value)
    ]
    if len(candidates) != 1:
        raise DomainError("ambiguous_command" if candidates else "not_found")
    return candidates[0]


def parsed(state, view, command, tail, now, refs=()):
    """Return action/payload only; the router freezes revisions and Engine checks roles."""
    if command in {"/accept", "/begin", "/archive", "/canceltask"}:
        if not re.fullmatch(r"T\d{6,}", tail, re.I):
            raise DomainError("context_required")
        target = task_target(view, tail, refs)
        action = {
            "/accept": "accept",
            "/begin": "start",
            "/archive": "archive",
            "/canceltask": "cancel",
        }[command]
        return "tasks." + action, {"id": target}
    if command in {"/approvebuy", "/rejectbuy"}:
        return "shopping." + ("approve" if command == "/approvebuy" else "reject"), {
            "id": shopping_target(view, tail),
        }
    if command == "/changes":
        match = re.fullmatch(r"(T\d{6,})\s*(?:\||\s)\s*(.+)", tail, re.I)
        if not match:
            raise DomainError("context_required")
        return "tasks.request_changes", {
            "id": task_target(view, match[1], refs),
            "note": match[2].strip(),
        }
    if command == "/edit":
        match = re.fullmatch(
            r"(T\d{6,})\s+(срок|термін|deadline|текст|title|text|исполнитель|виконавець|assignee)"
            r"\s+(.+)",
            tail,
            re.I,
        )
        if not match:
            raise DomainError("ambiguous_command")
        payload = {"id": task_target(view, match[1], refs)}
        field, value = match[2].casefold(), match[3].strip()
        if field in {"срок", "термін", "deadline"}:
            payload["due_at"] = parse_due(value, now, state["settings"]["timezone"])
        elif field in {"исполнитель", "виконавець", "assignee"}:
            payload["assignee"] = find_member(state, value)
        else:
            payload["title"] = value
        return "tasks.revise", payload
    return None


def help_text(language):
    return {
        "en": (
            "\n/mine — my tasks\n/accept ID · /begin ID\n/changes ID | reason\n"
            "/edit ID deadline tomorrow · /edit ID title new title\n/archive ID · /canceltask ID\n"
            "/approvebuy ID · /rejectbuy ID\n/ask question\n"
            "/learn phrase | command · /forgetphrase ID\n"
            "/alarm member | weekdays or weekends | HH:MM, on or off\n"
            "Reminders: remind me to call tomorrow at 18:00"
        ),
        "ru": (
            "\n/mine — мои дела\n/accept ID — принять · /begin ID — начать\n"
            "/changes ID | причина — доработать\n"
            "/edit ID срок завтра · /edit ID текст новый текст\n"
            "/archive ID — архив · /canceltask ID — отмена задачи\n"
            "/approvebuy ID · /rejectbuy ID — решение по покупке\n/ask вопрос\n"
            "/learn фраза | команда · /forgetphrase ID\n"
            "/alarm участник | будни или выходные | ЧЧ:ММ, on или off\n"
            "Напоминания: напомни мне позвонить завтра в 18:00"
        ),
        "uk": (
            "\n/mine — мої справи\n/accept ID — прийняти · /begin ID — почати\n"
            "/changes ID | причина — доопрацювати\n"
            "/edit ID термін завтра · /edit ID текст новий текст\n"
            "/archive ID — архів · /canceltask ID — скасувати завдання\n"
            "/approvebuy ID · /rejectbuy ID — рішення щодо покупки\n/ask запитання\n"
            "/learn фраза | команда · /forgetphrase ID\n"
            "/alarm учасник | будні або вихідні | ГГ:ХХ, on або off\n"
            "Нагадування: нагадай мені зателефонувати завтра о 18:00"
        ),
    }[language]
