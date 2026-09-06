# Routines / Распорядки / Розпорядки

## English (EN)

The routines module provides opt-in, non-punitive checklists for family habits. Turning the module off in settings stops routine execution and entity reads without stopping the integration's shared background engine; active runs cancel with reason `authorization_removed`. Each household stores durable data in its own separate Home Assistant `Store` file, surviving restarts.

Routine notifications respect quiet hours and the durable delivery policy. These
steps do not replace alarm challenges or stop an alarm siren. Deactivating an
assignee (or changing their role to guest) cancels their active runs.

### Core Mechanics & Roles

* **Ownership & Roles**: Only parents/owners can create or edit routine templates (`U...`) and household modes. Children can only view assigned routines and start or advance their own active runs (`J...`).
* **Starts & Runs**: Scheduled ticks instantiate an independent run for every assigned member (`assignees`, up to 20). Manual `/routinestart` or UI start targets exactly one member. Exactly one active run is permitted per template and member at a time.
* **Step Progression**: Each step specifies non-decreasing `offset_minutes` from planned start. A step activates only after all previous steps are completed/skipped **and** server time reaches `planned_at + offset_minutes`.
* **Escalation & Incidents**: `escalate_minutes` counts from step activation. If overdue, an incident notifies parents once. If that notification was actually sent, in-flight, or uncertain, closing the step or run announces closure to parents; unsent alerts are superseded quietly.
* **Safety & Non-Actuation**: Routines observe but **never** actuate Home Assistant devices. Missing or overdue steps never incur automatic penalties or court point deductions.
* **Observation Allowlist & Conditions**: Sensor checks test exact string state equality (not numeric thresholds) against up to 50 owner-approved entities (`domain.object`). States must be recent (default max age 120s, range 1–3600s; timestamps >5s in the future evaluate to `None`). Unknown, unavailable, or stale states yield `None`; negation of `None` remains `None` (never `True`).
* **Skip Scope**: Step `skip_when` is evaluated strictly at step activation. Template-level `skip_when` is evaluated at run creation (skipping all steps if `True`).
* **Confirmations**: Manual steps issue a fresh plaintext nonce per activation. Nonces bind the confirmation to that exact step and run—they do not prove biometric presence or human identity (an authenticated client can automate calls). Parents can override any active step or cancel a run with a required reason.
* **Edits & Lifecycle**: Template edits do not rewrite active runs. Setting `enabled: false` prevents new starts while letting active runs finish. Revoking creator permissions cancels associated active runs. Recurrence catch-up is bounded to 24h by default (0–48h max, at most 3 local dates deduplicated).
* **Current UI Scope**: Recurrence rules are currently configured via API only. Per-step different assignees are pending. Template-level skip rules from presets/API are preserved but not edited in UI.

### Dashboard Card & Telegram

* **Card (`custom:family-routines-card`)**: Single-entry setups discover `entry_id` automatically (`entry_id` is optional). No placeholder entities required.
* **Telegram**: Routine commands work **only in private bot chat** (group chat commands are rejected):
  * `/routines` — List templates and recent runs.
  * `/routine morning | member` — Create template from preset (`morning`, `evening`, `school_bag`).
  * `/routinestart U000001 | member` — Start a run for an assigned member.
  * `/routinecancel J000001 | reason` — Cancel an active run (parents only).
  * `/routinemode holidays, guests` — Set household modes (canonical values: `normal` [exclusive], `holidays`, `guests`, `ill`, `vacation`).

---

## Русский (RU)

Модуль распорядков помогает формировать семейные привычки без автоматических штрафов. Выключение модуля останавливает обработку рутин и чтение сенсоров, не затрагивая общий фоновый планировщик интеграции; активные выполнения отменяются (`authorization_removed`). Данные каждой семьи сохраняются в отдельном файле Home Assistant `Store` и переживают перезагрузку.

Уведомления рутин соблюдают тихие часы и общую политику доставки. Шаги не заменяют
проверки пробуждения и не останавливают сирену будильника. Деактивация исполнителя
или перевод в гости отменяет его активные выполнения. Максимальная давность
показаний — 120 секунд по умолчанию, настраивается от 1 до 3600 секунд.

### Принципы работы

* **Роли**: Шаблоны (`U...`) и режимы настраивают только родители/владелец. Дети видят свои распорядки и запускают только собственные выполнения (`J...`).
* **Запуск**: Расписание создаёт отдельное выполнение для каждого участника (`assignees`, до 20). Ручной запуск стартует выполнение ровно для одного участника. На один шаблон и участника может быть только одно активное выполнение.
* **Шаги и эскалация**: Шаг активируется, только когда завершены все предыдущие шаги **и** наступило время `planned_at + offset_minutes`. Таймер `escalate_minutes` отсчитывается от момента активации шага. При просрочке родители получают уведомление; сообщение о закрытии инцидента отправляется, только если оповещение уже отправлено, доставляется или его статус неопределён (неотправленные тихо заменяются).
* **Безопасность и сенсоры**: Модуль только наблюдает и **никогда** не управляет устройствами. Штрафные баллы за задержки отсутствуют. Проверка сенсоров сравнивает состояние на точное равенство строк (не числовые пороги) по белому списку владельца (до 50 сущностей). Устаревшие (>120 с) или «будущие» (>5 с) данные дают `None`. Недоступные сущности (`unavailable`/`unknown`) дают `None`, отрицание `None` не равно `True`.
* **Пропуск и подтверждение**: `skip_when` шага проверяется при его активации, а `skip_when` шаблона — при старте выполнения. Для ручного шага создаётся свежий незашифрованный nonce (привязка к текущему шагу, не биометрия и не защита от автоматизации клиентом). Родитель может переопределить шаг или отменить выполнение с указанием причины.
* **Правки и UI**: Правка шаблона не перезаписывает текущие выполнения. `enabled: false` запрещает новые старты. Повторение задаётся через API; разные исполнители на отдельные шаги пока не поддерживаются.

### Карточка и Telegram

* **Карточка (`custom:family-routines-card`)**: `entry_id` опционален при одной семье. Заглушки сущностей не требуются.
* **Telegram (только личный чат с ботом)**:
  * `/routines` — список шаблонов и выполнений.
  * `/routine morning | участник` — создание шаблона из пресета.
  * `/routinestart U000001 | участник` — запуск для одного участника.
  * `/routinecancel J000001 | причина` — отмена родителем.
  * `/routinemode holidays, guests` — режимы: `normal` (только отдельно), `holidays` (каникулы), `guests` (гости), `ill` (болезнь), `vacation` (отпуск).

---

## Українська (UK)

Модуль розпорядків допомагає формувати сімейні звички без автоматичних штрафів. Його вимкнення припиняє обробку рутин і читання сенсорів, не зупиняючи загальний фоновий планувальник інтеграції; активні виконання скасовуються (`authorization_removed`). Дані кожної родини зберігаються в окремому сховищі Home Assistant `Store` та стійкі до перезапусків.

Сповіщення рутин дотримуються тихих годин і загальної політики доставки. Кроки не
замінюють перевірок пробудження та не зупиняють сирену будильника. Деактивація
виконавця або зміна його ролі на гостя скасовує активні виконання. Максимальна
давність показань — 120 секунд за замовчуванням, налаштовується від 1 до 3600 секунд.

### Принципи роботи

* **Ролі**: Шаблони (`U...`) і режими налаштовують лише батьки або власник. Діти бачать призначені рутини та запускають лише власні виконання (`J...`).
* **Запуск**: Розклад створює окреме виконання кожному призначеному учасникові (`assignees`, до 20). Ручний запуск призначений рівно для одного учасника. Дозволено лише одне активне виконання на шаблон і учасника.
* **Кроки та ескалація**: Крок активується лише після завершення попередніх кроків **і** настання `planned_at + offset_minutes`. Таймер `escalate_minutes` рахується від активації кроку. У разі запізнення батькам відкривається інцидент; закриття сповіщається батькам, лише якщо перше сповіщення відправлено, перебуває в процесі чи має невизначений статус (невислані тихо скасовуються).
* **Безпека та сенсори**: Модуль лише спостерігає та **ніколи** не керує приладами. Автоштрафи відсутні. Умови перевіряють строковий збіг стану (не числові пороги) за білим списком власника (до 50 сутностей). Застарілі (>120 с) чи «майбутні» (>5 с) спостереження повертають `None`. Стан `unavailable`/`unknown` дає `None`, заперечення якого ніколи не є `True`.
* **Пропуск та підтвердження**: `skip_when` кроку перевіряється під час його активації; `skip_when` шаблону — під час створення виконання. Ручне підтвердження використовує свіжий відкритий nonce (прив'язка до поточного кроку, а не біометрія чи захист від клієнтської автоматизації). Батьки можуть переозначити крок або скасувати рутину з причиною.
* **Зміни та стан UI**: Зміна шаблону не змінює активні виконання. `enabled: false` зупиняє нові старти. Розклад наразі налаштовується через API; різні виконавці для окремих кроків у розробці.

### Картка та Telegram

* **Картка (`custom:family-routines-card`)**: `entry_id` необов'язковий для однієї сім'ї. Заглушки сутностей не потрібні.
* **Telegram (лише особистий чат із ботом)**:
  * `/routines` — перелік шаблонів і виконань.
  * `/routine morning | учасник` — шаблон із пресету.
  * `/routinestart U000001 | учасник` — старт виконання для учасника.
  * `/routinecancel J000001 | причина` — скасування батьками.
  * `/routinemode holidays, guests` — сімейні режими: `normal` (виключний), `holidays` (канікули), `guests` (гості), `ill` (хвороба), `vacation` (відпустка).

---

## Shared API Example / Пример API / Приклад API

WebSocket command `family_assistant/execute` saving a recurring weekday school routine.
*(Note: IDs like `U...` are assigned by the server; replace synthetic `"M000001"` with a real internal member ID from `family_assistant/view`)*:

```json
{
  "id": 1,
  "type": "family_assistant/execute",
  "entry_id": "synthetic-entry",
  "operation_id": "unique-example-1",
  "action": "routines.save",
  "payload": {
    "title": "School Morning Routine",
    "description": "Weekday morning habits",
    "assignees": ["M000001"],
    "enabled": true,
    "skip_when": {
      "kind": "any",
      "conditions": [
        {"kind": "mode", "mode": "holidays"},
        {"kind": "mode", "mode": "vacation"}
      ]
    },
    "rule": {
      "frequency": "weekly",
      "interval": 1,
      "start_date": "2026-09-07",
      "time": "07:00",
      "timezone": "Europe/Kyiv",
      "weekdays": [0, 1, 2, 3, 4],
      "catchup_hours": 24
    },
    "steps": [
      {
        "title": "Wake up and stretch",
        "offset_minutes": 0,
        "confirmation": "manual",
        "completion_condition": null,
        "skip_when": null,
        "escalate_minutes": 15
      },
      {
        "title": "Wash face and brush teeth",
        "offset_minutes": 15,
        "confirmation": "manual",
        "completion_condition": null,
        "skip_when": null,
        "escalate_minutes": 15
      },
      {
        "title": "Healthy breakfast",
        "offset_minutes": 30,
        "confirmation": "manual",
        "completion_condition": null,
        "skip_when": null,
        "escalate_minutes": 20
      },
      {
        "title": "Check school backpack",
        "offset_minutes": 50,
        "confirmation": "manual",
        "completion_condition": null,
        "skip_when": null,
        "escalate_minutes": 10
      }
    ]
  }
}
```
