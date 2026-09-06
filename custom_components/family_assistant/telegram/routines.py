"""Private, typed routine commands and actor-bound step callbacks."""

import re

from ..domain.validation import DomainError
from .intents import find_member

COPY = {
    "en": {
        "title": "Routines",
        "private": "Open my private chat to view or manage routines.",
        "empty": "No routines yet.",
        "active": "in progress",
        "completed": "completed",
        "skipped": "skipped",
        "cancelled": "cancelled",
        "confirm": "Step done",
        "saved": "Routine settings saved.",
        "member": "member",
        "reason": "reason",
        "normal": "normal",
        "holidays": "holidays",
        "guests": "guests",
        "ill": "ill",
        "vacation": "vacation",
    },
    "ru": {
        "title": "Рутины",
        "private": "Откройте личный чат со мной для просмотра и управления рутинами.",
        "empty": "Рутин пока нет.",
        "active": "выполняется",
        "completed": "завершена",
        "skipped": "пропущена",
        "cancelled": "отменена",
        "confirm": "Шаг выполнен",
        "saved": "Настройки рутин сохранены.",
        "member": "участник",
        "reason": "причина",
        "normal": "обычный",
        "holidays": "каникулы",
        "guests": "гости",
        "ill": "болеем",
        "vacation": "отпуск",
    },
    "uk": {
        "title": "Рутини",
        "private": "Відкрийте особистий чат зі мною для перегляду та керування рутинами.",
        "empty": "Рутин поки немає.",
        "active": "виконується",
        "completed": "завершена",
        "skipped": "пропущена",
        "cancelled": "скасована",
        "confirm": "Крок виконано",
        "saved": "Налаштування рутин збережено.",
        "member": "учасник",
        "reason": "причина",
        "normal": "звичайний",
        "holidays": "канікули",
        "guests": "гості",
        "ill": "хворіємо",
        "vacation": "відпустка",
    },
}


def help_text(language):
    t = COPY.get(language, COPY["en"])
    return (
        f"\n/routines\n/routine morning | {t['member']}\n/routinestart U000001 | {t['member']}"
        f"\n/routinecancel J000001 | {t['reason']}"
        "\n/routinemode holidays, guests\n/routinemode normal"
    )


def summary(record, language, private=False):
    t = COPY.get(language, COPY["en"])
    if not private:
        return t["private"]
    if "modes" in record:
        return t["saved"] + " " + ", ".join(t[m] for m in record["modes"])
    return f"{record['id']} · {record['title']}" + (
        " · " + t[record["status"]] if "status" in record else ""
    )


def read(view, language, private=False):
    if "routines" not in view["settings"]["modules"]:
        raise DomainError("module_disabled")
    if view["role"] == "guest":
        raise DomainError("forbidden")
    t = COPY.get(language, COPY["en"])
    if not private:
        return t["private"]
    lines = [t["title"]]
    for record in view["routines"]["templates"] + view["routines"]["runs"][-20:]:
        line = summary(record, language, True)
        if len("\n".join(lines)) + len(line) > 3300:
            break
        lines.append(line)
    return "\n".join(lines) if len(lines) > 1 else t["empty"]


def parsed(state, view, command, parts, private):
    if command not in {"/routine", "/routinestart", "/routinecancel", "/routinemode"}:
        return None
    if not private or view["role"] == "guest":
        raise DomainError("forbidden")
    if "routines" not in view["settings"]["modules"]:
        raise DomainError("module_disabled")
    if command == "/routinemode":
        if len(parts) != 1:
            raise DomainError("invalid_field", "modes")
        return "routines.modes", {
            "modes": [p.strip() for p in parts[0].split(",")],
            "revision": view["routines"]["config"]["revision"],
        }
    if len(parts) != 2:
        raise DomainError("invalid_field", "routine")
    if command == "/routine":
        preset = next((p for p in view["routines"]["presets"] if p["id"] == parts[0]), None)
        if preset is None:
            raise DomainError("not_found")
        return "routines.save", {
            **{k: v for k, v in preset.items() if k != "id"},
            "assignees": [find_member(state, parts[1])],
        }
    bucket = "templates" if command == "/routinestart" else "runs"
    record = next((r for r in view["routines"][bucket] if r["id"] == parts[0].upper()), None)
    if record is None:
        raise DomainError("not_found")
    payload = {"id": record["id"], "revision": record["revision"]}
    if command == "/routinestart":
        payload["member"] = find_member(state, parts[1])
        return "routines.start", payload
    return "routines.cancel", {**payload, "reason": parts[1]}


def callback(content):
    match = re.fullmatch(r"fr:(J\d{6,12}):(\d{1,2}):(\d{1,16}):([A-Za-z0-9_-]{24})", content)
    if match is None:
        raise DomainError("invalid_field", "callback")
    return {"id": match[1], "step": int(match[2]), "revision": int(match[3]), "nonce": match[4]}
