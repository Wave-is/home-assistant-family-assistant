"""Transport-neutral conversation status copy."""

COPY = {
    "en": {
        "learned": (
            "📖 Remembered for your account: {id}. It grants no new permissions; "
            "deadlines and targets are resolved anew. /forget {id} disables it."
        ),
        "forgotten": "📖 Phrase {id} is disabled. History is preserved.",
        "queued": "💬 I'll work on that. Ordinary commands and wake-up buttons remain available.",
        "preview": (
            "Please check the interpretation. Nothing has changed yet:\n{preview}\n"
            "Confirm: /confirm {id}\nCancel: /cancel {id}\nThis proposal expires in 5 minutes."
        ),
        "model": "💬 {text}\n\nFamily data was not changed.",
        "sources": "Sources (search snippets, not full articles):",
        "no_sources": "No suitable public sources were found. Family data was not changed.",
        "confirmed": "✅ Applied:\n{result}",
        "rejected": "Cancelled. Nothing was changed.",
    },
    "ru": {
        "learned": (
            "📖 Запомнил для вашего аккаунта: {id}. Новых прав это не даёт; "
            "сроки и объекты определяются заново. /forget {id} отключит правило."
        ),
        "forgotten": "📖 Фраза {id} отключена. История сохранена.",
        "queued": (
            "💬 Разберусь с обращением. Обычные команды и кнопки подъёма продолжают работать."
        ),
        "preview": (
            "Проверьте, правильно ли я понял. Пока ничего не изменено:\n{preview}\n"
            "Подтвердить: /confirm {id}\nОтменить: /cancel {id}\nПредложение действует 5 минут."
        ),
        "model": "💬 {text}\n\nДанные семьи не изменены.",
        "sources": "Источники (поисковые выдержки, не полные статьи):",
        "no_sources": "Подходящих открытых источников не найдено. Данные семьи не изменены.",
        "confirmed": "✅ Выполнено:\n{result}",
        "rejected": "Отменено. Ничего не изменено.",
    },
    "uk": {
        "learned": (
            "📖 Запам’ятав для вашого акаунта: {id}. Нових прав це не дає; "
            "терміни й об’єкти визначаються заново. /forget {id} вимкне правило."
        ),
        "forgotten": "📖 Фразу {id} вимкнено. Історію збережено.",
        "queued": "💬 Розберуся зі зверненням. Звичайні команди та кнопки підйому працюють далі.",
        "preview": (
            "Перевірте, чи правильно я зрозумів. Поки нічого не змінено:\n{preview}\n"
            "Підтвердити: /confirm {id}\nСкасувати: /cancel {id}\nПропозиція діє 5 хвилин."
        ),
        "model": "💬 {text}\n\nДані сім’ї не змінено.",
        "sources": "Джерела (пошукові уривки, не повні статті):",
        "no_sources": "Відповідних відкритих джерел не знайдено. Дані сім’ї не змінено.",
        "confirmed": "✅ Виконано:\n{result}",
        "rejected": "Скасовано. Нічого не змінено.",
    },
}
