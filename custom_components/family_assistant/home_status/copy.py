"""Bounded trilingual factual readouts; never physical activity claims."""

from datetime import datetime

ROWS = {
    "role_owner": ("Owner", "Владелец", "Власник"),
    "role_parent": ("Parent", "Родитель", "Батько / мати"),
    "role_adult": ("Adult", "Взрослый", "Дорослий"),
    "role_child": ("Child", "Ребёнок", "Дитина"),
    "state_on": ("On", "Вкл.", "Увімкнено"),
    "state_off": ("Off", "Выкл.", "Вимкнено"),
    "state_playing": ("Playing", "Воспроизведение", "Відтворення"),
    "state_paused": ("Paused", "Пауза", "Пауза"),
    "state_buffering": ("Buffering", "Буферизация", "Буферизація"),
    "state_idle": ("Idle", "Простой", "Очікування"),
    "state_standby": ("Standby", "Режим ожидания", "Режим очікування"),
    "state_heat": ("Heat mode", "Режим отопления", "Режим опалення"),
    "state_cool": ("Cool mode", "Режим охлаждения", "Режим охолодження"),
    "state_heat_cool": (
        "Heat/cool mode",
        "Режим отопления/охлаждения",
        "Режим опалення/охолодження",
    ),
    "state_auto": ("Automatic mode", "Автоматический режим", "Автоматичний режим"),
    "state_dry": ("Dry mode", "Режим осушения", "Режим осушення"),
    "state_fan_only": ("Fan-only mode", "Режим вентиляции", "Режим вентиляції"),
    "state_recording": ("Recording", "Запись", "Запис"),
    "state_streaming": ("Streaming", "Трансляция", "Трансляція"),
    "state_clear-night": ("Clear night", "Ясная ночь", "Ясна ніч"),
    "state_cloudy": ("Cloudy", "Облачно", "Хмарно"),
    "state_fog": ("Fog", "Туман", "Туман"),
    "state_hail": ("Hail", "Град", "Град"),
    "state_lightning": ("Thunderstorm", "Гроза", "Гроза"),
    "state_lightning-rainy": ("Thunderstorm with rain", "Гроза с дождём", "Гроза з дощем"),
    "state_partlycloudy": ("Partly cloudy", "Переменная облачность", "Мінлива хмарність"),
    "state_pouring": ("Heavy rain", "Ливень", "Злива"),
    "state_rainy": ("Rain", "Дождь", "Дощ"),
    "state_snowy": ("Snow", "Снег", "Сніг"),
    "state_snowy-rainy": ("Snow and rain", "Снег с дождём", "Сніг з дощем"),
    "state_sunny": ("Sunny", "Солнечно", "Сонячно"),
    "state_windy": ("Windy", "Ветрено", "Вітряно"),
    "state_windy-variant": ("Windy and cloudy", "Ветрено и облачно", "Вітряно та хмарно"),
    "state_exceptional": ("Exceptional conditions", "Исключительные условия", "Виняткові умови"),
    "title": ("Home status", "Состояние дома", "Стан дому"),
    "energy": ("Energy readings", "Энергетические показания", "Енергетичні показники"),
    "active": (
        "Configured activity states",
        "Настроенные состояния активности",
        "Налаштовані стани активності",
    ),
    "empty": (
        "No readable configured sources.",
        "Нет доступных настроенных источников.",
        "Немає доступних налаштованих джерел.",
    ),
    "private": (
        "Ask for home status in our private chat.",
        "Запросите состояние дома в личном чате бота.",
        "Запитайте стан дому в особистому чаті бота.",
    ),
    "denied": (
        "Home status is unavailable for this account or configuration.",
        "Состояние дома недоступно для этой учётной записи или настройки.",
        "Стан дому недоступний для цього облікового запису або налаштування.",
    ),
    "invalid": (
        "Use /home, /energy, /active or /status followed by an exact configured group key.",
        "Используйте /home, /energy, /active или /status с точным ключом настроенной группы.",
        "Використовуйте /home, /energy, /active або /status із точним ключем налаштованої групи.",
    ),
    "note": (
        "HA report time is not verified measurement time. "
        "Reported state is not proof of physical operation.",
        "Время записи HA — не подтверждённое время измерения. "
        "Сообщённое состояние не доказывает физическую работу.",
        "Час запису HA — не підтверджений час вимірювання. "
        "Повідомлений стан не доводить фізичну роботу.",
    ),
    "reported": ("HA reports", "HA сообщает", "HA повідомляє"),
    "matched": (
        "matches activity mapping",
        "соответствует настройке активности",
        "відповідає налаштуванню активності",
    ),
    "not_matched": (
        "does not match activity mapping",
        "не соответствует настройке активности",
        "не відповідає налаштуванню активності",
    ),
    "generated": ("Read at", "Прочитано", "Прочитано"),
    "age": ("HA report age, seconds", "Возраст записи HA, секунд", "Вік запису HA, секунд"),
    "missing": ("No HA state", "Нет состояния HA", "Немає стану HA"),
    "unknown": ("HA reports unknown", "HA сообщает unknown", "HA повідомляє unknown"),
    "unavailable": (
        "HA reports unavailable",
        "HA сообщает unavailable",
        "HA повідомляє unavailable",
    ),
    "stale": ("HA report is too old", "Запись HA устарела", "Запис HA застарів"),
    "restored": (
        "Restored state is unverified",
        "Восстановленное состояние не подтверждено",
        "Відновлений стан не підтверджено",
    ),
    "missing_timestamp": (
        "HA report time is missing",
        "Нет времени записи HA",
        "Немає часу запису HA",
    ),
    "future_timestamp": (
        "HA report time is in the future",
        "Время записи HA в будущем",
        "Час запису HA в майбутньому",
    ),
    "invalid_unit": (
        "Unsupported or incompatible unit",
        "Неподдерживаемая или несовместимая единица",
        "Непідтримувана або несумісна одиниця",
    ),
    "invalid_value": (
        "Invalid numeric reading",
        "Некорректное числовое показание",
        "Некоректний числовий показник",
    ),
    "invalid_state": (
        "Unsupported reported state",
        "Неподдерживаемое состояние",
        "Непідтримуваний стан",
    ),
    "invalid_metadata": (
        "Invalid state metadata",
        "Некорректные метаданные состояния",
        "Некоректні метадані стану",
    ),
    "battery_soc": ("Battery charge (%)", "Заряд батареи (%)", "Заряд батареї (%)"),
    "battery_power": (
        "Battery power (signed)",
        "Мощность батареи (со знаком)",
        "Потужність батареї (зі знаком)",
    ),
    "load_power": ("Load power", "Мощность нагрузки", "Потужність навантаження"),
    "pv_power": ("PV power", "Мощность солнечной генерации", "Потужність сонячної генерації"),
    "grid_power": (
        "Grid power (signed)",
        "Мощность сети (со знаком)",
        "Потужність мережі (зі знаком)",
    ),
}
COPY = {
    language: {key: values[index] for key, values in ROWS.items()}
    for index, language in enumerate(("en", "ru", "uk"))
}


def render(snapshot, language):
    t = COPY.get(language, COPY["en"])
    lines = [t["title"], f"{t['generated']}: {snapshot['generated_at']}", t["note"]]
    sections = [
        (t["energy"], snapshot["energy"]),
        (t["active"], snapshot["active"]),
        *[(item["title"], item["rows"]) for item in snapshot["groups"]],
    ]
    count = 0
    for title, rows in sections:
        if not rows:
            continue
        lines.append(title)
        for row in rows:
            count += 1
            if row["quality"] != "ok":
                value = t[row["quality"]]
            elif row["value"] is not None:
                value = f"{row['value']:g} {row['unit']}".rstrip()
            elif row.get("reported_timestamp") is not None:
                stamp = datetime.fromisoformat(row["reported_timestamp"])
                value = f"{t['reported']}: {stamp:%Y-%m-%d %H:%M:%S} UTC"
            else:
                value = f"{t['reported']}: {t['state_' + row['reported_state']]}"
                if row["active"] is not None:
                    value += " · " + t["matched" if row["active"] else "not_matched"]
            if row["report_age_seconds"] is not None:
                value += f" · {t['age']}: {int(row['report_age_seconds'])}"
            lines.append(f"{row['label']}: {value}")
    if not count:
        lines.append(t["empty"])
    # All source count/label/number sizes are independently bounded. Telegram has
    # a smaller transport budget; disclose that a long explicit summary is clipped.
    text = "\n".join(lines)
    return text if len(text) <= 3900 else text[:3897] + "…"
