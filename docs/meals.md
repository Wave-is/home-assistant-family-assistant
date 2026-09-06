# Weekly menu / Меню на неделю / Меню на тиждень

Development feature under the **Pantry & household stock** module. Enable that
module in integration options and add `custom:family-meals-card`. The visual card
editor selects a household and language; authentication determines permissions.

```yaml
type: custom:family-meals-card
language: en
```

## English

Parents and owners create a named draft for a week beginning on Monday. Each
entry specifies a date, breakfast/lunch/dinner/snack, a dish, servings and an
optional ingredient list. There may be one entry per date and meal slot, up to
28 entries per plan. Ingredient quantities are **totals for the stated servings**:
changing servings does not scale quantities or convert units. Check both fields.

Publishing is a separate reviewed action. Active adults and children see only
published plans; guests see none. Notes and history remain parent-private.
Only one plan can be published per week. Editing a published plan returns it to
a private draft until a parent publishes it again. Archiving requires a reason
and preserves the record and its history; an archived plan cannot be edited.

An edit carries the version that was displayed. A stale form cannot overwrite a
newer plan. After a lost response, Retry uses the same payload and operation ID,
even if saving already succeeded; it does not create a duplicate. Permission
revocation still applies to old receipts.

This slice is manual planning: it does not place orders, deduct stock, or
perform allergy checks. When both **Pantry & household stock** and **Shopping**
are enabled, parent-initiated calculation followed by explicit review and
acceptance creates approved shopping list entries only (see
[meal-shopping.md](meal-shopping.md)). Private notes are never copied, only one
accepted transfer is permitted per plan ID, and later amendments to shopping
must be done manually. [Private preferences](dietary-profiles.md) have a separate
consent-controlled section in this card and are never copied into meal records.
[Mealie](recipes.md) optionally supplies manually reviewed recipe candidates.
An ingredient list is not a statement
that a meal is safe for someone with an allergy; no such inference is made.

## Русский

Включите модуль «Продукты и запасы» и добавьте карточку «Меню на неделю».
Родитель или владелец создаёт черновик недели с понедельника: название,
дата, приём пищи, блюдо, порции и необязательные ингредиенты. На один день и
приём пищи — одна запись, всего до 28 записей. Количество ингредиентов —
**суммарное на все указанные порции**. При изменении порций количество само
не пересчитывается; единицы также не конвертируются.

Публикация требует отдельного подтверждения. Дети и взрослые видят только
опубликованные планы, гости — ничего. Заметки и история доступны только
родителям. На неделю допускается один опубликованный план. После правки он
снова становится черновиком до повторной публикации. Архивирование требует
причины и сохраняет историю; архивный план не редактируется.

Устаревшая форма не перезаписывает более новую запись. «Повторить» после
потери ответа повторяет прежнюю операцию с прежними данными, не создавая
второй план. Снятые права не возвращаются при повторе старой команды.

Само планирование не оформляет заказы, не списывает запасы и не выполняет
проверки аллергенов. При включении обоих модулей («Продукты и запасы» и
«Покупки») инициированный родителем расчёт с последующим явным просмотром и
подтверждением создаёт только согласованные позиции в списке покупок (см.
[meal-shopping.md](meal-shopping.md)). Приватные заметки не копируются, для
одного идентификатора плана допускается только один принятый перенос, а все
последующие изменения вносятся в список покупок вручную. [Приватные
предпочтения](dietary-profiles.md) находятся в отдельном разделе карточки с
управлением согласием и не копируются в меню. [Mealie](recipes.md) можно подключить
как источник рецептов с ручной проверкой. Список ингредиентов не подтверждает безопасность блюда
при аллергии.

## Українська

Увімкніть модуль «Продукти й запаси» та додайте картку «Меню на тиждень».
Батьки або власник створюють чернетку тижня з понеділка: назва, дата,
прийом їжі, страва, порції та необов'язкові інгредієнти. На одну дату та
прийом їжі — один запис, до 28 на тиждень. Кількість інгредієнтів —
**загальна на всі зазначені порції**. Зміна порцій не перераховує кількості;
одиниці вимірювання також не конвертуються.

Публікація потребує окремого підтвердження. Діти й дорослі бачать лише
опубліковані плани, гості — нічого. Примітки та історія доступні лише батькам.
На тиждень допускається один опублікований план. Редагування повертає його
до чернетки до повторної публікації. Архівування потребує причини та зберігає
історію; архівний план не редагується.

Застаріла форма не перезапише новіший запис. «Повторити» після втрати відповіді
надсилає ту саму операцію з тими самими даними, не створюючи дубліката.
Відкликані права не відновлюються повторенням старої команди.

Саме планування не оформлює замовлення, не списує запаси та не виконує перевірки
алергенів. Якщо ввімкнено обидва модулі («Продукти й запаси» та «Покупки»),
ініційований батьками розрахунок із подальшим явним переглядом і підтвердженням
створює лише погоджені позиції в списку покупок (див.
[meal-shopping.md](meal-shopping.md)). Приватні примітки не копіюються, для
одного ідентифікатора плану дозволено лише одне прийняте перенесення, а будь-які
подальші зміни вносяться до списку покупок вручну. [Приватні вподобання](dietary-profiles.md)
розміщені в окремому розділі картки з керуванням згодою й не копіюються до меню.
[Mealie](recipes.md) можна підключити як джерело рецептів із ручною перевіркою. Перелік
інгредієнтів не підтверджує безпечність страви за наявності алергії.

## API contract

Actions use `pantry.meal_save`, `pantry.meal_publish`, `pantry.meal_archive`.
All existing-record actions require an integer `revision` in `1..2^53-1`.
Create omits both `id` and `revision`; edits preserve omitted metadata.
Publish takes only `id` and `revision`. Archive additionally requires `reason`.

```json
{
  "action": "pantry.meal_save",
  "payload": {
    "week_start": "2026-09-07",
    "title": "Example week",
    "entries": [{
      "date": "2026-09-07", "slot": "dinner", "title": "Soup",
      "servings": 4,
      "ingredients": [{"name": "Carrot", "unit": "kg", "quantity": 0.5}]
    }]
  }
}
```

Titles/names are limited to 120 characters, units to 24, notes/reasons to 500.
Servings are integers `1..50`. Each meal permits up to 20 ingredients, at most
100 per plan. Quantities are positive, at most one million, with up to three
decimal places. Dates must be canonical ISO dates within the complete selected
Monday–Sunday week. Persistence/replay use the same transaction engine as other
modules; no separate private script or external provider is required.
