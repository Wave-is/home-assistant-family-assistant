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
        "in_stock": "in stock",
        "out_of_stock": "out of stock",
        "preorder": "pre-order",
        "backorder": "backorder",
        "discontinued": "discontinued",
        "unknown_status": "awaiting check",
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
        "in_stock": "в наличии",
        "out_of_stock": "нет в наличии",
        "preorder": "предзаказ",
        "backorder": "под заказ",
        "discontinued": "снят с продажи",
        "unknown_status": "ожидает проверки",
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
        "in_stock": "в наявності",
        "out_of_stock": "немає в наявності",
        "preorder": "передзамовлення",
        "backorder": "під замовлення",
        "discontinued": "знято з продажу",
        "unknown_status": "очікує перевірки",
        "days": ("пн", "вт", "ср", "чт", "пт", "сб", "нд"),
    },
}


def summary(item, view, language):
    words = WORDS.get(language, WORDS["en"])
    if "url" in item and (str(item.get("id", "")).startswith("PW") or "price_text" in item):
        parts = [item.get("name", "")]
        price_text = item.get("price_text", "")
        currency = item.get("currency", "")
        if price_text:
            parts.append(f"{price_text} {currency}".strip())
        avail = item.get("availability")
        if avail and avail != "unknown":
            parts.append(words.get(avail, avail))
        elif avail == "unknown" and not price_text:
            parts.append(words.get("unknown_status", "awaiting check"))
        return " · ".join(part for part in parts if part)
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
        detail = item.get("reason_data", {})
        reference = detail.get("task_id") or detail.get("run_id")
        if reference:
            parts.append(reference)
        task = next((t for t in view.get("tasks", []) if t["id"] == detail.get("task_id")), None)
        if task:
            parts.append(task["title"])
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


def court_stats(view, language, *, weekly=False):
    """Totals and bounded reasons come from the same authorized ledger projection."""
    labels = {
        "en": (
            "Court ledger · current balances",
            "Current week",
            "No score events.",
            "More records are available in the court card.",
            "reversed",
        ),
        "ru": (
            "Журнал суда · текущие балансы",
            "Текущая неделя",
            "Начислений нет.",
            "Остальные записи доступны в карточке суда.",
            "отменено",
        ),
        "uk": (
            "Журнал суду · поточні баланси",
            "Поточний тиждень",
            "Нарахувань немає.",
            "Решта записів доступні в картці суду.",
            "скасовано",
        ),
    }
    title, week_title, empty, more, reversed_word = labels.get(language, labels["en"])
    records = view["court"]
    if weekly:
        period = view.get("court_summary")
        if not period:
            return empty
        zone = ZoneInfo(period["timezone"])
        start, end = (timestamp(period[key], key).astimezone(zone) for key in ("start", "end"))
        title = (
            f"{week_title}: {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M} ({period['timezone']})"
        )
        ids = set(period["events"])
        records = [record for record in records if record["id"] in ids]
    lines = ["⚖️ " + title]
    if not records:
        return "\n".join(lines + [empty])
    totals = {}
    for item in records:
        value = totals.setdefault(item["member"], {"positive": 0, "negative": 0, "reversed": 0})
        if item["status"] == "reversed":
            value["reversed"] += 1
        elif item["points"] > 0:
            value["positive"] += item["points"]
        else:
            value["negative"] += item["points"]
    for member in view["members"]:
        if member["id"] not in totals:
            continue
        value = totals[member["id"]]
        lines.append(
            f"{member['name']}: +{value['positive']} / {value['negative']} "
            f"= {value['positive'] + value['negative']:+d} · {reversed_word}: {value['reversed']}"
        )
    for item in sorted(
        records, key=lambda record: timestamp(record["created_at"], "created_at"), reverse=True
    ):
        line = f"{item['id']} · {summary(item, view, language)}"
        if len(line) > 240:
            line = line[:237] + "…"
        if len("\n".join(lines)) + len(line) > 3400:
            lines.append(more)
            break
        lines.append(line)
    return "\n".join(lines)[:3800]
