# Recurring shopping / Регулярные покупки / Регулярні покупки

## English

In the Shopping card, a parent or owner can select **Add recurring item**.
Enter the item, quantity/unit, optional buyer and release schedule. Daily, weekly
and monthly rules use the selected time zone. Advanced settings include the
interval, end date, excluded dates, store/category/note and catch-up window.

Each occurrence creates an ordinary approved shopping item. If an unfinished
item from that same series is already open, including a partial purchase, the
occurrence is recorded as skipped instead of adding another. Manual same-name
items are not automatically merged. A monthly day absent from a month is skipped;
so is a nonexistent local time during the spring clock change. An autumn repeated
time creates only one item.

Use **Edit recurring item**, **Enable** or **Disable** to manage a schedule.
Re-enabling does not backfill times before activation. Disabling does not remove
an existing shopping item. Only parents/owners can manage recurring approved
purchases; other family members have a read-only schedule view, and guests do not.
An inactive creator or buyer pauses generation. A guest cannot be assigned as buyer.

If another change wins a revision conflict, reopen the editor to review current
data. A failed save keeps the draft. All schedules and occurrences live in local
HA storage, outside HACS-managed source files. No real shopping purchase is placed.

## Русский

Родитель или владелец выбирает **Добавить регулярную покупку** в карточке покупок.
Укажите товар, количество/единицу, необязательного покупателя и расписание.
Доступны ежедневный, еженедельный и ежемесячный повтор. В дополнительных параметрах —
часовой пояс, интервал, окончание, даты-исключения, магазин/категория/заметка и
допустимое время восстановления пропущенного запуска.

По расписанию создаётся обычная согласованная позиция списка. Если предыдущая
позиция той же серии ещё не куплена полностью, новый повтор отмечается пропущенным.
Ручные позиции с таким же названием не объединяются. Несуществующий день месяца
или время при весеннем переводе часов пропускается; повторяющийся осенний час не
создаёт две позиции.

Кнопки **Изменить регулярную покупку**, **Включить**, **Выключить** управляют серией.
После включения старые запуски до момента активации не восстанавливаются.
Выключение серии не удаляет уже созданную покупку. Управление доступно родителям
и владельцу; остальным членам семьи — просмотр, гостям — нет. При отключённом
авторе или покупателе новые позиции не создаются. Гостя нельзя назначить покупателем.

При конфликте изменений заново откройте редактор и проверьте актуальные данные.
Неудачное сохранение не стирает черновик. Настройки хранятся локально в HA и не
заменяются обновлением HACS. Система ведёт список, а не оформляет заказ в магазине.

## Українська

Батьки або власник обирають **Додати регулярну покупку** в картці покупок.
Укажіть товар, кількість/одиницю, необов’язкового покупця й розклад. Доступні
щоденні, щотижневі та щомісячні повтори. Додаткові налаштування містять часовий
пояс, інтервал, дату завершення, винятки, магазин/категорію/примітку й допустиме
вікно відновлення пропущеного запуску.

Кожен запуск створює звичайний погоджений пункт списку. Якщо покупку цієї ж
серії ще не завершено, навіть частково, новий повтор позначається пропущеним.
Ручні пункти з такою ж назвою не об’єднуються. Відсутній день місяця або час
під час весняного переведення годинника пропускається; повторювана осіння година
створює лише один пункт.

Кнопки **Редагувати регулярну покупку**, **Увімкнути**, **Вимкнути** керують серією.
Увімкнення не відновлює запуски до моменту активації. Вимкнення не видаляє вже
створену покупку. Керування доступне батькам і власнику; іншим членам сім’ї —
перегляд, гостям — ні. Неактивний автор чи покупець зупиняє створення нових пунктів.
Гостя не можна призначити покупцем.

Після конфлікту змін відкрийте редактор заново й перевірте актуальні дані.
Невдале збереження залишає чернетку. Розклади зберігаються локально в HA й не
замінюються оновленням HACS. Інтеграція веде список, а не оформлює замовлення.
