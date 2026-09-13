# Interface and legacy parity audit — 2026-09-13

This audit supersedes claims that every legacy feature was transferred. **Data
preserved in a private migration archive is not an active migrated capability.**
Passing source/unit/browser checks is not household deployment, physical sound,
real Telegram delivery, or proof that every possible user expression works.

## Inventory and reproducibility

### Optional home-status increment — development after rc.7

The [home-status module](home-status.md) replaces exactly seven declarations:
named status groups, explicit activity mappings and five energy readouts. Owner
reviewed, registered sources stay off by default and require current family role
and HA ACL before an on-demand read. No private configuration is imported or
automatically activated. Home controls, kettle operations and forecasts remain
missing. Isolated native HA 2026.9.2 acceptance passed using synthetic entities,
real Options/Store/WS and a synthetic Telegram transport; this is not physical
device or live-bot acceptance. These counts describe the development source, not
the published rc.7 archive.

### Current release checkpoint — rc.7

[Early release 0.2.0-rc.7](https://github.com/Wave-is/home-assistant-family-assistant/releases/tag/0.2.0-rc.7)
is published, not a draft. All ten [exact-commit CI jobs](https://github.com/Wave-is/home-assistant-family-assistant/actions/runs/34760567071)
passed for `02dede051603a15a718fefc9b64fe863f6c47b95`. Combined local acceptance
passed 6440 Python tests (six skips, 23 subtests), 793 Node checks and 433 Chromium
scenarios. Actual isolated HA2026.9.2 command/school Store and Options cases, and
the exact published rc.6-to-rc.7 upgrade, passed. These are software gates, not
proof of every household expression or physical device behavior.

The table below now states current bounded support directly instead of leaving
repaired workflows labelled missing. Read-only household status and opt-in task
rollover/correction are separate development streams, **not rc.7 features**.

### Shared buyer increment — included in rc.7

The bounded assigned-purchase gap is implemented in rc.7: strict RU/UK/EN
creation, exact S-ID buyer edits, self/named filters and verified-shape name
correction. Shopping stays a shared family model and other members may still
help buy it. Fresh-request duplicate disambiguation, arbitrary/multiple-purchase
prose and complete legacy parity remain open.
See [scope, evidence and remaining gates](shopping-assignments.md). Deployment
does not establish unrestricted prose or live-message acceptance.

### Completion increment — included since rc.6

Bounded natural task report/deadline qualifiers, shopping quantities and named task-list
queries are now implemented (93 grammar regressions). Parent-only optional
reviewer deadlines have separate durable private reminders with no child penalty
during review; existing tasks stay off. See [reviewer contract](task-review-deadlines.md).
Root's actual isolated HA2026.9.2 `command-completion` case passed: grammar,
authenticated submit/review, real Store/reload, exact command replay and
cancellation of the completed review's pending reminder. Unrestricted prose
remains unsupported; assigned shopping and numbered batches have separate scope.

New namespaced card types coexist with previously loaded legacy task/alarm
elements without replacing them. Seven actual Chromium collision cases passed;
existing aliases remain compatibility-only and are not advertised as new cards.
The rc.7 combined release/browser gates are recorded above. Daily rollover and
exact correction are implemented in the separate rc.8 candidate, with their own
default-off contract. Remaining gaps include scoped memory/media, household
control mappings and the other explicitly open rows.

### Numbered-task increment — included in rc.7

The bounded [2–5 numbered-task grammar](telegram-task-batches.md) now validates
declared counts, per-item recipients and shared/per-item deadline/report settings
before one Engine batch. Invalid batches cannot fall through to single-command
or model repair. Recipient revisions and resolved dates are frozen; storage and
authority races, restart/replay, localized manager failures and task-ID receipts
have synthetic adapter/domain coverage. This supersedes only the explicit
numbered-creation gap below. Root's actual isolated HA2026.9.2 command-completion
case also passed real Store/reload, date-stable replay and authenticated atomic
rejection. Inline lists, arbitrary multi-task prose and live
bot acceptance for this increment remain open.

- [Source setting inventory](legacy-settings-inventory.json): all 26 original
  Assistant and three Court top-level configuration declarations are accounted
  for. Seventeen are replaced by the independent public architecture, three require
  explicit member/output review, and nine home-control/forecast declarations remain
  missing. These counts describe keys, **not 29 independent features**.
- `python tools/check_legacy_settings_inventory.py --legacy-root <local-source>`
  compares that inventory against the two actual old Python setup modules. It
  parses declarations without importing source, reading YAML/Store/credentials,
  or printing private values. Actual local source comparison passed. The default
  no-source check is only inventory validation, not legacy source acceptance.
- The actual old offline suites passed: 409 tests and 415 subtests across tasks,
  alarms, court, memory, household commands, migration snapshots, controller,
  gateway, voice/image and improvement helpers. They establish what the old code
  does; **they do not establish that the new implementation reproduces it**.
- `tests/test_legacy_court_phrase_coverage.py`: 52 passing recognition/response
  checks, including examples for all 42 original assessment pattern families,
  negation, history questions, and 20 positive/20 negative Russian variants.
  One old household-specific consequence joke is intentionally generic. English
  and Ukrainian use localized factual responses, not translated 20-item banks.
- [Native settings inventory](native-settings-audit.md) names every Options
  route and its actual consumer; [Telegram contract](telegram-command-parity.md)
  maps commands, aliases, callbacks and remaining language gaps. The separate
  [frontend audit](../tests/README-control-audit.md) records source sites and
  actual synthetic browser handler/action evidence without calling all rendered
  controls tested merely because they appeared on screen.

## Configuration: old → new

| Legacy keys | Current replacement / disposition |
| --- | --- |
| `telegram_event_entity`, `telegram_config_entry_id`, `family_chat_id`; Court `telegram_event_entity`, `chat_id`, `notify_entity` | One owner-configured private bot and explicit member/group enrollment. No old event entity, shared poller token or notify permission is silently adopted. Actual household cutover is a separate gate. |
| `group_mentions`, `group_privacy_mode` | Actual authenticated bot username and verified Telegram addressing metadata. An old Privacy Mode assertion is not a substitute for proof that a message addresses this bot. Custom old mention aliases are not automatically imported. |
| `gateway_url`, `gateway_secret` | Configurable direct Ollama/fallback, explicitly bounded HA agent, search and article providers. A private arbitrary-code agent/gateway and its credentials are not copied into public runtime. This does not reproduce all former gateway features. |
| `members`, `member_profiles` | Reviewed identity mapping, explicit aliases, names, roles and HA/Telegram bindings. Actor-relative spouse/son/daughter/sibling relationships are **not** modeled. A matching display name cannot confer identity or permissions. |
| `alarm_sirens` | Explicit native alarm binding. This audit restores separate `number` duration and `select` volume companions to the same registered alarm device. Existing native siren volume remains supported. Imported schedules remain disabled/gentle/penalty-free pending review. |
| `gate_entity`, `climates`, `fans`, `car_chargers` | **Missing:** generic reviewed household-control mappings and typed effect execution, including charger source interlock/read-back. Never replace this with arbitrary HA service execution. |
| `status_groups`, `active_entities`, `battery_soc_entity`, `battery_power_entity`, `load_power_entity`, `pv_power_entity`, `grid_power_entity` | **Replaced in development:** optional owner-configured factual home status/energy/groups, role + HA ACL + registry fences, manual card/API/private Telegram reads. Native isolated acceptance passed; no automatic legacy import, private configuration, physical inference or household activation. See [contract and evidence](home-status.md). |
| `kettle_status_entity`, `kettle_temperature_entity`, `kettle_fault_entity`, `kettle_stop_entity` | **Missing:** mapped kettle operations and factual temperature-growth/settings confirmation. A generic device switch is not equivalent. |
| `solar_forecast_audit` | **Missing:** matched-lead-time weekly forecast freezing, actual yield, curtailment flags and error statistics. School/calendar statistics do not replace it. |

### Nested settings and constants

- Alarm `duration_entity_id`, `volume_entity_id`, `duration_seconds`, and symbolic
  volume had been omitted. Repaired using optional explicit companion controls;
  they are validated before save and execution, with device binding checks and
  bounded read-back. Selecting them does not send device commands.
- Old enabled alarm flags and output permissions are not active after import.
  Modern second-check interval/grace, schedule exceptions and automatic-penalty
  settings must be reviewed explicitly. The old fixed daily cutoff and old
  random-delay constants are not necessarily the modern defaults.
- Court weekday/time/thresholds now have configurable period rules and labels.
  The old delivery-gated destructive weekly reset is intentionally replaced by
  period reports plus retained lifetime history. This is a documented semantic
  change, not byte-for-byte parity. Automatic consequences remain opt-in.
- Device addresses, measured household standby thresholds, bot IDs, credentials,
  and family-specific labels remain local. They are not portable defaults.
- The 29-declaration check is not a nested-field inventory. The old forecast
  configuration contains ten fields: five source entities, optional curtailment
  entity, capture/finalize clocks, SOC threshold and minimum PV power. Missing
  status groups contain `title/entities`; charger mappings contain `battery/grid`.
  These structures need actual consumers, not just preservation of their parent key.
- Old member profiles also used `match`, ordinal/role fallback, gender and aliases.
  Explicit reviewed identity mapping replaces positional inference. Memory stored
  scoped web-policy preferences and blocked-domain suffixes as well as dialogue;
  the new model/search configuration does not reproduce that memory policy.

## Algorithm and expression disposition

| Behavior | Evidence / limit |
| --- | --- |
| Task create/edit/assign/accept/start/report/review/return/cancel/archive | Canonical domain, Telegram aliases, private photo transport, migration text/report/history/reviewer/source-link tests. Audit repairs complete multiword recipient matching, whitespace in slash arguments and bounded relative day/week deadlines including `продли TASK на неделю`. Whole-slot validation blocks negation/malformed duration falling back to today's clock. Arbitrary prose and all legacy clarification chains are not claimed. |
| Shopping approval, partial purchase, duplicate resolution, separate model | Domain/UI/Telegram tests; legacy task-kind purchases convert into shopping records with reviewed quantities. Ambiguous matches are not purchased by guessing. |
| Two-stage wake-up, fresh answer, repeated siren, post-restart recovery | Alarm state-machine/output tests. Audit closes acknowledgement-during-intent-save race and omitted companion settings. Known pre-start failures restore earlier ownership; uncertain siren-call results retain it for compensating stop. Revocation and device replacement during helper calls stop before further commands. Physical loudness and hardware behavior still require separate acceptance. |
| Court assessments, negation, reasons, undo, periods, threshold display | Literal pattern-family checks plus canonical ledger/period/replay tests. Actual family roles and consequence policy are reviewed separately. |
| Mentions, bot replies, deterministic fallback, command ownership | Telegram transport/router/callback tests. Voice-only addressed messages now receive a clear unsupported-STT explanation rather than silence; this is **not** voice recognition support. |
| `/forget` historical semantics | Legacy cleared short dialogue context; public code used it to delete learned phrases. Audit makes old ambiguous commands explanation-only and introduces explicit `/forgetphrase ID`. No silent deletion of a different data type. |
| Personal/family long memory and short clarification continuation | **Incomplete:** archived memory is not active scoped conversational memory. Actor-private learned command templates are a different feature. |
| Telegram voice and general image interpretation | **Incomplete:** native Assist STT and task-photo submission do not replace the legacy Telegram voice/image assistant. No automatic media upload to an unconfigured provider. |
| Kinship expressions and inflected multiword identities | Explicit configured names/aliases are supported; complete-name parsing repaired. Unknown or ambiguous kinship must clarify, not infer a spouse or child from gender/role. Explicit relationship modeling remains open. |
| Self-improvement cloud-agent cascade | Private technical diagnostics, local phrase learning and reviewed proposals exist; arbitrary cloud-agent access to household credentials and auto-deployment is intentionally not part of public runtime. A bounded sanitized patch queue remains incomplete. |
| Home controls, forecast comparison and status interpretation | Missing mapping/algorithm groups listed above. Do not count their original private tests as public support. |

The final independent alarm review also reproduced cancellation before the main
siren attempt leaving a false ownership marker. This is repaired for companion
calls/read-back and durable intent-save cancellation, preserving previous real
ownership and normal cancellation propagation. Stop/unload drains compensating
cleanup even with a cancelled worker/caller. Tests distinguish known no-start from
an uncertain attempted start and retain that distinction through Engine restart;
they never use a real household signal as a test output.

## Workflow-level omissions confirmed by actual source comparison

These are additional concrete gaps, not covered by the top-level declaration
count or generic claims that tasks/shopping/court work. Old source references are
module/function names; no private settings or source files are shipped here.

| Legacy workflow / source contract | Public behavior and open gate |
| --- | --- |
| Evening unfinished-child-task settlement: `controller._async_settle_missed_child_tasks`; old task/controller runtime tests | **Optional replacement in rc.8 candidate.** Explicit parent policy rolls ordinary one-off child tasks; repeat penalties require separate consent. Submitted tasks are exempt. Exact dated receipts are atomic with score/date/notice, disabled/capped days are explicit skips, and downtime does not create a penalty backlog. No old external Court retry bridge or automatic import activation. [Contract and acceptance](task-settlements.md). |
| Same-day parent correction: `controller._same_day_court_correction_source`, `_async_reconcile_court_corrections`, `_handle_contextual_task_penalty_correction` | **Optional replacement in rc.8 candidate.** Parent completion corrects only the exact recorded task/date/child-epoch penalty; independent appeal rules still apply. Verified single-task Telegram reply or exact T-ID command freezes the correction receipt. Cancellation/archive/later-day completion do not reverse it. Full skipped-receipt history browsing remains deferred. [Contract](task-settlements.md). |
| Creation report qualifiers: `task_parser._extract_report_requirement` | **Bounded grammar repaired in rc.6.** Natural report/deadline qualifiers produce structured `text/photo/none` and deadlines; contradictory requirements reject before mutation. RU/UK/EN parser and native command-completion cases cover the repaired forms. Arbitrary sentence structure is not claimed. |
| Natural shopping quantities / assigned purchase tasks: `task_parser.split_shopping_quantity` and assigned-purchase parser | **Bounded grammar repaired in rc.6; shared assignments added in rc.7.** Natural quantities and explicit assigned-purchase forms create one separate S-record, not an ordinary task. Exact buyer edits/filters preserve metadata and helping-purchase permissions. See [forms and exclusions](shopping-assignments.md); arbitrary multi-purchase prose and fresh-request semantic duplicate detection remain open. |
| Explicit multi-task message and scoped task-list parser: old `task_parser` / atomic controller creation | **Bounded grammar repaired; acceptance scoped above.** Explicit 2–5 numbered messages validate declared counts, shared/per-item deadlines and reports/assignees before all-or-nothing Engine creation. Named scoped queries were repaired in the preceding increment. Arbitrary/inline multi-task prose remains unsupported; existing dashboard batches and model proposals remain separate entry points. |
| Reminder cadence and outage catch-up: old controller reminder dispatcher | **Changed policy.** Old precise deadlines used a one-hour reminder; day-only work used two daily slots and only the latest missed slot after downtime. Public tasks use one configurable reminder offset. Current behavior is not the old slot algorithm. |
| Reviewer deadline: old task ledger review window / overdue-review event | **Optional workflow repaired in rc.6.** Parent-only `review_minutes` schedules one durable, report-generation-bound private overdue-review notice. Submitted work stays exempt from child penalties. Existing records remain off; series-level configuration and natural-language review-policy editing are not added. [Contract and native/browser evidence](task-review-deadlines.md). |

Old source evidence was checked against its task/parser/controller and memory
tests. Public counter-evidence is in `test_task_events.py`,
`test_court_configured_rules.py`, `test_telegram_legacy_parity.py` and the actual
parser/domain code. Six original read-only parser probes used fictional members;
they exposed the gaps subsequently repaired in the bounded increments above,
not passing acceptance at the time. No additional omitted Court assessment
pattern family was identified in this bounded second review.

### Next repair order and acceptance

1. Continue exact regression coverage for the released deterministic report,
   quantity, assignment, scoped-list, numbered-task and reviewer workflows.
2. Complete combined release gates for the implemented opt-in rollover/correction
   policy. Evaluate day-only cadence separately; no retroactive or repeated
   penalties unless separately reviewed and explicitly enabled.
3. Scoped memory/web policy, home/energy/forecast mappings and remaining provider
   capabilities: separate privacy, effect-authorization and household gates.

Online-school integration is included in rc.6/rc.7 with its own provider and
privacy gates; it does not establish parity for these non-school workflows.

## Release/cutover gate

Keep unfinished rows visible. Any release must link exact-commit Python/frontend/
browser/native-HA/upgrade checks. Core configuration, active sirens, penalties,
network policies and existing household records must not be changed just to make
the readiness display green. Activation requires a reviewed rollback point and
the applicable household authorization, not an audit checkbox.
