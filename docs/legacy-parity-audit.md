# Interface and legacy parity audit — 2026-09-13

This audit supersedes claims that every legacy feature was transferred. **Data
preserved in a private migration archive is not an active migrated capability.**
Passing source/unit/browser checks is not household deployment, physical sound,
real Telegram delivery, or proof that every possible user expression works.

## Inventory and reproducibility

- [Source setting inventory](legacy-settings-inventory.json): all 26 original
  Assistant and three Court top-level configuration declarations are accounted
  for. Ten are replaced by the independent public architecture, three require
  explicit member/output review, and 16 home/energy mapping declarations remain
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
| `status_groups`, `active_entities`, `battery_soc_entity`, `battery_power_entity`, `load_power_entity`, `pv_power_entity`, `grid_power_entity` | **Missing:** configurable factual home/energy/status groups. Current family Today card is not the old home-energy summary. |
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
| Evening unfinished-child-task settlement: `controller._async_settle_missed_child_tasks`; old task/controller runtime tests | Old logic skipped submitted work, applied an exact-source Court penalty, then rolled the due date forward one day; unavailable Court retained a retry. Public `domain/task_events.py` uses due time plus grace, and `domain/penalties.py` deliberately permits one automatic penalty per task. `test_task_events.py` verifies rescheduling does not repeat it. **Changed penalty policy; missing daily rollover.** Do not silently introduce repeated penalties during import. |
| Same-day parent correction: `controller._same_day_court_correction_source`, `_async_reconcile_court_corrections`, `_handle_contextual_task_penalty_correction` | Generic `court.reverse_source` exists and is tested, but automatic same-day completion reconciliation and its contextual Telegram expression are **missing**. Reversal must target the original penalty and date, retain a retry receipt, and never reverse an unrelated score. |
| Creation report qualifiers: `task_parser._extract_report_requirement` | **Missing grammar.** `с фотоотчётом`, `нужен фотоотчёт`, `с фото`, `без отчёта` previously set policy and contradictory requirements rejected. Current synthetic `задача child убрать стол на завтра с фотоотчетом` leaves the deadline/report words in the title, with no deadline or report policy. Domain `text/photo/none` and photo transport work; they do not fix creation parsing. |
| Natural shopping quantities / assigned purchase tasks: `task_parser.split_shopping_quantity` and assigned-purchase parser | **Missing grammar/assignment semantics.** `добавь 2 кг яблок в покупки` currently becomes a name containing the quantity, quantity 1 and no unit; `попроси child купить хлеб` has no deterministic intent. Explicit `/buy NAME \| QUANTITY \| UNIT` works. A separate shopping record needs a reviewed assignment model, not silent conversion to an ordinary task. |
| Explicit multi-task message and scoped task-list parser: old `task_parser` / atomic controller creation | **Missing Telegram grammar.** Old 2–5-item messages validated declared counts, shared/per-item deadlines and per-item reports/assignees before all-or-nothing creation. Explicit multi-item and `покажи задачи child` probes have no deterministic intent. Dashboard batch operations and model proposals are different entry points. |
| Reminder cadence and outage catch-up: old controller reminder dispatcher | **Changed policy.** Old precise deadlines used a one-hour reminder; day-only work used two daily slots and only the latest missed slot after downtime. Public tasks use one configurable reminder offset. Current behavior is not the old slot algorithm. |
| Reviewer deadline: old task ledger review window / overdue-review event | **Missing live workflow.** Public submission notifies the reviewer and correctly stops child deadline/penalty processing, but does not implement the old separate review deadline and overdue-review reminder. Preserved ledger fields do not schedule that work. |

Old source evidence was checked against its task/parser/controller and memory
tests. Public counter-evidence is in `test_task_events.py`,
`test_court_configured_rules.py`, `test_telegram_legacy_parity.py` and the actual
parser/domain code. Six read-only parser probes used fictional members; they
exposed gaps, not passing acceptance. No additional omitted Court assessment
pattern family was identified in this bounded second review.

### Next repair order and acceptance

1. Deterministic report/deadline and shopping-quantity parsing: exact structured
   payloads, contradiction/ambiguity rejection, permission checks and frozen retry.
2. Role-dependent legacy command compatibility, scoped list queries and atomic
   multi-task grammar: no silent semantic reinterpretation or partial writes.
3. Reviewer reminders, day-only cadence and explicit rollover/correction policy:
   restart/outage tests, exact source/date correction, no retroactive or repeated
   penalties unless separately reviewed and explicitly enabled.
4. Scoped memory/web policy, home/energy/forecast mappings and remaining provider
   capabilities: separate privacy, effect-authorization and household gates.

The independent online-school branch remains separate from these repairs.

## Release/cutover gate

Keep unfinished rows visible. Any release must link exact-commit Python/frontend/
browser/native-HA/upgrade checks. Core configuration, active sirens, penalties,
network policies and existing household records must not be changed just to make
the readiness display green. Activation requires a reviewed rollback point and
the applicable household authorization, not an audit checkbox.
