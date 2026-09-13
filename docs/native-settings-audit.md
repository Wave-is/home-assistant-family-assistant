# Native settings audit

Scope: public ConfigFlow/Options code on the home-next branch. Synthetic tests only;
no household configuration, production API or hardware was read or operated.
This is a settings inventory, **not a claim of complete legacy behavioral parity**.
The online-school branch is independent and is not included here.

## Every native route

`tests/test_native_settings_inventory.py` checks that every declared native step
appears below. Menu routing is not itself a configuration write. Referenced test
files are evidence locations; a listed HA scenario is not a claim it ran locally.
ConfigEntry Options are server-side private storage, never browser drafts.

| Native step | Inputs / route | Persistence and actual consumer | Evidence / status |
|---|---|---|---|
| `user` | name, owner_name, language, timezone, template | ConfigEntry.data; runtime new_state/household.apply_template, owner HA identity | ha_smoke, ha_panel_smoke; active admin and pinned HTTP caller |
| `modules` | CONFIGURABLE_MODULES booleans | ConfigEntry.data.modules, then canonical Store settings.modules | ha_smoke, test_module_runtime; explicit providers remain separate |
| `init` | next_step_id | grouped navigation only | test_ha_options_menu |
| `menu_family` | general, member, guided_onboarding, init | navigation only | test_ha_options_menu |
| `menu_telegram` | telegram, telegram_group, telegram_member, alarm_device, init | navigation only | test_ha_options_menu |
| `menu_ai` | conversation, ha_agent, search, articles, init | navigation only | test_ha_options_menu |
| `menu_services` | mikrotik, recipes, presence_sources, digests, init | navigation only | test_ha_options_menu |
| `menu_maintenance` | copy/prepare/resume, developer diagnostics, init | navigation only | test_ha_options_menu |
| `all_options` | flattened leaf navigation | no duplicate settings implementation | test_ha_options_menu |
| `general` | name, language, timezone, modules, automatic_penalties, daily_penalty_cap, pantry_expiry_reminders/days, school_preparation_reminders/days_before/time | Engine settings.save → Store; scheduler/domain court/pantry/school; module_runtime.watch handles unchanged Options | test_school_reminder_options, test_panel_settings, test_module_runtime, ha_smoke |
| `member` | member_id or _new | chooses profile, no write | ha_smoke, ha_member_revision_smoke |
| `edit_member` | name, role, language, ha_user_id/_none, active, aliases lines | Engine members.save; actor_for_ha, role/profile guards; omitted fields preserved | ha_member_revision_smoke; displayed revision fence |
| `guided_onboarding` | readiness links | read-only onboarding.readiness; no Options overwrite | test_onboarding_options, ha_onboarding_smoke |
| `guided_finish` | finish | read-only abort receipt | test_onboarding_options |
| `conversation` | enabled; primary/fallback URL, model, key, clear_key; fallback_enabled; allow_http; timeout | Options.conversation → runtime.async_configure_assistant → Ollama/Cascade; fallback.enabled false excludes it without deletion | test_provider_options, ha_settings_audit_smoke; fixed stale overwrite, disabled edits and fallback preservation |
| `search` | enabled, URL, api_key, clear_key, allow_http | Options.conversation.search → runtime Search; disabled config retained, legacy missing enabled means enabled | test_provider_options, ha_settings_audit_smoke; fixed destructive disable |
| `ha_agent` | enabled, entity_id, timeout | staged reviewed Options.conversation.ha_agent; supported existing HA agent only | test_ha_agent_options, ha_ha_agent_smoke |
| `ha_agent_review` | confirmed | current HA entity/binding proof then Options commit; disable removes reviewed binding, direct providers preserved | test_ha_agent_options |
| `articles` | enabled, allow_children | staged Options.articles policy | test_article_options, ha_article_smoke |
| `article_policy_review` | confirmed | enabled/allow_children/revision → ArticleService/guards; current owner and provider scope rechecked | test_article_options |
| `telegram` | enabled, token, clear_token | Options.telegram → TelegramManager; empty keeps token, explicit clear removes token+bot identity, disabled does no inspection | test_provider_options, ha_telegram_smoke; no credentials enter Store/view |
| `telegram_group` | start group invitation | Enrollment.issue → Store bounded invitation | ha_telegram_smoke, ha_panel_smoke; no inferred group identity |
| `telegram_member` | member | Enrollment.issue → one member invitation | ha_telegram_smoke; private chat scope |
| `telegram_wait` | polling / proceed | reads captured invitation; no fabricated success | ha_telegram_smoke |
| `telegram_confirm` | confirmed | Enrollment.confirm exact candidate → durable binding, then runtime refresh | ha_telegram_smoke, ha_panel_smoke; owner and candidate rechecked |
| `alarm_device` | member | selection only, hydrates exact member's next form | test_alarm_options; fixed blank/default editor |
| `alarm_device_settings` | entity_id, volume, enabled, confirmed; optional duration_entity_id/duration_seconds and volume_entity_id/select_volume; clear_duration/clear_volume | Options.alarm_devices[member] → Scheduler/AlarmDevices; read-only alarm_binding validation; same-device companion pin and cross-binding exact-entity exclusivity | test_alarm_options, ha_settings_audit_smoke; actual hardware audibility remains external gate |
| `mikrotik` | enabled, HTTPS URL, username, password, clear_password, CA PEM, allow_write, allow_kid_control, HA/management MAC, management_confirmed | Options.mikrotik → certificate_context/RouterClient/NetworkManager; protected identities and separate write capability | test_provider_options, network tests, ha_smoke; configuring uses read-only inspect, never a network mutation |
| `recipes` | enabled, URL, token, clear_token, allow_http, timeout | Options.recipes revision → Mealie source; local endpoint checks and read-only inspect | ha_recipes_smoke; disabled retains connection unless clear requested |
| `presence_sources` | member | pins the chosen member and current source; navigation only | test_presence_options, ha_presence_smoke |
| `presence_source_settings` | enabled, entity_id, presence_max_age_seconds | hydrates only the pinned member; stages source with identity revision and registered readable entity | test_presence_options, ha_presence_smoke; fixed first-member defaults |
| `presence_source_review` | confirmed | Engine source mirror then Options.presence_sources and max_age; reconcile_presence_sources uses reviewed identity, not current observations | test_presence_options; before/after Store await guards |
| `digests` | digest_morning_enabled/time, digest_evening_enabled/time, digest_weekly_enabled/time/weekday | staged domain policy and fingerprint | test_digest_options, ha_digests_smoke |
| `digest_policy_review` | confirmed | Engine settings.digest_policy, durable exact-operation retry → domain digests/scheduler | test_digest_options, test_digest_settings |
| `developer_diagnostics` | enabled | Engine settings.developer_policy, expected generation and exact retry; future technical observations only | test_developer_options; locally unavailable capability cannot be enabled |
| `legacy_copy` | copy_name, uploaded bundle, private_files_reviewed | validated isolated copy-flow session; no live target write yet | migration/copy_flow, copy-acceptance tests; separate explicit workflow |
| `legacy_copy_matches` | review_token, confirmed, discard_review | frozen member-match review | migration/copy_flow; identity/revision fence |
| `legacy_copy_review` | review_token, confirmed, discard_review | guarded isolated shadow copy and recovery journal, not replacement of the live household | ha_copy_resume_acceptance, migration tests |
| `legacy_copy_complete` | completion display | reviewed copy receipt; no configuration toggle | migration/copy_flow |
| `legacy_copy_residue` | review_token, confirmed, discard_review | explicitly reviewed residue cleanup in copy coordinator | copy-acceptance tests; not implicit cleanup |
| `legacy_prepare` | copy_name, assistant_export, court_export, additional_members, private_files_reviewed | server-side preparation session, uploaded exports only | migration/copy_prepare; no credentials inferred |
| `legacy_prepare_member` | review_token, confirmed, discard_review; member, archive_only | staged legacy member mapping | migration/copy_prepare |
| `legacy_prepare_reviewer` | review_token, confirmed, discard_review; reviewers | staged reviewer mappings | migration/copy_prepare |
| `legacy_prepare_photo` | review_token, confirmed, discard_review; photo upload | staged reviewed attachment mapping | migration/copy_prepare |
| `legacy_resume` | selected attempt, review/discard choice | copy_resume selects bounded durable recovery state | test_copy_resume, ha_copy_resume_smoke |
| `legacy_resume_review` | confirmation of frozen recovery plan | explicit coordinator resume; no silent redeployment | test_copy_resume, ha_copy_resume_smoke |

## Semantics and verified fixes

- Provider Options guard covers the actual active HA user, pinned HTTP caller,
  owner member epoch, loaded entry/runtime/Engine, full Options snapshot and
  canonical settings revision. Successful and failed inspection paths are fenced.
  A changed form aborts with conflict rather than silently rebasing. The guard is
  only for ConfigEntry-result steps; it is not a substitute for a pre-write Engine guard.
- Empty model/search keys keep the current secret at the same endpoint. Explicit
  clear wins, including while disabled. MikroTik and Telegram now have matching
  clear controls. Clearing while enabled still must pass normal provider validation.
- Search disable preserves reviewed connection fields; no query occurs. Re-enable
  inspects again. Runtime and guided readiness honor enabled:false. Search remains
  a model-assisted capability, not a standalone command subsystem.
- Disabled model, MikroTik and Telegram submissions now retain explicit edits:
  URL/model/timeout/HTTP policy, router identity/CA/write safeguards, and replacement
  bot token. Actual provider constructors perform local validation, with no transport
  for disabled providers. Changed endpoints cannot inherit old credentials: the
  owner must replace or explicitly clear them. A replacement Telegram token clears
  unverified old bot identity; a blank field keeps the current token.
- Fallback disable retains its connection under `enabled:false`, excludes it from
  the runtime Cascade, and re-enabling inspects it again. Legacy configurations
  without this flag remain enabled. Primary, HA agent, AGY and search configuration
  stay independent; direct primary settings are not required for an HA-only setup.
- Presence now selects a member before opening the source editor. Defaults and
  reviewed identity belong to that exact member; changing a source still does not
  grant presence consent. Domain, adapter and native projection tests keep consent
  separate from source selection, including revocation during awaited operations.
- Alarm selection no longer opens blank/default settings for an arbitrary member.
  Companion edits use the shared read-only validator; saved device identity is pinned.
  Disabling removes only that member's binding and does not need reachable hardware.
  Settings must not sound a siren; actual sending requires a durable desired alarm run.

## Remaining gaps / boundaries, not hidden success

1. Native edit_member does not show birth date/avatar; these are implemented in
   the authenticated control-center profile editor. Likewise alarms, court rules,
   presence policies, lists, routines, calendar, school and other card/domain
   settings are not missing merely because they are not ConfigEntry Options.
2. Hardware audibility, real model/provider reachability, unsupported agent types,
   and exact legacy feature/algorithm parity are not established by this audit.
   Private legacy comparison is a separate owner-coordinated workstream.
3. Existing-module runtime reconciliation is implemented by module_runtime.watch;
   an AGY finding claiming every general-setting switch leaves workers running
   was rejected after checking this consumer. Pre-update module signatures are
   intentional to allow catch-up after an Options update yields.

## Verification

Local provider Options/identity, alarm Options and native inventory tests passed,
including disabled endpoint/credential edits, fallback preservation, static
validation and secret-free form defaults. Full-suite totals, onboarding/domain
checks, syntax/lint, localization parity and privacy are tracked by the release run.
Dedicated real HA hook: `tests/ha_smoke.py --case settings`, calling
`verify_settings_audit(hass, user)` in `ha_settings_audit_smoke.py`. It uses real HTTP
Options routes, ConfigEntry persistence/reload, current runtime search selection,
fallback Cascade membership, disabled connection edits, real device/entity
registries and synthetic siren/number/select services. Provider
inspection is replaced at the external-I/O boundary. Run this case in isolated HA
CI; local syntax checks do not substitute for that execution. The first isolated
HA run exposed a real HTTP 500 caused by a non-serializable numeric validator.
After that repair and the additional provider-draft checks, fresh dedicated
settings and authenticated panel cases passed on actual HA 2026.8.2. The final
full native smoke also passed, including companion number/select/siren sequencing
and projection-scoped presence reads. It uses synthetic states and services,
not the household's hardware.
