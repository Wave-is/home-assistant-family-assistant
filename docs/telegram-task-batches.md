# Numbered Telegram tasks

The deterministic Telegram route can create **2–5 independent tasks in one
transaction**. This is a bounded numbered grammar, available without a language
model. It uses configured member names/aliases and the current sender's rights.

## Examples

Russian, with a shared recipient and deadline/report defaults:

```text
создай 2 задачи для Ребёнок 1 на завтра с фотоотчетом:
1. Убрать стол
2. Собрать рюкзак без отчета
```

Ukrainian, with an explicit second recipient and deadline:

```text
створи 2 завдання для Дитина 1 на завтра з фотозвітом:
1. Прибрати стіл
2. для Дитина 2: Зібрати рюкзак через тиждень без звіту
```

English, with explicit recipients on every item:

```text
create 2 tasks tomorrow with a text report:
1. for Child One: Clear the desk
2. task Child Two Pack the bag tomorrow at 18:00 with a photo report
```

The example names are placeholders: use the exact name or an explicit alias of
a configured active family member. Roles or kinship words do not identify people.

## Rules

- The header declares a digit from `2` through `5`, uses `tasks`, `задачи`/`задач`
  or `завдання`/`завдань`, and ends with a colon. `create`, `создай`, `створи` and
  their bounded assignment/add verbs are optional.
- Put one task on each numbered line, numbered exactly `1…N`. Use `1.` or `1)`
  consistently throughout one message. Blank separator lines are allowed.
- A header recipient is the default for plain titles. For an explicit item
  recipient, use `for MEMBER: TITLE`, `для MEMBER: TITLE`, or an existing complete
  single-task assignment such as `task MEMBER TITLE`.
- Header report/deadline values are defaults. An explicit item report or deadline
  replaces only that default for that item. Conflicting qualifiers within the
  header or one item reject. Photo/text/no-report and deadline grammar retain the
  [single-task limits](telegram-command-parity.md).
- A parent/owner may assign configured members. A child or adult may create only
  tasks assigned to self. Guests cannot create tasks or receive assignments.
- Recipient revisions and resolved calendar timestamps are frozen in the plan.
  A changed recipient before execution rejects the whole batch. Successful retry
  returns the original result without recalculating dates or duplicating tasks.
- The result lists each task ID. Replying only `done` to a multi-task receipt does
  not choose a task; use its explicit ID.

The exact remaining title spelling, punctuation and case are retained. Commas,
semicolons, clocks, decimal points and title numbers are not list separators.
Explicitly repeated numbered items remain distinct tasks; there is no inferred
deduplication. `/task MEMBER | TITLE` keeps its literal-title behavior, including
multiline titles; it is not this numbered grammar.

## Failure and limits

A wrong count, missing/duplicate/out-of-order number, mixed numbering punctuation,
empty item, unnumbered continuation, unknown or ambiguous recipient, conflicting
report policy or invalid deadline rejects the entire message. Once recognized as
a numbered task request, these errors do not reach Court, network, single-task,
learned-phrase or model repair routes. No valid prefix of the list is executed.

Every item must describe a task. Nested batch declarations and slash commands
inside the list reject. Number-word counts, inline comma/semicolon lists,
multiline task titles, universal `all` modifiers and unrestricted prose are not
supported by this route. The header's shared member slot is parsed alongside its
qualifiers; a name that itself looks like a deadline should be provided through
an explicit per-item assignment. A later manually changed message is a new
request, not an implicit continuation of a rejected list.

Task titles are limited to 500 characters; the full message to Telegram's 4096
characters. Assigned-shopping semantics, personal reminders and automatic penalty
policy are not added by this grammar. Task report/review and configured reminder
policies continue through the ordinary task domain.

The Engine commits the list's tasks, IDs, notifications and audit/processed receipt
together. A separate interpretation checkpoint may survive a storage failure;
that checkpoint is a pending frozen plan, not a successful creation. Retry with
the same operation ID after recovery. Recipient/actor/module checks still apply.

## Verification scope

`tests/test_telegram_task_batches.py` exercises the actual parser, router, Engine,
storage callback and Telegram manager using fictional family data. It covers
counts 2–5, localized examples, shared/item overrides, exact titles, ambiguity,
role denial, recipient revision races, first/second checkpoint failure, restart
and date-stable replay, duplicate delivery, addressing, localized failures and
multi-ID reply context. The existing `tests/test_task_multi_create.py` verifies
the underlying domain batch transaction independently.

`tests/ha_command_completion_smoke.py` additionally prepares native isolated-HA
acceptance through the existing `command-completion` case: numbered two-task
creation, shared/item settings, persisted task-ID references, authenticated child
denial, unknown/nested-list rejection, actual batch rollback on a stale recipient,
and date-stable replay after ConfigEntry/Store reload. This exercises route results
and command receipts; it does not send a message to a real Telegram bot. Adding
the test is not evidence that its native run passed.

The development checkpoint records exact executed test totals in
[implementation status](implementation-status.md). Unit/adapter tests do not
establish actual Telegram delivery, household deployment or native HA acceptance
for this new grammar; those remain release gates.

Focused validation command:

```text
python -m pytest -q tests/test_telegram_task_batches.py tests/test_telegram_creation_grammar.py tests/test_telegram.py tests/test_telegram_legacy_parity.py tests/test_telegram_language_audit.py tests/test_telegram_command_scope.py tests/test_telegram_photo_reports.py tests/test_telegram_media_jobs.py tests/test_legacy_relative_deadlines.py tests/test_language_context.py tests/test_intent_typo_robustness.py tests/test_learning.py tests/test_assistant.py tests/test_task_multi_create.py
```
