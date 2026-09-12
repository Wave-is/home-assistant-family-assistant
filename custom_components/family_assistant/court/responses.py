"""Localized response texts for Family Court."""

from __future__ import annotations

import hashlib
from typing import Any

from .parser import display_child

PLUS_VARIANTS: tuple[str, ...] = (
    "🏅 Сенсация подтверждена свидетелями.",
    "📈 Семейная статистика неожиданно пошла вверх.",
    "✅ Следствие временно не имеет вопросов.",
    "🎖️ Канцелярия зарегистрировала достойный поступок.",
    "🌟 Прокуратура нехотя признаёт: это было хорошо.",
    "📜 В личное дело подшит приятный документ.",
    "🕊️ Сегодня судебный молоток используется для аплодисментов.",
    "🫡 Хороший поступок принят на государственный семейный учёт.",
    "🔔 Заседание прервано редким сообщением о хорошем поведении.",
    "🧾 Бюрократия всё проверила: плюс настоящий.",
    "🏛️ Верховный Семейный Суд выражает осторожное одобрение.",
    "✨ Репутационный капитал официально вырос.",
    "📚 Летопись семьи пополнилась приятной главой.",
    "🧑‍⚖️ Суд постановил похвалить без лишних проволочек.",
    "🥇 Комиссия по хорошим поступкам наконец получила работу.",
    "📬 В канцелярию доставлено доказательство благонадёжности.",
    "🎉 Обвинительная сторона на минуту снимает мантию.",
    "🪄 Неожиданный поворот дела: всё сделано правильно.",
    "🗂️ Папка «Молодец» торжественно пополнена.",
    "⚖️ Семейный кодекс сегодня применён в поощрительном режиме.",
)

MINUS_VARIANTS: tuple[str, ...] = (
    "⚖️ Дело принято к производству.",
    "📉 Репутационный индекс официально просел.",
    "🚨 Семейная прокуратура открыла новое производство.",
    "🧾 Косяк зарегистрирован, пронумерован и подшит.",
    "🔨 Судебный молоток снова вышел на работу.",
    "📜 Материалы дела пополнились тревожной страницей.",
    "🕵️ Следствие закончено подозрительно быстро.",
    "🏛️ Верховный Семейный Суд принял сведения к учёту.",
    "📬 Канцелярия получила очередное саморазоблачающее письмо.",
    "🗃️ Архив правонарушений радостно распахнул ящик.",
    "⛔ Протокол составлен без скидок на хорошую погоду.",
    "🔔 Внеочередное заседание началось по печальному поводу.",
    "🧑‍⚖️ Обвинительная сторона выглядит слишком довольной.",
    "📋 Комиссия обнаружила материал для статистики.",
    "🧨 В журнал добавлена ещё одна запись.",
    "🚓 Семейный патруль внёс эпизод в реестр.",
    "🪪 Личное дело стало на одну запись толще.",
    "📢 Прокуратура сообщает: незамеченным это не осталось.",
    "🧮 Счётчик косяков подтвердил, что умеет считать.",
    "🛎️ Канцелярский колокольчик прозвенел недобро.",
)


COPY = {
    "en": {
        "title": "Family court",
        "history": "Current score reasons",
        "case": "Score history",
        "period": "Reporting period",
        "empty": "No active records in this period.",
        "reason": "Reason",
        "task_missed": "Task deadline was missed",
        "alarm_missed": "Wake-up was not confirmed",
        "system": "System",
        "more": "Additional records",
        "saved": "Score recorded.",
        "reached": "threshold reached",
        "remaining": "points to threshold",
        "appeal": "To appeal: /appeal record ID | reason",
        "help": "/stats · /week · /history · /дело member · /rules. Parents: /undo.",
        "rules": "Scores retain their reasons and history. Parents can reverse scores; "
        "members can appeal their own records with /appeal record ID | reason. "
        "Weekly reports follow the household settings and do not reset balances.",
        "denied": "You do not have permission for this court action.",
        "ambiguous": "No score recorded. Specify one member, score and reason per clause.",
        "missing": "Specify a configured member name or alias and the reason.",
        "undo_ok": "The score was reversed. Its original record remains in the history.",
        "undo_empty": "No active score to reverse in this period.",
        "launch": "Family court is available. Use /stats for scores and /rules for guidance.",
    },
    "ru": {
        "title": "Семейный суд",
        "history": "Причины текущих начислений",
        "case": "История баллов",
        "period": "Отчётный период",
        "empty": "В этом периоде нет действующих записей.",
        "reason": "Причина",
        "task_missed": "Задача не выполнена к сроку",
        "alarm_missed": "Подъём не подтверждён",
        "system": "Система",
        "more": "Дополнительных записей",
        "saved": "Оценка записана.",
        "reached": "порог достигнут",
        "remaining": "баллов до порога",
        "appeal": "Для апелляции: /appeal ID записи | причина",
        "help": "/stats · /week · /history · /дело участник · /rules. Родителям: /undo.",
        "rules": "Баллы сохраняют причины и историю. Родители могут отменить оценку; "
        "участники могут обжаловать свои записи: /appeal ID записи | причина. "
        "Недельные отчёты следуют настройкам семьи и не обнуляют баланс.",
        "denied": "У вас нет прав на это действие суда.",
        "ambiguous": "Ничего не записано. Укажите участника, оценку и причину для каждого пункта.",
        "missing": "Укажите настроенное имя или обращение участника и причину.",
        "undo_ok": "Оценка отменена. Исходная запись сохранена в истории.",
        "undo_empty": "В текущем периоде нет действующих оценок для отмены.",
        "launch": "Семейный суд доступен. Баллы: /stats. Справка: /rules.",
    },
    "uk": {
        "title": "Сімейний суд",
        "history": "Причини поточних нарахувань",
        "case": "Історія балів",
        "period": "Звітний період",
        "empty": "У цьому періоді немає чинних записів.",
        "reason": "Причина",
        "task_missed": "Завдання не виконано до терміну",
        "alarm_missed": "Підйом не підтверджено",
        "system": "Система",
        "more": "Додаткових записів",
        "saved": "Оцінку записано.",
        "reached": "поріг досягнуто",
        "remaining": "балів до порогу",
        "appeal": "Для апеляції: /appeal ID запису | причина",
        "help": "/stats · /week · /history · /дело учасник · /rules. Батькам: /undo.",
        "rules": "Бали зберігають причини та історію. Батьки можуть скасувати оцінку; "
        "учасники можуть оскаржити власні записи: /appeal ID запису | причина. "
        "Щотижневі звіти відповідають налаштуванням родини й не обнуляють баланс.",
        "denied": "У вас немає прав на цю дію суду.",
        "ambiguous": "Нічого не записано. Вкажіть учасника, оцінку й причину для кожного пункту.",
        "missing": "Вкажіть налаштоване ім’я або звертання учасника й причину.",
        "undo_ok": "Оцінку скасовано. Початковий запис збережено в історії.",
        "undo_empty": "У поточному періоді немає чинних оцінок для скасування.",
        "launch": "Сімейний суд доступний. Бали: /stats. Довідка: /rules.",
    },
}


def localized(key: str, language: str = "ru") -> str:
    return COPY.get(language, COPY["en"])[key]


def _variant(items: tuple[str, ...], seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return items[int.from_bytes(digest[:4], "big") % len(items)]


def signed(value: int) -> str:
    return f"{value:+d}".replace("-", "−")


def assessment_response(
    child: str,
    kind: str,
    stats: dict[str, Any],
    reason: str,
    seed: str,
    *,
    language: str = "ru",
) -> str:
    """Report the stored score without promising an unconfigured consequence."""
    name = stats.get("name", display_child(child))
    header = (
        _variant(PLUS_VARIANTS if kind == "plus" else MINUS_VARIANTS, seed)
        if language == "ru"
        else localized("saved", language)
    )
    delta = "+1" if kind == "plus" else "−1"
    return (
        f"{header}\n{name}: {delta} · 👍 {stats['pluses']} · − {stats['minuses']} · "
        f"⚖️ {signed(stats['balance'])}.\n{localized('reason', language)}: {reason}."
    )


def stats_line(child: str, stats: dict[str, Any], *, language: str = "ru") -> str:
    result = (
        f"{stats.get('name', display_child(child))}: 👍 {stats['pluses']} | "
        f"− {stats['minuses']} | ⚖️ {signed(stats['balance'])}"
    )
    for rule in stats.get("thresholds", []):
        status = (
            localized("reached", language)
            if rule["reached"]
            else f"{localized('remaining', language)}: {rule['remaining']}"
        )
        result += f"\n  {rule['label']}: {status}."
    return result


def all_stats(
    stats_by_child: dict[str, dict[str, Any]],
    week_id: str,
    *,
    language: str = "ru",
) -> str:
    lines = [localized("title", language), ""]
    lines.extend(
        stats_line(child, stats, language=language) for child, stats in stats_by_child.items()
    )
    lines.extend(("", f"{localized('period', language)}: {week_id}."))
    return "\n".join(lines)


def history_report(
    history_by_child: dict[str, list[dict[str, Any]]],
    *,
    kind: str | None = None,
    names: dict[str, str] | None = None,
    language: str = "ru",
) -> str:
    """Render only the supplied authorized history, preserving actual point values."""
    lines = [localized("history", language)]
    for child, history in history_by_child.items():
        records = [r for r in history if kind is None or r.get("type") == kind]
        lines.extend(("", f"{display_child(child, names)}:"))
        if not records:
            lines.append(localized("empty", language))
        for record in records[-10:]:
            points = record.get("points", 1 if record.get("type") == "plus" else -1)
            actor = record.get("parent_name") or localized("system", language)
            reason = record.get("reason", "")
            if not reason and record.get("reason_key") in {"task_missed", "alarm_missed"}:
                reason = localized(record["reason_key"], language)
                reference = record.get("reason_data", {})
                source_id = reference.get("task_id") or reference.get("run_id")
                if source_id:
                    reason += f" · {source_id}"
            lines.append(f"• {signed(points)} — {reason} · {actor}")
        if len(records) > 10:
            lines.append(f"{localized('more', language)}: {len(records) - 10}")
    return "\n".join(lines)


def case_report(
    child: str,
    stats: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    language: str = "ru",
) -> str:
    return (
        f"{localized('case', language)}\n{stats_line(child, stats, language=language)}\n"
        + history_report(
            {child: history}, names={child: stats.get("name", child)}, language=language
        )
    )


def weekly_report(
    stats_by_child: dict[str, dict[str, Any]],
    week_id: str,
    *,
    language: str = "ru",
) -> str:
    """Present a report without claiming that balances were reset."""
    return all_stats(stats_by_child, week_id, language=language)


HELP_TEXT = localized("help")
RULES_TEXT = localized("rules")
DENIED_TEXT = localized("denied")
APPEAL_TEXT = localized("appeal")
AMBIGUOUS_TEXT = localized("ambiguous")
MISSING_CHILD_TEXT = localized("missing")
UNDO_OK_TEXT = localized("undo_ok")
UNDO_EMPTY_TEXT = localized("undo_empty")
LAUNCH_TEXT = localized("launch")
