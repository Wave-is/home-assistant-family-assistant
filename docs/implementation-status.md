# Implementation and acceptance matrix

The product vision remains the scope. Status is explicit: planned, implemented,
unit-tested, HA-tested, hardware-tested, released. These are distinct gates.
Nothing is production-ready solely because a mock test passes.

| Requirement | Implementation | Verification / remaining gate |
| --- | --- | --- |
| Clean public source and HACS structure | In progress | No public release yet |
| Atomic persistence, idempotency, roles | Implemented / unit-tested | Disk faults, concurrent replay, revoked identities, batch rollback |
| Multiple households / member administration | Implemented / HA-tested | Config/options, four generic templates, time zone, aliases and bound HA identity |
| Separate shopping model | In progress / unit-, browser- and HA-tested | Partial purchase, approvals, recurring items and parent editor; merging/media/price/history extensions pending |
| Tasks, deadlines, reports and reviews | In progress | Text lifecycle, repeat duties/rotation, reminders, paired overdue incidents and opt-in idempotent penalties tested; legacy parity and media pending |
| Court, rewards, penalties and appeals | In progress | Automatic settlement/rewards pending |
| Alarms and durable fresh challenges | Implemented / unit- and HA-tested | Two stages, renewed siren, fresh nonce, expiry, DST, exceptions, penalty cap; physical sound check pending |
| Own Telegram bot and onboarding | Implemented / HA-tested with synthetic transport | Options, polling lifecycle, owner-confirmed enrollment, mentions, replay/roles; live Telegram acceptance still pending |
| LLM, search, command repair | In progress / unit- and HA-tested | Own Ollama/fallback, bounded plans, confirmed mutations, SearXNG snippets and standard Assist entity; real-model eval, full article fetching and external agent delegation pending |
| RU / UK / EN | In progress | Existing forms/cards/errors translated; Telegram/docs and future modules pending |
| Today and module cards | Eight cards browser-tested | Today/shopping/tasks/court/alarms/conversation/network/health; richer editors and other module cards pending |
| Routines and family calendar | Planned | Recurrence, catch-up, time zones |
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

- 357 Python tests passed (domain, adapters, outbox, Telegram, model/search isolation, language/context, recurring tasks/purchases and incidents, network inventory/lease/Kid Control effects and status, lab fixtures, public contracts).
- 25 frontend unit tests and 20 Chromium browser tests passed.
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
- Recurring duty creation/rotation is browser-tested on mobile; the real HA
  scheduler generated one ordinary task instance. Daily, weekly, monthly,
  exclusions, DST, bounded catch-up and Store faults are unit-tested.
- Due reminders, parent-review exemption, one penalty per task, pending-alert
  supersession and paired closure after sent/in-flight/uncertain notices are tested.
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
- All five GitHub check jobs passed on checkpoint 18df770 (run 34041486164).
  The separate native RouterOS CI also passed (run 34040076386). Its first run
  had timed out downloading the official image; bounded download retries fixed
  that infrastructure issue. Every device effect rechecks authority after
  persisting intent. The recurring-purchase checkpoint is locally verified here.
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
  per-item partial buying, task checklists/revision, appeals.
- No real bot has been contacted during development tests. Poller restart/Telegram
  conflict scenarios need further integration tests before the live cutover.
- Archive/retention strategy, comprehensive module health and migration are pending.
- Live model evaluation is pending; local Ollama was not reachable on its default
  port during this checkpoint. No server was started or production provider changed.
- Test every frontend/API flow with actual HA WebSocket transport, not only fixtures.
- All original vision modules and acceptance scenarios remain the goal.
