# Guided onboarding and readiness design

Status: the pure readiness model, Options guide and shared menu route are
implemented and unit-tested. The complete actual Home Assistant 2026.8.2 run
verified localized open/finish/resume on the exact entry: Engine state, Options,
entry modification time and runtime identity remain unchanged. Release and an
automatic post-create handoff remain separate gates.

## Purpose and first slice

Vision section 9 describes a ten-part first-run wizard. The smallest safe first
slice is a localized, owner-only readiness guide layered over the existing Home
Assistant Config Flow and Options Flow. It improves discovery of the settings
that already exist; it does not introduce a second configuration store or make
optional providers prerequisites.

The existing two setup steps remain the only requirements for creating a
household:

1. household name, owner name, language, time zone and family template;
2. enabled modules.

The entry is usable after those steps. The guide then reports locally derived
status for household settings, members, modules, the household's own Telegram
bot, optional model/search providers and dedicated wake-up sirens. A user may
leave at any time and reopen the same guide later.

This slice deliberately does not add notification-policy editing, provider
installation, Telegram bot creation, siren testing, MikroTik setup or a final
claim that the household is production-ready. Those remain existing Options
steps or later gates.

## Home Assistant flow contract

Home Assistant data-entry flows, rather than frontend URLs, are the supported
navigation mechanism. The implementation should use `async_show_menu()` and
named `async_step_*` methods. It must not construct a private `/config/...` URL
or assume a frontend route. See the official documentation for
[data-entry flows](https://developers.home-assistant.io/docs/data_entry_flow_index/),
[config flows](https://developers.home-assistant.io/docs/core/integration/config_flow/)
and [options flows](https://developers.home-assistant.io/docs/core/integration/options_flow/).

Add `guided_onboarding` as the first choice in
`FamilyOptionsFlow.async_step_init`. `async_step_guided_onboarding` displays a
read-only summary and an `async_show_menu` whose choices route to the existing
steps:

| Guide choice | Existing step | Effect |
| --- | --- | --- |
| Household and modules | `general` | Existing reviewed Engine settings write |
| Family members | `member` | Existing member selector/editor |
| Own Telegram bot | `telegram` | Existing password selector and explicit connection check on submit |
| Private Telegram chat | `telegram_member` | Existing one-time enrollment and confirmation |
| Family Telegram group | `telegram_group` | Existing one-time enrollment and confirmation |
| Language model | `conversation` | Existing optional provider form and check on submit |
| Internet search | `search` | Existing optional SearXNG form and public synthetic check on submit |
| Dedicated wake-up siren | `alarm_device` | Existing entity selection and explicit confirmation |
| Finish for now | `guided_finish` | Reauthorize, then abort with localized `guided_finished`; no Options update listener runs |

Bot enrollment choices are omitted until this entry's Telegram runtime is
ready. Siren configuration is omitted when the alarms module is disabled.
Everything else may be shown with an `off` or `optional` status; the guide does
not turn a module on merely to open its form.

Each current Options step calls `async_create_entry` after a successful change,
so that Options Flow ends. The first slice must state that the user should open
**Settings > Devices & services > Integrations > Family Assistant > Configure**
again to continue. Refactoring every existing step into one long transaction is
not part of this slice.

An automatic post-create hand-off is a separate acceptance gate, not part of
this first implementation. If it is added on a supported Home Assistant version,
the Config Flow can use `async_on_create_entry()` and `next_flow` to open a newly
initialized Options Flow for the entry that was just created. The Options Flow's
initial input must select `guided_onboarding`; it must not search for an entry by
title or use the first Family Assistant entry. The intended Core API shape is:

```python
guided = await self.hass.config_entries.options.async_init(
    result["result"].entry_id,
    context={"user_id": self.context.get("user_id")},
    data={"guided": True},
)
result["next_flow"] = (FlowType.OPTIONS_FLOW, guided["flow_id"])
```

This hand-off needs an actual Home Assistant 2026.8 acceptance test before it is
enabled. Until then, an ordinary Options launch shows the normal menu with the
guide as its first item. Household creation cannot fail because of this optional
guide. There is no durable `first_run` flag. Neither flow mutates a `ConfigEntry`
object directly; current Options writes continue through the Options Flow result
(and title changes through `async_update_entry`).

## Exact entry and authority boundaries

Every render and every routed step is pinned to `self.config_entry.entry_id`.
Resolve runtime state only with:

```python
runtime = get_runtime(self.hass, self.config_entry.entry_id)
actor = runtime.engine.actor_for_ha(self.context.get("user_id"))
```

The actor must still be the current active `owner` on every step invocation,
including submission after a form has been left open. Do not accept HA admin
status as a substitute for household ownership. `FamilyOptionsFlow`'s existing
backup guard and per-step `_authorized_runtime()` checks remain authoritative.

Multiple config entries are separate households. Readiness must never aggregate
entries, pick `hass.data[DOMAIN]["entries"]` by iteration order, or infer that a
bot, chat, member, provider or siren belongs to another entry. Existing provider
steps may perform their deliberate cross-entry collision checks only when the
owner submits that step.

The sources of truth are intentionally split:

- `config_entry.data` is bootstrap data used to create a new Store. It must not
  be used for current member, module, language, name or time-zone readiness.
- `runtime.engine.snapshot()` is authoritative for current household settings,
  members, Telegram enrollments and module state.
- `config_entry.options` is authoritative for external connection options and
  device bindings.
- `runtime.telegram`, `runtime.assistant` and bounded code-only entries in
  `runtime.health` may refine the status of the current loaded runtime. Their
  absence is not permission to probe a network while rendering.

The guide stores no cursor, completion bit or copied status. Reopening it
recomputes readiness. This makes skip/resume safe across edits, restores,
upgrades, role changes and provider revocation without a new migration or ABA
problem.

## Pure readiness model

A private helper may construct the following in-memory value for the current
flow. It is not an Engine projection, WebSocket response, diagnostic export or
persisted option:

```text
ReadinessItem {
  key: household | members | modules | telegram | models | siren,
  status: ready | attention | optional | off,
  counts: bounded integer map,
  action: one existing Options step
}
```

Only bounded counts and status enums enter description placeholders. Never put
member names or IDs, HA user IDs, Telegram IDs/usernames, entity IDs, URLs,
model names, tokens, API keys, passwords, CA material, provider error text or
raw `runtime.health` values in a FlowResult.

Status means configuration discoverability, not an end-to-end health promise:

- `household`: `ready` when the authoritative name, language and time zone are
  structurally valid. This is normally guaranteed by the existing domain.
- `members`: counts active members, active HA-linked members and private
  Telegram-linked members. The current owner binding is required. Unlinked
  template placeholders are `attention`, not a security principal and not a
  blocker; a legitimate one-person household is ready.
- `modules`: count enabled modules from current Engine settings. Disabled
  optional modules are not failures.
- `telegram`: `off` when this entry's Telegram option is absent or disabled;
  `attention` when it is enabled but the saved bot metadata/current runtime is
  unavailable; otherwise `ready`. Group and private-link counts are hints, not
  a requirement. Never assume or recommend a shared bot.
- `models`: `off` when Conversation is disabled or its provider option is off;
  `attention` when explicitly enabled but no current assistant is available;
  otherwise `ready`. Search is an optional substatus. No model or search call is
  made by the guide.
- `siren`: `off` when Alarms is disabled, `optional` with no binding, otherwise
  `ready` with a count of bindings to current active members. This does not
  prove that an entity exists, is audible, is safe, or is currently available;
  only the existing siren step performs an explicit live validation.

Malformed state or options produce a generic `attention`/unavailable summary,
not raw exceptions or partial private values. The guide must remain read-only:
opening it performs no Engine command, Store save, config-entry update, reload,
provider request, Telegram enrollment, entity state read or device action.

## Secret and safety rules

Connection secrets stay exactly where current Options steps store them. The
guide neither copies them nor introduces `has_token` options. It may derive an
ephemeral boolean from structural presence, but it must discard that boolean
with the flow.

Password fields remain password selectors. Blank-secret preservation and
URL-change scope checks remain owned by the existing Telegram, model, search,
recipe and MikroTik steps. Readiness must not format even a prefix or suffix of
a secret. It also must not display bot/chat IDs or siren entity IDs.

Opening, skipping or finishing the guide changes no runtime. Choosing a route
does not change anything either; only the existing step's validated, confirmed
submission may persist. A connection failure leaves its prior options and
runtime untouched under the existing step contract.

## Localization contract

All guide titles, descriptions and menu choices belong under
`options.step.guided_onboarding`; the finish result uses
`options.abort.guided_finished`; status words use
`selector.onboarding_status.options`. These keys are mirrored exactly in
`translations/en.json`, `ru.json` and `uk.json`. Python contains keys and bounded
numbers only.

Core wording for the landing page:

| Language | Title | Safety/resume sentence |
| --- | --- | --- |
| EN | Guided family setup | Review what is configured and choose one area to continue. Optional services may stay off. You can close this guide and resume from Configure at any time. |
| RU | Пошаговая настройка семьи | Проверьте текущую настройку и выберите один раздел. Необязательные сервисы можно оставить выключенными. Закройте мастер и продолжите позже через «Настроить». |
| UK | Покрокове налаштування родини | Перевірте поточне налаштування й виберіть один розділ. Необов'язкові сервіси можна залишити вимкненими. Закрийте майстер і продовжте пізніше через «Налаштувати». |

Status translations must distinguish `optional/off` from `attention`; neither
may be translated as an error. Generated counts use placeholders and localized
nouns, not English concatenation.

## Acceptance tests for implementation

1. Actual HA Config Flow still creates and loads a useful household after the
   two existing forms with no provider, bot or siren.
2. The initial Config Flow does not start another flow in this slice. A later
   `next_flow` implementation must target the exact newly created entry and pass
   an actual HA acceptance test before it is enabled.
3. Reopening Configure for either of two entries computes only that entry's
   counts and options, even when both use similarly named members.
4. A current owner can open the guide. HA admin without household membership,
   a parent, a demoted owner and an inactive owner receive the existing generic
   authorization failure. Demotion while a menu/form is open is rechecked.
5. Opening, finishing and abandoning the guide leave Engine state, Store,
   config-entry data/options, audit and outbox byte-for-byte unchanged.
6. Provider/client/entity methods are instrumented to fail if called; rendering
   readiness still succeeds with zero network, registry, state or device reads.
7. Secret and identifier canaries placed in every current option/state field do
   not occur anywhere in the returned FlowResult or logs captured by the test.
8. Telegram/model/siren/module status transitions are driven only by a fresh
   same-entry snapshot/options/runtime. Disabled optional components are shown
   as `off`/`optional`, not setup failures.
9. Selecting each guide action reaches the existing step. Cancelling it writes
   nothing; a valid confirmed submission preserves that step's current stale
   revision, credential-scope and backup behavior.
10. Skip followed by a Store reload and Configure reopen recomputes the guide;
    no cursor or completion option exists.
11. `strings.json`, EN, RU and UK contain identical guide key/placeholder sets;
    Hassfest and a real Options Flow render pass without missing translations.
12. Existing Options menu and direct tests remain compatible; adding the guide
    does not silently reorder or invoke another existing step.

## Later increments

A later release may add dedicated notification policy editing, richer per-step
return navigation, Repairs links and an explicit final diagnostic run. Each
requires its own current-authority and no-side-effect contract. The readiness
guide alone is not evidence that Telegram delivery, a siren, a model, search or
any physical device has been tested in the user's environment.
