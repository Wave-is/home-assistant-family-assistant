# Family Assistant Calendar / Календарь / Календар

User guide for the Family Assistant calendar module in Home Assistant.
Руководство пользователя модуля календаря Family Assistant в Home Assistant.
Посібник користувача модуля календаря Family Assistant у Home Assistant.

---

## English (EN)

### Overview & Activation

The calendar module is enabled via the integration's general options in Home Assistant (`settings.modules`). All calendar data is stored in durable local storage (`Store`) outside of code repositories, with zero credentials exposed publicly.

> [!NOTE]
> Testing was performed against an isolated Home Assistant 2026.8.2 environment. This guide documents current capabilities and does not claim a production deployment or public HACS release.

### UI Card (`custom:family-calendar-card`)

Add the card to any dashboard:

```yaml
type: custom:family-calendar-card
# entry_id is optional; automatically discovers household if omitted
# entry_id: your_entry_id
```

#### Card Capabilities

Authorized members can create and edit events through the card interface:

* **Title**, **Start / End**, **Timezone**
* **All-day event**: uses an exclusive end date: October 10–11 means October 10 only
* **Participants** and optional **Adult Escort** (`escort` must be `owner`, `parent`, or `adult`)
* **Preparation checklist** (`preparation` items)
* **Reminders**: customizable notification offsets in minutes (`reminder_minutes`)
* **Visibility**: `family` (shared across household) or `participants` (restricted to assigned members)

> [!IMPORTANT]
> Recurrence rules (daily, weekly, monthly) and linking task IDs (`task_ids`) are fully supported by the underlying Domain API. However, advanced UI controls for recurrence and tasks are not yet implemented in the card interface.

### Roles & Permissions

* **Parent / Owner**: Can view, create, edit, approve, cancel, and archive all events.
* **Adult**: Can manage their own events and act as an escort.
* **Child**: Can create own events (created with `tentative` status awaiting parent approval). Any subsequent edit by a child resets status to `tentative`, requiring re-approval.
* **Guest**: No access to calendar actions or views.

### Telegram Commands

Integration with Telegram provides typed commands:

* `/calendar` — Displays upcoming events (within 30 days).
* `/event <title> | <ISO start with offset> | <ISO end with offset>` — Quick event creation.
  * Example: `/event Dentist | 2026-10-01T09:00+03:00 | 2026-10-01T10:00+03:00`
* `/eventapprove <event_id> | <reason>` — Approve a tentative event (Parents/Owners only).
  * Example: `/eventapprove E000001 | Approved for dental appointment`
* `/eventcancel <event_id> | <reason>` — Cancel an event.
  * Example: `/eventcancel E000001 | Rescheduled`

#### Privacy in Telegram

* **Group Chats**: Automatically hide participant-only (`participants`) and tentative (`tentative`) events to protect member privacy.
* **Private Messages (PM)**: Authorized users can see full event details, including tentative and participant-only items.

### Reminders & Notifications

* Sent exclusively to assigned **participants** and the designated **escort** via private notifications.
* **Catch-up & Expiry Window**: Reminders trigger within a 5-minute catch-up window (`now - 5m <= due <= now`) and expire after 5 minutes.
* **No Offline Backlog**: If Home Assistant was offline, missed reminders outside the 5-minute window are dropped rather than flooding users.
* **Safety**: Reminders are strictly notifications with preparation checklists; they trigger no physical device effects or automations.

### Home Assistant Calendar Entity Integration

* **Read-Only**: The published Home Assistant calendar entity is strictly read-only.
* **Owner Opt-In**: Disabled by default. An owner must explicitly enable `publish_to_ha` with an explicit confirmation (`confirm_public_visibility`).
* **Entity Access**: Only `family` visibility events that are `confirmed` are published to the HA entity, viewable by any HA user with access to that entity.
* **Privacy Boundary**: `participants` (private) and `tentative` events are never published to Home Assistant.
* **Revocation**: Disabling `publish_to_ha` immediately clears the live calendar state.
* **Recorder History Note**: Prior events may persist in the Home Assistant recorder database, because disabling this feature does not purge recorder history.

### Data Lifecycle

* Events are never hard-deleted; cancellation and archiving preserve audit history (`history`).

---

## Русский (RU)

### Обзор и включение

Модуль календаря активируется в общих настройках интеграции Home Assistant (`settings.modules`). Все данные хранятся в постоянном локальном хранилище (`Store`) вне кодовой базы без публичных учетных данных.

> [!NOTE]
> Тестирование проводилось в изолированной среде Home Assistant 2026.8.2. Документ отражает текущее состояние и не заявляет о релизе в HACS или развертывании в production.

### Карточка интерфейса (`custom:family-calendar-card`)

Добавление на панель дашборда:

```yaml
type: custom:family-calendar-card
# entry_id не обязателен; домохозяйство определяется автоматически
# entry_id: your_entry_id
```

#### Возможности карточки

Авторизованные пользователи могут создавать и редактировать события:

* **Название**, **Начало / Окончание**, **Часовой пояс**
* **Событие на весь день (All-day)**: исключающая граница окончания (exclusive end)
* **Участники** и сопровождающий взрослый (**Adult Escort**: только роли `owner`, `parent`, `adult`)
* **Список подготовки** (`preparation`)
* **Напоминания**: смещение оповещений в минутах (`reminder_minutes`)
* **Видимость**: `family` (для всей семьи) или `participants` (только для участников)

> [!IMPORTANT]
> Правила повторения (ежедневно, еженедельно, ежемесячно) и связывание задач (`task_ids`) поддерживаются на уровне API домена, однако расширенные элементы управления в карточке пока не реализованы.

### Роли и права доступа

* **Родитель / Владелец (Parent / Owner)**: Полное управление всеми событиями, включая утверждение, отмену и архивацию.
* **Взрослый (Adult)**: Управление собственными событиями, роль сопровождающего.
* **Ребенок (Child)**: Создание личных событий (статус `tentative` — ожидает одобрения родителя). Любое изменение события ребенком требует повторного утверждения.
* **Гость (Guest)**: Доступ к календарю запрещен.

### Команды Telegram

* `/calendar` — Список ближайших событий (на 30 дней).
* `/event <название> | <ISO начало со смещением> | <ISO окончание со смещением>` — Быстрое создание.
  * Пример: `/event Стоматолог | 2026-10-01T09:00+03:00 | 2026-10-01T10:00+03:00`
* `/eventapprove <ID события> | <причина>` — Одобрение события (только родители/владельцы).
  * Пример: `/eventapprove E000001 | Согласовано`
* `/eventcancel <ID события> | <причина>` — Отмена события.
  * Пример: `/eventcancel E000001 | Перенесено`

#### Приватность в Telegram

* **Групповые чаты**: Личные события (`participants`) и неподтвержденные события (`tentative`) скрываются.
* **Личные сообщения (ЛС)**: Отображаются все события, доступные пользователю по его правам.

### Напоминания и уведомления

* Отправляются только **участникам** и **сопровождающему** в личные сообщения.
* **Окно догона и истечения**: Напоминания отправляются в 5-минутном окне (`now - 5m <= due <= now`) и сгорают через 5 минут.
* **Без очереди после офлайна**: Пропущенные за время отсутствия связи напоминания не спамят при перезапуске.
* **Безопасность**: Напоминания носят исключительно информационный характер и не вызывают физических воздействий на устройства.

### Экспорт в стандартный календарь Home Assistant

* **Только чтение (Read-only)**: Сущность календаря доступна только для чтения.
* **Явное подтверждение владельца**: Отключено по умолчанию. Владелец должен подтвердить включение флагом `confirm_public_visibility`.
* **Доступ**: Экспортируются только подтвержденные события с видимостью `family`. События видны всем пользователям HA с доступом к сущности.
* **Защита приватности**: События `participants` и `tentative` никогда не экспортируются.
* **Отзыв доступа**: Отключение публикации очищает текущее состояние сущности.
* **История в Recorder**: Записи, уже сохраненные в базе данных Home Assistant Recorder, могут оставаться в истории, поскольку отключение этой функции не очищает историю Recorder.

### Жизненный цикл данных

* Физическое удаление событий отсутствует. Отмена и архивация сохраняют полную историю изменений (`history`).

---

## Українська (UK)

### Огляд та активація

Модуль календаря активується в загальних налаштуваннях інтеграції Home Assistant (`settings.modules`). Усі дані зберігаються у локальному сховищі (`Store`) поза кодовою базою, без публічного розкриття облікових даних.

> [!NOTE]
> Тестування проводилося в ізольованому середовищі Home Assistant 2026.8.2. Документ описує поточні можливості та не заявляє про реліз у HACS чи публічний продакшн-деплой.

### Картка інтерфейсу (`custom:family-calendar-card`)

Додавання на панель:

```yaml
type: custom:family-calendar-card
# entry_id необов'язковий; домогосподарство визначається автоматично
# entry_id: your_entry_id
```

#### Можливості картки

Авторизовані учасники можуть створювати та редагувати події:

* **Назва**, **Початок / Завершення**, **Часовий пояс**
* **Подія на весь день (All-day)**: конвенція виключної кінцевої дати (exclusive end)
* **Учасники** та дорослий супроводжуючий (**Adult Escort**: дозволені ролі `owner`, `parent`, `adult`)
* **Список підготовки** (`preparation`)
* **Нагадування**: інтервали сповіщень у хвилинах (`reminder_minutes`)
* **Видимість**: `family` (для всієї родини) або `participants` (лише для призначених учасників)

> [!IMPORTANT]
> Правила повторення (щодня, щотижня, щомісяця) та зв'язування завдань (`task_ids`) підтримуються на рівні Domain API, але інтерфейсні елементи керування цим у картці поки не реалізовані.

### Ролі та права доступу

* **Батьки / Власник (Parent / Owner)**: Повне керування всіма подіями, включаючи схвалення, скасування та архівування.
* **Дорослий (Adult)**: Керування власними подіями та можливість бути супроводжуючим.
* **Дитина (Child)**: Створення власних подій (статус `tentative` — очікує схвалення батьків). Будь-яке редагування дитиною потребує повторного схвалення.
* **Гість (Guest)**: Доступ до дій та перегляду календаря заблоковано.

### Команди Telegram

* `/calendar` — Перегляд майбутніх подій (на 30 днів).
* `/event <назва> | <ISO початок зі зміщенням> | <ISO завершення зі зміщенням>` — Швидке створення події.
  * Приклад: `/event Стоматолог | 2026-10-01T09:00+03:00 | 2026-10-01T10:00+03:00`
* `/eventapprove <ID події> | <причина>` — Схвалення події (тільки для батьків та власників).
  * Приклад: `/eventapprove E000001 | Погоджено`
* `/eventcancel <ID події> | <причина>` — Скасування події.
  * Приклад: `/eventcancel E000001 | Перенесено`

#### Приватність у Telegram

* **Групові чати**: Особисті події (`participants`) та події на розгляді (`tentative`) приховуються.
* **Особисті повідомлення (ПП)**: Відображаються всі дозволені користувачеві події.

### Нагадування та сповіщення

* Надсилаються виключно **учасникам** та **супроводжуючому** в приватні повідомлення.
* **Вікно наздоганяння та застарівання**: Спрацьовують у межах 5-хвилинного вікна (`now - 5m <= due <= now`) та згорають через 5 хвилин.
* **Без накопичення беклогу офлайн**: Пропущені за час простою сповіщення не накопичуються та відкидаються.
* **Безпека**: Нагадування мають виключно інформаційний зміст і не спричиняють жодних фізичних дій чи керування пристроями.

### Експорт у стандартний календар Home Assistant

* **Тільки для читання (Read-only)**: Сутність календаря Home Assistant доступна виключно для читання.
* **Особисте підтвердження власника**: Вимкнено за замовчуванням. Власник має явно увімкнути експорт із підтвердженням `confirm_public_visibility`.
* **Доступ**: Експортуються лише підтверджені події з видимістю `family`. Вони видимі будь-якому користувачу HA з правами доступу до цієї сутності.
* **Межа приватності**: Події `participants` та `tentative` ніколи не потрапляють до сутності HA.
* **Відкликання доступу**: Вимкнення публікації миттєво очищує поточний стан сутності.
* **Історія в Recorder**: Дані, які вже були збережені в базі даних Home Assistant Recorder, залишаються в історії, оскільки вимкнення цієї функції не очищує історію Recorder.

### Життєвий цикл даних

* Події не видаляються безповоротно. Скасування та архівування зберігають повну історію аудиту (`history`).
