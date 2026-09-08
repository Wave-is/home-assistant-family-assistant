# Task batches / Несколько задач / Кілька завдань

## English

The Tasks card's parent-only batch panel selects up to 20 ordinary shared tasks
for one action. Review every task and the chosen action before confirming.
Completion or cancellation applies only to unfinished tasks; batch archiving
selects already completed or cancelled tasks. Personal reminders and tasks managed
by specialized modules stay in their individual workflows.

The card sends one native atomic `batch` command with each selected task's reviewed
revision. If a task has changed, the entire first attempt fails without changing
the others. An uncertain response retains the same payload and operation ID for
an exact retry; it does not silently refresh revisions or create another command.
Closing an uncertain review does not undo a command already accepted by HA.
Changed household, user, permissions or member bindings invalidate the private
review. Server-side permissions still apply to every operation.

This is not shared ownership of one task, automatic completion, bulk deletion or
a replacement for reviewing individual reports. Archiving keeps the history.

## Русский

В карточке задач родитель выбирает до 20 обычных общих задач и одно действие.
Перед подтверждением проверьте полный список. Завершать и отменять можно
незаконченные задачи, отправлять в архив — уже завершённые или отменённые.
Личные напоминания и задачи специальных модулей остаются в своих отдельных формах.

Отправляется одна атомарная команда с проверенными ревизиями задач. Если одна
задача изменилась, первая попытка отклоняется целиком — остальные не меняются.
При потере ответа повтор сохраняет исходный набор и ID операции; ревизии не
подменяются. Закрытие экрана не отменяет уже принятую HA команду. Смена семьи,
пользователя, прав или привязок участников сбрасывает приватный просмотр.
Сервер проверяет права независимо от карточки.

Это не совместное владение одной задачей и не удаление истории. Не подтверждайте
выполнение до проверки отчётов. Архивация сохраняет записи.

## Українська

У картці завдань батьки обирають до 20 звичайних спільних завдань та одну дію.
Перед підтвердженням перевірте весь список. Завершувати й скасовувати можна
незакінчені завдання, архівувати — уже завершені або скасовані. Особисті нагадування
та завдання спеціальних модулів залишаються у своїх окремих формах.

Надсилається одна атомарна команда з перевіреними ревізіями. Якщо одне завдання
змінилося, перша спроба відхиляється цілком — інші не змінюються. За втрати відповіді
повтор зберігає вихідний набір та ID операції, без підміни ревізій. Закриття екрана
не скасовує вже прийняту HA команду. Зміна родини, користувача, прав чи прив’язок
учасників скидає приватний перегляд. Сервер незалежно перевіряє права.

Це не спільне володіння одним завданням і не видалення історії. Перевірте звіти
перед підтвердженням виконання. Архівування зберігає записи.
