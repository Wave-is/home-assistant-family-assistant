# School preparation reminder retention

This checkpoint bounds the durable markers and outbox intents created by the
opt-in school preparation reminder. It does not add a new schedule, reminder,
routine start, task, score, device action, or message body.

## User-visible behavior / Для пользователя / Для користувача

**EN.** Cleanup is automatic and does not change reminder preferences. Messages
that are waiting, being sent, or have an uncertain result are preserved for
review. Completed old records are removed without allowing an old school date
to send again after a clock rollback. If safe cleanup cannot continue, Home
Assistant shows one counts-only Repair; it contains no child, timetable,
recipient, or message details.

**RU.** Очистка выполняется автоматически и не меняет настройки напоминаний.
Сообщения, которые ожидают отправки, отправляются или имеют неизвестный
результат, сохраняются для проверки. Старые завершённые записи удаляются так,
чтобы откат часов не отправил напоминание за прежний учебный день повторно.
Если безопасная очистка невозможна, Home Assistant показывает одну проблему
Repair только со счётчиками — без данных ребёнка, расписания, получателя и
текста сообщения.

**UK.** Очищення виконується автоматично й не змінює налаштування нагадувань.
Повідомлення, які очікують надсилання, надсилаються або мають невідомий
результат, зберігаються для перевірки. Старі завершені записи видаляються так,
щоб відкат годинника не надіслав нагадування за минулий навчальний день ще
раз. Якщо безпечне очищення неможливе, Home Assistant показує одну проблему
Repair лише з лічильниками — без даних дитини, розкладу, одержувача чи тексту
повідомлення.

## Stored lineage

The existing marker key is the exact JSON tuple
`[recipient, timetable_id, school_date]`. Its value pins the event ID plus the
timetable, member, recipient, routine, and subscription revisions. The paired
outbox event must:

- have key `school_preparation_reminder` and the same recipient;
- carry exactly the current reminder event fields;
- match the marker's timetable, date, and every pinned revision;
- have a valid policy fingerprint, creation time, and first-lesson expiry;
- describe the actual today-or-tomorrow reminder interval (bounded to three
  elapsed days to cover extreme lesson clocks and daylight-saving changes).

Unknown fields, malformed values, missing pairs, mismatches, and unsupported
states fail closed. They remain stored and increase counts-only health signals;
retention never guesses which other record is safe to remove.

## Terminal retention

An exact pair is removed atomically only when both the event and all delivery
records are terminal and the horizon measured from `expires_at` has elapsed:

- `sent`, `superseded`, or explicitly `resolved`: 35 days;
- `failed`: 90 days.

Events in `pending`, `awaiting_channel`, `sending`, or `uncertain` are never
deleted by this policy. A terminal event with a pending, sending, unknown, or
otherwise incompatible delivery record is also retained. An explicitly
`resolved` event may retire a delivery whose last transport result was
`uncertain`; that is an operator acknowledgement, not a claim that delivery
succeeded.

## Clock rollback protection

Deleting a marker alone would allow the same date to be generated after a wall
clock rollback. Each successful prune therefore advances one bounded,
monotonic record at
`school.preparation_reminder_retention`:

```json
{
  "through_date": "2026-09-08",
  "updated_at": "2026-10-13T05:30:00+00:00"
}
```

It contains no recipient, child, timetable, routine, lesson, or message data.
Reminder creation must reject a target date at or before `through_date`. A
future jump followed by a rollback may conservatively suppress reminders until
the real date passes the watermark; it must never replay an old date.

## Capacity and health

Both live marker count and retained school-reminder event count are bounded at
10,000. Creation stops if either reaches the cap. `health_stats` returns only
counts and booleans: marker, retained, unresolved, unpaired, retention-error,
capacity, and clock-rollback signals. It never returns member IDs, Telegram
targets, dates, timetable IDs, event IDs, or content.

Malformed retention state blocks pruning and creation. This preserves evidence
for a repair flow instead of silently weakening replay protection.

## Shared integration required

`school_retention.py` exports:

- `prune(ctx) -> int`: remove exact eligible pairs and advance the watermark;
- `creation_allowed(state, target_date) -> bool`: enforce the watermark and
  both 10,000-record caps;
- `health_stats(state, now=None) -> dict`: pure counts-only health.

The existing `school_reminders.tick(ctx)` should call `prune(ctx)` at its start,
inside the same Engine transaction and before its existing marker-cap early
return. It should call `creation_allowed` immediately after computing its
household-local target date, and again immediately before every `ctx.notify`.
The inner check is required because one tick can add several intents and the
retained-outbox cap must not be crossed inside that loop. This makes deletion,
watermark persistence, and any new intent one Store commit. A failed Store
write then rolls all three back.

The Repairs/health adapter may call `health_stats(engine.snapshot(), now)`.
No scheduler should delete marker or outbox records directly, and no repair
action should rewrite the monotonic watermark automatically.
