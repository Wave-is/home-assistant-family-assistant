# Opt-in daily task settlement and exact completion correction

This is a bounded extension for ordinary **one-off tasks assigned to a current
child member**. It is not a general penalty engine or a complete port of every
legacy task rule. Existing and newly created tasks remain unchanged when the
optional policy is absent. No household policy is enabled by installation.

## Parent controls

Open Tasks → Add / Edit task → deadline options. Select a child and a deadline.
The EN/RU/UK form offers three separate choices:

- Move an unfinished task forward daily.
- Allow its configured penalty on later missed days. This remains subject to
  the existing global automatic-penalties switch, Court module and daily cap.
- Reverse only this task's exact penalty when a parent confirms completion on
  the settlement day. An independent appeal review may still be required.

All three choices start off. The local cutoff defaults to `20:00`; `00:00` through
`23:59` are accepted. A rollover alone is not consent to repeat penalties.
Penalty amount remains the ordinary task setting (`0` means no penalty).
Turning rollover off clears the two dependent choices. Omitting the policy
when saving an older task does not introduce it. Failed saves retry the same
frozen payload and operation ID.

RU: «Задачи» → добавить / редактировать → политика срока. Ежедневный перенос,
повторный штраф и точная отмена штрафа включаются отдельно родителем. По
умолчанию всё выключено. Сданная на проверку работа не штрафуется и не
переносится. После долгого простоя старые дни пропускаются без начислений.

UK: «Завдання» → додати / редагувати → політика терміну. Щоденне перенесення,
повторний штраф і точне скасування штрафу вмикаються окремо батьками. Типово
все вимкнено. Робота на перевірці не штрафується й не переноситься. Після
тривалого простою старі дні пропускаються без нарахувань.

Personal/private tasks, recurring-series occurrences, school homework and
maintenance work reject this policy in the domain. Children, adults and guests
cannot configure it, including an explicit off policy. The first form supports
single-person creation; its multi-person preview disables these new controls
and does not silently apply a shared rollover policy. Each resulting ordinary
task can later be reviewed individually by a parent.

## Calendar and outage semantics

The household timezone is stamped when the parent authorizes the policy. For
an open task, settlement occurs no earlier than both its due time plus grace
and the configured cutoff on the **original due local date**. The task keeps
its lifecycle status, report and checklist. `missed_original_due_at` preserves
its first opted-in deadline; each receipt preserves its own exact prior due
time. Only `due_at` advances, retaining the local clock time.

Submitted, completed, cancelled and archived tasks are never settled. Submitted
work can have its separate reviewer reminder; this feature does not penalize
the child for parent review delay. After request-changes, an old day is skipped
rather than charged retroactively.

One tick performs at most one settlement per task. If the scheduled settlement
belongs to an older local day, a single `skipped_outage` receipt advances directly
to a future settlement opportunity. It does not loop through missed dates or
issue scores for a backlog. A deadline already reached when the policy was
authorized is `skipped_retroactive`. A nonexistent spring-clock cutoff is skipped
without a score, but never before a later explicit deadline plus grace. Local
clock gaps in future due times are skipped; an autumn repeated clock uses its
first occurrence once.

The ordinary grace period can cross midnight. In that case the receipt keeps
both `due_local_date` and `settled_local_date`: the ledger identity uses the
former; same-day parent completion is compared with the latter. The rolled
deadline is never used to identify the score being corrected.

## Scores, receipts and corrections

With repeat penalties off, there can be only the ordinary `task:T000001` score
for that task. With explicit repeat consent, the durable source is
`task:T000001:missed:YYYY-MM-DD`. A policy generation change does not change the
ledger deduplication key. Previous task scores, including reversed ones, prevent
another assessment of that task on the same local settlement day. Returning to
ordinary one-off behavior cannot charge a task already assessed by settlement.

Each immutable receipt has a task / policy-generation / original-date identity
and stamps the authorizing parent epoch, child epoch, policy, timezone, exact
prior/new deadlines, actual settlement date, outcome and exact ledger ID when
one exists. A score suppressed by disabled configuration, zero points, the daily
cap or deduplication has an explicit terminal skip outcome. It is not retried
later when the cap or switches change.

History is append-only and limited to 366 receipts per task. At capacity only
that task's rollover pauses with `needs_review` / `settlement_capacity`. No new
score or rollover is made, history is not evicted, and later ticks do not repeat
the pause or create notification storms. The task card shows the localized
capacity reason. Re-enabling a full history is rejected; there is no automatic
history deletion/reset action. A parent can still finish or cancel the task, or
disable daily behavior and retain the ordinary task workflow.

Rollover, score, receipt and parent-private outbox event commit in the same Engine
transaction. Parent completion and exact correction also commit atomically.
Store failure leaves the previous whole state intact; restart/replay cannot
partially apply a date change or reverse a different/latest score.

Correction verifies the original ledger's task, source, child epoch, amount,
original deadline and receipt identity. It uses the existing exact Court reversal
with its revision and independent-review rules, never a broad member balance
undo. A changed/appealed ledger allows task completion but records `needs_review`;
a separate authorized parent can then review the exact source. The correction
decision is separate from the immutable settlement receipt. Later-day completion,
submission alone, cancellation and archival do not reverse the earlier score.

## Commands and API

Canonical `tasks.create` and `tasks.revise` accept an optional complete policy:

```json
{
  "missed_actor_revision": 1,
  "missed_policy": {
    "daily_rollover": true,
    "settle_time": "20:00",
    "repeat_penalty": false,
    "same_day_correction": false
  }
}
```

Use the normal assignee revision on create and task revision on revise. The
additional actor revision must match the current authorizing parent. Identity,
deadline, grace/penalty, Tasks/Court module, global automatic-penalty or timezone changes
revoke active policy authority; a parent reviews and reauthorizes it. Changing
only the task title or resaving an identical active policy preserves generation.
Current epochs and role are checked again during replay and notification delivery.
An old parent audience or old task deadline cannot receive a stale rollover notice.

Parent completion uses the existing `tasks.complete`, `/approve T000001` or
confirmation button. When separate review is needed, the completed task exposes
an exact correction button. Telegram also accepts:

```text
/correcttask T000001 | reason
correct penalty for T000001
исправь штраф за T000001
виправ штраф за T000001
```

“Correct penalty for this task” / «исправь штраф за эту задачу» /
«виправ штраф за це завдання» requires a verified bot delivery reply containing
exactly one task reference. Quoted text alone, a forged bot ID, another chat or
multiple task references supplies no authority. A malformed claimed correction
does not fall through to a model or generic latest-score undo.

`tasks.correct_miss` freezes `id`, task `revision`, `actor_revision`,
`settlement_id`, `court_revision` and `reason` before execution. Telegram stores
that plan durably; retry cannot reinterpret it against a new task or Court row.

## Scope and acceptance evidence

- Synthetic Engine tests cover cutoff, grace/midnight, DST gap, outage bounding,
  exact source/correction, no default policy, separate consent, skipped scores,
  submitted exemption, authority revocation, history/cap and Store failure/replay.
- Router tests cover EN/RU/UK exact commands, verified reply references, rejection
  of ambiguous/untrusted context, parent-only execution and frozen stale retries.
- Actual form browser tests exercise EN/RU/UK creation/editing, opt-in omission,
  unsupported scopes, multi-person preview, failed-save freeze, exact correction
  retry and truthful capacity status. The fixture is synthetic; domain authority
  is proved separately by Engine/native tests, not the fixture adapter.
- `tests/ha_task_settlements_smoke.py` is registered as native
  `ha_smoke.py --case task-settlements` and in the all-case path. Isolated HA 9.2
  acceptance passed authenticated execute, actual Store/reload, immutable history,
  exact score correction, cutoff/outage, submitted exemption and member revocation.

The card shows the last settlement only. Browsing **all skipped historical
settlements is not yet a user-facing feature**; full history remains preserved
internally and scored dates remain identifiable in Court. No standalone history
read endpoint is exposed without a matching bounded parent UI. No migration
auto-enables this policy, no external Court retry bridge is introduced, and no
legacy multi-date penalty avalanche is retained. These are intentional changes
from the former daily rollover algorithm, not claims of identical legacy behavior.
