# Control center and migration repair

The September control-center changes require renewed acceptance. The incoming
working tree contained a demonstration panel with household examples, simulated
connection checks and unverified endpoints. Those paths are being replaced and
re-tested; previous release labels do not prove that new paths work.

## Execution plan

1. Compare the running installation, canonical domain, old adapters and current
   changes; preserve existing data and unrelated work.
2. Replace demonstration state with authorized household projections. Implement
   the five sections (overview, members, capabilities, connections, advanced),
   independent module settings, member profiles and a durable four-step guide.
3. Share validation, revisions and persistence between the panel and native
   flows. Resolve the actual authenticated HA user; never substitute an owner.
4. Repair Telegram/court/provider regressions and verify legacy command parity
   against the same ledger, schedules and task lifecycle.
5. Verify domain transactions, browser interactions, real HA API/flow transport,
   reload, multilingual copy, privacy and packaging before release or cutover.

## Settings map

| Stored keys | Section | Validation / authority | Verification |
| --- | --- | --- | --- |
| Store settings: name, language, timezone | Family / guide | settings handler, owner, revision | partial save, reload, stale window |
| Store members: name, role, aliases, language, active, HA identity | Members | members handler, owner, member revision, last-owner check | preserve links, duplicate identity, replay |
| Optional birth_date, avatar | Members / additional | bounded date and bundled preset, owner | no default personal values, clear explicitly |
| Store settings.modules | Capabilities | known modules, owner, revision | disable retains records and settings |
| automatic_penalties, daily_penalty_cap | Court / rules | existing settings handler; zero cap means no automatic penalties | unchanged semantics, no implicit activation |
| Court period/report policy, rewards | Court / advanced | existing court commands | canonical ledger and configured period |
| school_preparation_*; school records/subscriptions | School / member school | existing settings and school handlers | shared data, recipients and next-run preview |
| pantry_expiry_*; pantry subscriptions | Pantry | existing settings/pantry handlers | scoped save and delivery rules |
| digest_*; digest subscriptions | Digests / member notifications | existing digest policy/subscription handlers | preserve policy epochs and personal scope |
| Telegram options; Store telegram/enrollments | Connections / member accounts | HA authenticated owner, existing enrollment | distinct transport observations, confirmed single-use invites |
| conversation, search, article options | Connections / understanding | native owner flows and existing providers | no secrets in panel, nonexecuting intent test |
| Network options and managed profiles | Connections / network | existing reviewed network workflows | no implicit router effects |
| Alarm records and output options | Alarms / member | existing alarm commands and device options | no sound or penalties during preview |
| Presence source options and consents | Presence / member | native consent/source handlers | no invented presence status |
| Recipes options, maintenance, polls, calendar, routines, price watches | Corresponding capability | existing handlers/cards and native options | retained records, supported actions |
| Developer consent, migration, backup | Advanced | existing owner/admin checks | no credential export or automatic cutover |
| Store onboarding | Guide | owner, independent revision | back/skip/resume after reload without side effects |

Existing native forms remain compatible technical configuration routes and use
the same data. Unknown stored settings are preserved. Provider health, enabled
state and verified transport observations are distinct; missing evidence is
shown as unverified. Technical tests do not send household messages or activate
devices.

## Fresh acceptance and outstanding work

The authenticated panel REST/WS scenario passed against a network-isolated
Home Assistant 2026.8.2 container: real caller identity, cross-administrator
rejection, native options, canonical member/settings saves, stale edit rejection,
nonexecuting recognition preview, guide Store reload and panel unload/reload.
The extended case also passed owner/member/group Telegram enrollment using
synthetic transport, mismatched-candidate rejection, exact acknowledgement-loss
retry and no invitation secret in the saved projection.

The final full Python repair run passed 4,953 tests and 23 subtests, with five
skips. JavaScript passed 189 pretests and 501 main tests; Chromium passed all 253
browser scenarios, including mobile/dark mode and EN/RU/UK member contexts.
Public-tree privacy, locale synchronization, Ruff and deterministic packaging
passed. Browser-debug artifacts are outside publishable source.

The final full real-HA scenario passed on HA 2026.8.2 with no network, household
credentials or production mounts. It exercised actual native Options, authenticated
WebSockets, Telegram transport fixtures and isolated image decoding, task photos,
court, alarms, module settings, shadow copy, Store/reload and unload. Photo reports
were verified through real MediaStorage and private authenticated byte retrieval,
not a mocked invented upload interface. Native tests follow the actual grouped
menus; synthetic update IDs cannot reuse directly processed callback IDs.

The separate two-process update test passed from the exact published 0.1.1 code
to 0.2.0-rc.1, preserving synthetic Config Entry, Options, identities and domain
records. All nine CI jobs passed at the initial repair commit `0f462d3`, including
real HACS installation, encrypted restore and copy-resume across processes.
Final review also repaired the compatibility module-toggle endpoint: its stable
caller intent is now hashed before deriving a merged module list under the Engine
lock. A response-loss retry after another window's edit returns the original
receipt without reverting the other edit. Fresh real-HA panel acceptance passed.
The follow-up candidate still requires its own CI run.

Current runtime package: 295 files, 1,083,155 archive bytes; SHA-256
`f2812b5b2581d17722f42e1538ff70198c7d02727dc203658e426912dd7e07ef`.
Actual household/device acceptance is an independent gate.

Implemented repair areas include the real five-section control center, member
profiles and immutable retry requests, Telegram enrollment, generic court parser
and reporting rules, deterministic legacy task/shopping/alarm commands, durable
photo/model jobs, quota cooldown and factual transport observations. No migrated
alarm, siren, penalty policy or router rule is activated by these repairs.

Court entities contain personal score information and do not inherit the family
panel's per-member authorization. New score entities are disabled by default;
enabling them explicitly publishes their states to HA's entity-access model.
Existing entity-registry choices are retained, not silently changed.

Remaining work must not be disguised as completed migration:

- Home/energy/environment status and device controls need generic owner-configured
  mappings and verified permitted actions; private household constants must not
  be copied into the public integration.
- Telegram voice messages need a configured STT path; the existing native Assist
  voice-shopping support does not provide Telegram voice support.
- Personal/family conversational memory and short clarification follow-ups need
  durable actor scopes, retention and secret rejection.
- Unified in-panel model configuration still uses native technical Options for
  credentials and providers. Recognition previews currently test deterministic
  parsing without executing actions, not the selected model's response quality.
- Imported alarm schedules are intentionally disabled, gentle and penalty-free.
  Their exact original settings remain in the migration archive. Reviewed
  activation/output mapping and physical audibility are still required; a green
  module switch cannot be considered proof that an alarm will sound.
- The archived legacy delivery-gated weekly reset is not reproduced as a destructive
  reset of lifetime points. Current public weekly totals use configured periods,
  while immutable history and lifetime balances remain intact.
- Household cutover, actual Telegram acceptance, live device tests and promotion
  of a release require their independent backup/validation/authorization gates.

### Additional closed paths

- Module switches now reconcile configured conversation/network services without
  restarting HA or the Telegram poller. Unknown external health is not displayed
  as verified success.
- School, alarms and digests cards support optional `member_id`. School also
  supports `school_section: all|reminders`. This filters display/defaults and
  guards writes, but never changes authorization or impersonates the selected
  member. School reminders clearly identify the signed-in recipient; another
  person's private digest preferences require that person's login.
- Telegram photo task reports use one verified file with `/report T000001` or
  an exact receipted task-prompt reply. A durable bounded queue pins actor/task/
  configuration revisions and supports restart. Albums, extra caption notes and
  ambiguous/forged task replies are rejected explicitly; no model selects tasks.
- Saved profile timestamps, optional avatars/birth dates and existing Telegram
  identities no longer make a reviewed shadow copy fail. Exact copy verification
  and all shadow no-worker/no-device-effect fences remain in force.
