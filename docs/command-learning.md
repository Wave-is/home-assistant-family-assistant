# Command understanding and local learning — early version

## Implemented path

The strict router runs first. An unrecognized participant now reaches the model
instead of stopping with `unknown_member`. The model returns a typed action,
read, clarification or conversational answer, not a shell command.

An explicit parent/owner task assignment can execute after a narrowly proven
name repair: exactly one active configured name/alias differs by one insertion,
deletion, substitution or adjacent transposition; replacing only the recipient
slot and strictly parsing it reproduces the whole typed action. Bounded Cyrillic
case endings and ё/е are considered. Short, multiword, mixed-script or ambiguous
spellings, changed titles/deadlines, extra fields and non-task operations keep
the ordinary expiring review. Model confidence alone is not proof.

Synthetic example: `assign task Alxe - Buy bread`, with only Alex matching,
creates the task and explains the correction. Later `Alxe task Wash dishes` uses
the saved rule without inference, including after restart. Text inside the title
is not rewritten; relative deadlines are calculated anew for each request.

Task, private spelling rule and receipt commit atomically. A failed write teaches
nothing. Future rule use checks current permissions, rule validity and actor and
recipient revisions inside that same transaction. Duplicate delivery does not
create another task. A revoked rule is not automatically resurrected.

The rule belongs to the requesting account and household. It is not a login,
Telegram identity, permission, renamed member or shared model training. Configured
names win; a newly ambiguous match or changed identity stops use of an old rule.
`/forgetphrase L000001` or **Disable phrase** in the conversation card disables it
without deleting history. The existing 200-record private dictionary limit applies.
Already created tasks need separate correction/cancellation; disabling a spelling
rule is not a task rollback.

Ordinary discussion stays an answer. Questions about family records use the
authorized read path. Quotes, images and search results cannot authorize an action
absent from the current request. Real execution/storage failures do not become
new LLM commands. Bad JSON/timeouts use bounded fallback; revoked access is terminal.

## Provider order and AGY limitation

When configured: **AGY-compatible HTTP slot → reviewed HA agent → direct primary
Ollama → enabled fallback**. A valid result stops the chain. The historical `agy`
option currently requires an Ollama-compatible HTTP service using `/api/tags` and
`/api/chat`. It is not a native AGY CLI adapter. Installing AGY on a developer PC
does not connect it to Home Assistant, and native Options do not provision an AGY
server. Ordinary Ollama and the reviewed HA agent need no developer PC.

A proper optional AGY bridge remains a separate acceptance item: explicit setup,
authentication, minimal message context, bounded structured responses, no file or
household credential access, no arbitrary command execution, health/fallback
tests and uninstall/restart behavior. Using AGY for development is not runtime
acceptance of such a bridge.

## Следующие улучшения / Next priorities

1. **Уточнение одним нажатием:** an expiring actor-bound draft with actual candidate
   names; choosing one resumes the same operation instead of re-inferring a duplicate.
2. **История решения:** parser/model/rule provenance, interpreted target, committed
   result and notification state together; correction tied to the exact original task.
3. **Обучение формулировкам:** reviewed reusable slot templates beyond task names,
   without binding variable commands to old task IDs or dates.
4. **Тесты из ошибок:** explicitly approved, deidentified interpretation failures
   become synthetic regression cases for each provider/release. Private feedback
   notes are not yet anonymized tests or automatically applied patches.
5. **Настройки обучения:** per-account controls, no-effect explanation/test mode,
   real provider-protocol verification. Rule-level disable already works.
6. **Сначала надёжность:** finish the [legacy workflow gaps](legacy-parity-audit.md),
   especially report phrases, task correction, reviewer reminders and shopping quantities.

## Кратко по-русски

Однозначную опечатку в имени адресата обычной задачи сначала разбирает LLM.
Независимая проверка должна доказать, что исправлено только имя. Задача и правило
сохраняются вместе; следующие обращения работают локально. При неоднозначности
или других изменениях требуется подтверждение плана. Правило можно отключить в
карточке разговора или через `/forgetphrase ID`. Это обучение распознаванию, не
автоматическое переписывание кода. Консольный AGY ещё не является готовым runtime
провайдером; одноимённый слот пока требует HTTP-совместимого сервиса.

## Коротко українською

Однозначну помилку в імені адресата звичайного завдання спочатку розбирає LLM.
Незалежна перевірка має довести, що виправлено лише ім'я. Завдання й правило
зберігаються разом; наступні звернення працюють локально. За неоднозначності чи
інших змін потрібне підтвердження плану. Правило можна вимкнути в картці розмови
або через `/forgetphrase ID`. Це навчання розпізнаванню, а не переписування коду.
Консольний AGY ще не є готовим runtime-провайдером; однойменний слот наразі
потребує HTTP-сумісного сервісу.
