# Home maintenance / Обслуживание дома / Обслуговування дому

Development module. Enable **Home maintenance** in integration options and use
`custom:family-maintenance-card`. Fault reports and recurring services also need
**Tasks**. The card editor chooses the household/language; the signed-in account
determines permissions. Recurring service tasks support private photo reports;
initial fault photos and manual log/document attachments are not supported yet.

## English

Parents/owners register equipment: name, category, location, responsible member,
optional warranty date/vendor/reference, private note and manually recorded
consumables. Review the complete record before saving. A change replaces all
editable fields; nothing is guessed from a device name or sent to a supplier.

By default only parents and the current responsible person can report a fault.
A parent can explicitly allow other non-guest family members to report this
equipment; this exposes its name/category/location, not warranty/private notes.
A fault has a short task title and separate private details. Saving creates one
ordinary private task assigned to the reviewed responsible person. The reporter
can follow that fault; the current assignee works in Tasks, and parents review
completion. An identical open report by the same reporter is rejected. Details,
warranty and equipment notes are never copied into the task title.

Parents can schedule service as an ordinary recurring task: choose assignees,
rotation or individual duties, recurrence, creation time, due time and checklist.
Choose a text or photo completion report. Photo tasks use the private upload and
separate submission in the [Tasks card](tasks.md); changing the service title
does not reset that choice. No photo is sent to Telegram or a model.
The existing Tasks scheduler handles reminders and reviews. Maintenance service
penalties start at zero. Service edits belong in Maintenance, not the generic
task-series editor. Changing the equipment, approving parent or an assignee's
member record suspends generation until a parent reviews and saves the current
versions again. Disabling Maintenance or Tasks also prevents new service tasks.
Already created tasks remain real work, with current Tasks permissions; retiring
equipment does not silently complete or delete them.

Record a service history entry with the actual local date and a description.
Optionally link a completed task for this equipment and list consumed items.
This records a person's statement, **not a verified repair or stock deduction**.
It does not change task status, make purchases or control equipment. Retired
equipment still accepts historical service records. Retiring requires a reason
and preserves parent-visible history; it is not deletion or backup erasure.

All writes use reviewed versions. After a lost response, retry the same operation
to recover its receipt rather than create another task/log. Changed permissions
or identity still revoke access. Private task details are excluded from group
task lists and automatic model input; notifications target the assignee/parents
privately. Missing Telegram enrollment does not turn a private message into a
family-group message.

## Русский

Включите **Обслуживание дома** и добавьте карточку этого модуля. Для поломок и
регламентных работ также включите **Задачи**. Родитель или владелец заводит
оборудование: название, категорию, расположение, ответственного, гарантийные
сведения, приватную заметку и расходники. Перед сохранением проверяется вся
карточка: изменение заменяет её редактируемые поля целиком.

По умолчанию сообщить о поломке могут родители и актуальный ответственный.
Родитель может отдельно разрешить сообщения остальным участникам, кроме гостей.
Им станут видны название, категория и расположение, но не гарантия и заметки.
Краткое описание станет названием приватной задачи ответственному; подробности
останутся в сообщении о поломке. Автор следит за своей поломкой, исполнитель
работает в карточке задач, родитель подтверждает результат. Одинаковая открытая
поломка от того же автора не создаёт ещё одну задачу.

Для регламентной работы родитель выбирает исполнителей, ротацию, повторение,
время создания, срок и чек-лист. Используются существующие задачи и напоминания;
можно потребовать текстовый или фотоотчёт. Фото загружается и отдельно сдаётся
в карточке задач, приватно и без отправки в Telegram или ИИ. Правка названия
регламента сохраняет выбранный тип отчёта;
штраф изначально равен нулю. Расписание редактируется в обслуживании, а не в
общем редакторе повторяющихся задач. Изменение оборудования, родителя,
подтвердившего настройку, или карточки исполнителя приостанавливает новые
экземпляры до повторной проверки и сохранения актуальных версий. Отключение
модулей также останавливает создание. Уже созданные задачи не исчезают и не
становятся выполненными при списании оборудования.

История обслуживания содержит местную дату, описание и по желанию завершённую
задачу этого оборудования и расходники. Это **запись человека, а не проверка
ремонта или автоматическое списание запасов**. Она не меняет задачу, не делает
заказы и не управляет устройствами. Можно записать прошлую работу и после
списания оборудования. Списание требует причины и сохраняет историю родителей.

После потери ответа повторяется тот же проверенный запрос без дубля. Изменение
прав не обходится повтором. Приватные задачи не попадают в групповой список и
автоматический контекст ИИ; уведомления идут исполнителю или родителям лично.
Если личный чат не подключён, система не подменяет его семейной группой.
Фото самой поломки и вложения к ручному журналу пока не поддерживаются.
Данные хранятся локально вне каталога
обновляемого HACS-кода; администратор HA и резервные копии имеют к ним доступ.

## Українська

Увімкніть **Обслуговування дому** та додайте його картку. Для несправностей і
регламентних робіт також потрібні **Завдання**. Батьки або власник реєструють
обладнання: назву, категорію, розташування, відповідального, гарантійні відомості,
приватну примітку й витратні матеріали. Перед збереженням перевіряють увесь запис:
редагування замінює всі його редаговані поля.

Типово повідомляти про несправність можуть батьки й чинний відповідальний.
Батьки можуть окремо дозволити це іншим учасникам, крім гостей: їм відкриються
назва, категорія та розташування, але не гарантія чи примітки. Короткий опис стає
назвою приватного завдання відповідальному; подробиці залишаються у повідомленні.
Автор стежить за власною несправністю, виконавець працює в Завданнях, батьки
підтверджують завершення. Однакова відкрита несправність від того самого автора
не породжує ще одного завдання.

Для регламентної роботи батьки обирають виконавців, ротацію, повторення, час
створення, строк і чекліст. Працює наявний механізм завдань і нагадувань; штраф
початково нульовий. Розклад редагують в Обслуговуванні, не в загальному редакторі
серій завдань. Зміна обладнання, батьківського підтвердження або картки виконавця
зупиняє нові екземпляри до перевірки й збереження чинних версій. Вимкнення модулів
також зупиняє створення. Раніше створені завдання залишаються: списання обладнання
не видаляє й не завершує їх непомітно.

Історія обслуговування містить місцеву дату, опис, за бажанням завершене завдання
цього обладнання та використані матеріали. Це **запис людини, не підтверджена
перевірка ремонту й не автоматичне списання запасів**. Він не змінює завдання,
не робить замовлень і не керує пристроями. Можна додавати минулі роботи й після
списання обладнання. Списання потребує причини та зберігає батьківську історію.

Після втрати відповіді повторюється той самий перевірений запит без дубля.
Відкликання прав не обходиться повторенням. Приватні завдання не потрапляють
до групового списку чи автоматичного контексту ШІ; повідомлення надсилаються
виконавцю або батькам особисто. Відсутність особистого чату не перенаправляє їх
до сімейної групи. Для регламенту можна обрати текстовий або фотозвіт:
фото приватно завантажується й окремо здається в картці завдань, без Telegram
чи ШІ. Зміна назви зберігає тип звіту. Фото самої поломки та вкладення до
ручного журналу поки не підтримуються. Локальні дані поза
каталогом HACS доступні адміністратору HA та входять до резервних копій.

## API boundaries

- `maintenance.asset_save`: full replacement with strict current `id/revision`
  when editing, and `responsible_member_revision`. New records omit both identity
  fields; `reportable` defaults false and is preserved if omitted on edit.
- `asset_retire`: `id`, `revision`, nonempty `reason` (500 chars).
- `fault_report`: current `asset_id/asset_revision`, `reporter_member_revision`,
  `summary` (200), `details` (2000), `attachment_ids: []`.
- `service_save`: current asset and optional existing series identity/revision,
  `title`, `assignees: [{id,revision}]`, `rotation`, `rule`, `due_time`,
  `checklist`, `enabled`, `reminder_minutes`, `grace_minutes`, optional
  `report_type` (`text` or `photo`; new defaults to text, omitted edit preserves).
  Existing recurrence
  rules and their DST/catch-up safeguards apply; no separate scheduler.
- `service_enable`: current `id/revision`, `asset_revision`, boolean `enabled`.
- `service_log`: current asset, `performed_on` (not a future household-local date),
  `summary` (2000), `task: null` or completed matching `{id,revision}`,
  `consumables_used`, `attachment_ids: []`. At most one log links a given task.

Warranty has exact `expires_on` (ISO date or null), `vendor`, `reference` fields.
Consumable rows have `label`, `unit`, positive quantity with up to three decimal
places, and `pantry: null` or a current same-unit `{id,revision}` reference.
There is no automatic decrement. Stale references must be explicitly corrected.
Opaque receipts contain IDs/versions/status, not private notes. Store keeps
assets/faults/logs under `maintenance` and service rules under `task_series`;
materialized tasks retain private source provenance locally. API versions are
strict JSON-safe integers. No photographs, document bytes, paths or URLs are
accepted as attachments in this stage.
