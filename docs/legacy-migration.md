# Legacy migration contract / Соглашение о миграции со старой системы / Угода про міграцію зі старої системи

[Advanced read-only copy wizard / Мастер проверочной копии / Майстер перевірочної копії](legacy-copy-wizard.md)

[Cross-ledger consistency checks and packaging / Согласованность и сборка / Узгодженість і створення архіву](legacy-source-links.md)

[Source preparation wizard / Мастер подготовки / Майстер підготовки](legacy-preparation.md)

[Isolated migration review / Проверка переноса / Перевірка перенесення](legacy-shadow.md)

## English

Status: read-only preflight, immutable source/member review, private archive codec
and joined conversion proposals; not a complete import or live cutover feature.
The old private integrations remain running until a separately verified switch.
Only synthetic examples belong in this repository.

The current [advanced read-only copy wizard](legacy-copy-wizard.md) combines the
internal stages described here. [Cross-ledger consistency checks and deterministic
packaging](legacy-source-links.md) add a refusal boundary, not source repair or
activation. A [source preparation wizard](legacy-preparation.md) accepts the two
already obtained exports, explicit member/reviewer mappings and historical photos.
Coherent source capture and controlled cutover remain separate requirements.
## Source boundaries

The reviewed legacy Assistant Store can contain either the schema-1 task ledger
directly or an envelope with `ledger`, `alarms`, `memories`,
`processed_home_updates`, and `sent_task_reminders`. The schema-1 Court Store is
separate. A Home Assistant Store file wrapper is not a domain payload: extraction
must validate its key/version and take its `data` explicitly, without guessing.

Task-ledger buckets are `tasks`, ordered `history`, `processed_commands` and
the next task/event sequences. Each task has `task_id`, `kind`, `state`, `title`,
`creator`, optional `assignee`/`reviewer`, `created_at`, `due_at`, report settings,
metadata and lifecycle timestamps. Shopping is a legacy task kind: quantity,
remaining quantity, unit and approval are in its metadata. Reminders are private
to their creator and must not become shared household tasks during conversion.

Alarm data has per-member `weekday`/`weekend` schedules and dated runs. Old runs
can contain plaintext challenge answers and Telegram-specific state. Preserve
them only in an owner-private historical archive; never reactivate a challenge,
output command, penalty or notification by importing a run. Active runs require
an explicit cutover decision. Imported schedules start disabled in shadow mode.

Court history contains events, member references, signed points, the source
week, cancellation details and transport metadata. Historical weeks are separate
from the currently open week. Reconcile current counters against uncancelled
current-week events; never sum all historical weeks into the current balance or
turn a cancelled penalty back into an active penalty.

## Required pipeline

1. Obtain a coherent, local source export and a verified rollback copy through
   the source application's supported API/backup procedure. A read-only scan of
   two independently changing files is not a coherent export.
2. Run bounded, non-mutating preflight. Report only fixed issue codes and counts:
   unsupported schema/status, broken references, ambiguous members/timestamps,
   invalid quantities, inconsistent balances and active alarm runs. Do not send
   source data to an LLM or print task titles, names, IDs or message bodies.
3. Review the explicit old-to-new member mapping. Never infer HA users, Telegram
   bindings, owner/admin roles or router credentials from a name or old log.
4. Build a deterministic conversion proposal with source fingerprint, mapping
   revision, counts, ID mappings, preserved private archive and all exceptions.
   No silent row dropping, invented dates, collapsed people or string truncation.
5. Apply once to an empty, owner-created shadow household through the integration
   runtime and Store API. Match the reviewed fingerprint and mapping under lock;
   write state plus receipt atomically. Never edit `.storage` directly. All
   transports, schedules, network writes and automatic consequences remain off.
6. Compare counts, quantities, statuses, balances, historical references and
   exact replay before/after restarting the isolated target. Test faults and
   rollback. Old transport delivery receipts must not become new command rights.
7. Only after acceptance: quiesce the legacy handler, take a final export,
   reconcile its delta, and explicitly switch one poller and the dashboards.
   Preserve the original source and rollback until the live acceptance is done.

The shared domain name means legacy and public `family_assistant` code cannot
be loaded side by side in one HA process. Shadow acceptance therefore runs in
an isolated HA instance, not by overwriting the working component directory.

## Implemented local review boundary

`migration.review.read_store_pair` accepts already obtained private bytes, not
paths, URLs or credentials. It requires the exact schema-1 Store keys
`family_assistant.tasks` and `family_court.ledger`; unsupported wrapper fields or
versions, duplicate JSON keys, invalid UTF-8, non-finite/unsafe numbers, excessive
depth and size fail with fixed codes. It never reads a live Store itself.

`source.review(mapping, members, mapping_revision=...)` requires a successful
preflight and an explicit old-to-existing-member mapping with current revisions.
Distinct old members cannot silently collapse into one target. An old history-only
system actor can be marked `archive_only: true`, but a task owner, recipient,
reviewer, court subject or alarm member cannot. Mapping never creates an HA user,
role, Telegram binding, command receipt or device permission.

The immutable review pins both raw exports, mapping and all current target-member
fields. `matches(...)` fails if any has changed, even a transport binding without
a revision bump. Its summary contains only counts, fingerprints and fixed status;
`repr` is content-free. Explicitly private payload methods return fresh copies for
the future local converter. These objects must not be sent to an LLM, diagnostic
export or ordinary family view. A matching fingerprint proves unchanged inputs,
not coherent capture: `coherence_verified` and `import_available` remain false.

## Disabled-alarm conversion proposal

`migration.alarm_plan.build_alarm_plan(review, timezone, members=current_members)`
converts the reviewed weekday/weekend schedules into modern save payloads. It
revalidates both frozen sources and every current member field, not just a member
ID. Missing targets, changed bindings, stale revisions, forged reviews and active
legacy wake-up runs fail closed. Source timezone is not guessed: it is an explicit
operator input, included in the immutable fingerprint.

All proposed schedules are **disabled, gentle, zero penalty**, regardless of the
old enabled state. Original enabled flags, finished runs, old challenge material,
delivery metadata and unknown fields remain only in the unchanged decoded alarm
archive accessible through the deliberately private payload method. They cannot
become live challenges, commands, receipts or notification rights. Raw Store-file
bytes remain in the source review. Public summaries contain only fixed status,
counts and fingerprints; returned dictionaries cannot mutate the frozen plan.

This helper has no HA, filesystem, transport or Engine side effects. Modern-domain
tests validate proposed payloads on a fictional state. A future complete converter
must apply a matched whole-source plan under lock to an empty shadow household and
persist its private archive atomically. This helper does not establish coherent
capture, import other task/shopping/court records, expose an import endpoint, or
permit partial household cutover. Private reminders and unknown shopping quantities
must not be silently converted into shared tasks or an invented quantity of one.

The alpha.8 candidate adds explicit `delivery_scope: personal` for convertible
no-report reminders: mapped creator and assignee must be identical, current identity
revision is retained, and the modern task engine permits only that person to view,
complete or archive. No parent review, reassignment, group incident or penalty is
introduced. The complete raw reminder and history remain in the private archive.
See [personal reminders](personal-reminders.md) for privacy and transport limits.
Reminders with unsupported notes/report state still block; later text-history
support below describes convertible ordinary report tasks. This is not a
partial-import permission or a coherence claim.

## Joined conversion review and private archive

`migration.conversion.build_conversion_review(review, timezone, members=...)`
collects alarm, task, shopping and current-score proposals in a single immutable
review. Its summary exposes fixed codes, counts and fingerprints only. Every
blocked row remains present in the owner-private source archive. Raw sources are
stored once, with the reviewed mapping, not as repeated overlapping copies.
The joined proposal itself grants no write authority or claim of coherent capture;
the separate owner-confirmed wizard performs read-only-copy staging/registration.

`migration.archive.encode_private_review` produces **private bytes containing the
entire source**, not a sanitized diagnostic export. Keep them only in owner-private
local storage or backup; never send them to an LLM, public issue, ordinary family
view or log. `decode_private_review` preserves the exact original Store-file bytes
and revalidates all current target identities before accepting a saved review.
Strict envelope/version/UTF-8/base64/size and JSON checks reject malformed input.
Fingerprints detect changed inputs; they are not an authorization token or a
signature against someone who can rewrite the archive. The codec does not itself
read or write files. The isolated HA test roundtrips it through the real Store API.

Shopping proposals preserve source creators, assigned buyers, partial quantities
and current approval state. Unknown quantities, precision finer than the modern
six-decimal model, unsupported states and names over 200 characters are explicit
blockers, not guesses or silent truncation. Cancellation never becomes approval
or a purchase. A cancelled pending proposal is non-active archived work; the
original approval and history remain private. Legacy transport/history events
are not fabricated as new authenticated shopping commands.

Court proposals seed only uncancelled events from the **source open week**, keeping
their original reasons and timestamps. Prior weeks and cancelled events remain
in the full private archive, without resurrecting their scores. The source's
current plus/minus counters must reconcile before review. A missing period or an
unrepresentable current reason is a blocker. Old Telegram parent identifiers are
not converted to a current authenticated actor; no role or approval is inferred.
This requires explicit historical attribution handling at the future apply step.

Task proposals currently cover ordinary no-report records with supported states,
preserved dates and zero reminder/penalty settings. When pre-overdue metadata lags
behind a later acceptance/start, a complete source history must reconcile the
current assignment, metadata and exact activity times before proposing its real
progress. Incomplete evidence or a source revision that actually rewound progress
still blocks; a timestamp alone is not proof. Convertible no-report personal reminders retain their self-only scope;
text-report tasks can now produce proposals from complete explicit event history.
Their reviewer and review actors must map to current owner/parent identities;
the proposal explicitly states the modern `household_parents` review policy.
The source history, submission timestamps, prior reports, feedback and separate
completion/cancellation/archive notes remain distinct. An old empty report is
preserved as empty, not fabricated or automatically completed. Unknown events,
inconsistent timestamps/notes and unverified assignment chains are explicit blockers.
Explicit reassignment archives the former assignee's report and review with
identity/submission/reassignment stamps. The new assignee receives no old report;
assigning back does not restore one. Old reports remain parent-only.
No-report tasks and personal reminders reconstruct separate terminal notes from
explicit history without inventing a submission, review authority or approval.
Nonparent designated reviewers require a separate authority review. The complete
old/new reviewer-set comparison still belongs to capture/cutover acceptance;
the proposal does not grant a role or constitute authorization to import.
A photo-required task with no historical submission can preserve its future
photo requirement and explicit lifecycle outcome without creating any attachment.
An old direct parent completion must have an explicit authorized source event;
it does not claim a photo exists. Any historical photo submission still requires
evidence resolution, even after rejection, reassignment or completion. A Telegram
photo reference is not a verified local attachment. All original notes and history
remain in the private archive.
`getFile` requires a file identifier; an old event/message reference alone is not
one. Telegram's pending update queue is not a history archive and retains updates
for at most 24 hours. Forwarding a message is a new external send, not read-only
retrieval, so it is not used as an automatic migration probe.
See [Telegram Bot API: updates](https://core.telegram.org/bots/api#getting-updates),
[files](https://core.telegram.org/bots/api#getfile) and
[forwarding](https://core.telegram.org/bots/api#forwardmessage).
**Zero reminder and penalty settings alone are not a shadow isolation mechanism:**
an open overdue task can still produce an incident when its module is activated.
The complete shadow runtime must keep all modules/transports/effects off, then
explicitly review activation. These planners must not be used for partial cutover.

## Explicit reviewer-set comparison

`migration.reviewer_policy.build_reviewer_policy_review` compares an explicitly
supplied **complete** old effective reviewer set for every report task with the
current target `household_parents` set. A designated reviewer alone may not be the
effective set: the legacy controller can also allow configured parents. The source
adapter must capture that policy; names and previous successful reviews do not prove it.

The schema-1 policy pins its revision and exact source/mapping review fingerprint.
Its per-task coverage must be exact, include each designated reviewer, exclude
duplicates and resolve every old actor through the explicit immutable mapping.
No identities are inferred or promoted. Private output lists mapped old, current,
added and removed reviewers per task. Public summaries contain fixed status, counts
and fingerprints only. Member, binding, source or policy changes invalidate replay.

`build_conversion_review(..., reviewer_policy=...)` includes this comparison in the
joined fingerprint/private payload. Omission is explicit `not_supplied`, never
implicit acceptance. Added/removed reviewers require a separate decision; historical
nonparent authority is not converted into a current role. Even equivalent sets do
not prove the supplied policy is truthful or coherently captured: `source_policy_verified`,
`coherence_verified` and `import_available` remain false. This is one acceptance gate,
not an import endpoint, source exporter, role grant or partial-cutover mechanism.

The next engineering stage can construct an entire isolated read-only copy from
fully convertible records. It still grants no activation or live import authority.
See [persistent shadow isolation and its remaining gates](legacy-shadow.md).
## Русский

Статус: предварительная проверка только для чтения (preflight), неизменяемый аудит источников и участников, кодек приватного архива и объединённые предложения конвертации; не является полным импортом или живым переключением. Старые приватные интеграции продолжают работать до отдельного подтверждённого переключения. В этом репозитории используются только синтетические примеры.

Текущий [мастер проверочной копии](legacy-copy-wizard.md#русский) объединяет описанные здесь внутренние этапы. [Сверка согласованности журналов и детерминированная сборка пакета](legacy-source-links.md#русский) задают границу отказа, а не восстановление источника или активацию. [Мастер подготовки источника](legacy-preparation.md#русский) принимает два уже полученных экспорта, явные сопоставления участников/проверяющих и исторические фотографии. Согласованный захват источника и контролируемое переключение остаются отдельными требованиями.

### Границы источника

Проверенное старое хранилище Assistant может содержать либо журнал задач схемы 1 напрямую, либо обёртку с `ledger`, `alarms`, `memories`, `processed_home_updates` и `sent_task_reminders`. Хранилище Court схемы 1 хранится отдельно. Файловая обёртка Home Assistant Store не является доменной полезной нагрузкой: извлечение обязано валидировать ключ и версию и брать `data` строго явно, без предположений.

Разделы журнала задач: `tasks`, упорядоченная `history`, `processed_commands` и следующие последовательности задач/событий. Каждая задача содержит `task_id`, `kind`, `state`, `title`, `creator`, опциональные `assignee`/`reviewer`, `created_at`, `due_at`, настройки отчётов, метаданные и временные метки жизненного цикла. Покупки — это старый тип задачи (`kind: shopping`): количество, остаток, единица измерения и подтверждение находятся в её метаданных. Напоминания приватны для создателя и не должны превращаться в общие семейные задачи при конвертации.

Данные будильников содержат расписания `weekday`/`weekend` для каждого участника и датированные запуски. Старые запуски могут содержать открытые ответы на математические задания и состояние Telegram. Они сохраняются только в приватном историческом архиве владельца; импорт запуска никогда не активирует задание, команду, штраф или уведомление повторно. Активные запуски требуют явного решения о переключении. Импортированные расписания создаются отключёнными в режиме shadow.

История суда содержит события, ссылки на участников, баллы со знаком, неделю источника, детали отмены и метаданные доставки. Исторические недели отделены от текущей открытой недели. Текущие счётчики согласуются только по неотменённым событиям текущей недели; исторические недели никогда не суммируются в текущий баланс, а отменённый штраф не восстанавливается.

### Требуемый конвейер

1. Получить согласованный локальный экспорт источника и проверенную точку возврата через штатную процедуру резервного копирования/API старого приложения. Чтение двух независимо меняющихся файлов не является согласованным экспортом.
2. Запустить ограниченную неизменяющую предварительную проверку (preflight). Сообщать только фиксированные коды проблем и количества: неподдерживаемая схема/статус, битые ссылки, неоднозначные участники/метки времени, невалидные количества, расхождения баланса и активные запуски будильников. Данные источника не передаются в LLM; заголовки задач, имена, ID и тексты сообщений не выводятся.
3. Проверить явное сопоставление старых участников с новыми. Пользователи HA, привязки Telegram, роли владельца/администратора или пароли роутера никогда не угадываются по именам или старым журналам.
4. Построить детерминированное предложение конвертации с отпечатком источника, ревизией сопоставления, количествами, таблицей ID, сохранённым приватным архивом и всеми исключениями. Никаких скрытых пропусков строк, выдуманных дат, объединения людей или усечения строк.
5. Применить один раз к пустому созданному владельцем теневому пространству (shadow) через runtime интеграции и Store API. Сверить проверенный отпечаток и сопоставление под блокировкой; атомарно записать состояние и квитанцию. Файлы `.storage` напрямую не редактируются. Все транспорты, расписания, запись в сеть и автоматические последствия остаются выключенными.
6. Сверить количества, статусы, балансы, исторические ссылки и точный повтор команд до и после перезапуска изолированного экземпляра. Проверить сбои и откат. Старые квитанции доставки сообщений не превращаются в новые права на команды.
7. Только после приёмки: перевести старый обработчик в режим покоя (quiesce), снять финальный экспорт, согласовать дельту и явно переключить один опросчик и дашборды. Сохранять исходные файлы и откат до завершения живой приёмки.

Общий домен интеграции означает, что старый и публичный код `family_assistant` не могут работать одновременно в одном процессе HA. Поэтому приёмочные теневые испытания проводятся в изолированном экземпляре Home Assistant.

### Реализованная граница локального аудита

`migration.review.read_store_pair` принимает уже полученные приватные байты, а не пути, URL или пароли. Требуются точные ключи хранилищ схемы 1 `family_assistant.tasks` и `family_court.ledger`; неподдерживаемые поля обёртки или версии, дубликаты JSON-ключей, невалидный UTF-8, нечисловые/небезопасные значения, избыточная глубина и размер отклоняются с фиксированными кодами. Функция никогда сама не читает рабочее хранилище.

`source.review(mapping, members, mapping_revision=...)` требует успешного preflight и явного сопоставления старых участников с существующими с актуальными ревизиями. Разные старые участники не могут неявно объединиться в одного. Исторический системный субъект может быть помечен как `archive_only: true`, но владелец задачи, получатель, проверяющий, субъект суда или участник будильника — нет. Сопоставление никогда не создаёт пользователя HA, роль, привязку Telegram, квитанцию команды или разрешение устройства.

Неизменяемый аудит связывает оба необработанных экспорта, сопоставление и все текущие поля участников-получателей. `matches(...)` возвращает отказ при любом изменении, даже при изменении привязки транспорта без изменения ревизии. Сводка содержит только количества, отпечатки и фиксированный статус; строковое представление не содержит персональных данных. Приватные методы возвращают свежие копии для локального конвертера. Эти объекты нельзя передавать в LLM, диагностический экспорт или обычный семейный интерфейс. Совпадение отпечатка доказывает неизменность входных данных, а не согласованность захвата: `coherence_verified` и `import_available` остаются `false`.

### Предложение конвертации отключённых будильников

`migration.alarm_plan.build_alarm_plan(review, timezone, members=current_members)` конвертирует проверенные расписания будней/выходных в современные полезные нагрузки сохранения. Повторно проверяются оба замороженных источника и каждое поле текущих участников. Отсутствие получателей, изменённые привязки, устаревшие ревизии, поддельные аудиты и активные старые запуски приводят к безопасному отказу. Часовой пояс источника не угадывается: это явный ввод оператора, включённый в неизменяемый отпечаток.

Все предлагаемые расписания создаются в состоянии **отключено, мягкий профиль, нулевой штраф**, независимо от старого состояния включения. Исходные флаги включения, завершённые запуски, старые материалы заданий, метаданные доставки и неизвестные поля остаются только в неизменённом декодированном архиве будильников через приватный метод. Они не могут стать активными заданиями, командами, квитанциями или правами на уведомления. Публичные сводки содержат только фиксированный статус, количества и отпечатки; возвращаемые словари не могут изменить замороженный план.

### Объединённый аудит конвертации и приватный архив

`migration.conversion.build_conversion_review(review, timezone, members=...)` объединяет предложения по будильникам, задачам, покупкам и текущим баллам в единый неизменяемый аудит. Его сводка раскрывает только фиксированные коды, количества и отпечатки. Каждая заблокированная строка остаётся в приватном архиве источника владельца. Исходные данные сохраняются один раз с проверенным сопоставлением. Само объединённое предложение не даёт прав на запись; отдельный подтверждённый владельцем мастер выполняет подготовку и регистрацию копии только для чтения.

`migration.archive.encode_private_review` создаёт **приватные байты со всем исходным содержимым**, а не очищенный диагностический экспорт. Храните их только в приватном локальном хранилище или резервной копии владельца; никогда не передавайте их в LLM, публичный issue, общий семейный вид или журнал. `decode_private_review` сохраняет точные байты исходных файлов и повторно валидирует всех участников. Строгие проверки конверта, версии, UTF-8, base64, размера и JSON отвергают некорректные данные. Отпечатки выявляют изменения входа; они не являются Capability-токеном или подписью против того, кто может перезаписать архив. Изолированный тест HA проверяет сквозную запись и чтение через штатный Store API.

Предложения по покупкам сохраняют создателей источника, назначенных покупателей, дробные количества и статус согласования. Неизвестные количества, точность выше шести десятичных знаков, неподдерживаемые статусы и названия длиннее 200 символов являются явными блокерами. Отмена никогда не становится согласованием или покупкой. Старые события транспорта/истории не фабрикуются как новые команды.

Предложения по суду переносят только неотменённые события из **открытой недели источника**, сохраняя их причины и метки времени. Предыдущие недели и отменённые события остаются в полном приватном архиве без воскрешения баллов. Текущие плюсы и минусы источника должны согласовываться до аудита. Старые идентификаторы родителей в Telegram не конвертируются в текущего аутентифицированного субъекта; роли и согласования не выводятся автоматически.

Предложения по задачам охватывают обычные записи без отчётов с поддерживаемыми статусами, сохранёнными датами и нулевыми штрафами/напоминаниями. Задачи с текстовыми отчётами создают предложения на основе полной истории событий. Проверяющий и субъект проверки должны сопоставляться с текущими родителями/владельцем. Исходная история, метки времени сдачи, предыдущие отчёты, отзывы и заметки завершения/отмены/архивации остаются разделены. Неизвестные события, противоречивые метки времени и неподтверждённые цепочки переназначений являются блокерами. Задача с требованием фото без исторических сдач сохраняет требование фото без создания вложений. Любая историческая сдача фото требует разрешения свидетельств через сопоставление файлов. Нулевые штрафы и напоминания сами по себе не являются механизмом изоляции: открытая просроченная задача может вызвать инцидент при активации модуля. Поэтому в режиме shadow все модули, транспорты и эффекты полностью отключены.

### Явное сопоставление состава проверяющих

`migration.reviewer_policy.build_reviewer_policy_review` сравнивает явно предоставленный **полный** старый состав проверяющих для каждой задачи с отчётом с текущим составом родителей `household_parents`. Назначенный проверяющий может не быть единственным: старый контроллер мог разрешать проверку всем настроенным родителям. Адаптер источника обязан зафиксировать эту политику; имена и прошлые проверки этого не доказывают.

Политика схемы 1 фиксирует ревизию и точный отпечаток аудита источника/сопоставления. Охват задач должен быть точным, включать назначенного проверяющего, исключать дубликаты и разрешать каждого участника через неизменяемое сопоставление. Приватный вывод содержит списки старых, текущих, добавленных и удалённых проверяющих по задачам. Любые изменения участников, привязок или политики делают повтор недействительным. Добавленные или удалённые проверяющие требуют отдельного решения; исторические полномочия не родителей не превращаются в современные роли.

## Українська

Статус: попередня перевірка лише для читання (preflight), незмінний аудит джерел та учасників, кодек приватного архіву й об'єднані пропозиції конвертації; не є повним імпортом або живим перемиканням. Старі приватні інтеграції продовжують працювати до окремого підтвердженого перемикання. У цьому репозиторії містяться виключно синтетичні приклади.

Поточний [майстер перевірочної копії](legacy-copy-wizard.md#українська) поєднує описані тут внутрішні етапи. [Звірка узгодженості журналів і детерміноване пакування](legacy-source-links.md#українська) задають межу відмови, а не відновлення джерела чи активацію. [Майстер підготовки джерела](legacy-preparation.md#українська) приймає два вже отримані експорти, явні зіставлення учасників/перевіряльників та історичні фотографії. Узгоджене отримання джерела та контрольоване перемикання залишаються окремими вимогами.

### Межі джерела

Перевірене старе сховище Assistant може містити або журнал завдань схеми 1 безпосередньо, або обгортку з `ledger`, `alarms`, `memories`, `processed_home_updates` та `sent_task_reminders`. Сховище Court схеми 1 зберігається окремо. Файлова обгортка Home Assistant Store не є корисною навантагою домену: вилучення зобов'язане перевіряти ключ та версію і явно брати `data`, без припущень.

Розділи журналу завдань: `tasks`, упорядкована `history`, `processed_commands` та наступні послідовності завдань/подій. Кожне завдання містить `task_id`, `kind`, `state`, `title`, `creator`, необов'язкові `assignee`/`reviewer`, `created_at`, `due_at`, налаштування звітів, метадані та часові позначки життєвого циклу. Покупки — це старий різновид завдання (`kind: shopping`): кількість, залишок, одиниця вимірювання та погодження містяться в її метаданих. Нагадування приватні для творця і не повинні ставати спільними сімейними завданнями під час конвертації.

Дані будильників містять розклади `weekday`/`weekend` для кожного учасника та датовані запуски. Старі запуски можуть містити відкриті відповіді на математичні завдання та стан Telegram. Вони зберігаються лише у приватному історичному архіві власника; імпорт запуску ніколи не активує завдання, команду, штраф чи сповіщення повторно. Активні запуски потребують явного рішення щодо перемикання. Імпортовані розклади створюються вимкненими в режимі shadow.

Історія суду містить події, посилання на учасників, бали зі знаком, тиждень джерела, деталі скасування та метадані доставки. Історичні тижні відокремлені від поточного відкритого тижня. Поточні лічильники узгоджуються лише за нескасованими подіями поточного тижня; історичні тижні ніколи не додаються до поточного балансу, а скасований штраф не відновлюється.

### Необхідний конвеєр

1. Отримати узгоджений локальний експорт джерела та перевірену точку повернення через штатну процедуру резервного копіювання/API старої програми. Читання двох незалежно змінюваних файлів не є узгодженим експортом.
2. Запустити обмежену незмінну попередню перевірку (preflight). Повідомляти лише фіксовані коди проблем та кількості: непідтримувана схема/статус, пошкоджені посилання, неоднозначні учасники/часові позначки, недійсні кількості, розбіжності балансу та активні запуски будильників. Дані джерела не передаються в LLM; заголовки завдань, імена, ID та тексти повідомлень не виводяться.
3. Перевірити явне зіставлення старих учасників із новими. Користувачі HA, прив'язки Telegram, ролі власника/адміністратора чи паролі роутера ніколи не вгадуються за іменами чи старими журналами.
4. Побудувати детерміновану пропозицію конвертації з відбитком джерела, ревізією зіставлення, кількостями, таблицею ID, збереженим приватним архівом та всіма винятками. Жодних прихованих пропусків рядків, вигаданих дат, об'єднання людей чи обрізання рядків.
5. Застосувати один раз до порожнього створеного власником тіньового простору (shadow) через runtime інтеграції та Store API. Звірити перевірений відбиток і зіставлення під блокуванням; атомарно записати стан і квитанцію. Файли `.storage` безпосередньо не редагуються. Усі транспорти, розклади, запис у мережу та автоматичні наслідки залишаються вимкненими.
6. Звірити кількості, статуси, баланси, історичні посилання та точний повтор команд до й після перезапуску ізольованого екземпляра. Перевірити збої та відкат. Старі квитанції доставки повідомлень не перетворюються на нові права на команди.
7. Лише після прийомки: перевести старий обробник у стан спокою (quiesce), зняти фінальний експорт, узгодити дельту та явно перемкнути один опитувач і дашборди. Зберігати початкові файли та точку повернення до завершення живої прийомки.

Спільний домен інтеграції означає, що старий і публічний код `family_assistant` не можуть працювати одночасно в одному процесі HA. Тому прийомочні тіньові випробування проводяться в ізольованому екземплярі Home Assistant.

### Реалізована межа локального аудиту

`migration.review.read_store_pair` приймає вже отримані приватні байти, а не шляхи, URL чи паролі. Вимагаються точні ключі сховищ схеми 1 `family_assistant.tasks` та `family_court.ledger`; непідтримувані поля обгортки чи версії, дублікати JSON-ключів, недійсний UTF-8, нечислові/небезпечні значення, надмірна глибина та розмір відхиляються з фіксованими кодами. Функція ніколи сама не читає робоче сховище.

`source.review(mapping, members, mapping_revision=...)` вимагає успішного preflight та явного зіставлення старих учасників із наявними з актуальними ревізіями. Різні старі учасники не можуть неявно об'єднатися в одного. Історичний системний суб'єкт може бути позначений як `archive_only: true`, але власник завдання, одержувач, перевіряльник, суб'єкт суду чи учасник будильника — ні. Зіставлення ніколи не створює користувача HA, роль, прив'язку Telegram, квитанцію команди чи дозвіл пристрою.

Незмінний аудит пов'язує обидва необроблені експорти, зіставлення та всі поточні поля учасників-одержувачів. `matches(...)` повертає відмову за будь-якої зміни, навіть за зміни прив'язки транспорту без зміни ревізії. Зведення містить лише кількості, відбитки та фіксований статус; рядкове представлення не містить персональних даних. Приватні методи повертають свіжі копії для локального конвертера. Ці об'єкти не можна передавати в LLM, діагностичний експорт або звичайний сімейний інтерфейс. Збіг відбитка доводить незмінність вхідних даних, а не узгодженість отримання: `coherence_verified` та `import_available` залишаються `false`.

### Пропозиція конвертації вимкнених будильників

`migration.alarm_plan.build_alarm_plan(review, timezone, members=current_members)` конвертує перевірені розклади буднів/вихідних у сучасні корисні навантаги збереження. Повторно перевіряються обидва заморожені джерела та кожне поле поточних учасників. Відсутність одержувачів, змінені прив'язки, застарілі ревізії, підроблені аудити та активні старі запуски призводять до безпечної відмови. Часовий пояс джерела не вгадується: це явне введення оператора, включене до незмінного відбитка.

Усі запропоновані розклади створюються у стані **вимкнено, м'який профіль, нульовий штраф**, незалежно від старого стану ввімкнення. Початкові прапорці ввімкнення, завершені запуски, старі матеріали завдань, метадані доставки та невідомі поля залишаються лише в незміненому декодованому архіві будильників через приватний метод. Вони не можуть стати активними завданнями, командами, квитанціями чи правами на сповіщення. Публічні зведення містять лише фіксований статус, кількості та відбитки; повернені словники не можуть змінити заморожений план.

### Об'єднаний аудит конвертації та приватний архів

`migration.conversion.build_conversion_review(review, timezone, members=...)` об'єднує пропозиції щодо будильників, завдань, покупок і поточних балів у єдиний незмінний аудит. Його зведення розкриває лише фіксовані коди, кількості та відбитки. Кожен заблокований рядок залишається у приватному архіві джерела власника. Початкові дані зберігаються один раз із перевіреним зіставленням. Сама об'єднана пропозиція не надає прав на запис; окремий підтверджений власником майстер виконує підготовку та реєстрацію копії лише для читання.

`migration.archive.encode_private_review` створює **приватні байти з усім початковим вмістом**, а не очищений діагностичний експорт. Зберігайте їх лише у приватному локальному сховищі або резервній копії власника; ніколи не передавайте їх у LLM, публічний issue, загальний сімейний перегляд чи журнал. `decode_private_review` зберігає точні байти початкових файлів і повторно валідує всіх учасників. Суворі перевірки конверта, версії, UTF-8, base64, розміру та JSON відхиляють некоректні дані. Відбитки виявляють зміни входу; вони не є Capability-токеном чи підписом проти того, хто може перезаписати архів. Ізольований тест HA перевіряє наскрізний запис і читання через штатний Store API.

Пропозиції щодо покупок зберігають творців джерела, призначених покупців, дробові кількості та статус погодження. Невідомі кількості, точність вище шести десяткових знаків, непідтримувані статуси та назви довші за 200 символів є явними блокерами. Скасування ніколи не стає погодженням чи покупкою. Старі події транспорту/історії не фабрикуються як нові команди.

Пропозиції щодо суду переносять лише нескасовані події з **відкритого тижня джерела**, зберігаючи їхні причини та часові позначки. Попередні тижні та скасовані події залишаються в повному приватному архіві без відновлення балів. Поточні плюси та мінуси джерела мають узгоджуватися до аудиту. Старі ідентифікатори батьків у Telegram не конвертуються в поточного автентифікованого суб'єкта; ролі та погодження не виводяться автоматично.

Пропозиції щодо завдань охоплюють звичайні записи без звітів із підтримуваними статусами, збереженими датами та нульовими штрафами/нагадуваннями. Завдання з текстовими звітами створюють пропозиції на основі повної історії подій. Перевіряльник та суб'єкт перевірки мають зіставлятися з поточними батьками/власником. Початкова історія, часові позначки здачі, попередні звіти, відгуки та нотатки завершення/скасування/архівування залишаються розділеними. Невідомі події, суперечливі часові позначки та непідтверджені ланцюжки перепризначень є блокерами. Завдання з вимогою фото без історичних здач зберігає вимогу фото без створення вкладень. Будь-яка історична здача фото вимагає вирішення свідчень через зіставлення файлів. Нульові штрафи та нагадування самі по собі не є механізмом ізоляції: відкрите прострочене завдання може спричинити інцидент під час активації модуля. Тому в режимі shadow усі модулі, транспорти та ефекти повністю вимкнені.

### Явне зіставлення складу перевіряльників

`migration.reviewer_policy.build_reviewer_policy_review` порівнює явно наданий **повний** старий склад перевіряльників для кожного завдання зі звітом із поточним складом батьків `household_parents`. Призначений перевіряльник може не бути єдиним: старий контролер міг дозволяти перевірку всім налаштованим батькам. Адаптер джерела зобов'язаний зафіксувати цю політику; імена та минулі перевірки цього не доводять.

Політика схеми 1 фіксує ревізію і точний відбиток аудиту джерела/зіставлення. Охоплення завдань має бути точним, включати призначеного перевіряльника, виключати дублікати та дозволяти кожного учасника через незмінне зіставлення. Приватне виведення містить списки старих, поточних, доданих і вилучених перевіряльників за завданнями. Будь-які зміни учасників, прив'язок чи політики роблять повтор недійсним. Додані або вилучені перевіряльники вимагають окремого рішення; історичні повноваження не батьків не перетворюються на сучасні ролі.
