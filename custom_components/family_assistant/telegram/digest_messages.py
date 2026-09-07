"""Private, bounded, localized digests rendered only against current authority."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain import digest_content, digests
from ..notifications import DeliveryError

MAX_UNITS = 3800
COPY = {
    "en": {
        "morning": "☀️ Your morning digest",
        "evening": "🌙 Your evening digest",
        "weekly": "🗓 Your weekly digest",
        "counts": "{count} without details",
        "more": "More information is available on your family cards.",
        "all_day": "all day",
        "tasks": "Your tasks / visible task total",
        "calendar": "Calendar",
        "routines": "Current routine steps",
        "school": "School",
        "shopping": "Open shopping items · count only",
        "pantry_low_stock": "Low stock · count only",
        "pantry_expiring": "Recorded expiry · count only",
        "maintenance_faults": "Open faults · count only",
        "maintenance_services": "Active services · count only",
        "polls_open": "Available polls · count only",
        "polls_results": "Available poll results · count only",
        "assigned": "assigned",
        "accepted": "accepted",
        "in_progress": "in progress",
        "submitted": "awaiting review",
        "needs_changes": "changes requested",
    },
    "ru": {
        "morning": "☀️ Ваш утренний дайджест",
        "evening": "🌙 Ваш вечерний дайджест",
        "weekly": "🗓 Ваш недельный дайджест",
        "counts": "Без подробностей: {count}",
        "more": "Остальные подробности — в семейных карточках.",
        "all_day": "весь день",
        "tasks": "Ваши задачи / всего доступных задач",
        "calendar": "Календарь",
        "routines": "Текущие шаги рутин",
        "school": "Школа",
        "shopping": "Открытые покупки · только количество",
        "pantry_low_stock": "Мало запасов · только количество",
        "pantry_expiring": "Записанные сроки годности · только количество",
        "maintenance_faults": "Открытые поломки · только количество",
        "maintenance_services": "Активное обслуживание · только количество",
        "polls_open": "Доступные голосования · только количество",
        "polls_results": "Доступные итоги голосований · только количество",
        "assigned": "назначена",
        "accepted": "принята",
        "in_progress": "в работе",
        "submitted": "ждёт проверки",
        "needs_changes": "нужна доработка",
    },
    "uk": {
        "morning": "☀️ Ваш ранковий дайджест",
        "evening": "🌙 Ваш вечірній дайджест",
        "weekly": "🗓 Ваш тижневий дайджест",
        "counts": "Без подробиць: {count}",
        "more": "Решта подробиць — у родинних картках.",
        "all_day": "увесь день",
        "tasks": "Ваші завдання / усього доступних завдань",
        "calendar": "Календар",
        "routines": "Поточні кроки рутин",
        "school": "Школа",
        "shopping": "Відкриті покупки · лише кількість",
        "pantry_low_stock": "Мало запасів · лише кількість",
        "pantry_expiring": "Записані терміни придатності · лише кількість",
        "maintenance_faults": "Відкриті несправності · лише кількість",
        "maintenance_services": "Активне обслуговування · лише кількість",
        "polls_open": "Доступні голосування · лише кількість",
        "polls_results": "Доступні підсумки голосувань · лише кількість",
        "assigned": "призначено",
        "accepted": "прийнято",
        "in_progress": "у роботі",
        "submitted": "чекає перевірки",
        "needs_changes": "потрібне доопрацювання",
    },
}


def _text(value):
    if not isinstance(value, str):
        raise ValueError("invalid text")
    return " ".join(value.split()).encode("utf-8", errors="replace").decode()


def _units(value):
    return len(value.encode("utf-16-le")) // 2


def _moment(value, zone):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError("naive time")
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M")


def _row(key, row, copy, zone):
    if key == "tasks":
        return f"{_moment(row['due_at'], zone)} · {_text(row['title'])} · {copy[row['status']]}"
    if key == "calendar":
        start = (
            f"{row['start']} · {copy['all_day']}" if row["all_day"] else _moment(row["start"], zone)
        )
        return f"{start} · {_text(row['title'])}"
    if key == "routines":
        return f"{_text(row['routine_title'])} → {_text(row['step_title'])}"
    if key == "school":
        materials = ", ".join(_text(item) for item in row["materials"])
        return f"{row['date']} {row['start']} · {_text(row['subject'])}" + (
            f" · {materials}" if materials else ""
        )
    raise ValueError("invalid section")


def render(event, target, state, now):
    current = digests.target(state, event, now)
    if (
        current is None
        or target.get("channel") != "telegram"
        or type(target.get("id")) is not int
        or target["id"] != current["id"]
    ):
        raise DeliveryError("delivery_revoked")
    data = event["data"]
    actor = state["members"][event["recipient"]]
    snapshot = digest_content.snapshot(
        state, actor, data["kind"], data["window_start"], data["window_end"], now
    )
    if not digest_content.has_content(snapshot):
        raise DeliveryError("delivery_revoked")
    copy = COPY[current["language"]]
    try:
        zone = ZoneInfo(state["settings"]["timezone"])
        last = (date.fromisoformat(snapshot["window_end"]) - timedelta(days=1)).isoformat()
        period = (
            snapshot["window_start"]
            if last == snapshot["window_start"]
            else f"{snapshot['window_start']} — {last}"
        )
        message = f"{copy[data['kind']]}\n{period} · {zone}"
        omitted = False
        for section in snapshot["sections"]:
            block = f"\n\n{copy[section['key']]}: {section['count']}"
            shown = 0
            for row in section["rows"]:
                line = "\n• " + _row(section["key"], row, copy, zone)
                if _units(message + block + line) > MAX_UNITS - 160:
                    omitted = True
                    break
                block += line
                shown += 1
            if section["count"] > shown and section["key"] in digest_content.DETAIL_KEYS:
                block += "\n" + copy["counts"].format(count=section["count"] - shown)
            if _units(message + block) > MAX_UNITS - 100:
                omitted = True
                break
            message += block
        if omitted:
            message += "\n\n" + copy["more"]
        if _units(message) > MAX_UNITS:
            raise ValueError("message limit")
    except (KeyError, TypeError, ValueError, OverflowError):
        raise DeliveryError("notification_template_missing") from None
    return {
        "chat_id": current["id"],
        "text": message,
        "link_preview_options": {"is_disabled": True},
    }
