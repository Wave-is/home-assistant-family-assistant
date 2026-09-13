"""Transport-neutral conversation status copy."""

COPY = {
    "en": {
        "name_repaired": (
            "✅ {result}\n📖 Understood {source} as {canonical}. Remembered this task-recipient "
            "spelling for your account. /forgetphrase {id} disables the rule."
        ),
        "learned": (
            "📖 Remembered for your account: {id}. It grants no new permissions; "
            "deadlines and targets are resolved anew. /forgetphrase {id} disables it."
        ),
        "forgotten": "📖 Phrase {id} is disabled. History is preserved.",
        "queued": "💬 I'll work on that. Ordinary commands and wake-up buttons remain available.",
        "preview": (
            "Please check the interpretation. Nothing has changed yet:\n{preview}\n"
            "Confirm: /confirm {id}\nCancel: /cancel {id}\nThis proposal expires in 5 minutes."
        ),
        "model": "💬 {text}\n\nFamily data was not changed.",
        "sources": "Sources (search snippets, not full articles):",
        "no_sources": "No suitable public sources were found.",
        "confirmed": "✅ Applied:\n{result}",
        "rejected": "Cancelled. Nothing was changed.",
        "feedback_saved": (
            "Proposal rejected; your private note was saved. The expected command was not "
            "executed or learned. Review or delete the note in your conversation card."
        ),
        "feedback_private": (
            "Send /feedback in your private chat with the bot. A message already sent to a "
            "group remains visible there. No proposal was changed."
        ),
    },
    "ru": {
        "name_repaired": (
            "✅ {result}\n📖 Понял «{source}» как «{canonical}». Запомнил это написание "
            "адресата задач для вашего аккаунта. /forgetphrase {id} отключит правило."
        ),
        "learned": (
            "📖 Запомнил для вашего аккаунта: {id}. Новых прав это не даёт; "
            "сроки и объекты определяются заново. /forgetphrase {id} отключит правило."
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
        "no_sources": "Подходящих открытых источников не найдено.",
        "confirmed": "✅ Выполнено:\n{result}",
        "rejected": "Отменено. Ничего не изменено.",
        "feedback_saved": (
            "Предложение отклонено, личная заметка сохранена. Ожидаемая команда не выполнена "
            "и не стала правилом. Просмотреть или удалить заметку можно в карточке разговора."
        ),
        "feedback_private": (
            "Отправьте /feedback в личный чат бота. Уже отправленное в группу сообщение "
            "остаётся видно участникам. Предложение не изменено."
        ),
    },
    "uk": {
        "name_repaired": (
            "✅ {result}\n📖 Зрозумів «{source}» як «{canonical}». Запам’ятав це написання "
            "адресата завдань для вашого акаунта. /forgetphrase {id} вимкне правило."
        ),
        "learned": (
            "📖 Запам’ятав для вашого акаунта: {id}. Нових прав це не дає; "
            "терміни й об’єкти визначаються заново. /forgetphrase {id} вимкне правило."
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
        "feedback_saved": (
            "Пропозицію відхилено, особисту нотатку збережено. Очікувану команду не виконано "
            "й не перетворено на правило. Переглянути або видалити нотатку можна в картці розмови."
        ),
        "feedback_private": (
            "Надішліть /feedback в особистий чат бота. Уже надіслане в групу повідомлення "
            "залишається видимим учасникам. Пропозицію не змінено."
        ),
    },
}
