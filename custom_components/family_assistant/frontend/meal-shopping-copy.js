/* Local copy for parent-reviewed meal-plan shopping transfers. */

export const MEAL_SHOPPING_COPY = {
  en: {
    title: "Meal plan shopping",
    calculate: "Calculate shopping needs",
    retry: "Retry exact request",
    cancel: "Cancel",
    accept: "Send to shopping list",
    confirm_accept: "I reviewed every amount and want to add these items",
    plan: "Meal plan",
    week_start: "Week starting",
    proposals: "Private shopping proposals",
    no_proposals: "No meal shopping proposals yet.",
    no_published: "Publish a meal plan before calculating shopping needs.",
    status_open: "Ready for parent review",
    status_superseded: "Superseded by a newer calculation",
    status_accepted: "Sent to the shopping list",
    status_covered: "Already fully covered",
    required: "Required by the plan",
    stock: "Recorded pantry stock",
    open_shopping: "Remaining on the shopping list",
    deficit: "Uncovered amount",
    quantity: "Amount to add",
    shopping_id: "Shopping item",
    shopping_ids: "Created shopping items",
    transfer_count: "Shopping records created",
    rounding_hint:
      "A positive uncovered amount is rounded up to 0.001 for the shopping list; exact stock and coverage remain shown above.",
    prepare_hint:
      "Calculation creates a private proposal only. It does not buy anything, change pantry stock, or add items to the shopping list.",
    accept_hint:
      "Confirming creates shopping-list records only. It does not place an order or deduct pantry stock.",
    after_transfer_hint:
      "This plan has already been transferred. Later plan edits do not update these shopping items; edit the shopping list manually.",
    terminal_empty_hint:
      "Nothing was added because recorded stock and open shopping already cover the plan.",
    module_off:
      "Enable both Pantry & household stock and Shopping to calculate meal shopping needs.",
  },
  ru: {
    title: "Покупки по плану питания",
    calculate: "Рассчитать необходимые покупки",
    retry: "Повторить тот же запрос",
    cancel: "Отмена",
    accept: "Передать в список покупок",
    confirm_accept: "Я проверил(а) все количества и хочу добавить эти позиции",
    plan: "План питания",
    week_start: "Неделя с",
    proposals: "Личные предложения покупок",
    no_proposals: "Предложений покупок по плану пока нет.",
    no_published: "Опубликуйте план питания, прежде чем рассчитывать покупки.",
    status_open: "Ожидает проверки родителем",
    status_superseded: "Заменено более новым расчётом",
    status_accepted: "Передано в список покупок",
    status_covered: "Уже полностью покрыто",
    required: "Требуется по плану",
    stock: "Учтённый остаток в кладовой",
    open_shopping: "Осталось в списке покупок",
    deficit: "Непокрытое количество",
    quantity: "Будет добавлено",
    shopping_id: "Позиция покупок",
    shopping_ids: "Созданные позиции покупок",
    transfer_count: "Создано записей покупок",
    rounding_hint:
      "Положительное непокрытое количество округляется вверх до 0,001 для списка покупок; точные остаток и покрытие показаны выше.",
    prepare_hint:
      "Расчёт создаёт только личное предложение. Он ничего не покупает, не меняет остатки и не добавляет позиции в список покупок.",
    accept_hint:
      "Подтверждение создаёт только записи в списке покупок. Заказ не оформляется, остатки в кладовой не списываются.",
    after_transfer_hint:
      "Этот план уже передан. Последующие изменения плана не обновят созданные позиции; редактируйте список покупок вручную.",
    terminal_empty_hint:
      "Ничего не добавлено: учтённые остатки и открытые покупки уже покрывают план.",
    module_off:
      "Для расчёта включите одновременно модули «Продукты и запасы» и «Покупки».",
  },
  uk: {
    title: "Покупки за планом харчування",
    calculate: "Розрахувати необхідні покупки",
    retry: "Повторити той самий запит",
    cancel: "Скасувати",
    accept: "Передати до списку покупок",
    confirm_accept: "Я перевірив(ла) всі кількості й хочу додати ці позиції",
    plan: "План харчування",
    week_start: "Тиждень від",
    proposals: "Приватні пропозиції покупок",
    no_proposals: "Пропозицій покупок за планом поки немає.",
    no_published:
      "Опублікуйте план харчування, перш ніж розраховувати покупки.",
    status_open: "Очікує перевірки батьками",
    status_superseded: "Замінено новішим розрахунком",
    status_accepted: "Передано до списку покупок",
    status_covered: "Уже повністю покрито",
    required: "Потрібно за планом",
    stock: "Зафіксований залишок у коморі",
    open_shopping: "Залишилося у списку покупок",
    deficit: "Непокрита кількість",
    quantity: "Буде додано",
    shopping_id: "Позиція покупок",
    shopping_ids: "Створені позиції покупок",
    transfer_count: "Створено записів покупок",
    rounding_hint:
      "Додатна непокрита кількість округлюється вгору до 0,001 для списку покупок; точні залишок і покриття наведено вище.",
    prepare_hint:
      "Розрахунок створює лише приватну пропозицію. Він нічого не купує, не змінює залишки й не додає позиції до списку покупок.",
    accept_hint:
      "Підтвердження створює лише записи у списку покупок. Замовлення не оформлюється, залишки в коморі не списуються.",
    after_transfer_hint:
      "Цей план уже передано. Подальші зміни плану не оновлять створені позиції; редагуйте список покупок вручну.",
    terminal_empty_hint:
      "Нічого не додано: зафіксовані залишки й відкриті покупки вже покривають план.",
    module_off:
      "Для розрахунку одночасно ввімкніть модулі «Продукти й запаси» та «Покупки».",
  },
};
