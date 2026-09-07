# Personal reminders / Личные напоминания / Особисті нагадування

## English

On the Tasks card, choose **Add → Personal reminder — only for me**. Set the title,
optional deadline and checklist. Household time zone and explicit DST-fold choice
apply as for ordinary tasks. Save; later choose **Confirm done** yourself. You can
also edit, cancel and archive your reminder. Other family roles, including parents
and the household owner, cannot view or change it through Family Assistant.

The assignee is fixed to you, with no report or parent review, no reassignment,
grace period or penalties. One private notice is persisted at the deadline;
optional advance notice uses the reminder setting. Completion or deadline removal
supersedes unsent notices. A restart does not send a second deadline notice.
Telegram delivery requires your own verified private bot enrollment; missing
enrollment never falls back to a family group or parent. Quiet hours and ordinary
delivery uncertainty handling still apply: this is not an emergency alarm.

Personal records are omitted from other family views, parent command journals
(including mixed batches), delivery-review rows and the public pending-task sensor.
Group bot context and LLM planning exclude them. A changed member identity revision
invalidates old access, receipts and notifications, including for parent/owner
roles; there is no automatic transfer to a new person. Dashboard support and typed
task lifecycle commands are implemented. Personal reminders cannot be linked into
family calendar events, including by their author. Free-text personal reminder
creation is not inferred from an ordinary shared task request.

This is application-level privacy, **not encryption against the Home Assistant
server administrator**. Configuration storage and backups contain the data.
Protect their access and encrypted backups. A verified legacy reminder conversion
proposal now preserves this personal scope; this alone does not implement whole
household migration or authorize a live import.

## Русский

В карточке задач нажмите **Добавить → Личное напоминание — только для меня**.
Укажите текст, при необходимости срок и чек-лист. Используется часовой пояс семьи;
при переводе часов неоднозначное время нужно выбрать явно. Сохраните, затем сами
нажмите **Подтвердить выполнение**. Напоминание можно изменить, отменить и архивировать.

Другие члены семьи, включая родителей и владельца семьи, не видят его в Family
Assistant. Исполнитель — только вы: без отчёта, родительской проверки, переназначения,
штрафов и льготного периода. В срок сохраняется одно личное уведомление; напоминание
заранее настраивается отдельно. Завершение или удаление срока отменяет неотправленные
уведомления. Перезапуск не создаёт повторного уведомления о сроке.

Для Telegram нужна ваша подтверждённая личная привязка к боту. Без неё сообщения
не отправляются вместо вас родителям или в группу. Действуют тихие часы; это не
аварийный будильник. Личные данные исключены из чужого журнала, группового контекста
и планирования LLM. Перепривязка личности отзывает доступ к старому напоминанию.
Создание доступно в карточке; обычную просьбу о семейной задаче бот не превращает
в личное напоминание неявно.

Приватность действует внутри интеграции: администратор сервера HA с доступом к
файлам или резервным копиям может прочесть данные. Это не шифрование от администратора.
Перенос старых напоминаний теперь сохраняет личный доступ в проекте преобразования,
но полный импорт семьи ещё требует отдельной проверки и переключения.

## Українська

У картці завдань виберіть **Додати → Особисте нагадування — лише для мене**.
Вкажіть текст, за потреби строк і чекліст. Діє часовий пояс сім’ї; неоднозначний час
під час переходу годинника потрібно вибрати явно. Збережіть, потім самостійно
натисніть **Підтвердити виконання**. Можна редагувати, скасувати й архівувати.

Інші члени сім’ї, зокрема батьки та власник сім’ї, не бачать нагадування у Family
Assistant. Виконавець — лише ви: без звіту, перевірки батьками, перепризначення,
штрафів і пільгового періоду. У строк зберігається одне особисте сповіщення;
нагадування заздалегідь налаштовується окремо. Завершення або видалення строку
скасовує ненадіслані сповіщення. Перезапуск не створює повторного сповіщення про строк.

Для Telegram потрібна ваша підтверджена особиста прив’язка до бота. Без неї
повідомлення не надсилаються батькам чи в групу. Діють тихі години; це не аварійний
будильник. Особисті дані виключені з чужого журналу, групового контексту та
планування LLM. Переприв’язка особи відкликає доступ до старого нагадування.
Створення доступне в картці; звичайний запит про сімейне завдання не змінює
видимість на особисту неявно.

Це приватність усередині інтеграції, а не шифрування від адміністратора сервера HA:
дані є у файлах і резервних копіях. Захищайте доступ до них. Проєкт перетворення
старих нагадувань тепер зберігає особистий доступ, але повний імпорт сім’ї ще
потребує окремої перевірки та перемикання.
