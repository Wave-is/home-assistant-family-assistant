"""Calendar commands; group responses never include participant-only appointments."""

from ..domain.validation import DomainError

COPY = {
    "en": {
        "title": "Family calendar",
        "empty": "No upcoming events.",
        "private": "Participant-only events are shown only in a private chat or your family card.",
        "confirmed": "confirmed",
        "tentative": "awaiting parent approval",
        "cancelled": "cancelled",
        "archived": "archived",
        "reason": "reason",
        "name": "title",
    },
    "ru": {
        "title": "Семейный календарь",
        "empty": "Предстоящих событий нет.",
        "private": "Личные события доступны только в личном чате или семейной карточке.",
        "confirmed": "подтверждено",
        "tentative": "ждёт одобрения родителя",
        "cancelled": "отменено",
        "archived": "в архиве",
        "reason": "причина",
        "name": "название",
    },
    "uk": {
        "title": "Сімейний календар",
        "empty": "Майбутніх подій немає.",
        "private": "Особисті події доступні лише в особистому чаті або сімейній картці.",
        "confirmed": "підтверджено",
        "tentative": "чекає схвалення батьків",
        "cancelled": "скасовано",
        "archived": "в архіві",
        "reason": "причина",
        "name": "назва",
    },
}


def help_text(language):
    t = COPY.get(language, COPY["en"])
    return (
        f"\n/calendar\n/event {t['name']} | 2026-10-01T09:00+03:00 | 2026-10-01T10:00+03:00"
        f"\n/eventapprove E000001 | {t['reason']}\n/eventcancel E000001 | {t['reason']}"
    )


def summary(record, language, private=False):
    t = COPY.get(language, COPY["en"])
    if not private and record.get("visibility") == "participants":
        return t["private"]
    status = t["archived"] if record.get("archived") else t[record["status"]]
    return f"{record['title']} · {record['start']} · {status}"


def read(view, language, private=False):
    if "calendar" not in view["settings"]["modules"]:
        raise DomainError("module_disabled")
    if view["role"] == "guest":
        raise DomainError("forbidden")
    t = COPY.get(language, COPY["en"])
    records = {r["id"]: r for r in view["calendar"]["events"]}
    lines = ["📅 " + t["title"]]
    for item in view["calendar"]["occurrences"]:
        record = records[item["event_id"]]
        if not private and (record["visibility"] != "family" or record["status"] != "confirmed"):
            continue
        line = f"{record['id']} · {summary({**record, **item}, language, private)}"
        if sum(map(len, lines)) + len(line) > 3300:
            break
        lines.append(line)
    if len(lines) == 1:
        lines.append(t["empty"])
    if not private:
        lines.append(t["private"])
    return "\n".join(lines)


def parsed(view, command, parts):
    if command not in {"/event", "/eventapprove", "/eventcancel"}:
        return None
    if "calendar" not in view["settings"]["modules"]:
        raise DomainError("module_disabled")
    if view["role"] == "guest":
        raise DomainError("forbidden")
    if command == "/event":
        if len(parts) != 3:
            raise DomainError("invalid_field", "event")
        return "calendar.save", {"title": parts[0], "start": parts[1], "end": parts[2]}
    if len(parts) != 2:
        raise DomainError("invalid_field", "event")
    record = next((r for r in view["calendar"]["events"] if r["id"] == parts[0].upper()), None)
    if record is None:
        raise DomainError("not_found")
    return "calendar." + ("approve" if command == "/eventapprove" else "cancel"), {
        "id": record["id"],
        "revision": record["revision"],
        "reason": parts[1],
    }
