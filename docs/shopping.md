# Shopping / Покупки / Покупки

## English

Use **Bought remaining** to record the full remaining quantity, or **Partial
purchase** for an amount bought now. Quantities use six-decimal precision. Parents
can approve/reject children's suggestions and archive items without deleting them.

**Merge items** lets a parent select up to 19 approved open duplicates into the
current item. Names match ignoring case and repeated whitespace; units, category,
store, note and buyer must match exactly. Review the totals and confirm. Pending
suggestions cannot bypass approval. A concurrent change rejects the stale preview.
Source records remain in the archive with links and their history, not duplicate
active purchases. A merged recurring item still suppresses repeats until completed.

**Item history** shows who recorded each change and when, newest first, with more
entries available on demand. Old records do not get invented past events. **Archived
& Completed Items** contains bought, rejected, archived and merged records. A failed
partial/merge attempt retains its exact payload for retry; cancel/reopen to change
the values or review a conflict. Telegram: `/bought S000001 | 0.5` records a partial
purchase; omitting the quantity records the remaining amount. The module only
records purchases made by people; it does not place an order or spend money.

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

**Куплено: весь остаток** отмечает полную покупку, **Частичная покупка** — количество,
купленное сейчас. Точность количества — шесть знаков после запятой. Родители могут
одобрять/отклонять предложения детей и отправлять записи в архив без удаления.

Кнопка **Объединить** позволяет выбрать до 19 согласованных незавершённых дублей
в текущую позицию. Регистр и лишние пробелы в названии не важны, но единицы,
категория, магазин, комментарий и покупатель должны совпадать точно. Проверьте
итоговые количества и подтвердите. Ожидающие одобрения предложения объединять
нельзя. Конкурирующее изменение отклонит устаревший просмотр. Исходные записи
останутся в архиве с историей; незавершённая объединённая регулярная покупка
по-прежнему не создаст новый повтор.

**История изменений** показывает автора и время, начиная с последних записей;
старые записи доступны по кнопке. Прошлые события не выдумываются. Купленные,
отклонённые и объединённые позиции находятся в **Архиве и завершённых покупках**.
При ошибке сохраняется точная команда для повторной попытки. Чтобы изменить её
или пересмотреть конфликт, отмените форму и откройте заново. В Telegram команда
`/bought S000001 | 0.5` отмечает частичную покупку; без количества — весь остаток.
Интеграция только ведёт учёт, а не покупает товары и не тратит деньги.

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

**Куплено: увесь залишок** позначає повну покупку, **Часткова покупка** — кількість,
куплену зараз. Точність кількості — шість знаків після коми. Батьки можуть
схвалювати/відхиляти пропозиції дітей та архівувати записи без видалення.

**Об'єднати** дозволяє обрати до 19 погоджених незавершених дублів у поточний пункт.
Регістр і зайві пробіли в назві не важливі, але одиниці, категорія, магазин, примітка
й покупець мають збігатися точно. Перевірте підсумки й підтвердьте. Пропозиції без
схвалення об'єднувати не можна. Конкурентна зміна відхилить застарілий перегляд.
Вихідні записи лишаються в архіві з історією. Незавершена об'єднана регулярна
покупка й надалі стримує створення наступного повтору.

**Історія змін** показує автора й час, починаючи з останніх записів; старі записи
доступні за кнопкою. Минулі події не вигадуються. Куплені, відхилені й об'єднані
пункти містяться в **Архіві і завершених покупках**. Після помилки точна команда
зберігається для повтору; щоб змінити її чи переглянути конфлікт, скасуйте форму
й відкрийте знову. У Telegram `/bought S000001 | 0.5` позначає часткову покупку;
без кількості — увесь залишок. Інтеграція веде облік, а не купує товари й не витрачає гроші.

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
