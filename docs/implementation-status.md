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
| Tasks, deadlines, reports and reviews | In progress / unit-, browser- and HA-tested | Checklist/lifecycle/editor, household-zone deadline, text and private verified photo reports, review/return/archive, strict recurring edits; legacy parity and complete media lifecycle pending |
| Court, rewards, penalties and appeals | In progress / unit-, browser- and HA-tested | Reversible ledger, independent appeals, weekly snapshots; privilege catalog/reservations/parent approval/fulfillment/refund; advanced automatic consequences pending |
| Alarms and durable fresh challenges | Implemented / unit- and HA-tested | Two stages, renewed siren, fresh nonce, expiry, DST, exceptions, penalty cap; physical sound check pending |
| Own Telegram bot and onboarding | Implemented / HA-tested with synthetic transport | Options, polling lifecycle, owner-confirmed enrollment, mentions, replay/roles; live Telegram acceptance still pending |
| LLM, search, command repair | In progress / unit- and HA-tested | Own Ollama/fallback, bounded plans, confirmed mutations, SearXNG snippets and standard Assist entity; real-model eval, full article fetching and external agent delegation pending |
| RU / UK / EN | In progress | Existing forms/cards/errors translated; Telegram/docs and future modules pending |
| Today and module cards | Fourteen cards browser-tested | Today/shopping/tasks/court/alarms/conversation/network/health/calendar/routines/pantry/meals/school/maintenance; richer editors and other module cards pending |
| Family calendar | In progress / unit-, browser- and HA-tested | Private event projection, child approval, date-only/timed agenda, recurrence/task-link editor, preparation reminders, opt-in read-only HA calendar; production acceptance pending |
| Routines | In progress / unit-, browser- and HA-tested | Ordered durable runs, per-step handoffs, private confirmations, overrides, approved observations, three-valued conditions, modes/templates, recurrence and template skip editor; richer per-step editors and production acceptance pending |
| Durable notifications / incident closure | Core unit- and HA-tested | Fanout, retries, quiet hours, uncertainty; Telegram wiring, Repairs and explicit review/retry UI |
| Corrections / journal / local learning | In progress / HA-tested | Explicit actor-private phrase dictionary, fresh parsing and authorization; developer patch loop pending |
| Pantry and household stock | In progress / unit-, browser- and HA-tested | Manual stock, minimum/expiry projection, private parent notes, reviewable low-stock and meal shopping proposals, opt-in private expiry reminders, consent-controlled dietary notes and localized cards; extended media/providers pending |
| Weekly meals | In progress / unit-, browser- and HA-tested | Parent drafts/publication, strict weekly/ingredient validation, private history, reviewed shopping transfer, private dietary section and optional read-only Mealie v3 source with manual candidate review; production provider acceptance pending |
| School | In progress / unit-, browser- and HA-tested | Parent-reviewed timetables, private homework using ordinary tasks, reviewed backpack routine starts and opt-in private preparation reminders; reviewed imports and reminder retention health pending |
| Maintenance | In progress / unit-, browser- and HA-tested | Private equipment/warranty/consumables, authorized faults backed by private tasks, recurring service reuse, manual repair history and card; media/documents and production acceptance pending |
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

## Verified checkpoint, 2026-09-07

- 1685 Python tests passed, with 2 POSIX-specific CLI tests skipped on Windows (domain, adapters, outbox, Telegram, model/search isolation, language/context, recurring tasks/purchases, task editing, shopping merge/history, court periods/review, reward wallets/requests, calendar/privacy/reminders, routine conditions/handoffs/replay authority/private commands and incidents, pantry stock/proposals/strict revisions/expiry reminders/dietary consent, weekly meal plans/reviewed shopping transfers/Mealie source, school timetables/homework/preparation/private reminders/replay/privacy, maintenance/private task receipts/delivery, private media authority/real-file faults/decoder/HTTP/replay, network inventory/lease/Kid Control effects and status, lab fixtures, public contracts).
- 303 frontend unit tests and 117 Chromium browser tests passed. After a fixture
  correction distinguishing a lost committed response from an actual Store refusal,
  all 6 media browser cases passed again with unchanged action assertions.
- Private task photo reports now use an opaque versioned reservation, raw bounded
  authenticated upload, isolated Pillow 12.3.0 JPEG/PNG/WebP validation, immutable
  blob publication and a separate atomic task submission. Current actor, assignment
  epoch, module, task/media revisions and exact retained reference are checked
  before/after I/O. HA admin alone is not family authority. Parents can explicitly
  load retained history; children cannot read an earlier assignment's report.
  Text reports retain their existing contract. Media does not enter Telegram,
  model/search input, notifications, diagnostics or public static paths.
  The complete isolated actual HA suite tested authenticated upload/download for
  all three image formats, decoded rather than hinted MIME, exact submission,
  denial after revocation, real Linux decoder execution and Store/blob integrity
  after reload. An initial helper call accidentally omitted `await`; it was fixed
  and the entire HA suite rerun before claiming reload acceptance.
  The RU/UK/EN card has local-only selected-file preview, explicit upload/submit,
  exact lost-response retry, explicit-only private downloads and Blob URL cleanup.
  Revoked/stale/error views hide private DOM and old asynchronous completions cannot
  clear a newer user's draft. RU narrow upload and UK submit-retry screenshots were
  visually checked. Original EXIF is retained and clearly disclosed, not stripped.
  Public privacy checks reject the private data directory, temp names, opaque blob
  basenames and non-brand image files. Two-phase pending expiry is implemented;
  stale temp/orphan recovery, permanent tombstone capacity, backup barriers,
  retained-report purge, maintenance documents and School imports remain gates.
  AGY's read-only review exposed the subprocess cancellation cleanup gap, fixed
  with spawn/reap regressions. A later review confirmed a crash-only hard-link/temp
  residue issue for the upcoming recovery slice; normal cancellation cleanup and
  exact-body Store-failure retry were independently checked, not assumed broken.
  See [task guide](tasks.md) and [media design](media-design.md).
- School preparation reminders default off and need both an owner-selected global
  household-local time/day policy and an exact actor-private subscription. Parents
  subscribe only their own recipient, children only their own timetable. Creation
  has a five-minute window, current actual lessons and a usable pinned routine;
  missed windows are not replayed. The first DST fold is used once; gaps are
  skipped. Stable per-recipient/timetable/day markers prevent edit/re-enable spam.
  The outbox stores only IDs, revisions, date, expiry and policy fingerprint.
  Private EN/RU/UK rendering resolves current names and bounded materials only at
  send time, never family broadcast or automatic routine/task/device/point changes.
  Quiet hours/retries cannot extend delivery past the first lesson. Both claim
  and post-persistence dispatch recheck source, identity, subscription and expiry;
  the production adapter injects a live clock sampled after lock acquisition, so
  earlier waits cannot retain the old tick time. A newly active quiet period
  returns the unsent claim to pending; an in-flight request is not recalled.
  Store failures, batches, replay/restart, stale Options, recipient isolation,
  delayed claims/expiry and quiet-hour races passed real domain/adapter tests.
  The named review card preserves exact pre/post-commit retries and clears revoked
  drafts. RU narrow review and UK child views were visually inspected; shared
  checkbox CSS was corrected without relaxing viewport tests. The complete isolated
  actual HA Options/WebSocket/scheduler/Store suite passed after live-clock
  hardening. Its synthetic Telegram rate-limit test now advances the injected
  clock explicitly and restores production time afterwards; passing a future
  tick no longer overrides the production live clock. The first test-helper edit
  had an out-of-scope function reference; that fixture error was corrected and
  lint plus the entire HA suite rerun successfully. AGY's read-only review
  identified the lifetime 10,000-marker cap as a retention/health release gate;
  claimed DST/replay/transaction bugs were ruled out against the actual Engine
  and existing adversarial tests. The first photo-report slice is described above.
- School homework is explicitly created by parents or the current child subject
  as an ordinary private task with a zero-penalty deadline policy. Parent edits
  use the School route, not generic task reassignment. Same-identity edits retain
  progress; a reviewed identity rebind resets current lifecycle and hides the
  prior report/review from the child while preserving parent-only history. A
  source-version oracle across children's lesson IDs is blocked. Failed Store
  writes/batches, concurrent exact retries, module/role/epoch revocation, private
  first/replay receipts, group/model exclusion and reload are tested. Materialized
  homework survives timetable archive/School disable in the Tasks lifecycle.
  Explicit backpack starts delegate to existing routines and store one opaque
  timetable/date-to-run marker. The actual school day must be today/tomorrow,
  with current member, timetable and usable pinned routine versions. A second
  operation cannot start that same preparation again; unrelated active runs are
  never adopted. Private history reports the actual run status, not completion
  inferred from a start. Actual HA authenticated Options/WebSockets and reload
  passed. Routines-disable correctly cancelled active fixtures; the smoke test
  now explicitly starts a new ordinary run for its final nonce-persistence check
  and compares the exact run Store rather than an obsolete fixed count.
  RU mobile named homework review and UK own-child view were visually inspected.
  Localized deadlines retain exact unchanged DST instants; actor/module/entry/
  timezone changes revoke focused drafts; pre- and post-commit failures retain
  the exact reviewed request where authority still permits it. AGY's bounded
  documentation review identified ambiguous receipt wording, which was corrected;
  its conditional history-leak concern is ruled out by real projection/replay
  tests. School preparation notifications and imports remain subsequent work.
  Browser fixtures now freeze their school-day clock and model current source/
  replay authority and identity-reset post-state; added cases exercise those
  boundaries. A full run exposed a blank older meal fixture: its trace records
  `net::ERR_NO_BUFFER_SPACE` while loading an imported module. The test server's
  default HTTP/1.0 created separate loopback connections per asset. Switching
  only this loopback test server to HTTP/1.1 enables connection reuse; all 104
  cases then passed with unchanged assertions/timeouts. No OS networking or
  household services were modified.
- Maintenance records parent-reviewed equipment, warranty, notes and consumables;
  explicitly reportable/current responsible scope controls fault creation. Faults
  create one ordinary private task. Service schedules reuse task recurrence,
  checklist, review and reminders, with zero initial penalty and current source/
  member/approver versions. Retiring equipment stops future generation, not already
  materialized work; manual historical service logs remain possible. No stock,
  orders, device actuation or safety certification is implied. Generic series edits
  cannot bypass maintenance approval. Current-role private projections, first/replay/
  batch receipts, reassignment history and model previews are regression-tested.
  Outbox dispatch rechecks task authority after its durable claim; exact incident
  pairs preserve an announced overdue closure even after a newer incident starts.
  Actual HA Options, authenticated WebSocket, scheduler/replay, transport revocation
  and Store reload passed without contacting household devices or Telegram.
  The RU/UK/EN card covers full named reviews, strict pinned links, frozen retries,
  stale service re-review, retired equipment logs and focused-DOM revocation.
  RU mobile edit/review and UK child report were visually inspected; redundant
  headings/help were collapsed and review paragraph spacing tightened. AGY review
  helped align the browser fixture's projections and required payload fields with
  the real backend. Photos and documents still require the shared media work.
  See [maintenance guide](maintenance.md).
- School stores parent-reviewed full-replacement weekly timetables with strict
  member/record versions, dates, non-overlapping lessons, materials and exceptions.
  Children receive only their own current identity-bound timetable and 14-day
  household-local agenda; other adults/guests receive none. Parents retain archive
  history. The optional current-version backpack link does not start a routine.
  Stale links require explicit removal or replacement, never silent clearing on a
  title edit. Frozen retries recover opaque committed receipts after target changes
  while still enforcing current actor/module/entry authority. Actual HA Options,
  authenticated WebSockets, negative permissions and final Store reload passed.
  RU mobile edit/review and UK child views were visually inspected. Two older
  browser cases initially timed out on blank fixture pages, passed in isolation,
  then the complete 80-case run passed with four workers and failure tracing.
  No assertions/timeouts were relaxed and no cause is inferred from that retry.
  This initial timetable checkpoint did not start preparation; explicit handoffs
  are now covered above. School-specific reminders, media imports and a HA calendar
  remain pending. See [school guide](school.md).
- Optional Mealie v3 uses owner-configured private options and fixed bounded GETs;
  bearer tokens are not prefilled, returned in views or reused for another URL.
  Parents explicitly search/select and correct missing ingredient quantities/units
  or remove unsupported rows. Servings never scale quantities. A named frozen
  review creates one ordinary private one-meal draft with an exact retry ID;
  no stock, shopping, source instructions or dietary data is copied automatically.
  Displayed Options bind source/member revisions; success and failure recheck
  authority and source after transport. Revoked owners receive no private form,
  stale errors reveal no old provider state, and stale forms cannot re-enable a
  disabled source. Real authenticated HA Options/HTTP/WebSocket tested these
  races, strict validation, privacy, disable/token-clear and reload. In the
  network-none lab only the HA session lookup uses an owned real aiohttp loopback
  session because multicast DNS has no interface; parser/auth/HTTP remain real.
  Mobile RU correction/retry and UK review were visually inspected. A global
  fieldset layout collision was corrected. No real Mealie deployment was contacted;
  this validates the documented v3 contract, not every Mealie version.
- Dietary profiles are isolated local records with manual likes/dislikes/avoid labels
  and an optional allergy note, not a safety assessment or ingredient classifier.
  Adults manage their own initially private profile; other parents receive read-only
  access only after explicit consent. Current member versions bind that consent,
  preventing role round trips or a member edit between review and execution from
  granting unintended access. The access command freezes both profile and member
  revisions. Parent-managed child records retain their management provenance; role
  changes never expose formerly self-managed adult notes. Clear removes current
  content but retains a versioned tombstone against stale recreation; no claim is
  made about erasing backups or previously read information.
  Opaque receipts keep notes out of audit/processed results, outbox, Telegram,
  LLM/search, entity attributes, diagnostics and meal/shopping records. Strict
  versions/limits, replay, Store failure, batches, concurrency and revocation are
  tested. Actual HA exercised separate identities, consent/revoke, role roundtrip,
  membership change before execution, real ReadFamily and diagnostics/entity
  canaries, and private Store reload. The additional synthetic adult required an
  explicit four-member fixture assertion; the first run's old count was corrected.
  The card freezes exact named reviews and operation IDs, discards revoked drafts,
  and forces private DOM refresh even when an unrelated form has focus. RU mobile
  review and UK child screenshots were inspected; duplicated old profile values
  beneath the review were removed. See [dietary profile guide](dietary-profiles.md).
- Pantry expiry reminders are owner opt-in (off by default, lead window 0–30 days).
  The scheduler creates at most one reminder per item revision after 09:00 in the
  household timezone, only for positive active stock within the recorded date window.
  Private linked parents receive only the item name, recorded date, ID and revision;
  notes, quantities and group chats are excluded. Quiet hours remain effective.
  Source edits, zero stock, archive, module/policy revocation and a narrowed lead
  window supersede unsent work; authority is checked again after the durable claim.
  Already sending/sent/uncertain requests cannot be recalled. Marked revisions are
  not recreated after policy changes, and expired backlog is not emitted.
  Dates are manually recorded facts, not a food-safety assessment. Stock, shopping
  and penalties remain unchanged. Store faults, reload, fanout and race cases passed.
  A second synthetic actual-HA household exercised real Options schemas/owner access,
  authenticated commands, clocked scheduler dedup and persisted markers after reload.
  Russian mobile policy and Ukrainian child-redaction screenshots were inspected;
  the card explains policy without introducing a second configuration endpoint.
  See [expiry reminder guide](pantry-expiry.md).
- Published menus now have parent-only shopping calculation and reviewed acceptance.
  Required ingredient totals are grouped by normalized name and exact unit, with
  active stock and remaining pending/approved shopping subtracted using decimals.
  Positive shortfalls are explicitly rounded up to shopping's 0.001 minimum; exact
  shortfalls and zero lines remain visible, and unlike units are never summed.
  Acceptance rechecks the source version and relevant record fingerprints, creates
  only approved shopping-list entries with provenance, and never deducts stock,
  places orders or copies private notes. A plan ID has one accepted/covered transfer
  for its lifetime; later amendments are manual. Module/role revocation, stale and
  malformed versions, concurrent requests, Store faults, replay after restart and
  batch rollback are tested. Actual HA WebSockets verified changed coverage refusal,
  recalculation, acceptance, child redaction and persisted receipts after reload.
  Real FamilyCard tests verify frozen named review and operation IDs even when an
  intervening section command replaces its pending fingerprint. RU mobile review
  and UK terminal/child views were visually inspected; duplicate review lines were
  removed and historical receipts collapsed. An initial browser startup timeout
  was not reproduced in the isolated scenario or a fresh full 63-case run; no
  assertions were relaxed. See [menu shopping guide](meal-shopping.md).
- Weekly menu drafts are parent-managed under the pantry module, with one published
  plan per canonical Monday week. Editing a published plan returns it to a private
  draft; archiving preserves history and requires a reason. Entries have strict
  date/slot/servings/ingredient budgets and manual total quantities; stock and
  shopping are not changed. Guest/inactive/child/adult permissions, strict current
  versions, concurrent dedup, receipt replay after revocation, Store faults and
  batches are tested. Actual HA WebSockets exercised publication, child redaction,
  stale edits and exact replay; reload retained the final published menu. Menus
  are not added to LLM input, group Telegram output, diagnostics or entity states.
  Root review and real-card tests fixed module-alias gating, real checkbox/date
  types, stale focused forms, lost-response cleanup, private draft revocation,
  named frozen review, literal-null markup and silent date replacement. The
  independent renderer tests alone did not establish these contracts. Localized
  history labels and mobile ingredient layout were refined after visual review.
  Russian mobile editing/publication and Ukrainian child screenshots were inspected;
  the oversized remove-meal button was corrected and the full browser suite rerun.
  See [weekly menu guide](meals.md). Consent-controlled manual preferences are
  covered above; recipe providers remain pending. No allergy-safety assessment
  is claimed. Reviewed shopping linkage is described above.
- Existing shopping/task/court/alarm/member edits now require strict current
  revisions. A shared validator rejects missing/malformed versions; read-only
  Context lookups remain distinct from explicit null. Member edits cannot silently
  create a new identity from an invalid ID or restore privileges from a stale form.
  Telegram freezes the interpreted command's visible version before execution;
  replay does not rebase it. Model plans use the inference input's view rather than
  a newer record observed after generation. Concurrent inference/update, stale
  persisted plans, unchanged state/storage on refusal and old receipt replays are
  regression-tested. Actual HA exercised two concurrent member Options Flows:
  a stale privilege change conflicted; fresh displayed values allowed an intentional
  retry without changing bindings, schedules or timezone. Producer fixtures were
  updated explicitly; no engine/test wrapper auto-fills revisions. See
  [command version contracts](command-revisions.md). No historical data was migrated.
- Pantry records keep manually entered quantities/units, a minimum, optional expiry,
  category/location and parent-private notes. Quantity or unit corrections require
  reasons; unit relabeling does not convert stock. All five existing-record actions
  reject null, boolean, float, string and out-of-range revisions. Tick creates only
  revision-deduplicated proposals, never purchases or stock changes. Parent acceptance
  rechecks current stock and exact-unit open shopping coverage, then adds only a
  shopping-list record without private notes. Replays, permission/module revocation,
  persistence failures, atomic batches and restart are tested. The expiry projection
  uses the household date supplied by the HA WebSocket adapter, not a freshness or
  safety inference. RU/UK/EN cards preserve focused drafts, show the exact item/amount
  before confirmation and retry the identical operation after committed-but-lost
  responses. Child views hide notes/proposals; adults only correct counts. Russian
  mobile editor, Ukrainian child view and English review were visually inspected.
  Actual HA exercised authenticated actions, scheduler dedup, private views and
  Store reload. General options now preserve unshown module flags and expose routines
  and pantry. Expiry alerts and private dietary profiles are covered above;
  automatic orders are not claimed.
- An actual-HA privacy test falsely rejected legitimate timestamps containing
  `02:11` as a MAC prefix. It now checks complete synthetic identifiers and forbidden
  fields, with positive leak-detection and real-projection timestamp regressions.
  The complete isolated HA smoke passed after this correction.
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
- All five GitHub check jobs passed on handoff checkpoint 1b91ca4 (run 34057944480)
  and condition-editor checkpoint 9c03f54 (run 34058895807), then pantry checkpoint
  e0ae29e (run 34060586354) and strict-command revision checkpoint
  544ac8c (run 34061803612), followed by weekly menus
  161b4d5 (run 34062734832) and menu shopping transfers
  657540d (run 34063962083), then expiry reminders
  ad3fd17 (run 34064991218) and dietary profiles
  cd9cae8 (run 34066055297) and Mealie recipes
  59e6eeb (run 34067804708), then school follow-up
  8d25ac0 (run 34069706131), and maintenance
  659e1ed (run 34071531113), and School homework/preparation
  61229b3 (run 34073656489), then private school reminders
  bc130a1 (run 34075063864). The school feature's first actual-HA CI run exposed
  a fixture race with scheduled pantry reconciliation; the follow-up drains
  pending HA work before the explicit clock pass and verifies scheduler health.
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

- Legacy pending plans without required revisions need explicit review during
  migration; do not silently rebase an old instruction to current household records.
- Some controls are still API-only: advanced alarm exceptions/delay fields,
  task-series editing and advanced per-step routine conditions.
- No real bot has been contacted during development tests. Poller restart/Telegram
  conflict scenarios need further integration tests before the live cutover.
- Archive/retention strategy, comprehensive module health and migration are pending.
- Private media still needs bounded stale temp/orphan recovery, capacity health and
  tombstone retention, coherent backup/restore and explicit retained-content purge.
  A crash after exclusive publication but before temp unlink can leave two hard
  links; current reads/expiry refuse that ambiguous state until recovery is added.
- School reminder lifetime marker retention must avoid replay after clock rollback
  and expose capacity health; the present 10,000-marker bound is not release-ready.
- Live model evaluation is pending; local Ollama was not reachable on its default
  port during this checkpoint. No server was started or production provider changed.
- Test every frontend/API flow with actual HA WebSocket transport, not only fixtures.
- All original vision modules and acceptance scenarios remain the goal.
