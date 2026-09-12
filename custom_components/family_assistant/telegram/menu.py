"""Native Telegram command catalog, with no household names or identifiers."""

COMMANDS = (
    ("commands", "Command help", "Все команды", "Усі команди"),
    ("ping", "Check the bot", "Проверить бота", "Перевірити бота"),
    ("tasks", "Available tasks", "Доступные задачи", "Доступні завдання"),
    ("mine", "My tasks and reminders", "Мои дела и напоминания", "Мої справи й нагадування"),
    ("task", "Create a task", "Создать задачу", "Створити завдання"),
    ("accept", "Accept a task", "Принять задачу", "Прийняти завдання"),
    ("begin", "Start a task", "Начать задачу", "Почати завдання"),
    ("done", "Submit a task report", "Отчёт по задаче", "Звіт про завдання"),
    ("report", "Send a task photo", "Фотоотчёт по задаче", "Фотозвіт про завдання"),
    (
        "approve",
        "Parent task approval",
        "Родителю: подтвердить задачу",
        "Батькам: підтвердити завдання",
    ),
    ("edit", "Edit a task", "Изменить задачу", "Змінити завдання"),
    ("archive", "Archive a task", "Архивировать задачу", "Архівувати завдання"),
    ("shopping", "Shopping list", "Список покупок", "Список покупок"),
    ("buy", "Add a purchase", "Добавить покупку", "Додати покупку"),
    ("bought", "Mark purchased quantity", "Отметить купленное", "Позначити придбане"),
    (
        "approvebuy",
        "Parent purchase approval",
        "Родителю: одобрить покупку",
        "Батькам: схвалити покупку",
    ),
    (
        "rejectbuy",
        "Parent purchase rejection",
        "Родителю: отклонить покупку",
        "Батькам: відхилити покупку",
    ),
    ("alarms", "Alarm schedules", "Расписания будильников", "Розклади будильників"),
    ("alarm", "Set or toggle an alarm", "Настроить будильник", "Налаштувати будильник"),
    ("stats", "Scores and reasons", "Баллы и причины", "Бали й причини"),
    ("week", "Current week scores", "Баллы за неделю", "Бали за тиждень"),
    ("calendar", "Family calendar", "Семейный календарь", "Сімейний календар"),
    ("routines", "Family routines", "Семейные рутины", "Сімейні рутини"),
    ("rewards", "Rewards catalog", "Каталог наград", "Каталог винагород"),
    ("wallet", "My points balance", "Мой баланс баллов", "Мій баланс балів"),
    ("prices", "Tracked prices", "Отслеживаемые цены", "Відстежувані ціни"),
    ("ask", "Ask the assistant", "Вопрос помощнику", "Запитання помічнику"),
)


def command_menu(language):
    index = {"en": 1, "ru": 2, "uk": 3}.get(language, 1)
    return [{"command": row[0], "description": row[index]} for row in COMMANDS]
