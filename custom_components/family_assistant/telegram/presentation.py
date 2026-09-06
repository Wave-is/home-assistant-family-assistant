"""Human-readable, localized record summaries with no provider or access data."""

from zoneinfo import ZoneInfo

from ..domain.validation import timestamp

WORDS = {
    "en": {
        "assigned": "assigned",
        "accepted": "accepted",
        "in_progress": "in progress",
        "submitted": "awaiting review",
        "needs_changes": "needs changes",
        "completed": "completed",
        "active": "active",
        "reversed": "reversed",
        "pending": "awaiting approval",
        "approved": "ready to buy",
        "purchased": "bought",
        "enabled": "enabled",
        "disabled": "disabled",
        "alarm_missed": "Wake-up was not confirmed within 30 minutes",
        "task_missed": "Task was not completed by its deadline",
        "record": "record",
        "cancelled": "cancelled",
        "archived": "archived",
        "rejected": "rejected",
        "days": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    },
    "ru": {
        "assigned": "назначена",
        "accepted": "принята",
        "in_progress": "в работе",
        "submitted": "ждёт проверки",
        "needs_changes": "на доработке",
        "completed": "выполнена",
        "active": "действует",
        "reversed": "отменён",
        "pending": "ждёт одобрения",
        "approved": "можно покупать",
        "purchased": "куплено",
        "enabled": "включён",
        "disabled": "выключен",
        "alarm_missed": "Подъём не подтверждён за 30 минут",
        "task_missed": "Задача не выполнена к сроку",
        "record": "запись",
        "cancelled": "отменена",
        "archived": "в архиве",
        "rejected": "отклонено",
        "days": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
    },
    "uk": {
        "assigned": "призначено",
        "accepted": "прийнято",
        "in_progress": "у роботі",
        "submitted": "чекає перевірки",
        "needs_changes": "на доопрацюванні",
        "completed": "виконано",
        "active": "діє",
        "reversed": "скасовано",
        "pending": "чекає схвалення",
        "approved": "можна купувати",
        "purchased": "куплено",
        "enabled": "увімкнено",
        "disabled": "вимкнено",
        "alarm_missed": "Підйом не підтверджено за 30 хвилин",
        "task_missed": "Завдання не виконано до терміну",
        "record": "запис",
        "cancelled": "скасовано",
        "archived": "в архіві",
        "rejected": "відхилено",
        "days": ("пн", "вт", "ср", "чт", "пт", "сб", "нд"),
    },
}


def summary(item, view, language):
    words = WORDS.get(language, WORDS["en"])
    name = next(
        (m["name"] for m in view["members"] if m["id"] == item.get("member", item.get("assignee"))),
        "",
    )
    parts = [item.get("title", item.get("name", "")), name]
    if "quantity" in item:
        parts.append(f"{item['quantity'] - item['purchased']:g} {item['unit']}")
    if "points" in item:
        parts += [
            f"{item['points']:+d}",
            item.get("reason") or words.get(item.get("reason_key"), words["record"]),
        ]
    if "days" in item:
        parts += [
            item["time"],
            ", ".join(words["days"][day] for day in item["days"]),
            item["timezone"],
            words["enabled" if item["enabled"] else "disabled"],
        ]
    if item.get("due_at"):
        zone = view["settings"].get("timezone", "UTC")
        due = timestamp(item["due_at"], "due_at").astimezone(ZoneInfo(zone))
        parts.append(f"📅 {due:%Y-%m-%d %H:%M} ({zone})")
    if "status" in item:
        parts.append(words.get(item["status"], words["record"]))
    return " · ".join(part for part in parts if part)
