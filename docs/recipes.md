# Mealie recipes / Рецепты Mealie / Рецепти Mealie

Optional development feature for a user's own **Mealie v3** server. This is a
read-only source, not a recipe scraper, automatic meal planner or ordering service.

## English

1. In your Mealie account, create an API token at **User profile → API tokens**
   (`/user/profile/api-tokens`). Prefer a separate account with only the recipe
   access you intend to share. A token may have more capabilities than this client
   uses; Family Assistant sends GET requests only.
2. As the household owner, open Family Assistant **Configure → Mealie recipes**.
   Enable the source and enter the base URL (without `/api`), token and timeout.
   HTTPS is the default. Explicitly allowing HTTP sends the token unencrypted;
   use that only on a network you trust. HA must be able to reach the server.
3. Keep **Pantry & household stock** enabled and open the **Weekly menu** card.
   Parents/owners can expand **Recipes from Mealie**, search or deliberately
   browse with an empty query, then select a recipe. Nothing fetches in the background.
4. Set **Week start** to that week's Monday, then choose a meal date within that
   week, meal slot and 1–50 servings.
   Check every ingredient's name, unit and **total quantity for those servings**.
   Changing servings does not scale quantities. Missing or unsupported source
   lines require explicit manual correction and their own verification checkbox, or
   explicit removal. Linked recipes are not fetched recursively.
5. Review the complete final draft, check the confirmation and create it. This
   creates **one new private plan with one meal**, not an update to an existing
   plan. Publish it separately in the menu card, reviewing that confirmation.
   Transfer to shopping has its own proposal and acceptance step;
   importing never places orders, changes stock or checks allergens.

When saving an existing configuration, a blank token field preserves its token
only for the same URL; the field never displays that token. A changed URL
requires a newly entered token. Turning off **Enable source** stops access but retains settings;
**Clear stored token** removes the active saved credential. Existing HA backups
are not erased. Concurrent configuration/identity changes reject stale forms;
reopen and review current settings. After a lost save response, use **Retry exact
request** to avoid a duplicate draft.

## Русский

1. В своей учётной записи Mealie создайте токен: **Профиль → API tokens**
   (`/user/profile/api-tokens`). Желательно выделить отдельную учётную запись
   с доступом только к нужным рецептам. Клиент использует только чтение, даже если
   сам токен позволяет больше.
2. Владелец семьи открывает **Настроить → Рецепты Mealie** в интеграции. Включите
   источник, укажите базовый URL без `/api`, токен и тайм-аут. По умолчанию нужен
   HTTPS. Разрешение HTTP означает передачу токена без шифрования; включайте его
   только в доверенной сети. Сервер должен быть доступен из Home Assistant.
3. Включите модуль **Продукты и запасы**. В карточке **Меню на неделю** родитель
   раскрывает **Рецепты из Mealie**, запускает поиск и выбирает рецепт. Пустой
   запрос позволяет просмотреть рецепты. Фоновой загрузки нет.
4. Укажите понедельник нужной недели, дату блюда, приём пищи и 1–50 порций.
   Проверьте название, единицу и **общее количество** каждого ингредиента.
   Изменение порций не пересчитывает количества. Проблемную строку нужно вручную
   исправить и отметить проверенной либо явно убрать. Вложенные рецепты не
   загружаются; неизвестные единицы не угадываются.
5. Проверьте итог целиком и подтвердите создание. Появится **новый приватный
   черновик с одним блюдом**; существующий план не изменится. Публикация и перенос
   в покупки подтверждаются отдельно. Заказов, списания запасов и проверки
   аллергенов здесь нет.

Пустое поле токена сохраняет прежний токен только для прежнего URL. Для другого
адреса введите новый токен. Выключение сохраняет настройки; отдельная галочка
очищает сохранённый токен, но не резервные копии HA. При изменении прав или
настроек устаревшая форма отклоняется: откройте её заново. Если ответ при
сохранении потерялся, повторите тот же запрос кнопкой, не создавая новый черновик.

## Українська

1. У власному обліковому записі Mealie створіть токен: **Профіль → API tokens**
   (`/user/profile/api-tokens`). Краще використати окремий обліковий запис лише
   з потрібними рецептами. Клієнт виконує тільки читання, навіть якщо токен
   дозволяє більше.
2. Власник сім'ї відкриває **Налаштувати → Рецепти Mealie** в інтеграції.
   Увімкніть джерело, введіть базовий URL без `/api`, токен і тайм-аут. Типово
   потрібен HTTPS. Дозвіл HTTP означає передавання токена без шифрування;
   використовуйте його лише в довіреній мережі. HA має бачити сервер.
3. Увімкніть **Продукти й запаси**. У картці **Меню на тиждень** батьки
   розгортають **Рецепти з Mealie**, запускають пошук і вибирають рецепт.
   Порожній запит дозволяє перегляд. Фонового завантаження немає.
4. Укажіть понеділок тижня, дату страви, прийом їжі та 1–50 порцій. Перевірте
   назву, одиницю й **загальну кількість** кожного інгредієнта. Зміна порцій
   нічого не перераховує. Проблемний рядок потрібно виправити вручну й позначити
   перевіреним або явно прибрати. Вкладені рецепти не завантажуються, одиниці
   не вгадуються.
5. Перевірте весь підсумок і підтвердьте створення. З'явиться **нова приватна
   чернетка з однією стравою**; наявний план не змінюється. Публікація та
   перенесення до покупок — окремі підтвердження. Замовлень, списання запасів
   і перевірки алергенів немає.

Порожнє поле зберігає старий токен лише для того самого URL. Інший URL потребує
заново введеного токена. Вимкнення зберігає налаштування; окрема позначка очищає
збережений токен, але не резервні копії HA. Застаріла форма після зміни прав або
налаштувань відхиляється: відкрийте й перевірте її заново. Якщо відповідь після
збереження втрачено, повторіть той самий запит кнопкою, не створюючи нову чернетку.

## Privacy and API contract

Owner-managed config-entry options hold `recipes` settings separately from the
public code and household domain records. Tokens are never prefilled or returned
by family views. Parent-visible `recipe_source` contains only `enabled`, provider
`mealie`, and an opaque revision. Children, other adults and guests cannot query
the provider. Access is rechecked after both successful and failed requests.
Disabling or revising a source removes old candidates from refreshed cards;
already viewed content, screenshots and in-flight requests cannot be recalled.

Only these fixed GET paths are used: `/api/app/about` (no token), `/api/recipes`,
`/api/recipes/{slug}`. Redirects are disabled. The response limit is 256 KiB and
timeouts are 5–30 seconds. Search uses `page` and `perPage=10`; page is 1–1000,
query at most 120 characters. Responses use Mealie's `items`, `per_page` and
`total_pages`; `next`/`previous` URLs are never followed. Inspection checks the
major version and authenticates a bounded one-item recipe listing.

Authenticated WebSocket `family_assistant/recipes` accepts `entry_id`, `kind`:

- `search`: `query` (default empty), `page` (default 1); returns `source_revision`,
  `page`, `total_pages`, `items` with `id`, `slug`, `name`.
- `get`: `slug` from that listing; returns `source_revision`, `candidate`.
  The candidate contains source identity, title, source servings, ingredient
  display/name/unit/quantity and explicit blockers, not recipe instructions,
  notes, images, linked URLs or arbitrary extras.

At most 100 source lines are accepted; more than 20 require explicit removals.
Names are at most 120 characters, units 24, display text 500. Quantities must be
positive, at most 1,000,000 and exact to at most three decimal places. Missing
servings are not guessed from free-text yield. Unknown shapes fail closed.

The final reviewed `pantry.meal_save` contains ordinary fields only:
`week_start`, `title`, `entries[{date,slot,title,servings,ingredients}]`, `note:""`.
No source ID, display text, token or dietary profile is persisted with that plan.
Private dietary notes are never sent to Mealie or used to infer food safety.

Official sources: [API usage and token creation](https://docs.mealie.io/documentation/getting-started/api-usage/),
[recipe routes](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/routes/recipe/recipe_crud_routes.py),
[pagination response](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/schema/response/pagination.py),
[ingredient schema](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/schema/recipe/recipe_ingredient.py).
This documents a v3 API contract, not a claim that every Mealie release was tested.
