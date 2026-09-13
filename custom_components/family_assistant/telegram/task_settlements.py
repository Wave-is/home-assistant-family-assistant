"""Exact completed-task corrections, never the generic latest-score undo."""

import re

from ..domain.task_settlements import correction_payload
from ..domain.validation import DomainError
from .intents import task_target

COPY = {
    "en": {
        "reversed": "The exact same-day task penalty was reversed.",
        "already_reversed": "That exact task penalty was already reversed.",
        "needs_review": "Task completed. Its exact penalty needs separate parent review.",
        "reason": "Parent reviewed this task's same-day penalty",
    },
    "ru": {
        "reversed": "Отменён точный штраф этой задачи за день выполнения.",
        "already_reversed": "Этот точный штраф задачи уже отменён.",
        "needs_review": "Задача выполнена. Её точный штраф требует отдельной проверки родителем.",
        "reason": "Родитель проверил точный штраф задачи за день выполнения",
    },
    "uk": {
        "reversed": "Скасовано точний штраф цього завдання за день виконання.",
        "already_reversed": "Цей точний штраф завдання вже скасовано.",
        "needs_review": "Завдання виконано. Його точний штраф потребує окремої перевірки батьками.",
        "reason": "Батьки перевірили точний штраф завдання за день виконання",
    },
}


def parsed(state, view, content, refs, language):
    value = content.strip()
    match = re.fullmatch(
        r"(?:/correcttask|исправь\s+штраф\s+за|виправ\s+штраф\s+за|correct\s+(?:the\s+)?penalty\s+for)\s+(T\d{6,})(?:\s*\|\s*(.+))?",
        value,
        re.I,
    )
    contextual = re.fullmatch(
        r"исправь\s+штраф\s+за\s+эту\s+задачу|виправ\s+штраф\s+за\s+це\s+завдання|correct\s+(?:the\s+)?penalty\s+for\s+this\s+task",
        value,
        re.I,
    )
    if not match and not contextual:
        if re.match(
            r"/correcttask\b|(?:исправь|виправ)\s+штраф\b|correct\s+(?:the\s+)?penalty\b",
            value,
            re.I,
        ):
            raise DomainError("context_required")
        return None
    if view["role"] not in {"owner", "parent"}:
        raise DomainError("forbidden")
    task_id = task_target(view, match[1] if match else None, refs)
    task = state["tasks"][task_id]
    payload = correction_payload(state, task, state["members"][view["actor"]])
    payload["reason"] = match[2] if match and match[2] else COPY[language]["reason"]
    return "tasks.correct_miss", payload


def reply(result, language):
    status = result.get("correction_status")
    return f"{result['id']} · {COPY[language][status]}" if status in COPY[language] else None
