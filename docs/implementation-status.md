# Implementation and acceptance matrix

The product vision remains the scope. Status is explicit: planned, implemented,
unit-tested, HA-tested, hardware-tested, released. These are distinct gates.
Nothing is production-ready solely because a mock test passes.

| Requirement | Implementation | Verification / remaining gate |
| --- | --- | --- |
| Clean public source and HACS structure | In progress | No public release yet |
| Atomic persistence, idempotency, roles | Implemented / unit-tested | Disk faults, concurrent replay, revoked identities, batch rollback |
| Multiple households / member administration | Implemented / HA-tested | Config/options and bound HA identity; family templates pending |
| Separate shopping model | Implemented / unit-tested | Partial purchase and approvals; recurring/media/price extensions pending |
| Tasks, deadlines, reports and reviews | In progress | Legacy parity and media pending |
| Court, rewards, penalties and appeals | In progress | Automatic settlement/rewards pending |
| Alarms and durable fresh challenges | Implemented / unit- and HA-tested | Two stages, renewed siren, fresh nonce, expiry, DST, exceptions, penalty cap; physical sound check pending |
| Own Telegram bot and onboarding | Implemented / HA-tested with synthetic transport | Options, polling lifecycle, owner-confirmed enrollment, mentions, replay/roles; live Telegram acceptance still pending |
| LLM, search, command repair | Planned | Adapters, bounded tools, privacy |
| RU / UK / EN | In progress | Existing forms/cards/errors translated; Telegram/docs and future modules pending |
| Today and module cards | Six cards browser-tested | Today/shopping/tasks/court/alarms/health; richer editors and other module cards pending |
| Routines and family calendar | Planned | Recurrence, catch-up, time zones |
| Durable notifications / incident closure | Core unit- and HA-tested | Fanout, retries, quiet hours, uncertainty; Telegram wiring, Repairs and explicit review/retry UI |
| Corrections / journal / local learning | In progress | Journal foundation only |
| Pantry, meals, school, maintenance | Planned | APIs, scheduling and cards |
| Polls, digests, presence | Planned | Consent, permissions and fallbacks |
| MikroTik inventory / HA matching | Planned | Router fixtures + read-only live checks |
| Static leases / comments | Planned | Preview, ownership, read-back, compensation |
| Kid Control including Telegram parents | Planned | Schedule vs override, autonomy |
| Unknown clients / allowlist | Planned | Topology + IPv6 + local rollback prerequisite |
| Diagnostics / Repairs / backup / migration | Planned | No live legacy data modified |
| Release CI and secret checks | In progress | Local privacy/catalog checks pass; CI configured, GitHub HACS/Hassfest run pending |
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

- 86 Python tests passed (domain, device adapter, outbox, Telegram API/enrollment, public contracts).
- 6 frontend unit tests and 8 Chromium browser tests passed.
- Ruff lint and formatting passed.
- Real HA smoke: Config/Options Flow, owner-linked authenticated service,
  entity setup, explicit siren opt-in, actual siren service parameter validation,
  continuous renewal, alternating tones, answer stops sound, Store reload/unload.
- Real HA Telegram options, group and private enrollment, owner confirmation,
  addressed mention reply, duplicate update and unauthorized-command rejection:
  passed with a synthetic Telegram client and no network access.
- Mobile Ukrainian wake-up and Russian shopping screenshots visually inspected.
- Private legacy family-only suite: 397 tests passed.
- No production family module, Telegram bot, router or siren has been changed.
- Public development repository created at Wave-is/home-assistant-family-assistant.
- HACS and Hassfest passed on GitHub. Frontend CI passed. The first Python CI
  run exposed a test import-path difference; an explicit pytest root fixes it.
- No public release, migration or HACS default submission yet.

Transport caveat: a timeout after Telegram accepts a message cannot be deduplicated
with sendMessage. The outbox marks it uncertain and does not blindly resend;
operator review/Repairs and explicit duplicate-aware retry are implemented. A successful siren
service call does not prove physical sound or volume.

## Next work

1. Expand deterministic language/context handling and test callback/end-to-end routing.
2. Improve the setup guide, templates, translations and visual editors.
3. Complete recurrence, reports, rewards and module parity, then LLM/search and
   extended family modules. Keep all unmet rows visible.
4. Implement and independently test MikroTik plans/read-back/rollback and parents'
   Telegram controls. No live router changes during development tests.
5. Add release CI/privacy scanning, migration/shadow verification and only then
   a tested release and controlled production cutover.

## Open engineering gates (not release-ready)

- Some controls are still API-only: advanced alarm exceptions/delay fields,
  per-item partial buying, task checklists/revision, appeals.
- No real bot has been contacted during development tests. Poller restart/Telegram
  conflict scenarios need further integration tests before the live cutover.
- Archive/retention strategy, comprehensive module health and migration are pending.
- Test every frontend/API flow with actual HA WebSocket transport, not only fixtures.
- All original vision modules and acceptance scenarios remain the goal.
