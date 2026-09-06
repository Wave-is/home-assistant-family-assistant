# Implementation and acceptance matrix

The product vision remains the scope. Status is explicit: planned, implemented,
unit-tested, HA-tested, hardware-tested, released. These are distinct gates.
Nothing is production-ready solely because a mock test passes.

| Requirement | Implementation | Verification / remaining gate |
| --- | --- | --- |
| Clean public source and HACS structure | In progress | No public release yet |
| Atomic persistence, idempotency, roles | Implemented / unit-tested | Disk faults, concurrent replay, revoked identities, batch rollback |
| Multiple households / member administration | Implemented / HA-tested | Config/options, four generic templates, time zone, aliases and bound HA identity |
| Separate shopping model | In progress / unit-, browser- and HA-tested | Partial purchase, approvals, recurring items, explicit merge, per-item history and archive; metadata/media/price/pantry extensions pending |
| Tasks, deadlines, reports and reviews | In progress / unit-, browser- and HA-tested | Checklist/lifecycle/editor, household-zone deadline, text review/return/archive, strict recurring edits; legacy parity and media pending |
| Court, rewards, penalties and appeals | In progress / unit-, browser- and HA-tested | Reversible ledger, independent appeals, weekly snapshots; privilege catalog/reservations/parent approval/fulfillment/refund; advanced automatic consequences pending |
| Alarms and durable fresh challenges | Implemented / unit- and HA-tested | Two stages, renewed siren, fresh nonce, expiry, DST, exceptions, penalty cap; physical sound check pending |
| Own Telegram bot and onboarding | Implemented / HA-tested with synthetic transport | Options, polling lifecycle, owner-confirmed enrollment, mentions, replay/roles; live Telegram acceptance still pending |
| LLM, search, command repair | In progress / unit- and HA-tested | Own Ollama/fallback, bounded plans, confirmed mutations, SearXNG snippets and standard Assist entity; real-model eval, full article fetching and external agent delegation pending |
| RU / UK / EN | In progress | Existing forms/cards/errors translated; Telegram/docs and future modules pending |
| Today and module cards | Ten cards browser-tested | Today/shopping/tasks/court/alarms/conversation/network/health/calendar/routines; richer editors and other module cards pending |
| Family calendar | In progress / unit-, browser- and HA-tested | Private event projection, child approval, date-only/timed agenda, recurrence/task-link editor, preparation reminders, opt-in read-only HA calendar; production acceptance pending |
| Routines | In progress / unit-, browser- and HA-tested | Ordered durable runs, per-step handoffs, private confirmations, overrides, approved observations, three-valued conditions, modes/templates, recurrence and template skip editor; richer per-step editors and production acceptance pending |
| Durable notifications / incident closure | Core unit- and HA-tested | Fanout, retries, quiet hours, uncertainty; Telegram wiring, Repairs and explicit review/retry UI |
| Corrections / journal / local learning | In progress / HA-tested | Explicit actor-private phrase dictionary, fresh parsing and authorization; developer patch loop pending |
| Pantry, meals, school, maintenance | Planned | APIs, scheduling and cards |
| Polls, digests, presence | Planned | Consent, permissions and fallbacks |
| MikroTik inventory / HA matching | Implemented / unit-, HA- and native-tested | HTTPS/CA options, bounded tables, registry MAC/current tracker evidence, ambiguous/stale handling and parent-only card; native CHR REST inventory passed |
| Static leases / comments | Implemented / unit-, browser-, HA- and native-tested | Native DHCP exchange produced a dynamic lease; public executor converted/commented/read back/replayed over verified REST; native multi-target fault rollback remains a separate gate |
| Kid Control including Telegram parents | In progress / unit-, browser-, HA- and native-tested | Adopted profiles; pause/resume, hours/rate, temporary grants/pauses, private outcomes and timers. Native hAP checks plus CHR REST, routed IPv4 UDP, autonomous expiry and actual VM startup restoration passed; richer modes/topologies remain |
| Unknown clients / allowlist | Planned | Topology + IPv6 + local rollback prerequisite |
| Diagnostics / Repairs / backup / migration | Planned | No live legacy data modified |
| Release CI and secret checks | Implemented / CI-tested | Python, browser, actual HA, HACS and Hassfest all passed on main; release artifact/migration gates still pending |
| Existing-home migration and verification | Planned | Final integration gate |

## Baseline, 2026-09-06

Private legacy project: 401 unittest cases discovered; one unrelated guest-image
test could not import the missing paramiko dependency. The family suite's cases
ran without failures in that invocation. No production code was changed.

Local workstation has Python 3.11 and Node 20. Real HA checks run in a separate
ephemeral HA 2026.8.2 container with network disabled, no production configuration,
credentials, ports or devices mounted. The actual Home Assistant siren platform
is exercised with a synthetic entity, not by replacing its service registry.

## Verified checkpoint, 2026-09-06

- 638 Python tests passed (domain, adapters, outbox, Telegram, model/search isolation, language/context, recurring tasks/purchases, task editing, shopping merge/history, court periods/review, reward wallets/requests, calendar/privacy/reminders, routine conditions/handoffs/replay authority/private commands and incidents, network inventory/lease/Kid Control effects and status, lab fixtures, public contracts).
- 165 frontend unit tests and 49 Chromium browser tests passed.
- Calendar and routine cards now share localized daily/weekly/monthly recurrence
  controls, strict bounded numeric/date parsing, exceptions, timezone and until.
  Calendar rule start follows event fields and rejects second-fold/subminute starts
  without changing one-off timestamps. Existing recurrence values survive metadata
  edits and frozen-payload retries. Calendar task links validate fresh assignees;
  actual HA accepted full recurrence/link edits and preserved them on a rename,
  keeping child approval/private publication boundaries. Calendar reminder TTL stays
  fixed at five minutes; the ineffective shared catchup control is hidden there.
  RU/UK mobile recurrence editors were inspected, their single-column layout fixed
  and explanations collapsed. Browser tests exercise failed network retries and
  explicit recurrence disable. Invalid hidden controls cannot block a disabled rule.
- Routines snapshot ordered steps per assigned member. Manual confirmations require
  the current run revision and fresh step nonce; other members and future steps
  are rejected. Conditions use only owner-approved HA entities and fresh reports;
  stale/unavailable/future observations remain unknown even under negation. The
  adapter reads last_reported, not last_changed, and does not persist raw readings.
  Parents have reasoned override/cancel, global modes and localized starter templates.
  Escalation waits from actual step activation, sends once to parents and closes
  announced incidents without penalties. Recurrence/date dedup, disabled module,
  revoked roles, Store faults and retained nonces are tested. Actual HA exercised
  authenticated WebSocket commands, real state reports, the Telegram callback
  handler/replay and entry reload. RU mobile ordered editing/failed-payload retry,
  UK child successive nonces and owner allowlist validation passed in Chromium.
  Visual review moved the current step ahead of templates and collapsed settings.
  An actual-card refresh regression is covered: successful commands clear drafts,
  failed ones retain the same operation/payload. Routine steps neither actuate
  devices nor substitute for independent wake-up challenges. Steps may now hand off
  to another active non-guest member; runs snapshot that assignment. Only the current
  assignee receives the private step notification and may confirm it. Participants
  see shared steps, but not another person's nonce or observed HA conditions.
  Any participant/source revocation cancels active runs. Historical command receipts
  recheck module and run authority, including batches, rather than returning a stale
  active nonce after revocation. Notification dispatch rechecks its persisted claim
  and current recipient before transport begins; an in-flight network request cannot
  be recalled. Real HA verified child-to-parent handoff, redaction, authorization,
  replay and reload. RU editor and UK child view were visually inspected.
  The template skip editor now provides modes, approved entity states, time windows,
  negation and nested all/any groups, with strict depth/node budgets. It preserves
  typed values/focus, prior rules on a rename and children when changing all/any.
  Unsupported fields require explicit replacement; current allowlist permission is
  revalidated at save. Node tests cover disabled/stale/detached events and malformed
  rules. Chromium exercised a nested RU frozen retry, UK time rule/clear and revoked
  entity refusal; mobile screenshots were inspected. Actual HA accepted a nested
  rule and preserved it on a metadata-only edit. Advanced per-step conditions still
  have only the existing simple editors and preserve unedited API rules.
- Calendar commands use durable revisions and replay; child edits require renewed
  approval. Participant-only records are absent from unrelated members and group
  `/calendar` replies. Preparation reminders target participants/escort, expire
  after five minutes and do not flood after downtime. Shared confirmed events
  reach a read-only HA calendar only after explicit owner opt-in; revocation clears
  live state without claiming to purge Recorder history. Actual HA tested this
  gate, private filtering, date types, read-only services and Store reload. Recurrence
  expansion has bounded scans, UTC elapsed duration, gap skipping and first-fold
  selection. Card edits preserve original timestamp offsets/seconds unless changed,
  require a choice for newly entered folded times and reject stale identity/drafts.
  RU mobile creation/publication and UK child editing were checked in Chromium;
  recurrence/task links are now editable in the card with replay protection.
- Ruff lint and formatting passed.
- Real HA smoke: Config/Options Flow, owner-linked authenticated service,
  entity setup, explicit siren opt-in, actual siren service parameter validation,
  continuous renewal, alternating tones, answer stops sound, Store reload/unload.
- Real HA Telegram options, group and private enrollment, owner confirmation,
  addressed mention reply, receipt-backed task reply context, duplicate update and unauthorized-command rejection:
  passed with a synthetic Telegram client and no network access.
- Real HA WebSocket authentication, household listing, owner/child projections,
  unknown-user isolation and rejected child mutation passed over container-only loopback.
- End-of-week calendar computation, natural assignment/rescheduling, durable
  interpretation replay and denial after role revocation are covered by tests.
- RU/UK/EN setup guides explain own-bot setup, identity confirmation, current
  limits, wake-up testing and delivery uncertainty. Card editor lists authorized households.
- Mobile Ukrainian wake-up and Russian shopping screenshots visually inspected.
- Court cards provide original score reasons and task/wake-up IDs, current-week
  totals, prior weekly reports, manual awards, appeals, reasoned reversal and
  resolution, including previous appeal history. Children see only their own
  records. Optional independent review requires another active parent/owner and
  cannot be bypassed via direct reversal. Weekly summaries are opt-in, use the
  household calendar week and selected boundary, survive restart and never reset
  balances or issue penalties. Downtime produces at most the latest completed
  period; old snapshots stay unchanged after later corrections. Half-open dates,
  DST gaps/folds, historical zones, duplicate records, Store faults and replay are
  unit-tested. Telegram `/stats`, `/week`, `/award`, `/appeal`, `/reverse` and
  `/courtresolve` use the same authorized ledger. Actual authenticated HA WebSocket
  tested three actors, stale revisions, review guards, replay and scheduler output;
  Store reload retained the resolved appeal and report. RU mobile configuration,
  UK child appeal, independent review and stale-form recovery passed in Chromium.
  Visual inspection found and fixed squeezed mobile summary labels; a geometry
  regression assertion now protects the heading. No physical or Telegram effects
  were performed against the running household.
- Parent-defined privileges snapshot their name, description and cost when
  requested. Requested/approved promises reserve points; fulfillment spends the
  reservation; rejection, cancellation, expiry and refund release it without
  rewriting court scores. Concurrent requests cannot double-spend. Negative
  balances after score correction remain visible as debt. Catalog revisions,
  eligibility, active roles, lifecycle/history, expiry across disabled modules,
  Store faults and replay are unit-tested. Telegram `/rewards`, `/wallet`,
  `/rewardadd`, `/reward` and `/rewarddecide` share the same engine and permissions.
  Actual authenticated HA WebSocket tested reservation, insufficient funds,
  forbidden child approval, parent approval/fulfillment, replay and Store reload.
  RU mobile catalog edit/failed-payload retry, UK request/approval/history and
  stale focused revisions passed in Chromium. Screenshots were visually inspected;
  mobile catalog spacing and short price labels were corrected. Privileges do not
  execute router, siren or arbitrary device commands. Provision is a parent's
  recorded confirmation, not a hardware observation.
- Recurring duty creation/rotation is browser-tested on mobile; the real HA
  scheduler generated one ordinary task instance. Daily, weekly, monthly,
  exclusions, DST, bounded catch-up and Store faults are unit-tested.
- Due reminders, parent-review exemption, one penalty per task, pending-alert
  supersession and paired closure after sent/in-flight/uncertain notices are tested.
- Task cards expose checklists, accept/start/report, review/return, edit,
  cancellation confirmation and collapsed final-task history. Creation and editing
  use the household zone, reject DST gaps and require an explicit fold choice;
  unchanged deadlines retain seconds/microseconds and their original offset.
  Failed saves retain a frozen payload. Stale focused editors check refreshed
  revisions and roles. Same-assignee edits keep progress; reassignment preserves
  prior reports and supersedes old queued assignment/review notices. Strict series
  revisions and optional-setting/creator/occurrence preservation are tested.
  Actual HA WebSocket exercised checklist/edit/replay/report/review/completion;
  Store reload retained it. Russian mobile creation/edit and Ukrainian reports
  were browser-tested and visually inspected. Photo transport is still pending.
- Recurring purchases are separate shopping records, not tasks. Parent-only
  schedules support daily/weekly/monthly recurrence, time zones, exclusions and
  bounded catch-up. Open or partially purchased items from the same series suppress
  new duplicates; unrelated manual items are untouched. Revoked creators and
  inactive/guest buyers cannot generate new purchases. Strict revision checks,
  storage failures, restart/replay and actual DST gaps/folds are unit-tested.
  RU/UK/EN card creation/edit/enable/disable is implemented; browser checks cover
  mobile creation and clearing a buyer/exclusions. Failed saves retain draft data
  with a stable retry payload. Household changes clear private drafts. The real
  HA scheduler generated exactly one approved purchase and Store reload retained it.
  The Russian mobile recurring-purchase form was visually inspected.
- Shopping duplicate merge requires a parent, explicit selected sources, strict
  revisions for every item, matching units/metadata and approved open status.
  Quantities are conserved at six-decimal precision; original source records and
  append-only history remain. Merged recurrence provenance is followed through
  chains, so an unfinished merged item still suppresses the next occurrence.
  Archive cannot destroy that provenance. Existing records without history work;
  malformed history is rejected without overwriting it. Actual HA merge/replay and
  Store reload passed. RU/UK/EN cards include partial purchase, review/confirmation,
  failed-payload retry, history pagination and a collapsed archive. Russian merge
  review and Ukrainian partial purchase were browser-tested and visually inspected.
  Telegram supports partial `/bought` and omits merged/finished items from the active
  shopping list. Non-finite command data is rejected before persisting interpretation.
  Late command responses cannot replace another household's status or drafts.
- Real HA model options/fallback, persisted nonblocking Telegram inbox, proposal
  confirmation buttons, authenticated Assist and actor/session receipt context passed.
- Mobile Russian model-plan confirmation visually inspected; no command before confirmation.
- Real HA bounded LLM tools, actor-private phrase learning and authenticated
  dashboard chat passed. Anonymous tools and unlinked chat users are rejected.
- Mobile Russian conversation/learning card visually inspected.
- Real HA RouterOS options, credential scope, registry MAC matching, parent-only
  inventory and preservation of the last good data after failure passed with a
  synthetic REST transport. Mobile Russian network card visually inspected.
- Real HA selected-lease preview/confirmation/application/read-back, replay and
  private result notification passed. Transport uncertainty, disk interruption,
  scoped compensation and concurrent user-edit preservation are unit-tested.
- Private legacy family-only suite: 397 tests passed.
- Real HA Kid Control adoption, parent Telegram confirmation/replay, native-guard
  template verification, private result and expiry closure passed with synthetic transport.
- Native hAP ac / RouterOS 7.24.2 acceptance used only new synthetic profile/device
  records through pinned SSH. Pause, resume, schedule, rate, grant and autonomous
  one-minute expiry passed; all test records were removed and existing profiles,
  services, DHCP, VRRP and schedulers compared unchanged. No real client was blocked.
  Duration rendering and native `disabled=yes/no` assignment regressions were
  found by native tests and added to the test suite. This is not a REST-wire or
  end-to-end traffic claim; the isolated CHR checks below cover those separately.
- Native CHR 7.20.1 in QEMU/TCG with Docker network disabled verified HTTPS/CA REST,
  a dedicated limited account, real DHCP discover/offer/request/ack, dynamic-to-static
  conversion/comment/read-back/replay and all implemented Kid Control modes. Fresh
  bidirectional routed IPv4 UDP verified pause/resume and temporary modes; a separate
  unbound control client remained reachable during blocks. Both one-minute modes
  expired without HA. An orderly VM reboot ended a 30-minute grant early, restored
  the prior paused state and removed its two timers. No household packets or credentials
  were used. Rate configuration was checked, not throughput, IPv6 or FastTrack behavior.
- Native REST uncovered exact error-shape regressions: absent `wireless` is HTTP 400;
  permission denial can be HTTP 500 with `not enough permissions (9)`. Both now have
  bounded, narrow classification tests. On CHR 7.20.1 the limited account needed `api`
  in addition to `rest-api`; localized setup/error guidance records that observed caveat.
- Mobile Russian Kid Control review and Ukrainian child-only schedule were checked.
- Kid Control now projects configured allowed/blocked status, the next permission
  change, remaining allowed minutes and verified temporary-mode expiry. The
  schedule calculator covers midnight, UTC/local inputs, both DST folds and
  subsecond instants at spring transitions. Stale/future inventory, clock mismatch,
  unmodeled turbo schedules, pending effects and unverified expiry return unknown.
  A deadline alone never claims that the router restored its prior configuration.
  Telegram and the card localize this projection in RU/UK/EN and use the household
  time zone. The card rejects an expired/malformed validity deadline. Historical
  weekly hours remain visible without treating old paused/disabled flags as live.
  Real HA tested the projection after a verified grant and its freshness limit;
  the Russian mobile child view was visually inspected.
- Routed-packet fixtures now verify Ethernet/IP endpoints, header checksum,
  lengths and non-fragmentation in addition to ports and the fresh nonce. The
  hardened fixture passed a complete isolated native RouterOS run.
- No production family module, Telegram bot or siren has been changed. Existing
  router configuration was preserved during the explicitly authorized reserve test.
- Public development repository created at Wave-is/home-assistant-family-assistant.
- All five GitHub check jobs passed on handoff checkpoint 1b91ca4 (run 34057944480).
  The separate native RouterOS CI also passed (run 34040076386). Its first run
  had timed out downloading the official image; bounded download retries fixed
  that infrastructure issue. Every device effect rechecks authority after
  persisting intent. The calendar checkpoint passed the actual HA CI job too.
  The initial
  Python CI import-path difference was fixed with an explicit pytest root.
- No public release, migration or HACS default submission yet.

Transport caveat: a timeout after Telegram accepts a message cannot be deduplicated
with sendMessage. The outbox marks it uncertain and does not blindly resend;
operator review/Repairs and explicit duplicate-aware retry are implemented. A successful siren
service call does not prove physical sound or volume.

## Next work

1. Extend language/context coverage and the LLM/search cascade; keep calendar
   calculations and authorization deterministic.
2. Complete module controls, localization and automatic card resource registration.
3. Complete recurrence, reports, rewards and module parity, then LLM/search and
   extended family modules. Keep all unmet rows visible.
4. Extend native fault/IPv6/FastTrack topology coverage, richer Kid Control
   modes and fail-closed unknown-client controls. Hardware tests require explicit
   authorization, synthetic targets, exact pre-state and scoped cleanup.
5. Add release CI/privacy scanning, migration/shadow verification and only then
   a tested release and controlled production cutover.

## Open engineering gates (not release-ready)

- Some controls are still API-only: advanced alarm exceptions/delay fields,
  task-series editing and advanced per-step routine conditions.
- No real bot has been contacted during development tests. Poller restart/Telegram
  conflict scenarios need further integration tests before the live cutover.
- Archive/retention strategy, comprehensive module health and migration are pending.
- Live model evaluation is pending; local Ollama was not reachable on its default
  port during this checkpoint. No server was started or production provider changed.
- Test every frontend/API flow with actual HA WebSocket transport, not only fixtures.
- All original vision modules and acceptance scenarios remain the goal.
