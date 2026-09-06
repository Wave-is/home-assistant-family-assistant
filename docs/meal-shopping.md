# Shopping from a menu / Покупки по меню / Покупки за меню

## English

Enable both **Pantry & household stock** and **Shopping**. A parent can calculate
a shopping proposal from a published weekly menu in the meals card. Calculation
does not add purchases. It groups ingredient totals by normalized name and exact
unit, subtracts recorded active stock and the remaining quantities of pending or
approved shopping items, and shows the result for review. Units are not converted.

Each line displays required quantity, recorded stock, open shopping and the amount
to add. The shopping list accepts amounts from 0.001; a positive shortfall is
rounded **up** to that quantum. The exact shortfall is retained separately. No
total combines quantities with different units. Pending purchases count as planned
coverage, not as products already bought; recorded stock is not an allergy or
food-safety judgment. Correct stock and the shopping list before confirming.

Acceptance requires explicit review and creates only approved shopping-list
records for positive amounts. It does not place orders or deduct stock. Parent
notes are never copied. Zero-shortfall lines remain visible; accepting an entirely
covered proposal records that decision without creating any shopping items.

Before acceptance, the integration rechecks the published menu version and every
relevant stock/shopping input. New matching items, changed counts, partial purchases
or a menu edit invalidate an old calculation. Recalculate and review the new
proposal; unrelated records do not invalidate it. Retrying a lost response uses
the identical operation ID and payload.

**One accepted transfer per menu plan.** Later purchases or edits to that menu
cannot automatically generate another transfer. Its receipt remains linked to the
original shopping records. Amend the shopping list manually after acceptance.
Incremental menu amendments and allocation of stock between different weeks are
not implemented; the calculation is not a reservation of supplies.

## Русский

Включите «Продукты и запасы» и «Покупки». Родитель может рассчитать покупки для
опубликованного меню. Сам расчёт ничего в список покупок не добавляет. Ингредиенты
объединяются по нормализованному названию и точной единице, затем вычитаются
записанные активные остатки и ещё не купленное количество в открытых покупках.
Единицы не пересчитываются. Ожидающая согласования покупка учитывается как план,
а не как уже приобретённый продукт.

Перед подтверждением видны потребность, запас, открытые покупки и количество к
добавлению. Положительный дефицит округляется **вверх до 0,001** — минимального
количества в списке покупок. Исходный дефицит сохраняется отдельно. Разные единицы
не складываются в общий итог. Записанный остаток не означает, что продукт безопасен
или подходит при аллергии; перед подтверждением проверьте записи.

Только явное подтверждение создаёт согласованные позиции в покупках. Заказы не
оформляются, запас не списывается, заметки родителей не копируются. Полностью
покрытый расчёт можно подтвердить без создания покупок. Изменение меню, остатков
или соответствующих открытых покупок требует нового расчёта и проверки; посторонние
позиции не мешают. При потере ответа повторяется та же операция без дубля.

**Для одного плана — один принятый перенос.** Отметка продуктов купленными или
правка меню не создаёт повторную закупку. После принятия меняйте список покупок
вручную. Автоматические дополнения к уже принятому переносу и распределение
остатков между разными неделями пока не реализованы; расчёт не резервирует продукты.

## Українська

Увімкніть «Продукти й запаси» та «Покупки». Батьки можуть розрахувати покупки для
опублікованого меню. Сам розрахунок нічого до списку покупок не додає. Інгредієнти
об'єднуються за нормалізованою назвою й точною одиницею, потім віднімаються
записані активні залишки та ще не придбана кількість у відкритих покупках.
Одиниці не перераховуються. Покупка, що очікує погодження, враховується як план,
а не як уже придбаний продукт.

Перед підтвердженням видно потребу, запас, відкриті покупки та кількість до
додавання. Додатний дефіцит округлюється **вгору до 0,001** — мінімальної кількості
у списку покупок. Початковий дефіцит зберігається окремо. Різні одиниці не
підсумовуються. Записаний запас не підтверджує безпечність продукту чи його
придатність за наявності алергії; перевірте записи перед підтвердженням.

Лише явне підтвердження створює погоджені позиції в покупках. Замовлення не
оформлюються, запас не списується, примітки батьків не копіюються. Повністю
покритий розрахунок можна підтвердити без нових покупок. Зміна меню, залишків чи
відповідних відкритих покупок потребує нового розрахунку й перевірки; сторонні
позиції не заважають. Після втрати відповіді повторюється та сама операція без дубля.

**Для одного плану — одне прийняте перенесення.** Позначення продуктів придбаними
або зміна меню не створює повторної закупівлі. Після прийняття змінюйте список
покупок вручну. Автоматичні доповнення й розподіл залишків між різними тижнями
поки не реалізовані; розрахунок не резервує продукти.

## API

`pantry.meal_shop_prepare` takes `{id, revision}` of a published meal plan and
returns a private proposal. `pantry.meal_shop_accept` takes `{id, revision}` of
that proposal. Source and proposal namespaces are distinct (`MP…` and `MS…`).
Only current parents/owners may act, and both modules must remain enabled even
when replaying an old receipt. The private parent projection is
`pantry.meal_shopping`; child/adult projections contain no proposals.

Lines include `required`, `stock`, `open_shopping`, exact `deficit`, rounded
`quantity`, `unit` and `name`; created lines gain a `shopping_id`. `transfer_count`
counts created records, never heterogeneous physical quantities. Source and
proposal provenance is attached to created shopping records. Local persistence,
rollback on Store failure and command replay share the integration transaction
engine. No user credentials or external service are needed for calculation.
