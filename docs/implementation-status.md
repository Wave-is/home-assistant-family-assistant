# Implementation and acceptance matrix

The product vision remains the scope. Status is explicit: planned, implemented,
unit-tested, HA-tested, hardware-tested, released. These are distinct gates.
Nothing is production-ready solely because a mock test passes.

| Requirement | Implementation | Verification / remaining gate |
| --- | --- | --- |
| Clean public source and HACS structure | Test prereleases published | Available for isolated evaluation; not a stable production/migration release or HACS default-catalog inclusion |
| Atomic persistence, idempotency, roles | Implemented / unit-tested | Disk faults, concurrent replay, revoked identities, batch rollback |
| Multiple households / member administration | Implemented / HA-tested | Config/options, four generic templates, time zone, aliases and bound HA identity |
| Separate shopping model | In progress / unit-, browser- and HA-tested | Partial purchase, approvals, recurring items, explicit merge, metadata add/edit review, per-item history and archive; optional exact purchase prices passed authenticated HA/reload. GTIN/manual entry, recurring preservation and local camera scanning unit/browser-tested; authenticated barcode/history/Store reload passed. Native Assist PCM/STT/spoken review passed in alpha.35 candidate. Photo recognition and real speech/camera acceptance pending |
| Tasks, deadlines, reports and reviews | In progress / unit-, browser- and HA-tested | Checklist/lifecycle/editor, household-zone deadline, text and private verified photo reports, review/return/archive, strict recurring edits; self-only reminders and private replies. Parent-reviewed bulk completion/cancellation/archive passed actual authenticated HA atomic rollback, replay and reload; released alpha.32; reviewed independent multi-member assignments released alpha.33. Legacy parity and complete media lifecycle pending |
| Court, rewards, penalties and appeals | In progress / unit-, browser- and HA-tested | Reversible ledger, independent appeals, weekly snapshots; privilege catalog/reservations/parent approval/fulfillment/refund; advanced automatic consequences pending |
| Alarms and durable fresh challenges | Implemented / unit- and HA-tested | Two stages, renewed siren, fresh nonce, expiry, DST, exceptions, penalty cap; physical sound check pending |
| Own Telegram bot and onboarding | Implemented / HA-tested with synthetic transport | Options, polling lifecycle, owner-confirmed enrollment, mentions, replay/roles; live Telegram acceptance still pending |
| LLM, search, command repair | In progress / unit-, browser- and HA-tested | Own Ollama/fallback, bounded plans, confirmed mutations, SearXNG snippets, standard Assist entity and explicit bounded public-article reading; scoped ordinary chat and exact retries verified; real Qwen evaluation identified schema/day/quote fixes, broader model acceptance remains; explicitly bounded existing official HA Ollama agent/native identity gate passed in the alpha.34 candidate |
| RU / UK / EN | Implemented / unit- and contract-tested | Existing forms/cards/errors translated; 975 keys in full parity across strings.json and translations/*.json; Telegram messages full parity across EN/RU/UK; strict precondition reason selectors added |
| Today and module cards | Seventeen cards browser-tested; automatic resource HA-tested | Today/shopping/tasks/court/alarms/conversation/network/health/calendar/routines/pantry/meals/school/maintenance/polls/presence/digests; ownership-safe Lovelace registration, module-graph versioning and offline HACS install/upgrade tested; richer overview and live provider acceptance pending |
| Family calendar | In progress / unit-, browser- and HA-tested | Private event projection, child approval, date-only/timed agenda, recurrence/task-link editor, preparation reminders, opt-in read-only HA calendar; production acceptance pending |
| Routines | In progress / unit-, browser- and HA-tested | Ordered durable runs, per-step handoffs, private confirmations, overrides, approved observations, three-valued conditions, modes/templates, recurrence, template and advanced per-step condition editors; production acceptance pending |
| Durable notifications / incident closure | Core unit- and HA-tested | Fanout, retries, quiet hours, uncertainty; Telegram wiring, Repairs and explicit review/retry UI; network watch incident lifecycle with cleared notification unit-tested |
| Corrections / journal / local learning | In progress / HA-tested | Explicit actor-private phrase dictionary, fresh parsing and authorization. Owner-opt-in technical Telegram job counts and deidentified report review/download tested. Private pending-proposal rejection notes, atomic retry, scoped purge and card/Telegram controls unit-, browser- and actual-HA-tested. Anonymized semantic reproducer and developer patch queue pending |
| Pantry and household stock | In progress / unit-, browser- and HA-tested | Manual stock, minimum/expiry projection, private parent notes, reviewable low-stock and meal shopping proposals, opt-in private expiry reminders, consent-controlled dietary notes and localized cards; extended media/providers pending |
| Weekly meals | In progress / unit-, browser- and HA-tested | Parent drafts/publication, strict weekly/ingredient validation, private history, reviewed shopping transfer, private dietary section and optional read-only Mealie v3 source with manual candidate review; production provider acceptance pending |
| School | In progress / unit-, browser- and HA-tested | Parent-reviewed timetables, private homework, reviewed backpack starts, opt-in private preparation reminders, exact terminal retention and counts-only Repairs; explicit one-week HA calendar draft import tested; photograph import and household acceptance pending |
| Maintenance | In progress / unit-, browser- and HA-tested | Private equipment/warranty/consumables, authorized faults backed by private tasks, recurring text/photo service completion, manual repair history and card; separate initial fault images and parent-only equipment documents passed authenticated upload/read/purge/Store-reload in actual HA; document release gates and production acceptance remain |
| Polls | Implemented / unit-, browser- and HA-tested | Private ballots, fresh confirmations, Telegram private replies, aggregates and explicit archive/purge; older archive pagination and production acceptance pending |
| Presence | In progress / unit-, browser- and HA-tested | Independent display and notification-purpose self/guardian consent, HA read permission, source lineage, fresh/unknown evidence; durable bounded private return-home holds/expiry/catch-up tested in actual HA; household acceptance remains |
| Digests | Implemented / unit-, browser- and HA-tested | Off-default owner schedule, self-only subscriptions, private send-time content, exact replay, quiet hours/expiry and retained-period anti-replay floor; optional independent presence-gated private delivery; household acceptance remains |
| MikroTik inventory / HA matching | Implemented / unit-, HA- and native-tested | HTTPS/CA options, bounded tables, registry MAC/current tracker evidence, ambiguous/stale handling and parent-only card; native CHR REST inventory passed |
| Static leases / comments | Implemented / unit-, browser-, HA- and native-tested | Native DHCP exchange and conversion/comment/read-back/replay; two-target native permission failure, exact static compensation, uncertain dynamic conversion response, selected DHCP recovery and unchanged sentinels passed; broader fault/topology acceptance remains |
| Kid Control including Telegram parents | In progress / unit-, browser-, HA- and native-tested | Profiles, hours/rate, temporary modes, private outcomes and timers; native CHR REST/expiry/restart passed. Learned IPv6 directional rejects observed; raw accelerated traffic can bypass pause. Focused no-outbound-leak gate passed only after fixture-owned FastTrack withdrawal/selected expiry, not a runtime mitigation. Richer modes/topologies remain |
| Unknown clients / allowlist | Local audit and private discovery unit-, browser- and HA-tested | Protected/approved/unreviewed bounded inventory; owner-reviewed source-bound local records and private parent reads. Opt-in self-only discovery subscriptions, bounded baseline/quiet batching, source/identity revocation and RU/UK/EN card; actual authenticated HA delivery/withdrawal/reload passed. Strict enforcement hard precondition gate implemented (9 reason codes, owner-only evidence, 30-day expiry, 17 unit tests); topology + IPv6 + local rollback prerequisite for enforcement documented |
| Diagnostics / Repairs / backup / migration | In progress / unit- and HA-tested | Counts-only diagnostics/health, media recovery, coherent Store/blob copy, admin-confirmed failed-release Repair; native encrypted Core restore and fresh authenticated bootstrap passed in isolated HA 2026.8.2; HAOS restore and migration remain pending; no live legacy data modified |
| Release CI and secret checks | Implemented / CI-tested | alpha.35 runtime ZIP/tag verified at 8ffe6889; all nine Checks jobs (34261542830) passed, including fresh-process copy resume, encrypted restore and offline actual-HACS install/failure rollback/upgrade. Live HACS bootstrap and legacy migration remain pending |
| Existing-home migration and verification | Read-only copy/preparation wizards, staging and sealed registration HA-tested | Native source-pair upload, explicit participant/reviewer selections, three original photo submissions, deterministic packaging and separate sealed ConfigEntry passed. Same-package retry retains ID/time/exact Store. Reviewed residue preservation released alpha.30; indexed discovery/direct resume released alpha.31. Fresh-process restart acceptance passed on the exact alpha.31 runtime. No blank writable fallback. Coherent real capture, index retention/cleanup, activation and controlled cutover remain pending |

## Immediate v1-pre execution queue (2026-09-09)

1. **Live Telegram acceptance on real user/channel**
   - Current status: implemented as synthetic transport only.
   - Next: execute read/write flow with a real group and parent chat.
   - Required evidence: actual-HA acceptance tests for mention/reply, duplicate handling,
     replay and restricted command denial.

2. **Live physical-device critical checks**
   - Current status: alarms and shopping media are HA-tested, but physical verification
     is still marked pending.
   - Next: explicit acceptance gates for siren audibility and photo/reportability
     under representative device conditions.

3. **MikroTik strict enforcement policy — COMPLETED 2026-09-09**
   - Implemented: `network/strict_preconditions.py` — `check()`, `record_evidence()`,
     `public_status()` with 9 reason codes.
   - Routing in `network/plans.py`, `network/admission.py`, `domain/engine.py`.
   - Evidence recording with actor auth, revision conflict guard, 30-day expiry,
     backend-identity binding, and capacity limit (max 5 backends).
   - `authorize_replay()` for `mikrotik.network_record_strict_evidence` in engine.
   - 17 unit tests: all pass. Strict reasons in EN/RU/UK translations.

4. **Close critical incident lifecycle — COMPLETED 2026-09-09**
   - Implemented: `network/watch.py` tick() now tracks open/closed incident state
     in `state["incidents"]` (key `network_watch:{member_id}`).
   - Closure notification `network_watch_cleared` sent when all pending devices
     reviewed and at least one discovery batch was previously dispatched.
   - EN/RU/UK `network_watch_cleared` strings added to `telegram/messages.py`.
   - All 42 existing watch tests pass without regression.

5. **RU/UK/EN documentation parity — COMPLETED 2026-09-09**
   - `telegram/messages.py` MESSAGES dict: full key parity across EN/RU/UK.
   - `translations/*.json`: 975 keys, complete parity across EN/RU/UK.
   - `strict_precondition_reason` selector with all 9 reason codes in EN/RU/UK.
   - `strings.json` matches `translations/en.json` exactly (verified by contract test).

Completion rule for v1-pre: no item moves to v1-rc without a matching reproducible
test or proof in the table above and in corresponding release artifacts.

Items 1 and 2 (live hardware/Telegram) remain as the only open v1-pre gates.

## Strict preconditions and incident closure candidate, 2026-09-09

Alpha.36 closes the software prerequisites for `v1-pre`: MikroTik strict enforcement
precondition gating, network watch incident lifecycle with closure confirmation,
and complete RU/UK/EN localization parity.

The MikroTik strict gate enforces a hard precondition matrix (module active, topology
evidence within 30 days, backend match, verified IPv4/IPv6 rules, FastTrack bypass
accounted for, management hosts excluded, restart recovery verified) before strict
mode can be activated. Evidence recording is owner-only, bound to the router backend
hash, expires in 30 days, and is validated by replay authorization in the Engine.
View projection exposes `strict_available` and machine-readable reason codes.

Network watch tracks unreviewed devices as explicit incidents: opening upon new
discovery, persisting while unreviewed, and closing with a localized `network_watch_cleared`
notification across EN/RU/UK when all devices are reviewed. Unannounced quiet-hour
incidents close silently if resolved before quiet hours expire.

Trilingual parity reaches 100% across all 975 translation keys (`strings.json`,
`en.json`, `ru.json`, `uk.json`) and all Telegram message templates, verified by
contract tests. Full Python test suite passed (4,653+ passed, 5 skipped, 23 subtests).
Deterministic alpha.36 packaging verified (271 files, 983,833 archive bytes, SHA-256
`2b78531e3cc71ffd93254536dc7f208b8b5a6e5a78b50e7bef06259be4e530e3`).
[Release notes](releases/0.1.0-alpha.36.md).

## Spoken review candidate, 2026-09-08

Actor/session-scoped proposal references now survive native reload and allow exact
spoken EN/RU/UK confirmation or cancellation without a second model call. Native
speech presents the review instruction instead of requiring an opaque ID. New
turns clear old session refs while retaining their own frozen request context;
late earlier replies cannot overwrite a newer turn. Domain authorization,
five-minute expiry and child purchase approval are unchanged.

AGY54204 supplied actual-Engine contract tests; root reviewed, reran87PASS and
added in-flight/failed-turn regressions. Focused115PASS. Native34251 passed real
authenticated PCM/STT/intent in all three languages, native reload/Store,
outsider/session denial, cancellation and child approval. Only recognizer/model
outputs were synthetic; no live audio accuracy or household acceptance is claimed.
The first native28369 failed a fixture's missing ConfigEntry.subentries_data;
the fixture was corrected without changing the production API. Full Python30107
passed4636/five skips/23subtests; full native61270 passed all gates including
voice/native agent/copy/restore. Node85363 passed450 and Chromium90299 passed244.
Ruff580/privacy/locales and deterministic alpha.35 packaging passed. Exact final
commit/CI/release gates remain pending. [Voice setup](voice-shopping.md).

## Existing Home Assistant agent released, 2026-09-08

Alpha.34 adds an off-default, separately reviewed native provider slot before
unchanged direct Ollama primary/fallback. Only the exact official Ollama entity
on Core2026.8.2 is supported, with no native control API and default prompt.
Opaque target/client/config proofs and persistent entry/subentry binding protect
selection; request-local actor context is carried through plan, quote, search
and article calls. Revoked authority does not continue to another provider;
unlinked users may use configured direct providers without globally cooling down
the HA provider. [Setup and limits](ha-conversation-agent.md).

AGY26111 supplied an initial draft; root replaced permissive/invented native
interfaces and implemented the wizard. Further implementation assistance stalled
or timed out; no unverified output was merged. AGY95889 read-only review's
subentry.options and unassigned-result claims were checked against actual Core
and exception flow; neither was reproducible. Root added cancellation/error tests.
Native checks first exposed unknown last activity and an unnecessary direct
HTTP/DNS session in the network-none fixture; both causes were diagnosed and fixed.
Focused native38169 and extended86917 passed actual official entity/stream parsing,
reviewed Options, proposal/confirmation, child context and private projection,
inactive/unlinked denial, Store/reload/off and unsolicited-tool-call denial.
Full native41835 also passed. Full Python66825 passed4544/five skips/23subtests
before two final exception regressions. Node2704 passed450; Chromium10612 passed244.
Final Python74383 passed4546/five skips/23subtests; focused118 passed, explicit
Node pretests189 passed. Full native21923 repeated every gate including extended
child/privacy/reload/off acceptance. Ruff575/privacy/locales and deterministic
alpha.34 runtime packaging passed. Initial a6dc027 failed only hassfest's missing
optional Ollama declaration. Final f2a371c adds after_dependencies and a packaging
regression; full native7975 and all nine Checks34258915209 passed. Published tag
0.1.0-alpha.34 points to f2a371c9d625a15b41121eb3eeaa1de74eb72a50; its269-file
runtime ZIP is976900bytes, SHA256
71b4d8cf18afb1a16a027f4ec79f21cf06f8adcd22083dcf2812b1938f6b498d.
No household deployment or support for arbitrary third-party agents is claimed.

## Independent multi-person assignments released, 2026-09-08

Alpha.33 extends one-off task creation with explicit parent selection of 1–20
members, a complete review and confirmation. Each receives its own task/report/
checklist and optional penalty policy; this is not shared completion. The existing
atomic batch creates all or none. An optional reviewed assignee revision is checked
under the Engine lock; older unpinned callers remain compatible. Separate frozen
request IDs survive uncertain replies even after another card command. Personal
reminders stay self-only. [Workflow](task-multi-assignment.md).

AGY33928 supplied bounded read-only design; AGY26685 implemented only the owned
form and two Node test files. Root implemented backend revision guards,20 domain
tests (including queued member updates, failed persistence, independent reports/
penalties and replay), actual authenticated HA acceptance, browser fixture/tests
and shared-card wiring. Python31519 passed4420/five skips/23 subtests. Native6056
passed the full HA suite including separate assignment/Store reload and unchanged
other child's task. Root Chromium99290 reproduced two form defects missed by Node
mocks: unrelated real-card success hid uncertain creation and direct rerender
retained the previous actor's review. Root fixed both, member-role pending guards,
wall-time/UTC Back separation and localized review copy. Chromium47404 passed8;
full93604 passed244 including a real DST second-occurrence Back check.

Root then reproduced and fixed shared command finalization clearing a newer
generation's busy state; focused form tests pass20. Full Node70535/28266 passed450
plus186 pretests before that additional regression. Review forms no longer show
an unrelated empty task list/archive below the form. Final general checks and
independent AGY93002 review followed. Its wall-time/autofill mismatch and retained
confirmation after closing were reproduced and fixed (22 focused Node tests).
Its managed-task/privacy claims were independently investigated by AGY52782,
then verified by root: the actual Engine already blocks generic school revision,
private/photo receipt replay after reassignment and non-parent audit access.
Six real-Engine regression tests retain those boundaries without runtime changes.
Final Node90331 passed 450 tests; pretests passed 189. Chromium56621 had one
fixture-load timeout (243 passed), focused52694 passed 13, then complete79975
passed all 244 without changing the affected poll fixture or weakening assertions.
Native27695 repeated the full actual-HA gate successfully. Root visually inspected
the final Russian mobile review. Final Python91148 passed 4426 tests, five skips
and 23 subtests. Ruff (567 files), privacy, locale parity and deterministic runtime
packaging passed. All nine Checks34249784758 passed exactfa76da3; the alpha.33
tag and deterministic ZIP match that frozen commit. No household deployment.

## Reviewed task batches released, 2026-09-08

Alpha.32 adds a parent-only Tasks-card flow for up to 20 ordinary shared tasks.
The user reviews exact selected records before separately confirming one atomic
completion, cancellation or terminal archive. Personal and specialized-module
tasks retain their own forms. An uncertain request retains its original operation
ID and revisions even after another card command; changed identity/member binding
invalidates the old review instead of silently rebasing it. Mobile review uses
readable task tiles, with record versions in a separate disclosure.

AGY52795 implemented the isolated panel, copy and initial 14 Node tests. Root review
and Chromium12563 independently reproduced three stale uncertain-retry defects
(actor revision, assignee revision, reassignment). Root fixed them plus detached
start/review scope checks; Chromium13183 passed all nine focused cases. Root added
six further Node regressions and wired the test file into npm's release gate.
Native85627 passed the full synthetic HA suite, including actual authenticated
batch rollback on one stale item, child denial, one commit/audit step, unchanged
sentinel, exact replay after runtime reload, complete/archive/cancel. The final
native71335 repeated the full HA gate successfully. Full Python11808 passed4400,
five skips and23 subtests; Node69178 passed450 and final pretests passed174.
Chromium19008 passed234 and caught one obsolete table selector after the tile
redesign; root corrected the selector, and complete Chromium50480 passed235.
The RU mobile review was visually inspected. Ruff562/privacy/locales/runtime
build passed. AGY46629 independently found that real maintenance tasks use private
delivery scope without a managed-by flag. Root confirmed the actual projection,
excluded private/source-marked work on selection and uncertain retry, and added
actual-HA maintenance creation/projection/sentinel coverage. It also found the
already-fixed obsolete browser selector and a no-op revision-change unit test;
root made that test exercise a real subsequent change. Complete Chromium99707
passed235 after the privacy filter. Final native2495 passed including real
maintenance projection/sentinel (root corrected an invalid warranty test fixture).
Final npm64951 passed450 plus175 pretests, including21 batch tests. All nine
Checks34244678284 passed exactcadaa9b. Alpha.32 tag and deterministic runtime
asset match the frozen commit; no household deployment.

## Indexed copy resume released, 2026-09-08

Only final-confirmed attempts enter a bounded immutable native Store index before
staging starts. The original active administrator-owner can discover this prototype's
attempts through EN/RU/UK Options. Complete native state and photo blobs are rebuilt
through actual converters against the indexed original summary and exact bytes.
Separate fresh confirmation registers the same sealed ID, not another household.
Partial/drifted/unindexed copies still require the original bundle. No automatic
startup action or index eviction. [Workflow and limits](legacy-copy-resume.md).

Root index/flow/scope tests passed 77. Hardened native27980 passed the full synthetic HA suite,
including interrupted complete staging, lost review/runtime reload, owner discovery
and photo reconversion without reupload, child denial, false confirmation, exact
same-ID registration/replay and unchanged source/index/Store. AGY implemented the
index core and hardened it; root independently repaired fixture membership, added
runtime/authority read-boundary tests and strict bounded record/photo validation.
Full Python72864 passed 4379 tests, five skips and 23 subtests; Node90116 passed
450 tests plus 154 pretests; Chromium46500 passed 226. Independent read-only AGY77761
review found no additional material defects. Ruff (556 files), privacy, locale
parity and the runtime build passed. All eight Checks jobs34237980964 passed exact
3b09a80. Alpha.31 tag and runtime asset match the frozen commit; no deployment.

A separate two-process acceptance gate passed after this release (native9439).
Actual HA creates durable synthetic auth/config/Store state, exits the first HA
process, then resumes in a fresh process without any review/candidate in memory.
The hashes-only contract does not supply raw source or candidate objects. Fresh
owner confirmation loads the same sealed ID with zero workers, child denial and
exact replay; source/index/intents/media remain unchanged. Runtime SHA256 matches
the released alpha.31 asset. This proves graceful process restart, not power-loss
atomicity or activation. Runner unit tests passed 31 with one platform skip; full
Python passed 4398/five skips/23 subtests before the last two runner regressions.
Ruff/privacy/locales/build passed; all nine Checks jobs34240668570 passed exact
acceptance-only commit9f6532d. No new runtime release was needed for that commit.

## Interrupted copy preservation released, 2026-09-08

Separate EN/RU/UK consent preserves recognized temporary photo uploads before
removing their temporary names and retrying the same sealed copy. Authority,
candidate, native staging intent/Store and filesystem identity are rechecked.
Unknown files, external links, drift and registered targets fail closed. Native
Store journals retain prepared/completed attempts for exact acknowledgement-loss
retry; archives stay private and retained. [Workflow and limits](legacy-recovery.md).

Root implemented the HA wrapper and Options path; AGY implemented the bounded
filesystem helper, followed by root review and a second AGY hardening pass. Focused
wrapper/flow tests passed48. Native93755 passed the complete synthetic suite,
including partial upload/publication hardlink, separate consent, interrupted
journal, durable-plan reload, unchanged Store and same sealed registration.
AGY9811 hardened capacity/manifest/archive boundaries; root then fixed multi-alias
unlink retry accounting and revoked-authority failure projection. Full Python15829
passed4333/five skips/23 subtests, Node25093 passed450 plus154 pretests, and complete
Chromium63963 passed226. Hardened native91546 passed the full HA suite. Independent
AGY85360 read-only review found no additional material issues. Ruff549files,
privacy/locales/build passed; all eight Checks34232293825 passed exact3ce1284.
Alpha.30 runtime ZIP and tag were verified against that commit.
No automatic startup cleanup, source coherence, activation or household change.

## Private proposal notes released, 2026-09-08

Current pending, unexpired proposals can be explicitly rejected with an actor-private
category, expected intent and optional byte-exact original request. Note and rejection
commit together; exact retry, failed Store, purging, account revision, capacity and
corrupt-storage boundaries are covered. No automatic teaching, execution, developer
sharing or anonymization is claimed. Private Telegram only; generic plan cache does
not receive another raw-text copy. Dashboard includes EN/RU/UK review and explicit
purge, preserving failed-write drafts and discarding revoked identity drafts.

AGY implemented the pure module and tests, followed by independent root review and
extra malformed-role/sequence fixes. Host Python4268/five skips/23 subtests passed;
Node450 plus154 pretests passed. Three focused native Chromium flows passed. Full
native HA77517 passed authenticated child-only note/replay, original hash mismatch
denial, unchanged shopping/learning, parent non-disclosure, complete Store reload and
explicit owner-denied/child-approved purge. Full Chromium47008 passed226 checks;
independent AGY80956 read-only review found no further material issues. All eight
Checks jobs34227319295 passed exact commit771ec38; alpha.29 ZIP/tag verified.
Only active proposal rejection is covered; arbitrary answer feedback, anonymized
semantic reproducers, developer patch queue and old-identity retention remain open.
[Scope and limitations](semantic-feedback.md). Live household untouched.

## Optional technical report released, 2026-09-08

Owner consent is off by default and generation-bound. Fixed technical categories
from queued Telegram model job failures are aggregated in the same completion/
outbox transaction; no text, IDs, timestamps, URLs, private hashes or raw health
state are exported. EN/RU/UK Options and Health-card preview/fresh local download
are implemented. No automatic sharing, semantic reproducer or generated patch
execution is claimed; [boundaries and workflow](developer-diagnostics.md).

AGY's pure-module and API work was independently checked against actual Engine/
CommandScope contracts. Root corrected malformed/duplicate bucket handling,
generation limits and SemVer, then tested exact Store/response-loss retries.
Native54677 passed the new path; the later old personal-task equality test raced
with its synthetic clock. Draining that scheduler before unchanged-denial checks
made full native21319 pass. Host full Python4142/five skips/23 subtests and
Node450/146 passed before one additional post-commit consent-race regression.
Chromium verified exact downloaded JSON bytes and review invalidation.
Exact alpha.28 commit33d22f2 passed all eight Checks34223795544 including the last
post-commit consent guard regression. Tag and ZIP digest were independently verified.
Running household installation unchanged.

## Guided private package preparation released, 2026-09-08

The EN/RU/UK Options path accepts two explicitly selected source exports, then
requires exact participant, complete old reviewer and historical image choices.
No automatic name/permission inference occurs. Historical report actors and
assignees needed by conversion cannot be offered archive-only. Unknown additional
reviewer IDs can be supplied explicitly. Deterministic packaging joins the
existing final association/fingerprint review and sealed registration; no source
exporter or activation is implied.

Full Python3979/five skips/23 subtests and Node450/141 passed before the final
independent-review regressions. Native45793 passed two source uploads, two member
choices, two complete reviewer sets, three photos, sealed copy, exact repeat and
discard preserving the existing copy/intent, plus the full HA suite. AGY10338
identified overly permissive archive choices and cancellation-held idle slots;
root checked the actual conversion/writer contracts and added fixes. Focused63
passed afterward. Final Python3990/five skips/23 subtests and full native8231
passed with the final guards. All eight exact-commit Checks34219419802 passed;
alpha.27 tag and runtime ZIP digest were independently verified.

## Cross-ledger source checks and packaging candidate, 2026-09-08

Whole-copy construction now rejects one-sided automatic Court/task/alarm effects,
duplicate/malformed receipts, historical-assignee mismatches and unfinished score
corrections. A deterministic bounded private ZIP writer reuses the independent
parser; it does not capture files or grant permissions. The wizard has a specific
RU/UK/EN source-consistency error. Complete capture coherence remains unproven;
pruned alarm history outside the current Court period is explicitly archive-only.

Full Python3935/five skips/23 subtests and Node450/141 passed. The exact alpha.25
synthetic whole-copy seal is unchanged by the new guard. Native private
legacy-controller82589 passed Court-first commit refusal, idempotent completion of
the missing rollover without a duplicate minus, deterministic ZIP roundtrip and
actual reversal/acknowledgement. Public native17272 passed the complete HA suite,
including orphan-penalty upload refusal and zero Store/entry effects. Exact release
CI is still pending. The two earlier native failures were invalid fixture API
sequences (unaccepted task; correction on a no-report task); the corrected fixture
uses actual parent-reviewed task contracts. No production records were operated on.

## Private copy wizard released, 2026-09-08

The native Options flow consumes a bounded private ZIP through HA file_upload,
requires paged exact member/reviewer/photo associations and a separate final
counts/hash confirmation, then creates an isolated sealed read-only entry. A
private immutable intent keeps the original ID/time for exact-file/unchanged-
target retries. Explicit discard releases only the review, never the existing
copy or saved retry intent. The source prototype and old installation stay intact.
Bundle preparation and coherent source capture remain operator-assisted.

Full Python3876/five skips/23 subtests passed, including bounded ZIP central/local
header checks, authority revocation at persistent boundaries, settled cancellation,
nonce replay and review discard. Node450/141 passed. Native HA47301 passed real
authenticated upload, two-page review, three historical photos, sealed creation,
same-bundle retry and unchanged prototype. Native6521 then passed the full suite
including discard-preservation cases. All eight Checks34212564006 passed on
41546e28; alpha25 tag and runtime ZIP digest/size were verified. No production rollout.
Three additional locale tests ensure abort text is in HA's actual Options abort
section rather than only the similarly named error catalogue.

## Native shadow staging released, 2026-09-08

The internal fresh-entry staging API replays complete source/member/reviewer/photo
conversion before any write. Current active administrator-owner authorization,
target pins and setup/backup coordination guard native HA Store intent and final
publication. Verified blobs precede the one final Store; exact retries do not
overwrite unrelated data or register an entry. Cancellation drains owned writes.
Unknown residues fail closed without deletion; reviewed cleanup remains pending.

Full Python3741/five skips/23 subtests passed, including strict intent-version and
unknown-residue regressions. Focused58 passed before the final intent-version test.
Native full HA65579 passed actual Store/blob staging, exact retry after a lost
acknowledgement following an actual commit, child/registered-target denial, fresh
setup, owner-only historical photo HTTP, zero entities/workers and reload. No
fixture-only blob copying remains in this test. Node450/141 passed; no frontend
source changed. Alpha23 was published from c365837c after all eight Checks34203386117
jobs passed; tag and runtime asset were verified. Alpha24 adds the separate
ConfigEntry seal and registration, verified at71f0f46b in Checks34205977830.

## Reviewed barcodes released, 2026-09-08

Optional GTIN-8/12/13/14 structural validation and canonical metadata flow through
add/edit, recurring generation, merge guards and purchase history. Reviewed RU/UK/EN
forms have manual/HID input and a button-only browser-local camera path; no product
lookup, image upload, guessed name, automatic purchase or child-approval bypass.
Camera permission/detection is scoped to the current form/identity, stops on
cancellation/revocation/hiding and has a one-minute bound. Barcode entry also stops
an outstanding scan; a keyboard scanner's Enter cannot skip the save review.

Python3708/five skips/23 subtests passed; Node450 plus141 pretests passed.
Full Chromium220 passed, followed by nine focused cases including the added
scanner-Enter/manual-override regression. Actual HA78618
passed authenticated barcode add/edit/read, exact replay, invalid-input rollback,
historical purchase codes and the entire shopping Store comparison after reload.
Mobile RU review was visually inspected. Camera browser tests use synthetic local
video and a controlled detector, not a physical device/native-decoder certification.
All eight Checks34201156401 passed; alpha22 tag and asset verified against
68da569a64d151762a1e04c373cad99f8ef46d4b. No production rollout.

## Historical photo evidence released, 2026-09-08

An internal preparation API requires complete owner-matched source event/reference
digests and actual selected bytes. The existing bounded POSIX decoder checks images;
no Telegram lookup or supplied filename is used. Current and prior report rounds
keep their assignee revisions, separate attachments and generation high-water marks.
The whole copy carries private Store metadata AND exact private blobs; archive
replay redecodes all files and checks the frozen mapping. This does not prove image
meaning or create a public import/matching/activation endpoint.

Full Python3682/five skips/23 subtests passed, including26 new cases. The local
Windows suite uses the actual verifier on fixed generated fixtures; the resource-
limited helper correctly refuses Windows. Native HA82355 passed actual bounded
decoding, archive replay, complete Store/blob reload, authenticated owner GET,
child denial and zero workers. Main Node448/122 pretests and full Chromium212
passed; exact committed alpha21 release CI and publication verified at ea5c572e,
eight Checks34198253945 passed. No real source
export or production data changed.

## Whole shadow copy released, 2026-09-08

Pure whole-candidate construction rejects nonempty targets, any blocked source
record and changed reviewer sets. Tasks/reminders retain IDs; all other core IDs
have an explicit private map. Current-week balances and exact source archive replay
are checked. Modules remain off; the persistent read-only data schema blocks every
Engine write lane and prevents older releases from treating a copy as writable.

Actual HA69099 passed whole native Store/reload, authenticated owner-only view,
command/Options denial, zero provider/scheduler starts and unchanged state, before
the final separate-schema downgrade guard. The exact published alpha19 Engine
subsequently rejected that new schema. Full Python3649/five skips/23 subtests and
frontend448 main/122 pretests passed; three mobile Chromium shadow cases passed
and the Russian layout was visually inspected. Final focused actual HA56501 passed
on a newly created shadow entry before any ordinary setup, with zero entity registry
records and no providers. An earlier reused-entry fixture correctly exposed retained
ordinary entity registry records and was replaced by this fresh-target acceptance.
Final Python3656/five skips/23 subtests and full Chromium212 passed. Published
alpha20 at caadea8c86b6bed9388fe589eb578c73395d2e1e; all eight Checks34195267740
passed. Tag/target and runtime archive verified:241 files/3144799 runtime bytes,
ZIP848007 bytes, SHA256
`6d0a88845e7cfa328817fbc7e56e1f1f54e9878b0bd54235b563cf5b77332e6a`.
There is no public import/activation endpoint and no
real source capture, historical-photo resolution or household cutover claim.

## Migration reviewer comparison released, 2026-09-08

The next candidate adds complete declared per-task reviewer-set comparison to the
joined conversion fingerprint. Coverage, designated reviewer, explicit mapping,
duplicates and all current member fields are checked. Per-task differences stay
private; counts do not grant rights. Missing source policy is explicit, not guessed
from previous successful reviews. No live capture, role changes or import endpoint.
18 focused cases plus the legacy conversion/archive subset passed56 tests; the
full Python suite passed3624/five skips/23 subtests, Ruff473 passed. A private,
synthetic-only parity test against the actual old ledger confirmed additional-parent
review behavior. Actual HA87386 passed private source/archive and joined reviewer
policy replay through native Store, with exact restored fingerprints and changed-
binding refusal. Node445 plus122 pretests passed. Published as alpha19 at
55dd1565c277bfd3e2bf2219afb89593a00fdd8c; all8 Checks34192326986 passed. Tag/target
and asset verified:238 files/3118898 runtime bytes, ZIP841146 bytes, SHA256
`37d5bde2fca0dfe22ac9c939c0e6f7c38fe1f65e1e4ef4f02c4103e30bb8b426`.
No source exporter was installed and no live data imported.

## Equipment documents released, 2026-09-08

Alpha.18 candidate adds a distinct parent-private equipment document purpose,
explicit upload/attach/download, owner-only reviewed purge and retained history.
The pinned restricted PDF parser is isolated; task/fault image lanes still reject
PDF. No equipment revisions, service rules, tasks, stock, alarm or court effects.
RU/UK/EN real-card controls have exact uncertain-request replay, revoked-source
guards, download-only Blob links and bounded removed-history pagination.

Full Python passed3602/five skips/23 subtests; Ruff470 and privacy/locales passed.
Main Node passed445; full Chromium209 passed, with four focused document cases and
Russian mobile visual inspection. Later pagination/strict-ID regressions passed
the focused Node suite and are included in the final checks. Actual isolated HA
run81451 passed authenticated document HTTP/WS access, purpose denial, replay,
owner purge and retained private PDF bytes after Store reload.

An initial lab bootstrap rejected QNAP's bonding_masters control file as if it
were a network interface. The helper now counts only actual interface directories;
five synthetic guards verify this does not admit a real interface or capabilities.
No production configuration was changed. Final frozen runtime passed full HA91886.
Published at1dd84a03c3867caeb18aeec99ef8501b4c542d95; all eight Checks jobs passed
(34190052072), including encrypted restore and HACS install/upgrade. Tag, target,
asset size and digest verified: 237 runtime files/3112824 bytes, ZIP839096 bytes,
SHA256 `f6d70a8c0b5a18fe257efcc668a2dc419291d7a86c3c29b8276438bcfd8c4533`.
Final Node445 plus122 pretests passed; four document browser cases reran after final
pagination/strict-ID changes. Four local workflow tests now catch YAML command syntax
and accidental placement of binary test dependencies inside the public build source.

## Optional purchase prices released, 2026-09-08

Alpha.17 candidate adds explicit purchase-delta totals and currency, immutable
name/store snapshots and shared-family disclosure. Price is optional and never
backfilled, reused for the remainder, converted between currencies or sent to a
shop. Strict decimal validation, replay, approvals and non-guest purchase roles
are unchanged. Card drafts pin the current actor/source; an uncertain response
keeps the exact operation ID even if the shared pending-command slot changes.

Full local Python passed3566/five skips/23 subtests, Ruff461/privacy/locales passed;
frontend444 main Node and14 focused price cases passed. Full Chromium passed205
scenarios, including RU/UK/EN mobile price entry and response-loss retry. Russian
layout visually inspected. All106 pretest cases passed after three extra optional-
price regressions. Actual HA authenticated optional-price commands, invalid-input
rollback, shared history, exact replay and complete Store reload passed in full
isolated run86341. The 234-file / 3075598-byte runtime candidate ZIP is827860 bytes,
SHA-256 `003302d769fa36da61f76154a961142379858198311321a9fd93dc53d308f16a`.
Published at57695ffa5b61539179f532ae25dd9b0232a04a23; all eight Checks jobs passed
(34186485298), and tag/target/asset digest and size were verified. Production was
not changed.

## Native topology checkpoint verified, 2026-09-08

Developer-only CHR7.20.1/vmxnet3 tests now distinguish configuration read-back,
round-trip failure and actual outbound delivery. Raw Kid Control with active
FastTrack can still pass traffic; an unsuccessful echo must not be reported as
complete quarantine. A focused run passed no-outbound IPv4/IPv6 checks after
fixture-only acceleration withdrawal and exact selected connection expiry.
The public runtime remains unchanged and makes no new isolation claim.

Two-target native lease compensation passed in a separate full run, including
the deliberately lost response after a real conversion, native permission denial,
selected DHCP recovery and an unchanged unselected sentinel. Pure packet tests
passed88 cases; the full Python suite passed3525/five skips/23 subtests and
frontend444 main cases plus92 pretests. Full unified local run96736 passed; exact
commit d89a048a81791bbdb5ce2630939c784817eee638 passed all eight Checks jobs
(34184754899) and Native RouterOS acceptance (34184755848). The fixture mitigation
is not a public runtime feature. Resume checks deliberately use unaccelerated
routing and do not claim FastTrack restoration acceptance.
See [the evidence and boundaries](network-topology-testing.md).

## Private discovery released, 2026-09-08

Alpha.16 adds self-only parent/owner subscriptions. Current observed devices form
an explicit baseline without initial alerts. New unreviewed MACs are batched;
quiet hours retain pending markers, and durable dispatch gates prevent catch-up
bursts. Source replacement, member epoch, private binding, role and current
freshness are independently checked. An uncertain send is not blindly retried;
an expired one-hour queued intent is not automatically recreated. Capacity stops
require explicit reviewed reset; no router configuration is changed.

The final full Python suite passed 3447 cases/five skips/23 subtests, including
private-channel readiness regressions. The full frontend passed 444 main Node
cases, 92 pretest cases and 201 Chromium scenarios. The new watch Node subset
has 24 passes, including stale-observation status. Russian mobile layout was
visually inspected.
Actual authenticated HA baseline, private TelegramManager delivery, duplicate
suppression, command withdrawal and Store reload passed with no router writes.
Published at `109c25cbc8a9b655be39be6ca4f2e8168d3a9e3c`, all eight Checks jobs
passed (34180711105). The verified 824268-byte ZIP has 232 runtime files /
3066059 uncompressed bytes, SHA-256
`a121d680a0471a8b9aa685142b85d516befc146aab882866239067c9d16877c4`.
See [the three-language discovery guide](network-watch.md).

## Local network review released, 2026-09-08

Alpha.15 adds a distinct local approval ledger, not firewall authorization. HA
matches/comments/static leases do not silently approve devices. Fresh complete
inventory and protected infrastructure anchors bind owner-reviewed plans to actor,
source, policy and observation; source replacement explicitly archives old data.
Parents can read exact unknown-device commands privately without an LLM; group
requests disclose no MAC/IP, and queued details have source/identity/expiry guards.
The real FamilyCard includes a RU/UK/EN mobile review and exact response-loss retry.

Focused Python tests (56), 23 new real-card Node cases and three mobile Chromium
cases passed. Russian mobile screenshot was visually reviewed, including inert
hostile name text. Actual HA authenticated commands, replay, zero router effects,
Store reload and outsider denial passed. The full suite reached 3404 Python passes,
five intentional skips and 23 subtests, plus one later targeted preview-replay
regression; all 444 main Node / 65 then-current pretest and 198 Chromium cases
passed (three extra Node regressions subsequently passed separately). Initial full
suite caught a missing capacity-error translation; RU/UK/EN catalogs were fixed
and the full Python suite rerun successfully. Published at
`05448be7c9d44d30b9510141e1fb52c52df6c0c8`; all eight Checks jobs passed
(34177834134). The verified 810008-byte ZIP contains 228 runtime files /
3013489 uncompressed bytes, SHA-256
`c570b5734b1a188a658fd487ac1fe352bdcdab340fb7211803bad025368fb385`.
See [the three-language guide](network-admission.md) for audit-only semantics,
capacity limits, observed-only card scope and explicitly pending enforcement.

## Independent return-home reminders released, 2026-09-08

Alpha.14 was published at `67fb227ca0f7cc21438da8d3eddff344c90cf853`, all eight
Checks jobs passed (34175077607). The verified 787897-byte ZIP contains 223 runtime
files / 2928995 uncompressed bytes, SHA-256
`2caeefcbfc48f2a950330cd6368b58cc781f19f414df7bbef98052c0c2fd6715`.
Local full suite: 3349 Python cases, five intentional skips, 23 subtests;
444 main Node cases plus 45 pretest cases; 195 Chromium cases and actual HA
authenticated consent/ACL/Store/delivery verification. No production change.

Alpha.14 adds separate, off-default notification-purpose self/guardian consent.
Only selected private nonurgent Telegram reminders can wait for a fresh home
report; dashboard sharing alone never grants this permission. Current HA account,
entity ACL, source/member/approver lineage and runtime are checked. No source state
or coordinates are retained. Explicit wait bounds, expiry, pinned recipients and
one held delivery per person per two minutes prevent stale catch-up bursts.
Alarms, direct replies and group messages retain their ordinary delivery lane.

Actual HA passed authenticated consent, denied-read zero observations, durable
hold/reload, catch-up, expiry and withdrawal using an isolated synthetic entry.
3348 Python tests/five skips/23 subtests passed before one final expiry-on-withdrawal
regression was added; the 18 queue tests then passed. RU/UK/EN real-card consent,
strict numeric input, exact response-loss retries and stale-control revocation
passed22 Node tests and three mobile Chromium scenarios; Russian layout inspected.
AGY Flash High wrote two public-only UI files before its timeout. Root reviewed
them, removed an invented fallback API, fixed fractional parsing/consent checks,
integrated the real card lifecycle and wrote independent tests. Final local checks
passed3349 Python tests/five skips/23 subtests,434-file Ruff/format,444 main Node
tests plus45 pretest tests,195 Chromium scenarios and privacy/locales checks.
Exact final223-file runtime candidate passed the full isolated actual HA suite;
SHA256 `2caeefcbfc48f2a950330cd6368b58cc781f19f414df7bbef98052c0c2fd6715`
(2928995 runtime bytes;787897 ZIP bytes). Exact-commit eight-job CI and verified
tag/asset publication remain the final release gates. No production changes occurred.

## Fault observation photo release, 2026-09-08

Alpha.13 adds a second consumer of the existing bounded private image service.
An open reported fault can reserve/upload one uploader-private image and explicitly
attach it for current parents/reporter/assignee. It never changes the task, outbox,
alarm, routine or court. Owner-only explicit purge with a reason revokes reads at
commit and preserves bounded parent-visible history; a later image does not erase it.
Malformed or incomplete source records withhold the upload grant without breaking
ordinary maintenance/digest projection. Competing uploads cannot replace an attachment.

RU/UK/EN real-card tests cover explicit upload, attach, view, owner purge, exact
lost-response retries, stale/detached controls and identity/module/entry changes.
Four mobile Chromium scenarios passed; Russian layout was visually inspected.
AGY Flash High wrote the new public-only HTTP smoke file before its final-response
timeout; root reviewed contracts, added whole-state no-side-effect checks and a
second image for authenticated Store-reload verification. The first HA run caught
an invalid cross-purpose test request: a photo completion cannot include text.
Removing that field makes the test exercise the intended media-purpose denial.
The complete second HA run passed upload, authorized bytes, denied reads, collector,
exact replay, Store-reload and all other module gates. No household credentials
or production changes involved.

Local3276 Python tests/five skips/23 subtests,425-file Ruff/format, public privacy,
locale checks,444 main Node plus23 pretest and192 Chromium scenarios passed.
Final review added three observed-failing regressions for boolean task, assignment
and asset-source revision pins; all are now strictly validated. The final full
Python rerun passed3279 tests/five skips/23 subtests. Exact-commit eight-job CI
34172370908 and final actual HA run passed. Alpha.13 was published at
43966c09f0d52dd6b86546ecdffd043232b1a0af; the verified218-file runtime ZIP has
SHA256 `b564c24041b423c36fbe5386394e4057210466c658fabaa21be5576bda7a5a8b`
(2867415 runtime bytes;771279 ZIP bytes).

## Explicit guardian presence release, 2026-09-08

Alpha.12 adds `presence.guardian_access_set`; `presence.access_set` remains self-only.
Current active HA-linked parents/owners may explicitly consent for current active
children only, including children without an HA link. Paired guardian identity and
revision pins invalidate sharing and receipt replay after revocation. A linked
child may take over or disable their own sharing. No-op detection includes consent
authority, allowing fresh explicit reapproval, not silent enablement.

The parent-only normalized managed rows carry no entity ID, coordinates or raw
observations. HA source read permissions remain required, and inactive requesting
HA users are rejected before registry/state reads. RU/UK/EN mobile reviews and
stable response-loss retries are tested; the narrow Russian review was visually
inspected. A first browser run caught an incorrect English test label; corrected
to the actual translated label, then all seven presence browser cases passed.
Local3238 Python tests, five skips and23 subtests passed;420-file Ruff/format,
privacy/locales,444 main Node and188 Chromium scenarios passed. AGY's separate
implementation and frontend review timed out without files or usable findings;
root implemented and tested this slice. No production changes occurred.

The initial exact runtime archive has215 files,2835260 runtime bytes and761392 ZIP
bytes; SHA256 `5e47444a2a7aa304046be3977457a400c8892d077487e174f817669e0e6b5e53`.
Actual HA passed guardian transport/read permissions/Store/replay/revocation and
the subsequent module gates, but the global final assertion still expected five
members before the two new fixture identities. The test now compares the complete
pre/post-load identity set and exact saved member records. A full rerun and exact
commit CI are required; no full HA pass is claimed from that initial run.
AGY's no-tool bounded design review completed and emphasized household scoping and
atomic consent checks. Both are existing per-entry Engine/synchronous projection
boundaries, not newly discovered defects or a substitute for actual code tests.

The full rerun on those unchanged runtime bytes passed, including final exact
member-set/Store/reload/unload assertions. Initial CI68138ca passed the actual HA,
encrypted restore, upgrade, HACS installer and Python tests but caught the stale
alpha.11 packaging command. Updated the explicit CI candidate to alpha.12 and
added a local manifest/workflow agreement regression (observed failing before
the fix). The pinned alpha.3 upgrade baseline is unchanged. Final db5bd99 CI
34169788842 passed all eight gates; alpha.12 was published and its tag, ZIP digest
and size verified. This is a checkpoint, not full-vision or production completion.

## Future photo / overdue progress checkpoint, 2026-09-08

Published alpha.11 at `5be34933aa865dde12dc03e4e5eaec4bd9e95765` after all
eight Checks jobs in `34167701159` passed. GitHub tag and asset digest match the
final 24186326 archive below. The earlier initial artifact was not published.

Alpha.11 adds strict proposals for photo-required tasks without any past photo
submission and reconciles overdue activity only from full identity-aware history,
original metadata and matching timestamps. It does not fabricate images, guess
progress or remove an actual source inconsistency. Forty-four fictional cases
generated through the actual private legacy ledger API passed without household
data or production writes. Thirty-one new public cases cover photo requirements,
current-role submission/completion denial, late activity and unresolved history;
the extended native Store fixture covers both new paths. Initial full3205 Python,
440 main Node and185 Chromium cases passed, as did the complete isolated HA suite.
AGY's focused read-only review raised a possible needs-changes inconsistency.
Root reproduced an explicit malformed transition into needs-changes without any
submitted report, then added a failing regression test and the missing history
invariant. Final exact-artifact verification is pending; the earlier artifact is
superseded and must not be published.

Final local3206 Python tests, five skips and23 subtests passed with418-file
Ruff/format and privacy/locale checks. The final runtime archive has215 files,
2826377 runtime bytes and759635 ZIP bytes, SHA256
`24186326c066d8f7ce3456d7d9cd6f8ac98a9c9595e9c49d20243f770cde604c`.
The full final actual-HA run passed on these exact runtime bytes, including
native Store/reload and all existing integration gates. Exact commit CI remains
pending. Frontend source is unchanged from the successful440 main Node /185
Chromium run.

## Task lifecycle checkpoint, 2026-09-08

Alpha.10 was published at `daea228fa09cdc0210bced99dfd04beaa6910b61` after all
eight Checks jobs in `34166470255` passed. Tag and asset digest match the frozen
candidate below. No production update occurred.

Alpha.10 adds verified text-report reassignment chains and separate terminal
notes for no-report tasks and self-only reminders. Former reports remain
parent-only; assignment back never restores an earlier confirmation. Invalid
assignment actors, source state transitions and stale member epochs fail closed.
Twenty-five synthetic cases through the actual private legacy ledger API passed;
no household source was read. Full local3175 Python tests, five skips and23
subtests passed, as did414-file Ruff/format, locales/privacy,440 main Node tests
and185 Chromium scenarios. AGY's assigned test attempt and focused review timed
out without files/results; root implemented and verified this slice.

Exact candidate:214 runtime files,2821105 runtime bytes,758043 ZIP bytes,
SHA256 `f0d531f9fc251f69a7fd93b85c18d57ce7b8c17259e2d48ca1ffcf08870c77d7`.
The complete isolated HA 2026.8.2 suite passed, including exact Store archive
roundtrip and reproducible proposals for reassignment and private terminal notes.
Exact commit CI subsequently passed as recorded above. No apply/import capability,
active transport or production migration is introduced.

## Text report checkpoint, 2026-09-08

Published alpha.9 at `46df777950d2ed58a3df31ec3151b686bfd1d0b0`: all eight
Checks jobs passed in `34164907978`. Exact final tag and asset digest matched the
candidate recorded below. The earlier pending wording records the pre-CI stage;
the final CI did verify the exact-offset and archived-close additions too.

The alpha.9 slice fixes text resubmission history and stale review notes, retaining
submission times and identity stamps. Parent-only RU/UK/EN history paging is
browser-tested, including role revocation and literal rendering. Legacy text
reports now require explicit submission/review history and a current parent
reviewer mapping; ambiguous/reassigned/photo records remain blocked and privately
archived. Eighteen fictional scenarios generated through the actual private legacy
ledger API passed without reading household records or changing production.
The complete actual-HA suite passed report/review/resubmission, Store/reload and
private conversion-archive reproducibility. Final exact-artifact CI is still a
release gate. The first full local run exposed two stale fixture expectations:
the added source report task changed counts, and archived school reports now
include identity/timestamps. Both expectations were corrected, not bypassed.

AGY's read-only runtime review identified the genuine text-history/stale-note
defects. Its helper implementation timed out without files; root authored and
tested the converter. A subsequent AGY review's raw-input/privacy claims did not
account for the validated immutable review or parent projection and were not
accepted as bugs. Its equivalent-ISO-timestamp observation led to preserving the
current source row's exact timestamp spelling after instant equality validation.
Archived completed/cancelled tasks also retain the original close timestamp.

Final local checks:3145 Python tests passed, five host skips and23 subtests;
Ruff/format411, locale/privacy checks;440 main Node tests plus six pretest cases,
185 Chromium scenarios. Exact final candidate:214 runtime files,2817524 runtime
bytes,757480 ZIP bytes, SHA256
`919dbd060ee4d72e704702e7ec7d576edd4d1b80bb022ba6b97b2ce05ad640a6`.
The complete actual-HA gate passed before the final exact-offset/archived-close
preservation additions;155 focused cases and the full Python run cover those
additions, and exact final CI remains required before publication.

## Personal reminder checkpoint, 2026-09-08

Published alpha.8 at `8f7e85484e660e0815558188fd125111264809df`: all eight
Checks jobs passed in `34163195733`. Tag and GitHub asset digest match the exact
candidate below, including final calendar-link refusal. Local final suite passed
3100 Python tests, five skips,23 subtests and182 Chromium scenarios, plus Node,
lint/format, locale and privacy checks. No production cutover occurred.

Alpha.8 adds explicit self-only reminders, not ordinary parent-visible private
tasks. Current identity is enforced on view/mutation/replay, mixed audit batches,
delivery review and Telegram. Other parents/owners, global pending counts,
calendar links and automatic quote/model context cannot expose personal records.
The due event is persisted once, has no court consequence and never falls back
from a missing private enrollment to a parent or group. Legacy reminder proposals
preserve this scope; they do not constitute a whole-home importer.

The complete actual-HA suite passed personal create/complete/archive, current
HA-user deactivation, exact Store reload/replay and a real Telegram-manager private
list reply carrying its persisted no-quote marker. Native encrypted restore and
all five offline HACS phases also passed that reviewed runtime. A final calendar
link refusal was then added and covered by two domain tests and a card test;
the exact final artifact and full eight-job CI remain release gates. Candidate:
212 runtime files, 2803183 runtime bytes, 752959 ZIP bytes, SHA256
`6e4adc7d329731d66965d04282a0d03611ea274010bafafbb580e419dc2d9089`.
EN/RU/UK personal-reminder browser scenarios passed, including self completion;
the narrow mobile Ukrainian form was visually inspected. AGY provided a bounded
read-only privacy review. Its separate implementation attempt timed out without
a test file; root implemented and independently tested the guards. Production
integration, Telegram transports, household records and devices are unchanged.

## Baseline, 2026-09-06

Private legacy project: 401 unittest cases discovered; one unrelated guest-image
test could not import the missing paramiko dependency. The family suite's cases
ran without failures in that invocation. No production code was changed.

Local workstation has Python 3.11 and Node 20. Real HA checks run in a separate
ephemeral HA 2026.8.2 container with network disabled, no production configuration,
credentials, ports or devices mounted. The actual Home Assistant siren platform
is exercised with a synthetic entity, not by replacing its service registry.

## Verified checkpoint, 2026-09-07

Published alpha.5 at `0379cf193a5e9d524d45c0939a794d90d68a39c9`. All seven
CI jobs passed in `34153790263`, including frontend and actual HA. Tag and GitHub
asset digest match the `c7f3d586...` runtime recorded below; 175 Chromium cases
passed locally too. It is still an isolated-evaluation development release.

The published alpha.6 slice joins private task/shopping/court/alarm conversion reviews
and adds a strict exact-source archive codec. 63 shopping/court tests passed;
the full suite at that point passed 2876 tests (five skips, 23 subtests). Archive,
task and joined-review checks subsequently passed 97 tests. AGY delivered task
files before timing out, but root found a failing preflight test and a lifecycle
test that exercised a different record than intended. Root corrected them, added
unhashable-field guards, preserved known lifecycle dates and refused to rewind
progress recorded after a task became overdue. The full joined suite passed 2973
Python tests, five host skips and 23 subtests, Ruff/format (392 files), privacy and
locale checks. Exact runtime ZIP: 207 files, SHA256
`6550342426637df6cfc6b27d0bfc56f00959af6fbd7df901b62e077b7a48e996`.
The complete actual-HA suite passed, including the new private archive Store
roundtrip/source-byte equality/plan reproducibility test. All five offline HACS
install/failed-update rollback/upgrade phases passed this exact runtime against
published alpha.3. All seven jobs in CI `34155811374` passed. The release tag
resolves to `77ab7e5219d893adb418fadb8844750f69a2696b`, and GitHub's asset digest
matches the exact ZIP above. No production data or transport changed.

The next acceptance slice passed all four fresh-process native encrypted restore
phases in an isolated HA 2026.8.2 container against the exact alpha.6 runtime
(`6550342426...`). It prepares synthetic data, creates a protected backup through
HA's real manager, refuses an incorrect key without changing state/restarting,
then requests restore through that manager and checks the actual default Core
restart exit status. A separate process invokes HA's native startup restore before
the final fresh Core bootstrap reads the restored configuration. The fixture
intentionally changes task/auth/Options data after backup and damages a synthetic
blob after shutdown. Exact Store/runtime/blob checks, original access-token HTTP
authentication, authorized private-media download, unauthenticated refusal,
frontend delivery, disabled transports/siren and operation-receipt replay passed.
The restart instruction is consumed once; backup state returns to idle. Fifteen
pure runner tests also passed. The full local suite passed 2988 tests, five host
skips and 23 subtests, plus Ruff/format (396 files), locales and privacy checks.
The native four-phase gate passed again with startup-time service observation.
All eight CI jobs passed in `34157304040` at
`d0757556a0533345d8814654d0fb6c9cfd120bf5`, including native encrypted restore.
This is Core/Container configuration restoration, not HAOS/Supervisor add-ons,
database history restoration, live installation restore or household cutover.

The alpha.7 candidate adds explicit, non-mutating school-calendar week import.
42 pure conversion tests and 12 school card tests passed, as did ten targeted
Chromium scenarios including EN/RU/UK reviewed import and in-flight role revocation.
The mobile UK review screenshot was inspected. The full actual-HA suite passed
with real CalendarEntity, authenticated parent/child/outsider requests, independent
read-permission guard and in-flight HA-user revocation. Concurrent-read and
explicitly confirmed Store/replay acceptance also passed; the full run then found
an outdated fixture assertion expecting four members after this test added a
fifth. The assertion now verifies five and exact full member state across reload.
The full local suite passed 3030 Python tests, five host skips and 23 subtests,
Ruff/format, privacy/locales, 438 Node cases (including six pretest cases) and
179 Chromium scenarios. Exact final runtime candidate: 211 files, 2791985 runtime
bytes, 750124 ZIP bytes, SHA256
`06dbdd47bb43fa3e838b1394e72f39a0d3cdd15ce5712077d2417f8c6e5ab639`.
The complete exact-artifact HA suite, native encrypted-restore gate and all five
offline HACS install/failed-update rollback/upgrade phases passed against the
published alpha.3 baseline. CI/publication are next. AGY's bounded
implementation and follow-up review timed out without files/results; this slice
was implemented/reviewed by root, not attributed to a completed AGY review.

Published alpha.4: real Qwen3.5-9B synthetic evaluation passed 12 cases
after reproducing and fixing envelope, command selection, alarm-day and quote
injection failures. Raw quotes cannot enter planning; their terminal answer pass
cannot return commands. Numeric model days cannot create/change alarm schedules,
and shopping projection retains the actual partial purchase field. The full local
suite passed 2784 Python tests, five host skips and 23 subtests, plus lint/format,
locales and privacy checks. All 175 Chromium scenarios passed, with Node checks.
The exact reviewed runtime passed the complete actual-HA suite, including atomic
two-alarm preview, Store reload and authenticated confirmation/replay. Offline HACS
installed alpha.3, restored it after a failed update, then upgraded to this candidate
and retained the synthetic household data. Runtime ZIP: 201 files, SHA256
`92d1295d05efe912e8357bdb1d79f0e44d5f732e2e1103a5e4697f27d04dae3e`.
All seven jobs in CI `34152121973` passed. The release tag resolves to
`72d5987a0906d1d070ed01ae346aeeff0cd93019`, and GitHub's asset digest matches.
No live cutover is claimed.

The next migration slice adds a pure disabled-alarm proposal. AGY provided an
initial implementation; root corrected target identity revalidation, archive
comparison and the test's confusion between HA user and Engine member IDs.
143 focused migration tests passed, including changed binding/role/revision,
forged reviews, exact decoded archive, absent source buckets, immutability and
real modern Engine payload validation. The complete local suite passed 2813 Python
tests, five host skips and 23 subtests; Ruff/format, privacy and locale checks
passed. The exact alpha.5 runtime passed the full isolated HA suite and five
offline HACS phases (alpha.3 install, prepared data, failed-update rollback,
upgrade, verification). Runtime ZIP: 202 files, SHA256
`c7f3d586d5c266742e1129f232749673d9c46e43affbd71308f19d8b27c16c69`.
The shopping-planner AGY implementation task timed out without delivering files;
it is not a completed review or implementation. This is not a complete importer.

Published test prerelease `0.1.0-alpha.2` at commit
`49c9891c48625d3f62d7baa5c1677a06f1e17e82`. All seven jobs in CI run
`34147012232` passed, including the offline HACS installer gate. GitHub's
asset SHA256 matches the joined runtime below; the tag resolves to the tested
commit. This is an isolated-evaluation prerelease, not household migration.

The next development slice adds strict legacy Store-wrapper decoding with
duplicate-key/UTF-8/JSON limits and immutable source/mapping reviews. Every source
byte and current target member field is pinned. An explicit archive-only actor
can preserve old history without becoming a recipient or gaining a role. Source
coherence is not implied by a hash and no import endpoint is present. 114 focused
review/preflight tests passed. Media diagnostics now also recognize exhausted
byte/pending-upload capacity, not only record ceilings; all 21 retention tests
passed. AGY's narrow read-only review identified the byte-health mismatch; root
verified it and implemented the correction after the implementation task timed out.

The joined alpha.3 development export passed 2620 Python tests (five host skips,
23 subtests), Ruff/format, privacy/locales, the full actual-HA suite and all five
offline HACS install/rollback/upgrade phases. Runtime-only ZIP: 200 files, SHA256
`f46ac492f5ae2a5528991a54eb27883ac7d8a63458cf9d6131cfb48d5935800a`.
Alpha.3 was published at `7930f7e8825de158a2d3facc590f44e40d78a4b5`; all seven
jobs in run `34148532409` passed. GitHub tag and asset digest match. A narrow AGY review
of the new source-review helper timed out; it is not a passing review claim.

Reviewed shopping metadata editing now preserves quantities, partial purchases,
status, creator and recurrence/merge provenance. Category, store, household-visible
note and assigned buyer have strict validation and a named review. Children may
edit only their own pending proposals; these remain pending. Lost replies retain
one exact request even after another command occupies the card's shared slot.
Current member epochs, source revisions and disabled modules revoke stale forms.
Actual authenticated HA WebSockets tested editing, child denial/proposals,
stale revisions and replay; the full Store reload retained shopping data.

Advanced per-step routine skip/completion rules use the same bounded nested
condition editor as template rules. Rule meaning and the minimum observed-entity
requirement are explained in EN/RU/UK. Reordering/handoff retains each rule;
switching to manual completion preserves the draft but explicitly removes the
condition on save. Every frozen routine editor command owns its retry ID; a
focused stale template/run/config form is invalidated on a conflicting refresh.
Old browser fixtures lacking member revisions were corrected to the real view
contract. Root passed 2545 Python tests (five host skips, 23 subtests), all 175
Chromium scenarios, 435 Node tests (including six shopping pretests), Ruff/format,
privacy/locales, and the complete actual-HA suite for the joined runtime.
RU per-step and UK shopping-review mobile screenshots were visually inspected.

The read-only legacy preflight reports fixed counts/issues, not raw family data.
It validates bounded schema-1 inputs, references, schedules, quantities, active
runs and current-week court reconciliation. It is not wired to an import endpoint
and cannot modify either installation. See `legacy-migration.md` for the explicit
mapping, coherent-source and isolated shadow-instance prerequisites.

The offline HACS 2.0.5 installer gate passed for this exact joined runtime,
including registration/install, exact installed bytes, failed-update restoration,
successful upgrade and durable data across fresh HA processes. The installer CI
job subsequently passed for alpha.2. HACS OAuth/update-entity bootstrap is outside this
gate; the specific synthetic boundaries are documented in `hacs-lab.md`.

Joined runtime-only ZIP: 199 files; SHA256
`ce2ab345f2cfcacf12b58e68254c1e4011a5f10d7e24d732ac2722d196fc6c94`.
This runtime is now published as the alpha.2 test prerelease, not a household
migration. The original vision's remaining module/retention/provider/network
and migration gates remain open.

The joined command-scope candidate passed 2464 Python tests, five host skips
and 23 subtests, Ruff/format, privacy and locale checks. The complete actual-HA
suite passed with guarded Telegram commands, background job/provider changes,
Assist and LLM tools, ordinary chat, and generic service/WebSocket execution.
Queued work cannot silently adopt a replacement member or retired runtime.
The exact runtime-only ZIP contains 197 files; SHA256:
`7ffd4df708fb48efdc244d38fce954c63062488111e248be7cda64678a254221`.
The two-process actual-HA application-upgrade gate passed for this exact
candidate too, preserving the synthetic Config Entry, Options and domain data
from the reviewed unshipped alpha.1 baseline. HACS installer acceptance remains
a distinct gate.

Actual-HA testing caught an over-strict post-command check for a legitimate
owner self-profile edit. The exception now requires the exact durable operation
receipt and current result, unchanged role/active status/HA binding, and a fresh
user/runtime check. Altered receipts, later edits and changed authority remain
rejected. Fifteen focused scope tests and the full real-HA suite passed after
the fix. This is a verified development checkpoint, not a production migration.

Dashboard chat now owns bounded asynchronous requests, pins the current member,
provider configuration and runtime, and saves content-free retry context before
interpretation. A lost response can be retried with the original operation and
references, without silently sending a new instruction. The localized card
provides exact Retry plus an explicit new-request reset with an uncertainty
warning. Model plans are bound to the member revision; legacy plans are retained
but cannot be adopted by a replacement identity. Engine writes have in-lock
authority guards, cancellation-safe persistence settlement and permanent
retirement after successful unload.

Root verified 2426 Python tests (five host skips, 23 subtests), 422 Node tests,
166 Chromium scenarios and the complete actual-HA suite on the reviewed dashboard
slice. Actual HA exercised response loss, exact replay after reload, provider
revocation, failed-unload hook preservation and rejection of retired Engine
writes. Its runtime-only ZIP SHA256 was
`fb5f1a314cf42496444f7b9ce5a395a33912ad1e72e6ad8335a34aed1c8ae5f3`.
That dashboard-only checkpoint was subsequently joined with the Telegram,
Assist/LLM and generic HA-command scope repairs verified above.

Explicit article reading is now connected to owner-reviewed Options and the
Conversation card. It remains off by default, with a separate child policy,
reviewed public HTTPS URL, transient answer and verified source link. Full
entry/runtime/member/provider generations revoke in-flight work and unload
settles owned workers. Root verified 410 Node and 161 Chromium scenarios and
visually checked RU review and UK result. The exact runtime passed the full
actual-HA suite, including Options, authenticated WebSockets, policy changes,
unchanged family data, generation revocation and unload. The isolated test uses
a real owned HTTP session because HA's multicast resolver cannot initialize in
a network-disabled container; retrieval/model responses remain synthetic. A
contract test also checks the synthetic model reply against the real schema.

Whole-export checks passed 2347 Python tests, five host-specific skips and 23
subtests, plus Ruff/format/locales/privacy. The separate two-process actual-HA
upgrade gate passed from reviewed, unshipped alpha.1 source to candidate alpha.2:
the same synthetic configuration, Options, tasks, points, disabled alarm and
replay receipts survived. Candidate runtime ZIP SHA256:
`9779a5ce97213e1bbc872d487f3a1a9291fafca4449064452a0e25cbd793d9eb`.
This is not HACS-installed acceptance, a production upgrade, full HA restore or
legacy migration. No release has been published. Review identified ordinary-chat
request lifecycle, stale-authority and lost-response retry defects; the later
joined checkpoint above verifies their fixes separately from this upgrade gate.

The full recurring-task editor now reviews people, recurrence, deadline policy,
report type and checklist in EN/RU/UK. Exact retries preserve the reviewed operation;
harmless refresh preserves typed fields and stale authority detaches controls. Server
lineage pins actor/creator/assignees and suspends stale series without silently
assigning work to a replacement identity. Root verified 400 Node, 156 Chromium and
the complete actual-HA suite; the narrow RU full review was visually inspected.

At the preceding checkpoint, public-article transport and answer-only synthesis
were foundations without a user-facing endpoint. Real synthetic TLS tests
exercise pinned host/address/port/family/protocol, redirect and response limits.
Model input has no family view or source URL; authority rechecks precede fallback
and health changes, completed responses are transient, and concurrency is bounded
even during authority lookup. A deterministic runtime-only ZIP was built from exact
staged source: 187 files; source symlinks/junctions, inventory drift, mismatched
manifest bytes and missing declared local imports fail closed. Whole-export result:
2272 Python passed, four host-specific skips, 23 subtests; Ruff/format/locales/privacy
and full actual HA passed. This is not a published release, a packaged-upgrade
acceptance, a real-model evaluation or existing-home migration.

Automatic post-create guided Options handoff is now included and actual-HA-tested:
the exact loaded new entry, duplicate reuse, manual-flow collision and strict
sentinel work without changing Engine, Options, modification time or runtime.
Per-entry weak locks also protect replacement-runtime races in unit tests.
That checkpoint passed 2172 Python tests (three host skips, 23 subtests).

The complete alarm schedule editor now supports all existing save fields with
named review, current actor/member/source guards and immutable response-loss
retry. The old reduced alarm form is removed. Shared passive-refresh focus and
disclosure restoration fails closed on authority/scope drift and respects user
focus movement. Root verified 386 Node and 152 Chromium scenarios, a subsequent
31-scenario focused Chromium pass, and the full actual-HA suite on exact staged
source; the RU mobile alarm review was visually checked. This does not certify
physical audibility or atomically pin target member epochs in `alarms.save`.

The owner-only guided Options summary is localized, same-entry, resumable and
read-only until a separate existing settings form is submitted. Actual HA
verified unchanged Engine, Options, modification time and runtime on open/finish;
2118 Python tests passed (three host skips, 23 subtests), with Ruff/format,
locale parity and privacy checks. The later post-create checkpoint above extends it.

Actual HA encrypted archive acceptance now creates one protected local archive,
rejects absent/wrong keys, compares all archived Family Assistant Store and media
bytes and rehydrates them through fresh application objects. It deletes only the
generated ID using the supported API and restores prior local-agent settings.
This is not a full HA restore, production backup operation or legacy migration.

Dashboard checkpoint: Today now presents bounded current role-projected tasks,
reviews, agenda, shopping, routines/alarms, presence, balances and attention.
Health labels are localized and unknown codes stay generic; notification review
checks current authority and refresh clears focused private forms after revocation.
Five dedicated cards explain unavailable states. Root verified 365 Node,
143 Chromium and the complete actual-HA suite alongside 2092 Python tests
(three host skips, 23 subtests), Ruff/format/locales/privacy. A visual Health
timestamp fix additionally passed three Chromium/31 focused Node checks.
Further focus, editors, onboarding and packaged/live acceptance remain open.

Private digest acceptance adds a named owner policy review and independent member
self-subscriptions, a seventeenth localized card and explicit-only authenticated
preview. Content is rebuilt under current authority immediately before private
Telegram delivery, never stored in the outbox or automatically quoted to models.
Global policy epochs prevent disable/re-enable or schedule ABA from reviving old
intents. Quiet hours do not extend expiry. Exact terminal marker/event retention
advances three compact monotonic dates in the same Store transaction, preventing
recreation after clock rollback; malformed lineage cannot poison those dates.
Counts-only diagnostics and HA Repairs expose capacity without recipient details.
The card invalidates displayed and in-flight previews on observed source revision
or module changes, without breaking an exact subscription lost-response retry.
The weekly half-open API window is displayed with an inclusive final date.
Actual HA verifies Options, authenticated WebSockets, delivery guards, Store reload
and Repairs. Narrow RU review and UK preview were visually inspected. Initial
failures exposed a test's overly strict whole-FlowResult comparison and a privacy
scanner traversal race with replaceable browser output. The scanner now prunes
excluded directories before traversal while still failing on source I/O errors.
See [digest guide](digests.md) and [concrete UI release gaps](ui-acceptance-gaps.md).

- 2073 Python tests passed, with 2 POSIX-specific CLI tests skipped on Windows and
  23 subtests. This checkpoint includes the digest lifecycle, source invalidation,
  retention-floor and public-scanner regressions alongside earlier domains.
  School retention includes real HA Store failure/reload and IssueRegistry checks.
  In-progress frontend-resource and backup-recovery code is excluded from this count.
- 334 frontend unit tests and 133 Chromium browser tests passed. The full Chromium
  run used two workers. Narrow RU poll review and photo-purge review were visually
  inspected; EN/RU/UK copy is included. The full isolated actual HA suite also passed.
- Presence source Options require a current owner with HA entity read permission,
  a named review and an exact current target-member epoch. A source binding is not
  consent: each HA-linked non-guest enables only their own sharing. Per-member
  source lineage revokes earlier consent on replacement/removal/re-add; an
  Engine-first source-pin commit and Options mismatch fail closed. An unrelated
  unchanged stale source stays inert without preventing another source's removal.
  Observations exist only in the authenticated WebSocket projection, not Engine
  views/storage, Telegram, models, diagnostics, history or device effects. Current
  HA permissions are checked before any source read; unavailable/stale evidence
  is unknown, named zones reduce to reported-away and attributes are never read.
  The EN/RU/UK card has named self-consent, exact retry and stale/private DOM cleanup.
  Root visually checked the narrow RU review. Actual HA verified Options, real
  registry/states, self-consent/replay, permission denial with zero reads, source
  replacement, module/member revocation and Store reload. Its read-observation
  fixture was corrected for HA StateMachine's read-only instance attributes.
  AGY's independent review found a stale target-member form race; transaction and
  form-boundary regressions now cover it. Configuration while the module is off is
  permitted preparation, never consent or observation. See [presence guide](presence.md).
- Full-suite testing also found two pre-existing fixture instabilities: random
  opaque poll tokens can coincidentally contain the short option string `O1`, so
  privacy assertions now validate exact descriptor fields/token grammar; recurring
  rule times have minute precision, so the actual-HA future tick is aligned to its
  minute and waits for any normal tick. No runtime timing/window was relaxed.
- Poll definitions and each member's private ballot have independent revisions.
  Fresh member/source authority, exact retries, revotes, close/archive/purge and
  aggregate privacy are enforced by the domain. The localized card and private
  Telegram confirmations use the same commands. Poll transport envelopes retain
  opaque descriptors, not questions/choices; delivery rechecks current identity,
  binding, source and expiry. Private bot poll quotes do not enter model context.
  Actual HA verified authenticated WebSockets, Telegram review/revote, module
  revocation, Store reload and replay without task/points/notification effects.
  Synthetic clock and reload-baseline helper issues were corrected before rerunning
  the complete suite; normal HA alarm-output shutdown is not a poll side effect.
  See [polls guide](polls.md).
- An explicit owner-only retained-photo purge detaches the exact task/report/media
  revision, immediately revokes HTTP reads and lets the collector unlink the blob.
  Task status, report text/history and other retained photos survive. The card has
  a named irreversible review and exact lost-response retry. Deleted tombstones
  expire after 24 hours with bounded cleanup and counts-only capacity diagnostics.
  Existing backups may still contain photos; no automatic retained-report purge or
  backup deletion is performed. Actual HA tested the complete lifecycle and retry.
  See [media retention](media-retention.md).
- Background notification receipts, Telegram updates and completed model answers
  wait for backup thaw while interactive mutations still reject frozen writes.
  Store failure retries saving an already generated answer without rerunning its
  provider within that process. Claim/dispatch/completion recheck current authority;
  revoked member epochs or bindings cancel stale replies. Actual HA ran the real
  Telegram polling/conversation loops through backup races and injected Store
  failures. Exactly-once model execution across a process crash is not claimed.
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
  tombstone capacity and retained-report purge are covered above; complete archive
  restore, maintenance documents and School imports remain gates.
  AGY's read-only review exposed the subprocess cancellation cleanup gap, fixed
  with spawn/reap regressions. A later review confirmed a crash-only hard-link/temp
  residue issue for the upcoming recovery slice; normal cancellation cleanup and
  exact-body Store-failure retry were independently checked, not assumed broken.
  See [task guide](tasks.md) and [media design](media-design.md).
- Bounded recovery now scans stale temporary files and opaque unreferenced blobs,
  re-stats exact file identity before deletion, and handles the two-name hard-link
  publication crash without deleting retained content. Malformed inventory blocks
  orphan guesses but does not stop independent valid expiry. Missing/corrupt
  retained bytes raise code-only health and leave report/history intact. Unit
  tests cover scan continuation, timestamps, hard links, malformed revisions,
  interrupted Store/cleanup and backup pause. Fresh `os.stat` is required on
  Windows because `DirEntry.stat` zeros inode/device/link-count fields there.
- Real HA discovers the backup platform and invokes its pre/post hooks. Media
  I/O drains before Engine freezing; partial acquisition and cancellation unwind
  in reverse order. Authenticated writes and new media requests are blocked while
  views stay readable. Actual HA proved coherent synthetic Store/blob copies,
  fresh Store/Engine reload with matching bytes, Options gating and exact replay.
  The first unload guard returned false; HA marked it `FAILED_UNLOAD`. It now
  waits outside the lifecycle lock for that backup generation to release, then
  completes normal reload. The entire isolated HA suite passed after this fix.
  Expected alarm-output shutdown receipts after thaw are distinct from the frozen
  copy; the latter is checked exactly. Actual encrypted archive creation and a
  full HAOS/container restore are not yet claimed.
- Recurring maintenance can require a private photo task report. Full replacement
  review preserves the choice on an omitted-field/title edit; domain, actual HA,
  Node and RU narrow browser review/exact retry passed. This does not enable
  initial fault photos or manual log/document attachments.
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
- School reminders now prune only exact old terminal marker/event pairs after
  35 days (90 days for failure), preserving pending, in-flight and uncertain
  outcomes. A monotonic retired-through date prevents clock rollback from
  recreating removed history, even with the module disabled. Creation checks
  both marker and retained-event capacity before every individual notification.
  Unpaired/malformed records and clock rollback produce counts-only diagnostic
  health and localized Repairs. The final exact staged-tree export passed the
  complete Python and isolated actual-HA suite with real HA Store persistence,
  injected pre-save failure, fresh Store reload and actual IssueRegistry. The
  first helper used MemoryStore; it was replaced before claiming durable HA
  acceptance. A remaining poll test wrongly forbade the chance substring `O2`
  in an opaque random token; exact descriptor grammar plus a deterministic
  `O2` token regression replaces that check. See [retention guide](school-retention.md).
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
  bc130a1 (run 34075063864), then verified private task photos
  732787b (run 34078178972). The school feature's first actual-HA CI run exposed
  a fixture race with scheduled pantry reconciliation; the follow-up drains
  pending HA work before the explicit clock pass and verifies scheduler health.
  The separate native RouterOS CI also passed (run 34040076386). Its first run
  had timed out downloading the official image; bounded download retries fixed
  that infrastructure issue. Every device effect rechecks authority after
  persisting intent. The calendar checkpoint passed the actual HA CI job too.
  The initial
  Python CI import-path difference was fixed with an explicit pytest root.
- Test prereleases through alpha.16 are published; no migration or HACS default submission yet.

Transport caveat: a timeout after Telegram accepts a message cannot be deduplicated
with sendMessage. The outbox marks it uncertain and does not blindly resend;
operator review/Repairs and explicit duplicate-aware retry are implemented. A successful siren
service call does not prove physical sound or volume.

## Next work

1. Extend language/context coverage and the LLM/search cascade; keep calendar
   calculations and authorization deterministic.
2. Complete module controls and localization; extend offline HACS acceptance with live bootstrap/card loading before household cutover.
3. Complete recurrence, reports, rewards and module parity, then LLM/search and
   extended family modules. Keep all unmet rows visible.
4. Extend native fault/IPv6/FastTrack topology coverage, richer Kid Control
   modes and fail-closed unknown-client controls. Hardware tests require explicit
   authorization, synthetic targets, exact pre-state and scoped cleanup.
5. Verify release CI/privacy scanning, migration/shadow verification and only then
   a tested release and controlled production cutover.

## Open engineering gates (not release-ready)

- Legacy pending plans without required revisions need explicit review during
  migration; do not silently rebase an old instruction to current household records.
- Advanced per-step routine conditions, alarm exceptions/delay fields and
  task-series editing now have reviewed card forms. Production acceptance is
  separate from the synthetic browser/HA checks documented above.
- No real bot has been contacted during development tests. Poller restart/Telegram
  conflict scenarios need further integration tests before the live cutover.
- Archive/retention strategy, comprehensive module health and migration are pending.
- Private media has bounded capacity/tombstone retention and explicit retained
  photo purge, including real-HA tests. Native encrypted Core restoration is now
  verified separately from archive creation and Store/media rehydration. Backup release
  failure keeps writes and reload gated until a successful unwind; its visible
  generation-bound Repair/retry now passes actual admin/non-admin HTTP tests.
  An active backup cannot be force-cleared. Native encrypted Core/Container
  archive restoration has since passed the isolated CI gate documented above;
  HAOS/Supervisor, history-database and live household restoration are not claimed.
- Opt-in real Qwen evaluation now runs against checked-in fictional fixtures only.
  It exposed schema, alarm-day and quote-planning defects; see model-evaluation.md.
  Wider language/model acceptance remains pending. Local Ollama was not started
  and production provider settings were not changed.
- Test every frontend/API flow with actual HA WebSocket transport, not only fixtures.
- All original vision modules and acceptance scenarios remain the goal.
