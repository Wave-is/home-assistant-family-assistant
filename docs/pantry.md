# Pantry and household stock

The pantry is a local stock register. It is separate from the shared shopping
list: a pantry record describes what the household has, while a shopping item
describes something to obtain. Enable **Pantry** in the integration's module
settings, then add `custom:family-pantry-card` to the dashboard. The card is
available in English, Russian and Ukrainian and uses the authenticated Home
Assistant family member; it never accepts a role supplied by the browser.

```yaml
type: custom:family-pantry-card
language: en
```

For multiple households, choose the household in the card editor. Parents can
edit records and review the exact item and quantity before adding a suggestion
to shopping. Adults can correct counts with a reason; children only view stock.
The editor preserves typed fields after refresh. After an uncertain response,
**Retry** submits the same frozen operation, even if the backend already saved
it; it cannot create a second shopping item. Changed permissions still apply.

## English

### What is recorded

Each active record has a name, unit, quantity, minimum quantity, optional
category, location, parent-private note, and one optional `expires_on` date.
Quantities are bounded to `0..1,000,000` with at most three decimal places.
The date is the date recorded for that stock record; it is not a medical,
freshness, or food-safety judgment. Separate lots or different expiry dates
must be separate records. Expiry does not decrement quantity and currently
does not create notifications, menus, or preferences.

Changing quantity or unit requires a reason. A unit change is a relabeling, not
an automatic conversion; use a reason such as `unit_relabel_not_conversion`.
Parent notes are private and are never copied into shared shopping items.

Owners and parents can create, edit, and archive records. Owners, parents, and
active adults can correct a stock count with a reason. Children have a
read-only view; guests and inactive members see no pantry records.

### Low-stock suggestions

The pantry tick creates at most one open suggestion for an item and source
revision. Suggestions carry the deficit, exact unit, source revision, and
reason (`below_minimum`). A changed count or item revision supersedes the old
suggestion. Dismissing an unchanged suggestion prevents it being recreated.

Suggestions are deduplicated against open shopping items with status
`pending` or `approved`, matching normalized name and exact unit. An accepted
suggestion rechecks the current revision and creates or links only a shopping
list item; it does not place an order, increase pantry stock, or promise a
partial top-up. Any matching open shopping quantity counts as covered under
the current policy.

Only a parent or owner can accept or dismiss a suggestion. Acceptance requires
the shopping module to be enabled; stale source revisions and changed
authorization are rejected.

### API actions and representative synthetic payloads

The domain actions are `item_save`, `stock_set`, `item_archive`,
`suggestion_accept`, and `suggestion_dismiss`. These examples use synthetic
IDs only:

```json
{
  "action": "item_save",
  "payload": {
    "name": "Milk", "unit": "l", "quantity": 1,
    "minimum_quantity": 3, "category": "Food", "location": "Fridge",
    "note": "Parent-private note", "expires_on": "2026-09-10"
  }
}
```

An edit includes `id` and `revision`; a quantity or unit edit also includes a
human-readable `reason`. A stock correction uses
`{"id":"I-synthetic","revision":2,"quantity":2,"reason":"Counted"}`.
Suggestion actions use `id` and `revision`; dismissal additionally requires a
reason, while acceptance does not accept one.

## Русский

Кладовая — это отдельный локальный учёт запасов, а не список покупок.
Карточка запаса хранит название, единицу, количество, минимальный остаток,
необязательные категорию, место, заметку родителя и одну дату `expires_on`.
Количество: от 0 до 1 000 000, не более трёх знаков после запятой. Разные
партии или разные сроки годности записываются отдельными строками; указанный
срок не является оценкой свежести или безопасности продукта. Истёкшая
дата ничего не списывает и пока не создаёт уведомления, меню, предпочтения или
рецепты.

Изменение количества или единицы требует причины. Единица только
переподписывается, автоматического пересчёта нет: объясните причину изменения
своими словами. Заметка родителя приватна и не переносится в
общую покупку. Создавать, редактировать и архивировать записи могут владелец
и родители; исправлять количество — также активный взрослый. Ребёнок видит
запасы только для чтения, гость и неактивный участник не видят ничего.

Проверка минимума создаёт одну открытую версию предложения с дефицитом,
точной единицей, исходной ревизией и причиной `below_minimum`. Изменение
остатка или записи заменяет старое предложение, а отклонение без изменения
остатка не порождает его снова. Совпадением считаются открытые покупки со
статусом `pending` или `approved`, одинаковой нормализованной строкой названия
и точно такой же единицей. Принятие после свежей проверки создаёт или связывает
только элемент списка покупок: оно не заказывает товар и не увеличивает запас;
при текущем правиле любое совпавшее открытое количество считается покрытым.
Принять или отклонить предложение могут только владелец и родитель.

Действия API: `item_save`, `stock_set`, `item_archive`, `suggestion_accept`,
`suggestion_dismiss`. Для изменения передаются `id` и `revision`; для
количества и единицы обязательна причина, а для отклонения — тоже. Примеры
выше используют только синтетические значения. Включите модуль кладовой в
настройках интеграции и добавьте `custom:family-pantry-card` на дашборд
(`language: ru`). При нескольких семьях выберите нужную в редакторе карточки.
Перед добавлением покупки показаны её название и количество. «Повторить»
повторяет ту же сохранённую операцию, если ответ потерялся; введённые поля
не теряются при обновлении. Изменение прав доступа блокирует старую команду.

## Українська

Комора — це окремий локальний облік запасів, а не спільний список покупок.
Запис містить назву, одиницю, кількість, мінімальний залишок, необов’язкові
категорію, місце, приватну нотатку батьків і одну дату `expires_on`.
Кількість: від 0 до 1 000 000, не більше трьох десяткових знаків. Різні партії
або строки придатності записуються окремо; зазначений строк не є оцінкою
свіжості чи безпечності продукту. Після цієї дати кількість не
зменшується, сповіщень, меню, уподобань і рецептів наразі немає.

Зміна кількості або одиниці потребує причини. Одиниця лише перейменовується,
автоматичного перерахунку немає: поясніть причину зміни своїми словами.
Нотатка батьків приватна й не копіюється до
спільної покупки. Створювати, редагувати й архівувати записи можуть власник і
батьки; виправляти кількість — також активний дорослий. Дитина має лише
перегляд, гість і неактивний учасник не бачать запасів.

Перевірка мінімуму створює одну відкриту пропозицію з дефіцитом,
точною одиницею, вихідною ревізією та причиною `below_minimum`. Зміна залишку
або запису замінює стару пропозицію, а відхилена пропозиція без нової зміни не
повторюється. Покриттям вважається відкрита покупка зі статусом `pending` або
`approved`, з однаковою нормалізованою назвою та точною одиницею. Прийняття
після повторної перевірки створює або пов’язує лише елемент списку покупок; це
не замовлення і не збільшення запасу, а будь-яка відповідна відкрита кількість
нині вважається достатньою.

Дії API: `item_save`, `stock_set`, `item_archive`, `suggestion_accept`,
`suggestion_dismiss`. Для редагування потрібні `id` і `revision`; зміна
кількості чи одиниці потребує причини, як і відхилення пропозиції. Наведені
приклади використовують лише синтетичні значення. Увімкніть модуль комори в
налаштуваннях інтеграції та додайте `custom:family-pantry-card` на дашборд
(`language: uk`). Якщо родин декілька, виберіть потрібну в редакторі картки.
Перед додаванням покупки показано назву та кількість. «Повторити» надсилає ту
саму збережену операцію, якщо відповідь втрачено; введені поля не зникають при
оновленні. Зміна прав доступу блокує стару команду.

## Current limits

There are no expiry notifications, expiry-driven quantity decrements, menu or
preference management, recipe provider, or pantry-specific user preferences in
the current API. Use the exact action names and fields above; household IDs,
device IDs, credentials, and real shopping data do not belong in this guide.
