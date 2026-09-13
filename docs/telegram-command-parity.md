# Telegram command and legacy parity audit

Audit date: 2026-09-13. This inventory describes the public development code,
not a claim that every legacy algorithm or live Telegram scenario was migrated.
Only fictional fixtures were used. No bot, school account or household device
was contacted. Legacy observations below were supplied as sanitized contracts;
no private source, data or credentials were copied into this worktree.

## Entry points and evidence

- `telegram/manager.py:process`: current bot/configuration and actor epoch checks,
  owner-confirmed enrollment, scoped command execution, persisted reply/offset.
- `telegram/router.py:addressed` and `route`: own-bot mentions/replies, deterministic
  commands first, explicit unsupported slash commands never sent to an LLM.
- `telegram/commands.py`: exact input/reference signature and persisted plan before
  mutation; record revisions and Engine authority are checked again on replay.
- `telegram/context.py`: task/proposal references come from delivery receipts in
  the same bot/chat, not IDs pasted into quoted text. Private poll/digest/personal
  task responses are excluded from automatically copied model quotes.
- `assistant/jobs.py`, `provider.py`, `service.py`, `plans.py`: bounded durable
  jobs, provider fallback, typed reviewed proposals and independently checked
  roles/revisions. Answer-only model output explicitly states that family data
  was not changed. Search snippets and quotes cannot authorize mutations.

All paths above are under `custom_components/family_assistant/`.
The native command menu is a shortcut subset; `/commands` / `/help` provides
the larger text catalog. Hiding a menu item is not an authorization mechanism.

## Per-command inventory

Implemented means a public route exists with canonical domain checks. The
evidence column identifies reproducible tests; it does not certify unlisted
real-user phrases, real transport, physical sound or internet connectivity.

| Command and arguments | Public behavior / authority | Evidence in `tests/` |
| --- | --- | --- |
| `/start` without a code | Local help | `test_telegram.py` |
| `/start CODE` | Capture private enrollment; owner must separately approve | `test_telegram.py` |
| `/family_setup CODE` | Capture group enrollment; owner must separately approve | `test_telegram.py` |
| `/help`, `/commands` | Bounded EN/RU/UK help, no model | `test_telegram_legacy_parity.py`, `test_telegram_language_audit.py` |
| `/ping` | Immediate local availability response | `test_telegram.py` |
| `/tasks` | Authorized active task list, private-task filtering in groups | `test_telegram.py`, `test_telegram_legacy_parity.py` |
| `/mine` | Current actor's tasks/reminders only | `test_telegram_legacy_parity.py` |
| `/task MEMBER \| TITLE` | `tasks.create`; current member resolution and role gates | `test_telegram.py`, `test_telegram_language_audit.py` |
| `/accept TASK` | `tasks.accept`; not a parent's completion approval | `test_telegram_legacy_parity.py` |
| `/begin TASK` | `tasks.start` | `test_telegram_legacy_parity.py` |
| `/done TASK \| REPORT` | `tasks.submit`; preserves text report, requires current lifecycle | `test_telegram_legacy_parity.py` |
| `/report TASK` photo caption | One verified durable photo, current task/uploader binding; no extra note or album | `test_telegram_photo_reports.py`, `ha_telegram_smoke.py` |
| `/approve TASK` | `tasks.complete`; parent/owner approval | `test_telegram_legacy_parity.py` |
| `/changes TASK \| REASON` | `tasks.request_changes`; current revision | `test_telegram_legacy_parity.py` |
| `/edit TASK deadline EXPRESSION` | `tasks.revise` using deterministic deadline parser | `test_telegram_legacy_parity.py`, `test_language_context.py` |
| `/edit TASK title TEXT` | `tasks.revise`; existing lifecycle/authority retained | `test_telegram_language_audit.py` |
| `/edit TASK assignee MEMBER` | `tasks.revise`; configured identity, no inferred relationship | `test_telegram_legacy_parity.py` |
| `/canceltask TASK` | `tasks.cancel`; not proposal cancellation | `test_telegram_legacy_parity.py` |
| `/archive TASK` | `tasks.archive`; history preserved | `test_telegram_legacy_parity.py` |
| `/shopping` | Authorized separate shopping list | `test_telegram.py` |
| `/buy NAME \| QUANTITY \| UNIT` | `shopping.add`; children create approval requests | `test_telegram_legacy_parity.py` |
| `/bought ITEM [\| QUANTITY]` | `shopping.purchase`; exact ID or uniquely matching active name | `test_telegram_legacy_parity.py` |
| `/approvebuy ITEM` | `shopping.approve`; parent/owner | `test_telegram_legacy_parity.py` |
| `/rejectbuy ITEM` | `shopping.reject`; parent/owner | `test_telegram_legacy_parity.py` |
| `/alarms` | Authorized schedules and enabled state, not physical sound evidence | `test_telegram.py` |
| `/alarm MEMBER \| DAYS \| HH:MM` | Create/update exact day group using `alarms.save`; parent/owner | `test_telegram_legacy_parity.py`, `test_telegram_language_audit.py` |
| `/alarm MEMBER \| DAYS \| on/off` | `alarms.enable` for exactly one existing group | `test_telegram_legacy_parity.py` |
| `/stats` | Authorized court summary/reasons and configured thresholds | `test_court_periods.py`, `test_telegram_legacy_parity.py` |
| `/history`, `/история`, `/минусы`, `/плюсы`, `/дело MEMBER` | Scoped Court history/sign/member filtering via the Court parser | `test_court_full_fidelity.py`, `court/parser.py`, `court/patterns.py` |
| `/undo`, `/rules` | Existing Court undo/rules routes; current actor and record constraints remain | `test_court_full_fidelity.py`, `court/parser.py` |
| `/week` | Current configured week totals; no destructive lifetime reset | `test_court_periods.py`, `test_court_weekly.py` |
| `/award MEMBER \| POINTS \| REASON` | `court.award`; parent/owner, signed explicit points | `test_court_full_fidelity.py`, `test_court_configured_rules.py` |
| `/appeal RECORD \| REASON` | `court.appeal`; authorized record and revision | `test_court_full_fidelity.py` |
| `/reverse RECORD \| REASON` | `court.reverse`; parent/reviewer constraints | `test_court_full_fidelity.py` |
| `/courtresolve RECORD \| uphold/reverse \| REASON` | `court.resolve_appeal`; independent-review policy retained | `test_court_full_fidelity.py` |
| `/calendar` | Authorized agenda; participant-only/unapproved events excluded in group replies | `test_calendar_edges.py`, `test_family_calendar.py` |
| `/event TITLE \| START \| END` | `calendar.save`; exact ISO timestamps, child approval rules | `test_calendar_edges.py` |
| `/eventapprove EVENT \| REASON` | `calendar.approve` | `test_calendar_edges.py` |
| `/eventcancel EVENT \| REASON` | `calendar.cancel` | `test_calendar_edges.py` |
| `/routines` | Private authorized templates/runs | `test_routine_edges.py` |
| `/routine PRESET \| MEMBER` | `routines.save` from an available generic preset | `test_routine_edges.py` |
| `/routinestart TEMPLATE \| MEMBER` | `routines.start`; current template revision | `test_routine_edges.py` |
| `/routinecancel RUN \| REASON` | `routines.cancel`; private authorized request | `test_telegram_language_audit.py` |
| `/routinemode MODE[,MODE]` | `routines.modes`; current config revision | `test_telegram_language_audit.py` |
| `/rewards` | Authorized privilege catalog and wallet projection | `test_rewards.py` |
| `/wallet` | Actor wallet, not another person's score request | `test_rewards.py` |
| `/rewardadd NAME \| COST [\| DESCRIPTION]` | `court.reward_save`; parent/owner | `test_rewards.py` |
| `/reward REWARD [\| NOTE]` | `court.reward_request`; reserve available points | `test_rewards.py` |
| `/rewarddecide REQUEST \| DECISION \| REASON` | `court.reward_transition`; role/state checks, no device action | `test_rewards.py` |
| `/prices`, `/watchlist` | Authorized tracked-price list | `test_price_watch.py` |
| `/watch URL [\| NAME]`, bare URL | `price_watch.add`; canonical URL/role validation | `test_price_watch.py` |
| `/unwatch ID` | `price_watch.remove`; exact visible record revision | `test_price_watch.py` |
| `/internet [MEMBER]` | Authorized Kid Control projection; unknown/stale remains unknown | `test_kid_telegram.py` |
| `/netpause MEMBER` | Reviewed `mikrotik.kid_plan` pause, not immediate router execution | `test_telegram_language_audit.py` |
| `/netresume MEMBER` | Reviewed normal-schedule plan | `test_telegram_language_audit.py` |
| `/netgrant MEMBER \| MINUTES` | Reviewed temporary-access plan with native expiry prerequisites | `test_telegram_language_audit.py`, `test_kid_telegram.py` |
| `/netblock MEMBER \| MINUTES` | Reviewed temporary-pause plan | `test_telegram_language_audit.py` |
| `/netuntil MEMBER \| HH:MM` | Reviewed temporary access until next local clock occurrence | `test_telegram_language_audit.py` |
| `/netschedule MEMBER \| DAYS \| HOURS` | Reviewed schedule plan | `test_telegram_language_audit.py` |
| `/netlimit MEMBER \| RATE` | Reviewed rate plan | `test_telegram_language_audit.py` |
| `/netconfirm PLAN` | `mikrotik.kid_apply`; exact reviewed plan and current authority | `test_kid_telegram.py` |
| `/netcancel PLAN` | `mikrotik.kid_cancel` | `test_telegram_language_audit.py` |
| `/unknown_devices` | Private parent source-bound inventory, no admission/enforcement | `test_network_admission_telegram.py` |
| `/network_alerts on/off` | Private current actor discovery subscription, source/consent guards | `test_network_admission_telegram.py` |
| `/polls` | Private poll descriptors; group receives private-chat guidance | `test_telegram_polls.py` |
| `/ask QUESTION` | Explicit configured assistant request; not direct unreviewed mutation | `test_telegram_legacy_parity.py`, `test_assistant.py` |
| `/confirm PROPOSAL` | `conversation.confirm`; frozen five-minute proposal | `test_assistant.py`, `test_semantic_feedback.py` |
| `/confirm TASK` | Explicit task-ID compatibility path to `tasks.complete`; parent/owner only | `test_telegram_legacy_parity.py` |
| `/cancel PROPOSAL` | `conversation.reject`; does not cancel a task | `test_assistant.py` |
| `/feedback PROPOSAL \| CATEGORY \| EXPECTED` | Private rejection note; expected text neither executed nor learned | `test_semantic_feedback.py` |
| `/learn SOURCE \| CANONICAL` | Current actor's explicit phrase rule; no new permissions | `test_learning.py` |
| `/forgetphrase PHRASE` | Disable one current actor phrase rule; keep history | `test_learning.py`, `test_telegram_language_audit.py` |
| `/forget`, `/забыть` with any tail | Explanation only; incompatible legacy memory semantics, no deletion/replay | `test_telegram_language_audit.py` |
| `/voice`, addressed voice messages | Explicit EN/RU/UK unsupported response; no transcription/download/model job | `test_telegram_language_audit.py`, `test_telegram_command_scope.py` |

## Current slash aliases

Aliases inherit the canonical command's authority, not the apparent meaning of
an isolated verb. In particular, `/принять` means accept an assigned task, whereas
`/подтвердить TASK` means parent completion. Case and Russian `ё/е` normalize.
The historic wrong-keyboard-layout and `/.command` normalization remain bounded
to recognized commands; arbitrary fuzzy text is not executed as a slash command.

| Canonical | Explicit aliases |
| --- | --- |
| `/help` | `/commands`, `/команды`, `/команди`, `/помощник`, `/помічник`, `/помощь`, `/допомога`, `/хелп`, `/старт`; help also recognizes `/меню`, `/справка`, `/інструкція`, `/довідка` |
| `/ping` | `/пинг`, `/пінг` |
| `/tasks` | `/дела`, `/задачи`, `/таски`, `/завдання`, `/справи`, `/todo` |
| `/mine` | `/мои`, `/мої` |
| `/task` | `/задача`, `/створити_завдання`, `/таск`; `/завдання` with arguments |
| `/accept` | `/принять`, `/прийняти` |
| `/begin` | `/начать`, `/почати` |
| `/done` | `/сдано`, `/сдал`, `/сдала`, `/здано`, `/здав`, `/здала`, `/готово` |
| `/report` | `/фотоотчет`, `/фотоотчёт`, `/фотозвіт` in the photo handler |
| `/approve` | `/принято`, `/одобрить`, `/схвалити`, `/схвалено` |
| `/changes` | `/переделать`, `/доопрацювати` |
| `/edit` | `/изменитьзадачу` |
| `/canceltask` | `/отменитьзадачу`, `/скасуватизавдання` |
| `/archive` | `/архив`, `/архів` |
| `/shopping` | `/покупки`, `/шопинг`, `/шоппинг`, `/шопінг`, `/список` |
| `/buy` | `/купи`, `/купить`, `/придбай`, `/придбати` |
| `/bought` | `/куплено`, `/купил`, `/купила`, `/купили`, `/придбано`, `/придбав`, `/придбала` |
| `/approvebuy` | `/одобритьпокупку` |
| `/rejectbuy` | `/отклонитьпокупку` |
| `/alarms` | `/будильники`, `/будильник`, `/подъем`, `/подъём`, `/підйом`; these aliases list schedules, not inferred edits |
| `/stats` | `/статистика`, `/стата`, `/суд`, `/баллы`, `/бали`, `/штрафы`, `/штрафи`, `/очки`, `/рейтинг` |
| `/week` | `/неделя`, `/тиждень` |
| `/award` | `/штраф`, `/бонус`, `/наградить`, `/нагородити`; signed points still required |
| `/appeal` | `/апелляция`, `/апеляція` |
| `/calendar` | `/календарь`, `/календар`, `/планы`, `/плани`, `/розклад` |
| `/routines` | `/рутины`, `/рутини`, `/привычки`, `/звички` |
| `/rewards` | `/награды`, `/нагороди`, `/магазин` |
| `/wallet` | `/кошелек`, `/кошелёк`, `/гаманець`, `/баланс` |
| `/prices` | `/цены`, `/ціни`, `/вишлист`, `/вішліст` |
| `/ask` | `/спросить`, `/запитати` |
| `/confirm` | `/подтвердить`, `/підтвердити` |
| `/cancel` | `/отмена`, `/скасувати`, `/скасування`; not task cancellation |
| `/forget` | `/забыть`; compatibility guidance only |
| `/internet` | `/интернет`, `/інтернет` in the network adapter |
| `/netpause` | `/нетпауза` |
| `/netgrant` | `/нетпродовжити`, `/нетпродлить` |
| `/unknown_devices` | `/неизвестные`, `/невідомі` |

## Callback and natural-language inventory

| Input family | Implemented contract / limitation | Evidence |
| --- | --- | --- |
| `fa:RUN:NONCE:ANSWER` | Fresh actor-bound alarm challenge; wrong/stale answer cannot confirm wake-up | `test_telegram.py`, `test_telegram_command_scope.py`, `ha_telegram_smoke.py` |
| `fp:confirm/cancel:PROPOSAL` | Same proposal lifecycle as `/confirm` / `/cancel` | `test_assistant.py`, `ha_telegram_smoke.py` |
| `fn:confirm/cancel:PLAN` | Exact reviewed network plan, no bypass of read-back/authority | `test_kid_telegram.py`, `ha_telegram_smoke.py` |
| `fr:RUN:STEP:REVISION:NONCE` | Private current assignee and routine step | `test_routine_edges.py`, `test_routine_handoffs.py` |
| `ps:ACTION:POLL[:OPTION]`, `pr:yes/no:REVIEW` | Private selection, explicit fresh review, canonical poll mutation | `test_telegram_polls.py` |
| RU/UK/EN availability, help and read expressions | Strict whole-message patterns in `intents.py` / `router.py`; no model needed | `test_telegram.py`, `test_telegram_legacy_parity.py` |
| Task creation in either member/keyword order | Complete configured multiword name/alias is preferred; equal matches reject; no automatic kinship | `test_telegram_language_audit.py` |
| `напомни мне`, `нагадай мені`, `remind me to` | Self-only personal task, deterministic due date, zero penalty | `test_telegram_legacy_parity.py` |
| Deadline change, including exact task reply | `TASK_REVISE_RE`; received-date/week computation, bounded relative day/week slots, DST/past checks; receipt ID is not authority | `test_language_context.py`, `test_legacy_relative_deadlines.py` |
| Short `готово` / `done` reply | Exactly one receipted task; child submits, privileged actor confirms | `test_telegram_legacy_parity.py` |
| Natural shopping add / purchased name | Exact unique active item or ID; no arbitrary duplicate selection | `test_telegram_legacy_parity.py` |
| Natural alarm weekdays/weekends | Explicit member, day group and time; two groups atomic, no guessed holidays | `test_telegram_legacy_parity.py` |
| Natural court praise/penalty/history/periods | Configured identities/rules and authorized ledger; no household-specific consequences | `test_court_configured_rules.py`, `test_court_periods.py` |
| Natural internet pause/resume/grant | Conservative phrases in `telegram/network.py`; a reviewed plan, not immediate execution | `test_kid_telegram.py` |
| Short proposal confirmation phrases | Exact frozen proposal reference; generic yes is not accepted | `telegram/proposal_reply.py`, `test_assistant.py` |
| Other ordinary text | Optional configured model; typed mutations require confirmation, otherwise honest unknown | `test_assistant.py`, `test_telegram_media_jobs.py` |

## Confirmed missing or incompatible legacy behavior

1. **Conversation memory is not migrated as a live feature.** `/память`, `/запомни`,
   `/забудьпамять`, `/забыть_память`, `/forgetmemory` have no implemented public
   command. They return unknown and do not invoke the model. The old `/forget`
   and `/забыть` cleared actor/chat conversation context and pending clarification;
   they must not silently disable a different learned-phrase record. Their new
   guard is deliberately non-mutating. The explicit `/forgetphrase` retains the
   public phrase-rule operation and the dashboard's internal `conversation.forget`.
2. **Telegram STT and old voice behavior remain absent.** Native Assist voice
   shopping is a different adapter. Addressed voice now receives explicit
   unsupported guidance instead of silence; ordinary unrelated group audio is
   ignored. No download or speech recognition was added.
3. **Actor-relative kinship is absent.** Roles do not establish wife/husband,
   son/daughter or siblings. Explicit configured aliases and conservative name
   stems are supported; unknown/equally matching people reject. Reusable family
   relationships need a reviewed model and per-actor resolution before migration.
4. **Deadline grammar is deliberately bounded.** `/продлить` was present in an
   old ownership catalog but not dispatched by its slash handler: it is a stale
   advertised legacy command, not a verified working route to reproduce. This
   audit restores natural `продли TASK на неделю`, explicit reply-based edits,
   creation/reminder duration markers and `/edit TASK deadline in a week`.
   Day/week durations are 1–365 days, with digits or the documented one–four
   word forms. As in the actual old parser, they count from the received local
   calendar date, **not from the old task deadline**; default due time remains
   20:00 in the configured household timezone. The exact date/revision is frozen
   for replay. Negation, malformed counts, ambiguous task replies and DST
   gaps/folds reject; a trailing clock cannot rescue an invalid duration as
   today's deadline. Months, arbitrary number-word inflections and all possible
   prose remain unsupported. This is not unrestricted natural-language parsing.
5. **Home/energy/environment mappings, full reply-variant banks and short
   clarification algorithms are not complete.** They require generic settings,
   approved actor scopes/retention and effect permissions. No private household
   constants or fabricated states were substituted.
6. **This is not full algorithm parity.** Destructive weekly score resets are not
   reproduced; original history/lifetime points remain immutable. Alarm policy,
   output mapping, physical sound, live bot acceptance and household cutover have
   their separate migration and authorization gates.
7. **Some working old aliases now differ or are absent.** Old parent `/принять`
   or `/принял` approved completion; child usage accepted the assignment. Public
   `/принять` always means `/accept`, not approval. `/принял`, `/напомнить` and
   `/удалитьзадачу` have no public router alias. Old `/покупки TEXT` added an item;
   the public alias reads the list. Old `/internet` returned configured home-network
   status; the public route is Kid Control. These are explicit compatibility gaps,
   not successful transfers. Current unambiguous `/approve`, `/buy` and other
   documented canonical commands retain their own contracts.
8. **Concrete creation/query grammar is missing.** Report qualifiers can remain
   in task titles and suppress deadline extraction; natural leading shopping
   quantities remain part of the item name. Assigned purchases, explicit 2–5-item
   task messages, scoped named-child task queries, and contextual same-day penalty
   correction are not equivalent to the available dashboard/domain operations.
   See the [workflow-level audit](legacy-parity-audit.md#workflow-level-omissions-confirmed-by-actual-source-comparison)
   for reproduction examples and the exact missing/changed behavior.
9. Missing memory aliases additionally include `/memory`, `/remember`,
   `/forget_memory`, `/забудь` and natural list/remember/forget phrases. Scoped web
   preferences and blocked-domain suffixes were part of old memory behavior;
   retaining a transcript or providing a search endpoint does not reproduce them.

## Repairs and verification in this audit

- Complete multiword task recipients no longer silently resolve to a matching
  first-word ID; verb-first forms no longer get swallowed by the bare-name form.
- Task/alarm and normal slash argument parsing accepts tabs/newlines while exact
  original input is retained in idempotency signatures.
- Relative task/reminder deadlines and extend verbs are restored with whole-slot
  validation; unsupported or negated durations cannot fall through to a later
  time fragment. `tests/test_legacy_relative_deadlines.py` adds creation, reminder,
  edit, reply, timezone, strict range, permission and retry regressions.
- `/подъём` now reaches the existing alarm-list alias through `ё/е` normalization.
- `/forget` incompatibility is guarded before old pending-plan replay. New
  `/forgetphrase` is explicit, actor-scoped and replay-tested; EN/RU/UK teaching
  copy and setup guides use the new name.
- Addressed voice gets truthful localized guidance with zero media/model jobs.
- `/commands` now also exposes existing poll, proposal/feedback and additional
  network commands which previously had no help entry. The native quick menu
  remains a subset, not the sole catalog.

Focused regression command:

```text
python -m pytest -q tests/test_telegram_language_audit.py tests/test_telegram_command_scope.py tests/test_telegram.py tests/test_telegram_legacy_parity.py tests/test_language_context.py tests/test_learning.py tests/test_assistant.py tests/test_telegram_photo_reports.py tests/test_telegram_media_jobs.py tests/test_telegram_polls.py tests/test_kid_telegram.py tests/test_court_periods.py tests/test_court_full_fidelity.py tests/test_court_configured_rules.py tests/test_family_calendar.py tests/test_routines.py tests/test_rewards.py tests/test_network_admission_telegram.py tests/test_semantic_feedback.py tests/test_routine_handoffs.py tests/test_calendar_edges.py tests/test_routine_edges.py tests/test_price_watch.py
```

This focused run passed 567 tests in 24.53 seconds. Ruff and whitespace checks
passed for owned files. Native HA and full-release gates are separate evidence.
AGY ran a bounded sandboxed read-only review of public router/parser files. Its
multiword-recipient finding was independently reproduced and repaired; its
claim that `/accept` had no handler was rejected against the actual delegated
`task_commands` handler and passing lifecycle tests. A first timed-out review
provided no accepted evidence.
